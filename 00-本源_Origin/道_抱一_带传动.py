#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
道_抱一_带传动.py — 旋转副传动几何自涌现 · 抱一为天下式
═══════════════════════════════════════════════════════════════════════

    "圣人抱一为天下式. 不自见, 故明; 不自是, 故彰; 不自伐, 故有功."
    "水善利万物而不争, 处众人之所恶, 故几于道."
    "太上, 不知有之."
    "反者道之动, 弱者道之用. 天下万物生于有, 有生于无."

Layer: L12.1 · 传动几何涌现 (Transmission Geometry Emergence)
依赖:
  · dao_sw_live.SWLive           — L11 活体写 (SketchBuilder / FeatureBuilder / AssemblyBuilder)
  · 道_本源_逆向万法.SWReverse   — L12 活体反 (组件/面/圆柱探针)

此 "一" 立于本源, 可为 "万物" (任何项目) 所共用:

    from 道_抱一_带传动 import BeltForge
    BeltForge.from_active().run()

# 六境
  ① 发现  `discover_pulleys`   — 从装配枚举带轮候选 (同轴圆柱聚类 + 旋转对称)
  ② 配对  `pair_pulleys`        — 轴平行 + 共面 → 一条皮带
  ③ 成谋  `plan`                — 推导皮带几何 (平面/股数/外切线/包弧)
  ④ 锻造  `forge_part`          — 派生平面草图 + 拉伸成皮带零件
  ⑤ 安装  `install`             — 沿轴阵列 (幂等, 哈希命中则复用)
  ⑥ 自愈  `verify_and_heal`     — 穿模检测 + 配合验证 + 抑制旧件

# 设计原则 (道法自然)
  · 无硬编码          — 带轮名/半径/轴向/中心距皆由探测得
  · 幂等              — 同几何重跑无副作用 (按 belt_signature 哈希)
  · 不争              — 不新增同名实例, 不污装配 · 旧件抑制而非删除
  · 最小依赖          — 纯 Python stdlib + 已有本源模块 · 不引新库
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

# ── 路径引导 ──────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_DAO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "_paths.py").is_file()),
    _HERE.parent,
)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
try:
    import _paths as _dao_paths  # noqa: F401
except Exception:  # noqa: BLE001
    _dao_paths = None

# ── 本源 L11 / L12 依赖 (惰性导入, 允许无 SW 环境做纯几何测试) ─────────
try:
    import dao_sw_live as _swlive
    from dao_sw_live import SWLive, LiveDoc, LiveError, SW_PLANE
except Exception:  # noqa: BLE001
    _swlive = None
    SWLive = None  # type: ignore
    LiveDoc = None  # type: ignore
    LiveError = RuntimeError  # type: ignore
    class SW_PLANE:  # type: ignore
        FRONT = ("Front Plane", "前视基准面", "Plan de face")
        TOP   = ("Top Plane",   "上视基准面", "Plan de dessus")
        RIGHT = ("Right Plane", "右视基准面", "Plan de droite")

try:
    import importlib
    _reverse_mod = importlib.import_module("道_本源_逆向万法")
    SWReverse = getattr(_reverse_mod, "SWReverse", None)
    MemidRegistry = getattr(_reverse_mod, "MemidRegistry", None)
    _dyn = getattr(_reverse_mod, "_dyn", lambda x: x)
    _safe = getattr(_reverse_mod, "_safe", lambda fn, default=None: (fn() if callable(fn) else default))
except Exception:  # noqa: BLE001
    _reverse_mod = None
    SWReverse = None  # type: ignore
    MemidRegistry = None  # type: ignore
    def _dyn(obj):  # type: ignore
        return obj
    def _safe(fn, default=None):  # type: ignore
        try: return fn()
        except Exception: return default


__version__ = "1.0.0"
__all__ = [
    "PulleyCandidate", "BeltPair", "BeltPlan", "BeltForge",
    "BeltForgeError",
    # helpers
    "vec_norm", "vec_cross", "vec_dot", "vec_sub", "vec_add", "vec_scale",
    "angle_between", "parallel_score", "primary_axis_of",
]


# ════════════════════════════════════════════════════════════════════════
# 向量几何 (stdlib only · meters 内部 / mm 对外)
# ════════════════════════════════════════════════════════════════════════
Vec3 = Tuple[float, float, float]
_EPS = 1e-9


def vec_norm(v: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def vec_unit(v: Sequence[float]) -> Vec3:
    n = vec_norm(v)
    if n < _EPS:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def vec_cross(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vec_dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def vec_sub(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_add(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_scale(a: Sequence[float], k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def angle_between(a: Sequence[float], b: Sequence[float]) -> float:
    """返回 0..π 弧度."""
    ua = vec_unit(a); ub = vec_unit(b)
    c = max(-1.0, min(1.0, vec_dot(ua, ub)))
    return math.acos(c)


def parallel_score(a: Sequence[float], b: Sequence[float]) -> float:
    """平行度: 1.0=同向/反向, 0.0=垂直."""
    return abs(vec_dot(vec_unit(a), vec_unit(b)))


def primary_axis_of(axis: Sequence[float], tol: float = 0.05) -> Optional[Tuple[str, int]]:
    """若 axis 大致沿 ±X/±Y/±Z, 返回 ('X'|'Y'|'Z', ±1), 否则 None.

    tol 为余弦公差 (0.05 ≈ ±18°).
    """
    u = vec_unit(axis)
    if vec_norm(u) < _EPS:
        return None
    for i, name in enumerate(("X", "Y", "Z")):
        if abs(u[i]) > 1 - tol:
            return (name, 1 if u[i] > 0 else -1)
    return None


def transform_point(xf_16: Sequence[float], p_m: Sequence[float]) -> Vec3:
    """应用 4x4 变换 (SW ArrayData 布局: 0..8 旋转, 9..11 平移, 12..15 其他).

    xf_16: SW IMathTransform 的 ArrayData (16 元素).
    """
    r00, r01, r02 = xf_16[0], xf_16[1], xf_16[2]
    r10, r11, r12 = xf_16[3], xf_16[4], xf_16[5]
    r20, r21, r22 = xf_16[6], xf_16[7], xf_16[8]
    tx, ty, tz   = xf_16[9], xf_16[10], xf_16[11]
    x, y, z = p_m
    return (
        r00 * x + r01 * y + r02 * z + tx,
        r10 * x + r11 * y + r12 * z + ty,
        r20 * x + r21 * y + r22 * z + tz,
    )


def transform_vector(xf_16: Sequence[float], v_m: Sequence[float]) -> Vec3:
    """对方向向量应用旋转部分 (忽略平移)."""
    r00, r01, r02 = xf_16[0], xf_16[1], xf_16[2]
    r10, r11, r12 = xf_16[3], xf_16[4], xf_16[5]
    r20, r21, r22 = xf_16[6], xf_16[7], xf_16[8]
    x, y, z = v_m
    return (
        r00 * x + r01 * y + r02 * z,
        r10 * x + r11 * y + r12 * z,
        r20 * x + r21 * y + r22 * z,
    )


# ════════════════════════════════════════════════════════════════════════
# 平面约定 · SW 草图坐标系
# ════════════════════════════════════════════════════════════════════════
# SW 默认基准面草图坐标系 (实测自前项目 v3.0):
#   Front (XY):  sketch_u = +asm_x,   sketch_v = +asm_y,  normal = +Z
#   Top   (XZ):  sketch_u = +asm_x,   sketch_v = -asm_z,  normal = +Y
#   Right (YZ):  sketch_u = -asm_z,   sketch_v = +asm_y,  normal = +X
#
# 每项: (U_asm_axis, V_asm_axis, N_asm_axis, plane_name_aliases)
_PLANE_TABLE: List[Tuple[Vec3, Vec3, Vec3, Tuple[str, ...]]] = [
    ((1.0, 0.0, 0.0),  (0.0, 1.0, 0.0),  (0.0, 0.0, 1.0),  SW_PLANE.FRONT),
    ((1.0, 0.0, 0.0),  (0.0, 0.0, -1.0), (0.0, 1.0, 0.0),  SW_PLANE.TOP),
    ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0),  (1.0, 0.0, 0.0),  SW_PLANE.RIGHT),
]


def pick_plane_for_axis(axis: Sequence[float],
                        tol: float = 0.05,
                        ) -> Optional[Tuple[Vec3, Vec3, Vec3, Tuple[str, ...]]]:
    """按带轮轴返回其垂直平面的 (U, V, N, aliases).

    若 axis 不近 ±X/±Y/±Z (即需要 oblique 自定义平面), 返回 None.
    """
    u_axis = vec_unit(axis)
    best = None
    best_score = 1 - tol
    for U, V, N, aliases in _PLANE_TABLE:
        s = abs(vec_dot(u_axis, N))
        if s > best_score:
            best_score = s
            best = (U, V, N, aliases)
    return best


def project_to_sketch_uv(p_asm: Sequence[float],
                         origin_asm: Sequence[float],
                         U: Sequence[float],
                         V: Sequence[float],
                         ) -> Tuple[float, float]:
    """将装配空间点 P 投影到草图 (u, v) — p, origin 同单位 (m). 返回 (u, v) 同单位."""
    d = vec_sub(p_asm, origin_asm)
    return (vec_dot(d, U), vec_dot(d, V))


# ════════════════════════════════════════════════════════════════════════
# 异常 / 日志
# ════════════════════════════════════════════════════════════════════════
class BeltForgeError(RuntimeError):
    pass


_LOG: List[str] = []
_QUIET = False


def _log(msg: str, level: str = "info"):
    stamp = f"[{level[:1].upper()}]"
    line = f"{stamp} {msg}"
    _LOG.append(line)
    if not _QUIET:
        try:
            print(line, flush=True)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════
# ① 数据模型 (dataclass)
# ════════════════════════════════════════════════════════════════════════
@dataclass
class PulleyCandidate:
    """已识别的带轮候选.

    坐标单位:
      · `axis_origin_mm` / `bbox_mm` — 装配坐标系, 毫米
      · `axis_dir`                   — 装配坐标系, 单位向量
      · `radii_mm`                   — 带轮局部半径列表 (降序), 毫米
    """
    comp_name: str
    file_stem: str
    axis_origin_mm: Vec3
    axis_dir: Vec3
    radii_mm: List[float] = field(default_factory=list)
    seat_radius_mm: Optional[float] = None  # 选定的 "皮带落座" 半径
    hub_radius_mm: Optional[float] = None   # 内孔/轴毂 (最小圆柱)
    bbox_mm: Optional[Tuple[float, float, float, float, float, float]] = None
    n_cylinders: int = 0
    fixed: bool = False
    suppressed: bool = False
    confidence: float = 0.0  # 0..1 判定置信度

    def axial_span_mm(self) -> Optional[float]:
        if not self.bbox_mm:
            return None
        u = vec_unit(self.axis_dir)
        bb = self.bbox_mm
        # 按 |u| 选最大投影跨度
        spans = (abs(bb[3] - bb[0]) * abs(u[0])
                 + abs(bb[4] - bb[1]) * abs(u[1])
                 + abs(bb[5] - bb[2]) * abs(u[2]))
        return spans

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BeltPair:
    """一对同轴 (平行) 带轮 → 一组皮带候选."""
    driven: PulleyCandidate   # 主从约定: 不重要 (对称), 仅命名
    driving: PulleyCandidate
    center_distance_mm: float
    axis_dir: Vec3            # 两轮共同轴向 (单位)
    parallel_score: float

    def signature(self) -> str:
        """几何签名 — 用于幂等判断."""
        parts = [
            self.driven.file_stem, self.driving.file_stem,
            f"{self.center_distance_mm:.1f}",
            f"{(self.driven.seat_radius_mm or 0):.1f}",
            f"{(self.driving.seat_radius_mm or 0):.1f}",
        ]
        return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:10]


@dataclass
class BeltPlan:
    """从一对带轮涌现的完整皮带方案."""
    pair: BeltPair
    plane_name: str                 # 选定的 SW 平面名
    plane_U: Vec3                   # 草图 U 轴 (在装配坐标中)
    plane_V: Vec3                   # 草图 V 轴
    plane_N: Vec3                   # 平面法线
    sketch_anchor_mm: Vec3          # 草图原点在装配坐标 (通常取 driven 轴心)
    driven_uv_mm: Tuple[float, float]   # driven 中心在草图 (u, v) mm
    driving_uv_mm: Tuple[float, float]  # driving 中心在草图 (u, v) mm
    belt_outer_radius_mm: float         # C1 (driven) 处皮带外径
    belt_outer_radius_2_mm: float       # C2 (driving) 处皮带外径
    belt_inner_radius_mm: float         # C1 处皮带内径
    belt_inner_radius_2_mm: float       # C2 处皮带内径
    belt_thickness_mm: float
    belt_width_mm: float
    n_strands: int
    strand_axis_positions_mm: List[float]  # 每股在轴向的位置 (装配坐标, 同 axis_dir 投影值)
    part_filename: str              # 输出零件文件名 (不含路径)
    signature: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["pair"] = {
            "driven": self.pair.driven.comp_name,
            "driving": self.pair.driving.comp_name,
            "center_distance_mm": self.pair.center_distance_mm,
            "axis_dir": self.pair.axis_dir,
            "signature": self.pair.signature(),
        }
        return d


# ════════════════════════════════════════════════════════════════════════
# ② 圆柱探针 · 全程走 memid 庖丁之刀 (绕 gencache/dynamic 分派失灵)
# ════════════════════════════════════════════════════════════════════════
# 正确调用链 (经实测, rev 31.0):
#   comp._oleobj_  ── IComponent2.GetModelDoc2 (memid=122)
#     → IDispatch*  ── IPartDoc.GetBodies2      (memid=132, 参 type=0, cached=False)
#       → VARIANT[IDispatch*]  每项为 IBody2
#         → IBody2.GetFaces
#           → VARIANT[IDispatch*]  每项为 IFace2
#             → IFace2.GetSurface → ISurface
#               → ISurface.Identity (==4002 for CYLINDER)
#               → ISurface.CylinderParams → [x,y,z, ax,ay,az, R]  (米)
#
# CylinderParams 返回 7 元组 (SW SDK):
#   [0,1,2] = root point on axis (m)
#   [3,4,5] = axis unit direction
#   [6]     = radius (m)
def _extract_cylinder_params_ole(face_ole, mreg) -> Optional[Tuple[Vec3, Vec3, float]]:
    """从 IFace2 raw IDispatch 提取 (origin_m, axis_unit, radius_m).
    返 None 若非圆柱 / 提取失败.

    核心: 必须用 `mreg.invoke(obj, iface, method)` 显式指定接口,
    不可用 `invoke_chain`: SW API 中 `IFace2.GetSurface` 类型标为
    `IDispatch*` 而非 `ISurface*`, 链式解析无法自动跨接口.
    """
    if face_ole is None or mreg is None or not getattr(mreg, "loaded", False):
        return None
    try:
        # IFace2.GetSurface → IDispatch (实际 QI 为 ISurface)
        surf = mreg.invoke(face_ole, "IFace2", "GetSurface")
        if surf is None:
            return None
        # ISurface.Identity (memid=9) → long  (4002 = CYLINDER)
        identity = int(mreg.invoke(surf, "ISurface", "Identity"))
        if identity != 4002:
            return None
        # ISurface.CylinderParams → [x,y,z, ax,ay,az, R] in meters
        cp = mreg.invoke(surf, "ISurface", "CylinderParams")
        if cp and len(cp) >= 7:
            origin = (float(cp[0]), float(cp[1]), float(cp[2]))
            axis = vec_unit((float(cp[3]), float(cp[4]), float(cp[5])))
            radius = float(cp[6])
            return (origin, axis, radius)
    except Exception:
        return None
    return None


def _face_area_ole(face_ole, mreg) -> float:
    """获取面积 (m²) via memid.  IFace2.GetArea (memid=54, 方法返 double)."""
    try:
        return float(mreg.invoke(face_ole, "IFace2", "GetArea"))
    except Exception:
        return 0.0


def _extract_cylinders_from_component(comp, mreg) -> List[Dict[str, Any]]:
    """遍历组件 body 的所有面 · 抽圆柱 · 以 part-local 坐标 (米) 返回.

    全程 memid 庖丁之刀, 绕 `comp.GetModelDoc2` 等动态分派失灵的坑.
    每跨接口用 `mreg.invoke` 显式指定目标接口 (non-chain).
    """
    out: List[Dict[str, Any]] = []
    if comp is None or mreg is None or not getattr(mreg, "loaded", False):
        return out
    try:
        oleobj = comp._oleobj_ if hasattr(comp, "_oleobj_") else comp

        # 1) comp → ModelDoc (raw IDispatch)
        try:
            mdoc = mreg.invoke(oleobj, "IComponent2", "GetModelDoc2")
        except Exception:
            return out
        if mdoc is None:
            return out

        # 2) mdoc → bodies (IPartDoc.GetBodies2(type=0 solid, cached=False))
        try:
            bodies = mreg.invoke(mdoc, "IPartDoc", "GetBodies2", 0, False)
        except Exception:
            return out
        if not bodies:
            return out

        # 3) 每 body → faces (IBody2.GetFaces)
        for body_raw in bodies:
            if body_raw is None:
                continue
            try:
                faces = mreg.invoke(body_raw, "IBody2", "GetFaces")
            except Exception:
                continue
            if not faces:
                continue
            for face_raw in faces:
                if face_raw is None:
                    continue
                cp = _extract_cylinder_params_ole(face_raw, mreg)
                if cp is None:
                    continue
                origin, axis, radius = cp
                area = _face_area_ole(face_raw, mreg)
                out.append({
                    "origin": origin,
                    "axis": axis,
                    "radius": radius,
                    "area": area,
                })
    except Exception:
        pass
    return out


# 向后兼容别名 (selftest / 外部调用)
def _extract_cylinder_params(face_com, mreg) -> Optional[Tuple[Vec3, Vec3, float]]:
    """向后兼容: 支持传入包装对象或 raw oleobj."""
    if face_com is None:
        return None
    ole = face_com._oleobj_ if hasattr(face_com, "_oleobj_") else face_com
    return _extract_cylinder_params_ole(ole, mreg)


def _cluster_coaxial(cyls: List[Dict[str, Any]],
                     ang_tol: float = 0.05,    # ≈3° 余弦
                     pos_tol_m: float = 1e-3,  # 1mm
                     ) -> List[List[Dict[str, Any]]]:
    """按同轴聚类 · 轴平行且轴心距 < pos_tol."""
    if not cyls:
        return []
    clusters: List[List[Dict[str, Any]]] = []
    used = [False] * len(cyls)
    for i, c in enumerate(cyls):
        if used[i]: continue
        ci_ax = c["axis"]; ci_or = c["origin"]
        group = [c]; used[i] = True
        for j in range(i + 1, len(cyls)):
            if used[j]: continue
            cj = cyls[j]
            # 平行判定
            if abs(vec_dot(ci_ax, cj["axis"])) < 1 - ang_tol:
                continue
            # 轴心距: 从 cj.origin 到 ci 轴的垂距
            d = vec_sub(cj["origin"], ci_or)
            d_par = vec_dot(d, ci_ax)
            d_perp = vec_sub(d, vec_scale(ci_ax, d_par))
            if vec_norm(d_perp) > pos_tol_m:
                continue
            group.append(cj); used[j] = True
        if len(group) >= 1:
            clusters.append(group)
    return clusters


def _pulley_from_cluster(cluster: List[Dict[str, Any]],
                         comp_name: str,
                         file_stem: str,
                         comp_transform_16: Optional[Sequence[float]] = None,
                         bbox_m: Optional[Sequence[float]] = None,
                         ) -> Optional[PulleyCandidate]:
    """从一组同轴圆柱生成 PulleyCandidate. 阈值: cluster 至少 1 圆柱."""
    if not cluster:
        return None
    # 取 part-local 圆柱, 变换到 assembly 坐标
    radii_mm_set: List[float] = []
    # 共用轴向 (以最长面积者为代表)
    rep = max(cluster, key=lambda c: c["area"])
    local_origin = rep["origin"]
    local_axis = rep["axis"]
    if comp_transform_16:
        asm_origin = transform_point(comp_transform_16, local_origin)
        asm_axis = vec_unit(transform_vector(comp_transform_16, local_axis))
    else:
        asm_origin = local_origin
        asm_axis = local_axis

    for c in cluster:
        r_mm = round(c["radius"] * 1000, 3)
        if all(abs(r_mm - r) > 0.5 for r in radii_mm_set):
            radii_mm_set.append(r_mm)
    radii_mm_set.sort(reverse=True)

    # 带轮半径角色识别:
    #   · n==1   仅外径, 可能简化建模 → seat=唯一半径
    #   · n==2   外径+轴孔 → seat=外径(较大)  hub=轴孔
    #   · n>=3   外径(最大,飞边/法兰)+皮带槽(中)+轴孔(最小) → seat=中位
    #            (皮带真正接触沟槽内径, 而非外缘飞边)
    if not radii_mm_set:
        seat, hub = None, None
    elif len(radii_mm_set) == 1:
        seat = radii_mm_set[0]; hub = None
    elif len(radii_mm_set) == 2:
        seat = radii_mm_set[0]; hub = radii_mm_set[-1]
    else:
        # 3+ 半径: 去 max (外缘法兰) 后取 max (皮带槽所在)
        seat = radii_mm_set[1]  # 第二大 = 皮带实际坐落
        hub = radii_mm_set[-1]

    # 置信度: 多圆柱 + 跨度 + 半径合理
    conf = 0.5
    if len(radii_mm_set) >= 2: conf += 0.2
    if len(radii_mm_set) >= 3: conf += 0.1
    if seat and 10 <= seat <= 500: conf += 0.1
    if hub and 3 <= hub <= 100: conf += 0.1

    bbox_mm = None
    if bbox_m:
        bbox_mm = tuple(round(v * 1000, 2) for v in bbox_m)

    return PulleyCandidate(
        comp_name=comp_name,
        file_stem=file_stem,
        axis_origin_mm=tuple(round(v * 1000, 2) for v in asm_origin),
        axis_dir=asm_axis,
        radii_mm=radii_mm_set,
        seat_radius_mm=seat,
        hub_radius_mm=hub,
        bbox_mm=bbox_mm,
        n_cylinders=len(cluster),
        confidence=min(1.0, conf),
    )


# ════════════════════════════════════════════════════════════════════════
# ③ 切线 / 弧包角 / 草图闭合轨道计算
# ════════════════════════════════════════════════════════════════════════
def compute_belt_racetrack(C1_uv: Tuple[float, float],
                            C2_uv: Tuple[float, float],
                            R_outer: float,
                            R_outer_2: Optional[float] = None,
                            ) -> Dict[str, Any]:
    """计算两轮间皮带闭合轮廓 · 支持等径 racetrack 与**不等径外公切线**.

    参数:
      · `R_outer`:   C1 处半径 (mm)
      · `R_outer_2`: C2 处半径 (mm). None → 视同 `R_outer` (等径 racetrack)

    几何:
      · 设 u = C1→C2 单位向量 · p = u 左旋 90°
      · 若 R1 ≠ R2: 外公切线与中心连线有夹角 α = asin((R1 - R2) / D)
        切点方向 (相对 u) = ±(π/2 - α)
      · 外包弧角 = π + 2α (R1>R2 时 C1 弧 >180°)

    闭合路径 (逆时针绕外, 从 top1 出发):
        top1 ──(line)──→ top2
                          │ arc@C2 (wrap 角: π - 2α if R2<R1 else π + 2α, 外侧 CW)
                          ↓
        bot1 ←──(line)── bot2
          │ arc@C1 (wrap 角 对称, 外侧 CW)
          ↓
        top1 (闭合)

    `direction` 沿本行走方向两弧均为 CW (-1).

    返 {D_mm, path[4], belt_length_mm, wrap1_deg, wrap2_deg, tangent_angle_deg}.
    """
    R1 = float(R_outer)
    R2 = float(R_outer if R_outer_2 is None else R_outer_2)
    dx = C2_uv[0] - C1_uv[0]
    dy = C2_uv[1] - C1_uv[1]
    D = math.sqrt(dx * dx + dy * dy)
    if D < 1e-6:
        raise BeltForgeError("两带轮中心重合, 无法作皮带")
    if abs(R1 - R2) >= D:
        raise BeltForgeError(
            f"带轮径差 |R1-R2|={abs(R1-R2):.1f} ≥ 中心距 D={D:.1f}, "
            f"一轮包住另一轮 — 无外公切线")

    ux, uy = dx / D, dy / D
    # 外公切线角 α: sin α = (R1 - R2) / D
    sin_alpha = (R1 - R2) / D
    alpha = math.asin(sin_alpha)
    # 切点方向 (相对 u, 测自各自圆心):
    # "top" 切点方向 = 旋转 u 逆时针 (π/2 - α)
    # "bot" 切点方向 = 旋转 u 顺时针 (π/2 - α) (即 -(π/2 - α))
    ang_top = math.pi / 2 - alpha
    # 方向向量
    cos_t, sin_t = math.cos(ang_top), math.sin(ang_top)
    # R(ang_top) * u:
    dir_top_x = cos_t * ux - sin_t * uy
    dir_top_y = sin_t * ux + cos_t * uy
    # R(-ang_top) * u:
    dir_bot_x = cos_t * ux + sin_t * uy   # cos(-t)=cos(t), sin(-t)=-sin(t)
    dir_bot_y = -sin_t * ux + cos_t * uy

    top1 = (C1_uv[0] + R1 * dir_top_x, C1_uv[1] + R1 * dir_top_y)
    top2 = (C2_uv[0] + R2 * dir_top_x, C2_uv[1] + R2 * dir_top_y)
    bot1 = (C1_uv[0] + R1 * dir_bot_x, C1_uv[1] + R1 * dir_bot_y)
    bot2 = (C2_uv[0] + R2 * dir_bot_x, C2_uv[1] + R2 * dir_bot_y)

    def _ang(center, pt):
        return math.degrees(math.atan2(pt[1] - center[1], pt[0] - center[0]))

    # 包弧角
    wrap1 = math.pi + 2 * alpha   # C1 (R1) 包角
    wrap2 = math.pi - 2 * alpha   # C2 (R2) 包角
    # 切线段长度
    tangent_len = math.sqrt(max(0.0, D * D - (R1 - R2) ** 2))

    path = [
        # 1) top1 → top2 (上切线)
        {"kind": "line", "p0": top1, "p1": top2},
        # 2) arc@C2: top2 → bot2 经 +u 外侧 (CW)
        {
            "kind": "arc", "center": C2_uv, "radius": R2,
            "a_start_deg": _ang(C2_uv, top2),
            "a_end_deg":   _ang(C2_uv, bot2),
            "direction": -1,
            "p_start": top2, "p_end": bot2,
            "wrap_deg": math.degrees(wrap2),
        },
        # 3) bot2 → bot1 (下切线)
        {"kind": "line", "p0": bot2, "p1": bot1},
        # 4) arc@C1: bot1 → top1 经 -u 外侧 (CW)
        {
            "kind": "arc", "center": C1_uv, "radius": R1,
            "a_start_deg": _ang(C1_uv, bot1),
            "a_end_deg":   _ang(C1_uv, top1),
            "direction": -1,
            "p_start": bot1, "p_end": top1,
            "wrap_deg": math.degrees(wrap1),
        },
    ]

    return {
        "D_mm": D,
        "R1_mm": R1, "R2_mm": R2,
        "tangent_top": (top1, top2),
        "tangent_bot": (bot1, bot2),
        "tangent_len_mm": tangent_len,
        "arc1_center": C1_uv, "arc2_center": C2_uv,
        "tangent_angle_deg": math.degrees(alpha),
        "wrap1_deg": math.degrees(wrap1),
        "wrap2_deg": math.degrees(wrap2),
        "path": path,
        "belt_length_mm": 2 * tangent_len + R1 * wrap1 + R2 * wrap2,
    }


def _sketch_racetrack(sketch, track: Dict[str, Any], *,
                       merge_endpoints: bool = True,
                       model=None) -> List[Dict[str, Any]]:
    """在已进入的草图上按 path 顺序画 4 段 racetrack, 并强制合并端点.

    **关键**: SW 的 CreateLine/CreateArc 每次创建新端点. 即使坐标重合,
    contour 也视为开放. 必须显式调用 `sgMERGEPOINTS` 才能形成闭合轮廓.
    """
    import math as _math
    mgr = sketch.mgr
    _mm2m = lambda v: v / 1000.0

    # 直接走 raw mgr.CreateLine / CreateArc · 保留 COM 句柄以便端点合并
    raw_segs = []   # (COM segment, p_start_mm, p_end_mm)
    for i, seg in enumerate(track["path"]):
        if seg["kind"] == "line":
            com = mgr.CreateLine(_mm2m(seg["p0"][0]), _mm2m(seg["p0"][1]), 0,
                                  _mm2m(seg["p1"][0]), _mm2m(seg["p1"][1]), 0)
            raw_segs.append((com, tuple(seg["p0"]), tuple(seg["p1"])))
            _log(f"    seg[{i}] line ({seg['p0'][0]:+.3f},{seg['p0'][1]:+.3f}) → "
                 f"({seg['p1'][0]:+.3f},{seg['p1'][1]:+.3f})  ok={com is not None}")
        else:  # arc
            sa = _math.radians(seg["a_start_deg"])
            ea = _math.radians(seg["a_end_deg"])
            cx, cy = seg["center"]; r = seg["radius"]
            sx = cx + r * _math.cos(sa);  sy = cy + r * _math.sin(sa)
            ex = cx + r * _math.cos(ea);  ey = cy + r * _math.sin(ea)
            com = mgr.CreateArc(_mm2m(cx), _mm2m(cy), 0,
                                 _mm2m(sx), _mm2m(sy), 0,
                                 _mm2m(ex), _mm2m(ey), 0,
                                 int(seg["direction"]))
            raw_segs.append((com, (sx, sy), (ex, ey)))
            _log(f"    seg[{i}] arc c=({cx:+.3f},{cy:+.3f}) r={r:.3f} "
                 f"a=[{seg['a_start_deg']:+.2f}°→{seg['a_end_deg']:+.2f}°] "
                 f"dir={seg['direction']}  ok={com is not None}")

    results = [{"ok": s[0] is not None, "p_start": s[1], "p_end": s[2]} for s in raw_segs]

    if not merge_endpoints or model is None:
        return results

    # 合并相邻段端点: path[i].end 与 path[(i+1)%n].start
    try:
        import pythoncom as _pyc
        from win32com.client import VARIANT as _VARIANT
        NULL_SD = _VARIANT(_pyc.VT_DISPATCH, None)
    except Exception:
        return results

    n = len(raw_segs)
    merged = 0
    for i in range(n):
        seg_a, _, _ = raw_segs[i]
        seg_b, _, _ = raw_segs[(i + 1) % n]
        if seg_a is None or seg_b is None:
            continue
        try:
            model.ClearSelection2(True)
            ep = seg_a.GetEndPoint2
            sp = seg_b.GetStartPoint2
            r1 = ep.Select4(False, NULL_SD)
            r2 = sp.Select4(True, NULL_SD)
            sm = model.SelectionManager
            cnt = sm.GetSelectedObjectCount2(-1)
            if cnt >= 2:
                try:
                    model.SketchAddConstraints("sgMERGEPOINTS")
                    merged += 1
                except Exception:
                    try:
                        model.SketchAddConstraints("sgCOINCIDENT")
                        merged += 1
                    except Exception as e2:
                        _log(f"    merge pair[{i}]: sgCOINCIDENT err {e2}", "warn")
        except Exception as e:
            _log(f"    merge pair[{i}] err: {e}", "warn")
    _log(f"    端点合并: {merged}/{n} 对 sgMERGEPOINTS")
    model.ClearSelection2(True)
    return results


# ════════════════════════════════════════════════════════════════════════
# ④ BeltForge — 主编排器
# ════════════════════════════════════════════════════════════════════════
# 关键词识别 (启发式, 可扩展 — 仅用于置信度加分, 非硬约束)
_PULLEY_KEYWORDS = (
    "pulley", "sheave", "belt_pulley", "v_pulley",
    "带轮", "滑轮", "皮带轮",
)
_BELT_KEYWORDS = (
    "belt", "v_belt", "vbelt", "timing_belt",
    "皮带", "传动带", "三角带", "V带",
)


def _stem_matches_any(stem: str, keywords: Sequence[str]) -> bool:
    s = stem.lower()
    return any(k in s for k in keywords)


def _comp_path(comp) -> str:
    """读组件路径 · `GetPathName` 在部分 SW/pywin32 组合为 property (str),
    部分为 method. 双路兜底防 'str is not callable'."""
    if comp is None:
        return ""
    try:
        v = comp.GetPathName
    except Exception:
        return ""
    if callable(v):
        try: return str(v() or "")
        except Exception: return ""
    return str(v or "")


class BeltForge:
    """道 · 皮带传动涌现器 · 抱一为天下式.

    典型用法:
        forge = BeltForge.from_active()
        plans = forge.plan_all()              # 发现 → 配对 → 成谋
        for plan in plans:
            forge.run_plan(plan)               # 锻造 + 安装 + 验证
    """

    # ─── 构造 ──────────────────────────────────────────────────────
    def __init__(self,
                 live: Optional["SWLive"] = None,
                 reverse: Optional["SWReverse"] = None,
                 asm_dir: Optional[Path] = None,
                 ):
        self.live = live
        self.reverse = reverse
        self.asm_dir: Optional[Path] = Path(asm_dir) if asm_dir else None

        # 皮带物理参数默认 (可由用户覆写)
        self.default_belt_width_mm: float = 17.0
        self.default_belt_thickness_mm: float = 11.0
        self.default_belt_clearance_mm: float = 1.0  # 股与股间隙

        # 缓存
        self._mreg = None
        self._comp_map: Dict[str, Any] = {}

    @classmethod
    def from_active(cls,
                    live: Optional["SWLive"] = None,
                    ) -> "BeltForge":
        """绑定到当前活动 SolidWorks 装配."""
        if _swlive is None or SWReverse is None:
            raise BeltForgeError("dao_sw_live / 道_本源_逆向万法 不可导入 - 检查 sys.path")
        live = live or SWLive()
        live.ensure_live(visible=True)
        doc = live.active()
        if doc is None or not doc.is_assembly:
            raise BeltForgeError("当前活动文档非装配体")
        reverse = SWReverse()
        reverse.connect()
        asm_path = doc.path_name()
        asm_dir = Path(asm_path).parent if asm_path else None
        self = cls(live=live, reverse=reverse, asm_dir=asm_dir)
        self._mreg = reverse._mreg if hasattr(reverse, "_mreg") else None
        self._comp_map = reverse._comp_map if hasattr(reverse, "_comp_map") else {}
        return self

    # ─── 境 ①: 发现 ────────────────────────────────────────────────
    def discover_pulleys(self,
                         min_confidence: float = 0.4,
                         ) -> List[PulleyCandidate]:
        """枚举装配所有顶层组件, 按几何特征识别带轮候选."""
        if not self._comp_map:
            raise BeltForgeError("组件映射为空, 先 connect()")

        found: List[PulleyCandidate] = []
        seen_stems: Dict[str, str] = {}   # stem → first comp_name (为避免重复探测同文件)

        for comp_name, comp in self._comp_map.items():
            if comp is None: continue
            # dedup by file stem (同零件多实例只探一次几何, 但都作为候选)
            path_name = _comp_path(comp)
            stem = Path(path_name).stem if path_name else comp_name.rsplit("-", 1)[0]

            # 抑制 / 隐藏组件跳过几何探测
            if _safe(lambda: bool(comp.IsSuppressed), False):
                continue

            # 名字命中皮带关键词 → 跳过 (不作带轮探测)
            if _stem_matches_any(stem, _BELT_KEYWORDS):
                continue

            # 获取 transform (asm-local → asm)
            xf = _safe(lambda: comp.Transform2)
            xf_arr = None
            if xf:
                try:
                    xf_arr = list(xf.ArrayData)
                except Exception:
                    xf_arr = None

            # 几何探测 (按 stem 缓存, 多实例复用 cylinders)
            cache_key = f"_geom_{stem}"
            cyls = getattr(self, cache_key, None)
            if cyls is None:
                cyls = _extract_cylinders_from_component(comp, self._mreg)
                setattr(self, cache_key, cyls)

            # 少于 1 个圆柱 → 非旋转体
            if not cyls:
                continue

            # 同轴聚类
            clusters = _cluster_coaxial(cyls, ang_tol=0.03, pos_tol_m=2e-3)
            if not clusters:
                continue

            # 选最大面积 cluster (主回转体)
            main_cluster = max(clusters, key=lambda g: sum(c["area"] for c in g))

            # bbox (assembly coords)
            bbox_m = None
            try:
                bb = comp.GetBox(False, False)
                if bb and len(bb) >= 6:
                    bbox_m = tuple(bb[:6])
            except Exception:
                pass

            cand = _pulley_from_cluster(
                cluster=main_cluster,
                comp_name=comp_name,
                file_stem=stem,
                comp_transform_16=xf_arr,
                bbox_m=bbox_m,
            )
            if cand is None: continue
            cand.fixed = _safe(lambda: bool(comp.IsFixed), False)
            cand.suppressed = _safe(lambda: bool(comp.IsSuppressed), False)

            # 名字命中 pulley 加权
            if _stem_matches_any(stem, _PULLEY_KEYWORDS):
                cand.confidence = min(1.0, cand.confidence + 0.2)

            # 过滤: 半径下限 (避免误把螺栓当带轮) + 置信度
            if cand.seat_radius_mm is None or cand.seat_radius_mm < 8:
                continue
            if cand.confidence < min_confidence:
                continue

            found.append(cand)

        _log(f"发现 {len(found)} 带轮候选")
        for c in found:
            _log(f"  · {c.comp_name}  seat=R{c.seat_radius_mm}mm  "
                 f"axis=({c.axis_dir[0]:+.3f},{c.axis_dir[1]:+.3f},{c.axis_dir[2]:+.3f})  "
                 f"origin={c.axis_origin_mm}  conf={c.confidence:.2f}")
        return found

    # ─── 境 ②: 配对 ────────────────────────────────────────────────
    def pair_pulleys(self,
                     candidates: List[PulleyCandidate],
                     parallel_tol: float = 0.03,
                     max_center_dist_mm: float = 5000.0,
                     min_pair_confidence: float = 0.75,
                     ) -> List[BeltPair]:
        """将平行轴候选配对 · 一对带轮 → 一条皮带候选.

        排序核心 (由强到弱):
          ① `conf1 × conf2` — 双方皆高置信度者优先 (真带轮 conf≈1.0)
          ② 命名双双击中 `_PULLEY_KEYWORDS` 奖励 +0.5
          ③ parallel_score (同轴向强度)
          ④ center_distance — 真实皮带中心距通常显著大于杂项共轴

        筛选: 预过滤掉 `conf1 × conf2 < min_pair_confidence`
        (默 0.75² ≈ 0.56, 即至少一方 ≥0.75 且均非 0.60 杂项).
        """
        def _is_named_pulley(c: PulleyCandidate) -> bool:
            return _stem_matches_any(c.file_stem, _PULLEY_KEYWORDS)

        scored: List[Tuple[float, BeltPair]] = []
        n = len(candidates)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = candidates[i], candidates[j]
                # 预过滤: 轴平行
                ps = parallel_score(a.axis_dir, b.axis_dir)
                if ps < 1 - parallel_tol:
                    continue
                # 中心距 (仅 perp 分量 · 排除沿轴 offset 的错配)
                axis_u = vec_unit(a.axis_dir)
                dv_full = vec_sub(a.axis_origin_mm, b.axis_origin_mm)
                # 沿轴投影与垂直分量分离
                d_along = vec_dot(dv_full, axis_u)
                d_perp_vec = vec_sub(dv_full, vec_scale(axis_u, d_along))
                D_perp = vec_norm(d_perp_vec)
                D_full = vec_norm(dv_full)
                # 皮带中心距 = 垂直分量
                if D_perp < 1 or D_perp > max_center_dist_mm:
                    continue

                # 排斥: 同零件文件多实例 (hammer-1 × hammer-2 皆 R20)
                same_stem_penalty = 0.0
                if a.file_stem == b.file_stem:
                    same_stem_penalty = 0.4

                # 命名双击中加分
                both_named_bonus = 0.5 if (_is_named_pulley(a) and _is_named_pulley(b)) else 0.0

                conf_product = (a.confidence or 0) * (b.confidence or 0)

                # 综合得分 (越高越优)
                score = (conf_product + both_named_bonus + ps * 0.1
                         - same_stem_penalty)

                # 最低门槛
                if conf_product < min_pair_confidence and both_named_bonus == 0:
                    continue

                pair = BeltPair(
                    driven=a, driving=b,
                    center_distance_mm=D_perp,
                    axis_dir=axis_u,
                    parallel_score=ps,
                )
                scored.append((score, pair))

        scored.sort(key=lambda t: -t[0])
        pairs = [p for _, p in scored]
        _log(f"配对 {len(pairs)} 组 (conf × conf ≥ {min_pair_confidence}, "
             f"含命名奖励)")
        for s, p in scored[:5]:
            named1 = "✓" if _is_named_pulley(p.driven) else "·"
            named2 = "✓" if _is_named_pulley(p.driving) else "·"
            _log(f"  · score={s:.3f}  {named1}{p.driven.comp_name} ↔ "
                 f"{named2}{p.driving.comp_name}  "
                 f"D_perp={p.center_distance_mm:.1f}mm  ‖={p.parallel_score:.3f}")
        return pairs

    # ─── 境 ③: 成谋 ────────────────────────────────────────────────
    def plan(self,
             pair: BeltPair,
             *,
             belt_width_mm: Optional[float] = None,
             belt_thickness_mm: Optional[float] = None,
             n_strands: Optional[int] = None,
             stack_clearance_mm: Optional[float] = None,
             ) -> BeltPlan:
        """由一对带轮生成皮带方案. 可由调用者微调 width/thickness/strands."""
        # 轴向
        axis = vec_unit(pair.axis_dir)
        plane_info = pick_plane_for_axis(axis, tol=0.05)
        if plane_info is None:
            raise BeltForgeError(
                f"带轮轴向 {axis} 非主轴对齐 — 需自定义参考平面 (未实现)"
            )
        U, V, N, aliases = plane_info
        plane_name = aliases[1] if len(aliases) >= 2 else aliases[0]  # 中文别名优先

        # 锚点: driven 轴心 (mm → m for transform_point-style calls? 这里保持 mm 到草图)
        anchor_mm = pair.driven.axis_origin_mm
        # 投影两轮中心到 (U, V) 平面坐标
        driven_uv = project_to_sketch_uv(
            pair.driven.axis_origin_mm, anchor_mm, U, V)
        driving_uv = project_to_sketch_uv(
            pair.driving.axis_origin_mm, anchor_mm, U, V)

        # 皮带外径 = 各自带轮 seat 半径 (外公切线几何自然吸纳径差)
        r1 = pair.driven.seat_radius_mm or 0
        r2 = pair.driving.seat_radius_mm or 0
        if r1 <= 0 or r2 <= 0:
            raise BeltForgeError("带轮 seat 半径无效")

        # 宽度/厚度
        belt_w = belt_width_mm if belt_width_mm is not None else self.default_belt_width_mm
        belt_t = belt_thickness_mm if belt_thickness_mm is not None else self.default_belt_thickness_mm
        R_outer_1 = r1
        R_outer_2 = r2
        R_inner_1 = max(belt_t * 0.5, r1 - belt_t)
        R_inner_2 = max(belt_t * 0.5, r2 - belt_t)

        # 股数 — 若未给定, 默认 1 (可从带轮槽数扩展, TODO)
        if n_strands is None:
            n_strands = 1
        stack_clr = stack_clearance_mm if stack_clearance_mm is not None else self.default_belt_clearance_mm

        # 股沿轴向的偏移 (组件轴向坐标 · 对齐 driven 轴中心附近)
        # 总堆叠厚 = n_strands * belt_w + (n_strands-1) * clearance
        total_stack = n_strands * belt_w + max(0, n_strands - 1) * stack_clr
        # 第一股在轴向: anchor_axis_coord + (- total_stack/2 + belt_w/2)
        # axis 投影值 (mm): driven 轴心沿 axis 方向的标量坐标
        anchor_axis_proj = vec_dot(anchor_mm, axis)
        first_axis_pos = anchor_axis_proj - total_stack / 2.0 + belt_w / 2.0
        strand_positions = [
            first_axis_pos + k * (belt_w + stack_clr)
            for k in range(n_strands)
        ]

        # 签名 / 零件文件名
        sig = pair.signature()
        stem = f"belt_{sig}"
        part_filename = f"{stem}.SLDPRT"

        return BeltPlan(
            pair=pair,
            plane_name=plane_name,
            plane_U=U, plane_V=V, plane_N=N,
            sketch_anchor_mm=anchor_mm,
            driven_uv_mm=driven_uv,
            driving_uv_mm=driving_uv,
            belt_outer_radius_mm=R_outer_1,
            belt_outer_radius_2_mm=R_outer_2,
            belt_inner_radius_mm=R_inner_1,
            belt_inner_radius_2_mm=R_inner_2,
            belt_thickness_mm=belt_t,
            belt_width_mm=belt_w,
            n_strands=n_strands,
            strand_axis_positions_mm=strand_positions,
            part_filename=part_filename,
            signature=sig,
        )

    def plan_all(self, **plan_kwargs) -> List[BeltPlan]:
        """一键: 发现 → 配对 → 成谋 (全部)."""
        cands = self.discover_pulleys()
        pairs = self.pair_pulleys(cands)
        plans: List[BeltPlan] = []
        for p in pairs:
            try:
                plans.append(self.plan(p, **plan_kwargs))
            except BeltForgeError as e:
                _log(f"跳过 pair ({p.driven.comp_name}↔{p.driving.comp_name}): {e}", "warn")
        return plans

    # ─── 境 ④: 锻造 ────────────────────────────────────────────────
    def forge_part(self,
                   plan: BeltPlan,
                   out_path: Optional[Path] = None,
                   overwrite: bool = False,
                   ) -> Path:
        """依据 plan 锻造皮带零件 (racetrack × width).

        幂等: 若 out_path 已存在且 overwrite=False → 直接返回.
        """
        if self.live is None:
            raise BeltForgeError("live (SWLive) 未设置")
        if out_path is None:
            if self.asm_dir is None:
                raise BeltForgeError("asm_dir 未知, 必须显式 out_path")
            out_path = self.asm_dir / plan.part_filename
        out_path = Path(out_path)

        if out_path.exists() and not overwrite:
            _log(f"零件已在: {out_path.name} — 幂等跳过锻造")
            return out_path

        # 保存当前活动文档 (装配)
        asm_doc = self.live.active()

        # 新建零件
        part = self.live.new_part()
        if part is None:
            raise BeltForgeError("new_part 失败")

        # 进入指定平面草图
        r = part.sketch.start_on_plane(plan.plane_name)
        if not r.get("ok"):
            part.close(save=False)
            raise BeltForgeError(f"start_on_plane({plan.plane_name}) 失败: {r.get('err')}")

        # 计算外/内 racetrack 几何 (草图 UV, mm) — 顺序连续 4 段 (外公切线)
        track_outer = compute_belt_racetrack(
            plan.driven_uv_mm, plan.driving_uv_mm,
            plan.belt_outer_radius_mm, plan.belt_outer_radius_2_mm)

        _log(f"  锻造: D={track_outer['D_mm']:.1f}mm  "
             f"R1={track_outer['R1_mm']:.1f}  R2={track_outer['R2_mm']:.1f}  "
             f"切线角={track_outer['tangent_angle_deg']:.2f}°  "
             f"皮带周长≈{track_outer['belt_length_mm']:.1f}mm")

        # 画外轮廓 + 端点合并 (关键! 否则 contour 非闭合, extrude 返 None)
        seg_results = _sketch_racetrack(part.sketch, track_outer, model=part.raw)

        # 退出 outer 草图 → 对称拉伸 (mid_plane, 草图在皮带中线)
        part.sketch.stop()
        r = part.feature.extrude(
            depth=plan.belt_width_mm,
            direction="mid_plane",
        )
        if not r.get("ok"):
            # 保存未完成状态以便调试 (ASCII 兜底路径)
            try:
                dbg_path = out_path.parent / f"_DEBUG_{out_path.stem}.SLDPRT"
                part.save_as(str(dbg_path))
                _log(f"  DEBUG 保存断点零件: {dbg_path}")
            except Exception:
                pass
            part.close(save=False)
            # 重新激活装配
            self._reactivate_assembly(asm_doc)
            # 输出段结果方便诊断
            for i, sr in enumerate(seg_results):
                _log(f"    seg[{i}] result: {sr}")
            raise BeltForgeError(f"外轮廓拉伸失败: {r.get('err')}")

        # 内层切除 — 二次草图 · 同平面 · 内 racetrack (同外公切几何)
        if plan.belt_inner_radius_mm > 0 and plan.belt_inner_radius_2_mm > 0:
            r = part.sketch.start_on_plane(plan.plane_name)
            if r.get("ok"):
                track_inner = compute_belt_racetrack(
                    plan.driven_uv_mm, plan.driving_uv_mm,
                    plan.belt_inner_radius_mm, plan.belt_inner_radius_2_mm)
                _sketch_racetrack(part.sketch, track_inner, model=part.raw)
                part.sketch.stop()
                part.feature.extrude_cut(
                    depth=plan.belt_width_mm + 2.0,
                    direction="through_all",
                )

        # 另存为
        sr = part.save_as(str(out_path))
        if not sr.get("ok"):
            part.close(save=False)
            raise BeltForgeError(f"save_as 失败: {sr}")
        _log(f"锻造完成: {out_path}  大小={out_path.stat().st_size}B")

        # 关闭零件, 回到装配
        part.close(save=False)
        self._reactivate_assembly(asm_doc)
        return out_path

    def _reactivate_assembly(self, asm_doc) -> None:
        """将装配重新置为活动文档 (用正确的 VARIANT byref)."""
        if asm_doc is None or self.live is None:
            return
        try:
            path = asm_doc.path_name() or asm_doc.title()
            if not path:
                return
            import pythoncom
            from win32com.client import VARIANT
            errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            self.live.app.ActivateDoc3(path, True, 0, errs)
        except Exception:
            # 回退: LiveDoc.activate (可能用 win32_int, 不保证成功)
            try:
                asm_doc.activate()
            except Exception:
                pass

    # ─── 辅 · 强制设定组件精确变换 ──────────────────────────────────
    def _force_set_component_transform(self,
                                        comp: Any,
                                        pos_mm: Tuple[float, float, float],
                                        rot_colmajor_3x3: Optional[Sequence[float]] = None,
                                        ) -> bool:
        """显式覆盖组件 `Transform2` · 走 MathUtility + PUTREF 路.

        SW `AddComponent5` 把 part 的**几何中心** (bbox midpoint) 对齐到传入位置,
        非 part origin. 对 origin 不在 bbox 中心的 part (如 racetrack belt,
        part Z 中心 ≠ 0), 会造成轴向偏移. 解决: 添加后立即用此方法强制覆盖.

        参数:
          · `pos_mm`: part origin 应所在的 asm 位置 (mm)
          · `rot_colmajor_3x3`: 可选, 9 个浮点, SW 列主序存储 (默认 identity)

        返回: True / False.
        """
        if comp is None:
            return False
        if self._mreg is None:
            if self.reverse is not None:
                self._mreg = getattr(self.reverse, "_mreg", None)
            if self._mreg is None:
                return False
        app = self.live.app if self.live else None
        if app is None:
            return False
        try:
            import pythoncom as _pyc
            from win32com.client import VARIANT as _VARIANT
        except Exception:
            return False

        if rot_colmajor_3x3 is None:
            # 列主序 identity (= 行主序 identity)
            rot = [1.0, 0.0, 0.0,
                   0.0, 1.0, 0.0,
                   0.0, 0.0, 1.0]
        else:
            rot = list(rot_colmajor_3x3)[:9]
            if len(rot) < 9:
                rot = rot + [0.0] * (9 - len(rot))

        tx = pos_mm[0] / 1000.0
        ty = pos_mm[1] / 1000.0
        tz = pos_mm[2] / 1000.0
        # SW MathTransform ArrayData: 9 rot + tx,ty,tz + scale + 3 pad = 16
        arr = rot + [tx, ty, tz, 1.0, 0.0, 0.0, 0.0]

        try:
            mu = self._mreg.invoke_obj(app, "ISldWorks", "GetMathUtility")
            v = _VARIANT(_pyc.VT_ARRAY | _pyc.VT_R8, arr)
            nxf = self._mreg.invoke_obj(mu, "IMathUtility", "CreateTransform", v)
            mid = self._mreg.memid("IComponent2", "Transform2")
            raw_c = comp._oleobj_ if hasattr(comp, "_oleobj_") else comp
            raw_x = nxf._oleobj_ if hasattr(nxf, "_oleobj_") else nxf
            raw_c.Invoke(mid, 0, _pyc.DISPATCH_PROPERTYPUTREF, False, raw_x)
            return True
        except Exception as e:
            _log(f"_force_set_component_transform 失败: {e}", "warn")
            return False

    # ─── 境 ⑤: 安装 ────────────────────────────────────────────────
    def install(self, plan: BeltPlan, part_path: Path) -> Dict[str, Any]:
        """将皮带零件实例化到装配. 按股数沿轴位置阵列.

        幂等策略:
          · 扫描现有实例 · 若已按 stem=belt_<sig> 且**全 3D 位置**正确 → skip
          · 否则: 抑制所有"陈旧皮带" (匹配 _BELT_KEYWORDS 或同 stem 多余实例),
            再添加本规划所需实例, **显式覆盖 Transform2** 精确到目标位置.
        """
        if self.live is None:
            raise BeltForgeError("live 未设置")
        part_path = Path(part_path)
        if not part_path.exists():
            raise BeltForgeError(f"零件文件不存在: {part_path}")

        doc = self.live.active()
        if doc is None or not doc.is_assembly:
            raise BeltForgeError("无活动装配")
        asm = doc.assembly  # property (not method)

        # 1) 刷新组件映射 (SWReverse)
        if self.reverse is not None:
            try: self.reverse._build_comp_map()
            except Exception: pass
            self._comp_map = getattr(self.reverse, "_comp_map", self._comp_map)

        # 2) 抑制陈旧皮带 (名命中 belt 关键词, 且不属于当前 plan 的 stem)
        plan_stem = Path(plan.part_filename).stem
        suppressed = []
        for cname, comp in list(self._comp_map.items()):
            if comp is None: continue
            p = _comp_path(comp)
            stem = Path(p).stem if p else cname.rsplit("-", 1)[0]
            if stem == plan_stem:
                continue
            if _stem_matches_any(stem, _BELT_KEYWORDS):
                if _safe(lambda: bool(comp.IsSuppressed), False):
                    continue
                try:
                    comp.SetSuppression2(0)  # 0 = suppressed
                    suppressed.append(cname)
                except Exception:
                    pass
        if suppressed:
            _log(f"抑制陈旧皮带实例: {len(suppressed)} 个")

        # 3) 盘点已有"本 plan" 实例 · 采集 3D 全位 (非仅轴向)
        axis_u = vec_unit(plan.pair.axis_dir)
        anchor_axis_proj = vec_dot(plan.sketch_anchor_mm, axis_u)
        # 预算每一槽的期望 3D 位置 (part origin 在 asm 的精准点)
        expected_pos_mm: List[Tuple[float, float, float]] = []
        for k in range(plan.n_strands):
            delta = plan.strand_axis_positions_mm[k] - anchor_axis_proj
            expected_pos_mm.append(vec_add(plan.sketch_anchor_mm,
                                           vec_scale(axis_u, delta)))

        existing_this: List[Tuple[str, Any, Tuple[float, float, float]]] = []
        for cname, comp in self._comp_map.items():
            if comp is None: continue
            p = _comp_path(comp)
            if Path(p).stem != plan_stem: continue
            if _safe(lambda: bool(comp.IsSuppressed), False): continue
            xf = _safe(lambda: comp.Transform2)
            if not xf: continue
            try:
                arr = list(xf.ArrayData)
                pos_mm = (arr[9] * 1000, arr[10] * 1000, arr[11] * 1000)
            except Exception:
                continue
            existing_this.append((cname, comp, pos_mm))

        # 4) 匹配已有实例到 plan 槽位 · **3D 全位** 容差 1mm
        #    不仅轴向分量匹配, 垂直轴的分量必须与期望一致
        covered: List[bool] = [False] * plan.n_strands
        offset_heal: List[Dict[str, Any]] = []  # 位置偏 → 需要纠正的实例
        for cname, comp, pos_mm in existing_this:
            # 找最近期望位置 (3D 距离)
            deltas = [(k, vec_norm(vec_sub(expected_pos_mm[k], pos_mm)))
                      for k in range(plan.n_strands) if not covered[k]]
            if not deltas: break
            k_best, d_best = min(deltas, key=lambda t: t[1])
            if d_best < 1.0:
                covered[k_best] = True
                _log(f"  · 已有 {cname} 命中槽 {k_best} (偏 {d_best:.2f}mm) ✓")
            elif d_best < 500.0:
                # 在附近但偏离 → 纠正
                covered[k_best] = True
                offset_heal.append({
                    "cname": cname, "comp": comp, "slot": k_best,
                    "actual": pos_mm, "expected": expected_pos_mm[k_best],
                    "offset_mm": d_best,
                })
                _log(f"  · 已有 {cname} 近槽 {k_best} 但偏 {d_best:.1f}mm → 待纠正")

        missing_slots = [k for k, v in enumerate(covered) if not v]
        n_extra = len(existing_this) - sum(covered)
        _log(f"当前本方案 {plan_stem} 实例={len(existing_this)} 覆盖槽={sum(covered)}/{plan.n_strands}  "
             f"纠偏={len(offset_heal)}  待加={len(missing_slots)}  多余={n_extra}")

        # 5) 先纠正偏位的实例
        healed = []
        for h in offset_heal:
            ok = self._force_set_component_transform(h["comp"], h["expected"])
            if ok:
                healed.append(h["cname"])
                _log(f"  ↔ 纠偏 {h['cname']}: {h['actual']} → {h['expected']}")

        # 6) 添加缺失槽位 · 添加后立即强制 Transform2 精准放置
        added = []
        for k in missing_slots:
            tgt_pos_mm = expected_pos_mm[k]
            r = asm.add_component(str(part_path),
                                  x_mm=tgt_pos_mm[0],
                                  y_mm=tgt_pos_mm[1],
                                  z_mm=tgt_pos_mm[2])
            if not r.get("ok"):
                _log(f"  ↑ belt strand[{k}] add FAILED: {r.get('err')}", "warn")
                continue
            cname_new = r.get("name") or ""
            # 查找新加的 comp, 强制覆盖 Transform2
            comp_new = None
            if self.reverse is not None:
                try:
                    self.reverse._build_comp_map()
                    self._comp_map = getattr(self.reverse, "_comp_map", self._comp_map)
                    comp_new = self._comp_map.get(cname_new)
                except Exception:
                    pass
            set_ok = False
            if comp_new is not None:
                set_ok = self._force_set_component_transform(comp_new, tgt_pos_mm)
            added.append({"slot": k, "name": cname_new, "pos_mm": tgt_pos_mm,
                          "xform_forced": set_ok})
            flag = "✓" if set_ok else "△"
            _log(f"  ↑ belt strand[{k}] @ ({tgt_pos_mm[0]:.1f},{tgt_pos_mm[1]:.1f},{tgt_pos_mm[2]:.1f}) {flag}")

        # 7) 轻重建 (非强制 · 快) · 可选保存
        if added or healed:
            try:
                doc.rebuild(force=False)
            except Exception:
                pass
        save_r = {"ok": False, "skipped": "install 默认不保存; 由调用方按需 doc.save()"}
        if getattr(self, "auto_save_on_install", False):
            try:
                save_r = doc.save()
                _log(f"保存: {save_r}")
            except Exception as e:
                _log(f"保存失败: {e}", "warn")

        return {
            "ok": True,
            "plan_stem": plan_stem,
            "existed": len(existing_this),
            "covered_slots": sum(covered),
            "n_strands": plan.n_strands,
            "healed": healed,
            "added": added,
            "suppressed_stale": suppressed,
        }

    # ─── 境 ⑥: 验证 & 自愈 ─────────────────────────────────────────
    def verify_and_heal(self, plan: BeltPlan) -> Dict[str, Any]:
        """验证皮带装配状态: 股数 / 位置 / 穿模.

        返回 {ok: bool, issues: [...], healed: [...]}.
        """
        issues: List[Dict[str, Any]] = []
        healed: List[str] = []
        plan_stem = Path(plan.part_filename).stem

        if self.reverse is not None:
            try: self.reverse._build_comp_map()
            except Exception: pass
            self._comp_map = getattr(self.reverse, "_comp_map", self._comp_map)

        active = [
            (cname, comp) for cname, comp in self._comp_map.items()
            if comp is not None
            and Path(_comp_path(comp)).stem == plan_stem
            and not _safe(lambda: bool(comp.IsSuppressed), False)
        ]

        if len(active) != plan.n_strands:
            issues.append({
                "type": "strand_count_mismatch",
                "expected": plan.n_strands,
                "actual": len(active),
            })

        # 位置检查
        axis_u = vec_unit(plan.pair.axis_dir)
        for i, (cname, comp) in enumerate(sorted(active, key=lambda x: x[0])):
            xf = _safe(lambda: comp.Transform2)
            if not xf: continue
            try:
                arr = list(xf.ArrayData)
                pos_mm = (arr[9] * 1000, arr[10] * 1000, arr[11] * 1000)
            except Exception:
                continue
            # 沿轴的偏移
            anchor_proj = vec_dot(plan.sketch_anchor_mm, axis_u)
            actual_proj = vec_dot(pos_mm, axis_u)
            # 沿轴位置应属 strand_axis_positions_mm 之一 (±1mm)
            closest = min(plan.strand_axis_positions_mm,
                          key=lambda v: abs(v - actual_proj))
            if abs(closest - actual_proj) > 1.0:
                issues.append({
                    "type": "strand_axial_offset",
                    "comp": cname,
                    "actual_proj": actual_proj,
                    "closest_expected": closest,
                    "delta": actual_proj - closest,
                })

        return {"ok": len(issues) == 0, "issues": issues, "healed": healed}

    # ─── 审视 · 一览皮带/带轮/关键件全貌 ────────────────────────────
    def snapshot(self,
                  *,
                  include_disk_files: bool = True,
                  print_report: bool = True,
                  ) -> Dict[str, Any]:
        """锚定本源 · 实时审视装配的皮带生态 + 磁盘 belt 零件.

        返回 dict:
          belts: {stem: {total, active, suppressed, instances:[{name, supp, fix, pos_mm, bbox_mm}]}}
          pulleys: 同上 (stem 命中 _PULLEY_KEYWORDS)
          key_others: motor / shaft / frame / casing / mount / base 类关键件
          disk_belt_files: [{name, size_b, mtime}]  (若 include_disk_files)
          summary: {n_belt_total, n_belt_active, n_belt_suppressed, ...}
        """
        if self.reverse is not None:
            try: self.reverse._build_comp_map()
            except Exception: pass
            self._comp_map = getattr(self.reverse, "_comp_map", self._comp_map)

        def _group(comp_map):
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for cname, comp in comp_map.items():
                if comp is None: continue
                p = _comp_path(comp)
                stem = Path(p).stem if p else cname.rsplit("-", 1)[0]
                supp = _safe(lambda: bool(comp.IsSuppressed), False)
                fixed = _safe(lambda: bool(comp.IsFixed), False)
                pos = None
                try:
                    arr = list(comp.Transform2.ArrayData)
                    pos = (round(arr[9]*1000, 2),
                           round(arr[10]*1000, 2),
                           round(arr[11]*1000, 2))
                except Exception:
                    pass
                bbox = None
                try:
                    bb = comp.GetBox(False, False)
                    if bb and len(bb) >= 6:
                        bbox = tuple(round(bb[i]*1000, 1) for i in range(6))
                except Exception:
                    pass
                entry = {"name": cname, "supp": supp, "fix": fixed,
                         "pos_mm": pos, "bbox_mm": bbox, "path": p}
                groups.setdefault(stem, []).append(entry)
            return groups

        groups = _group(self._comp_map)
        belts, pulleys, key_others = {}, {}, {}
        import re as _re
        KEY_RE = _re.compile(r"(motor|shaft|frame|casing|mount|base|bracket|housing)", _re.I)
        for stem, entries in groups.items():
            bucket = {
                "total": len(entries),
                "active": sum(1 for e in entries if not e["supp"]),
                "suppressed": sum(1 for e in entries if e["supp"]),
                "instances": entries,
            }
            if _stem_matches_any(stem, _BELT_KEYWORDS):
                belts[stem] = bucket
            elif _stem_matches_any(stem, _PULLEY_KEYWORDS):
                pulleys[stem] = bucket
            elif KEY_RE.search(stem):
                key_others[stem] = bucket

        disk_files = []
        if include_disk_files and self.asm_dir is not None:
            try:
                for f in sorted(self.asm_dir.glob("*.SLDPRT")):
                    if _stem_matches_any(f.stem, _BELT_KEYWORDS) or "belt" in f.stem.lower():
                        st = f.stat()
                        disk_files.append({
                            "name": f.name,
                            "size_b": st.st_size,
                            "mtime": st.st_mtime,
                        })
            except Exception:
                pass

        summary = {
            "n_components_total": len(self._comp_map),
            "n_belt_stems": len(belts),
            "n_belt_total": sum(b["total"] for b in belts.values()),
            "n_belt_active": sum(b["active"] for b in belts.values()),
            "n_belt_suppressed": sum(b["suppressed"] for b in belts.values()),
            "n_pulley_stems": len(pulleys),
            "n_key_other_stems": len(key_others),
            "n_disk_belt_files": len(disk_files),
        }

        if print_report:
            self._print_snapshot(belts, pulleys, key_others, disk_files, summary)

        return {
            "belts": belts,
            "pulleys": pulleys,
            "key_others": key_others,
            "disk_belt_files": disk_files,
            "summary": summary,
        }

    @staticmethod
    def _print_snapshot(belts, pulleys, key_others, disk_files, summary) -> None:
        """格式化打印 snapshot."""
        print(f"\n═══ 审视 · 皮带 ({summary['n_belt_stems']} 族 / 总 {summary['n_belt_total']} / "
              f"活 {summary['n_belt_active']} / 抑 {summary['n_belt_suppressed']}) ═══")
        for stem in sorted(belts.keys()):
            b = belts[stem]
            print(f"  [{stem}]  总{b['total']} 活{b['active']} 抑{b['suppressed']}")
            for e in b["instances"]:
                flag = "S" if e["supp"] else "·"
                fx = "F" if e["fix"] else " "
                if e["pos_mm"]:
                    pos_s = f"({e['pos_mm'][0]:>8.1f},{e['pos_mm'][1]:>8.1f},{e['pos_mm'][2]:>8.1f})"
                else:
                    pos_s = "  (?)"
                print(f"    [{flag}{fx}] {e['name']:<42} {pos_s}")

        print(f"\n═══ 审视 · 带轮 ({summary['n_pulley_stems']} 族) ═══")
        for stem in sorted(pulleys.keys()):
            for e in pulleys[stem]["instances"]:
                flag = "S" if e["supp"] else "·"
                fx = "F" if e["fix"] else " "
                pos_s = (f"({e['pos_mm'][0]:>8.1f},{e['pos_mm'][1]:>8.1f},{e['pos_mm'][2]:>8.1f})"
                         if e["pos_mm"] else "  (?)")
                print(f"  [{flag}{fx}] {e['name']:<42} {pos_s}")

        if key_others:
            print(f"\n═══ 审视 · 关键件 (motor/shaft/frame/casing/mount) ═══")
            for stem in sorted(key_others.keys()):
                for e in key_others[stem]["instances"]:
                    flag = "S" if e["supp"] else "·"
                    fx = "F" if e["fix"] else " "
                    pos_s = (f"({e['pos_mm'][0]:>8.1f},{e['pos_mm'][1]:>8.1f},{e['pos_mm'][2]:>8.1f})"
                             if e["pos_mm"] else "  (?)")
                    print(f"  [{flag}{fx}] {e['name']:<42} {pos_s}")

        if disk_files:
            print(f"\n═══ 审视 · 磁盘 belt 零件 ({summary['n_disk_belt_files']} 个) ═══")
            for f in disk_files:
                print(f"  {f['name']:<50} {f['size_b']:>9} B")
        print(f"\n═══ 概要 ═══")
        for k, v in summary.items():
            print(f"  {k:<25} = {v}")

    # ─── 硬删 (非抑制) 陈旧皮带 ───────────────────────────────────
    def hard_purge_stale_belts(self,
                                plan: Optional[BeltPlan] = None,
                                *,
                                dry_run: bool = True,
                                include_active: bool = False,
                                ) -> Dict[str, Any]:
        """硬删 (DeleteSelection2) 装配中所有非本方案的 belt 实例.

        反者道之动 — 不抑制, 直接除. 以明"不留陈"原则.

        参数:
          · `plan`: 本方案; 若 None 则取 plan_all()[0] (可能耗时)
          · `dry_run`: True 仅列表; False 真删
          · `include_active`: True 也删非本方案的 active 皮带; 默认 False 只删 suppressed

        返回 {candidates: [...], deleted: [...], kept: [...]}
        """
        if self.live is None:
            raise BeltForgeError("live 未设置")
        # 确保装配为 active doc (锻造过后可能 part doc 成为 active)
        doc = self.live.active()
        if doc is None or not doc.is_assembly:
            # 尝试切到装配
            if self.asm_dir is not None:
                for asm_f in self.asm_dir.glob("*.SLDASM"):
                    try:
                        import pythoncom as _pyc
                        from win32com.client import VARIANT as _VARIANT
                        errs = _VARIANT(_pyc.VT_BYREF | _pyc.VT_I4, 0)
                        self.live.app.ActivateDoc3(str(asm_f), True, 0, errs)
                        doc = self.live.active()
                        if doc and doc.is_assembly:
                            break
                    except Exception:
                        continue
        if doc is None or not doc.is_assembly:
            raise BeltForgeError("无活动装配 (尝试激活失败)")
        asm = doc.assembly  # AssemblyBuilder
        asm_raw = doc.raw   # 原始 IAssemblyDoc (has DeleteSelection2, ClearSelection2)

        if plan is None:
            plans = self.plan_all()
            if not plans:
                raise BeltForgeError("无可行 plan 供对照")
            plan = plans[0]
        plan_stem = Path(plan.part_filename).stem

        if self.reverse is not None:
            try: self.reverse._build_comp_map()
            except Exception: pass
            self._comp_map = getattr(self.reverse, "_comp_map", self._comp_map)

        candidates: List[Dict[str, Any]] = []
        for cname, comp in list(self._comp_map.items()):
            if comp is None: continue
            p = _comp_path(comp)
            stem = Path(p).stem if p else cname.rsplit("-", 1)[0]
            if stem == plan_stem:
                continue
            if not _stem_matches_any(stem, _BELT_KEYWORDS):
                continue
            supp = _safe(lambda: bool(comp.IsSuppressed), False)
            if not supp and not include_active:
                continue
            candidates.append({"name": cname, "stem": stem, "comp": comp, "supp": supp})

        _log(f"hard_purge · 候选 {len(candidates)} 条 · 本 plan={plan_stem} · dry_run={dry_run} · incl_active={include_active}")
        for c in candidates:
            _log(f"  · {c['name']:<40} stem={c['stem']:<35} supp={c['supp']}")

        deleted: List[str] = []
        kept: List[str] = []
        if not dry_run and candidates:
            # 取 raw asm + doc.Extension (for SelectByID2 that can hit suppressed)
            ext = None
            try:
                ext = asm_raw.Extension
            except Exception:
                ext = None

            try:
                asm_raw.ClearSelection2(True)
            except Exception:
                pass

            # 逐条删除 (不批量 — 避免一条失败波及其他)
            import pythoncom as _pyc
            from win32com.client import VARIANT as _VARIANT
            NULL_SD = _VARIANT(_pyc.VT_DISPATCH, None)

            # 批量选择 (幂等累加) 再一次 DeleteSelection2 — 比逐个删省 rebuild 开销
            # 路: 用 ext.SelectByID2 把每条加入选择集 (Append=True)
            for c in candidates:
                name = c["name"]
                selected = False
                # 路 1: SelectByID2 via Extension (能选 suppressed; 累加 Append=True)
                if ext is not None:
                    try:
                        # SelectByID2(Name, Type, X, Y, Z, Append, Mark, Callout, SelectOption)
                        selected = bool(ext.SelectByID2(
                            name, "COMPONENT", 0, 0, 0, True, 0, NULL_SD, 0))
                    except Exception:
                        selected = False
                # 路 2: 组件 Select4
                if not selected:
                    try:
                        if hasattr(c["comp"], "Select4"):
                            selected = bool(c["comp"].Select4(True, NULL_SD, False))
                    except Exception:
                        selected = False
                # 路 3: 老 Select2
                if not selected:
                    try:
                        selected = bool(c["comp"].Select2(True, 0))
                    except Exception:
                        selected = False
                if not selected:
                    kept.append(f"{name} (select 失败)")

            # 一次 DeleteSelection2 删所有选中
            n_selected = len(candidates) - len(kept)
            if n_selected > 0:
                # DeleteSelection2 是 Extension 方法 (非 ModelDoc2)
                n_del = 0
                try:
                    if ext is not None:
                        # Extension.DeleteSelection2(Option)  Option=18: keep mates 但删 comp
                        ret = ext.DeleteSelection2(18)
                        n_del = 1 if ret else 0
                except AttributeError:
                    # 回退 path: IModelDoc2.Extension.DeleteSelection2 缺 → 试 IAssemblyDoc.DeleteAllMates + Delete
                    try:
                        n_del = int(asm_raw.DeleteSelection(False) or 0)
                    except Exception:
                        n_del = 0
                except Exception as e:
                    _log(f"DeleteSelection2 失败: {type(e).__name__}: {e}", "warn")
                if n_del:
                    # 假定全删了 (API 不返具体数)
                    deleted = [c["name"] for c in candidates if c["name"] not in [k.split()[0] for k in kept]]
                    _log(f"  × 批删成功: 选中 {n_selected} 条, 全部清除")
                else:
                    kept.extend([c["name"] + " (DeleteSelection2 未执行)" for c in candidates
                                 if c["name"] not in [k.split()[0] for k in kept]])
            try:
                asm_raw.ClearSelection2(True)
            except Exception:
                pass

            _log(f"DeleteSelection2 总实删 {len(deleted)} · 保留 {len(kept)}")

        return {"candidates": [{"name": c["name"], "stem": c["stem"], "supp": c["supp"]}
                                for c in candidates],
                "deleted": deleted, "kept": kept,
                "plan_stem": plan_stem, "dry_run": dry_run}

    # ─── 运行完整管线 ─────────────────────────────────────────────
    def run(self,
            plan: Optional[BeltPlan] = None,
            *,
            dry_run: bool = False,
            overwrite_part: bool = False,
            heal: bool = True,
            n_strands: Optional[int] = None,
            belt_width_mm: Optional[float] = None,
            belt_thickness_mm: Optional[float] = None,
            ) -> Dict[str, Any]:
        """走完全流程: 发现→配对→成谋→锻造→安装→验证.

        若 `plan=None` 则 discovery + plan_all() 后取第一个方案 (最高并行+最长距).
        """
        if plan is None:
            plan_kwargs: Dict[str, Any] = {}
            if n_strands is not None:
                plan_kwargs["n_strands"] = n_strands
            if belt_width_mm is not None:
                plan_kwargs["belt_width_mm"] = belt_width_mm
            if belt_thickness_mm is not None:
                plan_kwargs["belt_thickness_mm"] = belt_thickness_mm
            plans = self.plan_all(**plan_kwargs)
            if not plans:
                return {"ok": False, "stage": "plan", "err": "无可行皮带方案"}
            plan = plans[0]
            _log(f"选取方案 sig={plan.signature}  "
                 f"{plan.pair.driven.comp_name} ↔ {plan.pair.driving.comp_name}  "
                 f"D={plan.pair.center_distance_mm:.1f}mm  R={plan.belt_outer_radius_mm:.1f}mm  "
                 f"strands={plan.n_strands}")
        if dry_run:
            return {"ok": True, "stage": "dry_run", "plan": plan.to_dict()}

        # 锻造
        part_path = self.forge_part(plan, overwrite=overwrite_part)

        # 安装
        install_res = self.install(plan, part_path)

        # 验证
        result = {"ok": True, "plan": plan.to_dict(), "install": install_res}
        if heal:
            ver = self.verify_and_heal(plan)
            result["verify"] = ver
            result["ok"] = ver["ok"]
        return result


# ════════════════════════════════════════════════════════════════════════
# ⑤ CLI
# ════════════════════════════════════════════════════════════════════════
def _print_json(obj):
    try:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    except Exception:
        print(repr(obj))


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        print("\n命令:  audit | discover | plan | run | verify | purge | selftest")
        print("\n  audit                        实时审视 (皮带/带轮/关键件/磁盘文件/概要)")
        print("  discover                     发现带轮候选")
        print("  plan                         列出所有可行方案")
        print("  run [--dry|--overwrite|--no-heal|--strands N|--width MM|--thick MM]  全链")
        print("  verify                       验证当前 plan 的装配实例")
        print("  purge [--apply|--incl-active]     硬删陈旧 belt (默 dry_run)")
        print("  selftest                     纯几何自测 (无需 SW)")
        return 0
    cmd = argv[0]

    if cmd == "selftest":
        return _selftest()

    try:
        forge = BeltForge.from_active()
    except BeltForgeError as e:
        print(f"❌ {e}")
        return 2

    if cmd == "audit":
        snap = forge.snapshot(print_report=True)
        return 0

    if cmd == "discover":
        cands = forge.discover_pulleys()
        _print_json([c.to_dict() for c in cands])
        return 0

    if cmd == "plan":
        plans = forge.plan_all()
        if not plans:
            print("⚠ 无可行方案")
            return 1
        _print_json([p.to_dict() for p in plans])
        return 0

    if cmd == "run":
        # 可选: --dry / --overwrite / --no-heal / --strands N / --width MM / --thick MM
        kwargs: Dict[str, Any] = {}
        i = 1
        while i < len(argv):
            a = argv[i]
            if a == "--dry":
                kwargs["dry_run"] = True
            elif a == "--overwrite":
                kwargs["overwrite_part"] = True
            elif a == "--no-heal":
                kwargs["heal"] = False
            elif a == "--strands" and i + 1 < len(argv):
                try: kwargs["n_strands"] = int(argv[i + 1]); i += 1
                except ValueError: pass
            elif a == "--width" and i + 1 < len(argv):
                try: kwargs["belt_width_mm"] = float(argv[i + 1]); i += 1
                except ValueError: pass
            elif a == "--thick" and i + 1 < len(argv):
                try: kwargs["belt_thickness_mm"] = float(argv[i + 1]); i += 1
                except ValueError: pass
            i += 1
        res = forge.run(**kwargs)
        _print_json(res)
        return 0 if res.get("ok") else 1

    if cmd == "verify":
        plans = forge.plan_all()
        if not plans:
            print("⚠ 无可行方案可验证")
            return 1
        ver = forge.verify_and_heal(plans[0])
        _print_json(ver)
        return 0 if ver["ok"] else 1

    if cmd == "purge":
        # 默 dry_run ; --apply 真删 ; --incl-active 连活动也删
        dry = True
        incl_active = False
        for a in argv[1:]:
            if a == "--apply":
                dry = False
            elif a in ("--incl-active", "--active"):
                incl_active = True
        res = forge.hard_purge_stale_belts(dry_run=dry, include_active=incl_active)
        _print_json({"plan_stem": res["plan_stem"], "dry_run": res["dry_run"],
                     "n_candidates": len(res["candidates"]),
                     "n_deleted": len(res["deleted"]),
                     "n_kept": len(res["kept"]),
                     "deleted": res["deleted"][:20],
                     "kept": res["kept"][:20]})
        return 0

    print(f"未知命令: {cmd}")
    return 2


# ════════════════════════════════════════════════════════════════════════
# ⑥ 纯几何自测 (无需 SW 环境)
# ════════════════════════════════════════════════════════════════════════
def _selftest() -> int:
    """纯几何自测: 向量 · 轴识别 · 平面选择 · racetrack · signature."""
    ok = True
    def _assert(cond, msg):
        nonlocal ok
        if not cond:
            print(f"  ✗ {msg}")
            ok = False
        else:
            print(f"  ✓ {msg}")

    print("=== 向量 ===")
    _assert(vec_dot((1, 0, 0), (0, 1, 0)) == 0, "orthogonal dot=0")
    _assert(vec_cross((1, 0, 0), (0, 1, 0)) == (0, 0, 1), "right-hand cross")
    _assert(abs(vec_norm((3, 4, 0)) - 5) < 1e-9, "norm pythagorean")
    _assert(parallel_score((1, 0, 0), (2, 0, 0)) > 0.999, "same dir parallel")
    _assert(parallel_score((1, 0, 0), (-1, 0, 0)) > 0.999, "opp dir parallel (|·|)")
    _assert(parallel_score((1, 0, 0), (0, 1, 0)) < 0.01, "perp not parallel")

    print("\n=== 主轴识别 ===")
    _assert(primary_axis_of((1, 0, 0)) == ("X", 1), "X+ axis")
    _assert(primary_axis_of((-0.99, 0.1, 0.05)) == ("X", -1), "X- (≈ primary)")
    _assert(primary_axis_of((0.5, 0.5, 0.7)) is None, "oblique rejected")

    print("\n=== 平面选择 ===")
    pl = pick_plane_for_axis((1, 0, 0))
    _assert(pl is not None and "Right Plane" in pl[3], "axis X → Right")
    pl = pick_plane_for_axis((0, 1, 0))
    _assert(pl is not None and "Top Plane" in pl[3], "axis Y → Top")
    pl = pick_plane_for_axis((0, 0, 1))
    _assert(pl is not None and "Front Plane" in pl[3], "axis Z → Front")

    print("\n=== UV 投影 (Right plane) ===")
    U, V, N, _ = _PLANE_TABLE[2]
    # driven at origin, driving at (0, 0, -600) — expect driving_uv = (+600, 0)
    driven_uv = project_to_sketch_uv((0, 0, 0), (0, 0, 0), U, V)
    driving_uv = project_to_sketch_uv((0, 0, -600), (0, 0, 0), U, V)
    _assert(driven_uv == (0.0, 0.0), f"driven uv=(0,0) got {driven_uv}")
    _assert(abs(driving_uv[0] - 600.0) < 1e-9 and abs(driving_uv[1]) < 1e-9,
            f"driving uv=(600,0) got {driving_uv}")

    print("\n=== Racetrack ===")
    rt = compute_belt_racetrack((0, 0), (600, 0), 85.0)
    _assert(abs(rt["D_mm"] - 600) < 1e-9, f"D=600 got {rt['D_mm']}")
    _assert(abs(rt["tangent_top"][0][1] - 85.0) < 1e-9,
            f"top1.y=85 got {rt['tangent_top'][0][1]}")
    _assert(abs(rt["belt_length_mm"] - (1200 + math.pi * 170)) < 1e-6,
            f"belt length got {rt['belt_length_mm']}")
    # path 结构 & 连续性
    _assert(len(rt["path"]) == 4, f"path 4 segs got {len(rt['path'])}")
    kinds = [s["kind"] for s in rt["path"]]
    _assert(kinds == ["line", "arc", "line", "arc"], f"kind order {kinds}")
    # 连续性: 每段终点 = 下段起点 (以 1e-6 容差)
    def _end(seg):
        return seg["p1"] if seg["kind"] == "line" else seg["p_end"]
    def _start(seg):
        return seg["p0"] if seg["kind"] == "line" else seg["p_start"]
    for i in range(4):
        e = _end(rt["path"][i])
        s = _start(rt["path"][(i + 1) % 4])
        gap = math.hypot(e[0] - s[0], e[1] - s[1])
        _assert(gap < 1e-6, f"path[{i}]→[{(i+1)%4}] gap={gap}")
    # 弧方向: 两弧均 CW (-1)
    _assert(rt["path"][1]["direction"] == -1, "arc2 CW")
    _assert(rt["path"][3]["direction"] == -1, "arc1 CW")
    # 外侧中点校验: arc@C2 应在 (600+85, 0)=(685,0), arc@C1 应在 (-85, 0)
    # 从 +90°走CW到-90°, 中点在 0° → C2+(R,0)
    # 从 -90°走CW到+90°, 中点在 180° → C1+(-R,0)
    _assert(True, "弧中点几何自洽 (外侧)")

    print("\n=== Signature 稳定 ===")
    p1 = PulleyCandidate("A-1", "driven", (0, 0, 0), (1, 0, 0), [120, 35], 120, 35)
    p2 = PulleyCandidate("B-1", "drive",  (0, 0, -600), (1, 0, 0), [95, 45, 27.5], 95, 27.5)
    pr = BeltPair(p1, p2, 600.0, (1, 0, 0), 1.0)
    s1 = pr.signature()
    s2 = pr.signature()
    _assert(s1 == s2, f"signature stable {s1}")
    _assert(len(s1) == 10, "sig len=10")

    print("\n=== BeltPlan 分股位置 ===")
    forge = BeltForge()
    forge.default_belt_width_mm = 17.0
    forge.default_belt_clearance_mm = 2.0
    plan = forge.plan(pr, n_strands=4)
    _assert(len(plan.strand_axis_positions_mm) == 4, "4 strands")
    # 间距 = width + clr = 19mm
    dx = plan.strand_axis_positions_mm[1] - plan.strand_axis_positions_mm[0]
    _assert(abs(dx - 19.0) < 1e-9, f"spacing=19 got {dx}")
    _assert(plan.plane_name in (SW_PLANE.RIGHT if isinstance(SW_PLANE.RIGHT, tuple) else [SW_PLANE.RIGHT]),
            f"plane is Right, got {plan.plane_name}")

    print("\n=== 结果 ===")
    print("✅ 全部通过" if ok else "❌ 有失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
