"""tripo_comparison.py -- use an EXTERNAL image-to-3D reconstruction (TripoSR,
open-source, run via HuggingFace Space from the official SR6 photo) as an
independent ground-truth oracle, and measure where my mesh-snapped assembly
still disagrees with it.

Why: my dual critics (perceptual 2D + structural 3D) can still be fooled by
monocular depth ambiguity from a single viewpoint.  A neural single-image-to-3D
network hallucinates a *full 3D volume* consistent with the photo's shading, so
its multi-view geometry is an independent check on proportion / layout that a
single projection cannot give.

Pipeline:
  1. segment the real photo -> reference silhouette descriptors.
  2. load the TripoSR mesh; search viewpoints for the one whose silhouette best
     matches the photo (this recovers TripoSR's photo-consistent orientation).
  3. render my connected assembly from the canonical photo viewpoint.
  4. compare descriptors (both vs the real photo) + proportional metrics
     (TripoSR vs mine) and emit a 4-panel comparison + findings.
"""
import os, sys, math, json
import numpy as np
import trimesh
from PIL import Image
from scipy import ndimage

HERE = "C:/Users/Administrator/repos/Dao-3D-Modeling-Agent/80-装配_Assembly/v2"
sys.path.insert(0, HERE)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from assemble_connected import build
from perceptual_critic import segment_reference, descriptors, judge, silhouette

PHOTO = r"C:\Users\Administrator\attachments\2008e24e-4106-4c76-89a5-6823c2893ce1\SmartSelect_20260626_115856_Baidu.jpg"
TRIPO = r"C:\Users\Administrator\tripo_out\triposr.glb"
OUT = os.path.join(HERE, "tripo_vs_connected.png")


def _view_dirs(elev, azim):
    e, a = math.radians(elev), math.radians(azim)
    cam = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    up = np.array([0, 0, 1.0])
    right = np.cross(up, cam); right /= np.linalg.norm(right)
    trueup = np.cross(cam, right)
    return cam, right, trueup


def splat_mask(V, elev, azim, res=256, pad=0.08, splat=2):
    """Fast silhouette: project vertices, splat to a grid, close + fill holes.
    Same method used for BOTH meshes so descriptors are comparable."""
    cam, right, trueup = _view_dirs(elev, azim)
    ctr = (V.min(0) + V.max(0)) / 2
    span = (V.max(0) - V.min(0)).max() * (1 + 2 * pad)
    half = span / 2
    u = (V - ctr) @ right
    w = (V - ctr) @ trueup
    su = ((u + half) / span * (res - 1)).astype(int)
    sw = ((half - w) / span * (res - 1)).astype(int)
    ok = (su >= 0) & (su < res) & (sw >= 0) & (sw < res)
    m = np.zeros((res, res), bool)
    m[sw[ok], su[ok]] = True
    m = ndimage.binary_dilation(m, iterations=splat)
    m = ndimage.binary_closing(m, iterations=3)
    m = ndimage.binary_fill_holes(m)
    return m


def normalize_mask(mask, size=160):
    """Rotate so the silhouette major axis is horizontal, crop, resize to a
    square canvas -> a scale/rotation-normalised shape for IoU comparison."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 20:
        return np.zeros((size, size), bool)
    pts = np.column_stack([xs, ys]).astype(float)
    c = pts.mean(0)
    cov = np.cov((pts - c).T)
    ev, evec = np.linalg.eigh(cov)
    major = evec[:, -1]
    ang = math.degrees(math.atan2(major[1], major[0]))
    rot = ndimage.rotate(mask.astype(float), ang, reshape=True, order=0) > 0.5
    ys, xs = np.nonzero(rot)
    if len(xs) < 20:
        return np.zeros((size, size), bool)
    crop = rot[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(float)
    from scipy.ndimage import zoom
    zy, zx = size / crop.shape[0], size / crop.shape[1]
    return zoom(crop, (zy, zx), order=0) > 0.5


def iou(a, b):
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter) / float(union) if union else 0.0


def main():
    # 1) reference photo
    ref_mask = segment_reference(PHOTO)
    ref_d = descriptors(ref_mask)
    print("REF (photo):", ref_d)

    # 2) TripoSR mesh -> find photo-consistent viewpoint by max silhouette IoU
    ref_norm = normalize_mask(ref_mask)
    ref_norm_flip = ref_norm[::-1, ::-1]
    tm = trimesh.load(TRIPO, force="mesh", process=False)
    Vt = np.asarray(tm.vertices); Vt = Vt - Vt.mean(0)
    Ft = np.asarray(tm.faces)
    col = np.asarray(tm.visual.vertex_colors[:, :3]) / 255.0
    best = None
    for mirror in (False, True):
        Vm = Vt * np.array([-1, 1, 1.]) if mirror else Vt
        for elev in (-20, -10, 0, 10, 20, 30, 40, 50):
            for azim in range(-180, 180, 10):
                m = splat_mask(Vm, elev, azim)
                d = descriptors(m)
                if d["area"] < 100:
                    continue
                tn = normalize_mask(m)
                sc = max(iou(tn, ref_norm), iou(tn, ref_norm_flip))
                if best is None or sc > best[0]:
                    best = (sc, mirror, elev, azim, d, m)
    score, mirror, elev, azim, tri_d, tri_mask = best
    print(f"TRIPO best viewpoint mirror={mirror} elev={elev} azim={azim} IoU={score:.3f}")
    Vt_disp = Vt * np.array([-1, 1, 1.]) if mirror else Vt

    # final masks via the VALIDATED triangle-fill rasteriser (true holes; same
    # method that produced the prior PASS) -- removes the vertex-splat sampling
    # bias between a dense surface mesh and thin-rod parts.
    tri_parts = [(Vt_disp, Ft, "#cc2b1d")]
    tri_mask = silhouette(tri_parts, elev, azim, res=512)
    tri_d = descriptors(tri_mask)
    print("TRIPO descriptors:", tri_d)

    # 3) my connected assembly from the canonical photo viewpoint (roty -90, e22,a-65)
    parts = build(verbose=False)
    a = math.radians(-90)
    R = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    mine_parts = [(v @ R.T, f, c) for v, f, c in parts]
    mine_mask = silhouette(mine_parts, 22, -65, res=512)
    mine_d = descriptors(mine_mask)
    print("MINE descriptors:", mine_d)

    tri_verdict, tri_reasons = judge(tri_d, ref_d)
    mine_verdict, mine_reasons = judge(mine_d, ref_d)

    # 4) proportional metrics on the two silhouettes (TripoSR vs mine), each
    #    normalised by its own major-axis length -> scale-free shape comparison.
    def proportions(mask):
        ys, xs = np.nonzero(mask)
        pts = np.column_stack([xs, ys]).astype(float)
        c = pts.mean(0)
        cov = np.cov((pts - c).T)
        ev, evec = np.linalg.eigh(cov)
        major = evec[:, -1]
        proj = (pts - c) @ major
        L = proj.max() - proj.min()                 # major-axis length (px)
        perp = (pts - c) @ evec[:, 0]
        Wd = perp.max() - perp.min()                # minor-axis width
        # split silhouette into "near box end" vs "near ring end" halves
        order = np.argsort(proj)
        lo = proj < np.median(proj)
        end_lo = pts[proj < np.percentile(proj, 25)]
        end_hi = pts[proj > np.percentile(proj, 75)]
        # spread (perp extent) at each end -> box end is compact wide, ring end open
        def spread(p):
            if len(p) < 5: return 0.0
            pr = (p - c) @ evec[:, 0]
            return (pr.max() - pr.min())
        return dict(aspect=round(float(L / max(Wd, 1e-6)), 3),
                    end_spread_lo=round(spread(end_lo) / max(L, 1e-6), 3),
                    end_spread_hi=round(spread(end_hi) / max(L, 1e-6), 3))

    tri_p = proportions(tri_mask)
    mine_p = proportions(mine_mask)
    print("TRIPO proportions:", tri_p)
    print("MINE  proportions:", mine_p)

    # ---- 4-panel figure ----
    fig, ax = plt.subplots(1, 4, figsize=(22, 6))
    ax[0].imshow(Image.open(PHOTO)); ax[0].set_title("1. Real SR6 photo (ground truth)")
    # tripo colored point cloud at best viewpoint
    cam, right, trueup = _view_dirs(elev, azim)
    u = Vt_disp @ right; w = Vt_disp @ trueup
    order = np.argsort(Vt_disp @ cam)
    ax[1].scatter(u[order], w[order], c=col[order], s=2, marker=".")
    ax[1].set_aspect("equal"); ax[1].invert_yaxis()
    ax[1].set_title(f"2. TripoSR 3D (img->3D)  e{elev} a{azim}  IoU={score:.2f}")
    def cap(d):
        return (f"comp={d['n_components']} solidity={d['solidity']} "
                f"elong={d['elongation']} two_mass={d['two_mass']}")
    ax[2].imshow(tri_mask, cmap="gray_r")
    ax[2].set_title(f"3. TripoSR silhouette  [{tri_verdict}]\n{cap(tri_d)}", fontsize=9)
    ax[3].imshow(mine_mask, cmap="gray_r")
    ax[3].set_title(f"4. MY assembly silhouette  [{mine_verdict}]\n{cap(mine_d)}", fontsize=9)
    for a_ in ax: a_.set_xticks([]); a_.set_yticks([])
    fig.suptitle("Image->3D (TripoSR) as independent ground truth  vs  my mesh-snapped assembly  "
                 f"(ref photo: {cap(ref_d)})", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(OUT, dpi=110, facecolor="white")
    print("-> saved", OUT)

    findings = dict(ref=ref_d, tripo=tri_d, mine=mine_d,
                    tripo_verdict=tri_verdict, mine_verdict=mine_verdict,
                    tripo_proportions=tri_p, mine_proportions=mine_p,
                    tripo_viewpoint=dict(mirror=mirror, elev=elev, azim=azim))
    with open(os.path.join(HERE, "tripo_findings.json"), "w") as f:
        json.dump(findings, f, indent=2)
    print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
