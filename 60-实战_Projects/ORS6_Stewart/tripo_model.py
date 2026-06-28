#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tripo_model — ORS6 SR6 的"图片转3D"真相模型 (image-to-3D ground truth).

道法自然 · 反者道之动:
    旧路径(正向假设位姿: 用固件IK把31个STL逐件摆放再合并)产出"一坨浆糊"——
    位置排布全靠假设, 与实物对不上。
    本模块改走反向: 以实物照片的 image-to-3D 重建 (Tripo) 为唯一几何真相,
    它把真实装配状态(机体/白舵机摇臂/6红连杆+铬球头/红色接收圆环)如实记录下来,
    位置不再由我们假设, 而是来自对真实世界的重建。

资产: ``assets/ORS6_tripo.glb`` —— Tripo 重建网格, 已 meshopt 解压 + 精简到
    ~20万面 + 烘焙逐顶点色; trimesh 可直接读取。原始 77.5 万顶点/149 万面。

坐标: Tripo 归一化到单位立方 (最长轴 z≈1.0)。``SCALE_TO_MM`` 把它换算到毫米
    (实物最长尺寸 ≈ 289.5mm)。

对外 API:
    load_tripo(scale_mm=False)        -> (V, F, C)   顶点/面/逐顶点RGB(0..1)
    render(V, F, C, view_dir, ...)    -> HxWx3 uint8  逐顶点色软件光栅器
    render_tripo_views(out_dir, ...)  -> [png ...]    多视角渲染
    tripo_info()                      -> dict         顶点/面/包围盒/尺寸
"""
from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_HERE, "assets", "ORS6_tripo.glb")

# 实物 SR6 最长尺寸 ≈ 289.5 mm; Tripo 归一化最长轴 = 1.0
SCALE_TO_MM = 289.5

VIEWS: Dict[str, Tuple[float, float, float]] = {
    "iso": (1, -1, 0.6),
    "front": (0, -1, 0.1),
    "side": (1, 0, 0.1),
    "top": (0.05, 0.05, 1),
    "iso2": (-1, -1, 0.5),
    "back": (0, 1, 0.1),
}


def load_tripo(path: str = MODEL_PATH, scale_mm: bool = False
               ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load the Tripo model -> (V (N,3) float, F (M,3) int, C (N,3) float 0..1).

    Bakes texture/vertex colors into a per-vertex RGB array. Geometry is merged
    across scene parts into a single vertex/face buffer.
    """
    import trimesh

    scene = trimesh.load(path, process=False)
    geos = scene.geometry.values() if isinstance(scene, trimesh.Scene) else [scene]
    Vs: List[np.ndarray] = []
    Fs: List[np.ndarray] = []
    Cs: List[np.ndarray] = []
    voff = 0
    for g in geos:
        if not isinstance(g, trimesh.Trimesh) or len(g.faces) == 0:
            continue
        cv = None
        vis = g.visual
        try:
            if hasattr(vis, "vertex_colors") and getattr(vis, "kind", None) == "vertex":
                cv = np.asarray(vis.vertex_colors)
            else:
                cv = vis.to_color().vertex_colors
        except Exception:
            cv = None
        if cv is None or len(cv) != len(g.vertices):
            cv = np.tile(np.array([180, 180, 180, 255], np.uint8), (len(g.vertices), 1))
        Vs.append(np.asarray(g.vertices, np.float64))
        Fs.append(np.asarray(g.faces, np.int64) + voff)
        Cs.append(cv[:, :3].astype(np.float64) / 255.0)
        voff += len(g.vertices)
    if not Vs:
        raise ValueError(f"no renderable geometry in {path}")
    V = np.vstack(Vs)
    F = np.vstack(Fs)
    C = np.vstack(Cs)
    V = V - (V.min(0) + V.max(0)) / 2.0
    if scale_mm:
        V = V * SCALE_TO_MM
    return V, F, C


def _look_at(view_dir, up=(0, 0, 1)):
    f = np.array(view_dir, float)
    f /= np.linalg.norm(f)
    up = np.array(up, float)
    r = np.cross(f, up)
    if np.linalg.norm(r) < 1e-6:
        up = np.array([0, 1, 0.0])
        r = np.cross(f, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return r, u, f


def render(V: np.ndarray, F: np.ndarray, C: np.ndarray,
           view_dir=(1, -1, 0.6), up=(0, 0, 1), W: int = 720, H: int = 720,
           light=(0.3, -0.6, 0.8), bg=(1, 1, 1), ambient: float = 0.35,
           margin: float = 0.07) -> np.ndarray:
    """Pure-numpy orthographic z-buffer rasterizer with per-vertex Gouraud color
    and Lambertian face shading. Returns HxWx3 uint8 RGB."""
    r, u, f = _look_at(view_dir, up)
    P = V - V.mean(0)
    x = P @ r
    y = P @ u
    z = P @ f
    nrm = np.array(light, float)
    nrm /= np.linalg.norm(nrm)
    v0 = V[F[:, 0]]
    v1 = V[F[:, 1]]
    v2 = V[F[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    ln = np.linalg.norm(fn, axis=1, keepdims=True)
    ln[ln == 0] = 1
    fn = fn / ln
    xmin, xmax = x.min(), x.max()
    ymin, ymax = y.min(), y.max()
    span = max(xmax - xmin, ymax - ymin) * (1 + 2 * margin)
    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2
    px = (x - cx) / span * W + W / 2
    py = H / 2 - (y - cy) / span * H
    img = np.ones((H, W, 3), float) * np.array(bg)
    zb = np.full((H, W), 1e18)
    fp = np.stack([px, py], 1)
    for i in range(len(F)):
        a, b, c = F[i]
        x0, y0 = fp[a]
        x1, y1 = fp[b]
        x2, y2 = fp[c]
        minx = int(max(0, math.floor(min(x0, x1, x2))))
        maxx = int(min(W - 1, math.ceil(max(x0, x1, x2))))
        miny = int(max(0, math.floor(min(y0, y1, y2))))
        maxy = int(min(H - 1, math.ceil(max(y0, y1, y2))))
        if minx > maxx or miny > maxy:
            continue
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-9:
            continue
        ys, xs = np.mgrid[miny:maxy + 1, minx:maxx + 1]
        l0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / denom
        l1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / denom
        l2 = 1 - l0 - l1
        inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        if not inside.any():
            continue
        zf = l0 * z[a] + l1 * z[b] + l2 * z[c]
        shade = ambient + (1 - ambient) * max(0.0, abs(float(fn[i] @ nrm)))
        col = (l0[..., None] * C[a] + l1[..., None] * C[b] + l2[..., None] * C[c]) * shade
        yy = ys[inside]
        xx = xs[inside]
        zz = zf[inside]
        cc = col[inside]
        closer = zz < zb[yy, xx]
        yy, xx, cc = yy[closer], xx[closer], cc[closer]
        zb[yy, xx] = zz[closer]
        img[yy, xx] = np.clip(cc, 0, 1)
    return (img * 255).astype(np.uint8)


def render_tripo_views(out_dir: str = "output/tripo", views: Optional[Dict] = None,
                       W: int = 720, H: int = 720, path: str = MODEL_PATH) -> List[str]:
    """Render the Tripo model from each view to PNG. Returns list of paths."""
    from PIL import Image

    V, F, C = load_tripo(path)
    views = views or VIEWS
    os.makedirs(out_dir, exist_ok=True)
    paths: List[str] = []
    for name, vd in views.items():
        img = render(V, F, C, vd, W=W, H=H)
        p = os.path.join(out_dir, f"ORS6_tripo_{name}.png")
        Image.fromarray(img).save(p)
        paths.append(p)
    return paths


def tripo_info(path: str = MODEL_PATH) -> Dict:
    """Return verts/faces/bounds and physical size (mm) of the Tripo model."""
    V, F, C = load_tripo(path, scale_mm=True)
    lo = V.min(0)
    hi = V.max(0)
    return {
        "path": path,
        "vertices": int(len(V)),
        "faces": int(len(F)),
        "bounds_mm": [lo.tolist(), hi.tolist()],
        "size_mm": (hi - lo).tolist(),
        "mean_color": C.mean(0).tolist(),
        "scale_to_mm": SCALE_TO_MM,
    }
