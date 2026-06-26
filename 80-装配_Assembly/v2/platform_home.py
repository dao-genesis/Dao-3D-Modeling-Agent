"""v2/platform_home.py -- the corrected model: receiver is an ELEVATED platform.

Root-cause finding: the main push-rod (MainLink) is 175mm bore-to-bore. With the
receiver at its low identity position it sits only ~75mm from each servo, so a
175mm rod can only splay outward (the classic 'lying-flat / wings' failure).

The firmware confirms the truth: SetMainServo home puts the receiver pivot
162.48mm from each servo axis (arm 50 + rod 175). For a servo at z~20 that places
the platform pivots ~150mm ABOVE the servos -- the receiver/cradle is a raised
moving platform (the tall sleeve in the reference photo), NOT a part at servo
level. Here we solve the platform's home elevation from that 162mm reach and
render real meshes there, with the rods rising up to it.
"""
import os, sys, numpy as np, trimesh
from scipy.optimize import least_squares
sys.path.insert(0, os.path.dirname(__file__))
from cylinders import detect_cylinders
from render import render_views
from mate import place_coaxial, transform_pt, transform_dir, rot_between

STL_DIR = os.path.join(os.path.dirname(__file__), "..", "ground_truth", "stl")
OUT = os.path.join(os.path.dirname(__file__), "..", "results")
FIXED = ["Base", "LFrame", "RFrame"]
PLATFORM = ["Receiver", "Lid"]
COLORS = {"Base": "#9aa0a6", "Lid": "#3c4043", "LFrame": "#1f6fbf",
          "RFrame": "#1f6fbf", "Receiver": "#2a7fd0",
          "Arm": "#202124", "Rod": "#b0b4b8"}
REACH = 162.48   # firmware home: receiver pivot distance from each servo axis
ARM_BORE_PT = np.array([68.0, 0.0, 54.0])
ARM_BORE_AX = np.array([0.0, 0.0, 1.0])
ARM_CRANK_PT = np.array([67.5, 24.0, 53.8])
ROD_A = np.array([3.2, 0.0, 0.0])
ROD_B = np.array([3.2, -175.0, 0.0])
ROD_AX = (ROD_B - ROD_A) / np.linalg.norm(ROD_B - ROD_A)


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


def build_platform(verbose=True):
    """build the full assembly parts list at the solved elevated-platform home.
    Returns (parts, dz)."""
    Mf = {n: trimesh.load(os.path.join(STL_DIR, n + ".stl"), process=True) for n in FIXED}
    Mp = {n: trimesh.load(os.path.join(STL_DIR, n + ".stl"), process=True) for n in PLATFORM}
    arm = trimesh.load(os.path.join(STL_DIR, "Arm.stl"), process=True)
    rod = trimesh.load(os.path.join(STL_DIR, "MainLink_Alpha.stl"), process=True)

    bearings = frame_bearings(M={**Mf})
    servo_c = np.array([c for c, a in bearings])
    print("servos:", np.round(servo_c, 1).tolist())

    # platform raise: pure +z translation dz that brings the receiver pivots
    # (ears) to ~REACH mm from their nearest servo (the firmware home reach).
    rec = Mp["Receiver"]
    ears = np.array([[-61, -14.2, 53.1], [61, -14.2, 53.1]])

    def resid(dz):
        z = dz[0]
        r = []
        for e in ears:
            ez = e + np.array([0, 0, z])
            d = min(np.linalg.norm(ez - s) for s in servo_c)
            r.append(d - REACH)
        return r
    sol = least_squares(resid, [90.0])
    dz = float(sol.x[0])
    if verbose:
        print(f"solved platform raise dz = {dz:.1f} mm  (residual {sol.cost:.2e})")

    shift = np.array([0, 0, dz])
    parts = [(Mf[n].vertices, Mf[n].faces, COLORS[n]) for n in FIXED]
    for n in PLATFORM:
        parts.append((Mp[n].vertices + shift, Mp[n].faces, COLORS[n]))
    rc = rec.vertices.mean(axis=0) + shift
    # candidate rod attachment points = the REAL receiver surface (raised).
    # No invented pivots: each rod connects to an actual receiver vertex, picked
    # so the rod's true 175mm length fits and rods distribute over the cradle.
    rec_v = rec.vertices + shift
    ROD_LEN = abs(ROD_B[1] - ROD_A[1])

    for c, a in bearings:
        best = None
        for spin in range(0, 360, 2):
            v, T = place_coaxial(arm.vertices, ARM_BORE_PT, ARM_BORE_AX, c, a, spin)
            pin = transform_pt(T, ARM_CRANK_PT)
            sc = -np.linalg.norm(pin - rc)
            if best is None or sc > best[0]:
                best = (sc, v, T, pin)
        parts.append((best[1], arm.faces, COLORS["Arm"]))
        crankpin = best[3]
        # the rod is a real 175mm two-bore link with a ball joint at the crankpin
        # (free swing). Among the real receiver-surface points on the SAME side
        # as this servo, choose the one whose distance best matches the rod's
        # 175mm length, then orient the rod's bore axis straight at it. Rods rise
        # and spread to distinct real contact points instead of splaying flat.
        same = rec_v[np.sign(rec_v[:, 0]) == np.sign(crankpin[0])]
        cand = same if len(same) else rec_v
        d = np.linalg.norm(cand - crankpin, axis=1)
        tgt = cand[np.argmin(np.abs(d - ROD_LEN))]
        direction = (tgt - crankpin)
        direction = direction / np.linalg.norm(direction)
        R = rot_between(ROD_AX, direction)
        rv = rod.vertices @ R.T + (crankpin - R @ ROD_A)
        parts.append((rv, rod.faces, COLORS["Rod"]))
        endB = R @ ROD_B + (crankpin - R @ ROD_A)
        if verbose:
            print(f"   crankpin {np.round(crankpin,1)} -> recv pt {np.round(tgt,1)} "
                  f"gap {np.linalg.norm(tgt-crankpin):.1f}mm endB-tgt "
                  f"{np.linalg.norm(endB-tgt):.1f}mm")
    return parts, dz


def main():
    parts, dz = build_platform()
    render_views(parts, os.path.join(OUT, "v2_platform.png"),
                 title=f"OSR6 elevated platform home (raise {dz:.0f}mm) + arms + rods")
    print("saved v2_platform.png")


if __name__ == "__main__":
    main()
