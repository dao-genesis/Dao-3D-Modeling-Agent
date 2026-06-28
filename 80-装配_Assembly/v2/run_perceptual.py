"""Driver: prove the perceptual critic PASSES the validated ground-truth model and
FAILS the old "RMS=0.000 but looks wrong" tower -- the model I used to call
"reasonable" without ever comparing it to the photo.

Outputs:
  - seg_check.png / seg_mask.png   : reference machine segmentation
  - perceptual_panel.png           : photo | GT(horizontal) | GT(tower) | broken
  - prints descriptors + PASS/FAIL + reasons for each candidate
"""
import os, sys
import numpy as np
from PIL import Image
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import perceptual_critic as pc
from platform_home import build_platform

REF = os.path.join(HERE, "ref_machine.jpg")
GT_STL = os.path.join(HERE, "ORS6_home.stl")


def _roty(v, deg):
    if not deg:
        return v
    a = np.radians(deg)
    Ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    return v @ Ry.T


def gt_parts(rot_deg_y):
    """Validated fused home assembly; rot=-90 lays the main axis horizontal
    (photo-like), rot=0 keeps the Z-up 'tower' view I kept rendering."""
    m = trimesh.load(GT_STL, process=False)
    v = m.vertices.copy() - m.vertices.mean(0)
    return [(_roty(v, rot_deg_y), m.faces, "tab:red")]


def broken_parts(rot_deg_y):
    """The old 'platform raised +Z' model (4 splayed rods + floating ring),
    rendered through the SAME pipeline/viewpoint as GT for a fair comparison."""
    parts, _ = build_platform(verbose=False)
    allv = np.vstack([v for v, f, c in parts])
    ctr = allv.mean(0)
    return [(_roty(v - ctr, rot_deg_y), f, c) for v, f, c in parts]


def main():
    # 1) reference
    ref_mask = pc.segment_reference(REF)
    ref_im = np.asarray(Image.open(REF).convert("RGB"))
    ov = ref_im.copy(); ov[ref_mask] = (0, 255, 0)
    Image.fromarray((0.5 * ref_im + 0.5 * ov).astype(np.uint8)).save(os.path.join(HERE, "seg_check.png"))
    ref_d = pc.descriptors(ref_mask)

    # 2) candidates -- ALL rendered through the same silhouette pipeline, same
    #    photo-like viewpoint, so the comparison is apples-to-apples.
    VIEW = dict(elev=22, azim=-65, res=600)
    gt_h = pc.silhouette(gt_parts(-90), **VIEW)
    gt_h_d = pc.descriptors(gt_h)
    br_h = pc.silhouette(broken_parts(-90), **VIEW)
    br_h_d = pc.descriptors(br_h)
    #   GT tower: the Z-up view I kept rendering and calling "reasonable"
    gt_t = pc.silhouette(gt_parts(0), elev=18, azim=-60, res=600)
    gt_t_d = pc.descriptors(gt_t)

    print("REFERENCE :", ref_d)
    v_h = pc.report("GT model (horizontal, photo-like view)", gt_h_d, ref_d)
    v_b = pc.report("OLD broken model (+Z platform, splayed rods)", br_h_d, ref_d)
    v_t = pc.report("GT model (Z-up 'tower' view I used to render)", gt_t_d, ref_d)

    # 3) visual panel ----------------------------------------------------------
    fig, ax = plt.subplots(1, 4, figsize=(20, 5))
    ax[0].imshow(ref_im); ax[0].set_title("real photo (reference)")
    ax[1].imshow(gt_h, cmap="Greens_r"); ax[1].set_title(f"GT horizontal -> {v_h}")
    ax[2].imshow(br_h, cmap="Reds_r"); ax[2].set_title(f"old +Z platform -> {v_b}")
    ax[3].imshow(gt_t, cmap="Oranges_r"); ax[3].set_title(f"GT tower view -> {v_t}")
    for a in ax:
        a.axis("off")
    fig.suptitle("Perceptual critic: same gestalt cues a human uses, made measurable", fontsize=13)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "perceptual_panel.png"), dpi=110, facecolor="white")
    print("\nwrote perceptual_panel.png")


if __name__ == "__main__":
    main()
