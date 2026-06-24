# -*- coding: utf-8 -*-
"""反向审视 · 装配输出 STL 实测.

目标: 用 trimesh 直接读 ORS6_home.stl, 看 4 个 Arm + 2 Pitcher 实际世界位置.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import trimesh
import numpy as np

OUTPUT_STL = "ORS6_Stewart/output/ORS6_home.stl"

m = trimesh.load(OUTPUT_STL)
print(f"=== ORS6_home.stl ===")
print(f"  type: {type(m).__name__}")
if hasattr(m, "geometry"):
    # Scene with multiple parts
    print(f"  Geometries: {len(m.geometry)}")
    for name, geom in m.geometry.items():
        b = geom.bounds
        center = [(b[0][i] + b[1][i]) / 2 for i in range(3)]
        size = [b[1][i] - b[0][i] for i in range(3)]
        print(f"    {name:25s}  center=({center[0]:+7.1f},{center[1]:+7.1f},{center[2]:+7.1f})  "
              f"size=({size[0]:5.1f}x{size[1]:5.1f}x{size[2]:5.1f})  "
              f"Z=[{b[0][2]:.1f},{b[1][2]:.1f}]")
else:
    # Single mesh — total bbox
    b = m.bounds
    print(f"  Vertices: {len(m.vertices)}")
    print(f"  bbox: X=[{b[0][0]:.1f},{b[1][0]:.1f}] Y=[{b[0][1]:.1f},{b[1][1]:.1f}] Z=[{b[0][2]:.1f},{b[1][2]:.1f}]")
    # Cluster analysis: find all "components" by connectivity
    components = m.split()
    print(f"  Connected components: {len(components)}")
    for i, c in enumerate(components):
        b = c.bounds
        center = [(b[0][j] + b[1][j]) / 2 for j in range(3)]
        size = [b[1][j] - b[0][j] for j in range(3)]
        print(f"    [{i:2d}] verts={len(c.vertices):5d}  "
              f"center=({center[0]:+7.1f},{center[1]:+7.1f},{center[2]:+7.1f})  "
              f"size=({size[0]:5.1f}x{size[1]:5.1f}x{size[2]:5.1f})")
