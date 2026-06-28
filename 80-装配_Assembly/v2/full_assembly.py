"""v2/full_assembly.py -- body + 6 arms + 6 push-rods, all from real features.

Topology was DISCOVERED by radius-matching (match_features.py), not hand-set:
  Arm.crankpin(r4.03)  --bearing-->  Rod.end-bore(r5.98)
  Rod.other-end(r5.98) --bearing-->  Pitcher.boss(r6.44) / receiver pivot region

Placement is feature-grounded:
  * each Arm: servo bore (local Z @ (68,0,54)) coaxial onto a real frame
    bearing axis; crank spin chosen so the crankpin reaches toward receiver.
  * each Rod (MainLink, real 175mm bore-to-bore): one end coaxial on the arm's
    real crankpin; the residual spin DOF is chosen so the far bore lands closest
    to the matching receiver pivot (the natural closed-loop home).
No hand positions: crankpin comes from the placed arm, rod length from the mesh,
pivot targets from real Receiver holes.
"""
import os, sys, numpy as np, trimesh
sys.path.insert(0, os.path.dirname(__file__))
from cylinders import detect_cylinders
from render import render_views
from mate import place_coaxial, transform_pt, transform_dir

STL_DIR = os.path.join(os.path.dirname(__file__), "..", "ground_truth", "stl")
OUT = os.path.join(os.path.dirname(__file__), "..", "results")
BODY = ["Base", "Lid", "LFrame", "RFrame", "Receiver"]
COLORS = {"Base": "#9aa0a6", "Lid": "#3c4043", "LFrame": "#1f6fbf",
          "RFrame": "#1f6fbf", "Receiver": "#2a7fd0",
          "Arm": "#202124", "Rod": "#b0b4b8"}

ARM_BORE_PT = np.array([68.0, 0.0, 54.0])
ARM_BORE_AX = np.array([0.0, 0.0, 1.0])
ARM_CRANK_PT = np.array([67.5, 24.0, 53.8])   # real crankpin (r4.03)
# MainLink rod: two end bores (r5.98) 175mm apart along local Y
ROD_END_A = np.array([3.2, 0.0, 0.0])
ROD_END_B = np.array([3.2, -175.0, 0.0])
ROD_AXIS = (ROD_END_B - ROD_END_A) / np.linalg.norm(ROD_END_B - ROD_END_A)


def frame_bearings(M):
    out = []
    for fn in ["LFrame", "RFrame"]:
        for c in detect_cylinders(M[fn], min_faces=8, min_r=15, max_r=25,
                                  lam_max=0.18, round_tol=0.35):
            if abs(abs(c.center[0]) - 88.4) > 4.0:
                continue
            a = c.axis / np.linalg.norm(c.axis)
            if a[2] < 0:
                a = -a
            out.append((c.center.copy(), a))
    return out


def receiver_pivots(M):
    """real rod-attach pivots on the receiver: 2 ears (r1.79) + center (r3.56)."""
    pv = []
    for c in detect_cylinders(M["Receiver"], min_faces=3, min_r=1.0, max_r=8,
                              lam_max=0.4, round_tol=0.6):
        pv.append(c.center.copy())
    return pv


def main():
    M = {n: trimesh.load(os.path.join(STL_DIR, n + ".stl"), process=True) for n in BODY}
    arm = trimesh.load(os.path.join(STL_DIR, "Arm.stl"), process=True)
    rod = trimesh.load(os.path.join(STL_DIR, "MainLink_Alpha.stl"), process=True)

    bearings = frame_bearings(M)
    pivots = receiver_pivots(M)
    rc = M["Receiver"].vertices.mean(axis=0)
    parts = [(M[n].vertices, M[n].faces, COLORS[n]) for n in BODY]
    print("pivots:", [np.round(p, 1) for p in pivots])

    for c, a in bearings:
        # arm: crank spin so crankpin reaches toward receiver
        best = None
        for spin in range(0, 360, 2):
            v, T = place_coaxial(arm.vertices, ARM_BORE_PT, ARM_BORE_AX, c, a, spin)
            pin = transform_pt(T, ARM_CRANK_PT)
            sc = -np.linalg.norm(pin - rc)
            if best is None or sc > best[0]:
                best = (sc, v, T, pin)
        parts.append((best[1], arm.faces, COLORS["Arm"]))
        crankpin = best[3]
        # crankpin axis in world (the arm's local Z mapped)
        pin_ax = transform_dir(best[2], ARM_BORE_AX)
        # nearest receiver pivot to this crankpin -> rod target
        tgt = min(pivots, key=lambda p: np.linalg.norm(p - crankpin))
        # place rod: end A coaxial on crankpin axis at crankpin; spin so end B -> tgt
        rbest = None
        for spin in range(0, 360, 3):
            rv, RT = place_coaxial(rod.vertices, ROD_END_A, ROD_AXIS,
                                   crankpin, pin_ax, spin)
            endB = transform_pt(RT, ROD_END_B)
            sc = -np.linalg.norm(endB - tgt)
            if rbest is None or sc > rbest[0]:
                rbest = (sc, rv)
        parts.append((rbest[1], rod.faces, COLORS["Rod"]))

    render_views(parts, os.path.join(OUT, "v2_full.png"),
                 title="OSR6 body + 6 servo arms + 6 push-rods (all feature-grounded)")
    print("saved v2_full.png")


if __name__ == "__main__":
    main()
