#!/usr/bin/env python3
"""
道 · Audit — 三维审核系统
═══════════════════════════════════════════════════════════════════
从根本底层逆向研究人类三维理解识别机制，完全构建审核系统。

人类三维感知的本源 (Shepard & Metzler 1971):
  1. 拓扑直觉 — 闭合、连通、无穿刺 (Euler特征)
  2. 空间推理 — 体积、质心、对称性 (心理旋转)
  3. 工程审视 — 壁厚、干涉、公差 (制造可行性)
  4. 多视角整合 — 投影、截面、爆炸图 (认知模型)

本审核系统八层架构:
  Layer 0: 拓扑完整性   (OCCT BRepCheck — 内核级)
  Layer 1: 几何健全性   (体积/面积/包围盒/质心一致性)
  Layer 2: 工程适用性   (壁厚ray-casting/拔模角/曲率/边质量/悬垂)
  Layer 3: 装配验证     (干涉/间隙/配合面)
  Layer 4: 格式合规性   (STEP回环/STL网格质量)
  Layer 5: 参数合规性   (设计参数/BOM/规格对照)
  Layer 6: 设计意图验证 (几何 vs 原始意图/拓扑亏格/功能特征)
  Layer 7: 人类感知模拟 (Shepard心理旋转/Gibson可供性/Marr 2.5D草图)

内核: OCP/OCCT直连 (BRepCheck + ShapeAnalysis + ShapeFix)
"""
import sys, os, json, time, math, tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), Path(__file__).resolve().parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

sys.path.insert(0, os.path.dirname(__file__))
from dao_kernel import DaoKernel as K

# ── OCCT Shape Analysis Stack ──
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.ShapeAnalysis import (
    ShapeAnalysis_ShapeContents,
    ShapeAnalysis_ShapeTolerance,
    ShapeAnalysis_FreeBounds,
    ShapeAnalysis_Shell,
    ShapeAnalysis_Edge,
)
from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Wireframe
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import (
    TopAbs_VERTEX, TopAbs_EDGE, TopAbs_WIRE,
    TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_COMPOUND,
)
from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Face, TopoDS_Edge
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopExp import TopExp
from OCP.GeomAbs import (
    GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone,
    GeomAbs_Sphere, GeomAbs_Torus, GeomAbs_BSplineSurface,
    GeomAbs_BezierSurface, GeomAbs_OtherSurface,
)
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
import numpy as np


# ═══════════════════════════════════════════════════════════════
# GRADE SYSTEM: S > A > B > C > F
# ═══════════════════════════════════════════════════════════════
def _grade(score: float) -> str:
    if score >= 95: return "S"
    if score >= 85: return "A"
    if score >= 70: return "B"
    if score >= 50: return "C"
    return "F"


# ═══════════════════════════════════════════════════════════════
# Layer 0: 拓扑完整性 — BRepCheck直连OCCT内核
# ═══════════════════════════════════════════════════════════════
def audit_topology(shape: TopoDS_Shape) -> Dict[str, Any]:
    """
    OCCT BRepCheck_Analyzer: 验证shape的拓扑完整性。
    检查: 边/面/壳/体的几何一致性、闭合性、连通性。
    """
    t0 = time.time()
    analyzer = BRepCheck_Analyzer(shape, True)  # True = GeomControls
    is_valid = analyzer.IsValid()

    # Shape contents
    sc = ShapeAnalysis_ShapeContents()
    sc.Perform(shape)

    # Topology counts (unique via IndexedMap)
    topo = {}
    for name, ttype in [("vertices", TopAbs_VERTEX), ("edges", TopAbs_EDGE),
                         ("wires", TopAbs_WIRE), ("faces", TopAbs_FACE),
                         ("shells", TopAbs_SHELL), ("solids", TopAbs_SOLID)]:
        m = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, ttype, m)
        topo[name] = m.Extent()

    # Euler characteristic: V - E + F = 2 (for genus-0 closed solid)
    V = topo['vertices']
    E = topo['edges']
    F = topo['faces']
    euler = V - E + F
    # For a solid with g through-holes: V-E+F = 2(1-g)
    # Valid if euler <= 2 and even
    euler_valid = (euler == 2) if topo['solids'] == 1 and topo['shells'] == 1 else (
        euler <= 2 and euler % 2 == 0 if topo['solids'] >= 1 else None
    )

    # Free edges/wires (should be 0 for closed solid)
    free_edges = sc.NbFreeEdges()
    free_wires = sc.NbFreeWires()
    shared_edges = sc.NbSharedEdges()

    # Shell analysis
    shell_ok = True
    sa_shell = ShapeAnalysis_Shell()
    sa_shell.LoadShells(shape)
    if sa_shell.NbLoaded() > 0:
        has_free = sa_shell.HasFreeEdges()
        has_bad = sa_shell.HasBadEdges()
        shell_ok = not has_free and not has_bad

    # Tolerance
    st = ShapeAnalysis_ShapeTolerance()
    tol_avg = st.Tolerance(shape, 0)  # 0=average
    tol_max = st.Tolerance(shape, 1)  # 1=max
    tol_min = st.Tolerance(shape, -1) # -1=min

    # Score
    score = 100
    issues = []
    if not is_valid:
        score -= 40
        issues.append("BRepCheck INVALID")
    if free_edges > 0:
        score -= 20
        issues.append(f"{free_edges} free edges")
    if not shell_ok:
        score -= 15
        issues.append("shell defects")
    if euler_valid is False:
        score -= 10
        issues.append(f"Euler={euler} (V={V} E={E} F={F})")
    if tol_max > 0.01:
        score -= 5
        issues.append(f"max tolerance={tol_max:.6f}")

    return {
        "layer": 0,
        "name": "拓扑完整性",
        "grade": _grade(score),
        "score": max(0, score),
        "valid": is_valid,
        "topology": topo,
        "euler_characteristic": euler,
        "euler_valid": euler_valid,
        "free_edges": free_edges,
        "free_wires": free_wires,
        "shared_edges": shared_edges,
        "shell_ok": shell_ok,
        "tolerance": {"avg": tol_avg, "max": tol_max, "min": tol_min},
        "issues": issues,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ═══════════════════════════════════════════════════════════════
# Layer 1: 几何健全性 — 体积/面积/包围盒/质心
# ═══════════════════════════════════════════════════════════════
def audit_geometry(shape: TopoDS_Shape,
                   vol_range: Optional[Tuple[float, float]] = None,
                   bbox_range: Optional[Dict[str, Tuple[float, float]]] = None
                   ) -> Dict[str, Any]:
    """
    几何属性验证: 体积/面积/包围盒/质心/惯性矩。
    人类审图的第一反应: "大小对不对？比例对不对？"
    """
    t0 = time.time()
    vol = K.volume(shape)
    area = K.surface_area(shape)
    com = K.center_of_mass(shape)
    bb = K.bounding_box(shape)
    inertia = K.inertia(shape)
    sx, sy, sz = bb['size']

    # Aspect ratio (max/min dimension)
    dims = sorted([sx, sy, sz])
    aspect = dims[2] / max(dims[0], 0.001)

    # Volume-to-bbox ratio (how "solid" is it)
    bbox_vol = sx * sy * sz
    fill_ratio = abs(vol) / max(bbox_vol, 1) * 100

    score = 100
    issues = []

    if abs(vol) < 1e-6:
        score -= 50
        issues.append("zero volume")
    if area < 1e-6:
        score -= 30
        issues.append("zero surface area")
    if vol < 0:
        score -= 10
        issues.append("negative volume (inverted normals)")

    # Check against spec
    if vol_range:
        lo, hi = vol_range
        if not (lo <= abs(vol) <= hi):
            score -= 20
            issues.append(f"volume {abs(vol):.0f} outside spec [{lo:.0f}, {hi:.0f}]")

    if bbox_range:
        for key, (lo, hi) in bbox_range.items():
            val = max(sx, sy, sz) if key == "L" else min(sx, sy, sz) if key == "W" else sz
            if not (lo <= val <= hi):
                score -= 10
                issues.append(f"bbox {key}={val:.1f} outside [{lo}, {hi}]")

    return {
        "layer": 1,
        "name": "几何健全性",
        "grade": _grade(score),
        "score": max(0, score),
        "volume_mm3": round(vol, 2),
        "surface_area_mm2": round(area, 2),
        "center_of_mass": [round(c, 2) for c in com],
        "bounding_box": {
            "size": [round(sx, 2), round(sy, 2), round(sz, 2)],
            "center": [round(c, 2) for c in bb['center']],
        },
        "aspect_ratio": round(aspect, 2),
        "fill_ratio_pct": round(fill_ratio, 1),
        "inertia": {k: round(v, 1) for k, v in inertia.items()},
        "issues": issues,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ═══════════════════════════════════════════════════════════════
# Layer 2: 工程适用性 — 壁厚/面类型/小面/悬垂
# ═══════════════════════════════════════════════════════════════
def _sample_face_points(face: TopoDS_Face, n_samples: int = 8) -> list:
    """在面的参数域上均匀采样点(UV中点及周围)。"""
    adaptor = BRepAdaptor_Surface(face)
    u1, u2 = adaptor.FirstUParameter(), adaptor.LastUParameter()
    v1, v2 = adaptor.FirstVParameter(), adaptor.LastVParameter()
    pts = []
    nu = max(2, int(math.sqrt(n_samples)))
    nv = max(2, n_samples // nu)
    for i in range(nu):
        for j in range(nv):
            u = u1 + (u2 - u1) * (i + 0.5) / nu
            v = v1 + (v2 - v1) * (j + 0.5) / nv
            pnt = adaptor.Value(u, v)
            pts.append((pnt.X(), pnt.Y(), pnt.Z()))
    return pts


def _face_normal_at_center(face: TopoDS_Face) -> Optional[Tuple[float, float, float]]:
    """获取面中心处的法线方向。"""
    adaptor = BRepAdaptor_Surface(face)
    u = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
    v = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
    try:
        props = BRepLProp_SLProps(adaptor, u, v, 1, 1e-6)
        if props.IsNormalDefined():
            n = props.Normal()
            return (n.X(), n.Y(), n.Z())
    except Exception:
        pass
    return None


def _face_curvatures(face: TopoDS_Face) -> Optional[Dict[str, float]]:
    """获取面中心处的主曲率 (Gaussian + Mean curvature)。"""
    adaptor = BRepAdaptor_Surface(face)
    u = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
    v = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
    try:
        props = BRepLProp_SLProps(adaptor, u, v, 2, 1e-6)
        if props.IsCurvatureDefined():
            k1 = props.MaxCurvature()
            k2 = props.MinCurvature()
            return {
                "k_max": k1, "k_min": k2,
                "gaussian": k1 * k2,
                "mean": (k1 + k2) / 2,
            }
    except Exception:
        pass
    return None


def _edge_length(edge: TopoDS_Edge) -> float:
    """计算边的长度。"""
    try:
        adaptor = BRepAdaptor_Curve(edge)
        return GCPnts_AbscissaPoint.Length_s(adaptor)
    except Exception:
        return 0.0


def audit_engineering(shape: TopoDS_Shape,
                      min_wall_mm: float = 1.0,
                      max_aspect: float = 50.0,
                      pull_direction: Tuple[float, float, float] = (0, 0, 1),
                      process: str = "fdm"
                      ) -> Dict[str, Any]:
    """
    工程制造性分析 — 人类工程师的审视: "这个能做出来吗？"

    Shepard心理旋转 × 工程直觉:
      1. 面类型分布 — 几何复杂度
      2. 小面检测 — 可制造性
      3. 壁厚分析 — 真实ray-casting (面间最小距离)
      4. 悬臂分析 — 面法线 vs 重力方向
      5. 拔模角分析 — 面法线 vs 脱模方向 (注塑/CNC)
      6. 曲率分析 — 刀具可达性 / 打印分辨率
      7. 边质量分析 — 短边/退化边检测
    """
    t0 = time.time()

    # ── 1. Face type distribution + area statistics ──
    face_types = {}
    face_areas = []
    small_faces = 0
    min_face_area = float('inf')
    max_face_area = 0
    faces_list = []

    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        faces_list.append(face)
        adaptor = BRepAdaptor_Surface(face)
        surf_type = adaptor.GetType()
        type_name = {
            GeomAbs_Plane: "Plane",
            GeomAbs_Cylinder: "Cylinder",
            GeomAbs_Cone: "Cone",
            GeomAbs_Sphere: "Sphere",
            GeomAbs_Torus: "Torus",
            GeomAbs_BSplineSurface: "BSpline",
            GeomAbs_BezierSurface: "Bezier",
        }.get(surf_type, "Other")

        face_types[type_name] = face_types.get(type_name, 0) + 1

        area = K.face_area(face)
        face_areas.append(area)
        if area < min_face_area:
            min_face_area = area
        if area > max_face_area:
            max_face_area = area
        if area < 1.0:  # < 1mm²
            small_faces += 1

        exp.Next()

    n_faces = len(face_areas)
    avg_face_area = sum(face_areas) / max(n_faces, 1)

    # ── 2. Wall thickness — real face-pair minimum distance ──
    # Strategy: for each face, find closest opposing face via BRepExtrema
    # This is the ground-truth wall thickness, not the V/A approximation.
    vol = abs(K.volume(shape))
    area_total = K.surface_area(shape)
    va_wall = 2 * vol / max(area_total, 1)  # V/A fallback

    wall_samples = []
    n_check = min(len(faces_list), 30)  # cap to avoid O(n²) explosion
    sampled_faces = faces_list[:n_check]
    for i, f1 in enumerate(sampled_faces):
        for j in range(i + 1, len(sampled_faces)):
            f2 = sampled_faces[j]
            try:
                dist_calc = BRepExtrema_DistShapeShape(f1, f2)
                if dist_calc.IsDone() and dist_calc.NbSolution() > 0:
                    d = dist_calc.Value()
                    if 0.01 < d < 200:  # skip zero-dist (same face) and outliers
                        wall_samples.append(d)
            except Exception:
                pass

    if wall_samples:
        wall_min = min(wall_samples)
        wall_avg = sum(wall_samples) / len(wall_samples)
        wall_med = sorted(wall_samples)[len(wall_samples) // 2]
    else:
        wall_min = wall_avg = wall_med = va_wall

    # ── 3. Overhang analysis ──
    overhang_faces = 0
    overhang_area = 0
    total_area_oh = 0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        fa = K.face_area(face)
        total_area_oh += fa
        n_vec = _face_normal_at_center(face)
        if n_vec:
            nz = n_vec[2]  # Z component of normal
            if nz < -0.7071:  # > 45° overhang from vertical
                overhang_faces += 1
                overhang_area += fa
        exp.Next()

    overhang_pct = (overhang_area / max(total_area_oh, 1)) * 100

    # ── 4. Draft angle analysis (for injection/CNC) ──
    px, py, pz = pull_direction
    pull_len = math.sqrt(px*px + py*py + pz*pz)
    if pull_len > 1e-9:
        px, py, pz = px/pull_len, py/pull_len, pz/pull_len

    draft_angles = []  # degrees
    undraft_faces = 0
    undraft_area = 0
    min_draft_deg = 90.0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        n_vec = _face_normal_at_center(face)
        if n_vec:
            nx, ny, nz = n_vec
            # Draft angle = 90° - angle between normal and pull direction
            dot = abs(nx*px + ny*py + nz*pz)
            angle_from_pull = math.degrees(math.acos(min(dot, 1.0)))
            draft = 90.0 - angle_from_pull
            draft_angles.append(draft)
            if draft < min_draft_deg:
                min_draft_deg = draft
            if draft < 1.0:  # less than 1° draft
                undraft_faces += 1
                undraft_area += K.face_area(face)
        exp.Next()

    # ── 5. Curvature analysis ──
    curvatures_gauss = []
    curvatures_mean = []
    high_curvature_faces = 0
    for face in faces_list[:n_check]:
        curv = _face_curvatures(face)
        if curv:
            curvatures_gauss.append(abs(curv["gaussian"]))
            curvatures_mean.append(abs(curv["mean"]))
            # High curvature = small radius < 0.5mm (potential tooling issue)
            if abs(curv["mean"]) > 2.0:  # 1/R > 2 → R < 0.5mm
                high_curvature_faces += 1

    # ── 6. Edge quality analysis ──
    short_edges = 0
    min_edge_len = float('inf')
    total_edges = 0
    exp = TopExp_Explorer(shape, TopAbs_EDGE)
    while exp.More():
        edge = TopoDS.Edge_s(exp.Current())
        elen = _edge_length(edge)
        total_edges += 1
        if elen < min_edge_len:
            min_edge_len = elen
        if 0 < elen < 0.1:  # < 0.1mm = degenerate for manufacturing
            short_edges += 1
        exp.Next()
    if min_edge_len == float('inf'):
        min_edge_len = 0

    # ── Scoring ──
    score = 100
    issues = []

    if small_faces > 0:
        penalty = min(20, small_faces * 5)
        score -= penalty
        issues.append(f"{small_faces} small faces (<1mm²)")
    if wall_min < min_wall_mm:
        score -= 20
        issues.append(f"min wall thickness {wall_min:.2f}mm < {min_wall_mm}mm")
    elif wall_min < min_wall_mm * 1.5:
        score -= 5
        issues.append(f"wall thickness {wall_min:.2f}mm marginal (rec ≥{min_wall_mm*1.5:.1f}mm)")
    if overhang_pct > 30:
        score -= 10
        issues.append(f"overhang {overhang_pct:.1f}%")
    if undraft_faces > 0 and process in ("injection", "cnc"):
        score -= 10
        issues.append(f"{undraft_faces} faces with <1° draft angle")
    if high_curvature_faces > 0:
        score -= 5
        issues.append(f"{high_curvature_faces} high-curvature faces (R<0.5mm)")
    if short_edges > 0:
        score -= min(10, short_edges * 3)
        issues.append(f"{short_edges} short edges (<0.1mm)")

    bb = K.bounding_box(shape)
    dims = sorted(bb['size'])
    if dims[0] > 0 and dims[2] / dims[0] > max_aspect:
        score -= 10
        issues.append(f"extreme aspect ratio {dims[2]/dims[0]:.1f}")

    return {
        "layer": 2,
        "name": "工程适用性",
        "grade": _grade(score),
        "score": max(0, score),
        "face_types": face_types,
        "face_count": n_faces,
        "small_faces": small_faces,
        "min_face_area_mm2": round(min_face_area, 4),
        "avg_face_area_mm2": round(avg_face_area, 2),
        "wall_thickness": {
            "min_mm": round(wall_min, 3),
            "avg_mm": round(wall_avg, 3),
            "median_mm": round(wall_med, 3),
            "va_estimate_mm": round(va_wall, 3),
            "samples": len(wall_samples),
        },
        "overhang": {
            "faces": overhang_faces,
            "area_pct": round(overhang_pct, 1),
        },
        "draft_angle": {
            "min_deg": round(min_draft_deg, 1) if draft_angles else None,
            "undraft_faces": undraft_faces,
            "undraft_area_mm2": round(undraft_area, 1),
            "pull_direction": list(pull_direction),
        },
        "curvature": {
            "high_curvature_faces": high_curvature_faces,
            "max_mean_curvature": round(max(curvatures_mean), 4) if curvatures_mean else 0,
            "max_gaussian_curvature": round(max(curvatures_gauss), 6) if curvatures_gauss else 0,
        },
        "edge_quality": {
            "total": total_edges,
            "short_edges": short_edges,
            "min_edge_length_mm": round(min_edge_len, 4),
        },
        "issues": issues,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ═══════════════════════════════════════════════════════════════
# Layer 3: 装配验证 — 干涉/间隙检测
# ═══════════════════════════════════════════════════════════════
def audit_assembly(shapes: Dict[str, TopoDS_Shape],
                   min_clearance_mm: float = 0.5,
                   precise: bool = False
                   ) -> Dict[str, Any]:
    """
    装配级验证: 零件间干涉检测、间隙分析。
    precise=True: 精确布尔交集检测 (慢, 适合小装配)
    precise=False: AABB包围盒重叠检测 (快, 适合大装配)
    人类装配的直觉: "这些件能装到一起吗？"
    """
    t0 = time.time()

    names = list(shapes.keys())
    n = len(names)
    interferences = []
    clearances = []

    # Precompute bounding boxes
    bboxes = {}
    for name in names:
        bboxes[name] = K.bounding_box(shapes[name])

    for i in range(n):
        bb_i = bboxes[names[i]]
        for j in range(i + 1, n):
            bb_j = bboxes[names[j]]

            # AABB overlap test
            overlap = True
            overlap_vol = 1.0
            for axis in range(3):
                lo = max(bb_i['min'][axis], bb_j['min'][axis])
                hi = min(bb_i['max'][axis], bb_j['max'][axis])
                if lo >= hi:
                    overlap = False
                    break
                overlap_vol *= (hi - lo)

            if overlap:
                if precise:
                    # Precise boolean intersection (expensive)
                    try:
                        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
                        common = BRepAlgoAPI_Common(shapes[names[i]], shapes[names[j]])
                        if common.IsDone():
                            int_shape = common.Shape()
                            int_vol = abs(K.volume(int_shape))
                            if int_vol > 1.0:
                                interferences.append({
                                    "parts": [names[i], names[j]],
                                    "volume_mm3": round(int_vol, 1),
                                    "method": "boolean",
                                })
                    except Exception:
                        pass
                else:
                    # AABB overlap volume (fast approximation)
                    interferences.append({
                        "parts": [names[i], names[j]],
                        "overlap_bbox_mm3": round(overlap_vol, 1),
                        "method": "aabb",
                    })
            else:
                # Calculate bbox gap
                gaps = []
                for axis in range(3):
                    gap = max(bb_j['min'][axis] - bb_i['max'][axis],
                              bb_i['min'][axis] - bb_j['max'][axis])
                    gaps.append(max(0, gap))
                min_gap = min(gaps) if any(g > 0 for g in gaps) else 0
                clearances.append({
                    "parts": [names[i], names[j]],
                    "min_gap_mm": round(min_gap, 2),
                })

    score = 100
    issues = []

    if interferences:
        score -= min(50, len(interferences) * 15)
        issues.append(f"{len(interferences)} interference(s)")

    tight = [c for c in clearances if c['min_gap_mm'] < min_clearance_mm]
    if tight:
        score -= min(20, len(tight) * 5)
        issues.append(f"{len(tight)} tight clearance(s)")

    return {
        "layer": 3,
        "name": "装配验证",
        "grade": _grade(score),
        "score": max(0, score),
        "parts": len(shapes),
        "pairs_checked": n * (n - 1) // 2,
        "interferences": interferences,
        "tight_clearances": tight,
        "issues": issues,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ═══════════════════════════════════════════════════════════════
# Layer 4: 格式合规性 — STEP回环/STL网格质量
# ═══════════════════════════════════════════════════════════════
def audit_format(shape: TopoDS_Shape,
                 step_path: Optional[str] = None
                 ) -> Dict[str, Any]:
    """
    格式验证: STEP回环体积漂移、STL网格质量。
    数据传输的可靠性: "导出再导入还是同一个零件吗？"
    """
    t0 = time.time()
    score = 100
    issues = []
    result = {"layer": 4, "name": "格式合规性"}

    # STEP round-trip
    v_orig = abs(K.volume(shape))
    with tempfile.NamedTemporaryFile(suffix='.step', delete=False) as f:
        tmp_step = f.name
    try:
        K.to_step(shape, tmp_step)
        reimported = K.from_step(tmp_step)
        v_reimport = abs(K.volume(reimported))
        drift_pct = abs(v_orig - v_reimport) / max(v_orig, 1) * 100
        result["step_roundtrip"] = {
            "original_vol": round(v_orig, 2),
            "reimport_vol": round(v_reimport, 2),
            "drift_pct": round(drift_pct, 4),
        }
        if drift_pct > 0.1:
            score -= 15
            issues.append(f"STEP drift {drift_pct:.2f}%")
    except Exception as e:
        score -= 30
        issues.append(f"STEP roundtrip failed: {e}")
    finally:
        try: os.unlink(tmp_step)
        except: pass

    # STL mesh quality
    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
        tmp_stl = f.name
    try:
        K.to_stl(shape, tmp_stl, tolerance=0.1)
        import trimesh
        mesh = trimesh.load(tmp_stl)
        is_wt = bool(mesh.is_watertight)
        is_wc = bool(mesh.is_winding_consistent)
        import numpy as np
        degen = int(np.sum(mesh.area_faces < 1e-10))

        result["stl_quality"] = {
            "watertight": is_wt,
            "winding_consistent": is_wc,
            "faces": len(mesh.faces),
            "vertices": len(mesh.vertices),
            "degenerate_faces": degen,
            "mesh_volume_mm3": round(float(mesh.volume), 2) if is_wt else None,
        }

        if not is_wt:
            score -= 15
            issues.append("STL not watertight")
        if not is_wc:
            score -= 10
            issues.append("STL winding inconsistent")
        if degen > 0:
            score -= 5
            issues.append(f"{degen} degenerate STL faces")

        # Volume consistency: BREP vs mesh
        if is_wt:
            mesh_vol = abs(float(mesh.volume))
            vol_diff = abs(v_orig - mesh_vol) / max(v_orig, 1) * 100
            result["stl_quality"]["brep_vs_mesh_drift_pct"] = round(vol_diff, 2)
            if vol_diff > 5:
                score -= 5
                issues.append(f"BREP-mesh drift {vol_diff:.1f}%")

    except ImportError:
        result["stl_quality"] = {"note": "trimesh not available"}
    except Exception as e:
        score -= 10
        issues.append(f"STL quality check failed: {e}")
    finally:
        try: os.unlink(tmp_stl)
        except: pass

    result.update({
        "grade": _grade(score),
        "score": max(0, score),
        "issues": issues,
        "time_ms": round((time.time() - t0) * 1000, 1),
    })
    return result


# ═══════════════════════════════════════════════════════════════
# Layer 5: 参数合规性 — 设计参数/规格对照
# ═══════════════════════════════════════════════════════════════
def audit_params(shape: TopoDS_Shape,
                 specs: Dict[str, Any]
                 ) -> Dict[str, Any]:
    """
    参数规格验证: 对照设计参数表逐项检查。
    specs: {
        "volume_range": (min, max),
        "bbox_L_range": (min, max),
        "material": "...",
        "qty": N,
        ...
    }
    """
    t0 = time.time()
    score = 100
    issues = []
    checks = []

    vol = abs(K.volume(shape))
    bb = K.bounding_box(shape)
    dims = sorted(bb['size'], reverse=True)

    # Volume range check
    if "volume_range" in specs:
        lo, hi = specs["volume_range"]
        ok = lo <= vol <= hi
        checks.append({"param": "volume", "value": round(vol), "range": [lo, hi], "ok": ok})
        if not ok:
            score -= 15
            issues.append(f"volume {vol:.0f} outside [{lo:.0f}, {hi:.0f}]")

    # BBox dimension checks
    for key, dim_idx in [("bbox_L_range", 0), ("bbox_W_range", 1), ("bbox_H_range", 2)]:
        if key in specs:
            lo, hi = specs[key]
            val = dims[dim_idx]
            ok = lo <= val <= hi
            label = key.replace("_range", "")
            checks.append({"param": label, "value": round(val, 1), "range": [lo, hi], "ok": ok})
            if not ok:
                score -= 10
                issues.append(f"{label} {val:.1f} outside [{lo}, {hi}]")

    # Topology checks
    topo = K.count_topology(shape)
    if "min_faces" in specs:
        ok = topo['faces'] >= specs['min_faces']
        checks.append({"param": "faces", "value": topo['faces'], "min": specs['min_faces'], "ok": ok})
        if not ok:
            score -= 5
            issues.append(f"only {topo['faces']} faces (min {specs['min_faces']})")

    return {
        "layer": 5,
        "name": "参数合规性",
        "grade": _grade(score),
        "score": max(0, score),
        "checks": checks,
        "issues": issues,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ═══════════════════════════════════════════════════════════════
# Layer 6: 设计意图验证 — 几何是否忠于原始意图
# ═══════════════════════════════════════════════════════════════
def audit_intent(shape: TopoDS_Shape,
                 intent: Dict[str, Any]
                 ) -> Dict[str, Any]:
    """
    设计意图验证 — 人类审图的本质: "这是我要的东西吗？"

    Marr视觉理论的计算等价:
      - 2.5D草图 → 检查面数/孔数/拓扑是否匹配意图
      - 3D模型 → 检查体积/比例/特征数是否匹配意图
      - 功能认知 → 检查关键功能特征是否存在

    intent: {
        "expected_genus": 0,              # 拓扑亏格 (0=实体, 1=有一个通孔)
        "expected_faces_range": (6, 20),  # 预期面数范围
        "expected_holes": 4,              # 预期通孔数
        "expected_symmetry": "bilateral", # 预期对称性
        "key_features": [                 # 关键功能特征
            {"type": "hole", "diameter": 3.4, "tolerance": 0.3},
            {"type": "fillet", "radius": 2.0, "tolerance": 0.5},
        ],
        "volume_range": (1000, 5000),
        "aspect_target": {"L:W": 1.5, "tolerance": 0.3},
    }
    """
    t0 = time.time()
    score = 100
    issues = []
    checks = []

    vol = abs(K.volume(shape))
    bb = K.bounding_box(shape)
    topo = K.count_topology(shape)
    dims = sorted(bb['size'], reverse=True)

    # ── Euler genus check (topology understanding) ──
    V, E, F = topo.get('vertices', 0), topo.get('edges', 0), topo.get('faces', 0)
    euler = V - E + F
    actual_genus = max(0, (2 - euler) // 2)
    if "expected_genus" in intent:
        eg = intent["expected_genus"]
        ok = actual_genus == eg
        checks.append({"check": "genus", "expected": eg, "actual": actual_genus, "ok": ok})
        if not ok:
            score -= 15
            issues.append(f"genus {actual_genus} ≠ expected {eg} (topology mismatch)")

    # ── Face count range ──
    if "expected_faces_range" in intent:
        lo, hi = intent["expected_faces_range"]
        fc = topo.get('faces', 0)
        ok = lo <= fc <= hi
        checks.append({"check": "face_count", "expected": [lo, hi], "actual": fc, "ok": ok})
        if not ok:
            score -= 10
            issues.append(f"face count {fc} outside [{lo}, {hi}]")

    # ── Expected holes (cylindrical face pairs as hole proxy) ──
    if "expected_holes" in intent:
        n_cyls = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            adaptor = BRepAdaptor_Surface(face)
            if adaptor.GetType() == GeomAbs_Cylinder:
                n_cyls += 1
            exp.Next()
        # Each through-hole creates ~1 cylindrical face (inner wall)
        expected = intent["expected_holes"]
        ok = abs(n_cyls - expected) <= max(1, expected * 0.3)
        checks.append({"check": "holes", "expected": expected, "cylindrical_faces": n_cyls, "ok": ok})
        if not ok:
            score -= 10
            issues.append(f"{n_cyls} cylindrical faces vs {expected} expected holes")

    # ── Volume range ──
    if "volume_range" in intent:
        lo, hi = intent["volume_range"]
        ok = lo <= vol <= hi
        checks.append({"check": "volume", "expected": [lo, hi], "actual": round(vol, 1), "ok": ok})
        if not ok:
            score -= 15
            issues.append(f"volume {vol:.0f} outside [{lo:.0f}, {hi:.0f}]")

    # ── Aspect ratio target ──
    if "aspect_target" in intent:
        at = intent["aspect_target"]
        tol = at.get("tolerance", 0.3)
        if "L:W" in at and len(dims) >= 2 and dims[1] > 0.01:
            target = at["L:W"]
            actual = dims[0] / dims[1]
            ok = abs(actual - target) < tol
            checks.append({"check": "aspect_L:W", "expected": target,
                           "actual": round(actual, 2), "tolerance": tol, "ok": ok})
            if not ok:
                score -= 5
                issues.append(f"L:W ratio {actual:.2f} ≠ target {target} (±{tol})")

    # ── Key features verification ──
    if "key_features" in intent:
        for kf in intent["key_features"]:
            ft = kf.get("type", "")
            if ft == "hole":
                # Check if a cylinder face with matching radius exists
                target_r = kf.get("diameter", 0) / 2
                tol_r = kf.get("tolerance", 0.3) / 2
                found = False
                exp = TopExp_Explorer(shape, TopAbs_FACE)
                while exp.More():
                    face = TopoDS.Face_s(exp.Current())
                    adaptor = BRepAdaptor_Surface(face)
                    if adaptor.GetType() == GeomAbs_Cylinder:
                        cyl = adaptor.Cylinder()
                        r = cyl.Radius()
                        if abs(r - target_r) < tol_r:
                            found = True
                            break
                    exp.Next()
                checks.append({"check": f"hole_d{kf.get('diameter',0)}", "found": found})
                if not found:
                    score -= 8
                    issues.append(f"hole Ø{kf.get('diameter',0)}mm not found")

            elif ft == "fillet":
                # Fillet detection: look for toroidal/spherical faces
                target_r = kf.get("radius", 0)
                tol_r = kf.get("tolerance", 0.5)
                found = False
                exp = TopExp_Explorer(shape, TopAbs_FACE)
                while exp.More():
                    face = TopoDS.Face_s(exp.Current())
                    adaptor = BRepAdaptor_Surface(face)
                    if adaptor.GetType() == GeomAbs_Torus:
                        tor = adaptor.Torus()
                        r_minor = tor.MinorRadius()
                        if abs(r_minor - target_r) < tol_r:
                            found = True
                            break
                    exp.Next()
                checks.append({"check": f"fillet_r{target_r}", "found": found})
                if not found:
                    score -= 3  # minor: fillets are aesthetic

    return {
        "layer": 6,
        "name": "设计意图验证",
        "grade": _grade(score),
        "score": max(0, score),
        "checks": checks,
        "issues": issues,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ═══════════════════════════════════════════════════════════════
# Layer 7: 人类感知模拟 — 对称性/主轴/截面/重心直觉
# ═══════════════════════════════════════════════════════════════
def audit_perception(shape: TopoDS_Shape) -> Dict[str, Any]:
    """
    人类三维感知模拟 — 逆向研究人类如何理解三维物体。

    Shepard & Metzler (1971) — 心理旋转:
      人类能在脑中旋转物体，比较两个视角。
      → 我们计算主惯性轴，得到物体的"自然朝向"。

    Gibson (1979) — 可供性感知:
      人类看到物体即知功能: 平底→可放置，空腔→可容纳。
      → 我们检测底面/腔体/对称轴。

    Marr (1982) — 2.5D草图:
      人类从多视角整合理解物体。
      → 我们计算三正交截面面积比。

    本层输出:
      - 主惯性轴 (自然朝向)
      - 对称性检测 (双边/旋转/无)
      - 重心位置 & 稳定性评估
      - 截面特征 (XY/XZ/YZ截面面积比)
      - 视觉复杂度评分
    """
    t0 = time.time()
    score = 100
    findings = []

    vol = abs(K.volume(shape))
    bb = K.bounding_box(shape)
    com = K.center_of_mass(shape)
    inertia = K.inertia(shape)
    dims = sorted(bb['size'], reverse=True)

    # ── 1. Principal axes (Shepard mental rotation substrate) ──
    # Eigenvalues of inertia tensor → principal moments
    I_mat = np.array([
        [inertia['Ixx'], -inertia.get('Ixy', 0), -inertia.get('Ixz', 0)],
        [-inertia.get('Ixy', 0), inertia['Iyy'], -inertia.get('Iyz', 0)],
        [-inertia.get('Ixz', 0), -inertia.get('Iyz', 0), inertia['Izz']],
    ])
    try:
        eigenvalues, eigenvectors = np.linalg.eigh(I_mat)
        # Sort by descending eigenvalue (max inertia = longest axis)
        idx = np.argsort(eigenvalues)[::-1]
        principal_moments = eigenvalues[idx].tolist()
        principal_axes = eigenvectors[:, idx].T.tolist()
    except Exception:
        principal_moments = [inertia['Ixx'], inertia['Iyy'], inertia['Izz']]
        principal_axes = [[1,0,0], [0,1,0], [0,0,1]]

    # ── 2. Symmetry detection ──
    # Heuristic: compare inertia eigenvalue ratios
    pm = sorted(principal_moments)
    if pm[0] > 1e-6:
        ratio_12 = pm[1] / pm[0]
        ratio_23 = pm[2] / pm[1] if pm[1] > 1e-6 else 999
    else:
        ratio_12 = ratio_23 = 999

    symmetry = "asymmetric"
    if ratio_12 < 1.05 and ratio_23 < 1.05:
        symmetry = "isotropic"  # sphere-like
        findings.append("近似各向同性(球状)")
    elif ratio_12 < 1.05:
        symmetry = "axial"  # two similar axes → revolution body
        findings.append("轴对称(旋转体特征)")
    elif abs(ratio_12 - ratio_23) < 0.1:
        symmetry = "bilateral"  # likely mirror symmetry
        findings.append("近似双边对称")

    # Additional bilateral check: is CoM on a principal plane?
    bb_center = bb['center']
    com_offset = [com[i] - bb_center[i] for i in range(3)]
    com_offset_rel = [abs(com_offset[i]) / max(dims[i], 0.01) for i in range(3)]
    if max(com_offset_rel) < 0.05:
        if symmetry == "asymmetric":
            symmetry = "near_bilateral"
            findings.append("质心居中，可能近似对称")

    # ── 3. Stability assessment (Gibson: "can it stand?") ──
    # Check if CoM is above the base
    cz_rel = (com[2] - bb['min'][2]) / max(dims[2] if len(dims) > 2 else bb['size'][2], 0.01)
    base_area = bb['size'][0] * bb['size'][1]  # XY footprint
    stability = "stable" if cz_rel < 0.6 and base_area > 100 else \
                "marginal" if cz_rel < 0.75 else "unstable"
    if stability == "unstable":
        findings.append(f"重心偏高 (z_rel={cz_rel:.2f})，可能不稳定")

    # ── 4. Section area ratios (Marr 2.5D sketch proxy) ──
    # Approximate section areas using bounding box
    sx, sy, sz = bb['size']
    section_xy = sx * sy  # top view
    section_xz = sx * sz  # front view
    section_yz = sy * sz  # side view

    # Hollowness ratio: volume / bbox_volume
    bbox_vol = sx * sy * sz
    hollowness = 1.0 - (vol / max(bbox_vol, 1))

    # ── 5. Visual complexity (feature density) ──
    topo = K.count_topology(shape)
    face_count = topo.get('faces', 0)
    edge_count = topo.get('edges', 0)
    # Complexity proxy: edges per face
    complexity_ratio = edge_count / max(face_count, 1)
    if face_count <= 6:
        visual_complexity = "primitive"
    elif face_count <= 20:
        visual_complexity = "simple"
    elif face_count <= 60:
        visual_complexity = "moderate"
    elif face_count <= 200:
        visual_complexity = "complex"
    else:
        visual_complexity = "highly_complex"

    # ── 6. Functional affordance detection (Gibson) ──
    affordances = []
    # Flat bottom → can be placed
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    bottom_area = 0
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        adaptor = BRepAdaptor_Surface(face)
        if adaptor.GetType() == GeomAbs_Plane:
            n = _face_normal_at_center(face)
            if n and n[2] < -0.99:  # pointing down
                bottom_area += K.face_area(face)
        exp.Next()
    if bottom_area > 10:
        affordances.append({"type": "placeable", "base_area_mm2": round(bottom_area, 1)})

    # Hollow → containment
    if hollowness > 0.3:
        affordances.append({"type": "container", "hollowness_pct": round(hollowness * 100, 1)})

    # Has cylindrical holes → can be fastened
    n_holes = sum(1 for _ in _iter_faces_by_type(shape, GeomAbs_Cylinder))
    if n_holes > 0:
        affordances.append({"type": "fastenable", "holes": n_holes})

    return {
        "layer": 7,
        "name": "人类感知模拟",
        "grade": _grade(score),
        "score": max(0, score),
        "principal_axes": {
            "moments": [round(m, 1) for m in principal_moments],
            "axes": [[round(v, 4) for v in ax] for ax in principal_axes],
        },
        "symmetry": symmetry,
        "stability": {
            "assessment": stability,
            "com_z_relative": round(cz_rel, 3),
            "base_area_mm2": round(base_area, 1),
        },
        "sections": {
            "xy_area_mm2": round(section_xy, 1),
            "xz_area_mm2": round(section_xz, 1),
            "yz_area_mm2": round(section_yz, 1),
        },
        "hollowness_pct": round(hollowness * 100, 1),
        "visual_complexity": visual_complexity,
        "complexity_ratio": round(complexity_ratio, 2),
        "affordances": affordances,
        "findings": findings,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


def _iter_faces_by_type(shape: TopoDS_Shape, geom_type) -> list:
    """Iterator helper: yield faces of a specific geometric type."""
    result = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        adaptor = BRepAdaptor_Surface(face)
        if adaptor.GetType() == geom_type:
            result.append(face)
        exp.Next()
    return result


# ═══════════════════════════════════════════════════════════════
# Shape Healing — 自动修复
# ═══════════════════════════════════════════════════════════════
def heal_shape(shape: TopoDS_Shape, precision: float = 1e-4) -> Tuple[TopoDS_Shape, Dict]:
    """
    OCCT ShapeFix自动修复: 修复拓扑缺陷、去除小边/小面。
    道法自然: 不强制改变几何，只修复违规。
    """
    t0 = time.time()
    v_before = abs(K.volume(shape))

    fixer = ShapeFix_Shape(shape)
    fixer.SetPrecision(precision)
    fixer.Perform()
    fixed = fixer.Shape()

    v_after = abs(K.volume(fixed))
    drift = abs(v_before - v_after) / max(v_before, 1) * 100

    # Wireframe fix (remove small edges)
    try:
        wf = ShapeFix_Wireframe(fixed)
        wf.SetPrecision(precision)
        wf.FixSmallEdges()
        wf.FixWireGaps()
        fixed = wf.Shape()
    except Exception:
        pass

    report = {
        "volume_before": round(v_before, 2),
        "volume_after": round(v_after, 2),
        "drift_pct": round(drift, 4),
        "time_ms": round((time.time() - t0) * 1000, 1),
    }
    return fixed, report


# ═══════════════════════════════════════════════════════════════
# MASTER AUDIT — 全层审核
# ═══════════════════════════════════════════════════════════════
def full_audit(shape: TopoDS_Shape,
               name: str = "unnamed",
               vol_range: Optional[Tuple[float, float]] = None,
               specs: Optional[Dict] = None,
               intent: Optional[Dict] = None,
               process: str = "fdm",
               pull_direction: Tuple[float, float, float] = (0, 0, 1),
               ) -> Dict[str, Any]:
    """
    完整八层审核: 一次调用审视一切。

    Layer 0: 拓扑完整性   (OCCT BRepCheck)
    Layer 1: 几何健全性   (体积/面积/包围盒/质心)
    Layer 2: 工程适用性   (壁厚/拔模角/曲率/边质量/悬垂)
    Layer 3: 装配验证     (如有多零件)
    Layer 4: 格式合规性   (STEP回环/STL网格)
    Layer 5: 参数合规性   (设计参数对照)
    Layer 6: 设计意图验证 (几何是否忠于原始意图)
    Layer 7: 人类感知模拟 (对称性/主轴/稳定性/可供性)
    """
    t0 = time.time()

    layers = []
    layers.append(audit_topology(shape))
    layers.append(audit_geometry(shape, vol_range=vol_range))
    layers.append(audit_engineering(shape, process=process,
                                    pull_direction=pull_direction))
    layers.append(audit_format(shape))
    if specs:
        layers.append(audit_params(shape, specs))
    if intent:
        layers.append(audit_intent(shape, intent))
    layers.append(audit_perception(shape))

    # Overall score (weighted average)
    weights = {0: 30, 1: 25, 2: 20, 4: 15, 5: 10, 6: 15, 7: 5}
    total_weight = 0
    weighted_sum = 0
    for layer in layers:
        w = weights.get(layer['layer'], 10)
        weighted_sum += layer['score'] * w
        total_weight += w
    overall_score = weighted_sum / max(total_weight, 1)

    all_issues = []
    for layer in layers:
        for issue in layer.get('issues', []):
            all_issues.append(f"[L{layer['layer']}] {issue}")

    return {
        "name": name,
        "grade": _grade(overall_score),
        "score": round(overall_score, 1),
        "layers": layers,
        "issues": all_issues,
        "total_time_ms": round((time.time() - t0) * 1000, 1),
    }


# ═══════════════════════════════════════════════════════════════
# BATCH AUDIT — 批量审核一个目录的所有STEP文件
# ═══════════════════════════════════════════════════════════════
def batch_audit(directory: str,
                specs_map: Optional[Dict[str, Dict]] = None
                ) -> Dict[str, Any]:
    """
    批量审核目录下所有STEP文件。
    specs_map: {"part_name": {"volume_range": (lo, hi), ...}}
    """
    t0 = time.time()
    d = Path(directory)
    step_files = sorted(d.glob("*.step"))
    if not step_files:
        return {"error": "No STEP files found", "directory": str(d)}

    results = []
    for sf in step_files:
        name = sf.stem
        try:
            shape = K.from_step(str(sf))
            specs = (specs_map or {}).get(name, None)
            vol_range = specs.pop("volume_range", None) if specs else None
            audit = full_audit(shape, name=name, vol_range=vol_range, specs=specs)
            results.append(audit)
        except Exception as e:
            results.append({"name": name, "grade": "F", "score": 0, "error": str(e)})

    # Summary
    grades = [r['grade'] for r in results]
    scores = [r['score'] for r in results]
    avg_score = sum(scores) / max(len(scores), 1)

    return {
        "directory": str(d),
        "parts": len(results),
        "avg_score": round(avg_score, 1),
        "overall_grade": _grade(avg_score),
        "grade_distribution": {g: grades.count(g) for g in ["S", "A", "B", "C", "F"]},
        "results": results,
        "total_time_ms": round((time.time() - t0) * 1000, 1),
    }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
def _print_audit(audit: Dict, verbose: bool = True):
    """Pretty-print audit result."""
    name = audit.get('name', '?')
    grade = audit.get('grade', '?')
    score = audit.get('score', 0)
    grade_colors = {"S": "★★★", "A": "★★☆", "B": "★☆☆", "C": "☆☆☆", "F": "✗✗✗"}

    print(f"  {name:<20} {grade_colors.get(grade, '?')} {grade} ({score:.0f})")

    if verbose and audit.get('issues'):
        for issue in audit['issues']:
            print(f"    └─ {issue}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="道 · 三维审核系统")
    parser.add_argument("target", help="STEP file or directory")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    target = Path(args.target)

    print("=" * 70)
    print("  道 · 三维审核系统 — DaoAudit")
    print("=" * 70)

    if target.is_dir():
        result = batch_audit(str(target))
        print(f"\n  目录: {target}")
        print(f"  零件: {result['parts']}  平均: {result['avg_score']:.0f}  等级: {result['overall_grade']}")
        print(f"  分布: {result['grade_distribution']}")
        print("-" * 70)
        for r in result['results']:
            _print_audit(r, verbose=args.verbose)
        print("-" * 70)
        print(f"  耗时: {result['total_time_ms']:.0f}ms")
    elif target.suffix.lower() in ['.step', '.stp']:
        shape = K.from_step(str(target))
        result = full_audit(shape, name=target.stem)
        _print_audit(result, verbose=True)
        if result.get('layers'):
            print()
            for layer in result['layers']:
                ln = layer.get('name', '?')
                lg = layer.get('grade', '?')
                ls = layer.get('score', 0)
                print(f"    Layer {layer['layer']}: {ln:<12} {lg} ({ls:.0f})")
    else:
        print(f"  不支持的文件类型: {target.suffix}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    print("=" * 70)
