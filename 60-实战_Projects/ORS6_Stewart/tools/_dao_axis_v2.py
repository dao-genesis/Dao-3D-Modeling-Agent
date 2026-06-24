# -*- coding: utf-8 -*-
"""反者道之动 v2 · 圆柱孔 axis 真值提取 (取之尽锱铢, 万法之三~五)

本源算法:
  圆柱孔表面的三角面 → 法向皆垂直于孔 axis → 单位球上分布于"赤道平面"
  → 该平面之法向 = 孔 axis (可由法向集合的 SVD 第三主分量得).

步骤:
  1. mesh.face_adjacency_angles + connected components 得邻接面群
  2. 对每群: 求面积加权法向集合, 用 SVD 提取主轴
  3. 若最小奇异值 << 中等, 则法向"展平"于一个平面 → 该平面法向 = 圆柱 axis
  4. 求面群中心到此 axis 的垂直距离 = radius (一致即圆)
  5. 验证 radius std < 容差, 才是真圆柱孔
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import numpy as np
import trimesh
from ORS6_Stewart.parts import stl_path


def fit_cylinder_to_face_group(mesh: trimesh.Trimesh, face_indices: np.ndarray):
    """对一组面拟合圆柱: 返回 (axis_dir, axis_pt, radius, radius_std, length, ok).

    若拟合失败 (非圆柱) 返回 None.
    """
    if len(face_indices) < 8:
        return None
    fn = mesh.face_normals[face_indices]  # (k, 3)
    fc = mesh.triangles_center[face_indices]  # (k, 3)
    areas = mesh.area_faces[face_indices]  # (k,)

    # SVD 法向集合 → 第三主分量 (最小奇异值方向) = 圆柱 axis
    # 圆柱面法向皆垂直于 axis, 故 fn 在 axis 方向投影皆 ≈ 0
    # → axis 是 fn 协方差矩阵最小特征值方向
    fn_centered = fn - (fn * areas[:, None]).sum(axis=0) / areas.sum()
    cov = (fn_centered.T * areas) @ fn_centered / areas.sum()
    eigvals, eigvecs = np.linalg.eigh(cov)
    # 升序: eigvals[0]=最小 (axis 方向), [2]=最大 (法向主延展方向)
    axis_dir = eigvecs[:, 0]
    axis_dir = axis_dir / np.linalg.norm(axis_dir)

    # 圆柱性检验: 最小特征值远小于其他 → 法向确实在一平面内
    # 阈值: λ_min / λ_max < 0.05
    if eigvals[2] < 1e-6:
        return None
    cyl_score = eigvals[0] / eigvals[2]  # 越小越像圆柱
    if cyl_score > 0.05:
        return None

    # 进一步: |fn · axis| 应 < 0.15 (法向几乎完全垂直于 axis)
    perp = np.abs(fn @ axis_dir)
    if perp.max() > 0.25:
        return None

    # 求 axis 经过点: 投到 axis 垂直平面, 取面中心平均
    proj_perp_basis = np.eye(3) - np.outer(axis_dir, axis_dir)
    fc_perp = fc @ proj_perp_basis  # (k, 3)
    axis_pt = (fc_perp * areas[:, None]).sum(axis=0) / areas.sum()

    # radius: fc 到 axis 直线的距离 = ||fc_perp - axis_pt||
    d = np.linalg.norm(fc_perp - axis_pt, axis=1)
    radius = float(d.mean())
    radius_std = float(d.std())
    if radius < 0.5:
        return None

    # axis 方向上的范围
    fc_axis_proj = fc @ axis_dir
    z_min, z_max = float(fc_axis_proj.min()), float(fc_axis_proj.max())
    length = z_max - z_min

    # 凡是符合的: radius_std/radius < 0.2 (圆度 80%)
    if radius_std / max(radius, 1e-6) > 0.2:
        return None

    # axis 中点: axis_pt 在 axis 投影方向上滑到 (z_min+z_max)/2
    mid_axis_proj = (z_min + z_max) / 2
    # axis_pt 已在 axis 垂直平面内, 加上 axis_dir * mid 即得 axis 中点
    # 注意 axis_pt 可能不在 z=mid 处, 需要修正
    # 实际上 axis_pt 是垂直分量的均值; axis 中点 = axis_pt + axis_dir * mid_proj
    # (前提: axis_pt 已在 axis 垂直平面内)
    midpoint = axis_pt + axis_dir * mid_axis_proj

    return {
        "axis_dir": [round(float(v), 4) for v in axis_dir],
        "axis_midpoint": [round(float(v), 2) for v in midpoint],
        "radius_mm": round(radius, 2),
        "radius_std_mm": round(radius_std, 3),
        "length_mm": round(length, 2),
        "n_faces": int(len(face_indices)),
        "cyl_score": round(float(cyl_score), 4),
        "max_perp_dot": round(float(perp.max()), 3),
    }


def find_holes(mesh: trimesh.Trimesh,
               r_min: float = 1.0,
               r_max: float = 8.0,
               face_angle_thresh: float = 0.6) -> list[dict]:
    """连通邻接面群 + 拟合圆柱."""
    # 邻接面: 共边夹角 < 阈值 (rad). 默认 0.6 ≈ 34°, 较宽以包圆柱面.
    fa = mesh.face_adjacency  # (m, 2)
    angles = mesh.face_adjacency_angles  # (m,)
    keep = angles < face_angle_thresh

    # connected components on graph
    n = len(mesh.faces)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for (a, b), k in zip(fa, keep):
        if k:
            union(int(a), int(b))

    groups = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)

    holes = []
    for g in groups.values():
        if len(g) < 12:
            continue
        result = fit_cylinder_to_face_group(mesh, np.array(g))
        if result and r_min <= result["radius_mm"] <= r_max:
            holes.append(result)

    holes.sort(key=lambda h: (-h["n_faces"], -h["radius_mm"]))
    return holes


def analyze(name: str) -> dict:
    mesh = trimesh.load(stl_path(name))
    holes = find_holes(mesh)
    return {
        "stl": name,
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "bbox_min": [round(float(v), 2) for v in mesh.bounds[0]],
        "bbox_max": [round(float(v), 2) for v in mesh.bounds[1]],
        "n_holes": len(holes),
        "holes": holes,
    }


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else [
        "L_Frame", "R_Frame", "Arm", "L_Pitcher", "R_Pitcher", "Receiver",
        "Base",
    ]
    out = {}
    for n in targets:
        print(f"\n=== {n} ===")
        r = analyze(n)
        out[n] = r
        b0, b1 = r["bbox_min"], r["bbox_max"]
        print(f"  bbox X={b0[0]:+.1f}..{b1[0]:+.1f}  "
              f"Y={b0[1]:+.1f}..{b1[1]:+.1f}  "
              f"Z={b0[2]:+.1f}..{b1[2]:+.1f}  "
              f"n_holes={r['n_holes']}")
        for h in r["holes"][:20]:
            ad = h["axis_dir"]
            ap = h["axis_midpoint"]
            # axis dir 描述
            ax_dom = max(range(3), key=lambda i: abs(ad[i]))
            ax_label = "X" if ax_dom == 0 else "Y" if ax_dom == 1 else "Z"
            sgn = "+" if ad[ax_dom] >= 0 else "-"
            print(f"    axis≈{sgn}{ax_label} ({ad[0]:+.2f},{ad[1]:+.2f},{ad[2]:+.2f})  "
                  f"mid=({ap[0]:+6.2f},{ap[1]:+6.2f},{ap[2]:+6.2f})  "
                  f"R={h['radius_mm']:.2f}mm  L={h['length_mm']:.1f}mm  "
                  f"n={h['n_faces']:>3d}  std/r={h['radius_std_mm']/max(h['radius_mm'],0.01):.3f}")

    out_path = os.path.join(os.path.dirname(__file__), "_dao_axis_v2.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n✓ saved {out_path}")
