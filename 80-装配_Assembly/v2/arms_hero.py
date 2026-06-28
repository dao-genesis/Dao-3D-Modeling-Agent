"""v2/arms_hero.py -- perspective hero of body+4 servo arms, side-by-side vs ref."""
import os, sys, numpy as np, trimesh
sys.path.insert(0, os.path.dirname(__file__))
from render import render_views
from place_arms import frame_bearings, ARM_BORE_PT, ARM_BORE_AX, ARM_CRANK_PT, BODY, COLORS
from mate import place_coaxial, transform_pt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.image as mpimg

STL_DIR = os.path.join(os.path.dirname(__file__), "..", "ground_truth", "stl")
OUT = os.path.join(os.path.dirname(__file__), "..", "results")
REF = os.path.join(os.path.dirname(__file__), "..", "ground_truth", "ref", "ayva_3d_ref.png")


def build_parts():
    M = {n: trimesh.load(os.path.join(STL_DIR, n + ".stl"), process=True) for n in BODY}
    arm = trimesh.load(os.path.join(STL_DIR, "Arm.stl"), process=True)
    parts = [(M[n].vertices, M[n].faces, COLORS[n]) for n in BODY]
    rc = M["Receiver"].vertices.mean(axis=0)
    for c, a in frame_bearings(M):
        best = None
        for spin in range(0, 360, 2):
            v, T = place_coaxial(arm.vertices, ARM_BORE_PT, ARM_BORE_AX, c, a, spin)
            pin = transform_pt(T, ARM_CRANK_PT)
            score = -np.linalg.norm(pin - rc)
            if best is None or score > best[0]:
                best = (score, v)
        parts.append((best[1], arm.faces, COLORS["Arm"]))
    return parts


def main():
    parts = build_parts()
    render_views(parts, os.path.join(OUT, "v2_arms_hero.png"),
                 title="OSR6 body + 4 servo cranks (feature-mated to real bearings)",
                 views=[("perspective", 18, -58)], figsize=(7, 7))
    hero = mpimg.imread(os.path.join(OUT, "v2_arms_hero.png"))
    ref = mpimg.imread(REF)
    fig, ax = plt.subplots(1, 2, figsize=(14, 6))
    ax[0].imshow(ref); ax[0].set_title("reference (Ayva 3D)"); ax[0].axis("off")
    ax[1].imshow(hero); ax[1].set_title("v2 body + servo arms"); ax[1].axis("off")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "v2_arms_vs_ref.png"), dpi=110)
    print("saved v2_arms_hero.png, v2_arms_vs_ref.png")


if __name__ == "__main__":
    main()
