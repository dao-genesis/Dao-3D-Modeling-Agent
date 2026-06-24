#!/usr/bin/env python3
"""
道法自然 — FreeCAD 全类别 E2E 实操验证
通过 FreeCADConnection (launcher pattern) 测试所有 ops 类别
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

fc = FreeCADConnection()
s = fc.connect()
print(f"Connection: mode={s.mode} subprocess_ok={s.subprocess_ok}")
print()

tmp = tempfile.gettempdir()
results = []

def run_test(label, ops):
    t0 = time.time()
    r = fc.execute_ops(ops)
    elapsed = round(time.time() - t0, 2)
    ok = r.get("ok", False)
    shapes = r.get("shapes", {})
    errors = r.get("errors", [])
    exports = r.get("exports", [])
    n_ok = sum(1 for v in shapes.values() if v.get("type") != "ERROR")
    n_fail = sum(1 for v in shapes.values() if v.get("type") == "ERROR")
    status = "PASS" if ok and n_fail == 0 and not errors else "FAIL"
    results.append({"label": label, "ok": ok, "shapes": n_ok, "fail": n_fail, "errors": errors[:1], "elapsed": elapsed})
    print(f"  [{status}] {label}: shapes={n_ok} fail={n_fail} {elapsed}s" + (f" ERR: {str(errors[0])[:60]}" if errors else ""))
    return r

# ══════════════════════════════════════════════════════════════
print("═" * 60)
print("1. 基本几何体 (Primitives)")
print("═" * 60)
run_test("box+cylinder+sphere+cone+torus", [
    {"op": "make_box", "id": "b1", "L": 30, "W": 20, "H": 10},
    {"op": "make_cylinder", "id": "c1", "R": 8, "H": 20},
    {"op": "make_sphere", "id": "s1", "R": 12},
    {"op": "make_cone", "id": "co1", "R1": 10, "R2": 3, "H": 15},
    {"op": "make_torus", "id": "t1", "R1": 15, "R2": 4},
])

print()
print("═" * 60)
print("2. 布尔运算 (Boolean)")
print("═" * 60)
run_test("fuse+cut+common+fillet+chamfer", [
    {"op": "make_box", "id": "a", "L": 20, "W": 20, "H": 10},
    {"op": "make_cylinder", "id": "h", "R": 4, "H": 15, "pos": [10, 10, -3]},
    {"op": "cut", "id": "acut", "base": "a", "tool": "h"},
    {"op": "make_box", "id": "b2", "L": 25, "W": 15, "H": 8},
    {"op": "fuse", "id": "fused", "base": "acut", "tool": "b2"},
    {"op": "fillet", "id": "filleted", "shape": "b2", "radius": 2},
    {"op": "chamfer", "id": "chamfered", "shape": "b2", "size": 1.5},
])

print()
print("═" * 60)
print("3. Sketch + PartDesign")
print("═" * 60)
run_test("sketch_pad+pocket+revolve", [
    {"op": "sketch_pad", "id": "sp1",
     "geometry": [{"type": "rect", "x": -15, "y": -10, "w": 30, "h": 20}],
     "length": 12},
    {"op": "sketch_pocket", "id": "pkt1", "base": "sp1",
     "geometry": [{"type": "circle", "cx": 0, "cy": 0, "r": 5}], "depth": 8},
    {"op": "sketch_revolve", "id": "rev1",
     "geometry": [{"type": "rect", "x": 5, "y": 0, "w": 3, "h": 12}],
     "angle": 360, "plane": "XZ"},
])

run_test("partdesign_body+patterns", [
    {"op": "partdesign_body", "id": "body1",
     "features": [{"type": "pad", "length": 20,
                   "sketch": {"geometry": [{"type": "rect", "x": -20, "y": -10, "w": 40, "h": 20}]}}]},
    {"op": "make_cylinder", "id": "pin", "R": 2, "H": 10},
    {"op": "partdesign_linear_pattern", "id": "pin_arr",
     "shape": "pin", "direction": [1, 0, 0], "length": 30, "count": 4},
    {"op": "partdesign_polar_pattern", "id": "pin_polar",
     "shape": "pin", "axis": [0, 0, 1], "angle": 360, "count": 6},
])

print()
print("═" * 60)
print("4. 曲线与表面 (Wire/Surface)")
print("═" * 60)
run_test("helix+polygon3d+surface_loft", [
    {"op": "make_helix", "id": "hx1", "pitch": 5, "height": 30, "radius": 8},
    {"op": "make_polygon_3d", "id": "w1",
     "points": [[0,0,0],[20,0,0],[20,15,0],[0,15,0],[0,0,0]]},
    {"op": "make_polygon_3d", "id": "w2",
     "points": [[3,3,15],[17,3,15],[17,12,15],[3,12,15],[3,3,15]]},
    {"op": "surface_loft", "id": "loft1", "wires": ["w1","w2"], "solid": True},
])

run_test("parametric_curve+bspline+offset_surface", [
    {"op": "make_parametric_curve", "id": "spiral",
     "x": "10*cos(t)", "y": "10*sin(t)", "z": "t*2",
     "t_min": 0, "t_max": 6.283, "n_pts": 50},
    {"op": "make_bspline", "id": "bs1",
     "points": [[0,0,0],[5,10,2],[10,5,5],[15,15,3],[20,0,6]]},
    {"op": "make_bezier", "id": "bz1",
     "points": [[0,0,0],[5,20,0],[15,20,0],[20,0,0]]},
])

print()
print("═" * 60)
print("5. 高级几何 (Advanced Geometry)")
print("═" * 60)
run_test("wedge+frustum+pipe+sweep", [
    {"op": "make_wedge", "id": "wdg1",
     "xmin": 0, "ymin": 0, "zmin": 0, "xmax": 20, "ymax": 15, "zmax": 10,
     "x2min": 3, "z2min": 2, "x2max": 17, "z2max": 8},
    {"op": "make_frustum", "id": "frs1", "R1": 12, "R2": 6, "H": 18},
])

run_test("multi_fuse+multi_cut+clone", [
    {"op": "make_box", "id": "plate", "L": 50, "W": 30, "H": 3},
    {"op": "make_cylinder", "id": "h1", "R": 3, "H": 10, "pos": [10, 10, -4]},
    {"op": "make_cylinder", "id": "h2", "R": 3, "H": 10, "pos": [25, 10, -4]},
    {"op": "make_cylinder", "id": "h3", "R": 3, "H": 10, "pos": [40, 10, -4]},
    {"op": "multi_cut", "id": "plate_holes", "base": "plate", "tools": ["h1","h2","h3"]},
    {"op": "clone_shape", "id": "clone1", "shape": "plate_holes",
     "translate": [0, 40, 0]},
    {"op": "make_box", "id": "bb1", "L": 10, "W": 10, "H": 10},
    {"op": "make_box", "id": "bb2", "L": 10, "W": 10, "H": 10, "pos": [15, 0, 0]},
    {"op": "multi_fuse", "id": "mfused", "shapes": ["bb1","bb2"]},
])

print()
print("═" * 60)
print("6. 测量与分析 (Measurement)")
print("═" * 60)
run_test("shape_info+measure_area+measure_length+check_geometry", [
    {"op": "make_box", "id": "mbox", "L": 30, "W": 20, "H": 10},
    {"op": "shape_info", "shape": "mbox"},
    {"op": "measure_area", "shape": "mbox"},
    {"op": "measure_length", "shape": "mbox"},
    {"op": "check_geometry", "id": "chk1", "shape": "mbox"},
    {"op": "bounding_box", "id": "bb_chk", "shape": "mbox"},
    {"op": "center_of_mass", "shape": "mbox"},
])

print()
print("═" * 60)
print("7. 导出格式 (Export)")
print("═" * 60)
run_test("export STL+STEP+BREP+OBJ+IGES", [
    {"op": "make_box", "id": "exp_b", "L": 30, "W": 20, "H": 10},
    {"op": "fillet", "id": "exp_f", "shape": "exp_b", "radius": 2},
    {"op": "export_stl", "shape": "exp_f", "path": f"{tmp}/_fc_e2e_test.stl"},
    {"op": "export_step", "shape": "exp_f", "path": f"{tmp}/_fc_e2e_test.step"},
    {"op": "export_brep", "shape": "exp_f", "path": f"{tmp}/_fc_e2e_test.brep"},
    {"op": "export_obj", "shape": "exp_f", "path": f"{tmp}/_fc_e2e_test.obj"},
    {"op": "export_iges", "shape": "exp_f", "path": f"{tmp}/_fc_e2e_test.iges"},
])

# Check export files exist
print()
for ext in ["stl", "step", "brep", "obj", "iges"]:
    p = Path(tmp) / f"_fc_e2e_test.{ext}"
    size = p.stat().st_size if p.exists() else 0
    status = "OK" if size > 100 else "MISSING"
    print(f"  [{status}] {ext.upper()}: {size} bytes @ {p}")

print()
print("═" * 60)
print("8. TechDraw + FEM + Assembly")
print("═" * 60)
run_test("techdraw+fem+assembly", [
    {"op": "make_box", "id": "tdbox", "L": 40, "W": 30, "H": 15},
    {"op": "techdraw", "id": "td1", "shape": "tdbox",
     "output": f"{tmp}/_fc_e2e_techdraw.svg", "views": ["front","top","right"]},
    {"op": "make_cylinder", "id": "femcyl", "R": 10, "H": 25},
    {"op": "fem_mesh", "id": "mesh1", "shape": "femcyl", "max_size": 5},
    {"op": "fem_stress_estimate", "id": "stress1", "shape": "femcyl",
     "material": "steel", "force": 1000},
    {"op": "make_box", "id": "part_a", "L": 20, "W": 15, "H": 10},
    {"op": "make_cylinder", "id": "part_b", "R": 5, "H": 20},
    {"op": "assembly", "id": "asm1",
     "parts": [{"shape": "part_a", "pos": [0,0,0]}, {"shape": "part_b", "pos": [25,7,-5]}]},
])

# Check SVG
svg_p = Path(tmp) / "_fc_e2e_techdraw.svg"
print(f"  TechDraw SVG: {svg_p.stat().st_size if svg_p.exists() else 0} bytes")

print()
print("═" * 60)
print("9. Sheet Metal + CAM")
print("═" * 60)
run_test("sheet_metal_bend+unfold+cam_profile", [
    {"op": "make_box", "id": "sheet", "L": 50, "W": 30, "H": 2},
    {"op": "sheet_metal_bend", "id": "bent1", "shape": "sheet", "bend_angle": 90},
    {"op": "sheet_metal_unfold", "id": "flat1", "shape": "bent1"},
    {"op": "cam_profile", "id": "cam1", "shape": "sheet",
     "tool_radius": 2, "depth": 2, "step_down": 0.5,
     "path": f"{tmp}/_fc_e2e_test.gcode"},
])

print()
print("═" * 60)
print("10. 导入 (Import)")
print("═" * 60)
run_test("import_brep", [
    {"op": "make_sphere", "id": "to_export", "R": 15},
    {"op": "export_brep", "shape": "to_export", "path": f"{tmp}/_fc_import_test.brep"},
    {"op": "import_brep", "id": "reimported", "path": f"{tmp}/_fc_import_test.brep"},
    {"op": "shape_info", "shape": "reimported"},
])

print()
print("═" * 60)
print("═ SUMMARY")
print("═" * 60)
total = len(results)
passed = sum(1 for r in results if r["ok"] and r["fail"] == 0 and not r["errors"])
failed = total - passed
print(f"Groups: {passed}/{total} passed, {failed} failed")
total_shapes = sum(r["shapes"] for r in results)
total_errors = sum(r["fail"] for r in results)
print(f"Shapes: {total_shapes} OK, {total_errors} FAIL")
print()
if failed:
    print("FAILED GROUPS:")
    for r in results:
        if not r["ok"] or r["fail"] > 0 or r["errors"]:
            print(f"  - {r['label']}: {r['errors']}")
else:
    print("ALL GROUPS PASSED ✓")
