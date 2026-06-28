"""v2/place_arms.py -- place the 4 servo cranks on the real frame bearings.

The frame bearings (r~19.4 bores on L/RFrame) are the servo axes in the shared
body frame. Each Arm mates COAXIALLY: its servo bore (local Z through (68,0,54))
onto a frame bearing axis at the bearing centre. The only free value is the
crank spin angle (a real joint DOF), chosen so the crankpin points up-inward
toward the receiver.
"""
import os, sys, numpy as np, trimesh
sys.path.insert(0, os.path.dirname(__file__))
from cylinders import detect_cylinders
from render import render_views
from mate import place_coaxial, transform_pt

STL_DIR = os.path.join(os.path.dirname(__file__), "..", "ground_truth", "stl")
OUT = os.path.join(os.path.dirname(__file__), "..", "results")

BODY = ["Base", "Lid", "LFrame", "RFrame", "Receiver"]
COLORS = {"Base": "#9aa0a6", "Lid": "#3c4043", "LFrame": "#1f6fbf",
          "RFrame": "#1f6fbf", "Receiver": "#2a7fd0", "Arm": "#202124"}

# Arm local servo-bore feature
ARM_BORE_PT = np.array([68.0, 0.0, 54.0])
ARM_BORE_AX = np.array([0.0, 0.0, 1.0])
ARM_CRANK_PT = np.array([67.5, 24.0, 53.8])  # crankpin (24mm crank)


def frame_bearings(M):
    """return list of (center, axis) for the 4 servo bearings on L/RFrame.

    The true servo axes are the 4 symmetric corner bores at |x|~88 (two per
    side: a low-front and a high-back servo). Other large bores (mounting
    holes near |x|~96, near-vertical axis) are rejected by symmetry/position.
    """
    out = []
    for fn in ["LFrame", "RFrame"]:
        cs = detect_cylinders(M[fn], min_faces=8, min_r=15, max_r=25,
                              lam_max=0.18, round_tol=0.35)
        for c in cs:
            if abs(abs(c.center[0]) - 88.4) > 4.0:   # keep the 4 servo bores
                continue
            ax = c.axis / np.linalg.norm(c.axis)
            if ax[2] < 0:
                ax = -ax  # orient axes consistently +Z-ish
            out.append((c.center.copy(), ax))
    return out


def main():
    M = {n: trimesh.load(os.path.join(STL_DIR, n + ".stl"), process=True) for n in BODY}
    arm = trimesh.load(os.path.join(STL_DIR, "Arm.stl"), process=True)

    bearings = frame_bearings(M)
    print("frame servo bearings (body frame):")
    for c, a in bearings:
        print("   C=", np.round(c, 1), "ax=", np.round(a, 2))

    parts = [(M[n].vertices, M[n].faces, COLORS[n]) for n in BODY]
    rc = M["Receiver"].vertices.mean(axis=0)  # receiver centroid (body frame)
    print("receiver centroid", np.round(rc, 1))

    # place an Arm on each bearing; the residual crank-spin DOF is set so the
    # crankpin reaches toward the receiver (shortest pin->receiver distance) --
    # the natural home pose where the push-rod can close onto the receiver.
    for c, a in bearings:
        best = None
        for spin in range(0, 360, 2):
            v, T = place_coaxial(arm.vertices, ARM_BORE_PT, ARM_BORE_AX, c, a, spin)
            pin = transform_pt(T, ARM_CRANK_PT)
            score = -np.linalg.norm(pin - rc)
            if best is None or score > best[0]:
                best = (score, v, T, pin)
        parts.append((best[1], arm.faces, COLORS["Arm"]))
        print("   -> crankpin world", np.round(best[3], 1))

    render_views(parts, os.path.join(OUT, "v2_arms.png"),
                 title="OSR6 body + 4 servo cranks on real frame bearings")
    print("saved v2_arms.png")


if __name__ == "__main__":
    main()
