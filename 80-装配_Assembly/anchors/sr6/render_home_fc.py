#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render the solved SR6 home assembly (results/sr6_home_poses.json) -- the
same poses that freecad_build.py materialises into SR6_home.FCStd."""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import trimesh
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
STL = os.path.join(ROOT, "ground_truth", "stl")
OUT = os.path.join(ROOT, "results")

COLORS = {"Base": (.5, .5, .55, .25), "LFrame": (.35, .55, .8, .25),
          "RFrame": (.35, .55, .8, .25), "Lid": (.6, .6, .65, .15),
          "Receiver": (.85, .5, .3, .55)}


def color_of(name):
    if name in COLORS:
        return COLORS[name]
    if name.startswith(("Arm", "Pitcher")):
        return (.3, .7, .4, .9)
    return (.8, .25, .25, .9) if "main" in name else (.9, .55, .2, .9)


def main():
    with open(os.path.join(OUT, "sr6_home_poses.json")) as f:
        d = json.load(f)
    fig = plt.figure(figsize=(16, 8))
    for k, (nm, el, az) in enumerate(
            [("iso", 22, -60), ("front", 8, -90), ("side", 8, 0), ("top", 89, -90)]):
        ax = fig.add_subplot(1, 4, k + 1, projection="3d")
        allp = []
        for name, p in d["parts"].items():
            m = trimesh.load(os.path.join(STL, p["stl"]), process=False)
            m.apply_transform(np.asarray(p["T"], float))
            tris = m.vertices[m.faces]
            if len(tris) > 6000:
                idx = np.random.default_rng(0).choice(len(tris), 6000, replace=False)
                tris = tris[idx]
            pc = Poly3DCollection(tris, linewidths=0)
            pc.set_facecolor(color_of(name))
            ax.add_collection3d(pc)
            allp.append(m.vertices)
        P = np.vstack(allp)
        lo, hi = P.min(0), P.max(0)
        ctr, r = (lo + hi) / 2, (hi - lo).max() / 2
        ax.set_xlim(ctr[0] - r, ctr[0] + r)
        ax.set_ylim(ctr[1] - r, ctr[1] + r)
        ax.set_zlim(ctr[2] - r, ctr[2] + r)
        ax.view_init(el, az)
        ax.set_axis_off()
        ax.set_title(nm)
    fig.suptitle("SR6 home assembly (FreeCAD doc poses): "
                 "closure + bolt-axis + axial-stack validated")
    fig.tight_layout()
    path = os.path.join(OUT, "sr6_home_fc.png")
    fig.savefig(path, dpi=110)
    print("saved", path)


if __name__ == "__main__":
    main()
