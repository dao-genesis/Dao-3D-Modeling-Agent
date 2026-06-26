#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_perception.py · 空间知觉内核 · 第十六妙门「知」
══════════════════════════════════════════════════════════════════════════════
反者道之动 — 不从外部建模平台/云图生3D出发, 从「知觉」本源出发.
弱者道之用 — 仅 numpy 为基 (trimesh/scipy/PIL 皆可选), VM 内闭环, 不依赖
             FreeCAD/SolidWorks/OCP/任何在线平台.
无为而无不为 — 让 Agent 像人一样「看懂」三维: 内在可旋转的三维心象 + 自带渲染
             (心理旋转 Shepard) → 从任意视角抽 2.5D 草图 (Marr) → 由几何涌现
             结构理解 (可供性 Gibson) → 以「想象-比对」反演求解三维状态
             (analysis-by-synthesis). 建模只是此知觉能力的自然结果.

—— 把 20-万法_Forge/spatial_reasoning.md 中"为何Agent不能像人一样理解3D"的
   三根柱子 (心理旋转 / 2.5D草图 / 可供性), 从散文规则落地为可运行的内核.

五能:
  1. 心象渲染 render()        — z-buffer 软光栅 (纯 numpy), 由内在三维想象任意视角
  2. 2.5D 草图 sketch()       — 轮廓/深度/法向/遮挡边缘 = "眼睛所见"
  3. 结构理解 describe()      — PCA 朝向盒 + 对称面 + 连通件 + 亏格 + 稳定性 = "知三维态"
  4. 反演求解 recover_pose()  — 想象-比对, 由 2D 轮廓反推三维位姿 (真正的"看懂")
  5. 知觉验证 compare()       — 对齐两模型, 报三维差异 (替代硬编码数值验证, 抓"幻觉")

CLI:
  python dao_perception.py render  <mesh.stl> [--out o.png] [--view iso]
  python dao_perception.py sketch  <mesh.stl> [--out o.png]
  python dao_perception.py describe <mesh.stl>
  python dao_perception.py recover <mesh.stl>        # 自洽闭环: 藏位姿→反演→比误差
  python dao_perception.py compare <a.stl> <b.stl>
  python dao_perception.py demo    <mesh.stl> [--outdir d]
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

__version__ = "0.1.0"
__all__ = [
    "load_mesh", "Camera", "look_at", "RenderResult", "render",
    "sketch", "describe", "decimate_voxel", "recover_pose", "compare",
]

EPS = 1e-9
Array = np.ndarray


# ══════════════════════════════════════════════════════════════════════════════
# 零 · 网格本源 IO (纯 numpy STL; trimesh 仅作快路)
# ══════════════════════════════════════════════════════════════════════════════

def _load_stl_numpy(path: Path) -> Tuple[Array, Array]:
    """纯 numpy 读 STL (binary / ascii) → (V, F). 不去重顶点 (每面独立三顶点)."""
    data = Path(path).read_bytes()
    is_ascii = data[:5].lower().lstrip().startswith(b"solid") and b"facet" in data[:1024].lower()
    if not is_ascii:
        # binary: 80B header + uint32 count + 50B/face
        n = int(np.frombuffer(data, dtype="<u4", count=1, offset=80)[0])
        expect = 84 + n * 50
        if expect <= len(data):
            rec = np.frombuffer(data, dtype=np.uint8, count=n * 50, offset=84).reshape(n, 50)
            tri = rec[:, 12:48].copy().view("<f4").reshape(n, 3, 3).astype(np.float64)
            V = tri.reshape(-1, 3)
            F = np.arange(n * 3, dtype=np.int64).reshape(n, 3)
            return V, F
    # ascii fallback
    verts: List[Tuple[float, float, float]] = []
    for line in data.decode("utf-8", "ignore").splitlines():
        s = line.strip()
        if s.startswith("vertex"):
            p = s.split()
            verts.append((float(p[1]), float(p[2]), float(p[3])))
    V = np.asarray(verts, dtype=np.float64)
    F = np.arange(len(verts), dtype=np.int64).reshape(-1, 3)
    return V, F


def load_mesh(path: str | Path) -> Tuple[Array, Array]:
    """载入网格 → (V[n,3] float64, F[m,3] int64). 优先 trimesh, 退化到纯 numpy STL."""
    path = Path(path)
    try:
        import trimesh  # type: ignore
        m = trimesh.load(str(path), process=False, force="mesh")
        if hasattr(m, "geometry") and getattr(m, "geometry", None):
            m = m.dump(concatenate=True)
        V = np.asarray(m.vertices, dtype=np.float64)
        F = np.asarray(m.faces, dtype=np.int64)
        if len(V) and len(F):
            return V, F
    except Exception:
        pass
    return _load_stl_numpy(path)


# ══════════════════════════════════════════════════════════════════════════════
# 一 · 几何基元 / 相机 (心理旋转的数学基)
# ══════════════════════════════════════════════════════════════════════════════

def _unit(v: Array) -> Array:
    n = np.linalg.norm(v)
    return v / n if n > EPS else v


def axis_angle_to_R(axis: Array, angle: float) -> Array:
    """Rodrigues: 轴角 → 3x3 旋转 (右手)."""
    a = _unit(np.asarray(axis, dtype=np.float64))
    x, y, z = a
    c, s = math.cos(angle), math.sin(angle)
    C = 1.0 - c
    return np.array([
        [c + x*x*C,   x*y*C - z*s, x*z*C + y*s],
        [y*x*C + z*s, c + y*y*C,   y*z*C - x*s],
        [z*x*C - y*s, z*y*C + x*s, c + z*z*C],
    ], dtype=np.float64)


def euler_to_R(rx: float, ry: float, rz: float) -> Array:
    """ZYX intrinsic 欧拉角 → R."""
    Rx = axis_angle_to_R(np.array([1.0, 0, 0]), rx)
    Ry = axis_angle_to_R(np.array([0, 1.0, 0]), ry)
    Rz = axis_angle_to_R(np.array([0, 0, 1.0]), rz)
    return Rz @ Ry @ Rx


def R_geodesic_deg(Ra: Array, Rb: Array) -> float:
    """两旋转间测地角 (度)."""
    Rrel = Ra.T @ Rb
    c = (np.trace(Rrel) - 1.0) / 2.0
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


@dataclass
class Camera:
    """针孔相机. 相机系: x 右, y 下, z 前 (看向 +z). 像素 u=fx*x/z+cx, v=fy*y/z+cy."""
    R: Array               # world→cam 旋转 (行为相机基 x,y,z)
    eye: Array             # 相机世界位置
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    near: float = 1e-3

    def to_cam(self, Vw: Array) -> Array:
        return (Vw - self.eye[None, :]) @ self.R.T


def look_at(eye, target, up=(0, 0, 1), width=512, height=512, fov_deg=35.0) -> Camera:
    eye = np.asarray(eye, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    up = np.asarray(up, dtype=np.float64)
    zc = _unit(target - eye)              # 前
    xc = _unit(np.cross(zc, up))          # 右
    if np.linalg.norm(xc) < EPS:          # up 与视线平行时换参考
        xc = _unit(np.cross(zc, np.array([0.0, 1.0, 0.0])))
    yc = np.cross(zc, xc)                 # 下
    R = np.stack([xc, yc, zc], axis=0)
    f = 0.5 * height / math.tan(math.radians(fov_deg) * 0.5)
    return Camera(R=R, eye=eye, width=int(width), height=int(height),
                  fx=f, fy=f, cx=width / 2.0, cy=height / 2.0)


def camera_orbit(center: Array, radius: float, az_deg: float, el_deg: float,
                 width=512, height=512, fov_deg=35.0, up=(0, 0, 1)) -> Camera:
    """绕 center 的轨道相机 (方位角 az, 仰角 el, 单位度). z 为世界上方."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    d = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    eye = np.asarray(center, dtype=np.float64) + radius * d
    return look_at(eye, center, up=up, width=width, height=height, fov_deg=fov_deg)


# ══════════════════════════════════════════════════════════════════════════════
# 二 · 心象渲染 · z-buffer 软光栅 (纯 numpy)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RenderResult:
    depth: Array            # (H,W) float, 背景 = +inf
    mask: Array             # (H,W) bool, 前景
    normal: Array           # (H,W,3) 相机系法向 (-1..1), 背景 0
    tri_id: Array           # (H,W) int, 命中面 id, 背景 -1

    @property
    def shaded(self) -> Array:
        """Lambert 着色灰度图 (0..1). 双面着色 (装配网格绕序不一, 取 |n·l|) + 深度雾化."""
        ld = _unit(np.array([0.3, -0.4, -0.85]))   # 指向相机的光 (z 前为正, 取负=朝相机)
        ndl = np.abs(self.normal @ ld)              # 双面: 不依赖面绕序
        img = 0.25 + 0.75 * ndl
        img[~self.mask] = 0.0
        return img


def render(V: Array, F: Array, cam: Camera, cull_back: bool = False) -> RenderResult:
    """软光栅: 把内在三维心象渲染为 depth/mask/normal/tri_id. 纯 numpy, 逐面向量化像素."""
    H, W = cam.height, cam.width
    depth = np.full((H, W), np.inf, dtype=np.float64)
    tri_id = np.full((H, W), -1, dtype=np.int64)
    normal = np.zeros((H, W, 3), dtype=np.float64)

    Vc = cam.to_cam(V)                                  # (n,3) 相机系
    tri = Vc[F]                                          # (m,3,3)
    z = tri[:, :, 2]                                     # (m,3)
    front = np.all(z > cam.near, axis=1)                # 简单近裁 (整面在近面前)
    # 面法向 (相机系) 供着色
    e1 = tri[:, 1] - tri[:, 0]
    e2 = tri[:, 2] - tri[:, 0]
    fn = np.cross(e1, e2)
    fnl = np.linalg.norm(fn, axis=1, keepdims=True)
    fn_unit = fn / np.maximum(fnl, EPS)

    # 投影
    u = cam.fx * tri[:, :, 0] / z + cam.cx              # (m,3)
    v = cam.fy * tri[:, :, 1] / z + cam.cy
    area2 = (u[:, 1] - u[:, 0]) * (v[:, 2] - v[:, 0]) - \
            (u[:, 2] - u[:, 0]) * (v[:, 1] - v[:, 0])   # 有符号像素面积*2
    valid = front & (np.abs(area2) > 1e-7)
    if cull_back:
        valid &= (area2 < 0)                            # 朝相机的绕序 (本系下背面 area2>0)

    idx = np.nonzero(valid)[0]
    inv_area = np.zeros_like(area2)
    inv_area[valid] = 1.0 / area2[valid]

    for i in idx:
        u0, u1, u2 = u[i]
        v0, v1, v2 = v[i]
        xmin = max(int(math.floor(min(u0, u1, u2))), 0)
        xmax = min(int(math.ceil(max(u0, u1, u2))), W - 1)
        ymin = max(int(math.floor(min(v0, v1, v2))), 0)
        ymax = min(int(math.ceil(max(v0, v1, v2))), H - 1)
        if xmin > xmax or ymin > ymax:
            continue
        xs = np.arange(xmin, xmax + 1)
        ys = np.arange(ymin, ymax + 1)
        px, py = np.meshgrid(xs + 0.5, ys + 0.5)        # 像素中心
        ia = inv_area[i]
        w0 = ((u1 - px) * (v2 - py) - (u2 - px) * (v1 - py)) * ia
        w1 = ((u2 - px) * (v0 - py) - (u0 - px) * (v2 - py)) * ia
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        z0, z1, z2 = z[i]
        # 透视正确深度: 对 1/z 做重心插值
        invz = w0 / z0 + w1 / z1 + w2 / z2
        zpix = 1.0 / np.maximum(invz, EPS)
        sub_d = depth[ymin:ymax + 1, xmin:xmax + 1]
        better = inside & (zpix < sub_d)
        if not better.any():
            continue
        sub_d[better] = zpix[better]
        tri_id[ymin:ymax + 1, xmin:xmax + 1][better] = i
        normal[ymin:ymax + 1, xmin:xmax + 1][better] = fn_unit[i]

    mask = tri_id >= 0
    return RenderResult(depth=depth, mask=mask, normal=normal, tri_id=tri_id)


def project_to_pixels(pts: Array, cam: Camera) -> Tuple[Array, Array, Array]:
    """点→像素 (向量化). 返回 (ui, vi, valid)."""
    Pc = cam.to_cam(pts)
    z = Pc[:, 2]
    valid = z > cam.near
    u = cam.fx * Pc[:, 0] / np.where(valid, z, 1.0) + cam.cx
    v = cam.fy * Pc[:, 1] / np.where(valid, z, 1.0) + cam.cy
    ui = np.round(u).astype(np.int64)
    vi = np.round(v).astype(np.int64)
    valid &= (ui >= 0) & (ui < cam.width) & (vi >= 0) & (vi < cam.height)
    return ui, vi, valid


def _binary_dilate(mask: Array, r: int) -> Array:
    if r <= 0:
        return mask
    out = mask.copy()
    for _ in range(r):
        out[:-1, :] |= out[1:, :]; out[1:, :] |= out[:-1, :]
        out[:, :-1] |= out[:, 1:]; out[:, 1:] |= out[:, :-1]
    return out


def splat_mask(pts: Array, cam: Camera, close: int = 2) -> Array:
    """点云溅射轮廓 (全向量化, 无 python 逐面循环): 投影→置位→形态闭运算填实.
    用于反演求解的高速前向 (比三角光栅快 ~100×); 形状近似但足以驱动 IoU 优化."""
    ui, vi, valid = project_to_pixels(pts, cam)
    m = np.zeros((cam.height, cam.width), dtype=bool)
    m[vi[valid], ui[valid]] = True
    if close > 0:                               # 闭运算: 先膨胀填洞再腐蚀复原边界
        m = _binary_dilate(m, close)
        inv = _binary_dilate(~m, close)
        m = ~inv
    return m


# ── 灰度/法向 → PNG (PIL 可选; 退化到自写 P5/P6 PGM/PPM) ──────────────────────

def _to_uint8(img01: Array) -> Array:
    return np.clip(img01 * 255.0 + 0.5, 0, 255).astype(np.uint8)


def save_gray(img01: Array, path: str | Path) -> None:
    arr = _to_uint8(img01)
    path = Path(path)
    try:
        from PIL import Image  # type: ignore
        Image.fromarray(arr, mode="L").save(str(path))
        return
    except Exception:
        pass
    with open(path.with_suffix(".pgm"), "wb") as f:
        f.write(f"P5\n{arr.shape[1]} {arr.shape[0]}\n255\n".encode())
        f.write(arr.tobytes())


def save_rgb(rgb01: Array, path: str | Path) -> None:
    arr = _to_uint8(rgb01)
    path = Path(path)
    try:
        from PIL import Image  # type: ignore
        Image.fromarray(arr, mode="RGB").save(str(path))
        return
    except Exception:
        pass
    with open(path.with_suffix(".ppm"), "wb") as f:
        f.write(f"P6\n{arr.shape[1]} {arr.shape[0]}\n255\n".encode())
        f.write(arr.tobytes())


# ══════════════════════════════════════════════════════════════════════════════
# 三 · 2.5D 草图 (Marr): 轮廓 / 深度 / 法向 / 遮挡边缘
# ══════════════════════════════════════════════════════════════════════════════

def _sobel(img: Array) -> Array:
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64)
    ky = kx.T
    p = np.pad(img, 1, mode="edge")
    gx = (kx[0, 0]*p[:-2, :-2] + kx[0, 2]*p[:-2, 2:] +
          kx[1, 0]*p[1:-1, :-2] + kx[1, 2]*p[1:-1, 2:] +
          kx[2, 0]*p[2:, :-2] + kx[2, 2]*p[2:, 2:])
    gy = (ky[0, 0]*p[:-2, :-2] + ky[0, 1]*p[:-2, 1:-1] + ky[0, 2]*p[:-2, 2:] +
          ky[2, 0]*p[2:, :-2] + ky[2, 1]*p[2:, 1:-1] + ky[2, 2]*p[2:, 2:])
    return np.hypot(gx, gy)


def sketch(rr: RenderResult) -> Dict[str, Array]:
    """从渲染结果抽 2.5D 草图: 轮廓边 + 深度不连续 (遮挡边) + 法向不连续 (折痕)."""
    mask = rr.mask
    # 轮廓 = mask 与其腐蚀之差
    m = mask.astype(np.float64)
    eroded = (
        np.pad(m, 1)[:-2, 1:-1] * np.pad(m, 1)[2:, 1:-1] *
        np.pad(m, 1)[1:-1, :-2] * np.pad(m, 1)[1:-1, 2:] * m
    ) > 0.5
    silhouette = mask & ~eroded
    # 深度不连续 (遮挡边): 仅在前景算
    d = np.where(mask, rr.depth, np.nan)
    dfill = np.where(np.isfinite(d), d, np.nanmedian(d[np.isfinite(d)]) if mask.any() else 0.0)
    drange = (np.nanmax(dfill) - np.nanmin(dfill) + EPS)
    depth_edge = (_sobel(dfill) > (0.08 * drange)) & mask
    # 法向不连续 (折痕)
    ncomp = rr.normal.reshape(-1, 3)
    crease = np.zeros_like(mask, dtype=bool)
    for c in range(3):
        crease |= _sobel(rr.normal[:, :, c]) > 0.5
    crease &= mask
    return {"silhouette": silhouette, "depth_edge": depth_edge,
            "crease": crease, "depth_norm": dfill}


def sketch_rgb(rr: RenderResult) -> Array:
    """把 2.5D 草图叠成可视 RGB: 着色底 + 轮廓(白) + 遮挡边(红) + 折痕(蓝)."""
    sk = sketch(rr)
    base = rr.shaded
    rgb = np.stack([base, base, base], axis=-1)
    rgb[sk["crease"]] = [0.2, 0.4, 1.0]
    rgb[sk["depth_edge"]] = [1.0, 0.2, 0.2]
    rgb[sk["silhouette"]] = [1.0, 1.0, 1.0]
    return rgb


# ══════════════════════════════════════════════════════════════════════════════
# 四 · 结构理解 (可供性 Gibson + 拓扑): 由几何涌现「三维态」
# ══════════════════════════════════════════════════════════════════════════════

def _kdtree(pts: Array):
    try:
        from scipy.spatial import cKDTree  # type: ignore
        return cKDTree(pts)
    except Exception:
        return None


def _nn_dist(tree, query: Array, ref: Array) -> Array:
    if tree is not None:
        d, _ = tree.query(query)
        return d
    # 暴力退化 (分块)
    out = np.empty(len(query))
    for s in range(0, len(query), 2048):
        q = query[s:s + 2048]
        dd = np.linalg.norm(q[:, None, :] - ref[None, :, :], axis=2)
        out[s:s + 2048] = dd.min(axis=1)
    return out


def weld(V: Array, F: Array, tol: float = 1e-4) -> Tuple[Array, Array]:
    """合并重合顶点 (STL 每面独立顶点 → 焊接为共享拓扑), 供连通/欧拉/亏格计算."""
    diag = float(np.linalg.norm(V.max(0) - V.min(0))) or 1.0
    q = np.round(V / (tol * diag)).astype(np.int64)
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    Vw = np.zeros((len(uniq), 3))
    cnt = np.zeros(len(uniq))
    np.add.at(Vw, inv, V)
    np.add.at(cnt, inv, 1.0)
    Vw /= cnt[:, None]
    Fw = inv[F]
    good = (Fw[:, 0] != Fw[:, 1]) & (Fw[:, 1] != Fw[:, 2]) & (Fw[:, 0] != Fw[:, 2])
    return Vw, Fw[good]


def _connected_components(F: Array, nV: int) -> Tuple[int, List[int]]:
    """按共享顶点的并查集求面连通件 → (件数, 各件面数倒序)."""
    parent = np.arange(nV)

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    for f in F:
        r0 = find(f[0])
        for k in (1, 2):
            rk = find(f[k])
            if rk != r0:
                parent[rk] = r0
    roots = {}
    for f in F:
        r = int(find(f[0]))
        roots[r] = roots.get(r, 0) + 1
    sizes = sorted(roots.values(), reverse=True)
    return len(sizes), sizes


def describe(V: Array, F: Array, max_sym_pts: int = 4000) -> Dict[str, Any]:
    """结构理解: AABB/OBB(PCA) + 对称面 + 连通件 + 亏格 + 稳定性 + 「五问」自答."""
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    aabb_min = V.min(axis=0)
    aabb_max = V.max(axis=0)
    extents = aabb_max - aabb_min
    centroid = V.mean(axis=0)
    diag = float(np.linalg.norm(extents))

    # PCA 主轴 → 心理旋转的"自然朝向"
    Vc = V - centroid
    cov = (Vc.T @ Vc) / max(len(Vc), 1)
    evals, evecs = np.linalg.eigh(cov)
    order = np.argsort(evals)[::-1]
    axes = evecs[:, order].T                      # 3 行: 主/次/末 轴
    proj = Vc @ axes.T
    obb_extents = proj.max(axis=0) - proj.min(axis=0)

    # 对称性: 在主轴坐标系下, 沿每个主轴做镜像, 最近邻贴合率
    sample = V if len(V) <= max_sym_pts else V[np.random.default_rng(0).choice(len(V), max_sym_pts, replace=False)]
    sp = (sample - centroid) @ axes.T
    tree = _kdtree(sp)
    tol = 0.01 * diag
    symmetry = {}
    for k, name in enumerate(["major", "mid", "minor"]):
        mirrored = sp.copy()
        mirrored[:, k] = -mirrored[:, k]
        d = _nn_dist(tree, mirrored, sp)
        symmetry[name] = round(float(np.mean(d < tol)), 3)

    # 焊接顶点 → 真实拓扑 (STL 每面独立顶点会让连通/欧拉失真)
    Vw, Fw = weld(V, F)
    if len(Fw) <= 400000:
        ncomp, comp_sizes = _connected_components(Fw, len(Vw))
    else:
        ncomp, comp_sizes = -1, []

    # 亏格 (Euler): g = (2 - (V - E + F)) / 2, 仅对单壳水密有意义
    edges = np.sort(Fw[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    nE = len(np.unique(edges, axis=0))
    euler = len(Vw) - nE + len(Fw)
    genus = (2 - euler) // 2 if ncomp == 1 else None

    # 稳定性: 质心在 XY 的水平投影是否落在底面 (z≈zmin) 足迹内
    z = V[:, 2]
    base_band = V[z < aabb_min[2] + 0.05 * max(extents[2], EPS)]
    stable = None
    if len(base_band) >= 3:
        bx, by = base_band[:, 0], base_band[:, 1]
        cx, cy = centroid[0], centroid[1]
        stable = bool(bx.min() <= cx <= bx.max() and by.min() <= cy <= by.max())

    five = {
        "拓扑": f"V={len(Vw)} E={nE} F={len(Fw)} χ={euler}" + (f" genus≈{genus}" if genus is not None else f" 连通件={ncomp}"),
        "最易失败操作": "薄壁/悬伸处布尔 (壁厚<工艺最小)" if min(extents) < 0.02 * diag else "无明显薄弱",
        "关键尺寸约束": f"AABB {extents.round(1).tolist()} mm, 对角 {round(diag,1)} mm",
        "手感(质心/对称)": f"质心 {centroid.round(1).tolist()}, 主对称 {max(symmetry.values())}",
        "不能做(负空间)": "底面无足迹→不可自立" if stable is False else "可平放自立" if stable else "未定",
    }
    return {
        "aabb_min": aabb_min.round(4).tolist(),
        "aabb_max": aabb_max.round(4).tolist(),
        "extents": extents.round(4).tolist(),
        "centroid": centroid.round(4).tolist(),
        "diag": round(diag, 4),
        "pca_axes": axes.round(4).tolist(),
        "obb_extents": obb_extents.round(4).tolist(),
        "symmetry": symmetry,
        "n_components": ncomp,
        "component_sizes_top": comp_sizes[:12],
        "euler": int(euler),
        "genus": (int(genus) if genus is not None else None),
        "stable_upright": stable,
        "five_questions": five,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 五 · 网格简化 (体素聚类, 纯 numpy) — 反演时降面提速
# ══════════════════════════════════════════════════════════════════════════════

def decimate_voxel(V: Array, F: Array, target_faces: int = 4000) -> Tuple[Array, Array]:
    """体素聚类降面: 顶点按格聚类取均值, 重映射面, 删退化面."""
    if len(F) <= target_faces:
        return V, F
    diag = float(np.linalg.norm(V.max(0) - V.min(0)))
    # 由目标面数估格边长 (经验: 面数 ∝ (diag/voxel)^2)
    voxel = diag / max(math.sqrt(target_faces) * 1.2, 1.0)
    for _ in range(8):
        key = np.floor((V - V.min(0)) / voxel).astype(np.int64)
        uniq, inv = np.unique(key, axis=0, return_inverse=True)
        rep = np.zeros((len(uniq), 3))
        cnt = np.zeros(len(uniq))
        np.add.at(rep, inv, V)
        np.add.at(cnt, inv, 1.0)
        rep /= cnt[:, None]
        nf = inv[F]
        good = (nf[:, 0] != nf[:, 1]) & (nf[:, 1] != nf[:, 2]) & (nf[:, 0] != nf[:, 2])
        nf = nf[good]
        if len(nf) <= target_faces * 1.5 or len(nf) == 0:
            return rep, nf
        voxel *= 1.3
    return rep, nf


# ══════════════════════════════════════════════════════════════════════════════
# 六 · 反演求解 (analysis-by-synthesis): 由 2D 轮廓反推三维位姿
# ══════════════════════════════════════════════════════════════════════════════

def _iou(a: Array, b: Array) -> float:
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter) / float(union) if union > 0 else 1.0


def _splat_masks(pts: Array, R: Array, t: Array, cams: Sequence[Camera], close: int = 2) -> List[Array]:
    Pt = pts @ R.T + t[None, :]
    return [splat_mask(Pt, cam, close) for cam in cams]


def _orientation_seeds(n_axis: int = 6) -> List[Array]:
    """多起点朝向种子: 24 个立方对称 + 若干随机, 覆盖朝向空间."""
    seeds = [np.eye(3)]
    base = [
        euler_to_R(0, 0, a) for a in np.linspace(0, 2*math.pi, 8, endpoint=False)
    ]
    for ax in (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])):
        for ang in (math.pi/2, math.pi, 3*math.pi/2):
            seeds.append(axis_angle_to_R(ax, ang))
    seeds.extend(base)
    rng = np.random.default_rng(7)
    for _ in range(12):
        v = rng.normal(size=3)
        seeds.append(axis_angle_to_R(v, rng.uniform(0, math.pi)))
    return seeds


def recover_pose(target_masks: Sequence[Array], cams: Sequence[Camera],
                 pts: Array, R_seeds: Optional[Sequence[Array]] = None,
                 close: int = 2, verbose: bool = False) -> Dict[str, Any]:
    """想象-比对反演 (analysis-by-synthesis): 找 (R,t) 使各视角溅射轮廓与目标轮廓
    的 IoU 最大. pts = 物体表面采样点云 (内在三维心象). 不依赖任何外部引擎/平台.
    返回 {R, t, score(平均IoU), history}."""
    target_masks = [np.asarray(m, dtype=bool) for m in target_masks]
    center = pts.mean(axis=0)
    Pc = pts - center  # 绕自身质心转

    def loss_of(params: Array) -> float:
        rx, ry, rz, tx, ty, tz = params
        R = euler_to_R(rx, ry, rz)
        t = np.array([tx, ty, tz]) + center
        masks = _splat_masks(Pc, R, t, cams, close)
        return 1.0 - float(np.mean([_iou(m, tm) for m, tm in zip(masks, target_masks)]))

    seeds = list(R_seeds) if R_seeds is not None else _orientation_seeds()
    # 粗扫: 每个朝向种子评一次 (t=0), 取最优若干进入精修
    scored = []
    for R0 in seeds:
        rx, ry, rz = _R_to_euler(R0)
        L = loss_of(np.array([rx, ry, rz, 0, 0, 0]))
        scored.append((L, np.array([rx, ry, rz, 0.0, 0.0, 0.0])))
    scored.sort(key=lambda s: s[0])
    if verbose:
        print(f"[recover] coarse best IoU={1-scored[0][0]:.3f} over {len(seeds)} seeds")

    best = scored[0]
    history = [1 - scored[0][0]]
    span = float(np.linalg.norm(pts.max(0) - pts.min(0)))
    for L0, p0 in scored[:4]:
        p, L = _powell(loss_of, p0.copy(), step0=np.array([0.3, 0.3, 0.3, span*0.05, span*0.05, span*0.05]),
                       iters=80)
        history.append(1 - L)
        if L < best[0]:
            best = (L, p)
            if verbose:
                print(f"[recover] refine IoU={1-L:.4f}")
        if 1 - best[0] >= 0.99:        # 已足够贴合, 无为而止
            break
    L, p = best
    R = euler_to_R(p[0], p[1], p[2])
    t = np.array([p[3], p[4], p[5]]) + center - R @ center
    return {"R": R, "t": t, "score": 1 - L, "params": p.tolist(),
            "history": [round(h, 4) for h in history]}


def _R_to_euler(R: Array) -> Tuple[float, float, float]:
    """R (ZYX) → (rx,ry,rz). 与 euler_to_R 互逆."""
    sy = -R[2, 0]
    sy = max(-1.0, min(1.0, sy))
    ry = math.asin(sy)
    if abs(sy) < 0.9999:
        rx = math.atan2(R[2, 1], R[2, 2])
        rz = math.atan2(R[1, 0], R[0, 0])
    else:
        rx = math.atan2(-R[1, 2], R[1, 1])
        rz = 0.0
    return rx, ry, rz


def _powell(f, x0: Array, step0: Array, iters: int = 60, tol: float = 1e-4) -> Tuple[Array, float]:
    """无梯度坐标式模式搜索 (scipy 缺失时的自备优化器)."""
    try:
        from scipy.optimize import minimize  # type: ignore
        res = minimize(f, x0, method="Powell",
                       options={"maxiter": iters, "xtol": tol, "ftol": tol})
        return res.x, float(res.fun)
    except Exception:
        pass
    x = x0.copy()
    fx = f(x)
    step = step0.copy()
    for _ in range(iters):
        improved = False
        for d in range(len(x)):
            for s in (+1, -1):
                cand = x.copy()
                cand[d] += s * step[d]
                fc = f(cand)
                if fc < fx:
                    x, fx = cand, fc
                    improved = True
                    break
        if not improved:
            step *= 0.5
            if np.all(step < tol):
                break
    return x, fx


# ══════════════════════════════════════════════════════════════════════════════
# 七 · 知觉验证: 对齐两模型并报三维差异 (替代硬编码, 抓"幻觉")
# ══════════════════════════════════════════════════════════════════════════════

def _pca_frame(V: Array) -> Tuple[Array, Array]:
    c = V.mean(0)
    Vc = V - c
    _, evecs = np.linalg.eigh((Vc.T @ Vc) / max(len(Vc), 1))
    return c, evecs  # 列为轴


def _icp(src: Array, dst: Array, iters: int = 30) -> Tuple[Array, Array, float]:
    """点到点 ICP (Kabsch). 返回 R,t (src→dst) 与最终 RMS."""
    tree = _kdtree(dst)
    R = np.eye(3)
    t = np.zeros(3)
    cur = src.copy()
    rms = float("inf")
    for _ in range(iters):
        if tree is not None:
            d, j = tree.query(cur)
        else:
            dd = np.linalg.norm(cur[:, None, :] - dst[None, :, :], axis=2)
            j = dd.argmin(1)
            d = dd.min(1)
        corr = dst[j]
        mu_s, mu_d = cur.mean(0), corr.mean(0)
        H = (cur - mu_s).T @ (corr - mu_d)
        U, _, Vt = np.linalg.svd(H)
        dR = Vt.T @ U.T
        if np.linalg.det(dR) < 0:
            Vt[-1] *= -1
            dR = Vt.T @ U.T
        dt = mu_d - dR @ mu_s
        cur = cur @ dR.T + dt
        R = dR @ R
        t = dR @ t + dt
        new_rms = float(np.sqrt(np.mean(d ** 2)))
        if abs(rms - new_rms) < 1e-6:
            rms = new_rms
            break
        rms = new_rms
    return R, t, rms


def _sample_surface(V: Array, F: Array, n: int = 4000) -> Array:
    """按面积加权在三角面上采样点云."""
    tri = V[F]
    a = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    if a.sum() <= 0:
        return V[:n]
    rng = np.random.default_rng(0)
    fi = rng.choice(len(F), n, p=a / a.sum())
    u = rng.random((n, 1)); v = rng.random((n, 1))
    sw = u + v > 1
    u[sw] = 1 - u[sw]; v[sw] = 1 - v[sw]
    t = tri[fi]
    return t[:, 0] + u * (t[:, 1] - t[:, 0]) + v * (t[:, 2] - t[:, 0])


def compare(Va: Array, Fa: Array, Vb: Array, Fb: Array, n: int = 4000,
            align: bool = True) -> Dict[str, Any]:
    """知觉验证: 采样两模型表面, (可选)ICP 对齐后报双向距离/Hausdorff/差异率."""
    A = _sample_surface(Va, Fa, n)
    B = _sample_surface(Vb, Fb, n)
    diag = float(np.linalg.norm(np.vstack([Va, Vb]).max(0) - np.vstack([Va, Vb]).min(0)))
    R = np.eye(3); t = np.zeros(3); rms = None
    if align:
        # 先质心+PCA 粗对齐, 再 ICP
        ca, _ = _pca_frame(A); cb, _ = _pca_frame(B)
        R, t, rms = _icp(A - ca + cb, B, iters=40)
        A_al = (A - ca + cb) @ R.T + t
    else:
        A_al = A
    treeB = _kdtree(B); treeA = _kdtree(A_al)
    dAB = _nn_dist(treeB, A_al, B)
    dBA = _nn_dist(treeA, B, A_al)
    tol = 0.01 * diag
    return {
        "diag": round(diag, 3),
        "mean_surface_dist": round(float((dAB.mean() + dBA.mean()) / 2), 4),
        "hausdorff": round(float(max(dAB.max(), dBA.max())), 4),
        "p95_dist": round(float(np.percentile(np.concatenate([dAB, dBA]), 95)), 4),
        "match_ratio@1%diag": round(float(np.mean(np.concatenate([dAB, dBA]) < tol)), 3),
        "icp_rms": (round(rms, 4) if rms is not None else None),
        "aligned": align,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 八 · CLI
# ══════════════════════════════════════════════════════════════════════════════

_VIEWS = {
    "iso": (35.0, 25.0), "front": (-90.0, 0.0), "right": (0.0, 0.0),
    "top": (0.0, 89.0), "back": (90.0, 0.0), "left": (180.0, 0.0),
}


def _auto_cam(V: Array, view: str = "iso", res: int = 512) -> Camera:
    c = V.mean(0)
    radius = float(np.linalg.norm(V.max(0) - V.min(0))) * 1.6
    az, el = _VIEWS.get(view, _VIEWS["iso"])
    return camera_orbit(c, radius, az, el, width=res, height=res, fov_deg=35.0)


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="dao_perception · 空间知觉内核")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("render", "sketch", "describe", "recover"):
        p = sub.add_parser(name)
        p.add_parser if False else None
        p.add_argument("mesh")
        p.add_argument("--out", default=None)
        p.add_argument("--view", default="iso")
        p.add_argument("--res", type=int, default=512)
    pc = sub.add_parser("compare"); pc.add_argument("a"); pc.add_argument("b")
    pd = sub.add_parser("demo"); pd.add_argument("mesh"); pd.add_argument("--outdir", default="output/perception")
    pd.add_argument("--res", type=int, default=256)
    args = ap.parse_args(argv)

    import json
    if args.cmd == "compare":
        Va, Fa = load_mesh(args.a); Vb, Fb = load_mesh(args.b)
        print(json.dumps(compare(Va, Fa, Vb, Fb), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "demo":
        return _demo(args.mesh, args.outdir, args.res)

    V, F = load_mesh(args.mesh)
    if args.cmd == "describe":
        print(json.dumps(describe(V, F), ensure_ascii=False, indent=2))
        return 0
    cam = _auto_cam(V, args.view, args.res)
    rr = render(V, F, cam)
    out = args.out or f"perception_{args.cmd}_{args.view}.png"
    if args.cmd == "render":
        save_gray(rr.shaded, out)
    elif args.cmd == "sketch":
        save_rgb(sketch_rgb(rr), out)
    elif args.cmd == "recover":
        return _recover_selftest(V, F, args.res)
    print(f"saved {out}  (mask px={int(rr.mask.sum())})")
    return 0


def recover_selftest(V: Array, F: Array, res: int = 128, n_pts: int = 7000,
                     seed: int = 2026, verbose: bool = False) -> Dict[str, Any]:
    """自洽闭环: 藏一个随机位姿→渲多视角轮廓→从头反演→报角度/位移误差与IoU.

    返回结构化结果字典 (供上层 万法·感 调用); 不打印。
    """
    pts = _sample_surface(V, F, n_pts)            # 内在三维心象 = 表面采样点云
    c = pts.mean(0)
    rng = np.random.default_rng(seed)
    R_true = axis_angle_to_R(rng.normal(size=3), rng.uniform(0.4, 2.4))
    t_true = rng.normal(size=3) * float(np.linalg.norm(pts.max(0) - pts.min(0))) * 0.06
    cams = [_auto_cam(pts, v, res) for v in ("iso", "front", "top")]
    pt_true = (pts - c) @ R_true.T + c + t_true
    targets = [splat_mask(pt_true, cam) for cam in cams]
    t0 = time.time()
    out = recover_pose(targets, cams, pts, verbose=verbose)
    ang = R_geodesic_deg(R_true, out["R"])
    res_t = out["t"] - (c + t_true - R_true @ c)
    return {
        "surface_points": int(len(pts)),
        "true_axis_angle_deg": round(math.degrees(math.acos(max(-1, min(1, (np.trace(R_true)-1)/2)))), 2),
        "recovered_IoU": round(out["score"], 4),
        "rotation_error_deg": round(ang, 3),
        "translation_error_mm": round(float(np.linalg.norm(res_t)), 3),
        "seconds": round(time.time() - t0, 1),
        "iou_history": out["history"],
    }


def _recover_selftest(V: Array, F: Array, res: int = 128, n_pts: int = 7000) -> int:
    """CLI 包装: 跑自洽闭环并打印 JSON。"""
    import json
    print(json.dumps(recover_selftest(V, F, res, n_pts, verbose=True),
                     ensure_ascii=False, indent=2))
    return 0


def _demo(mesh: str, outdir: str, res: int) -> int:
    import json
    od = Path(outdir); od.mkdir(parents=True, exist_ok=True)
    V, F = load_mesh(mesh)
    print(f"[demo] loaded V={len(V)} F={len(F)}")
    desc = describe(V, F)
    (od / "describe.json").write_text(json.dumps(desc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[demo] describe →", desc["five_questions"]["拓扑"])
    for view in ("iso", "front", "right", "top"):
        cam = _auto_cam(V, view, res)
        rr = render(V, F, cam)
        save_gray(rr.shaded, od / f"shaded_{view}.png")
        save_rgb(sketch_rgb(rr), od / f"sketch_{view}.png")
        print(f"[demo] rendered {view}  mask px={int(rr.mask.sum())}")
    _recover_selftest(V, F, max(res // 1, 200) if res < 220 else 220)
    print(f"[demo] artifacts → {od}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
