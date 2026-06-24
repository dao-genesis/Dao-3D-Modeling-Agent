#!/usr/bin/env python3
"""
E2E verification — test everything via FreeCADConnection manager.
Tests the full pipeline from Python → connection manager → subprocess → FreeCAD backend.
"""
import json, sys, time, tempfile
from pathlib import Path

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), Path(__file__).resolve().parent.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

from freecad_connection import FreeCADConnection

print("=" * 70)
print("E2E VERIFICATION — FreeCAD Backend via Connection Manager")
print("=" * 70)

fc = FreeCADConnection()
status = fc.connect()
print(f"Mode: {status.mode} | subprocess_ok={status.subprocess_ok} | version={status.version}")
print(f"cmd: {status.cmd_path}")
print()

tmp = tempfile.gettempdir()
PASS = 0
FAIL = 0
results_detail = []


def test(name, ops):
    global PASS, FAIL
    t0 = time.time()
    try:
        r = fc.execute_ops(ops)
        elapsed = round(time.time() - t0, 2)
        ok = r.get("ok", False)
        shapes = r.get("shapes", {})
        errors = r.get("errors", [])
        n_shapes = len(shapes)
        n_errors = len(errors)

        if ok or (n_shapes > 0 and n_errors == 0):
            PASS += 1
            print(f"  [PASS] {name} ({elapsed}s, {n_shapes} shapes)")
            results_detail.append({"name": name, "ok": True, "elapsed": elapsed, "shapes": n_shapes})
        else:
            FAIL += 1
            err_short = errors[0][:120] if errors else "no shapes"
            print(f"  [FAIL] {name} ({elapsed}s): {err_short}")
            results_detail.append({"name": name, "ok": False, "elapsed": elapsed, "error": err_short})
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        FAIL += 1
        print(f"  [FAIL] {name} ({elapsed}s): {e}")
        results_detail.append({"name": name, "ok": False, "elapsed": elapsed, "error": str(e)})


# ═══════════════════════════════════════════════════════════════
# Category 1: Primitives
# ═══════════════════════════════════════════════════════════════
print("── 1. Primitives ──")
test("make_box", [{"op": "make_box", "id": "b1", "L": 30, "W": 20, "H": 10}])
test("make_cylinder", [{"op": "make_cylinder", "id": "c1", "R": 5, "H": 15}])
test("make_sphere", [{"op": "make_sphere", "id": "s1", "R": 10}])
test("make_cone", [{"op": "make_cone", "id": "cn1", "R1": 8, "R2": 3, "H": 12}])
test("make_torus", [{"op": "make_torus", "id": "t1", "R1": 10, "R2": 3}])

# ═══════════════════════════════════════════════════════════════
# Category 2: Boolean operations
# ═══════════════════════════════════════════════════════════════
print("\n── 2. Boolean Operations ──")
test("fuse", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "make_cylinder", "id": "c", "R": 3, "H": 15, "pos": [5, 5, 0]},
    {"op": "fuse", "id": "f1", "shapes": ["b", "c"]}
])
test("cut", [
    {"op": "make_box", "id": "b", "L": 20, "W": 20, "H": 10},
    {"op": "make_cylinder", "id": "c", "R": 5, "H": 15, "pos": [10, 10, -2]},
    {"op": "cut", "id": "ct1", "base": "b", "tool": "c"}
])
test("common", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "make_sphere", "id": "s", "R": 8, "pos": [5, 5, 5]},
    {"op": "common", "id": "cm1", "shapes": ["b", "s"]}
])

# ═══════════════════════════════════════════════════════════════
# Category 3: Modifications
# ═══════════════════════════════════════════════════════════════
print("\n── 3. Modifications ──")
test("fillet", [
    {"op": "make_box", "id": "b", "L": 20, "W": 15, "H": 10},
    {"op": "fillet", "id": "fl", "shape": "b", "radius": 2}
])
test("chamfer", [
    {"op": "make_box", "id": "b", "L": 20, "W": 15, "H": 10},
    {"op": "chamfer", "id": "ch", "shape": "b", "size": 1.5}
])
test("shell", [
    {"op": "make_box", "id": "b", "L": 20, "W": 15, "H": 10},
    {"op": "shell", "id": "sh", "shape": "b", "thickness": 1}
])
test("mirror", [
    {"op": "make_box", "id": "b", "L": 10, "W": 5, "H": 8, "pos": [2, 0, 0]},
    {"op": "mirror", "id": "m", "shape": "b", "plane": "YZ"}
])

# ═══════════════════════════════════════════════════════════════
# Category 4: Sketch + PartDesign Pipeline
# ═══════════════════════════════════════════════════════════════
print("\n── 4. Sketch + PartDesign ──")
test("sketch_pad (rect)", [
    {"op": "sketch_pad", "id": "sp1",
     "geometry": [{"type": "rect", "x": -10, "y": -5, "w": 20, "h": 10}],
     "length": 15}
])
test("sketch_pad (circle)", [
    {"op": "sketch_pad", "id": "sp2",
     "geometry": [{"type": "circle", "cx": 0, "cy": 0, "r": 8}],
     "length": 10}
])
test("sketch_pocket", [
    {"op": "make_box", "id": "base", "L": 30, "W": 20, "H": 15},
    {"op": "sketch_pocket", "id": "pkt", "base": "base",
     "geometry": [{"type": "circle", "cx": 15, "cy": 10, "r": 5}],
     "depth": 8}
])
test("sketch_revolve", [
    {"op": "sketch_revolve", "id": "rev",
     "geometry": [{"type": "rect", "x": 5, "y": 0, "w": 3, "h": 10}],
     "angle": 360, "plane": "XZ"}
])

# ═══════════════════════════════════════════════════════════════
# Category 5: Patterns
# ═══════════════════════════════════════════════════════════════
print("\n── 5. Patterns ──")
test("linear_pattern", [
    {"op": "make_cylinder", "id": "pin", "R": 2, "H": 10},
    {"op": "partdesign_linear_pattern", "id": "arr",
     "shape": "pin", "direction": [1, 0, 0], "length": 30, "count": 4}
])
test("polar_pattern", [
    {"op": "make_box", "id": "tooth", "L": 3, "W": 2, "H": 5, "pos": [10, -1, 0]},
    {"op": "partdesign_polar_pattern", "id": "gear",
     "shape": "tooth", "axis": [0, 0, 1], "angle": 360, "count": 12}
])

# ═══════════════════════════════════════════════════════════════
# Category 6: Wire / Curve (NEW ops)
# ═══════════════════════════════════════════════════════════════
print("\n── 6. Wire & Curve ──")
test("make_helix", [
    {"op": "make_helix", "id": "h1", "pitch": 5, "height": 30, "radius": 8}
])
test("make_parametric_curve", [
    {"op": "make_parametric_curve", "id": "pc",
     "x": "10*cos(t)", "y": "10*sin(t)", "z": "t*3",
     "t_min": 0, "t_max": 6.283, "n_pts": 50}
])
test("make_polygon_3d", [
    {"op": "make_polygon_3d", "id": "poly",
     "points": [[0,0,0],[20,0,0],[20,15,0],[0,15,0],[0,0,0]]}
])

# ═══════════════════════════════════════════════════════════════
# Category 7: Surface / Loft (NEW ops)
# ═══════════════════════════════════════════════════════════════
print("\n── 7. Surface & Loft ──")
test("surface_loft", [
    {"op": "make_polygon_3d", "id": "w1",
     "points": [[0,0,0],[20,0,0],[20,15,0],[0,15,0],[0,0,0]]},
    {"op": "make_polygon_3d", "id": "w2",
     "points": [[3,3,15],[17,3,15],[17,12,15],[3,12,15],[3,3,15]]},
    {"op": "surface_loft", "id": "loft", "wires": ["w1","w2"], "solid": True}
])

# ═══════════════════════════════════════════════════════════════
# Category 8: Assembly + Interference
# ═══════════════════════════════════════════════════════════════
print("\n── 8. Assembly ──")
test("assembly", [
    {"op": "make_box", "id": "plate", "L": 50, "W": 30, "H": 5},
    {"op": "make_cylinder", "id": "shaft", "R": 3, "H": 25},
    {"op": "assembly", "id": "asm", "parts": [
        {"id": "p1", "shape": "plate", "pos": [0, 0, 0]},
        {"id": "p2", "shape": "shaft", "pos": [25, 15, 5]},
    ]}
])
test("interference_check", [
    {"op": "make_box", "id": "a", "L": 10, "W": 10, "H": 10},
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10, "pos": [5, 0, 0]},
    {"op": "interference_check", "id": "chk", "shape1": "a", "shape2": "b"}
])

# ═══════════════════════════════════════════════════════════════
# Category 9: TechDraw
# ═══════════════════════════════════════════════════════════════
print("\n── 9. TechDraw ──")
test("techdraw", [
    {"op": "make_box", "id": "part", "L": 30, "W": 20, "H": 15},
    {"op": "techdraw", "id": "td", "shape": "part",
     "output": f"{tmp}/e2e_test_drawing.svg", "title": "E2E Test"}
])
test("techdraw_section", [
    {"op": "make_cylinder", "id": "cyl", "R": 10, "H": 30},
    {"op": "techdraw_section", "id": "sec", "shape": "cyl", "plane": "XZ", "offset": 0}
])

# ═══════════════════════════════════════════════════════════════
# Category 10: FEM
# ═══════════════════════════════════════════════════════════════
print("\n── 10. FEM ──")
test("fem_mesh", [
    {"op": "make_box", "id": "block", "L": 20, "W": 10, "H": 8},
    {"op": "fem_mesh", "id": "fm", "shape": "block", "deflection": 0.2}
])
test("fem_stress_estimate", [
    {"op": "make_box", "id": "beam", "L": 100, "W": 10, "H": 5},
    {"op": "fem_stress_estimate", "id": "stress", "shape": "beam",
     "force_N": 500, "material": "steel"}
])

# ═══════════════════════════════════════════════════════════════
# Category 11: Measurement / Analysis (NEW)
# ═══════════════════════════════════════════════════════════════
print("\n── 11. Measurement ──")
test("measure_area", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "measure_area", "shape": "b"}
])
test("check_geometry", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "check_geometry", "id": "chk", "shape": "b"}
])
test("shape_info", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "shape_info", "shape": "b"}
])

# ═══════════════════════════════════════════════════════════════
# Category 12: Export formats
# ═══════════════════════════════════════════════════════════════
print("\n── 12. Export ──")
test("export_stl", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "export_stl", "shape": "b", "path": f"{tmp}/e2e_test.stl"}
])
test("export_step", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "export_step", "shape": "b", "path": f"{tmp}/e2e_test.step"}
])
test("export_brep", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "export_brep", "shape": "b", "path": f"{tmp}/e2e_test.brep"}
])
test("export_obj", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "export_obj", "shape": "b", "path": f"{tmp}/e2e_test.obj"}
])

# ═══════════════════════════════════════════════════════════════
# Category 13: Advanced geometry (NEW)
# ═══════════════════════════════════════════════════════════════
print("\n── 13. Advanced Geometry ──")
test("make_wedge", [
    {"op": "make_wedge", "id": "w",
     "xmin": 0, "ymin": 0, "zmin": 0,
     "xmax": 20, "ymax": 15, "zmax": 10,
     "x2min": 3, "z2min": 2, "x2max": 17, "z2max": 8}
])
test("multi_fuse", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "make_cylinder", "id": "c", "R": 3, "H": 15, "pos": [5, 5, 0]},
    {"op": "make_sphere", "id": "s", "R": 5, "pos": [15, 5, 5]},
    {"op": "multi_fuse", "id": "mf", "shapes": ["b", "c", "s"]}
])
test("multi_cut", [
    {"op": "make_box", "id": "b", "L": 30, "W": 20, "H": 10},
    {"op": "make_cylinder", "id": "h1", "R": 3, "H": 20, "pos": [10, 10, -5]},
    {"op": "make_cylinder", "id": "h2", "R": 3, "H": 20, "pos": [20, 10, -5]},
    {"op": "multi_cut", "id": "mc", "base": "b", "tools": ["h1", "h2"]}
])
test("clone_shape", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "clone_shape", "id": "cl", "shape": "b", "translate": [20, 0, 0]}
])

# ═══════════════════════════════════════════════════════════════
# Category 14: Sheet Metal (NEW)
# ═══════════════════════════════════════════════════════════════
print("\n── 14. Sheet Metal ──")
test("sheet_metal_bend", [
    {"op": "make_box", "id": "plate", "L": 50, "W": 30, "H": 2},
    {"op": "sheet_metal_bend", "id": "bent", "shape": "plate", "bend_angle": 90}
])

# ═══════════════════════════════════════════════════════════════
# Category 15: Import BREP back
# ═══════════════════════════════════════════════════════════════
print("\n── 15. Import ──")
test("import_brep", [
    {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10},
    {"op": "export_brep", "shape": "b", "path": f"{tmp}/e2e_reimport.brep"},
    {"op": "import_brep", "id": "reimp", "path": f"{tmp}/e2e_reimport.brep"}
])

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
print()
print("=" * 70)
total = PASS + FAIL
print(f"RESULTS: {PASS}/{total} passed, {FAIL} failed")
if FAIL == 0:
    print("ALL TESTS PASSED — 道法自然，万物皆通")
else:
    print(f"FAILURES: {FAIL}")
    for r in results_detail:
        if not r["ok"]:
            print(f"  - {r['name']}: {r.get('error', '?')}")
print("=" * 70)
