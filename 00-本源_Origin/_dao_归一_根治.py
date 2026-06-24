#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_dao_归一_根治.py — 道·归一 · 根治活体装配 · 从本源至产物

"内固其本, 外彰其形, 表里相依, 浑然一统.
 两者同出, 异名同谓. 玄之又玄, 众妙之门."

纯直连器 · 无中间层 · 从根底 memid 一路到产物.

Phases:
  ① 诊  · 取活体现状 (mate ec / comp cs / feature err)
  ② 治  · 删 18 过约束 mate · 净删 5 停用 belt_a45
  ③ 建  · ForceRebuild3 · 活体收敛
  ④ 验  · 重诊 · 应 9 mate 全 ec=0 · 37 comp 全 cs∈{fixed,fully}
  ⑤ 存  · Save3
  ⑥ 彰  · BOM / 健康 / 4 视图 / 骨架 / 透视 / 碰撞分类 / 质量 / summary
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from 道_直连_底层 import Dao, DaoDispatch, _ole_of, _safe, _nothing, _byref_int
import 道_直连_底层_facets  # noqa: F401  # 挂载 facets 到 Dao


OUT_DIR = Path(__file__).resolve().parent / "_产物输出"
OUT_DIR.mkdir(exist_ok=True)


# ════════════════════════════════════════════════════════════════════════
# ① 诊 · 活体现状
# ════════════════════════════════════════════════════════════════════════
def diagnose(dao: Dao) -> Dict[str, Any]:
    """全景诊断 · mate ec / comp cs / feature err."""
    mates = dao.mate.list_all()
    cmap = dao.build_comp_map()

    ec_dist = {}
    bad_mates = []
    for m in mates:
        ec = m.get("error_status", -1)
        ec_dist[ec] = ec_dist.get(ec, 0) + 1
        if ec not in (0, None):
            bad_mates.append(m)

    CONS_NAMES = {0: "free", 1: "fully", 2: "over", 3: "fixed"}
    cs_dist = {}
    bad_comps = []
    supp_comps = []
    for name in cmap:
        cs = dao.comp.constrained_status(name)
        supp = bool(dao.comp.is_suppressed(name))
        key = (CONS_NAMES.get(cs, f"?{cs}"), supp)
        cs_dist[key] = cs_dist.get(key, 0) + 1
        if supp:
            supp_comps.append(name)
        elif cs not in (1, 3):  # 非 fully / fixed
            bad_comps.append({"name": name, "cs": cs})

    return {
        "mates_total": len(mates),
        "mates_ec_dist": ec_dist,
        "mates_bad": [{"name": m["name"], "ec": m["error_status"],
                        "type": m["type_name"]} for m in bad_mates],
        "comps_total": len(cmap),
        "comps_cs_dist": {f"{k[0]}/supp={k[1]}": v
                          for k, v in cs_dist.items()},
        "comps_bad": bad_comps,
        "comps_suppressed": supp_comps,
    }


# ════════════════════════════════════════════════════════════════════════
# ② 治 · 删 over-def mate · 净删 stale belt
# ════════════════════════════════════════════════════════════════════════
def remedy(dao: Dao, diag: Dict[str, Any]) -> Dict[str, Any]:
    """删 ec=51 mate + 删 suppressed comp · 根治."""
    result: Dict[str, Any] = {}

    # A. 删过约束 mate (ec=51)
    bad_mate_names = [m["name"] for m in diag["mates_bad"]
                      if m["ec"] == 51]
    if bad_mate_names:
        print(f"  A. 删 {len(bad_mate_names)} 过约束 mate ...")
        r = dao.mate.delete_many(bad_mate_names)
        result["mate_delete"] = r
        print(f"     删: {r.get('deleted', 0)} / 跳: "
              f"{len(r.get('skipped', []))}")
        if r.get("skipped"):
            print(f"     skipped: {r['skipped']}")
    else:
        result["mate_delete"] = {"ok": True, "deleted": 0}
        print("  A. 无 ec=51 mate · 跳过")

    # B. 删抑 belt_a45 (stale)
    stale_belts = [n for n in diag["comps_suppressed"]
                    if n.startswith("belt_a45")]
    if stale_belts:
        print(f"  B. 净删 {len(stale_belts)} stale belt_a45 ...")
        r = dao.comp.delete_many(stale_belts)
        result["belt_delete"] = r
        print(f"     删: {r.get('deleted', 0)} / 跳: "
              f"{len(r.get('skipped', []))}")
        if r.get("skipped"):
            print(f"     skipped: {r['skipped']}")
    else:
        result["belt_delete"] = {"ok": True, "deleted": 0}
        print("  B. 无 stale belt_a45 · 跳过")

    return result


# ════════════════════════════════════════════════════════════════════════
# ②a 正位 · 结构件归位 (casing/shaft/pin/motor 全位校正)
# ════════════════════════════════════════════════════════════════════════
# ── 几何根算 · 逆向推演 (反者道之动) ──
# frame_base CadQuery: base_plate z[-10,10], columns z[10,510]
#   → local z_range=[-10,510], 世界顶 = -970+510 = -460
# casing_lower CadQuery: box(960,610,460) 原点=中心 → local z[-230,+230]
#   底贴 frame 顶: tz+(-230)=-460 → tz=-230, 顶=z=0(分型面=轴心线)
# casing_upper CadQuery: box(960,610,460)+hopper → local z[-230,+380]
#   底贴 lower 顶: tz+(-230)=0 → tz=+230, 顶=z=610
# motor_body CadQuery: box(590,280,350) center, shaft stub 在 local x=+405, local z=+5
#   轴心 z=-600: tz≈-600; 轴端 x=-90(对齐belt): tx+405=-90 → tx=-495
# drive_pulley: 在电机轴端 x=-90, 皮带中心距 z=-600
# motor_mount: 720×600×180, origin=顶面中心, 贴电机底 z=-799.5
#   tx 偏右以连接 frame(-400 使右缘伸至 x=-40, 与 frame 底板重叠 37.5mm)
STRUCTURE_POSITIONS = {
    "casing_upper-1":  (572.5,    0.0,   230.0),  # 底 z=0 (分型面)
    "casing_lower-1":  (572.5,    0.0,  -230.0),  # 底 z=-460 (frame 顶)
    "motor_body-1":    (-495.0,   0.0,  -600.0),  # 轴心 z=-600
    "main_shaft-1":    (572.5,    0.0,     0.0),
    "hammer_pin-1":    (496.0,  220.0,     0.0),
    "hammer_pin-2":    (496.0, -220.0,     0.0),
    "hammer_pin-3":    (496.0,    0.0,   220.0),
    "hammer_pin-4":    (496.0,    0.0,  -220.0),
    "screen_plate-1":  (508.0,  100.0,     0.0),
    "frame_base-1":    (572.5,    0.0,  -970.0),
    "motor_mount-1":   (-400.0,   0.0,  -799.5),  # 右缘连 frame
    "drive_pulley-1":  (-90.0,    0.0,  -600.0),  # belt 对齐 driven_pulley
    "driven_pulley-1": (0.0,      0.0,     0.0),
}
STRUCTURE_TOL_MM = 2.0

# 需要强制设定旋转的组件 (col-major 9-float)
# 原screen_plate旋转[0,-1,0, 0,0,-1, 1,0,0]已合理(弧面包裹转子上方), 保留
STRUCTURE_ROTATIONS: Dict[str, Tuple[float, ...]] = {
}


def reposition_structure(dao: Dao) -> Dict[str, Any]:
    """结构件归位 · 含旋转校正 · 平移+旋转双修."""
    result: Dict[str, Any] = {"moved": [], "skipped": [], "errors": []}
    for name, (tx, ty, tz) in STRUCTURE_POSITIONS.items():
        arr = dao.transform.get(name)
        if not arr:
            result["errors"].append({"name": name, "err": "no transform"})
            continue
        cx, cy, cz = arr[9]*1000, arr[10]*1000, arr[11]*1000
        cur_rot = tuple(arr[:9])
        tgt_rot = STRUCTURE_ROTATIONS.get(name, cur_rot)
        pos_dist = ((cx-tx)**2 + (cy-ty)**2 + (cz-tz)**2) ** 0.5
        rot_dist = max(abs(cur_rot[j] - tgt_rot[j]) for j in range(9))
        if pos_dist < STRUCTURE_TOL_MM and rot_dist < 0.01:
            result["skipped"].append(name)
            continue
        was_fixed = dao.comp.is_fixed(name)
        if was_fixed:
            dao.comp.unfix(name)
        ok = dao.transform.set(name, (tx, ty, tz), rot=tgt_rot)
        if was_fixed:
            dao.comp.fix(name)
        if ok:
            result["moved"].append({
                "name": name,
                "from": (round(cx, 1), round(cy, 1), round(cz, 1)),
                "to": (tx, ty, tz),
                "rot_changed": rot_dist >= 0.01,
            })
        else:
            result["errors"].append({"name": name, "err": "set failed"})
    return result


# ════════════════════════════════════════════════════════════════════════
# ②b 正位 · 16 hammer 全变换 (位置 + 旋转 · 根治 disc 干涉)
# ════════════════════════════════════════════════════════════════════════
# Hammer hole local = (0, 120, -1)mm.  Pin world axis = (-1,0,0).
# Rotation col-major: maps local → world so hole axis // pin axis.
_PIN_ROT = {
    1: (0, 0, -1,  0, 1, 0,  1, 0, 0),   # pin-1 Y+220
    2: (0, 0,  1,  0,-1, 0,  1, 0, 0),   # pin-2 Y-220
    3: (0,  1, 0,  0, 0,  1, 1, 0, 0),   # pin-3 Z+220
    4: (0, -1, 0,  0, 0, -1, 1, 0, 0),   # pin-4 Z-220
}
_PIN_POS = {
    1: (1,  100,    0),
    2: (1, -100,    0),
    3: (1,    0,  100),
    4: (1,    0, -100),
}
_H_PIN = {
    1:1, 5:1, 9:1, 13:1,
    3:2, 7:2, 11:2, 15:2,
    2:3, 6:3, 10:3, 14:3,
    4:4, 8:4, 12:4, 16:4,
}
_H_XH = {
    1: 207,  5: 408,  9: 610, 13: 810,
    3: 207,  7: 408, 11: 610, 15: 810,
    2: 207,  6: 408, 10: 610, 14: 810,
    4: 207,  8: 408, 12: 610, 16: 810,
}
HAMMER_TOL_MM = 3.0


def reposition_hammers(dao: Dao) -> Dict[str, Any]:
    """16 hammer 全变换 (位置 + 旋转) · 根治 disc 干涉."""
    result: Dict[str, Any] = {"moved": [], "skipped": [], "errors": []}
    for i in range(1, 17):
        name = f"hammer-{i}"
        pin = _H_PIN[i]
        xh = _H_XH[i]
        rot = _PIN_ROT[pin]
        dx, dy, dz = _PIN_POS[pin]
        tgt = (xh + dx, dy, dz)
        arr = dao.transform.get(name)
        if not arr:
            result["errors"].append({"name": name, "err": "no transform"})
            continue
        cx, cy, cz = arr[9]*1000, arr[10]*1000, arr[11]*1000
        cur_rot = tuple(arr[:9])
        pos_d = ((cx-tgt[0])**2 + (cy-tgt[1])**2 + (cz-tgt[2])**2) ** 0.5
        rot_d = max(abs(cur_rot[j] - rot[j]) for j in range(9))
        if pos_d < HAMMER_TOL_MM and rot_d < 0.01:
            result["skipped"].append(name)
            continue
        was_fixed = dao.comp.is_fixed(name)
        if was_fixed:
            dao.comp.unfix(name)
        ok = dao.transform.set(name, tgt, rot=rot)
        if was_fixed:
            dao.comp.fix(name)
        if ok:
            result["moved"].append({
                "name": name, "to": tgt,
                "rot_fixed": rot_d >= 0.01,
            })
        else:
            result["errors"].append({"name": name, "err": "set failed"})
    return result


# ════════════════════════════════════════════════════════════════════════
# ③ 建 · ForceRebuild3
# ════════════════════════════════════════════════════════════════════════
def rebuild(dao: Dao) -> Dict[str, Any]:
    """触发 ForceRebuild3 · 活体收敛."""
    t0 = time.time()
    ok = _safe(lambda: bool(dao.doc.ForceRebuild3(False)), False)
    t1 = time.time()
    return {"ok": ok, "elapsed_s": round(t1 - t0, 2)}


# ════════════════════════════════════════════════════════════════════════
# ⑤ 存 · Save3
# ════════════════════════════════════════════════════════════════════════
def save(dao: Dao) -> Dict[str, Any]:
    """Save3 (1=silent save) · 返 err+warn."""
    import pythoncom, win32com.client
    err = win32com.client.VARIANT(
        pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warn = win32com.client.VARIANT(
        pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    t0 = time.time()
    try:
        # IModelDoc2.Save3(Options, Errors*, Warnings*)
        ok = bool(dao.doc.Save3(1, err, warn))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    t1 = time.time()
    return {
        "ok": ok, "elapsed_s": round(t1 - t0, 2),
        "errors": _safe(lambda: int(err.value), -1),
        "warnings": _safe(lambda: int(warn.value), -1),
    }


# ════════════════════════════════════════════════════════════════════════
# ⑥ 彰 · 产物输出
# ════════════════════════════════════════════════════════════════════════
def export_bom(dao: Dao) -> Path:
    """BOM.csv · Part 去重 · Qty 聚合."""
    cmap = dao.build_comp_map()
    by_part: Dict[str, Dict[str, Any]] = {}
    for name, comp in cmap.items():
        path = _safe(lambda c=comp: str(c.GetPathName()), "")
        part = Path(path).name if path else "(unknown)"
        supp = bool(dao.comp.is_suppressed(name))
        if part not in by_part:
            by_part[part] = {"part": part, "path": path, "qty": 0,
                              "suppressed": 0, "instances": []}
        by_part[part]["qty"] += 1
        if supp:
            by_part[part]["suppressed"] += 1
        by_part[part]["instances"].append(name)

    csv_path = OUT_DIR / "BOM.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["#", "Part", "Qty", "Active", "Suppressed",
                    "Instances", "Path"])
        rows = sorted(by_part.values(), key=lambda x: (-x["qty"], x["part"]))
        for i, r in enumerate(rows, 1):
            w.writerow([
                i, r["part"], r["qty"],
                r["qty"] - r["suppressed"], r["suppressed"],
                " / ".join(r["instances"]), r["path"],
            ])
    return csv_path


def _select_comp(dao: Dao, name: str, append: bool) -> bool:
    """选组件 · SelectByID2 · append 为 True 表追加."""
    try:
        comp = dao.comp[name]
        if comp is None:
            return False
        full = _safe(lambda c=comp: str(c.Name2), name)
        if callable(full):
            full = _safe(lambda c=comp: str(c.Name2()), name)
        ext = dao.doc.Extension
        if callable(ext):
            ext = ext()
        return bool(ext.SelectByID2(
            full or name, "COMPONENT", 0.0, 0.0, 0.0,
            append, 0, _nothing(), 0))
    except Exception:
        return False


def render_views(dao: Dao) -> List[Path]:
    """4 标准视图 BMP."""
    out: List[Path] = []
    views = {"iso": 7, "front": 1, "top": 5, "right": 3}
    try:
        dao.doc.ClearSelection2(True)
    except Exception:
        pass
    for key, vid in views.items():
        try:
            dao.doc.ShowNamedView2("", vid)
            time.sleep(0.15)
            dao.doc.ViewZoomtofit2()
            time.sleep(0.3)
            png = OUT_DIR / f"view_{key}.bmp"
            dao.doc.SaveBMP(str(png), 1600, 1000)
            print(f"    ✓ {key} → {png.name}")
            out.append(png)
        except Exception as e:
            print(f"    ✗ {key}: {e}")
    return out


def render_skeleton(dao: Dao) -> Path:
    """隐 casing + frame · 骨架视."""
    targets = ("casing_upper-1", "casing_lower-1", "frame_base-1")
    hidden: List[str] = []
    try:
        dao.doc.ClearSelection2(True)
    except Exception:
        pass
    for i, n in enumerate(targets):
        if _select_comp(dao, n, append=(i > 0)):
            hidden.append(n)
    if hidden:
        try:
            dao.doc.BlankComponent()
            print(f"    已隐藏 {len(hidden)}")
        except Exception as e:
            print(f"    BlankComponent: {e}")
    try:
        dao.doc.ClearSelection2(True)
    except Exception:
        pass

    png = Path()
    try:
        dao.doc.ShowNamedView2("", 7)
        time.sleep(0.2)
        dao.doc.ViewZoomtofit2()
        time.sleep(0.35)
        png = OUT_DIR / "skeleton_iso.bmp"
        dao.doc.SaveBMP(str(png), 1600, 1000)
        print(f"    ✓ skeleton → {png.name}")
    except Exception as e:
        print(f"    skel 失败: {e}")

    # 恢复
    try:
        dao.doc.ClearSelection2(True)
    except Exception:
        pass
    for i, n in enumerate(hidden):
        _select_comp(dao, n, append=(i > 0))
    if hidden:
        try:
            dao.doc.UnblankComponent()
            print(f"    已恢复 {len(hidden)}")
        except Exception:
            pass
    try:
        dao.doc.ClearSelection2(True)
    except Exception:
        pass
    return png


def render_xray(dao: Dao) -> Path:
    """深透 · 仅留 shaft/hammer/disc/pin/screen."""
    to_hide = [
        "casing_upper-1", "casing_lower-1", "frame_base-1",
        "motor_body-1", "motor_mount-1", "drive_pulley-1",
        "v_belt_dao_240x190x600_004333-1",
        "v_belt_dao_240x190x600_004333-2",
        "v_belt_dao_240x190x600_004333-3",
        "v_belt_dao_240x190x600_004333-4",
    ]
    hidden: List[str] = []
    try:
        dao.doc.ClearSelection2(True)
    except Exception:
        pass
    for i, n in enumerate(to_hide):
        if _select_comp(dao, n, append=(i > 0)):
            hidden.append(n)
    if hidden:
        try:
            dao.doc.BlankComponent()
            print(f"    已隐藏 {len(hidden)}")
        except Exception as e:
            print(f"    BlankComponent: {e}")
    try:
        dao.doc.ClearSelection2(True)
    except Exception:
        pass

    png = Path()
    try:
        dao.doc.ShowNamedView2("", 7)
        time.sleep(0.2)
        dao.doc.ViewZoomtofit2()
        time.sleep(0.35)
        png = OUT_DIR / "xray_iso.bmp"
        dao.doc.SaveBMP(str(png), 1600, 1000)
        print(f"    ✓ xray → {png.name}")
    except Exception as e:
        print(f"    xray: {e}")

    try:
        dao.doc.ClearSelection2(True)
    except Exception:
        pass
    for i, n in enumerate(hidden):
        _select_comp(dao, n, append=(i > 0))
    if hidden:
        try:
            dao.doc.UnblankComponent()
            print(f"    已恢复 {len(hidden)}")
        except Exception:
            pass
    try:
        dao.doc.ClearSelection2(True)
    except Exception:
        pass
    return png


def interference_classify(dao: Dao) -> Dict[str, Any]:
    """碰撞检测 + 分类 (design-intent vs real).

    纯 memid Invoke 路径 · 绕开 DaoDispatch setter 与 dynamic dispatch 各自 bug.
    """
    import pythoncom as pc
    result: Dict[str, Any] = {"ok": False}
    mt = dao.mt
    asm_ole = dao.asm.ole

    # Step 1: 取 IDM · PROPERTYGET
    mid_idm = mt.memid("IAssemblyDoc", "InterferenceDetectionManager")
    try:
        idm_raw = asm_ole.Invoke(
            mid_idm, 0, pc.DISPATCH_PROPERTYGET, True)
    except Exception as e:
        result["error"] = f"取 IDM: {e}"
        return result

    # Step 2: 设属性 · PROPERTYPUT
    for pname, pval in (
        ("TreatCoincidenceAsInterference", False),
        ("IncludeMultibodyPartInterferences", True),
        ("IgnoreHiddenBodies", True),
    ):
        mid_p = mt.memid("IInterferenceDetectionMgr", pname)
        if mid_p is None:
            continue
        try:
            idm_raw.Invoke(mid_p, 0, pc.DISPATCH_PROPERTYPUT, False, pval)
        except Exception:
            pass  # 某些属性可能只读或不支持, 忽略

    # Step 3: Count
    mid_cnt = mt.memid("IInterferenceDetectionMgr", "GetInterferenceCount")
    n = 0
    try:
        n = int(idm_raw.Invoke(
            mid_cnt, 0,
            pc.DISPATCH_METHOD | pc.DISPATCH_PROPERTYGET, True))
    except Exception:
        pass
    result["count"] = n

    # Step 4: GetInterferences → tuple of PyIDispatch
    mid_gi = mt.memid("IInterferenceDetectionMgr", "GetInterferences")
    arr = None
    try:
        arr = idm_raw.Invoke(
            mid_gi, 0,
            pc.DISPATCH_METHOD | pc.DISPATCH_PROPERTYGET, True)
    except Exception as e:
        result["error"] = f"GetInterferences: {e}"
        return result

    # Step 5: 每项 Volume + Components · 直 memid
    vol_mid = mt.memid("IInterference", "Volume")
    comps_mid = mt.memid("IInterference", "Components")
    name_mid = mt.memid("IComponent2", "Name2")
    items: List[Dict[str, Any]] = []
    for i, inter in enumerate(list(arr) if arr else []):
        if inter is None:
            continue
        try:
            vol_raw = inter.Invoke(
                vol_mid, 0, pc.DISPATCH_PROPERTYGET, True)
            vol = float(vol_raw) if vol_raw is not None else 0.0
            comps_raw = inter.Invoke(
                comps_mid, 0, pc.DISPATCH_PROPERTYGET, True)
            names: List[str] = []
            if comps_raw:
                for c in list(comps_raw):
                    if c is None:
                        continue
                    try:
                        nm_raw = c.Invoke(
                            name_mid, 0, pc.DISPATCH_PROPERTYGET, True)
                        names.append(str(nm_raw))
                    except Exception:
                        names.append("?")
            items.append({
                "idx": i,
                "volume_mm3": vol * 1e9,
                "components": names,
            })
        except Exception as e:
            items.append({"idx": i, "error": str(e)})

    # Step 6: Done
    mid_done = mt.memid("IInterferenceDetectionMgr", "Done")
    if mid_done:
        try:
            idm_raw.Invoke(mid_done, 0, pc.DISPATCH_METHOD, True)
        except Exception:
            pass

    # 分类: design (工程意图) vs real (需关注)
    # tag 匹配按 comp 基名 (去 subasm 前缀 + 去 instance -N 后缀)
    def _tag(cname: str) -> str:
        base = cname.rsplit("/", 1)[-1]
        dash = base.rfind("-")
        if dash > 0 and base[dash + 1:].isdigit():
            base = base[:dash]
        return base

    design_patterns = [
        ({"frame_base", "motor_mount"}, "mount_bolt_to_frame"),
        ({"casing_lower", "casing_upper"}, "casing_flange_overlap"),
        ({"drive_pulley", "v_belt_dao_240x190x600_004333"},
         "drive_belt_groove_contact"),
        ({"driven_pulley", "v_belt_dao_240x190x600_004333"},
         "driven_belt_groove_contact"),
        ({"rotor_disc", "hammer_pin"}, "rotor_pin_interface"),
        ({"hammer", "hammer_pin"}, "hammer_pin_bearing_contact"),
        ({"main_shaft", "rotor_disc"}, "shaft_disc_interface"),
        ({"main_shaft", "casing_upper"}, "shaft_casing_bearing"),
        ({"main_shaft", "casing_lower"}, "shaft_casing_bearing"),
        ({"main_shaft", "driven_pulley"}, "shaft_pulley_interface"),
        ({"motor_body", "motor_mount"}, "motor_mount_bolt"),
        ({"motor_body", "drive_pulley"}, "motor_shaft_interface"),
        ({"screen_plate", "casing_lower"}, "screen_casing_interface"),
        ({"screen_plate", "casing_upper"}, "screen_casing_interface"),
        ({"hammer", "casing_upper"}, "hammer_inside_casing"),
        ({"hammer", "casing_lower"}, "hammer_inside_casing"),
        ({"hammer_pin", "casing_upper"}, "pin_casing_pass"),
        ({"hammer_pin", "casing_lower"}, "pin_casing_pass"),
        ({"drive_pulley", "casing_lower"}, "drive_pulley_casing"),
        ({"drive_pulley", "casing_upper"}, "drive_pulley_casing"),
        ({"driven_pulley", "casing_upper"}, "driven_pulley_casing"),
        ({"driven_pulley", "casing_lower"}, "driven_pulley_casing"),
        ({"rotor_disc", "hammer"}, "disc_hammer_adjacent"),
        ({"rotor_disc", "casing_lower"}, "disc_casing_interface"),
        ({"rotor_disc", "casing_upper"}, "disc_casing_interface"),
        ({"casing_lower", "frame_base"}, "casing_frame_mount"),
        ({"casing_upper", "frame_base"}, "casing_frame_mount"),
        ({"motor_body", "frame_base"}, "motor_frame_mount"),
        ({"motor_mount", "motor_body"}, "motor_mount_bolt"),
    ]
    for it in items:
        if "components" not in it:
            continue
        cs = it["components"]
        tags = set(_tag(c) for c in cs)
        it["tags"] = sorted(tags)
        matched_patt = None
        for patt, label in design_patterns:
            if patt.issubset(tags):
                matched_patt = label
                break
        it["category"] = matched_patt or "real"
    result["items"] = items
    by_cat: Dict[str, int] = {}
    by_cat_vol: Dict[str, float] = {}
    for it in items:
        cat = it.get("category", "?")
        by_cat[cat] = by_cat.get(cat, 0) + 1
        by_cat_vol[cat] = by_cat_vol.get(cat, 0.0) + it.get(
            "volume_mm3", 0.0)
    result["by_category"] = by_cat
    result["by_category_vol_mm3"] = {
        k: round(v, 2) for k, v in by_cat_vol.items()}
    result["ok"] = True
    return result


def mass_properties(dao: Dao) -> Dict[str, Any]:
    """质量属性 (ExtensionMgr.CreateMassProperty)."""
    r: Dict[str, Any] = {}
    try:
        mp = dao.ext.CreateMassProperty()
        if mp is None:
            return {"error": "CreateMassProperty None"}
        mass = _safe(lambda: float(mp.Mass), None)
        vol = _safe(lambda: float(mp.Volume), None)
        dens = _safe(lambda: float(mp.Density), None)
        sa = _safe(lambda: float(mp.SurfaceArea), None)
        com_raw = _safe(lambda: mp.CenterOfMass, None)
        if callable(com_raw):
            com_raw = _safe(lambda cx=com_raw: cx(), None)
        com_mm = [v * 1000 for v in list(com_raw)] if com_raw else None
        return {
            "mass_kg": round(mass, 3) if mass is not None else None,
            "volume_mm3": round(vol * 1e9, 2) if vol is not None else None,
            "density_kg_m3": round(dens, 2) if dens is not None else None,
            "surface_area_mm2": round(sa * 1e6, 2) if sa is not None else None,
            "center_of_mass_mm": com_mm,
        }
    except Exception as e:
        return {"error": str(e)}


# ════════════════════════════════════════════════════════════════════════
# 主流
# ════════════════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    print("═══ 道·归一 · 根治活体装配 ═══\n")

    dao = Dao().connect()
    sw_rev = _safe(lambda: str(dao.sw.RevisionNumber()), "?")
    doc_title = _safe(lambda: str(dao.doc.GetTitle()), "?")
    print(f"  SW: {sw_rev} · Doc: {doc_title}\n")

    # ① 诊
    print("─── ① 诊 · 现状 ───")
    before = diagnose(dao)
    print(f"  mates={before['mates_total']} ec_dist={before['mates_ec_dist']}")
    print(f"  comps={before['comps_total']} cs_dist={before['comps_cs_dist']}")
    if before["mates_bad"]:
        print(f"  过约束 mate: {len(before['mates_bad'])}")
    if before["comps_suppressed"]:
        print(f"  停用 comp: {before['comps_suppressed']}")

    # ② 治
    print("\n─── ② 治 · 删错mate + 净belt ───")
    fix_result = remedy(dao, before)

    # ②a 正位 · 结构件归位
    print("\n─── ②a 正位 · 结构件归位 ───")
    struct = reposition_structure(dao)
    print(f"  移: {len(struct['moved'])}  跳: {len(struct['skipped'])}  "
          f"错: {len(struct['errors'])}")
    for m in struct["moved"]:
        print(f"    {m['name']:20s}  {m['from']} → {m['to']}")

    # ②b 正位 · 16 hammer 全变换
    print("\n─── ②b 正位 · 16 hammer 全变换 ───")
    repos = reposition_hammers(dao)
    print(f"  移: {len(repos['moved'])}  跳: {len(repos['skipped'])}  "
          f"错: {len(repos['errors'])}")
    for m in repos["moved"][:6]:
        rf = " +rot" if m.get("rot_fixed") else ""
        print(f"    {m['name']:12s}  → {m['to']}{rf}")
    if len(repos["moved"]) > 6:
        print(f"    ... 等 {len(repos['moved']) - 6} 件")

    # ③ 建
    print("\n─── ③ 建 · ForceRebuild3 ───")
    rb = rebuild(dao)
    print(f"  rebuild ok={rb['ok']} 耗时={rb['elapsed_s']}s")

    # ④ 验
    print("\n─── ④ 验 · 重诊 ───")
    after = diagnose(dao)
    print(f"  mates={after['mates_total']} ec_dist={after['mates_ec_dist']}")
    print(f"  comps={after['comps_total']} cs_dist={after['comps_cs_dist']}")
    if after["mates_bad"]:
        print(f"  !! 残余过约束 mate: {len(after['mates_bad'])}")
    else:
        print(f"  ✓ 所有 mate 无错")
    if after["comps_suppressed"]:
        print(f"  !! 残余 suppressed: {after['comps_suppressed']}")
    else:
        print(f"  ✓ 无 suppressed 组件")

    # ⑤ 存
    print("\n─── ⑤ 存 · Save3 ───")
    sv = save(dao)
    print(f"  save ok={sv.get('ok')} err={sv.get('errors')} "
          f"warn={sv.get('warnings')} 耗时={sv.get('elapsed_s')}s")

    # ⑥ 彰 · 产物
    print("\n─── ⑥ 彰 · 产物输出 ───")
    print("  [1/6] BOM ...")
    bom_path = export_bom(dao)
    print(f"       → {bom_path.name}")

    print("  [2/6] 4 视图 ...")
    views = render_views(dao)

    print("  [3/6] 骨架 ...")
    skel = render_skeleton(dao)

    print("  [4/6] 透视 ...")
    xray = render_xray(dao)

    print("  [5/6] 碰撞分类 ...")
    inter = interference_classify(dao)
    if inter.get("ok"):
        print(f"       总 {inter.get('count', 0)} 项 · "
              f"设计 vs 真干涉 分类:")
        for cat, ct in sorted(inter.get("by_category", {}).items(),
                               key=lambda x: -x[1]):
            vol = inter.get("by_category_vol_mm3", {}).get(cat, 0)
            marker = "✓" if cat != "real" else "!!"
            print(f"         {marker} {cat:32s} x{ct:2d}  "
                  f"vol={vol:.0f}mm³")
        if inter.get("by_category", {}).get("real", 0) > 0:
            reals = [it for it in inter.get("items", [])
                     if it.get("category") == "real"][:5]
            print(f"       真干涉前 {len(reals)} 项详:")
            for it in reals:
                print(f"         vol={it.get('volume_mm3', 0):.0f}mm³  "
                      f"{it.get('components')}")
    else:
        print(f"       错: {inter.get('error')}")

    print("  [6/6] 质量 ...")
    mp = mass_properties(dao)
    if "mass_kg" in mp:
        print(f"       mass={mp['mass_kg']}kg  vol={mp['volume_mm3']}mm³  "
              f"com={mp.get('center_of_mass_mm')}")

    # summary.json
    t1 = time.time()
    summary = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sw": sw_rev,
        "doc": doc_title,
        "doc_path": str(_safe(lambda: dao.doc.GetPathName(), "")),
        "elapsed_s": round(t1 - t0, 2),
        "phase_1_before": before,
        "phase_2_remedy": fix_result,
        "phase_2a_structure": struct,
        "phase_2b_hammers": repos,
        "phase_3_rebuild": rb,
        "phase_4_after": after,
        "phase_5_save": sv,
        "products": {
            "bom_csv": str(bom_path),
            "views": [str(p) for p in views],
            "skeleton": str(skel) if skel.name else None,
            "xray": str(xray) if xray.name else None,
            "interference": inter,
            "mass": mp,
        },
    }
    summary_path = OUT_DIR / "归一_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  ✓ summary → {summary_path.name}")

    # Snapshot MD
    md_path = OUT_DIR / "归一_报告.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write(f"# 道·归一 · 根治报告\n\n")
        f.write(f"- **时**: {summary['ts']}\n")
        f.write(f"- **SW**: {summary['sw']}\n")
        f.write(f"- **Doc**: `{summary['doc']}`\n")
        f.write(f"- **Path**: `{summary['doc_path']}`\n")
        f.write(f"- **耗时**: {summary['elapsed_s']}s\n\n")
        f.write(f"## 诊 → 治 → 验\n\n")
        f.write(f"| 项 | 前 | 后 |\n|---|---|---|\n")
        f.write(f"| mates 总 | {before['mates_total']} | "
                f"{after['mates_total']} |\n")
        f.write(f"| mate ec 分布 | {before['mates_ec_dist']} | "
                f"{after['mates_ec_dist']} |\n")
        f.write(f"| 过约束 mate | {len(before['mates_bad'])} | "
                f"{len(after['mates_bad'])} |\n")
        f.write(f"| 组件总 | {before['comps_total']} | "
                f"{after['comps_total']} |\n")
        f.write(f"| suppressed | {len(before['comps_suppressed'])} | "
                f"{len(after['comps_suppressed'])} |\n")
        f.write(f"\n## 施治\n\n")
        f.write(f"- 删 {fix_result.get('mate_delete', {}).get('deleted', 0)} "
                f"过约束 mate\n")
        f.write(f"- 净删 {fix_result.get('belt_delete', {}).get('deleted', 0)} "
                f"stale belt_a45\n")
        f.write(f"- 结构件归位: 移 {len(struct.get('moved', []))} · "
                f"跳 {len(struct.get('skipped', []))}\n")
        f.write(f"- hammer 全变换: 移 {len(repos.get('moved', []))} · "
                f"跳 {len(repos.get('skipped', []))}\n")
        f.write(f"- Rebuild: ok={rb['ok']} ({rb['elapsed_s']}s)\n")
        f.write(f"- Save: ok={sv.get('ok')} err={sv.get('errors')} "
                f"warn={sv.get('warnings')} ({sv.get('elapsed_s')}s)\n")
        f.write(f"\n## 产物\n\n")
        f.write(f"- BOM: `{bom_path.name}`\n")
        for p in views:
            f.write(f"- 视图: `{p.name}`\n")
        if skel.name:
            f.write(f"- 骨架: `{skel.name}`\n")
        if xray.name:
            f.write(f"- 透视: `{xray.name}`\n")
        f.write(f"\n## 碰撞分类 ({inter.get('count', 0)})\n\n")
        if inter.get("by_category"):
            for cat, ct in sorted(inter["by_category"].items(),
                                  key=lambda x: -x[1]):
                vol = inter["by_category_vol_mm3"].get(cat, 0)
                f.write(f"- **{cat}**: {ct} 项 · vol={vol:.0f}mm³\n")
        f.write(f"\n## 质量\n\n")
        if "mass_kg" in mp:
            f.write(f"- mass: **{mp['mass_kg']} kg**\n")
            f.write(f"- volume: {mp['volume_mm3']} mm³\n")
            f.write(f"- density: {mp['density_kg_m3']} kg/m³\n")
            f.write(f"- surface area: {mp['surface_area_mm2']} mm²\n")
            f.write(f"- CoM: {mp['center_of_mass_mm']}\n")
    print(f"  ✓ 报告 → {md_path.name}")

    print(f"\n═══ 归一终 · {round(t1-t0, 1)}s ═══")


if __name__ == "__main__":
    main()
