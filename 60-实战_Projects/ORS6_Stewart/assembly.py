#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORS6_Stewart · assembly — 统一装配器 (CadQuery+OCP + FreeCAD 双路径)

归一前: ors6_freecad_build.py (866行) + ors6_cq_build.py (534行)
       + freecad_assembly.py (187行) = 1587 行三处实现

归一后: 此文件 (~500 行) 两条装配路径共用:
  - StewartIK (来自 kinematics.py, 唯一实现)
  - PARTS / STL_ROOT / RECV_PARTS / DEFAULT_HIDDEN (来自 parts.py)

装配层次:
  A. Static structural parts — 真实 STL 原位导入
  B. Servo arms — 4× Arm STL (镜像+IK旋转) + 2× Pitcher STL (IK旋转)
  C. Receiver + T-wist group — elevate to HOME_H + IK 位姿 + 齿轮 twist
  D. Parametric rods — IK arm_tip → recv_mount (参数化圆柱+球头)

Output: 输出到 `60-实战_Projects/ORS6_Stewart/output/ORS6_<label>.{step,stl,FCStd}`
"""
from __future__ import annotations

import json
import math
import os
import time
import warnings
from typing import Any, Dict, List, Optional, Tuple

from .parts import (PARTS, STL_ROOT, HOME_H, RECV_PARTS, DEFAULT_HIDDEN,
                    SR6, SERVO_SLOTS, stl_path)
from .kinematics import StewartIK, TCODE_HOME
from .poses import MOTION_POSES

Pose6 = Tuple[int, int, int, int, int, int]

# Output directory (relative to this project)
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Arm STL hub center (trimesh-verified spline bore center)
ARM_PIVOT: Tuple[float, float, float] = (67.5, 0.0, 51.5)

# Frame X offset for pitch arm rotation pivot
FRAME_X = 99.6

# Servo arms are 4 main instances of Arm STL + 2 separate pitcher STLs
_INSTANCED = {"Arm", "L_Pitcher", "R_Pitcher"}

# Rod geometry defaults
ROD_BODY_D = 6.0
ROD_END_D = 10.0


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _color_rgb(color_hex: int) -> Tuple[float, float, float]:
    return (((color_hex >> 16) & 0xFF) / 255.0,
            ((color_hex >> 8) & 0xFF) / 255.0,
            (color_hex & 0xFF) / 255.0)


def _compute_ik(pose: Pose6) -> Dict[str, Any]:
    """Compute full IK for one pose + reference home (for arm angle delta)."""
    ik = StewartIK()
    geom = ik.compute_full_geometry(*pose)
    home = ik.compute_full_geometry(*TCODE_HOME)
    recv_pose = ik.compute_receiver_pose(*pose)
    return {
        "arm_tips": geom["arm_tips"],
        "recv_mounts": geom["recv_mounts"],
        "arm_angles": geom["arm_angles"],
        "home_angles": home["arm_angles"],
        "recv_pose": recv_pose,  # (tx, ty, tz, roll_deg, pitch_deg, twist_deg)
    }


# ══════════════════════════════════════════════════════════════════════════════
# CadQuery + OCP path (preferred — no FreeCAD dependency)
# ══════════════════════════════════════════════════════════════════════════════

def build_cadquery(pose: Pose6 = TCODE_HOME,
                   label: str = "home",
                   full_step: bool = False,
                   output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Build Stewart assembly via CadQuery + OCP (STL→BREP bridge).

    Args:
        pose: T-Code pose (L0, L1, L2, R0, R1, R2).
        label: output filename suffix.
        full_step: if True, export full assembly to STEP (~480MB per pose!).
                   Default False exports only BREP rods (~200KB).
        output_dir: override OUTPUT_DIR.

    Returns dict with paths, stats, rod lengths.
    """
    import cadquery as cq
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere
    from OCP.gp import (gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec)
    from OCP.StlAPI import StlAPI_Reader
    from OCP.TopoDS import TopoDS_Shape

    out_dir = output_dir or OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    ik = _compute_ik(pose)
    tx, ty, tz_stl, roll_deg, pitch_deg, twist_deg = ik["recv_pose"]
    recv_dz = tz_stl - HOME_H

    t0 = time.time()
    assy = cq.Assembly(name="ORS6")
    _rod_parts: List[Tuple[str, Any, Any]] = []
    loaded = 0

    # ---- helpers ----
    def _load_stl_shape(name: str):
        path = stl_path(name)
        if not os.path.exists(path):
            return None, None
        reader = StlAPI_Reader()
        shape = TopoDS_Shape()
        reader.Read(shape, path)
        if shape.IsNull():
            return None, None
        return shape, _color_rgb(PARTS[name][2])

    def _mirror_x(shape):
        t = gp_Trsf()
        t.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)))
        return BRepBuilderAPI_Transform(shape, t, True).Shape()

    def _arm_trsf(piv, shaft, angle_delta_deg):
        t1 = gp_Trsf(); t1.SetTranslation(gp_Vec(-piv[0], -piv[1], -piv[2]))
        rot = gp_Trsf(); rot.SetRotation(
            gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), math.radians(angle_delta_deg))
        t2 = gp_Trsf(); t2.SetTranslation(gp_Vec(shaft[0], shaft[1], shaft[2]))
        return t2.Multiplied(rot.Multiplied(t1))

    def _make_rod(p1, p2):
        dx, dy, dz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 0.1:
            return BRepPrimAPI_MakeSphere(gp_Pnt(*p1), ROD_END_D / 2).Shape()
        d = gp_Dir(dx / length, dy / length, dz / length)
        cyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*p1), d),
                                       ROD_BODY_D / 2, length).Shape()
        s1 = BRepPrimAPI_MakeSphere(gp_Pnt(*p1), ROD_END_D / 2).Shape()
        s2 = BRepPrimAPI_MakeSphere(gp_Pnt(*p2), ROD_END_D / 2).Shape()
        return BRepAlgoAPI_Fuse(BRepAlgoAPI_Fuse(cyl, s1).Shape(), s2).Shape()

    # ── A. Static structural parts ──
    static_parts = [n for n in PARTS
                    if n not in RECV_PARTS and n not in DEFAULT_HIDDEN
                    and n not in _INSTANCED]
    for pname in static_parts:
        shape, rgb = _load_stl_shape(pname)
        if shape:
            assy.add(cq.Shape(shape), name=pname, color=cq.Color(*rgb))
            loaded += 1

    # ── B. Servo arms (4 main + 2 pitcher) ──
    arm_raw, arm_rgb = _load_stl_shape("Arm")
    arm_count = 0
    if arm_raw:
        for sname, stype, sx, sy, _sign in SERVO_SLOTS:
            if stype != "main":
                continue
            is_left = sx < 0
            shape = _mirror_x(arm_raw) if is_left else arm_raw
            piv = (-ARM_PIVOT[0] if is_left else ARM_PIVOT[0],
                   ARM_PIVOT[1], ARM_PIVOT[2])
            shaft = (sx, sy, SR6["servoPivotH"])
            delta = math.degrees(ik["arm_angles"][sname] - ik["home_angles"][sname])
            trsf = _arm_trsf(piv, shaft, delta)
            assy.add(cq.Shape(shape), name=f"Arm_{sname}",
                     color=cq.Color(*arm_rgb), loc=cq.Location(trsf))
            arm_count += 1
            loaded += 1

    for pname in ["L_Pitcher", "R_Pitcher"]:
        shape, rgb = _load_stl_shape(pname)
        if not shape:
            continue
        sname = "LeftPitch" if "L_" in pname else "RightPitch"
        delta = math.degrees(ik["arm_angles"][sname] - ik["home_angles"][sname])
        if abs(delta) > 0.01:
            sx = -FRAME_X if "L_" in pname else FRAME_X
            rot = gp_Trsf()
            rot.SetRotation(gp_Ax1(gp_Pnt(sx, 0, SR6["servoPivotH"]),
                                   gp_Dir(0, 1, 0)), math.radians(delta))
            assy.add(cq.Shape(shape), name=pname,
                     color=cq.Color(*rgb), loc=cq.Location(rot))
        else:
            assy.add(cq.Shape(shape), name=pname, color=cq.Color(*rgb))
        arm_count += 1
        loaded += 1

    # ── C. Receiver + T-wist group ──
    _RECV_VISIBLE = [n for n in RECV_PARTS if n not in DEFAULT_HIDDEN]
    recv_count = 0
    for pname in _RECV_VISIBLE:
        shape, rgb = _load_stl_shape(pname)
        if not shape:
            continue
        base_trsf = gp_Trsf()
        base_trsf.SetTranslation(gp_Vec(tx, ty, HOME_H + recv_dz))
        combined = base_trsf
        if abs(roll_deg) > 0.01 or abs(pitch_deg) > 0.01:
            r_roll = gp_Trsf()
            r_roll.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)),
                               math.radians(roll_deg))
            r_pitch = gp_Trsf()
            r_pitch.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)),
                                math.radians(pitch_deg))
            combined = base_trsf.Multiplied(r_pitch.Multiplied(r_roll))
        if pname in ("RingGear", "ExchangeGear", "DriveGear"):
            tw_sign = 1 if pname == "RingGear" else -1
            r_tw = gp_Trsf()
            r_tw.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)),
                             math.radians(tw_sign * twist_deg))
            combined = combined.Multiplied(r_tw)
        transparency = 0.3 if pname == "Receiver" else 0.0
        assy.add(cq.Shape(shape), name=pname,
                 color=cq.Color(*rgb, 1.0 - transparency),
                 loc=cq.Location(combined))
        recv_count += 1
        loaded += 1

    # ── D. Parametric rods (6, BREP) ──
    rod_stats: List[Dict[str, Any]] = []
    for sname, stype, _sx, _sy, _sign in SERVO_SLOTS:
        tip = ik["arm_tips"][sname]
        mount = ik["recv_mounts"][sname]
        rod_shape = _make_rod(tip, mount)
        rod_len = math.sqrt(sum((a - b) ** 2 for a, b in zip(tip, mount)))
        # mount 与 tip 共面 (Y=sy) 后 rod 恒 175mm (firmware 2D IK)
        nominal = 175.0
        stress = abs(rod_len - nominal) / nominal
        g_col = max(0.0, 0.85 - stress * 8)
        rod_color = cq.Color(0.30, g_col, 0.91)
        assy.add(cq.Shape(rod_shape), name=f"Rod_{sname}", color=rod_color)
        _rod_parts.append((f"Rod_{sname}", rod_shape, rod_color))
        rod_stats.append({"servo": sname, "rod_3d_mm": round(rod_len, 1),
                          "stress_pct": round(stress * 100, 1)})
        loaded += 1

    elapsed_build = time.time() - t0

    # ── Export ──
    step_path = os.path.join(out_dir, f"ORS6_{label}.step")
    brep_assy = cq.Assembly(name="ORS6_BREP")
    for rname, rshape, rcolor in _rod_parts:
        brep_assy.add(cq.Shape(rshape), name=rname, color=rcolor)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        brep_assy.save(step_path, exportType="STEP")
    step_kb = round(os.path.getsize(step_path) / 1024, 1)

    full_step_path: Optional[str] = None
    full_step_kb = 0
    if full_step:
        full_step_path = os.path.join(out_dir, f"ORS6_{label}_full.step")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            assy.save(full_step_path, exportType="STEP")
        full_step_kb = round(os.path.getsize(full_step_path) / 1024, 1)

    stl_out = os.path.join(out_dir, f"ORS6_{label}.stl")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            assy.save(stl_out, exportType="STL", ascii=False)
        stl_kb = round(os.path.getsize(stl_out) / 1024, 1)
    except Exception as e:
        stl_out = None
        stl_kb = 0

    elapsed_total = time.time() - t0

    return {
        "ok": True,
        "label": label,
        "engine": "cadquery+ocp",
        "pose": {"L0": pose[0], "L1": pose[1], "L2": pose[2],
                 "R0": pose[3], "R1": pose[4], "R2": pose[5]},
        "receiver": {"tx": round(tx, 2), "ty": round(ty, 2),
                     "tz_stl": round(tz_stl, 2), "home_h": HOME_H,
                     "roll_deg": round(roll_deg, 2),
                     "pitch_deg": round(pitch_deg, 2),
                     "twist_deg": round(twist_deg, 2)},
        "arm_angles_deg": {k: round(math.degrees(v), 2)
                           for k, v in ik["arm_angles"].items()},
        "rods": rod_stats,
        "parts_count": loaded,
        "static_count": len(static_parts),
        "arm_count": arm_count,
        "recv_count": recv_count,
        "step_path": step_path, "step_kb": step_kb,
        "full_step_path": full_step_path, "full_step_kb": full_step_kb,
        "stl_path": stl_out, "stl_kb": stl_kb,
        "build_s": round(elapsed_build, 2),
        "total_s": round(elapsed_total, 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# FreeCAD path (requires FreeCAD 1.0)
# ══════════════════════════════════════════════════════════════════════════════

def build_freecad(pose: Pose6 = TCODE_HOME,
                  label: str = "home",
                  doc=None,
                  output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Build Stewart assembly inside FreeCAD (must run with FreeCADCmd.exe or FreeCAD GUI)."""
    import FreeCAD as App
    import Mesh
    import Part
    from FreeCAD import Base

    out_dir = output_dir or OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    ik = _compute_ik(pose)
    tx, ty, tz_stl, roll_deg, pitch_deg, twist_deg = ik["recv_pose"]
    recv_dz = tz_stl - HOME_H

    t0 = time.time()
    doc = doc or App.newDocument(f"ORS6_{label}")
    parts_placed: Dict[str, Any] = {}

    def _load_static(name: str, label_name: Optional[str] = None):
        if name not in PARTS:
            return None
        path = stl_path(name)
        if not os.path.exists(path):
            return None
        obj = doc.addObject("Mesh::Feature", label_name or name)
        obj.Mesh = Mesh.Mesh(path)
        rgb = _color_rgb(PARTS[name][2])
        # headless-safe: ViewObject is None in FreeCADCmd.exe
        if getattr(obj, "ViewObject", None) is not None:
            obj.ViewObject.ShapeColor = rgb + (0.0,)
        return obj

    # ── A. Static structural ──
    static_parts = [n for n in PARTS
                    if n not in RECV_PARTS and n not in DEFAULT_HIDDEN
                    and n not in _INSTANCED]
    for pname in static_parts:
        obj = _load_static(pname)
        if obj:
            parts_placed[pname] = obj

    # ── B. Servo arms ──
    arm_path = stl_path("Arm")
    arm_hex = PARTS["Arm"][2]
    arm_col = _color_rgb(arm_hex)
    for sname, stype, sx, sy, _sign in SERVO_SLOTS:
        if stype != "main":
            continue
        mesh = Mesh.Mesh(arm_path)
        mirror_x = sx < 0
        if mirror_x:
            mat = App.Matrix()
            mat.A11 = -1
            mesh.transform(mat)
        obj = doc.addObject("Mesh::Feature", f"Arm_{sname}")
        obj.Mesh = mesh
        piv = Base.Vector(-ARM_PIVOT[0] if mirror_x else ARM_PIVOT[0],
                          ARM_PIVOT[1], ARM_PIVOT[2])
        shaft = Base.Vector(sx, sy, SR6["servoPivotH"])
        translate = shaft - piv
        delta = math.degrees(ik["arm_angles"][sname] - ik["home_angles"][sname])
        rot = App.Rotation(Base.Vector(0, 1, 0), delta)
        obj.Placement = App.Placement(translate, rot, piv)
        if getattr(obj, "ViewObject", None) is not None:
            obj.ViewObject.ShapeColor = arm_col + (0.0,)
        parts_placed[f"Arm_{sname}"] = obj

    for pname in ["L_Pitcher", "R_Pitcher"]:
        obj = _load_static(pname)
        if not obj:
            continue
        sname = "LeftPitch" if "L_" in pname else "RightPitch"
        delta = math.degrees(ik["arm_angles"][sname] - ik["home_angles"][sname])
        if abs(delta) > 0.01:
            sx = -FRAME_X if "L_" in pname else FRAME_X
            shaft = Base.Vector(sx, 0, SR6["servoPivotH"])
            rot = App.Rotation(Base.Vector(0, 1, 0), delta)
            obj.Placement = App.Placement(Base.Vector(0, 0, 0), rot, shaft)
        parts_placed[pname] = obj

    # ── C. Receiver + T-wist ──
    rot_roll = App.Rotation(Base.Vector(0, 1, 0), roll_deg)
    rot_pitch = App.Rotation(Base.Vector(1, 0, 0), pitch_deg)
    recv_rot = rot_pitch.multiply(rot_roll)
    _RECV_VISIBLE = [n for n in RECV_PARTS if n not in DEFAULT_HIDDEN]
    for pname in _RECV_VISIBLE:
        obj = _load_static(pname)
        if not obj:
            continue
        base_pos = Base.Vector(tx, ty, HOME_H + recv_dz)
        if pname in ("RingGear", "ExchangeGear", "DriveGear"):
            tw_sign = 1 if pname == "RingGear" else -1
            twist_rot = App.Rotation(Base.Vector(0, 0, 1), tw_sign * twist_deg)
            obj.Placement = App.Placement(base_pos, recv_rot.multiply(twist_rot))
        else:
            obj.Placement = App.Placement(base_pos, recv_rot)
        if pname == "Receiver" and getattr(obj, "ViewObject", None) is not None:
            obj.ViewObject.Transparency = 30
        parts_placed[pname] = obj

    # ── D. Parametric rods (as Part.Features) ──
    rod_stats: List[Dict[str, Any]] = []
    for sname, stype, _sx, _sy, _sign in SERVO_SLOTS:
        tip = ik["arm_tips"][sname]
        mount = ik["recv_mounts"][sname]
        v1, v2 = Base.Vector(*tip), Base.Vector(*mount)
        direction = v2 - v1
        length = direction.Length
        if length < 0.1:
            shape = Part.makeSphere(ROD_END_D / 2, v1)
        else:
            cyl = Part.makeCylinder(ROD_BODY_D / 2, length, v1, direction)
            b1 = Part.makeSphere(ROD_END_D / 2, v1)
            b2 = Part.makeSphere(ROD_END_D / 2, v2)
            shape = cyl.fuse(b1).fuse(b2)
        obj = doc.addObject("Part::Feature", f"Rod_{sname}")
        obj.Shape = shape
        nominal = 175.0
        stress = abs(length - nominal) / max(nominal, 1.0)
        g_col = max(0.0, 0.85 - stress * 8)
        if getattr(obj, "ViewObject", None) is not None:
            obj.ViewObject.ShapeColor = (0.30, g_col, 0.91, 0.0)
        parts_placed[f"Rod_{sname}"] = obj
        rod_stats.append({"servo": sname, "rod_3d_mm": round(length, 1),
                          "stress_pct": round(stress * 100, 1)})

    doc.recompute()

    # ── GUI-environment visibility persistence ───────────────────────────────
    # 反者道之动: FreeCADCmd (headless) 写盘时 ViewObject=None, Visibility/ShapeColor 无法持久化,
    # 导致 FCStd 被双击打开时全部零件不可见. 若当前进程为 GUI (FreeCADGui 可加载),
    # 对所有 obj 统一设 Visibility=True 再 saveAs — FCStd 自带视觉真相, 无需后处理.
    try:
        import FreeCADGui  # noqa: F401  (triggers ViewProvider creation if GUI env)
        for _o in doc.Objects:
            _vp = getattr(_o, "ViewObject", None)
            if _vp is not None:
                try:
                    _vp.Visibility = True
                except Exception:
                    pass
    except Exception:
        # Headless (FreeCADCmd): no FreeCADGui, no ViewObject — expected, proceed.
        pass

    elapsed = time.time() - t0

    # Save FCStd
    fcstd_path = os.path.join(out_dir, f"ORS6_{label}.FCStd")
    doc.saveAs(fcstd_path)

    # Export STEP (Part::Feature rods only — small)
    step_path = None
    try:
        shapes = [o.Shape for o in doc.Objects
                  if hasattr(o, "Shape") and not o.Shape.isNull()]
        if shapes:
            compound = Part.makeCompound(shapes)
            step_path = os.path.join(out_dir, f"ORS6_{label}.step")
            compound.exportStep(step_path)
    except Exception:
        pass

    return {
        "ok": True,
        "label": label,
        "engine": "freecad",
        "pose": pose,
        "receiver": {"tx": round(tx, 2), "ty": round(ty, 2),
                     "tz_stl": round(tz_stl, 2), "home_h": HOME_H,
                     "roll_deg": round(roll_deg, 2),
                     "pitch_deg": round(pitch_deg, 2),
                     "twist_deg": round(twist_deg, 2)},
        "arm_angles_deg": {k: round(math.degrees(v), 2)
                           for k, v in ik["arm_angles"].items()},
        "rods": rod_stats,
        "parts_count": len(parts_placed),
        "fcstd_path": fcstd_path,
        "step_path": step_path,
        "elapsed_s": round(elapsed, 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Motion sequence (15 poses)
# ══════════════════════════════════════════════════════════════════════════════

def motion_sequence(engine: str = "cadquery",
                    output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Build all 15 canonical poses. engine ∈ {cadquery, freecad}."""
    out_dir = output_dir or OUTPUT_DIR
    builder = build_cadquery if engine == "cadquery" else build_freecad

    results: List[Dict[str, Any]] = []
    t0 = time.time()
    for name, L0, L1, L2, R0, R1, R2 in MOTION_POSES:
        print(f"\n>>> Motion: {name}")
        try:
            r = builder(pose=(L0, L1, L2, R0, R1, R2),
                        label=name, output_dir=out_dir)
            results.append(r)
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"ok": False, "label": name, "error": str(e)})

    built = sum(1 for r in results if r.get("ok"))
    report = {
        "engine": engine,
        "poses_built": built,
        "poses_total": len(MOTION_POSES),
        "elapsed_s": round(time.time() - t0, 1),
        "results": results,
    }
    report_path = os.path.join(out_dir, f"ORS6_motion_{engine}_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    report["report_path"] = report_path
    return report


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "home"
    if cmd == "home":
        r = build_cadquery()
        print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    elif cmd == "pose":
        args = sys.argv[2:8]
        if len(args) == 6:
            pose = tuple(int(a) for a in args)
        else:
            pose = TCODE_HOME
        label = sys.argv[8] if len(sys.argv) > 8 else "pose"
        r = build_cadquery(pose=pose, label=label)
        print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    elif cmd == "motion":
        engine = sys.argv[2] if len(sys.argv) > 2 else "cadquery"
        r = motion_sequence(engine=engine)
        print(f"\n{r['poses_built']}/{r['poses_total']} built in {r['elapsed_s']}s")
        print(f"Report: {r['report_path']}")
    else:
        print(__doc__)
