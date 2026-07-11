#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SR6 home: full rigid pose (4x4) for EVERY printed part, spin-DOF closed.

The abstract 6-leg closure (closure_firmware_6leg) fixes each leg's shaft, arm
tip and receiver pivot.  Placing a real STL between two points still leaves one
free spin about the point-pair line; earlier renders picked it arbitrarily.
Here the spin is closed PHYSICALLY: every mating bore on these parts is a bolt
axis, and on the assembled machine every one of those bolts runs along world X
(the servo shafts and all rod-end bolts are X-aligned; PDF pp.24-32).  So each
part pose is solved from TWO interface points PLUS the bore-axis direction --
a fully determined proper rigid transform (Kabsch on the virtual point set),
no residual freedom.

The remaining binary choice (axis sign = part flipped 180 deg about the pair
line) is closed by authority, not taste:
  * Arms/pitchers: the part must sit on the OUTSIDE of its frame wall for main
    arms and INSIDE for pitchers (PDF p.22: "2 pitch servos point inward, the
    4 main servos point outward") -> sign chosen so the arm body's mean-X falls
    on the required side of the shaft wall.
  * Links: symmetric about the pair line to within print detail; both signs are
    geometrically identical interfaces, the tab side is chosen per PDF p.31
    ("tabs pointing one up, one down") -> lower rod tab up, upper rod tab down.

Output: results/sr6_home_poses.json  {part -> {stl, T(4x4), interface points}}
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from closure_firmware_6leg import HOME_H, legs  # noqa: E402
from uam.cylinders import detect_cylinders  # noqa: E402

STL = os.path.join(ROOT, "ground_truth", "stl")
OUT = os.path.join(ROOT, "results")
X = np.array([1.0, 0.0, 0.0])


def kabsch(P, Q):
    """Proper rigid transform T (4x4) with T@P_i = Q_i (least squares)."""
    P = np.asarray(P, float)
    Q = np.asarray(Q, float)
    cp, cq = P.mean(0), Q.mean(0)
    H = (P - cp).T @ (Q - cq)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = cq - R @ cp
    return T


def pose_two_points_axis(a_loc, b_loc, ax_loc, a_w, b_w, ax_w):
    """Exact pose from two interface points + the (common) bore axis mapping.

    Uses virtual points a, b, a+40*axis, b+40*axis so Kabsch fully determines
    the rotation (no spin freedom left about the a-b line).
    """
    a_loc, b_loc = np.asarray(a_loc, float), np.asarray(b_loc, float)
    ax_loc = np.asarray(ax_loc, float) / np.linalg.norm(ax_loc)
    ax_w = np.asarray(ax_w, float) / np.linalg.norm(ax_w)
    P = [a_loc, b_loc, a_loc + 40 * ax_loc, b_loc + 40 * ax_loc]
    Q = [a_w, b_w, np.asarray(a_w) + 40 * ax_w, np.asarray(b_w) + 40 * ax_w]
    T = kabsch(P, Q)
    res = max(np.linalg.norm(T[:3, :3] @ p + T[:3, 3] - q) for p, q in zip(P, Q))
    return T, float(res)


def holes(path, **kw):
    return [c for c in detect_cylinders(path, **kw) if c["kind"] == "hole"]


def pair_by_span(feats, span, tol=2.0, perp=True):
    """Find the parallel-axis hole pair whose centre distance == span.

    perp=True measures ⊥ to the common axis (coplanar plate parts, where the
    detected centre's along-axis component is an arbitrary patch midpoint);
    perp=False measures the straight 3D distance (L-shaped links whose offset
    along the bolt axis is real geometry).
    """
    best = None
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            ci, cj = feats[i], feats[j]
            if abs(abs(float(np.dot(ci["axis"], cj["axis"]))) - 1.0) > 0.1:
                continue
            ax = np.asarray(ci["axis"], float)
            d = np.asarray(cj["center"], float) - np.asarray(ci["center"], float)
            if perp:
                d = d - np.dot(d, ax) * ax
            err = abs(np.linalg.norm(d) - span)
            if err < tol and (best is None or err < best[0]):
                best = (err, ci, cj)
    if best is None:
        raise RuntimeError(f"no hole pair with span {span}")
    return best[1], best[2]


def _coplanar(a, b, ax):
    """Drop b's arbitrary along-axis patch-midpoint offset relative to a."""
    d = b - a
    return a + (d - np.dot(d, ax) * ax)


def arm_interface():
    """Arm.stl: servo-axle bore + rod-end bolt hole, 50mm apart, axes local Z."""
    h = holes(os.path.join(STL, "Arm.stl"), rmin=1.0, rmax=5.0)
    ca, cb = pair_by_span(h, 50.0)
    # axle end = the larger bore (servo horn boss r~3.7); ball end = M4 (r~1.9)
    shaft, ball = (ca, cb) if ca["radius"] > cb["radius"] else (cb, ca)
    s = np.asarray(shaft["center"], float)
    ax = np.asarray(shaft["axis"], float)
    return s, _coplanar(s, np.asarray(ball["center"], float), ax), ax


def pitcher_interface(name):
    """L/RPitcher.stl: servo-axle centre + rod hole, 75mm apart."""
    h = holes(os.path.join(STL, name), rmin=1.0, rmax=6.0)
    ca, cb = pair_by_span(h, 75.0)
    shaft, ball = (ca, cb) if ca["radius"] > cb["radius"] else (cb, ca)
    s = np.asarray(shaft["center"], float)
    ax = np.asarray(shaft["axis"], float)
    return s, _coplanar(s, np.asarray(ball["center"], float), ax), ax


def link_interface(name):
    """Link STL: the two 6mm grommet bores (r~6), 175mm apart, axes local X."""
    h = holes(os.path.join(STL, name), rmin=4.5, rmax=8.0)
    span = 175.0 if "Main" in name else 185.0
    ca, cb = pair_by_span(h, span, perp=False)
    # arm end first (near local origin)
    a, b = sorted((ca, cb), key=lambda c: np.linalg.norm(c["center"]))
    return (np.asarray(a["center"], float), np.asarray(b["center"], float),
            np.asarray(a["axis"], float))


def Rx(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], float)


def solve_all():
    poses = {}

    def put(name, stl, T, res, iface=None):
        poses[name] = {"stl": stl, "T": np.asarray(T).tolist(),
                       "fit_residual_mm": res, "interface": iface or {}}

    # --- shell: print-frame STLs closed onto the world by their bolt pattern
    # (shell_poses.py: frames rotated vertical inside the base, body +15mm y) --
    from shell_poses import shell_poses, verify as verify_shell
    assert verify_shell(), "shell bolt pattern does not close"
    for nm, T in shell_poses().items():
        put(nm, f"{nm}.stl", T, 0.0)

    # --- receiver: Kabsch-proven home pose (closure_kabsch, RMS 0.014mm) ----
    Trec = np.eye(4)
    Trec[:3, :3] = Rx(-90.0)
    Trec[:3, 3] = [0.0, 0.0, HOME_H]
    put("Receiver", "Receiver.stl", Trec, 0.014)

    a_shaft, a_ball, a_ax = arm_interface()
    lp = pitcher_interface("LPitcher.stl")
    rp = pitcher_interface("RPitcher.stl")
    ml = link_interface("MainLink_Alpha.stl")
    pl = link_interface("PitcherLink_Alpha.stl")

    total = 0.0
    for nm, shaft, tip, piv, link, th, resid, ok in legs():
        assert ok, f"leg {nm} does not close"
        total += resid
        is_main = nm.startswith("main")
        # outward for main arms, inward for pitchers (PDF p.22)
        side = "L" if shaft[0] < 0 else "R"
        want_outward = is_main
        if is_main:
            s_loc, b_loc, ax_loc = a_shaft, a_ball, a_ax
            arm_stl, arm_name = "Arm.stl", f"Arm::{nm}"
        else:
            s_loc, b_loc, ax_loc = lp if side == "L" else rp
            arm_stl = f"{side}Pitcher.stl"
            arm_name = f"Pitcher::{nm}"
        best = None
        for sgn in (+1.0, -1.0):
            T, res = pose_two_points_axis(s_loc, b_loc, ax_loc, shaft, tip, sgn * X)
            # part-body mean x tells which side of the frame wall it ends on
            bulk = T[:3, :3] @ ((s_loc + b_loc) / 2 + 8.0 * ax_loc) + T[:3, 3]
            outward = abs(bulk[0]) > abs(shaft[0])
            score = (0 if outward == want_outward else 1, res)
            if best is None or score < best[0]:
                best = (score, T, res, sgn)
        _, T, res, sgn = best
        put(arm_name, arm_stl, T, res,
            {"shaft_world": list(map(float, shaft)), "tip_world": list(map(float, tip)),
             "axis_sign": sgn})

        link_stl = "MainLink_Alpha.stl" if is_main else "PitcherLink_Alpha.stl"
        a_loc, b_loc2, lax = ml if is_main else pl
        if is_main:
            # tabs one up one down (PDF p.31): lower rod bolt-axis +X, upper -X
            sgn = +1.0 if "lower" in nm else -1.0
            T, res = pose_two_points_axis(a_loc, b_loc2, lax, tip, piv, sgn * X)
        else:
            # L-shaped pitcher link: its 60mm along-bolt offset has no exact
            # planar embedding (docs/CLOSURE_FINDINGS #3c); the rod-end
            # bearings/grommets absorb the tilt.  Pick the diagonal-inward
            # orientation (PDF p.31) = the sign with the smaller honest
            # least-squares residual; report it, never zero it.
            cand = [pose_two_points_axis(a_loc, b_loc2, lax, tip, piv, s * X)
                    for s in (+1.0, -1.0)]
            (T, res), sgn = ((cand[0], +1.0) if cand[0][1] <= cand[1][1]
                             else (cand[1], -1.0))
        put(f"Link::{nm}", link_stl, T, res,
            {"tip_world": list(map(float, tip)), "pivot_world": list(map(float, piv)),
             "axis_sign": sgn})

    # close the bolt-axial stack DOF by contact (see stack_axial.py) ---------
    try:
        from stack_axial import close_axial_stack
        report = close_axial_stack(poses, STL)
        print("axial stack (dx along the bolt, residual joint depth):")
        for nm, (dx, resid) in report.items():
            print(f"  {nm:22s} dx={dx:+6.2f} mm  joint_depth={resid:5.2f} mm")
    except ImportError as e:  # python-fcl missing: poses stay point-closed
        print(f"!! axial stack pass skipped ({e}); poses are point-closed only")

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "sr6_home_poses.json")
    with open(path, "w") as f:
        json.dump({"home_h": HOME_H, "closure_residual_sum_mm": total,
                   "parts": poses}, f, indent=1)
    return path, poses, total


if __name__ == "__main__":
    path, poses, total = solve_all()
    print(f"=== SR6 home: full per-part rigid poses (spin closed by bolt axes) ===")
    for nm, p in poses.items():
        print(f"  {nm:22s} {p['stl']:22s} fit_residual={p['fit_residual_mm']:.3e} mm")
    print(f"\n  leg closure residual sum = {total:.3e} mm")
    print(f"  wrote {path}")
