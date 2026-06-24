#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORS6_Stewart · analysis — 质量 / 碰撞 / 工作空间 / 间距 分析

去芜存菁: 原 sr6_analyzer.py 932 行, 此处仅保留本源能力 (约 300 行).
删除: fingerprint (duplicate trimesh built-ins), detect_holes (never validated),
     assembly_graph (AABB-only), kinematic_chain (reconstructs known IK),
     gear_analysis (FFT toy), cross_verify (duplicate verify_assembly).

零外部依赖于 forge_v3 (避免 HTTP / 子进程). 仅依赖 trimesh + numpy.
可打印性分析通过 forge_v3.cmd_printability (若 3D建模Agent/forge_v3 可用).
"""
from __future__ import annotations

import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from .parts import (PARTS, SR6, BOUNDS_FILE, load_stl, stl_path, part_info)
from .kinematics import ik_forward

MATERIALS: Dict[str, int] = {
    "pla":   1240,
    "petg":  1270,
    "abs":   1050,
    "tpu":   1200,
    "nylon": 1140,
}
DEFAULT_MATERIAL = "pla"


# ══════════════════════════════════════════════════════════════════════════════
# 质量属性 · Mass Properties
# ══════════════════════════════════════════════════════════════════════════════

def mass_properties(name: str, material: str = DEFAULT_MATERIAL) -> Dict[str, Any]:
    """Compute volume/mass/CoM/inertia of a single part."""
    t0 = time.time()
    try:
        import numpy as np
        mesh = load_stl(name)
        density_kg_m3 = MATERIALS.get(material, 1240)
        density_g_mm3 = density_kg_m3 * 1e-6

        is_wt = bool(mesh.is_watertight)
        result: Dict[str, Any] = {
            "name": name,
            "material": material,
            "density_kg_m3": density_kg_m3,
            "watertight": is_wt,
            "vertices": len(mesh.vertices),
            "faces": len(mesh.faces),
        }

        if is_wt:
            vol_mm3 = float(mesh.volume)
            mass_g = vol_mm3 * density_g_mm3
            com = mesh.center_mass.tolist()
            eigvals = np.linalg.eigvalsh(mesh.moment_inertia)
            result.update({
                "volume_mm3": round(vol_mm3, 2),
                "volume_cm3": round(vol_mm3 / 1000, 3),
                "mass_g": round(mass_g, 2),
                "center_of_mass_mm": [round(v, 3) for v in com],
                "principal_moments_inertia": sorted([round(float(v), 4) for v in eigvals]),
                "bounding_box_mm": {
                    "min": mesh.bounds[0].tolist(),
                    "max": mesh.bounds[1].tolist(),
                    "size": (mesh.bounds[1] - mesh.bounds[0]).tolist(),
                },
            })
        else:
            bb = mesh.bounding_box
            vol_bb = float(bb.volume) if bb else None
            result.update({
                "volume_mm3": None, "volume_cm3": None, "mass_g": None,
                "note": "Not watertight — volume/mass cannot be computed exactly",
                "bounding_box_mm": {
                    "min": mesh.bounds[0].tolist(),
                    "max": mesh.bounds[1].tolist(),
                    "size": (mesh.bounds[1] - mesh.bounds[0]).tolist(),
                },
                "bounding_box_volume_cm3": round(vol_bb / 1000, 3) if vol_bb else None,
            })
        result["time_ms"] = round((time.time() - t0) * 1000, 1)
        return result
    except Exception as e:
        return {"name": name, "error": str(e), "time_ms": round((time.time() - t0) * 1000, 1)}


def mass_properties_all(material: str = DEFAULT_MATERIAL,
                        groups: Optional[List[str]] = None) -> Dict[str, Any]:
    """Aggregate mass properties across parts (optionally filtered by group)."""
    import numpy as np
    t0 = time.time()
    results: Dict[str, Any] = {}
    total_mass_g = 0.0
    com_weighted = np.zeros(3)
    watertight_count = 0

    parts = {k: v for k, v in PARTS.items() if groups is None or v[3] in groups}

    for name in parts:
        props = mass_properties(name, material)
        results[name] = props
        if props.get("mass_g") is not None:
            m = props["mass_g"]
            total_mass_g += m
            com_weighted += m * np.array(props["center_of_mass_mm"])
            watertight_count += 1

    assembly_com = (com_weighted / total_mass_g).tolist() if total_mass_g > 0 else None
    return {
        "parts": results,
        "summary": {
            "total_mass_g": round(total_mass_g, 2),
            "total_mass_kg": round(total_mass_g / 1000, 4),
            "assembly_com_mm": [round(v, 3) for v in assembly_com] if assembly_com else None,
            "watertight_parts": watertight_count,
            "total_parts": len(parts),
            "material": material,
        },
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 质量检查 · Quality (watertight / winding / degenerate / duplicate)
# ══════════════════════════════════════════════════════════════════════════════

def quality_check(name: str) -> Dict[str, Any]:
    """Check mesh quality: watertight / winding / degenerate / duplicate / isolated."""
    import numpy as np
    t0 = time.time()
    try:
        mesh = load_stl(name)
        is_wt = bool(mesh.is_watertight)
        is_winding = bool(mesh.is_winding_consistent)
        areas = mesh.area_faces
        degenerate = int(np.sum(areas < 1e-10))
        unique_faces, counts = np.unique(np.sort(mesh.faces, axis=1), axis=0, return_counts=True)
        duplicate = int(np.sum(counts > 1))
        referenced = set(mesh.faces.flatten())
        isolated = len(mesh.vertices) - len(referenced)

        issues = []
        if not is_wt: issues.append("not_watertight")
        if not is_winding: issues.append("winding_inconsistent")
        if degenerate > 0: issues.append(f"{degenerate}_degenerate_faces")
        if duplicate > 0: issues.append(f"{duplicate}_duplicate_faces")
        if isolated > 0: issues.append(f"{isolated}_isolated_vertices")

        grade = "S" if not issues else "A" if len(issues) <= 1 else "B" if len(issues) <= 2 else "C"
        return {
            "name": name, "grade": grade, "issues": issues,
            "watertight": is_wt, "winding_consistent": is_winding,
            "faces": len(mesh.faces), "vertices": len(mesh.vertices),
            "degenerate_faces": degenerate, "duplicate_faces": duplicate,
            "isolated_vertices": isolated,
            "surface_area_mm2": round(float(mesh.area), 2),
            "time_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        return {"name": name, "grade": "F", "error": str(e),
                "time_ms": round((time.time() - t0) * 1000, 1)}


def quality_check_all() -> Dict[str, Any]:
    """Quality check every part, aggregate grade distribution."""
    t0 = time.time()
    results = {name: quality_check(name) for name in PARTS}
    grades = {"S": 0, "A": 0, "B": 0, "C": 0, "F": 0}
    for r in results.values():
        grades[r.get("grade", "F")] += 1
    return {
        "parts": results,
        "summary": {
            "total": len(PARTS),
            "grades": grades,
            "perfect_s": grades["S"],
            "score": f"{grades['S']}/{len(PARTS)}",
            "all_watertight": all(r.get("watertight", False) for r in results.values()),
        },
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 碰撞检测 · Collision
# ══════════════════════════════════════════════════════════════════════════════

def collision_check(name1: str, name2: str,
                    transform1=None, transform2=None) -> Dict[str, Any]:
    """Check AABB / precise collision between two parts (identity transforms by default)."""
    t0 = time.time()
    try:
        import trimesh
        m1 = load_stl(name1)
        m2 = load_stl(name2)
        if transform1 is not None:
            m1.apply_transform(transform1)
        if transform2 is not None:
            m2.apply_transform(transform2)

        bb1_min, bb1_max = m1.bounds
        bb2_min, bb2_max = m2.bounds
        gaps = [max(bb2_min[a] - bb1_max[a], bb1_min[a] - bb2_max[a]) for a in range(3)]
        min_bb_gap = max(gaps)
        bb_collision = min_bb_gap < 0

        precise, method = bb_collision, "aabb"
        try:
            manager = trimesh.collision.CollisionManager()
            manager.add_object("p1", m1)
            manager.add_object("p2", m2)
            precise, _ = manager.in_collision_internal(return_names=True)
            method = "fcl"
        except Exception:
            pass

        return {
            "parts": [name1, name2],
            "collision": bool(precise),
            "bb_collision": bb_collision,
            "bb_gap_mm": round(min_bb_gap, 3),
            "axis_gaps_mm": {"x": round(gaps[0], 3),
                             "y": round(gaps[1], 3),
                             "z": round(gaps[2], 3)},
            "method": method,
            "time_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        return {"parts": [name1, name2], "error": str(e),
                "time_ms": round((time.time() - t0) * 1000, 1)}


# ══════════════════════════════════════════════════════════════════════════════
# IK 工作空间 · Workspace (depends on kinematics.ik_forward)
# ══════════════════════════════════════════════════════════════════════════════

def workspace_analysis(resolution: int = 10) -> Dict[str, Any]:
    """Sample IK across full T-Code range, compute reachable envelope volume."""
    import numpy as np
    t0 = time.time()
    positions: List[Dict[str, float]] = []

    L0_range = np.linspace(0.0, 1.0, resolution)
    L1_range = np.linspace(0.0, 1.0, max(resolution // 2, 5))
    L2_range = np.linspace(0.0, 1.0, max(resolution // 2, 5))

    for L0 in L0_range:
        for L1 in L1_range:
            for L2 in L2_range:
                p = ik_forward(float(L0), float(L1), float(L2))
                positions.append(p["receiver_position_mm"])

    xs = [p["x"] for p in positions]
    ys = [p["y"] for p in positions]
    zs = [p["z"] for p in positions]

    workspace_volume_cm3: Optional[float] = None
    workspace_surface_cm2: Optional[float] = None
    try:
        from scipy.spatial import ConvexHull
        pts = np.array([[p["x"], p["y"], p["z"]] for p in positions])
        hull = ConvexHull(pts)
        workspace_volume_cm3 = round(float(hull.volume) / 1000, 2)
        workspace_surface_cm2 = round(float(hull.area) / 100, 2)
    except Exception:
        pass

    return {
        "linear_workspace_mm": {
            "x": {"min": min(xs), "max": max(xs), "range": max(xs) - min(xs)},
            "y": {"min": min(ys), "max": max(ys), "range": max(ys) - min(ys)},
            "z": {"min": min(zs), "max": max(zs), "range": max(zs) - min(zs)},
        },
        "receiver_z_range_mm": {"min": min(zs), "max": max(zs)},
        "workspace_volume_cm3": workspace_volume_cm3,
        "workspace_surface_area_cm2": workspace_surface_cm2,
        "theoretical_ranges": {
            "thrust_mm": {"min": -60.0, "max": 60.0, "total": 120.0},
            "surge_mm":  {"min": -30.0, "max": 30.0, "total": 60.0},
            "sway_mm":   {"min": -30.0, "max": 30.0, "total": 60.0},
            "twist_deg": {"min": -135.0, "max": 135.0, "total": 270.0},
            "roll_deg":  {"min": -30.0,  "max": 30.0,  "total": 60.0},
            "pitch_deg": {"min": -25.0,  "max": 25.0,  "total": 50.0},
        },
        "dof": 6,
        "sample_points": len(positions),
        "resolution": resolution,
        "ik_constants": SR6,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 间距 · Clearance (bbox-based, uses bounds cache)
# ══════════════════════════════════════════════════════════════════════════════

_DEFAULT_PAIRS = [
    ("L_Frame", "R_Frame"), ("L_Frame", "Base"), ("R_Frame", "Base"),
    ("Receiver", "Lid"), ("Arm", "BearingMain"),
    ("Twist_Base", "Twist_Body"), ("Twist_Body", "Twist_Lid"),
    ("Shield", "L_Frame"), ("Shield", "R_Frame"),
]


def clearance_analysis(pairs: Optional[List[Tuple[str, str]]] = None) -> Dict[str, Any]:
    """Compute bbox separation for key part pairs. Reads from BOUNDS_FILE for speed."""
    import json
    t0 = time.time()
    pairs = pairs or _DEFAULT_PAIRS

    bounds_data: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(BOUNDS_FILE):
        bounds_data = json.load(open(BOUNDS_FILE, encoding="utf-8"))

    results: List[Dict[str, Any]] = []
    for p1, p2 in pairs:
        if p1 not in PARTS or p2 not in PARTS:
            results.append({"parts": [p1, p2], "error": "part not found"})
            continue
        b1, b2 = bounds_data.get(p1), bounds_data.get(p2)

        if b1 and b2 and "center" in b1 and "center" in b2:
            min1 = b1.get("min") or [b1["center"][i] - b1["size"][i] / 2 for i in range(3)]
            max1 = b1.get("max") or [b1["center"][i] + b1["size"][i] / 2 for i in range(3)]
            min2 = b2.get("min") or [b2["center"][i] - b2["size"][i] / 2 for i in range(3)]
            max2 = b2.get("max") or [b2["center"][i] + b2["size"][i] / 2 for i in range(3)]
            gx = max(min2[0] - max1[0], min1[0] - max2[0])
            gy = max(min2[1] - max1[1], min1[1] - max2[1])
            gz = max(min2[2] - max1[2], min1[2] - max2[2])
            dx = max(0, min2[0] - max1[0], min1[0] - max2[0])
            dy = max(0, min2[1] - max1[1], min1[1] - max2[1])
            dz = max(0, min2[2] - max1[2], min1[2] - max2[2])
            bb_distance = math.sqrt(dx * dx + dy * dy + dz * dz)
            results.append({
                "parts": [p1, p2],
                "bb_separation_mm": round(bb_distance, 2),
                "axis_gaps_mm": {"x": round(gx, 2), "y": round(gy, 2), "z": round(gz, 2)},
                "bb_overlap": bb_distance < 0.001,
                "min_axis_gap_mm": round(min(gx, gy, gz), 2),
            })
        else:
            # Fallback: full collision check
            cc = collision_check(p1, p2)
            results.append({
                "parts": [p1, p2],
                "bb_separation_mm": cc.get("bb_gap_mm"),
                "bb_overlap": cc.get("bb_collision", False),
                "axis_gaps_mm": cc.get("axis_gaps_mm", {}),
            })

    return {
        "clearances": results,
        "total_pairs": len(pairs),
        "overlapping": sum(1 for r in results if r.get("bb_overlap", False)),
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 装配整体统计 · Assembly Stats
# ══════════════════════════════════════════════════════════════════════════════

def assembly_stats() -> Dict[str, Any]:
    """Bounding envelope, per-group counts, part summary — uses BOUNDS_FILE."""
    import json
    t0 = time.time()
    bounds_data: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(BOUNDS_FILE):
        bounds_data = json.load(open(BOUNDS_FILE, encoding="utf-8"))

    group_stats: Dict[str, Dict[str, Any]] = {}
    all_mins: List[List[float]] = []
    all_maxs: List[List[float]] = []
    part_summary: List[Dict[str, Any]] = []

    for name, (sub, fn, color_int, group) in PARTS.items():
        group_stats.setdefault(group, {"count": 0, "parts": []})
        group_stats[group]["count"] += 1
        group_stats[group]["parts"].append(name)

        b = bounds_data.get(name)
        if b and "center" in b:
            center = b["center"]
            size = b.get("size") or [0, 0, 0]
            bmin = b.get("min") or [center[i] - size[i] / 2 for i in range(3)]
            bmax = b.get("max") or [center[i] + size[i] / 2 for i in range(3)]
            all_mins.append(bmin)
            all_maxs.append(bmax)
            part_summary.append({
                "name": name, "group": group,
                "center_mm": [round(v, 1) for v in center],
                "size_mm": [round(v, 1) for v in size],
                "bbox_volume_cm3": round(size[0] * size[1] * size[2] / 1000, 2),
            })

    if all_mins:
        a_min = [min(b[i] for b in all_mins) for i in range(3)]
        a_max = [max(b[i] for b in all_maxs) for i in range(3)]
        a_size = [a_max[i] - a_min[i] for i in range(3)]
        a_vol_L = a_size[0] * a_size[1] * a_size[2] / 1e6
    else:
        a_min = a_max = a_size = [0, 0, 0]
        a_vol_L = 0

    return {
        "assembly": {
            "total_parts": len(PARTS),
            "bounding_box_mm": {
                "min": [round(v, 1) for v in a_min],
                "max": [round(v, 1) for v in a_max],
                "size_xyz_mm": [round(v, 1) for v in a_size],
            },
            "footprint_mm2": round(a_size[0] * a_size[1], 1),
            "height_mm": round(a_size[2], 1),
            "envelope_volume_L": round(a_vol_L, 3),
        },
        "groups": group_stats,
        "parts": part_summary,
        "ik_constants": SR6,
        "kinematic_frame_width_mm": 199.2,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


if __name__ == "__main__":
    import json
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "assembly"
    if cmd == "mass":
        part = sys.argv[2] if len(sys.argv) > 2 else None
        mat = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_MATERIAL
        r = mass_properties(part, mat) if part else mass_properties_all(mat)
        print(json.dumps(r, indent=2, ensure_ascii=False))
    elif cmd == "quality":
        part = sys.argv[2] if len(sys.argv) > 2 else None
        print(json.dumps(quality_check(part) if part else quality_check_all(),
                         indent=2, ensure_ascii=False))
    elif cmd == "workspace":
        res = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        print(json.dumps(workspace_analysis(res), indent=2, ensure_ascii=False))
    elif cmd == "clearance":
        print(json.dumps(clearance_analysis(), indent=2, ensure_ascii=False))
    elif cmd == "assembly":
        print(json.dumps(assembly_stats(), indent=2, ensure_ascii=False))
    elif cmd == "collision":
        p1 = sys.argv[2] if len(sys.argv) > 2 else "Base"
        p2 = sys.argv[3] if len(sys.argv) > 3 else "L_Frame"
        print(json.dumps(collision_check(p1, p2), indent=2, ensure_ascii=False))
    else:
        print(__doc__)
