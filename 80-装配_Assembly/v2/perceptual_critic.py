"""v2/perceptual_critic.py -- externalise the human "instant wrongness" judgement.

The structural critic (critic.py) measures 3D contact/penetration/symmetry.  This
module measures the *perceptual* gap that a human sees in a fraction of a second
when a render "does not look like the real machine".  The key realisation behind
this whole effort:

    I kept declaring assemblies "reasonable" because I NEVER rendered them from the
    real photo's viewpoint and compared the silhouette.  I optimised numeric proxies
    (residual -> 1e-14) and trusted an internal "looks like a machine" feeling.
    Humans instead do a holistic 2D gestalt comparison against the reference image.

So this critic does exactly that, mechanically:

  1. Segment the real machine out of its (wood) background -> reference mask.
  2. Render a candidate model to a silhouette mask from the same kind of viewpoint.
  3. Compute viewpoint-robust *layout descriptors* that encode the gestalt cues a
     human uses to spot wrongness:
        - n_components   : a real assembly is ONE connected body; a splayed/floating
                           model breaks into several blobs.  (the #1 cue)
        - solidity       : filled-area / convex-hull-area.  A dense machine is solid;
                           a sparse "red-stick tripod" is mostly empty hull.
        - elongation     : major/minor axis ratio of the silhouette (box->ring is
                           elongated; a symmetric tower/starfish is not).
        - fill_fraction  : silhouette area / bounding-box area.
        - two_mass       : is mass split into a dense lump (servo box) + a thin ring,
                           bridged by rods?  measured as the bimodality of the
                           row/col mass profile.
  4. Score each descriptor against the reference and emit PASS/FAIL + WHY.

No SR6-specific constant lives here; any (mesh,transform) list + reference photo works.
"""
import os
import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- #
#  segmentation: pull the (red/white/chrome) machine out of a wood background
# --------------------------------------------------------------------------- #
def segment_render(path, sat_th=0.18, val_th=0.15):
    """Mask the coloured parts of a matplotlib render (light/grey bg + gridlines).

    Parts are saturated colours; the axis panes, gridlines and white margin are
    grey/white (low saturation), so a saturation threshold isolates the model.
    """
    im = np.asarray(Image.open(path).convert("RGB")).astype(float) / 255.0
    mx = im.max(-1)
    mn = im.min(-1)
    sat = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0.0)
    mask = (sat > sat_th) & (mx > val_th)
    mask = ndimage.binary_closing(mask, iterations=2)
    mask = ndimage.binary_opening(mask, iterations=1)
    mask = ndimage.binary_fill_holes(mask)
    return mask


def segment_reference(path):
    """Return a boolean mask of the machine in a reference photo (wood bg)."""
    im = np.asarray(Image.open(path).convert("RGB")).astype(float) / 255.0
    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    mx = im.max(-1)
    mn = im.min(-1)
    sat = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0.0)
    # red plastic + chrome balls: green channel strongly suppressed vs red
    red = (R > 0.2) & (G < 0.6 * R) & (B < 0.75 * R)
    # white gears / bright plastic: very bright, low saturation (wood tops out lower)
    white = (mx > 0.92) & (sat < 0.25)
    # dark vents/shadow inside the body: very dark and low sat (wood is bright)
    dark = (mx < 0.18)
    mask = red | white | dark
    # clean up: keep the dominant blob, fill holes
    mask = ndimage.binary_closing(mask, iterations=3)
    mask = ndimage.binary_opening(mask, iterations=2)
    lab, n = ndimage.label(mask)
    if n:
        sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
        keep = np.argmax(sizes) + 1
        mask = lab == keep
    mask = ndimage.binary_fill_holes(mask)
    return mask


# --------------------------------------------------------------------------- #
#  rasterise a model (list of (verts_world, faces, color)) to a silhouette
# --------------------------------------------------------------------------- #
def _view_dirs(elev, azim):
    e, a = np.radians(elev), np.radians(azim)
    cam = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    up = np.array([0, 0, 1.0])
    right = np.cross(up, cam)
    right /= np.linalg.norm(right)
    trueup = np.cross(cam, right)
    return cam, right, trueup


def silhouette(parts, elev, azim, res=512, pad=0.06):
    """Project all triangles to screen and fill -> boolean silhouette mask."""
    cam, right, trueup = _view_dirs(elev, azim)
    allv = np.vstack([v for v, f, c in parts])
    ctr = (allv.min(0) + allv.max(0)) / 2
    span = (allv.max(0) - allv.min(0)).max() * (1 + 2 * pad)
    half = span / 2
    mask = np.zeros((res, res), bool)
    yy, xx = np.mgrid[0:res, 0:res]
    for v, f, c in parts:
        u = (v - ctr) @ right
        w = (v - ctr) @ trueup
        su = (u + half) / span * (res - 1)
        sw = (half - w) / span * (res - 1)            # flip for image coords
        tri = np.stack([su, sw], -1)[f]               # M,3,2
        # rasterise each triangle by barycentric test over its bbox
        for t in tri:
            x0 = int(max(0, np.floor(t[:, 0].min())))
            x1 = int(min(res - 1, np.ceil(t[:, 0].max())))
            y0 = int(max(0, np.floor(t[:, 1].min())))
            y1 = int(min(res - 1, np.ceil(t[:, 1].max())))
            if x1 < x0 or y1 < y0:
                continue
            px = xx[y0:y1 + 1, x0:x1 + 1]
            py = yy[y0:y1 + 1, x0:x1 + 1]
            (ax, ay), (bx, by), (cx, cy) = t
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(d) < 1e-9:
                continue
            l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
            l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
            l3 = 1 - l1 - l2
            inside = (l1 >= -1e-4) & (l2 >= -1e-4) & (l3 >= -1e-4)
            mask[y0:y1 + 1, x0:x1 + 1] |= inside
    return mask


# --------------------------------------------------------------------------- #
#  layout descriptors -- the gestalt cues, made numeric
# --------------------------------------------------------------------------- #
def descriptors(mask):
    m = mask.astype(bool)
    area = int(m.sum())
    if area < 10:
        return dict(n_components=0, solidity=0.0, elongation=0.0,
                    fill_fraction=0.0, two_mass=0.0, area=area)
    # connected components (8-connectivity), ignore specks < 0.5% of area
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1)) if n else []
    big = int((np.asarray(sizes) > 0.005 * area).sum()) if n else 0

    ys, xs = np.nonzero(m)
    h = ys.max() - ys.min() + 1
    w = xs.max() - xs.min() + 1
    fill_fraction = area / float(h * w)

    # solidity via convex hull area
    try:
        from scipy.spatial import ConvexHull
        pts = np.column_stack([xs, ys]).astype(float)
        hull = ConvexHull(pts)
        solidity = area / float(hull.volume)        # 2D: .volume == area
    except Exception:
        solidity = fill_fraction

    # elongation: principal-axis ratio from the mask covariance
    cov = np.cov(np.column_stack([xs, ys]).T)
    ev = np.sort(np.linalg.eigvalsh(cov))[::-1]
    elongation = float(np.sqrt(ev[0] / max(ev[1], 1e-6)))

    # two-mass / bimodality: project mass onto the major axis, measure how
    # bimodal it is (dense box at one end, ring at the other).  Use the
    # dip between the two halves' peaks relative to the valley.
    vec = np.linalg.eigh(cov)[1][:, -1]
    proj = (np.column_stack([xs, ys]) - [xs.mean(), ys.mean()]) @ vec
    hist, _ = np.histogram(proj, bins=24)
    hist = hist.astype(float)
    if hist.max() > 0:
        hs = ndimage.uniform_filter1d(hist, 3)
        mid = len(hs) // 2
        peakL = hs[:mid].max()
        peakR = hs[mid:].max()
        valley = hs[max(1, mid - 3):mid + 3].min()
        two_mass = float((min(peakL, peakR) - valley) / (max(peakL, peakR) + 1e-6))
    else:
        two_mass = 0.0
    return dict(n_components=big, solidity=round(float(solidity), 3),
                elongation=round(elongation, 2),
                fill_fraction=round(float(fill_fraction), 3),
                two_mass=round(two_mass, 3), area=area)


# --------------------------------------------------------------------------- #
#  compare candidate descriptors against reference -> PASS/FAIL + reasons
# --------------------------------------------------------------------------- #
def judge(cand, ref):
    """Return (verdict, reasons[]).  Reasons explain *what a human would see*."""
    reasons = []
    ok = True

    # 1) connectivity -- the single strongest cue
    if cand["n_components"] > ref["n_components"]:
        ok = False
        reasons.append(
            f"DISCONNECTED: model breaks into {cand['n_components']} separate "
            f"blobs; the real machine reads as {ref['n_components']} connected body "
            f"-> parts are floating / not joined (the splayed-tripod look).")
    else:
        reasons.append(f"connectivity ok ({cand['n_components']} vs ref {ref['n_components']})")

    # 2) solidity -- sparse stick-figure vs dense machine
    if cand["solidity"] < 0.55 * ref["solidity"]:
        ok = False
        reasons.append(
            f"TOO SPARSE: solidity {cand['solidity']} vs ref {ref['solidity']} "
            f"-> looks like thin sticks in empty space, not a solid body.")
    else:
        reasons.append(f"solidity ok ({cand['solidity']} vs ref {ref['solidity']})")

    # 3) elongation -- tower/starfish vs box->ring layout
    lo, hi = 0.55 * ref["elongation"], 1.8 * ref["elongation"]
    if not (lo <= cand["elongation"] <= hi):
        ok = False
        reasons.append(
            f"WRONG PROPORTION: elongation {cand['elongation']} vs ref "
            f"{ref['elongation']} -> aspect/orientation unlike the real machine "
            f"(e.g. a symmetric tower instead of an elongated box->ring layout).")
    else:
        reasons.append(f"elongation ok ({cand['elongation']} vs ref {ref['elongation']})")

    # 4) two-mass layout -- box + ring bridged by rods
    if cand["two_mass"] < 0.5 * ref["two_mass"] - 0.05:
        reasons.append(
            f"LAYOUT WEAK: two-mass score {cand['two_mass']} vs ref {ref['two_mass']} "
            f"-> missing the dense-box + thin-ring split the eye expects.")
    else:
        reasons.append(f"two-mass ok ({cand['two_mass']} vs ref {ref['two_mass']})")

    return ("PASS" if ok else "FAIL"), reasons


def report(name, cand, ref):
    verdict, reasons = judge(cand, ref)
    print(f"\n=== perceptual critic: {name} ===")
    print("  reference :", ref)
    print("  candidate :", cand)
    for r in reasons:
        print("   -", r)
    print(f"  VERDICT: {verdict}")
    return verdict
