# -*- coding: utf-8 -*-
"""道.感.校 — silhouette pose-fit oracle (reusable).

Given a mesh (V, F) and a target photo, search camera pose (az/el/roll/mirror)
for the maximum envelope-silhouette IoU against the segmented photo.  This is
the quantitative bridge between any 3D model (Tripo visual mesh OR firmware
skeleton STL) and the real hardware photo — the common judge of all directions.

道法自然: 感 (perceive) is the oracle; we do not trust the eye, we measure.
"""
from __future__ import annotations
import os, sys
import numpy as np
from scipy.ndimage import rotate as ndrotate, binary_closing, binary_fill_holes, zoom
from scipy import ndimage

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORIGIN = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "00-本源_Origin"))
if _ORIGIN not in sys.path:
    sys.path.insert(0, _ORIGIN)
import dao_perception as dp  # noqa: E402

import matplotlib.image as mpimg


# ---------------------------------------------------------------- photo seg
def segment_photo(rgb):
    """Segment the red/white/chrome SR6 from tan wood. Strict thresholds:
    the only reliable red-vs-wood discriminator is a large r-g gap."""
    if rgb.max() > 1.5:
        rgb = rgb / 255.0
    rgb = rgb[..., :3]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    red = (r > 0.45) & (r - g > 0.22) & (r - b > 0.20)
    white = (mn > 0.64) & ((mx - mn) < 0.14)
    chrome = (mn > 0.42) & ((mx - mn) < 0.12) & (mx < 0.76)
    m = red | white | chrome
    m = binary_closing(m, iterations=2)
    lab, n = ndimage.label(m)
    if n:
        sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
        keep = np.where(sizes > 0.004 * m.size)[0] + 1
        m = np.isin(lab, keep)
    return binary_fill_holes(m), rgb


def load_photo(path):
    return segment_photo(mpimg.imread(path).astype(float))


# ---------------------------------------------------------------- mask utils
def crop(mask):
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def fit_norm(m, S=256):
    """Envelope-fill + aspect-preserving center fit to S×S (scale invariant)."""
    m = binary_fill_holes(binary_closing(m, iterations=1))
    c = crop(m)
    if c is None:
        return np.zeros((S, S), bool)
    h, w = c.shape
    s = (S * 0.92) / max(h, w)
    z = zoom(c.astype(float), s, order=1) > 0.5
    out = np.zeros((S, S), bool)
    oh, ow = z.shape
    out[(S - oh) // 2:(S - oh) // 2 + oh, (S - ow) // 2:(S - ow) // 2 + ow] = z
    return out


def iou(a, b):
    return (a & b).sum() / max((a | b).sum(), 1)


# ---------------------------------------------------------------- pose fit
class PoseFitter:
    def __init__(self, V, F, vcol=None):
        self.V = np.asarray(V, float)
        self.F = np.asarray(F, int)
        self.vcol = None if vcol is None else np.asarray(vcol, float)
        self.fc = None if vcol is None else self.vcol[self.F].mean(1)
        self.C = self.V.mean(0)
        self.R = float(np.linalg.norm(self.V.max(0) - self.V.min(0))) * 1.05

    def render_mask(self, az, el, W=170, H=170):
        cam = dp.camera_orbit(self.C, self.R, az, el, width=W, height=H, fov_deg=35)
        return dp.render(self.V, self.F, cam)

    def render_rgb(self, az, el, W=560, H=560):
        rr = self.render_mask(az, el, W, H)
        img = np.ones((H, W, 3))
        m = rr.mask
        if self.fc is not None:
            img[m] = self.fc[rr.tri_id[m]] * (0.35 + 0.65 * rr.shaded[m])[:, None]
        else:
            img[m] = np.array([0.80, 0.15, 0.12]) * (0.35 + 0.65 * rr.shaded[m])[:, None]
        return img, m

    def _score_mask(self, mm, pf, rolls, mirrors=(0, 1)):
        best = (-1.0, 0, 0)
        for mir in mirrors:
            m0 = mm[:, ::-1] if mir else mm
            for roll in rolls:
                mr = m0 if roll == 0 else (ndrotate(m0.astype(float), roll, reshape=True, order=0) > 0.5)
                s = iou(pf, fit_norm(mr))
                if s > best[0]:
                    best = (s, mir, roll)
        return best

    def search(self, photo_mask, az_step=20, els=(-20, -5, 10, 25, 40, 55, 70),
               coarse_res=170, fine=True, log=print):
        pf = fit_norm(photo_mask)
        coarse = []
        for az in range(0, 360, az_step):
            for el in els:
                rr = self.render_mask(az, el, coarse_res, coarse_res)
                s, mir, roll = self._score_mask(rr.mask, pf, range(0, 360, 45))
                coarse.append((s, az, el, mir, roll))
        coarse.sort(reverse=True)
        if log:
            log("  coarse top3: " + ", ".join(
                f"{c[0]:.3f}@az{c[1]}el{c[2]}m{c[3]}r{c[4]}" for c in coarse[:3]))
        best = coarse[0]
        if fine:
            for s0, az0, el0, _, _ in coarse[:3]:
                for az in range(az0 - 15, az0 + 16, 5):
                    for el in range(el0 - 12, el0 + 13, 6):
                        rr = self.render_mask(az % 360, el, 240, 240)
                        s, mir, roll = self._score_mask(rr.mask, pf, range(0, 360, 15))
                        if s > best[0]:
                            best = (s, az % 360, el, mir, roll)
        return best  # (iou, az, el, mirror, roll)

    def fitted_render(self, az, el, mir, roll, W=560):
        img, mm = self.render_rgb(az, el, W, W)
        if mir:
            img, mm = img[:, ::-1], mm[:, ::-1]
        if roll:
            img = ndrotate(img, roll, reshape=True, order=1, cval=1.0)
            mm = ndrotate(mm.astype(float), roll, reshape=True, order=0) > 0.5
        return img, mm
