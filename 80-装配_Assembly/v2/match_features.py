"""v2/match_features.py -- universal radius-matching to discover mate topology.

Detect cylindrical features on every part, then pair holes<->shafts whose radii
match within tolerance. This is how a CAD auto-mate discovers connectivity -- no
firmware, no hand topology. Output a ranked list of candidate coaxial mates.
"""
import os, sys, numpy as np, trimesh
sys.path.insert(0, os.path.dirname(__file__))
from cylinders import detect_cylinders

STL_DIR = os.path.join(os.path.dirname(__file__), "..", "ground_truth", "stl")
PARTS = ["Arm", "MainLink_Alpha", "PitcherLink_Alpha", "LPitcher", "RPitcher",
         "BearingMainLink", "BearingPitcherLink", "Receiver", "LFrame", "RFrame"]


def feats(name):
    m = trimesh.load(os.path.join(STL_DIR, name + ".stl"), process=True)
    out = []
    for c in detect_cylinders(m, min_faces=4, min_r=1.0, max_r=30,
                              lam_max=0.25, round_tol=0.4):
        out.append(c)
    return out


def main():
    table = {}
    print("=== features per part (r, kind, center) ===")
    for p in PARTS:
        cs = feats(p)
        table[p] = cs
        print(f"\n{p}: {len(cs)} cyls")
        for c in sorted(cs, key=lambda c: c.radius):
            print(f"   r={c.radius:5.2f} {c.kind:4s} c={np.round(c.center,1)} "
                  f"ax={np.round(c.axis,2)} half_len={c.half_len:4.1f}")
    print("\n=== candidate hole<->shaft matches (|dr|<0.6, opposite kind) ===")
    keys = list(table)
    for i, a in enumerate(keys):
        for b in keys[i+1:]:
            for ca in table[a]:
                for cb in table[b]:
                    if abs(ca.radius - cb.radius) < 0.6 and ca.kind != cb.kind:
                        print(f"  {a}.{ca.kind}(r{ca.radius:.2f}) <-> "
                              f"{b}.{cb.kind}(r{cb.radius:.2f})")
                        break


if __name__ == "__main__":
    main()
