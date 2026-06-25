#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coarse interference / sanity check on the assembled SR6.

Mechanism parts touch at joints by design, so we report (a) link lengths vs
target, (b) pairwise mesh min-distance / penetration between non-adjacent
groups (structure vs links, link vs link), flagging only deep interpenetration.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, trimesh
import render as R

def main():
    items = R.build()
    asm = R.ASM
    print("=== link lengths (ball->pivot) ===")
    worst = 0.0
    for k, leg in asm["legs"].items():
        d = np.linalg.norm(np.array(leg["pivot"])-np.array(leg["ball"]))
        err = d-leg["target"]; worst = max(worst, abs(err))
        print("  %-5s %.2f mm  (target %.0f, err %+.3f)" % (k, d, leg["target"], err))
    print("  worst link error = %.4f mm" % worst)

    # transformed meshes
    meshes = {}
    for name, mesh, M, color in items:
        m = mesh.copy(); m.apply_transform(np.array(M)); meshes[name] = m

    from scipy.spatial import cKDTree
    def min_dist(a, b):
        return cKDTree(b.vertices).query(a.vertices)[0].min()
    def pierce(a, b):
        """count of a-vertices inside watertight b (interpenetration)."""
        try:
            if not b.is_watertight:
                return -1
            return int(b.contains(a.vertices).sum())
        except Exception:
            return -1

    print("=== link <-> link clearance (vertex KD min-dist) ===")
    links = sorted(n for n in meshes if n.startswith("Link_"))
    for i in range(len(links)):
        for j in range(i+1, len(links)):
            d = min_dist(meshes[links[i]], meshes[links[j]])
            if d < 6.0:
                print("  %-7s <-> %-7s  %.2f mm" % (links[i], links[j], d))
    print("  (only pairs closer than 6mm listed; tabs spread to avoid stacking)")

    print("=== link <-> box structure clearance ===")
    box = trimesh.util.concatenate([meshes[n] for n in
          ("Base","Lid","L_Frame","R_Frame")])
    for n in links:
        d = min_dist(meshes[n], box)
        p = pierce(meshes[n], box)
        flag = "  <-- PIERCE" if p > 5 else ""
        print("  %-7s min-dist to box = %6.2f mm  pierce_verts=%s%s" % (n, d, p, flag))

if __name__ == "__main__":
    main()
