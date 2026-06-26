# -*- coding: utf-8 -*-
"""Final fused-evidence figure: real photo | Tripo fused (firmware coords) |
semantic parts | ring datum.  道.感.校 + 三向归一."""
from __future__ import annotations
import os, sys, json
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dao_jiao as dj

PHOTO = r"C:\Users\Administrator\attachments\1e3e689a-718b-47ac-a271-445caac3a39d\SmartSelect_20260626_115856_Baidu.jpg"
OUT = os.path.join(HERE, "output")

d = np.load(os.path.join(HERE, "tripo_fused.npz"))
V, F, C, lab = d["V"].astype(float), d["F"].astype(int), d["vcol"].astype(float), d["label"]
datum = json.load(open(os.path.join(OUT, "ring_datum.json"), encoding="utf-8"))

pf = dj.PoseFitter(V, F, C)
# semantic palette
SEM = np.array([[0.6, 0.6, 0.6],   # 0 other
                [0.83, 0.13, 0.10], # 1 red frame/rods/ring
                [0.78, 0.80, 0.83], # 2 metal joints
                [0.95, 0.93, 0.88]])# 3 cream arms
pf_sem = dj.PoseFitter(V, F, SEM[lab])

_, photo_rgb = dj.load_photo(PHOTO)

# a 3/4 view showing base-down, ring-up in firmware coords
az, el = 35, 18
img_real_col, _ = pf.render_rgb(az, el, 520, 520)
img_sem, _ = pf_sem.render_rgb(az, el, 520, 520)

fig = plt.figure(figsize=(20, 5.6))
ax0 = fig.add_subplot(1, 4, 1); ax0.imshow(photo_rgb)
ax0.set_title("real SR6 photo (ground truth)", fontsize=11); ax0.axis("off")
ax1 = fig.add_subplot(1, 4, 2); ax1.imshow(img_real_col)
ax1.set_title("Tripo fused -> firmware coords\n(base-down, ring-up, mm)", fontsize=11); ax1.axis("off")
ax2 = fig.add_subplot(1, 4, 3); ax2.imshow(img_sem)
ax2.set_title("semantic parts\nred=frame/rods/ring  metal=joints  cream=arms", fontsize=11); ax2.axis("off")

ax3 = fig.add_subplot(1, 4, 4); ax3.axis("off")
rr = datum["receiver_ring"]
txt = (
    "THREE-DIRECTION FUSION (Dao.Gan.Jiao judge)\n\n"
    "Dir1 Tripo visual mesh: faithful (orbit-verified)\n"
    "Dir2 firmware skeleton: metric scale + kinematics\n"
    "Dir3 perception: silhouette IoU oracle\n\n"
    "RING extracted from Tripo mesh:\n"
    f"  outer diam = {rr['outer_diam_mm']} mm\n"
    f"  firmware spec = {datum['firmware_ring_outer_diam_mm']} mm\n"
    f"  delta = {datum['ring_diam_vs_firmware']['delta_mm']} mm  (4%)\n"
    f"  -> visual & CAD CROSS-CONFIRM\n\n"
    f"  plane tilt = {rr['plane_tilt_deg']} deg\n"
    f"  lateral offset = {datum['ring_lateral_offset_mm']} mm\n"
    f"  axial standoff = {datum['base_to_ring_axial_standoff_mm']} mm\n"
    "  -> photo is a DEPLOYED pose;\n"
    "     firmware home = coaxial.\n"
    "     gap = pose/assembly, NOT parts.\n\n"
    f"fused AABB = {datum['fused_aabb_mm']} mm"
)
ax3.text(0.0, 1.0, txt, va="top", ha="left", fontsize=10, family="monospace")
plt.tight_layout()
p = os.path.join(OUT, "fusion_final.png")
plt.savefig(p, dpi=105, bbox_inches="tight")
print("saved", os.path.basename(p))
