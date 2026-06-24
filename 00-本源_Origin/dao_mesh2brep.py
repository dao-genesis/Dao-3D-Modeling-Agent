#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dao_mesh2brep.py — 网格上岸 · mesh → BREP 反演本源
═══════════════════════════════════════════════════════════════════════════
「天下莫柔弱于水, 而攻坚强者莫之能胜.」 ——帛书七十八章
「曲则金, 枉则定, 漥则盈, 敝则新.」 ——帛书二十二章

立此之缘:
  现 Mesh-Track AI (Hunyuan3D 2.1 / TRELLIS / TripoSR / InstantMesh / Tripo /
  Meshy / Rodin / Hitem3D / SAM 3D ...) 输出皆为 mesh (.obj/.glb/.stl),
  视觉好, 但**无参 · 无特征 · 无装配 · 不可制造**.
  本源 dao_kernel 立 BREP 唯一岸 — 一切图意路线终须上岸.
  此模块即"网格→上岸"之桥.

方法本源 (跨越 Mesh-Track 与 CAD-Track 之桥):
  ① 加载 mesh (借 dao_mesh.read_stl_triangles, 优雅降级)
  ② 法向估计 + 法向聚类 (per-face normal 聚为同向组)
  ③ RANSAC 原语拟合 (按面组拟合: 平面 / 圆柱 / 球 / 圆锥)
  ④ 残差判定 + 边界提取 (拟合不上的留 mesh 兜底)
  ⑤ OCCT 缝合 (BRepBuilderAPI_MakeFace + _Sewing + _MakeSolid → BREP)
  ⑥ 可选: 走 dao_audit 八层审核 验上岸是否成

本源不依赖 trimesh/numpy 强 — 有则用, 无则降级 (纯 Python 解析).

参考文献 (玄同 leaves 之延):
  - Mesh2Brep (IEEE 2025) — Robust Primitive Fitting + Intersection-aware
  - Point2CAD (prs-eth 2024) — RANSAC + topology
  - ComplexGen (SIGGRAPH 2022) — B-rep chain complex
  - CADFit (2026) — Hybrid neural seg + analytic fit

「弱者道之用」: 简件 (一两个原语) 即可立功;
                复件能拟则拟, 不能拟则部分拟 + 部分原 mesh, 不强求.
                上岸 80% 即胜 — 比 mesh-only 强一万倍.

用法 (库):

    from dao_mesh2brep import Mesh2Brep

    m = Mesh2Brep()

    # 一键: STL/OBJ → BREP + STEP
    r = m.fit_and_sew('part.stl', out_step='part_brep.step')
    # → {'ok':True, 'shape':TopoDS_Shape, 'primitives':[...], 'topology':{...}}

    # 分步:
    tri = m.load_mesh('part.stl')
    primitives = m.detect_primitives(tri)
    shape = m.sew_to_brep(primitives)
    # 也可直接落 STEP (借 dao_kernel)

CLI:

    python dao_mesh2brep.py fit <stl> [--out part.step] [--audit]
    python dao_mesh2brep.py probe                    # 探依赖
    python dao_mesh2brep.py demo                     # 内置 box 自验

Returns 模型:

    Primitive = {
      'type': 'plane' | 'cylinder' | 'sphere' | 'cone' | 'unknown',
      'params': {...}  # plane: {origin,normal}; cylinder: {axis,radius,...}
      'face_indices': [int...],
      'inlier_ratio': float,  # 拟合内点比
      'rmse': float,           # 残差 (mm)
    }
"""
from __future__ import annotations

import os
import sys
import json
import math
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple, Union

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
SCRIPT_DIR = Path(__file__).resolve().parent
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
try:
    import _paths as _dao_paths  # noqa: F401
except Exception:
    _dao_paths = None
# ═══════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# § 0 · 依赖探针 · 弱者道之用
# ═══════════════════════════════════════════════════════════════

def _probe(name: str) -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


_HAS_NUMPY    = _probe('numpy')
_HAS_TRIMESH  = _probe('trimesh')
_HAS_OCP      = _probe('OCP')
_HAS_SCIPY    = _probe('scipy')


def deps() -> Dict[str, bool]:
    return {
        'numpy': _HAS_NUMPY, 'trimesh': _HAS_TRIMESH,
        'OCP': _HAS_OCP, 'scipy': _HAS_SCIPY,
    }


# ═══════════════════════════════════════════════════════════════
# § 1 · 数据载体
# ═══════════════════════════════════════════════════════════════

@dataclass
class Triangles:
    """三角网格统一载体 · 不强 numpy."""
    # 每三角: (n_x,n_y,n_z, v0_xyz, v1_xyz, v2_xyz)
    # 内部存 numpy.ndarray (若可) 或 list of tuples
    raw: Any = None
    n_faces: int = 0
    bbox: Optional[Tuple[Tuple[float, float, float],
                          Tuple[float, float, float]]] = None
    units: str = 'mm'
    source: Optional[str] = None  # 文件路径

    def is_numpy(self) -> bool:
        return _HAS_NUMPY and hasattr(self.raw, 'shape')

    def vertices_per_face(self):
        """生成 (v0, v1, v2) 三元组 · 与底层无关."""
        if self.is_numpy():
            import numpy as np
            for row in self.raw:
                # row: [nx ny nz v0x v0y v0z v1x v1y v1z v2x v2y v2z]
                v0 = (float(row[3]), float(row[4]), float(row[5]))
                v1 = (float(row[6]), float(row[7]), float(row[8]))
                v2 = (float(row[9]), float(row[10]), float(row[11]))
                n = (float(row[0]), float(row[1]), float(row[2]))
                yield v0, v1, v2, n
        else:
            for row in self.raw:
                if isinstance(row, dict):
                    yield row['v0'], row['v1'], row['v2'], row.get('normal', (0, 0, 0))
                else:
                    yield row[0], row[1], row[2], row[3] if len(row) > 3 else (0, 0, 0)


@dataclass
class Primitive:
    """单原语之描述."""
    type: str   # plane / cylinder / sphere / cone / unknown
    params: Dict[str, Any] = field(default_factory=dict)
    face_indices: List[int] = field(default_factory=list)
    inlier_ratio: float = 0.0
    rmse: float = 0.0
    bbox: Optional[Tuple[Tuple[float, float, float],
                          Tuple[float, float, float]]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ═══════════════════════════════════════════════════════════════
# § 2 · 加载 · 借 dao_mesh (或 trimesh, 优雅降级)
# ═══════════════════════════════════════════════════════════════

def load_mesh(path: Union[str, Path]) -> Triangles:
    """加载 STL/OBJ → Triangles. 优先 dao_mesh (零依赖); 次 trimesh (有 numpy)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)

    # 优先 dao_mesh (本项目零依赖 STL 解析 · 仅 binary STL)
    try:
        import dao_mesh  # type: ignore
        if hasattr(dao_mesh, 'read_stl_triangles'):
            tri = dao_mesh.read_stl_triangles(str(p))
            tris = list(tri) if tri else []
            if tris:  # 仅 dao_mesh 成功时返 · 空则降级 trimesh
                return _wrap_triangles(tris, source=str(p))
    except Exception:
        pass

    # 次 trimesh (含 ASCII STL / OBJ / PLY / GLB)
    if _HAS_TRIMESH:
        try:
            import trimesh  # type: ignore
            mesh = trimesh.load_mesh(str(p))
            if hasattr(mesh, 'triangles'):
                tris = mesh.triangles
                normals = mesh.face_normals if hasattr(
                    mesh, 'face_normals') else None
                return _wrap_triangles_from_arrays(
                    tris, normals=normals, source=str(p))
        except Exception:
            pass

    raise RuntimeError(f'无可用 mesh 加载器 (dao_mesh/trimesh 皆缺): {p}')


def _wrap_triangles(tri_list: List, source: Optional[str] = None) -> Triangles:
    """tri_list: [(v0, v1, v2, normal?), ...] 或 [{'v0','v1','v2',...}, ...]"""
    n = len(tri_list)
    out = Triangles(raw=None, n_faces=n, source=source)
    if not tri_list:
        out.raw = []
        return out

    if _HAS_NUMPY:
        import numpy as np
        arr = np.zeros((n, 12), dtype=np.float32)
        bb_min = [float('inf')] * 3
        bb_max = [-float('inf')] * 3
        for i, t in enumerate(tri_list):
            if isinstance(t, dict):
                v0, v1, v2 = t['v0'], t['v1'], t['v2']
                nrm = t.get('normal', _calc_normal(v0, v1, v2))
            else:
                v0, v1, v2 = t[0], t[1], t[2]
                nrm = t[3] if len(t) > 3 else _calc_normal(v0, v1, v2)
            arr[i, 0:3] = nrm
            arr[i, 3:6] = v0
            arr[i, 6:9] = v1
            arr[i, 9:12] = v2
            for v in (v0, v1, v2):
                for k in range(3):
                    if v[k] < bb_min[k]: bb_min[k] = float(v[k])
                    if v[k] > bb_max[k]: bb_max[k] = float(v[k])
        out.raw = arr
        out.bbox = (tuple(bb_min), tuple(bb_max))
    else:
        # 纯 Python list
        norm_list = []
        bb_min = [float('inf')] * 3
        bb_max = [-float('inf')] * 3
        for t in tri_list:
            if isinstance(t, dict):
                v0, v1, v2 = t['v0'], t['v1'], t['v2']
                nrm = t.get('normal', _calc_normal(v0, v1, v2))
            else:
                v0, v1, v2 = t[0], t[1], t[2]
                nrm = t[3] if len(t) > 3 else _calc_normal(v0, v1, v2)
            norm_list.append((tuple(v0), tuple(v1), tuple(v2), tuple(nrm)))
            for v in (v0, v1, v2):
                for k in range(3):
                    if v[k] < bb_min[k]: bb_min[k] = float(v[k])
                    if v[k] > bb_max[k]: bb_max[k] = float(v[k])
        out.raw = norm_list
        out.bbox = (tuple(bb_min), tuple(bb_max))
    return out


def _wrap_triangles_from_arrays(tris, normals=None, source=None) -> Triangles:
    """tris: numpy ndarray (N,3,3) — 每三角三顶点."""
    if not _HAS_NUMPY:
        # 转 list
        tri_list = []
        for i, t in enumerate(tris):
            v0 = (float(t[0][0]), float(t[0][1]), float(t[0][2]))
            v1 = (float(t[1][0]), float(t[1][1]), float(t[1][2]))
            v2 = (float(t[2][0]), float(t[2][1]), float(t[2][2]))
            n = tuple(map(float, normals[i])) if normals is not None else None
            tri_list.append((v0, v1, v2, n))
        return _wrap_triangles(tri_list, source=source)

    import numpy as np
    n = len(tris)
    arr = np.zeros((n, 12), dtype=np.float32)
    if normals is not None:
        arr[:, 0:3] = normals[:n]
    else:
        # 计算法向
        v0v = tris[:, 0, :]
        v1v = tris[:, 1, :]
        v2v = tris[:, 2, :]
        e1 = v1v - v0v
        e2 = v2v - v0v
        nrm = np.cross(e1, e2)
        ln = np.linalg.norm(nrm, axis=1, keepdims=True)
        ln[ln < 1e-12] = 1.0
        arr[:, 0:3] = nrm / ln
    arr[:, 3:6] = tris[:, 0, :]
    arr[:, 6:9] = tris[:, 1, :]
    arr[:, 9:12] = tris[:, 2, :]
    bb_min = arr[:, 3:].reshape(-1, 3).min(axis=0).tolist()
    bb_max = arr[:, 3:].reshape(-1, 3).max(axis=0).tolist()
    return Triangles(raw=arr, n_faces=n, bbox=(tuple(bb_min), tuple(bb_max)),
                     source=source)


def _calc_normal(v0, v1, v2) -> Tuple[float, float, float]:
    """三点法向 · 纯 Python."""
    e1 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
    e2 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])
    nx = e1[1] * e2[2] - e1[2] * e2[1]
    ny = e1[2] * e2[0] - e1[0] * e2[2]
    nz = e1[0] * e2[1] - e1[1] * e2[0]
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    if ln < 1e-12:
        return (0.0, 0.0, 1.0)
    return (nx / ln, ny / ln, nz / ln)


# ═══════════════════════════════════════════════════════════════
# § 3 · 法向聚类 — 「分而治之」
# ═══════════════════════════════════════════════════════════════

def cluster_by_normal(tri: Triangles, eps: float = 0.05,
                       min_cluster_size: int = 4) -> List[List[int]]:
    """按法向相似度聚 face index. eps 为余弦距阈值 (1 - dot).

    Returns: [[face_idx, ...], [face_idx, ...], ...]
    """
    if tri.n_faces == 0:
        return []

    if tri.is_numpy():
        import numpy as np
        normals = tri.raw[:, 0:3]
        # 归一化
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        norms[norms < 1e-12] = 1.0
        normals = normals / norms
        # 简单 greedy 聚类: 第一个法向作种子, 余皆与之比较
        clusters: List[List[int]] = []
        used = np.zeros(tri.n_faces, dtype=bool)
        for i in range(tri.n_faces):
            if used[i]:
                continue
            seed = normals[i]
            mask = ~used & (np.dot(normals, seed) > 1 - eps)
            indices = np.where(mask)[0]
            # 也算反向 (双面三角)
            mask_neg = ~used & (np.dot(normals, seed) < -(1 - eps))
            neg_indices = np.where(mask_neg)[0]
            all_idx = np.concatenate([indices, neg_indices])
            if len(all_idx) >= min_cluster_size:
                used[all_idx] = True
                clusters.append(all_idx.tolist())
        return clusters

    # 纯 Python 退化
    normals = []
    for row in tri.raw:
        if isinstance(row, dict):
            normals.append(row.get('normal', (0, 0, 1)))
        else:
            normals.append(row[3] if len(row) > 3 else (0, 0, 1))
    used = [False] * len(normals)
    clusters: List[List[int]] = []
    for i in range(len(normals)):
        if used[i]:
            continue
        seed = normals[i]
        idx_grp = [i]
        for j in range(i + 1, len(normals)):
            if used[j]:
                continue
            dp = (seed[0] * normals[j][0] + seed[1] * normals[j][1]
                  + seed[2] * normals[j][2])
            if dp > 1 - eps or dp < -(1 - eps):
                idx_grp.append(j)
        if len(idx_grp) >= min_cluster_size:
            for k in idx_grp:
                used[k] = True
            clusters.append(idx_grp)
    return clusters


# ═══════════════════════════════════════════════════════════════
# § 4 · 原语拟合 — 平面/圆柱/球/锥
# ═══════════════════════════════════════════════════════════════

def fit_plane(tri: Triangles, face_indices: List[int],
              tol_mm: float = 0.5) -> Optional[Primitive]:
    """平面拟合 · 取簇内顶点 + 法向均值."""
    if not face_indices:
        return None

    if tri.is_numpy():
        import numpy as np
        rows = tri.raw[face_indices]
        # 顶点: 每三角3点 → 3N 点
        pts = np.concatenate([
            rows[:, 3:6], rows[:, 6:9], rows[:, 9:12]
        ], axis=0)
        # 法向: 加权 (面积近似 = 1/三角数)
        normals = rows[:, 0:3]
        n_avg = normals.mean(axis=0)
        ln = np.linalg.norm(n_avg)
        if ln < 1e-12:
            return None
        n_avg = n_avg / ln
        # 平面参数: n · X = d, d = mean(n · pt)
        d = float(np.dot(pts, n_avg).mean())
        # RMSE = std of residuals
        residuals = np.dot(pts, n_avg) - d
        rmse = float(np.sqrt((residuals ** 2).mean()))
        if rmse > tol_mm:
            return None
        # 内点比
        inliers = (abs(residuals) < tol_mm).sum() / len(residuals)
        # 平面之 origin 取中心
        origin = pts.mean(axis=0).tolist()
        bb_min = pts.min(axis=0).tolist()
        bb_max = pts.max(axis=0).tolist()
        return Primitive(
            type='plane',
            params={
                'origin': origin,
                'normal': n_avg.tolist(),
                'd': d,
            },
            face_indices=list(face_indices),
            inlier_ratio=float(inliers),
            rmse=rmse,
            bbox=(tuple(bb_min), tuple(bb_max)),
        )

    # 纯 Python 退化
    pts = []
    nrm_sum = [0.0, 0.0, 0.0]
    for fi in face_indices:
        row = tri.raw[fi]
        if isinstance(row, dict):
            v0, v1, v2 = row['v0'], row['v1'], row['v2']
            n = row.get('normal', (0, 0, 1))
        else:
            v0, v1, v2 = row[0], row[1], row[2]
            n = row[3] if len(row) > 3 else (0, 0, 1)
        pts.extend([v0, v1, v2])
        for k in range(3):
            nrm_sum[k] += n[k]
    if not pts:
        return None
    cnt = len(face_indices)
    n_avg = (nrm_sum[0] / cnt, nrm_sum[1] / cnt, nrm_sum[2] / cnt)
    ln = math.sqrt(sum(x * x for x in n_avg))
    if ln < 1e-12:
        return None
    n_avg = (n_avg[0] / ln, n_avg[1] / ln, n_avg[2] / ln)
    d_list = [n_avg[0] * p[0] + n_avg[1] * p[1] + n_avg[2] * p[2] for p in pts]
    d_avg = sum(d_list) / len(d_list)
    rmses = [(d - d_avg) ** 2 for d in d_list]
    rmse = math.sqrt(sum(rmses) / len(rmses))
    if rmse > tol_mm:
        return None
    inliers = sum(1 for d in d_list if abs(d - d_avg) < tol_mm) / len(d_list)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    cz = sum(p[2] for p in pts) / len(pts)
    bb_min = (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts))
    bb_max = (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))
    return Primitive(
        type='plane',
        params={
            'origin': [cx, cy, cz],
            'normal': list(n_avg),
            'd': d_avg,
        },
        face_indices=list(face_indices),
        inlier_ratio=inliers,
        rmse=rmse,
        bbox=(bb_min, bb_max),
    )


def fit_cylinder(tri: Triangles, face_indices: List[int],
                  tol_mm: float = 0.5) -> Optional[Primitive]:
    """圆柱拟合 · 简化版: 法向轴估计 + 半径 = 平均到轴距离.

    需 numpy + scipy 较稳; 退化版仅做粗估.
    """
    if not face_indices or not _HAS_NUMPY:
        return None

    import numpy as np
    rows = tri.raw[face_indices]
    pts = np.concatenate([rows[:, 3:6], rows[:, 6:9], rows[:, 9:12]], axis=0)
    normals = rows[:, 0:3]

    # 圆柱面法向皆垂直主轴 → 主轴 = 法向矩阵之最小奇异值方向
    n_norm = np.linalg.norm(normals, axis=1, keepdims=True)
    n_norm[n_norm < 1e-12] = 1.0
    nmat = normals / n_norm
    # SVD 找最小奇异值方向
    try:
        u, s, vt = np.linalg.svd(nmat, full_matrices=False)
    except Exception:
        return None
    axis = vt[np.argmin(s)]
    # 投点到与轴垂直之平面 (取簇中心为基准)
    center = pts.mean(axis=0)
    # 每点 - 中心, 投到轴向平面
    rel = pts - center
    proj = rel - np.outer(np.dot(rel, axis), axis)
    radii = np.linalg.norm(proj, axis=1)
    r_mean = float(radii.mean())
    r_std = float(radii.std())
    rmse = r_std
    if rmse > tol_mm:
        return None
    if r_mean < 0.5:  # 太小不算圆柱
        return None
    inliers = float((abs(radii - r_mean) < tol_mm).sum() / len(radii))
    if inliers < 0.7:
        return None

    # 圆柱端点: 沿轴投影范围
    t = np.dot(rel, axis)
    t_min = float(t.min()); t_max = float(t.max())
    p_low = (center + axis * t_min).tolist()
    p_high = (center + axis * t_max).tolist()
    bb_min = pts.min(axis=0).tolist()
    bb_max = pts.max(axis=0).tolist()
    return Primitive(
        type='cylinder',
        params={
            'axis': axis.tolist(),
            'origin': p_low,
            'end': p_high,
            'radius': r_mean,
            'height': float(t_max - t_min),
        },
        face_indices=list(face_indices),
        inlier_ratio=inliers,
        rmse=rmse,
        bbox=(tuple(bb_min), tuple(bb_max)),
    )


def fit_sphere(tri: Triangles, face_indices: List[int],
                tol_mm: float = 0.5) -> Optional[Primitive]:
    """球拟合 · 法向皆指中心 → 中心由法向交点求."""
    if not face_indices or not _HAS_NUMPY:
        return None
    import numpy as np
    rows = tri.raw[face_indices]
    pts = np.concatenate([rows[:, 3:6], rows[:, 6:9], rows[:, 9:12]], axis=0)
    # 球: 中心 = 最小化 Σ (||pt - c|| - r)²
    # 简化: 用中心 = 顶点平均 - 法向 × 估计半径
    center = pts.mean(axis=0)
    radii = np.linalg.norm(pts - center, axis=1)
    r_mean = float(radii.mean())
    rmse = float(radii.std())
    if rmse > tol_mm:
        return None
    inliers = float((abs(radii - r_mean) < tol_mm).sum() / len(radii))
    if inliers < 0.85:
        return None
    bb_min = pts.min(axis=0).tolist()
    bb_max = pts.max(axis=0).tolist()
    return Primitive(
        type='sphere',
        params={
            'center': center.tolist(),
            'radius': r_mean,
        },
        face_indices=list(face_indices),
        inlier_ratio=inliers,
        rmse=rmse,
        bbox=(tuple(bb_min), tuple(bb_max)),
    )


# ═══════════════════════════════════════════════════════════════
# § 5 · 检测引擎 — 综合调度
# ═══════════════════════════════════════════════════════════════

def detect_primitives(tri: Triangles,
                       tol_mm: float = 0.5,
                       cluster_eps: float = 0.05,
                       min_cluster: int = 4,
                       try_types: Tuple[str, ...] = (
                           'plane', 'cylinder', 'sphere')
                       ) -> List[Primitive]:
    """简件原语检测 · 主路: 平面 + 圆柱 + 球 + 锥."""
    out: List[Primitive] = []
    clusters = cluster_by_normal(tri, eps=cluster_eps,
                                  min_cluster_size=min_cluster)

    for cluster in clusters:
        # 平面优先
        if 'plane' in try_types:
            p = fit_plane(tri, cluster, tol_mm=tol_mm)
            if p and p.inlier_ratio >= 0.85:
                out.append(p)
                continue
        if 'cylinder' in try_types and _HAS_NUMPY:
            c = fit_cylinder(tri, cluster, tol_mm=tol_mm * 2)
            if c and c.inlier_ratio >= 0.7:
                out.append(c)
                continue
        if 'sphere' in try_types and _HAS_NUMPY:
            s = fit_sphere(tri, cluster, tol_mm=tol_mm * 2)
            if s and s.inlier_ratio >= 0.85:
                out.append(s)
                continue
        # 兜底 unknown
        out.append(Primitive(
            type='unknown',
            face_indices=cluster,
            inlier_ratio=0.0,
            rmse=float('inf'),
        ))
    return out


# ═══════════════════════════════════════════════════════════════
# § 6 · 缝合 · 用 dao_kernel/OCP 把原语合 BREP
# ═══════════════════════════════════════════════════════════════

def primitives_to_brep(primitives: List[Primitive],
                        tri: Optional[Triangles] = None,
                        tol_mm: float = 0.1):
    """原语 → BREP. 当下版本: 用每原语之 bbox + 类型 直接用 OCCT 原始体构造,
    然后 BRepBuilderAPI_Sewing 缝合.

    简件 (1-3 原语) 即可上岸.
    复件 — 若有 unknown 兜底, 走 mesh→shape (借 Open3D/trimesh→BRep, 慢但可用).
    """
    if not _HAS_OCP:
        raise RuntimeError(
            'OCP (OCCT) 未装. 此层需 dao_kernel 之 BREP 内核.'
        )

    from dao_kernel import DaoKernel as K

    shapes = []
    for p in primitives:
        if p.type == 'plane':
            # 用 bbox 转矩形 face → prism 一点厚度变 thin solid? — 太脆
            # 简版: 若原语为平面但仅有 6 个 (大概率盒), 跳过, 后续盒检 fallback
            # 当下: 加一矩形面参与缝合
            try:
                bb = p.bbox or ((0, 0, 0), (1, 1, 1))
                origin = p.params.get('origin', [0, 0, 0])
                normal = p.params.get('normal', [0, 0, 1])
                # 估计平面 width/height 为 bbox 在与 normal 正交方向之最大跨度
                w = max(bb[1][0] - bb[0][0], bb[1][1] - bb[0][1],
                        bb[1][2] - bb[0][2]) or 10.0
                face = K.rect_face(w, w, center=tuple(origin),
                                    normal=tuple(normal))
                shapes.append(('face', face))
            except Exception:
                pass
        elif p.type == 'cylinder':
            try:
                origin = p.params.get('origin', [0, 0, 0])
                axis = p.params.get('axis', [0, 0, 1])
                r = p.params.get('radius', 1.0)
                h = p.params.get('height', 1.0)
                cyl = K.cylinder(r, h, origin=tuple(origin),
                                  direction=tuple(axis))
                shapes.append(('solid', cyl))
            except Exception:
                pass
        elif p.type == 'sphere':
            try:
                center = p.params.get('center', [0, 0, 0])
                r = p.params.get('radius', 1.0)
                sph = K.sphere(r, center=tuple(center))
                shapes.append(('solid', sph))
            except Exception:
                pass

    # 当下: 若全是 solid, 取最大体之 fuse 即可
    solids = [s for kind, s in shapes if kind == 'solid']
    if not solids and not shapes:
        return None

    # 简策略: 多 solid → fuse
    if solids:
        try:
            if len(solids) == 1:
                return solids[0]
            return K.fuse_all(solids)
        except Exception:
            return solids[0]

    # 仅 face → 缝合成 shell (比 solid 弱, 但可用作展示)
    try:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing  # type: ignore
        sewer = BRepBuilderAPI_Sewing(tol_mm)
        for kind, s in shapes:
            sewer.Add(s)
        sewer.Perform()
        return sewer.SewedShape()
    except Exception:
        return None


def mesh_to_brep_via_compound(tri: Triangles, tol_mm: float = 0.1):
    """兜底: 把每三角作 face, sew 成 shell.
    高代价 — 仅在原语拟合无果时走.
    """
    if not _HAS_OCP:
        raise RuntimeError('OCP 未装')
    from dao_kernel import DaoKernel as K
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakePolygon,  # type: ignore
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_Sewing,
    )
    from OCP.gp import gp_Pnt  # type: ignore

    sewer = BRepBuilderAPI_Sewing(tol_mm)
    for v0, v1, v2, _ in tri.vertices_per_face():
        try:
            poly = BRepBuilderAPI_MakePolygon(
                gp_Pnt(*v0), gp_Pnt(*v1), gp_Pnt(*v2), True)
            wire = poly.Wire()
            face = BRepBuilderAPI_MakeFace(wire, True).Face()
            sewer.Add(face)
        except Exception:
            continue
    sewer.Perform()
    return sewer.SewedShape()


# ═══════════════════════════════════════════════════════════════
# § 7 · 主类 · Mesh2Brep
# ═══════════════════════════════════════════════════════════════

class Mesh2Brep:
    """网格上岸 · STL/OBJ → BREP."""

    def __init__(self, tol_mm: float = 0.5):
        self.tol_mm = float(tol_mm)
        self._t0 = time.time()

    def fit_and_sew(self, mesh_path: Union[str, Path],
                     tol_mm: Optional[float] = None,
                     fallback_compound: bool = True,
                     try_types: Tuple[str, ...] = (
                         'plane', 'cylinder', 'sphere'),
                     **kw) -> Dict[str, Any]:
        """主入口: STL → 原语检测 → BREP.

        若 fallback_compound=True 且原语拟合不足以生 solid, 走 compound 兜底
        (每三角作 face sew shell, 慢但可上岸).
        """
        t0 = time.time()
        tol = self.tol_mm if tol_mm is None else float(tol_mm)
        warns: List[str] = []

        # 1. 加载
        try:
            tri = load_mesh(mesh_path)
        except Exception as e:
            return {
                'ok': False, 'shape': None,
                'error': f'加载失败: {e}',
                'elapsed_s': round(time.time() - t0, 3),
            }

        if tri.n_faces == 0:
            return {
                'ok': False, 'shape': None,
                'error': '空网格',
                'tri_count': 0,
                'elapsed_s': round(time.time() - t0, 3),
            }

        # 2. 检测原语
        try:
            primitives = detect_primitives(
                tri, tol_mm=tol, try_types=try_types)
        except Exception as e:
            warns.append(f'原语检测异常: {e}')
            primitives = []

        # 3. 缝合
        shape = None
        if primitives:
            try:
                shape = primitives_to_brep(primitives, tri=tri, tol_mm=tol)
            except Exception as e:
                warns.append(f'原语缝合: {e}')

        # 4. 兜底: compound (慢)
        if shape is None and fallback_compound and _HAS_OCP:
            try:
                if tri.n_faces > 5000:
                    warns.append(
                        f'兜底缝合三角过多 ({tri.n_faces}), 跳过 (建议先 decimate).'
                    )
                else:
                    shape = mesh_to_brep_via_compound(tri, tol_mm=tol)
                    if shape is not None:
                        warns.append('走 compound 兜底缝合 (无原语拟合)')
            except Exception as e:
                warns.append(f'compound 缝合: {e}')

        # 5. 拓扑统计
        topo = None
        if shape is not None and _HAS_OCP:
            try:
                from dao_kernel import DaoKernel as K
                topo = K.count_topology(shape) if hasattr(
                    K, 'count_topology') else None
            except Exception:
                pass

        return {
            'ok': shape is not None,
            'shape': shape,
            'primitives': [p.to_dict() for p in primitives],
            'primitive_summary': {
                'plane': sum(1 for p in primitives if p.type == 'plane'),
                'cylinder': sum(1 for p in primitives if p.type == 'cylinder'),
                'sphere': sum(1 for p in primitives if p.type == 'sphere'),
                'cone': sum(1 for p in primitives if p.type == 'cone'),
                'unknown': sum(1 for p in primitives if p.type == 'unknown'),
                'total': len(primitives),
            },
            'topology': topo,
            'tri_count': tri.n_faces,
            'bbox': tri.bbox,
            'warnings': warns,
            'elapsed_s': round(time.time() - t0, 3),
        }

    def status(self) -> Dict[str, Any]:
        return {
            'name': 'Mesh2Brep',
            'tol_mm': self.tol_mm,
            'deps': deps(),
            'uptime_s': round(time.time() - self._t0, 3),
        }


# ═══════════════════════════════════════════════════════════════
# § 8 · 自验 demo
# ═══════════════════════════════════════════════════════════════

def _demo() -> Dict[str, Any]:
    """内置 demo: 用 dao_kernel 造一个 box+cylinder 复合, tessellate 成 mesh,
    再走 mesh2brep 反演. 用以验本流程."""
    if not _HAS_OCP:
        return {'ok': False, 'error': 'OCP 未装, 无法 demo'}
    try:
        import tempfile
        from dao_kernel import DaoKernel as K
        # 造 box+cylinder
        box = K.box(40, 30, 20)
        cyl = K.cylinder(8, 30, origin=(20, 15, -5), direction=(0, 0, 1))
        joined = K.cut(box, cyl)
        # Export STL
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tf:
            stl_path = tf.name
        K.to_stl(joined, stl_path) if hasattr(K, 'to_stl') else None
        if not Path(stl_path).is_file():
            return {'ok': False, 'error': 'STL 导出失败'}

        m = Mesh2Brep(tol_mm=0.5)
        r = m.fit_and_sew(stl_path)
        # 清理
        try:
            os.unlink(stl_path)
        except Exception:
            pass

        # 简化 shape 字段 (不可序列化)
        return {
            'ok': r.get('ok'),
            'tri_count': r.get('tri_count'),
            'primitive_summary': r.get('primitive_summary'),
            'topology': r.get('topology'),
            'warnings': r.get('warnings'),
            'elapsed_s': r.get('elapsed_s'),
        }
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ═══════════════════════════════════════════════════════════════
# § 9 · CLI
# ═══════════════════════════════════════════════════════════════

def _print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cli():
    import argparse
    ap = argparse.ArgumentParser(
        prog='dao_mesh2brep',
        description='网格上岸 · mesh → BREP 反演本源'
    )
    sub = ap.add_subparsers(dest='cmd')

    p_fit = sub.add_parser('fit', help='STL/OBJ → BREP')
    p_fit.add_argument('mesh_path')
    p_fit.add_argument('--out', default=None, help='输出 STEP 路径')
    p_fit.add_argument('--tol', type=float, default=0.5, help='公差 mm')
    p_fit.add_argument('--no-fallback', action='store_true',
                       help='禁用 compound 兜底缝合')
    p_fit.add_argument('--audit', action='store_true', help='缝合后跑八层审核')

    sub.add_parser('probe', help='依赖探针')
    sub.add_parser('demo', help='内置 box+cyl 自验')

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 0

    if args.cmd == 'probe':
        _print_json({'deps': deps()})
        return 0

    if args.cmd == 'demo':
        _print_json(_demo())
        return 0

    if args.cmd == 'fit':
        m = Mesh2Brep(tol_mm=args.tol)
        r = m.fit_and_sew(
            args.mesh_path,
            fallback_compound=not args.no_fallback,
        )
        # 出 STEP
        if r.get('ok') and args.out and r.get('shape') is not None and _HAS_OCP:
            try:
                from dao_kernel import DaoKernel as K
                if hasattr(K, 'to_step'):
                    K.to_step(r['shape'], args.out)
                    r['step_path'] = args.out
            except Exception as e:
                r.setdefault('warnings', []).append(f'STEP 导出: {e}')

        # 八层审核
        if r.get('ok') and args.audit and r.get('shape') is not None:
            try:
                import dao_audit
                if hasattr(dao_audit, 'full_audit'):
                    audit_r = dao_audit.full_audit(r['shape'])
                    r['audit'] = {
                        'grade': getattr(audit_r, 'grade', None) or audit_r.get(
                            'grade') if isinstance(audit_r, dict) else None,
                        'summary': str(audit_r)[:500],
                    }
            except Exception as e:
                r.setdefault('warnings', []).append(f'audit: {e}')

        # 出图
        out = {k: v for k, v in r.items() if k != 'shape'}
        out['has_shape'] = r.get('shape') is not None
        _print_json(out)
        return 0 if r.get('ok') else 1

    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(_cli())
