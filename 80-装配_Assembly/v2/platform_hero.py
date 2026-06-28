"""v2/platform_hero.py -- perspective hero of the full elevated-platform home
assembly (body + 6 servo cranks + rods rising to the receiver), side-by-side
vs the Ayva 3D reference photo."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from render import render_views
from platform_home import build_platform
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.image as mpimg

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
REF = os.path.join(os.path.dirname(__file__), "..", "ground_truth", "ref", "ayva_3d_ref.png")


def main():
    parts, dz = build_platform(verbose=False)
    render_views(parts, os.path.join(OUT, "v2_platform_hero.png"),
                 title=f"OSR6 full home assembly (platform raise {dz:.0f}mm)",
                 views=[("perspective", 16, -60)], figsize=(7, 8))
    hero = mpimg.imread(os.path.join(OUT, "v2_platform_hero.png"))
    fig, ax = plt.subplots(1, 2, figsize=(14, 7))
    if os.path.exists(REF):
        ax[0].imshow(mpimg.imread(REF))
    ax[0].set_title("reference (Ayva 3D)"); ax[0].axis("off")
    ax[1].imshow(hero)
    ax[1].set_title("v2 full home assembly"); ax[1].axis("off")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "v2_platform_vs_ref.png"), dpi=110)
    print("saved v2_platform_hero.png, v2_platform_vs_ref.png")


if __name__ == "__main__":
    main()
