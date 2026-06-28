# -*- coding: utf-8 -*-
"""Visual proof of the rigid-PLATFORM motion (closure_platform.py).

Renders the real STL assembly at three commanded heaves (dz = -20, 0, +20 mm).
The Receiver is the SAME rigid body translated by the SOLVED platform pose; every
leg's arm angle comes from the per-leg inverse kinematics, and each MainLink /
PitcherLink is drawn at the resulting arm-tip -> (pivot+dz) span.  Watching the
platform rise rigidly while the legs splay is the picture of the 6-DOF parallel
mechanism that closure_platform proved closes with RMS ~1e-14 mm.
"""
from __future__ import annotations
import os, sys, math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import trimesh                                                  # noqa: E402
from uam.cylinders import detect_cylinders                      # noqa: E402
from closure_firmware_6leg import solve_arm, recv_to_world, \
    MAIN_PIV_RECV, PITCH_PIV_RECV, SHAFT_Z, MAIN_ARM, MAIN_LINK, \
    PITCH_ARM, PITCH_LINK, HOME_H                                # noqa: E402

STL = os.path.join(ROOT, "ground_truth", "stl")
OUT = os.path.join(ROOT, "results"); os.makedirs(OUT, exist_ok=True)


def Rx(deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rigid_two_point(a_loc, b_loc, a_w, b_w):
    a_loc = np.asarray(a_loc, float); b_loc = np.asarray(b_loc, float)
    a_w = np.asarray(a_w, float); b_w = np.asarray(b_w, float)
    u = b_loc - a_loc; v = b_w - a_w
    u = u / (np.linalg.norm(u) + 1e-12); v = v / (np.linalg.norm(v) + 1e-12)
    w = np.cross(u, v); s = np.linalg.norm(w); c = float(np.dot(u, v))
    if s < 1e-9:
        R = np.eye(3) if c > 0 else -np.eye(3)
    else:
        wx = np.array([[0, -w[2], w[1]], [w[2], 0, -w[0]], [-w[1], w[0], 0]])
        R = np.eye(3) + wx + wx @ wx * ((1 - c) / (s * s))
    T = np.eye(4); T[:3, :3] = R; T[:3, 3] = a_w - R @ a_loc
    return T


def part_holes(name, **kw):
    return [c for c in detect_cylinders(os.path.join(STL, name), **kw) if c["kind"] == "hole"]


def legs_at(dz):
    """Per-leg IK at commanded heave dz: returns (name, shaft, tip, pivot)."""
    out = []
    for side in ("L", "R"):
        piv = recv_to_world(MAIN_PIV_RECV[side]) + np.array([0.0, 0.0, dz])
        for ysign, nm in ((+1, "lower"), (-1, "upper")):
            shaft = np.array([piv[0], recv_to_world(MAIN_PIV_RECV[side])[1] + ysign * 15.0, SHAFT_Z])
            hint = 0.0 if ysign > 0 else math.pi
            th, tip, res, ok = solve_arm(shaft, piv, MAIN_ARM, MAIN_LINK, hint)
            out.append((f"main-{side}-{nm}", shaft, tip, piv))
    for side in ("L", "R"):
        ppiv = recv_to_world(PITCH_PIV_RECV[side]) + np.array([0.0, 0.0, dz])
        shaft = np.array([MAIN_PIV_RECV[side][0], 61.25, SHAFT_Z])
        th, tip, res, ok = solve_arm(shaft, ppiv, PITCH_ARM, PITCH_LINK, 0.6)
        out.append((f"pitch-{side}", shaft, tip, ppiv))
    return out


def main():
    ah = part_holes("Arm.stl", rmin=1.0, rmax=5.0)
    a_shaft = min(ah, key=lambda c: abs(c["center"][1]))["center"]
    a_ball = max(ah, key=lambda c: c["center"][1])["center"]
    mh = sorted(part_holes("MainLink_Alpha.stl", rmin=2.5, rmax=8.0), key=lambda c: c["center"][1])
    ml_a, ml_b = mh[0]["center"], mh[-1]["center"]
    ph = sorted(part_holes("PitcherLink_Alpha.stl", rmin=2.5, rmax=8.0), key=lambda c: c["center"][1])
    pl_a, pl_b = ph[-1]["center"], ph[0]["center"]

    def pitcher_pts(name):
        h = part_holes(name, rmin=1.0, rmax=5.0)
        seat = [c for c in h if c["radius"] > 3.0]
        shaft = np.mean([c["center"] for c in seat], axis=0) if seat else h[0]["center"]
        ball = max(h, key=lambda c: c["center"][1])["center"]
        return shaft, ball
    lp_shaft, lp_ball = pitcher_pts("LPitcher.stl")
    rp_shaft, rp_ball = pitcher_pts("RPitcher.stl")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    fig = plt.figure(figsize=(16, 6))
    heaves = [(-20.0, "dz=-20mm (retracted)"), (0.0, "dz=0mm (home)"), (+20.0, "dz=+20mm (extended)")]
    for col, (dz, title) in enumerate(heaves):
        ax = fig.add_subplot(1, 3, col + 1, projection="3d")
        allpts = []

        def add_mesh(path, T, color, alpha):
            m = trimesh.load(path, process=False)
            V = (T[:3, :3] @ m.vertices.T).T + T[:3, 3] if T is not None else m.vertices
            tris = V[m.faces]
            if len(tris) > 6000:
                idx = np.random.default_rng(0).choice(len(tris), 6000, replace=False)
                tris = tris[idx]
            pc = Poly3DCollection(tris, linewidths=0.0)
            pc.set_facecolor((*[c / 255 for c in color[:3]], alpha)); ax.add_collection3d(pc)
            allpts.append(V)

        add_mesh(os.path.join(STL, "Base.stl"), None, [120, 120, 130], 0.20)
        add_mesh(os.path.join(STL, "LFrame.stl"), None, [90, 140, 200], 0.18)
        add_mesh(os.path.join(STL, "RFrame.stl"), None, [90, 140, 200], 0.18)
        # receiver: home Kabsch placement + SOLVED rigid heave (pure +dz translation)
        Trec = np.eye(4); Trec[:3, :3] = Rx(-90.0); Trec[:3, 3] = [0.0, 0.0, HOME_H + dz]
        add_mesh(os.path.join(STL, "Receiver.stl"), Trec, [210, 120, 70], 0.6)

        for nm, shaft, tip, piv in legs_at(dz):
            if nm.startswith("main"):
                add_mesh(os.path.join(STL, "Arm.stl"),
                         rigid_two_point(a_shaft, a_ball, shaft, tip), [70, 170, 90], 0.9)
                add_mesh(os.path.join(STL, "MainLink_Alpha.stl"),
                         rigid_two_point(ml_a, ml_b, tip, piv), [200, 60, 60], 0.9)
            else:
                side = nm.split("-")[1]
                ps, pb = (lp_shaft, lp_ball) if side == "L" else (rp_shaft, rp_ball)
                mesh = "LPitcher.stl" if side == "L" else "RPitcher.stl"
                add_mesh(os.path.join(STL, mesh),
                         rigid_two_point(ps, pb, shaft, tip), [70, 170, 140], 0.9)
                add_mesh(os.path.join(STL, "PitcherLink_Alpha.stl"),
                         rigid_two_point(pl_a, pl_b, tip, piv), [220, 130, 60], 0.9)
            ax.plot(*zip(shaft, tip, piv), color="k", lw=0.8, alpha=0.5)

        pts = np.vstack(allpts); lo = pts.min(0); hi = pts.max(0); ctr = (lo + hi) / 2
        r = 150.0
        ax.set_xlim(ctr[0] - r, ctr[0] + r); ax.set_ylim(ctr[1] - r, ctr[1] + r)
        ax.set_zlim(0, 320)
        ax.set_title(title); ax.view_init(elev=12, azim=-72)
        ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
    fig.suptitle("SR6 rigid-platform heave: one solved Receiver body, 6 legs articulate "
                 "(closure RMS ~1e-14 mm)", fontsize=12)
    fig.tight_layout()
    p = os.path.join(OUT, "platform_heave.png")
    fig.savefig(p, dpi=130); plt.close(fig); print("rendered", p)
    return p


if __name__ == "__main__":
    main()
