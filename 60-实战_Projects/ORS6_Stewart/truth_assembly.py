# -*- coding: utf-8 -*-
"""ORS6_Stewart · truth_assembly — physically-correct STL assembly (道法自然).

Root fix vs all prior attempts:
  The Arm / Pitcher STL broad face is native +Z (print bed orientation), and the
  servo shaft is HORIZONTAL (±X, out of each side-frame wall).  Earlier pipelines
  kept the arm at its native orientation and merely spun it about the wrong axis,
  so the arm never actually pointed at its rod ball -> "floating / misaligned".

  Here every articulated arm is rigidly re-seated by a 2-point + plane feature
  alignment:  native hub -> servo shaft, native ball -> solved ball, native broad
  normal (+Z) -> the horizontal shaft axis (±X).  The swing angle is solved so the
  rod length is *exactly* 175 mm to the receiver anchor (physical spec).  The left
  frame uses a true geometric mirror (x -> -x, winding flipped), not a mirrored
  anchor on un-mirrored geometry.

Result (HOME / neutral pose), by construction, zero trial-and-error:
  - 6 rods all = 175.0 mm (4 main + 2 pitch)
  - arms <-> rods <-> receiver mesh with no gaps / no floating parts
  - per-part hardware colors (red body+rods, white horns, chrome balls, red cradle)

Reference: SR6 Build Instructions PDF (cover + p24 step 9 + p31 rod mounts).
"""
from __future__ import annotations
import math
import os
from typing import List

import numpy as np
import trimesh

from .render import Part, render, hex_rgb, cylinder, uvsphere
from .parts import PARTS, SR6, HOME_H, SERVO_SLOTS, RECV_PARTS, DEFAULT_HIDDEN, stl_path

# ----- hardware palette (matches real SR6 photos) -----------------------------
PAL = {
    "body": hex_rgb(0xD62828),
    "frame": hex_rgb(0xD62828),
    "recv": hex_rgb(0xC81F1F),
    "rod": hex_rgb(0xD62828),
    "horn": hex_rgb(0xF0ECE4),
    "ball": hex_rgb(0xC2C6CC),
}

ROD = 175.0                       # physical rod length (PDF p31)
H = SR6["servoPivotH"]            # servo shaft height above base (46 mm)
RECV_LIFT = np.array([0.0, 0.0, HOME_H])   # receiver origin at home (208.48 mm)

# receiver main-rod anchors in receiver-native STL coords (shared bolt per side)
ANCH_MAIN_L = np.array([-68.0, 0.0, -1.5])
ANCH_MAIN_R = np.array([68.0, 0.0, -1.5])
# pitch anchor: centered (X=0), upper mount zone (Z_local=+23), Y solved per side
PITCH_ANCH_Y = 53.35
PITCH_ANCH_Z = 23.0

# arm STL native features (hub bore / rod ball), right-hand frame
ARM_HUB = np.array([67.5, 0.0, 51.0])
ARM_BALL = np.array([67.5, 50.0, 51.0])


def _load(name):
    p = stl_path(name)
    if not os.path.exists(p):
        return None, None
    m = trimesh.load(p, force="mesh")
    return np.asarray(m.vertices, float), np.asarray(m.faces, int)


def solve_alpha(sx, sy, L, M, prefer_y_sign):
    """Arm swings in the Y-Z plane about the horizontal shaft at (sx, sy, H).
    ball = (sx, sy + L cos a, H + L sin a).  Solve |ball - M| = ROD; pick the
    branch whose ball points outward (prefer_y_sign)."""
    Mx, My, Mz = M
    dx = sx - Mx
    P = sy - My
    Q = H - Mz
    const = dx * dx + P * P + Q * Q + L * L
    A = 2 * L * P
    B = 2 * L * Q
    C = ROD * ROD - const
    R = math.hypot(A, B)
    if R < 1e-9:
        return None
    ratio = max(-1.0, min(1.0, C / R))
    phi = math.atan2(B, A)
    cand = []
    for a in (phi + math.acos(ratio), phi - math.acos(ratio)):
        cand.append((a, sy + L * math.cos(a), H + L * math.sin(a)))
    cand.sort(key=lambda t: prefer_y_sign * t[1], reverse=True)
    return cand[0]


def place_2pt(V, hub, ballnat, shaft, balli, shaft_axis):
    """Rigid re-seat: native (hub->ballnat, broad normal +Z) maps to
    (shaft->balli, shaft_axis).  Then translate hub onto shaft."""
    Ln = ballnat - hub
    Ln = Ln / (np.linalg.norm(Ln) or 1)
    Nn = np.array([0.0, 0.0, 1.0])
    Nn = Nn - Ln * (Nn @ Ln)
    Nn = Nn / (np.linalg.norm(Nn) or 1)
    Tn = np.cross(Ln, Nn)
    Li = balli - shaft
    Li = Li / (np.linalg.norm(Li) or 1)
    Ni = np.array(shaft_axis, float)
    Ni = Ni - Li * (Ni @ Li)
    Ni = Ni / (np.linalg.norm(Ni) or 1)
    Ti = np.cross(Li, Ni)
    Rm = np.column_stack([Li, Ni, Ti]) @ np.column_stack([Ln, Nn, Tn]).T
    return (V - hub) @ Rm.T + shaft


def place_link(name, p0, p1):
    """Seat a rod-link STL spanning p0->p1, uniformly scaled to that length."""
    V, F = _load(name)
    if V is None:
        return cylinder(p0, p1, r=3.5)
    c = (V.min(0) + V.max(0)) / 2
    ea = np.array([c[0], V[:, 1].max(), c[2]])
    eb = np.array([c[0], V[:, 1].min(), c[2]])
    al = eb - ea
    Ll = np.linalg.norm(al) or 1
    al = al / Ll
    nl = np.array([0.0, 0.0, 1.0])
    tl = np.cross(al, nl)
    at = np.array(p1) - np.array(p0)
    Tl = np.linalg.norm(at) or 1
    at = at / Tl
    nt = np.array([0.0, 1.0, 0.0])
    if abs(at @ nt) > 0.99:
        nt = np.array([0.0, 0.0, 1.0])
    nt = nt - at * (at @ nt)
    nt = nt / (np.linalg.norm(nt) or 1)
    tt = np.cross(at, nt)
    Rm = np.column_stack([at, nt, tt]) @ np.column_stack([al, nl, tl]).T
    s = Tl / Ll
    return (s * (V - ea)) @ Rm.T + np.array(p0), F


def build() -> List[Part]:
    parts: List[Part] = []

    # --- static body / frames (native assembly coords) ---
    static = [n for n in PARTS if n not in RECV_PARTS and n not in DEFAULT_HIDDEN
              and n not in ("Arm", "L_Pitcher", "R_Pitcher")]
    for nm in static:
        V, F = _load(nm)
        if V is None:
            continue
        col = PAL["frame"] if nm in ("L_Frame", "R_Frame") else PAL["body"]
        parts.append(Part(V, F, col, nm))

    # --- receiver cradle, elevated to home height ---
    V, F = _load("Receiver")
    if V is not None:
        parts.append(Part(V + RECV_LIFT, F, PAL["recv"], "Receiver"))

    anch = {
        "LowerLeft": ANCH_MAIN_L + RECV_LIFT, "UpperLeft": ANCH_MAIN_L + RECV_LIFT,
        "LowerRight": ANCH_MAIN_R + RECV_LIFT, "UpperRight": ANCH_MAIN_R + RECV_LIFT,
    }

    # --- 4 main legs (arm + 175 mm rod + ball joints) ---
    Varm, Farm = _load("Arm")
    for sname, stype, sx, sy, _sign in SERVO_SLOTS:
        if stype != "main":
            continue
        sax = 1.0 if sx > 0 else -1.0
        shaft = np.array([sx, sy, H])
        M = anch[sname]
        _a, by, bz = solve_alpha(sx, sy, SR6["mainArm"], M,
                                 prefer_y_sign=(1 if sy > 0 else -1))
        ball = np.array([sx, by, bz])
        if sx < 0:   # true geometric mirror for the left frame
            Vsrc = Varm * np.array([-1.0, 1.0, 1.0])
            Fsrc = Farm[:, ::-1]
            hub = ARM_HUB * np.array([-1.0, 1.0, 1.0])
            bn = ARM_BALL * np.array([-1.0, 1.0, 1.0])
        else:
            Vsrc, Fsrc, hub, bn = Varm, Farm, ARM_HUB.copy(), ARM_BALL.copy()
        Vt = place_2pt(Vsrc, hub, bn, shaft, ball, [sax, 0, 0])
        parts.append(Part(Vt, Fsrc, PAL["horn"], f"Arm_{sname}"))
        Vr, Fr = place_link("MainLink", ball, M)
        parts.append(Part(Vr, Fr, PAL["rod"], f"Rod_{sname}"))
        for pt in (ball, M):
            Vs, Fs = uvsphere(pt, r=5.0)
            parts.append(Part(Vs, Fs, PAL["ball"], "Ball"))

    # --- 2 pitch legs (L-bent pitcher arm + 175 mm rod) ---
    for pname, sname, sx in (("L_Pitcher", "LeftPitch", -99.6),
                             ("R_Pitcher", "RightPitch", 99.6)):
        V, F = _load(pname)
        if V is None:
            continue
        sax = 1.0 if sx > 0 else -1.0
        shaft = np.array([sx, 0.0, H])
        if pname == "L_Pitcher":
            hub = np.array([-7.5, 30.0, 51.75])
            bn = np.array([-39.74, 97.72, 50.25])
            ysign = 1
        else:
            hub = np.array([7.5, 30.0, 51.75])
            bn = np.array([39.74, 97.72, 50.25])
            ysign = -1
        M = np.array([0.0, ysign * PITCH_ANCH_Y, HOME_H + PITCH_ANCH_Z])
        L = np.linalg.norm(bn - hub)
        _a, by, bz = solve_alpha(sx, 0.0, L, M, prefer_y_sign=ysign)
        ball = np.array([sx, by, bz])
        Vt = place_2pt(V, hub, bn, shaft, ball, [sax, 0, 0])
        parts.append(Part(Vt, F, PAL["horn"], pname))
        Vr, Fr = place_link("PitcherLink", ball, M)
        parts.append(Part(Vr, Fr, PAL["rod"], f"Rod_{sname}"))
        for pt in (ball, M):
            Vs, Fs = uvsphere(pt, r=5.0)
            parts.append(Part(Vs, Fs, PAL["ball"], "Ball"))

    return parts


def export_glb(parts: List[Part], path: str) -> str:
    scene = trimesh.Scene()
    for p in parts:
        if len(p.F) == 0:
            continue
        m = trimesh.Trimesh(vertices=p.V, faces=p.F, process=False)
        col = (np.array([*p.color, 1.0]) * 255).astype(np.uint8)
        m.visual.face_colors = np.tile(col, (len(p.F), 1))
        scene.add_geometry(m, geom_name=p.name or "part")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    scene.export(path)
    return path


VIEWS = {"iso": (1, -1, 0.5), "front": (0, -1, 0.05), "side": (1, 0, 0.05), "top": (0, 0, 1)}


def main():
    from PIL import Image
    parts = build()
    allv = np.vstack([p.V for p in parts])
    bounds = (allv.min(0), allv.max(0))
    print("bounds", allv.min(0).round(1), allv.max(0).round(1))
    outdir = os.path.join(os.path.dirname(__file__), "output", "truth")
    os.makedirs(outdir, exist_ok=True)
    ims = []
    for vn, vd in VIEWS.items():
        img = render(parts, view_dir=vd, W=720, H=720, bounds=bounds)
        f = os.path.join(outdir, f"t_{vn}.png")
        Image.fromarray(img).save(f)
        ims.append(f)
    g = [Image.open(f) for f in ims]
    c = Image.new("RGB", (1440, 1440), "white")
    for k, im in enumerate(g):
        c.paste(im, ((k % 2) * 720, (k // 2) * 720))
    c.save(os.path.join(outdir, "truth_montage.png"))
    hero = render(parts, view_dir=(1.1, -1.0, 0.35), W=1000, H=1100, bounds=bounds)
    Image.fromarray(hero).save(os.path.join(outdir, "ORS6_hero.png"))
    print("glb:", export_glb(parts, os.path.join(outdir, "ORS6_truth.glb")))
    print("ok")


if __name__ == "__main__":
    main()
