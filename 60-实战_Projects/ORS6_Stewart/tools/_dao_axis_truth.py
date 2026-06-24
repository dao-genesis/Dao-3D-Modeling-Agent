# -*- coding: utf-8 -*-
"""反者道之动 · 圆柱孔 axis 真值提取 (取之尽锱铢)

之前所有 trimesh 测量都用 bbox/cluster center, 这只是几何重心,
非旋转轴/装配孔 axis. 真本源装配真值是:
  - servo M3 螺栓孔的圆柱孔轴线 (servo shaft 真位置)
  - Arm spline horn 圆柱孔轴线 (servo 输出端真旋转轴)
  - Arm ball joint 螺栓孔轴线 (rod 连接真锚点)
  - L/R_Pitcher horn / ball 同理

法则: 用 trimesh 找出每个 STL 中的圆柱孔 (cylindrical bore),
返回其 axis 端点 + radius. 通过法向聚类 + 圆度检测.
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import numpy as np
import trimesh
from collections import defaultdict
from ORS6_Stewart.parts import stl_path, SR6


def find_cylindrical_holes(mesh: trimesh.Trimesh,
                           min_radius: float = 1.0,
                           max_radius: float = 8.0,
                           min_facets: int = 16,
                           tol_normal: float = 0.05) -> list[dict]:
    """识别 STL 中所有圆柱孔 (法向围绕一根 axis 360° 分布的面集合).

    返回每个 hole 的: axis 起点/终点, radius, 面数, axis 方向.
    """
    # facets: 用 mesh.facets (共面相邻三角形分组)
    # 但 facets 找不到圆柱孔 (圆柱面非共面). 改用 face_adjacency + normal cluster.

    fn = mesh.face_normals  # (n, 3)
    fc = mesh.triangles_center  # (n, 3)

    # 找出"环形面集合": 法向方向围绕一根直线轴 ω 旋转的面.
    # 启发式: 找一根 axis ω, 让 |fn · ω| ≈ 0 且 fc 投到 ω 上是单点的面集.
    # 我们用 trimesh 内置 facets() + 反向: 找非平面但邻接的面群 → 圆柱面候选.

    # 方法二: 在每个候选 axis 方向 (e.g. ±X, ±Y, ±Z, 6 个轴) 上,
    # 找法向垂直该 axis 的面, 然后聚类 axis 投影位置.
    holes = []
    candidate_axes = [
        np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]),
    ]
    for axis in candidate_axes:
        # 选出法向垂直 axis (|fn·axis|<tol) 的面
        proj = np.abs(fn @ axis)
        mask = proj < tol_normal
        if not mask.any():
            continue
        face_idx = np.where(mask)[0]
        # 计算每个面的"axis 投影中心" (fc 在 axis 平面内的位置)
        # 然后聚类 — 同一圆柱孔的面应共享一个圆心.
        axis_perp_basis = np.eye(3) - np.outer(axis, axis)  # 投影矩阵
        fc_perp = fc[face_idx] @ axis_perp_basis  # (k, 3)
        # 用简单网格聚类 (1mm grid) 把相邻投影点合并
        keys = np.round(fc_perp, 0).astype(int)
        clusters = defaultdict(list)
        for i, k in enumerate(keys):
            clusters[tuple(k)].append(face_idx[i])

        for k, members in clusters.items():
            if len(members) < min_facets:
                continue
            members = np.array(members)
            mc = fc[members]
            # 验证: 这些面的法向应当指向一个 axis (圆心)
            # 反向法 (向圆心) — 圆柱孔法向朝外/朝内
            # 算所有面到 axis 的距离 (作为 radius)
            # axis 经过 mean(fc · axis_perp_basis) 沿 axis 方向延伸
            center_perp = mc.mean(axis=0) @ axis_perp_basis
            # radius: 各面 fc 到 axis 直线的距离
            d = np.linalg.norm(mc @ axis_perp_basis - center_perp, axis=1)
            radius = float(d.mean())
            radius_std = float(d.std())
            if radius < min_radius or radius > max_radius:
                continue
            if radius_std > 0.5:  # 不够圆 (>0.5mm 偏差)
                continue
            # axis 方向上的范围
            axis_proj = mc @ axis
            z_min, z_max = float(axis_proj.min()), float(axis_proj.max())
            length = z_max - z_min
            if length < 1.0:  # 太短不像孔
                continue
            # axis 中点
            mid_perp = center_perp + (z_min + z_max) / 2 * axis
            holes.append({
                "axis_dir": axis.tolist(),
                "axis_passing_pt": [round(float(v), 2) for v in mid_perp],
                "radius_mm": round(radius, 2),
                "radius_std_mm": round(radius_std, 3),
                "length_mm": round(length, 2),
                "z_min_along_axis": round(z_min, 2),
                "z_max_along_axis": round(z_max, 2),
                "n_faces": int(len(members)),
            })
    return holes


def analyze(name: str) -> dict:
    """分析 STL 中所有圆柱孔."""
    mesh = trimesh.load(stl_path(name))
    holes = find_cylindrical_holes(mesh)
    holes.sort(key=lambda h: (-h["radius_mm"], -h["n_faces"]))
    return {
        "stl": name,
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "bbox_min": [round(float(v), 2) for v in mesh.bounds[0]],
        "bbox_max": [round(float(v), 2) for v in mesh.bounds[1]],
        "n_holes": len(holes),
        "holes": holes[:30],  # 只取前 30
    }


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else [
        "L_Frame", "R_Frame", "Arm", "L_Pitcher", "R_Pitcher", "Receiver",
    ]
    out = {}
    for n in targets:
        print(f"\n=== {n} ===")
        r = analyze(n)
        out[n] = r
        print(f"  bbox X={r['bbox_min'][0]:+.1f}..{r['bbox_max'][0]:+.1f}  "
              f"Y={r['bbox_min'][1]:+.1f}..{r['bbox_max'][1]:+.1f}  "
              f"Z={r['bbox_min'][2]:+.1f}..{r['bbox_max'][2]:+.1f}  "
              f"n_holes={r['n_holes']}")
        for h in r["holes"][:10]:
            ad = h["axis_dir"]
            ap = h["axis_passing_pt"]
            axdir = ("X" if ad[0] else "Y" if ad[1] else "Z")
            print(f"    axis||{axdir}  passing_pt=({ap[0]:+6.1f},{ap[1]:+6.1f},{ap[2]:+6.1f})  "
                  f"R={h['radius_mm']:.1f}mm  L={h['length_mm']:.1f}mm  "
                  f"std={h['radius_std_mm']:.3f}  n_faces={h['n_faces']}")

    out_path = os.path.join(os.path.dirname(__file__), "_dao_axis_truth.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n✓ saved {out_path}")
