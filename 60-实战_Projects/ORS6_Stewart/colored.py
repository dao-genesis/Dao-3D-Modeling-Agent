#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORS6_Stewart · colored — 逐件着色装配体 (单一真相源)

道生一: 31 个独立 STL = 唯一几何真相 (逐件加载, 绝不合并成单网格)
一生二: 已验证固件 IK (kinematics.py) 驱动运动件位置
二生三: 真实硬件配色 (红机体/红连杆 · 白舵机摇臂 · 铬球头关节)
三生万物: 任意 T-Code 姿态 → 多视角着色渲染 + 着色 GLB 导出

为什么上一轮是"一坨浆糊":
  1. 旧路径渲染**合并单网格**装配体 → 无逐件材质 → 整体一坨、无色彩区分;
  2. 在已处于装配坐标系的 STL 上**叠加运动学位姿** → 几何漂移错乱。
本模块从 0 重建: 静态件原位加载, 运动件仅由 IK 驱动, 逐件着色。
"""
from __future__ import annotations
import math
import os
from typing import Dict, List, Tuple

import numpy as np

from .render import Part, render, hex_rgb, cylinder, uvsphere
from .kinematics import StewartIK, TCODE_HOME, ARM_PIVOT_STL
from .parts import (PARTS, SR6, HOME_H, SERVO_SLOTS, RECV_PARTS,
                    DEFAULT_HIDDEN, stl_path)

# 接收器: 照片中的设备只有简单圆环, 无 T-wist 齿轮头 → 装配只取 "Receiver"
RECV_RING = "Receiver"
# 真实推杆 STL (191mm 实物连杆) — 取代旧版细圆柱("浆糊"主因之一)
LINK_MAIN, LINK_PITCH = "MainLink", "PitcherLink"

# TRIPO_POSE: 反者道之动 — 由 Tripo image-to-3D 真相反解出的接收器静止位姿.
# Tripo 圆环区中心 ≈ (-5, 9, 168)mm (相对 HOME 居中位 (0,0,208.48) 重力下沉 ~40mm),
# 经固件 IK 逆映射 → T-Code, compute_receiver_pose 验证落点 (-5.0, 8.99, 168.01).
TRIPO_POSE: Tuple = (1627, 6499, 4166, 5000, 5000, 5000)

FRAME_X = 99.6
_INSTANCED = {"Arm", "L_Pitcher", "R_Pitcher"}

# ── 真实硬件配色 (对照实物照片标定) ──
PALETTE = {
    "body":   hex_rgb(0xd62828),   # 机体结构件 (亮红)
    "frame":  hex_rgb(0xd62828),   # L/R 框架
    "recv":   hex_rgb(0xc81f1f),   # 接收器 (略深红)
    "rod":    hex_rgb(0xd62828),   # 连杆 — 实物为红色
    "horn":   hex_rgb(0xf0ece4),   # 舵机摇臂 / 枢纽块 — 白
    "ball":   hex_rgb(0xc2c6cc),   # 球头关节 — 铬
}

# 标准多视角 (一致取景)
VIEWS = {
    "iso":   (1, -1, 0.5),
    "front": (0, -1, 0.05),
    "side":  (1, 0, 0.05),
    "top":   (0, 0, 1),
}


def _load(name) -> Tuple[np.ndarray, np.ndarray]:
    import trimesh
    p = stl_path(name)
    if not os.path.exists(p):
        return None, None
    m = trimesh.load(p, force="mesh")
    return np.asarray(m.vertices, float), np.asarray(m.faces, int)


def _Ry(deg):
    t = math.radians(deg); c, s = math.cos(t), math.sin(t)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _Rx(deg):
    t = math.radians(deg); c, s = math.cos(t), math.sin(t)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _place_link(name, tip, mount):
    """Orient a real link STL so its two eye-ends meet (tip, mount).

    The link's long axis is native +Y; its flat (thin) normal is native +Z.
    Every SR6 rod lies in a constant-Y plane, so the placed flat normal = world
    +Y. Returns (V, F) of the oriented link, or (None, None) if missing.
    """
    V, F = _load(name)
    if V is None:
        return None, None
    c = (V.min(0) + V.max(0)) / 2
    ea = np.array([c[0], V[:, 1].max(), c[2]])   # eye end A (native +Y)
    eb = np.array([c[0], V[:, 1].min(), c[2]])   # eye end B (native -Y)
    al = eb - ea; Llen = np.linalg.norm(al) or 1.0; al = al / Llen
    nl = np.array([0, 0, 1.0])                   # native flat normal
    tl = np.cross(al, nl)
    at = np.array(mount) - np.array(tip); Tlen = np.linalg.norm(at) or 1.0; at = at / Tlen
    nt = np.array([0, 1.0, 0])
    if abs(np.dot(at, nt)) > 0.99:
        nt = np.array([0, 0, 1.0])
    nt = nt - at * np.dot(at, nt); nt = nt / (np.linalg.norm(nt) or 1.0)
    tt = np.cross(at, nt)
    R = np.column_stack([at, nt, tt]) @ np.column_stack([al, nl, tl]).T
    s = Tlen / Llen
    return (s * (V - ea)) @ R.T + np.array(tip), F


def build_colored(pose: Tuple = TCODE_HOME) -> List[Part]:
    """Return a list[Part] = fully colored SR6 assembly at the given T-Code pose.

    Static structural parts load at native assembly coordinates; servo arms rotate
    by their IK angle-delta from home; the receiver elevates to HOME_H (+pose);
    the 6 push-rods are generated parametrically from arm-tip → receiver-mount.
    """
    ik = StewartIK()
    geom = ik.compute_full_geometry(*pose)
    home = ik.compute_full_geometry(*TCODE_HOME)
    tx, ty, tz, roll, pitch, twist = ik.compute_receiver_pose(*pose)
    recv_dz = tz - HOME_H

    parts: List[Part] = []

    # ── A. static structural (red), native coords ──
    static = [n for n in PARTS if n not in RECV_PARTS and n not in DEFAULT_HIDDEN
              and n not in _INSTANCED]
    for nm in static:
        V, F = _load(nm)
        if V is None:
            continue
        col = PALETTE["frame"] if nm in ("L_Frame", "R_Frame") else PALETTE["body"]
        parts.append(Part(V, F, col, nm))

    # ── B. 4 main servo arms (white horns), instanced + IK-rotated ──
    Varm, Farm = _load("Arm")
    if Varm is not None:
        for sname, stype, sx, sy, _sign in SERVO_SLOTS:
            if stype != "main":
                continue
            is_left = sx < 0
            V = Varm.copy()
            if is_left:
                V = V * np.array([-1, 1, 1.0])
                F = Farm[:, ::-1]
                piv = np.array([-ARM_PIVOT_STL[0], ARM_PIVOT_STL[1], ARM_PIVOT_STL[2]])
            else:
                F = Farm
                piv = np.array(ARM_PIVOT_STL)
            shaft = np.array([sx, sy, SR6["servoPivotH"]])
            delta = math.degrees(geom["arm_angles"][sname] - home["arm_angles"][sname])
            Vt = (V - piv) @ _Ry(delta).T + shaft
            parts.append(Part(Vt, F, PALETTE["horn"], f"Arm_{sname}"))

    # ── B2. pitch horns (white) ──
    for pname in ("L_Pitcher", "R_Pitcher"):
        V, F = _load(pname)
        if V is None:
            continue
        sname = "LeftPitch" if pname.startswith("L_") else "RightPitch"
        delta = math.degrees(geom["arm_angles"][sname] - home["arm_angles"][sname])
        if abs(delta) > 0.01:
            sx = -FRAME_X if pname.startswith("L_") else FRAME_X
            piv = np.array([sx, 0, SR6["servoPivotH"]])
            V = (V - piv) @ _Ry(delta).T + piv
        parts.append(Part(V, F, PALETTE["horn"], pname))

    # ── C. receiver RING only (red) — 圆环中心落到接收器位姿 (tx,ty) + 安装环 Z ──
    mounts = np.array([geom["recv_mounts"][s] for s, _, _, _, _ in SERVO_SLOTS])
    mount_cz = float(mounts.mean(0)[2])
    V, F = _load(RECV_RING)
    if V is not None:
        rc = (V.min(0) + V.max(0)) / 2
        if abs(roll) > 0.01 or abs(pitch) > 0.01:
            V = (V - rc) @ _Rx(pitch).T @ _Ry(roll).T + rc
            rc = (V.min(0) + V.max(0)) / 2
        V = V - rc + np.array([tx, ty, mount_cz])
        parts.append(Part(V, F, PALETTE["recv"], RECV_RING))

    # ── D. 6 push-rods = REAL link STLs (tip→mount) + chrome ball joints ──
    for sname, stype, _sx, _sy, _sign in SERVO_SLOTS:
        tip = geom["arm_tips"][sname]
        mount = geom["recv_mounts"][sname]
        link = LINK_MAIN if stype == "main" else LINK_PITCH
        V, F = _place_link(link, tip, mount)
        if V is None:                       # fallback: thin rod
            V, F = cylinder(tip, mount, r=3.0)
        parts.append(Part(V, F, PALETTE["rod"], f"Rod_{sname}"))
        for pt in (tip, mount):
            Vs, Fs = uvsphere(pt, r=5.0)
            parts.append(Part(Vs, Fs, PALETTE["ball"], f"Ball_{sname}"))

    return parts


def _rot_a2b(a, b):
    """Rotation mapping unit vector a -> unit vector b (Rodrigues)."""
    a = a / (np.linalg.norm(a) or 1.0); b = b / (np.linalg.norm(b) or 1.0)
    v = np.cross(a, b); c = float(a @ b)
    if np.linalg.norm(v) < 1e-8:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1 + c)


FUSION_FIT = os.path.join(os.path.dirname(__file__), "assets", "fusion_fit.npz")


def build_fused(fit_path: str = FUSION_FIT) -> List[Part]:
    """Truth-fused assembly: every part placed by fitting the Tripo image-to-3D
    reconstruction (assets/ORS6_tripo.glb), NOT by forward IK assumptions.

    反者道之动 — the unpowered device rests in a slack pose unreachable by the
    symmetric servo IK, so position is *recovered from truth*:
      · rigid body  : similarity ICP  shell -> Tripo body cluster   (~4mm RMSE)
      · receiver ring: 6-DOF rigid ICP ring -> Tripo ring           (~1.6mm RMSE)
      · 6 push-rods : RANSAC line-detected directly in Tripo, real link STLs
    Transforms/segments are baked in assets/fusion_fit.npz (see ors6_work).
    """
    fit = np.load(fit_path)
    bc = float(fit["body_c"]); bR = fit["body_R"]; bt = fit["body_t"]
    rR = fit["recv_R"]; rt = fit["recv_t"]; rods = fit["rods"]

    def body_xf(V):
        return bc * (bR @ np.asarray(V).T).T + bt

    parts: List[Part] = []

    # A. rigid body (static structure) -> Tripo frame
    static = [n for n in PARTS if n not in RECV_PARTS and n not in DEFAULT_HIDDEN
              and n not in _INSTANCED]
    for nm in static:
        V, F = _load(nm)
        if V is None:
            continue
        col = PALETTE["frame"] if nm in ("L_Frame", "R_Frame") else PALETTE["body"]
        parts.append(Part(body_xf(V), F, col, nm))

    # C. receiver ring -> fitted 6-DOF pose
    V, F = _load(RECV_RING)
    if V is not None:
        parts.append(Part((rR @ V.T).T + rt, F, PALETTE["recv"], RECV_RING))

    # D. 6 push-rods on Tripo-detected segments + chrome balls
    seglen = [float(np.linalg.norm(p1 - p0)) for p0, p1 in rods]
    short2 = set(np.argsort(seglen)[:2].tolist())
    endpoints = []
    for ri, (p0, p1) in enumerate(rods):
        link = LINK_PITCH if ri in short2 else LINK_MAIN
        V, F = _place_link(link, p0, p1)
        if V is None:
            V, F = _place_link(LINK_MAIN, p0, p1)
        if V is not None:
            parts.append(Part(V, F, PALETTE["rod"], f"Rod_{ri}"))
        for pt in (p0, p1):
            endpoints.append(pt)
            Vs, Fs = uvsphere(pt, r=5.0)
            parts.append(Part(Vs, Fs, PALETTE["ball"], f"Ball_{ri}"))
    endpoints = np.array(endpoints)

    # B. servo arms (white) -> from each shaft toward nearest rod endpoint
    Varm, Farm = _load("Arm")
    if Varm is not None:
        ext = Varm.max(0) - Varm.min(0); ax = int(np.argmax(ext))
        c = (Varm.min(0) + Varm.max(0)) / 2
        ea = c.copy(); ea[ax] = Varm[:, ax].min()
        eb = c.copy(); eb[ax] = Varm[:, ax].max()
        nat = eb - ea
        for sname, _st, sx, sy, _sg in SERVO_SLOTS:
            sh = body_xf(np.array([sx, sy, SR6["servoPivotH"]]))[0]
            j = int(np.argmin(np.linalg.norm(endpoints - sh, axis=1)))
            be = endpoints[j]
            if np.linalg.norm(be - sh) > 90:
                continue
            Vt = (Varm - ea) @ _rot_a2b(nat, be - sh).T + sh
            parts.append(Part(Vt, Farm, PALETTE["horn"], f"Arm_{sname}"))

    return parts


def assembly_bounds(parts: List[Part]):
    allv = np.vstack([p.V for p in parts if len(p.V)])
    return allv.min(0), allv.max(0)


def render_views(pose=TCODE_HOME, out_dir="output/renders", label="home",
                 views=None, W=900, H=900):
    """Render the colored assembly from each view to PNG. Returns list of paths."""
    from PIL import Image
    parts = build_colored(pose)
    bounds = assembly_bounds(parts)
    views = views or VIEWS
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for vn, vd in views.items():
        img = render(parts, view_dir=vd, W=W, H=H, bounds=bounds)
        p = os.path.join(out_dir, f"ORS6_{label}_{vn}.png")
        Image.fromarray(img).save(p)
        paths.append(p)
    return paths


def render_fused_views(out_dir="output/renders", label="fused", views=None,
                       W=900, H=900):
    """Render the truth-fused assembly from each view to PNG."""
    from PIL import Image
    parts = build_fused()
    bounds = assembly_bounds(parts)
    views = views or VIEWS
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for vn, vd in views.items():
        img = render(parts, view_dir=vd, W=W, H=H, bounds=bounds)
        p = os.path.join(out_dir, f"ORS6_{label}_{vn}.png")
        Image.fromarray(img).save(p)
        paths.append(p)
    return paths


def export_fused_glb(out_path="output/ORS6_fused_colored.glb"):
    """Export the truth-fused colored assembly as a GLB scene."""
    import trimesh
    parts = build_fused()
    scene = trimesh.Scene()
    for p in parts:
        if len(p.F) == 0:
            continue
        m = trimesh.Trimesh(vertices=p.V, faces=p.F, process=False)
        col = (np.array([*p.color, 1.0]) * 255).astype(np.uint8)
        m.visual.face_colors = np.tile(col, (len(p.F), 1))
        scene.add_geometry(m, geom_name=p.name or "part")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    scene.export(out_path)
    return out_path


def export_glb(pose=TCODE_HOME, out_path="output/ORS6_home_colored.glb"):
    """Export the colored assembly as a single GLB scene (per-part face colors)."""
    import trimesh
    parts = build_colored(pose)
    scene = trimesh.Scene()
    for p in parts:
        if len(p.F) == 0:
            continue
        m = trimesh.Trimesh(vertices=p.V, faces=p.F, process=False)
        col = (np.array([*p.color, 1.0]) * 255).astype(np.uint8)
        m.visual.face_colors = np.tile(col, (len(p.F), 1))
        scene.add_geometry(m, geom_name=p.name or "part")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    scene.export(out_path)
    return out_path
