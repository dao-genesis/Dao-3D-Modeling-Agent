# -*- coding: utf-8 -*-
"""Honest multi-view characterization of the Tripo visual mesh.

Render the full Tripo mesh from a 3x3 azimuth orbit so we can discern what it
actually contains (does it carry the receiver ring? the 6 rods? the arms?)
rather than judging from a single fitted pose.  道.辨析.
"""
from __future__ import annotations
import os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dao_jiao as dj

d = np.load(os.path.join(HERE, "tripo_prepped.npz"))
pf = dj.PoseFitter(d["V"], d["F"], d["vcol"])

el = 20
azs = list(range(0, 360, 40))
fig, axs = plt.subplots(3, 3, figsize=(12, 12))
for ax, az in zip(axs.ravel(), azs):
    img, _ = pf.render_rgb(az, el, 420, 420)
    ax.imshow(img)
    ax.set_title(f"az={az} el={el}", fontsize=10)
    ax.axis("off")
axs.ravel()[-1].axis("off")
plt.suptitle("Tripo visual mesh - azimuth orbit (structure characterization)", fontsize=13)
plt.tight_layout()
p = os.path.join(HERE, "output", "tripo_orbit.png")
plt.savefig(p, dpi=95, bbox_inches="tight")
print("saved", os.path.basename(p))
