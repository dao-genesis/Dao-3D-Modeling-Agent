# -*- coding: utf-8 -*-
"""反者道之动 · 测 STL 中 rod ball joint 的精确局部坐标.

万物负阴而抱阳, 中气以为和.
firmware mainArm=50mm 是力矩臂数学简化, 实际 STL ball center
在 horn → +Y 56mm 处 (Arm), +Y 95mm 处 (Pitcher).
找到 STL ball mount 顶点中心, 让 rod 起点对齐 STL 真相.
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import trimesh
import numpy as np
from ORS6_Stewart.parts import stl_path, SR6


def find_ball_mount(name: str, search_radius: float = 6.0):
    """找 STL 中"远端 ball mount" 的局部坐标.
    
    策略: STL 上有一个圆形孔 (rod ball 安装点). 它通常是
    距 horn 最远的小圆柱孔. 用顶点最远点 + 邻域聚类.
    """
    m = trimesh.load(stl_path(name))
    v = m.vertices
    # horn axis 假设在 Z 方向 (STL Z-up), arm STL bbox center horn:
    # Arm: horn cluster center ~ (67.5, -0.9, 51.9)
    # L_Pitcher: horn ~ (-7.5, 9.5, 51.75) (mirrored)
    # R_Pitcher: horn ~ (+7.5, 9.5, 51.75)
    if name == "Arm":
        horn = np.array([67.5, 0, 51.5])
    elif name == "L_Pitcher":
        horn = np.array([-7.5, 9.5, 51.75])
    elif name == "R_Pitcher":
        horn = np.array([7.5, 9.5, 51.75])
    else:
        raise ValueError(name)
    
    dist = np.linalg.norm(v - horn, axis=1)
    # 取距 horn 最远 5% 的点
    n = max(20, len(v) // 20)
    far_idx = np.argpartition(-dist, n)[:n]
    far_pts = v[far_idx]
    
    # 在远端 cluster 中再聚类: 找最远点周围 search_radius 内的所有点
    farthest = v[np.argmax(dist)]
    near_far = np.linalg.norm(v - farthest, axis=1) < search_radius
    cluster = v[near_far]
    
    cx, cy, cz = cluster[:, 0].mean(), cluster[:, 1].mean(), cluster[:, 2].mean()
    return {
        "name": name,
        "horn_assumed": horn.tolist(),
        "ball_center": [round(cx, 2), round(cy, 2), round(cz, 2)],
        "delta_from_horn": [round(cx - horn[0], 2), round(cy - horn[1], 2), round(cz - horn[2], 2)],
        "ball_3d_dist": round(float(np.linalg.norm([cx - horn[0], cy - horn[1], cz - horn[2]])), 2),
        "cluster_size": int(len(cluster)),
    }


for n in ["Arm", "L_Pitcher", "R_Pitcher"]:
    info = find_ball_mount(n)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print()

# 同时测 rod attachment 上的 receiver mount STL 位置
print("=== Receiver STL · rod mount holes ===")
m = trimesh.load(stl_path("Receiver"))
v = m.vertices
b = m.bounds
print(f"  bbox: X=[{b[0][0]:.1f},{b[1][0]:.1f}] Y=[{b[0][1]:.1f},{b[1][1]:.1f}] Z=[{b[0][2]:.1f},{b[1][2]:.1f}]")
print(f"  vertices: {len(v)}")
# Receiver bottom mounts (4 main): expected at Z_local = -1.5 (per geometry.py ANCHOR_MAIN_*_LOCAL)
# Search for clusters at Z ≈ -1.5 (bottom)
bottom_mask = v[:, 2] < 5
bottom = v[bottom_mask]
print(f"  bottom (Z<5) verts: {len(bottom)}")
if len(bottom):
    # Find X extremes in bottom slice
    x_min_idx = bottom[:, 0].argmin()
    x_max_idx = bottom[:, 0].argmax()
    print(f"    extreme -X: {bottom[x_min_idx]}")
    print(f"    extreme +X: {bottom[x_max_idx]}")

# Top mounts (2 pitch): Z ≈ +23
top_mask = (v[:, 2] > 20) & (v[:, 2] < 30)
top = v[top_mask]
print(f"  top zone (20<Z<30) verts: {len(top)}")
if len(top):
    y_min_idx = top[:, 1].argmin()
    y_max_idx = top[:, 1].argmax()
    print(f"    extreme -Y: {top[y_min_idx]}")
    print(f"    extreme +Y: {top[y_max_idx]}")
