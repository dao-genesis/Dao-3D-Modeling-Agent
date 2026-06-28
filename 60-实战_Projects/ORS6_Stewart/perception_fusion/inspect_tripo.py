# -*- coding: utf-8 -*-
"""Inspect the prepped Tripo mesh: bounds, color classes, axis structure."""
from __future__ import annotations
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
d = np.load(os.path.join(HERE, "tripo_prepped.npz"))
V, F, C = d["V"].astype(float), d["F"], d["vcol"].astype(float)
print("V", V.shape, "F", F.shape, "C", C.shape, "Crange", C.min(), C.max())
print("bounds min", V.min(0), "max", V.max(0))
print("size", V.max(0) - V.min(0))

r, g, b = C[:, 0], C[:, 1], C[:, 2]
mx, mn = C.max(1), C.min(1)
red = (r > 0.40) & (r - g > 0.18) & (r - b > 0.15)
white = (mn > 0.60) & ((mx - mn) < 0.18)
metal = (~red) & (~white) & (mn > 0.30)
print("class counts  red %d  white %d  metal %d  other %d" %
      (red.sum(), white.sum(), metal.sum(), (~(red | white | metal)).sum()))

# principal axis
Vc = V - V.mean(0)
U, S, Wt = np.linalg.svd(Vc, full_matrices=False)
print("singular values", S / S[0])
ax = Wt[0]
t = Vc @ ax
print("axis extent", t.min(), t.max())
# where are white (arms) vs red along axis
print("white arms axis mean", (Vc[white] @ ax).mean() if white.sum() else None)
print("red axis mean", (Vc[red] @ ax).mean() if red.sum() else None)
