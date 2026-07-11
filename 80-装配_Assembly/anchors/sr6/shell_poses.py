#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SR6 shell (Base / LFrame / RFrame / Lid) assembly poses, closed by bolts.

Defect this fixes: the shell STLs were treated as "authored in the world frame"
(identity poses), but the frame halves are authored in their PRINT pose (lying
flat, wall perpendicular to Z) and the base/lid are authored centred on y=0
while the firmware world convention keeps the MAIN PIVOTS at y=0 (the machine
body is offset +15mm toward +Y, where the pitch servos live).  The identity
poses therefore put the frames OUTSIDE the base -- the "bottom box looks
wrong / something reversed" symptom.

The poses here are closed by the physical bolt pattern, no taste involved:
  * LFrame print->assembly: Ry(+90) -- local z (wall normal) -> world +X,
    local x -> world -Z (feet down), local y -> world y.
        world = ( lz - 59.9,  ly + 15,  -lx - 40.3 )
    - x: servo flange face lz=11.9 -> world -48; axle face protrudes to -59.5
      = the firmware main-shaft plane.
    - y: main servo windows local y = 0,-30 -> world +15,-15 = main shafts;
      pitch window local y = +30 -> world +45 = pitch window.
    - z: M4 foot bores local x=-50.4 -> world z=10.1 = base boss bore height.
  * RFrame: the mirror, Ry(-90):  world = ( -lz + 59.9,  ly + 15,  lx - 40.3 ).
  * Base: authored upright; only the +15mm y offset.
  * Lid: authored floating above the base; +15mm y offset and dropped so its
    4 M3 bores (local z=85.4) meet the frame-top nut bores (world z=61.7):
    dz = -23.7.

verify() re-detects every mating bore pair on the real meshes and reports the
xy misalignment of each bolt line -- the shell is "assembled" iff all pairs
align within print tolerance.
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from uam.cylinders import detect_cylinders  # noqa: E402

STL = os.path.join(ROOT, "ground_truth", "stl")

Y_OFF = 15.0          # world y of the machine body centreline (main pivots at y=0)
FOOT_BORE_Z = 10.1    # base M4 boss bore height (detected on Base.stl)
FOOT_LOCAL_X = 50.4   # frame foot M4 bore |local x|
TOP_LOCAL_X = 102.0   # frame top M3 nut bore |local x|
WALL_T = 59.9         # frame local z=0 plane -> world |x| (flange 11.9 -> 48)
LID_BORE_Z = 85.4     # lid M3 bore z as authored


def Ry(deg):
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], float)


def _T(R, t):
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


CLEAR = 0.15   # mm residual penetration allowed at a printed seat


def _seat_z(mesh, others, direction, span=60.0):
    """Seat `mesh` against `others` by sliding along z*direction until contact.

    Returns the z offset at which the mesh moves as far as possible along
    direction (gravity for -1) while penetration stays <= CLEAR.  If it already
    penetrates at 0, it first backs out against the direction.
    """
    import trimesh as _tm

    cm = _tm.collision.CollisionManager()
    for i, o in enumerate(others):
        cm.add_object(str(i), o)

    def depth(dz):
        m = mesh.copy()
        m.apply_translation([0.0, 0.0, dz])
        hit, data = cm.in_collision_single(m, return_data=True)
        return max((c.depth for c in data), default=0.0) if hit else 0.0

    # free: the largest |dz| along -direction that is penetration-free
    free = None
    if depth(0.0) <= CLEAR:
        free = 0.0
    else:
        d = 0.5
        while d <= span:
            if depth(-direction * d) <= CLEAR:
                free = -direction * d
                break
            d *= 2
        if free is None:
            raise RuntimeError("cannot back the part out of penetration")
    # advance along direction from the free offset until contact
    a = free                       # free
    b = free + direction * span    # assumed blocked
    for _ in range(24):
        mid = 0.5 * (a + b)
        if depth(mid) <= CLEAR:
            a = mid
        else:
            b = mid
    return a


def shell_poses(seated=True):
    """4x4 world poses for the four shell parts (print frame -> assembly).

    The xy plane and rotations are closed by the bolt pattern; the z of the
    Base and Lid is closed by CONTACT with the frames (seated=True): the frames
    carry the firmware datum (axle z=46 -> tz=-40.3), the base is lowered until
    the frame feet rest on its floor rails, the lid is dropped until it seats
    on the frame tops.  seated=False returns the raw bolt-only poses.
    """
    tz = -(FOOT_LOCAL_X - FOOT_BORE_Z)          # -40.3: axle z=46, feet z=7.1
    top_z = TOP_LOCAL_X + tz                    # 61.7: frame-top nut bore height
    P = {
        "Base":   _T(np.eye(3), [0.0, Y_OFF, 0.0]),
        "Lid":    _T(np.eye(3), [0.0, Y_OFF, top_z - LID_BORE_Z]),
        "LFrame": _T(Ry(+90.0), [-WALL_T, Y_OFF, tz]),
        "RFrame": _T(Ry(-90.0), [+WALL_T, Y_OFF, tz]),
    }
    if not seated:
        return P

    import trimesh as _tm

    def placed(nm, T):
        m = _tm.load(os.path.join(STL, f"{nm}.stl"), process=False)
        m.apply_transform(T)
        return m

    frames = [placed(nm, P[nm]) for nm in ("LFrame", "RFrame")]
    # base: the frame feet rest on its floor rails.  The frames carry the
    # firmware z datum, so the base drops until the rails just meet the feet
    # (direction=+1: it backs out downward, then closes back up to contact).
    base = placed("Base", _T(np.eye(3), [0.0, Y_OFF, 0.0]))
    bz = _seat_z(base, frames, direction=+1)
    P["Base"] = _T(np.eye(3), [0.0, Y_OFF, bz])
    base.apply_translation([0.0, 0.0, bz])
    # lid: drop from its authored float until it seats on frames/base
    lid = placed("Lid", _T(np.eye(3), [0.0, Y_OFF, 0.0]))
    lz = _seat_z(lid, frames + [base], direction=-1)
    P["Lid"] = _T(np.eye(3), [0.0, Y_OFF, lz])
    return P


def _holes(stl, rmin, rmax):
    return [c for c in detect_cylinders(os.path.join(STL, stl), rmin=rmin, rmax=rmax)
            if c["kind"] == "hole"]


def _xf(T, p):
    return T[:3, :3] @ np.asarray(p, float) + T[:3, 3]


def verify(tol=0.5):
    """Re-detect every shell bolt bore and report per-pair xy misalignment."""
    P = shell_poses()
    rows = []

    base = [( _xf(P["Base"], c["center"]) ) for c in _holes("Base.stl", 1.9, 2.5)
            if abs(c["axis"][2]) > 0.9 and abs(c["center"][0]) > 30]
    lid = [( _xf(P["Lid"], c["center"]) ) for c in _holes("Lid.stl", 1.4, 2.0)
           if abs(c["axis"][2]) > 0.9]

    for nm in ("LFrame", "RFrame"):
        T = P[nm]
        hs = _holes(f"{nm}.stl", 1.0, 2.5)
        feet = [c for c in hs if c["radius"] > 2.0
                and abs(abs(c["center"][0]) - FOOT_LOCAL_X) < 1.0]
        tops = [c for c in hs if c["radius"] < 2.0
                and abs(abs(c["center"][0]) - TOP_LOCAL_X) < 1.5
                and abs(abs(np.dot(c["axis"], [1, 0, 0])) - 1.0) < 0.1]
        for c in feet:
            w = _xf(T, c["center"])
            d = min(np.hypot(*(w[:2] - b[:2])) for b in base)
            rows.append((f"{nm} foot->base", d))
        for c in tops:
            w = _xf(T, c["center"])
            d = min(np.hypot(*(w[:2] - l[:2])) for l in lid)
            rows.append((f"{nm} top->lid", d))

    ok = True
    for label, d in rows:
        flag = "ok" if d <= tol else "MISALIGNED"
        ok = ok and d <= tol
        print(f"  {label:20s} xy misalign = {d:5.2f} mm  [{flag}]")
    return ok


if __name__ == "__main__":
    if not verify():
        raise SystemExit("shell bolt pattern does not close")
