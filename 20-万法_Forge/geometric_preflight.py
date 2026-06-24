"""
Geometric Preflight — 几何可行性预检引擎
=========================================
反者道之动：在写建模代码之前，先验证几何是否可行。
这是Agent的"空间直觉"的计算实现。

Usage:
    from geometric_preflight import preflight, GeometrySpec
    spec = GeometrySpec(
        outer_dims=(80, 50, 30),
        wall_thickness=2.0,
        holes=[{"d": 5.5, "depth": "thru"}, {"d": 3.4, "depth": 10}],
        fillets=[{"r": 3.0, "edges": "vertical"}],
        chamfers=[],
        process="fdm",
    )
    result = preflight(spec)
    print(result)  # {"feasible": True/False, "issues": [...], "suggestions": [...]}

    # Quick parametric check
    from geometric_preflight import check_fillet, check_wall, check_hole
    check_fillet(radius=5, min_adjacent_edge=8)  # {"ok": False, "max_r": 4.0, ...}
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════
# Manufacturing Constraints Database (先验知识，非事后检查)
# ═══════════════════════════════════════════════════════════════════════

PROCESS_CONSTRAINTS = {
    "fdm": {
        "min_wall": 1.2,        # mm — 3 perimeters × 0.4mm nozzle
        "rec_wall": 1.5,        # mm — recommended
        "min_hole": 1.5,        # mm — minimum printable hole
        "max_overhang_deg": 45, # degrees from vertical
        "max_bridge_mm": 10,    # mm unsupported span
        "min_bottom_area": 10,  # mm² for bed adhesion
        "layer_height": 0.2,    # mm typical
        "xy_tolerance": 0.2,    # mm dimensional accuracy
        "z_tolerance": 0.1,     # mm
        "clearance_fit": 0.3,   # mm for moving parts
        "press_fit": 0.1,       # mm interference
    },
    "sla": {
        "min_wall": 0.5,
        "rec_wall": 0.8,
        "min_hole": 0.5,
        "max_overhang_deg": 30,  # needs supports earlier
        "max_bridge_mm": 5,
        "min_bottom_area": 5,
        "layer_height": 0.05,
        "xy_tolerance": 0.05,
        "z_tolerance": 0.025,
        "clearance_fit": 0.15,
        "press_fit": 0.05,
    },
    "cnc": {
        "min_wall": 1.0,
        "rec_wall": 1.5,
        "min_hole": 1.0,        # smallest drill bit
        "max_overhang_deg": 90,  # no overhang concern
        "max_bridge_mm": 999,
        "min_bottom_area": 0,
        "layer_height": 0,
        "xy_tolerance": 0.02,
        "z_tolerance": 0.02,
        "clearance_fit": 0.1,
        "press_fit": 0.02,
    },
}

# Standard metric hole sizes (clearance holes)
METRIC_CLEARANCE = {
    "M2": 2.4, "M2.5": 2.9, "M3": 3.4, "M4": 4.5,
    "M5": 5.5, "M6": 6.6, "M8": 9.0, "M10": 11.0,
}

# Self-tap holes for FDM
METRIC_SELFTAP_FDM = {
    "M2": 1.7, "M2.5": 2.2, "M3": 2.7, "M4": 3.5,
    "M5": 4.5, "M6": 5.3,
}

# Material densities (g/cm³)
DENSITY = {
    "pla": 1.24, "abs": 1.04, "petg": 1.27, "nylon": 1.14,
    "tpu": 1.21, "resin": 1.15, "aluminum": 2.70, "steel": 7.85,
}


# ═══════════════════════════════════════════════════════════════════════
# Geometric Constraint Checks (单项检查)
# ═══════════════════════════════════════════════════════════════════════

def check_fillet(radius: float, min_adjacent_edge: float, tolerance: float = 0.1) -> dict:
    """Check if a fillet radius is feasible given adjacent edge lengths."""
    max_r = min_adjacent_edge / 2 - tolerance
    ok = radius <= max_r
    return {
        "ok": ok,
        "radius": radius,
        "min_adjacent_edge": min_adjacent_edge,
        "max_feasible_radius": round(max_r, 2),
        "suggestion": None if ok else f"Reduce fillet to ≤{max_r:.1f}mm (current {radius}mm exceeds limit for {min_adjacent_edge}mm edge)"
    }


def check_chamfer(size: float, min_adjacent_edge: float, tolerance: float = 0.1) -> dict:
    """Check if a chamfer size is feasible."""
    max_c = min_adjacent_edge / 2 - tolerance
    ok = size <= max_c
    return {
        "ok": ok,
        "size": size,
        "max_feasible_size": round(max_c, 2),
        "suggestion": None if ok else f"Reduce chamfer to ≤{max_c:.1f}mm"
    }


def check_wall(thickness: float, process: str = "fdm") -> dict:
    """Check wall thickness against manufacturing process constraints."""
    pc = PROCESS_CONSTRAINTS.get(process, PROCESS_CONSTRAINTS["fdm"])
    ok = thickness >= pc["min_wall"]
    return {
        "ok": ok,
        "thickness": thickness,
        "min_required": pc["min_wall"],
        "recommended": pc["rec_wall"],
        "process": process,
        "suggestion": None if ok else f"Increase wall to ≥{pc['min_wall']}mm for {process} (current {thickness}mm)"
    }


def check_hole(diameter: float, face_min_dim: float, depth: float = None,
               wall_remaining: float = None, process: str = "fdm") -> dict:
    """Check hole feasibility: size vs face, depth vs wall, process limits."""
    pc = PROCESS_CONSTRAINTS.get(process, PROCESS_CONSTRAINTS["fdm"])
    issues = []

    if diameter < pc["min_hole"]:
        issues.append(f"Hole Ø{diameter}mm below {process} minimum {pc['min_hole']}mm")
    if diameter >= face_min_dim:
        issues.append(f"Hole Ø{diameter}mm exceeds face dimension {face_min_dim}mm")
    if wall_remaining is not None and wall_remaining < pc["min_wall"]:
        issues.append(f"Remaining wall {wall_remaining}mm below minimum {pc['min_wall']}mm")
    if depth is not None and wall_remaining is not None and depth > (wall_remaining + depth):
        issues.append(f"Blind hole depth exceeds available material")

    return {"ok": len(issues) == 0, "diameter": diameter, "issues": issues}


def check_overhang(angle_deg: float, process: str = "fdm") -> dict:
    """Check if overhang angle needs support."""
    pc = PROCESS_CONSTRAINTS.get(process, PROCESS_CONSTRAINTS["fdm"])
    ok = angle_deg <= pc["max_overhang_deg"]
    return {
        "ok": ok,
        "angle_deg": angle_deg,
        "max_allowed": pc["max_overhang_deg"],
        "needs_support": not ok,
        "suggestion": None if ok else f"Angle {angle_deg}° exceeds {pc['max_overhang_deg']}° — add self-support or split part"
    }


def check_shell(outer_dims: tuple, wall_thickness: float, process: str = "fdm") -> dict:
    """Check shell/hollowing feasibility."""
    min_dim = min(outer_dims)
    max_wall = min_dim / 2 - 0.5  # must leave some interior
    pc = PROCESS_CONSTRAINTS.get(process, PROCESS_CONSTRAINTS["fdm"])
    issues = []
    if wall_thickness < pc["min_wall"]:
        issues.append(f"Wall {wall_thickness}mm < minimum {pc['min_wall']}mm")
    if wall_thickness >= max_wall:
        issues.append(f"Wall {wall_thickness}mm leaves no interior (min dim={min_dim}mm)")
    inner = tuple(d - 2 * wall_thickness for d in outer_dims)
    return {
        "ok": len(issues) == 0,
        "outer_dims": outer_dims,
        "wall_thickness": wall_thickness,
        "inner_dims": inner,
        "issues": issues,
    }


def check_dimension_chain(outer: float, wall: float, inner: float = None,
                          clearance: float = 0) -> dict:
    """Verify dimension chain closure: outer = 2*wall + inner + clearance."""
    if inner is None:
        inner = outer - 2 * wall - clearance
    expected_outer = 2 * wall + inner + clearance
    diff = abs(outer - expected_outer)
    ok = diff < 0.01
    return {
        "ok": ok,
        "outer": outer, "wall": wall, "inner": round(inner, 3),
        "clearance": clearance,
        "computed_outer": round(expected_outer, 3),
        "error": round(diff, 3),
        "suggestion": None if ok else f"Dimension chain mismatch: {outer} ≠ 2×{wall} + {inner} + {clearance} = {expected_outer}"
    }


def estimate_mass(volume_mm3: float, material: str = "pla", infill: float = 0.2) -> dict:
    """Estimate mass from volume, material, and infill percentage."""
    d = DENSITY.get(material.lower(), 1.24)
    volume_cm3 = volume_mm3 / 1000
    # Solid shell + infill interior approximation
    mass_g = volume_cm3 * d * (0.4 + 0.6 * infill)  # ~40% shell, 60% infill
    return {
        "volume_mm3": volume_mm3,
        "volume_cm3": round(volume_cm3, 2),
        "material": material,
        "density_g_cm3": d,
        "infill_pct": infill * 100,
        "estimated_mass_g": round(mass_g, 1),
    }


def suggest_screw(load_n: float = 50, material: str = "pla") -> dict:
    """Suggest appropriate screw size for given load and material."""
    # Simple heuristic: M3 for light, M4 for medium, M5+ for heavy
    if load_n < 30:
        screw = "M2.5"
    elif load_n < 100:
        screw = "M3"
    elif load_n < 300:
        screw = "M4"
    else:
        screw = "M5"
    return {
        "screw": screw,
        "clearance_hole": METRIC_CLEARANCE.get(screw, 0),
        "selftap_hole_fdm": METRIC_SELFTAP_FDM.get(screw, 0),
        "min_boss_wall": float(screw.replace("M", "")),  # wall ≥ screw diameter
        "load_n": load_n,
    }


# ═══════════════════════════════════════════════════════════════════════
# Part Decomposition Advisor (拆件顾问)
# ═══════════════════════════════════════════════════════════════════════

def advise_decomposition(max_overhang_deg: float = 0, has_internal_cavity: bool = False,
                         max_dimension_mm: float = 0, bed_size_mm: float = 220,
                         multi_material: bool = False, process: str = "fdm") -> dict:
    """Advise whether to split a part and how."""
    reasons = []
    strategy = "one_piece"

    pc = PROCESS_CONSTRAINTS.get(process, PROCESS_CONSTRAINTS["fdm"])
    if max_overhang_deg > pc["max_overhang_deg"]:
        reasons.append(f"Overhang {max_overhang_deg}° exceeds {pc['max_overhang_deg']}° limit")
        strategy = "split_horizontal"
    if has_internal_cavity:
        reasons.append("Internal cavity without opening")
        strategy = "shell_and_lid"
    if max_dimension_mm > bed_size_mm:
        reasons.append(f"Dimension {max_dimension_mm}mm exceeds bed {bed_size_mm}mm")
        strategy = "sectioned_with_alignment"
    if multi_material:
        reasons.append("Multiple materials needed")
        strategy = "multi_part"

    connectors = {
        "one_piece": [],
        "split_horizontal": ["snap_fit", "m3_screws"],
        "shell_and_lid": ["snap_fit", "lip_groove"],
        "sectioned_with_alignment": ["dowel_pins", "m4_screws"],
        "multi_part": ["press_fit", "adhesive"],
    }

    return {
        "split_needed": strategy != "one_piece",
        "strategy": strategy,
        "reasons": reasons,
        "suggested_connectors": connectors.get(strategy, []),
    }


# ═══════════════════════════════════════════════════════════════════════
# Full Preflight Check (完整预检)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class GeometrySpec:
    """Specification for a geometry to be validated before code generation."""
    outer_dims: tuple = (50, 30, 20)       # (L, W, H) mm
    wall_thickness: float = 2.0            # mm — 0 for solid
    holes: list = field(default_factory=list)  # [{"d": 5.5, "depth": "thru"|mm, "face_dim": mm}]
    fillets: list = field(default_factory=list)  # [{"r": 3.0, "min_edge": mm}]
    chamfers: list = field(default_factory=list)  # [{"size": 1.0, "min_edge": mm}]
    process: str = "fdm"
    material: str = "pla"
    max_overhang_deg: float = 0
    has_internal_cavity: bool = False
    target_bed_mm: float = 220


def preflight(spec: GeometrySpec) -> dict:
    """
    Run full geometric preflight check.
    Returns feasibility assessment with issues and suggestions.
    This is the Agent's "spatial intuition" — called BEFORE writing any CAD code.
    """
    issues = []
    suggestions = []
    warnings = []

    L, W, H = spec.outer_dims
    min_dim = min(L, W, H)
    pc = PROCESS_CONSTRAINTS.get(spec.process, PROCESS_CONSTRAINTS["fdm"])

    # 1. Wall thickness
    if spec.wall_thickness > 0:
        wc = check_wall(spec.wall_thickness, spec.process)
        if not wc["ok"]:
            issues.append(wc["suggestion"])
        elif spec.wall_thickness < pc["rec_wall"]:
            warnings.append(f"Wall {spec.wall_thickness}mm works but {pc['rec_wall']}mm recommended for {spec.process}")

        # Shell feasibility
        sc = check_shell(spec.outer_dims, spec.wall_thickness, spec.process)
        if not sc["ok"]:
            issues.extend(sc["issues"])
        else:
            suggestions.append(f"Interior dimensions: {sc['inner_dims'][0]:.1f} × {sc['inner_dims'][1]:.1f} × {sc['inner_dims'][2]:.1f}mm")

    # 2. Fillets
    for i, f in enumerate(spec.fillets):
        r = f.get("r", 3.0)
        min_edge = f.get("min_edge", min_dim)
        fc = check_fillet(r, min_edge)
        if not fc["ok"]:
            issues.append(fc["suggestion"])
            suggestions.append(f"Fillet #{i+1}: use r≤{fc['max_feasible_radius']}mm")

    # 3. Chamfers
    for i, c in enumerate(spec.chamfers):
        size = c.get("size", 1.0)
        min_edge = c.get("min_edge", min_dim)
        cc = check_chamfer(size, min_edge)
        if not cc["ok"]:
            issues.append(cc["suggestion"])

    # 4. Holes
    for i, h in enumerate(spec.holes):
        d = h.get("d", 5.5)
        face_dim = h.get("face_dim", min(L, W))
        wall_left = spec.wall_thickness if spec.wall_thickness > 0 else min_dim / 2
        hc = check_hole(d, face_dim, wall_remaining=wall_left, process=spec.process)
        if not hc["ok"]:
            issues.extend(hc["issues"])

    # 5. Overhang
    if spec.max_overhang_deg > 0:
        oc = check_overhang(spec.max_overhang_deg, spec.process)
        if not oc["ok"]:
            warnings.append(oc["suggestion"])

    # 6. Bed size
    max_dim = max(L, W, H)
    if max_dim > spec.target_bed_mm:
        issues.append(f"Max dimension {max_dim}mm exceeds bed {spec.target_bed_mm}mm")

    # 7. Decomposition advice
    decomp = advise_decomposition(
        spec.max_overhang_deg, spec.has_internal_cavity,
        max_dim, spec.target_bed_mm, False, spec.process
    )
    if decomp["split_needed"]:
        warnings.append(f"Consider splitting: {decomp['strategy']} ({', '.join(decomp['reasons'])})")

    # 8. Mass estimate (for solid or shelled)
    volume = L * W * H
    if spec.wall_thickness > 0:
        inner = tuple(d - 2 * spec.wall_thickness for d in spec.outer_dims)
        inner_vol = max(0, inner[0]) * max(0, inner[1]) * max(0, inner[2])
        volume = volume - inner_vol
    me = estimate_mass(volume, spec.material)

    feasible = len(issues) == 0

    return {
        "feasible": feasible,
        "issues": issues,
        "warnings": warnings,
        "suggestions": suggestions,
        "mass_estimate": me,
        "decomposition": decomp if decomp["split_needed"] else None,
        "process_constraints": {
            "min_wall": pc["min_wall"],
            "clearance_fit": pc["clearance_fit"],
            "xy_tolerance": pc["xy_tolerance"],
        }
    }


# ═══════════════════════════════════════════════════════════════════════
# Engine Selection Advisor (引擎选择顾问)
# ═══════════════════════════════════════════════════════════════════════

def advise_engine(needs_fillet: bool = False, needs_step: bool = False,
                  needs_assembly: bool = False, needs_nurbs: bool = False,
                  needs_modify_stl: bool = False, complexity: str = "medium") -> dict:
    """Advise which modeling engine to use based on requirements."""
    scores = {"cadquery": 0, "build123d": 0, "openscad": 0, "freecad": 0}

    if needs_fillet or needs_step:
        scores["cadquery"] += 3
        scores["build123d"] += 2
        scores["freecad"] += 2
    if needs_assembly:
        scores["freecad"] += 3
        scores["cadquery"] += 1
    if needs_nurbs:
        scores["freecad"] += 3
        scores["build123d"] += 2
    if needs_modify_stl:
        scores["freecad"] += 2
    if complexity == "low":
        scores["openscad"] += 3
        scores["cadquery"] += 2
    elif complexity == "high":
        scores["freecad"] += 2
        scores["cadquery"] += 1

    # Reliability bonus (from real-world testing)
    scores["cadquery"] += 1  # most reliable BREP kernel
    scores["openscad"] += 1  # never crashes, just slow

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return {
        "recommended": ranked[0][0],
        "fallback": ranked[1][0],
        "scores": dict(ranked),
        "reasoning": _engine_reasoning(ranked[0][0]),
    }


def _engine_reasoning(engine: str) -> str:
    reasons = {
        "cadquery": "CadQuery: most reliable BREP, excellent fillet/chamfer, STEP export, Pythonic API",
        "build123d": "build123d: modern context-manager API, good for medium complexity",
        "openscad": "OpenSCAD: fastest for CSG prototypes, never crashes, Customizer UI",
        "freecad": "FreeCAD: full PartDesign, assemblies, NURBS surfaces, most capable but complex",
    }
    return reasons.get(engine, "Unknown engine")


# ═══════════════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════════════

def main():
    """CLI entry point for geometric preflight checks."""
    import sys
    if len(sys.argv) < 2:
        print("Usage: python geometric_preflight.py <json_spec>")
        print("       python geometric_preflight.py demo")
        return

    if sys.argv[1] == "demo":
        # Demo: ESP32 enclosure preflight
        spec = GeometrySpec(
            outer_dims=(84, 54, 32),
            wall_thickness=2.0,
            holes=[
                {"d": 3.4, "face_dim": 54, "depth": "thru"},  # M3 mounting
                {"d": 3.4, "face_dim": 54, "depth": "thru"},
                {"d": 3.4, "face_dim": 54, "depth": "thru"},
                {"d": 3.4, "face_dim": 54, "depth": "thru"},
            ],
            fillets=[{"r": 3.0, "min_edge": 32}],  # vertical edges
            chamfers=[],
            process="fdm",
            material="pla",
            has_internal_cavity=True,
        )
        result = preflight(spec)
        print(json.dumps(result, indent=2, ensure_ascii=False))

        print("\n--- Engine Advice ---")
        ea = advise_engine(needs_fillet=True, needs_step=True, complexity="medium")
        print(json.dumps(ea, indent=2))
    else:
        # Parse JSON spec from argument or file
        arg = sys.argv[1]
        try:
            if arg.endswith(".json"):
                with open(arg, encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = json.loads(arg)
            spec = GeometrySpec(**data)
            result = preflight(spec)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"error": str(e)}, indent=2))


if __name__ == "__main__":
    main()
