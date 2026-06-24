#!/usr/bin/env python3
"""
FreeCAD Backend — 新增能力验证测试

运行方式:
  freecadcmd.exe _test_freecad_ops.py

验证: Sketch系统 + PartDesign管道 + Assembly + TechDraw + FEM
"""
import sys
import os
import json
import tempfile
from pathlib import Path

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), Path(__file__).resolve().parent.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

PASS = 0
FAIL = 0
WARN = 0


def test(name, fn):
    global PASS, FAIL, WARN
    try:
        result = fn()
        if result.get("ok", True) and not result.get("errors"):
            PASS += 1
            warnings = result.get("warnings", [])
            if warnings:
                WARN += 1
                print(f"  [PASS+WARN] {name}: {warnings[0][:60]}")
            else:
                print(f"  [PASS] {name}")
            return result
        else:
            FAIL += 1
            errs = result.get("errors", [])
            print(f"  [FAIL] {name}: {errs[0][:80] if errs else 'unknown'}")
            return result
    except Exception as e:
        FAIL += 1
        print(f"  [FAIL] {name}: {e}")
        return {"ok": False, "error": str(e)}


def main():
    from freecad_backend import run_ops

    print("=" * 60)
    print("FreeCAD Backend — 新增能力验证")
    print("=" * 60)

    tmp = Path(tempfile.gettempdir()) / "fc_test"
    tmp.mkdir(exist_ok=True)

    # ── 1. Sketch → Pad ──────────────────────────────────────
    print("\n── Sketch + PartDesign ──")

    test("sketch_pad (rect)", lambda: run_ops([
        {"op": "sketch_pad", "id": "sp1",
         "geometry": [{"type": "rect", "x": -10, "y": -5, "w": 20, "h": 10}],
         "length": 15}
    ]))

    test("sketch_pad (circle)", lambda: run_ops([
        {"op": "sketch_pad", "id": "sp2",
         "geometry": [{"type": "circle", "cx": 0, "cy": 0, "r": 8}],
         "length": 10}
    ]))

    test("sketch_pad (hexagon)", lambda: run_ops([
        {"op": "sketch_pad", "id": "sp3",
         "geometry": [{"type": "hexagon", "cx": 0, "cy": 0, "r": 12}],
         "length": 8}
    ]))

    # ── 2. Sketch → Pocket ───────────────────────────────────
    test("sketch_pocket", lambda: run_ops([
        {"op": "make_box", "id": "base", "L": 30, "W": 20, "H": 15},
        {"op": "sketch_pocket", "id": "pkt",
         "base": "base",
         "geometry": [{"type": "circle", "cx": 15, "cy": 10, "r": 5}],
         "depth": 8}
    ]))

    # ── 3. Sketch → Revolution ───────────────────────────────
    test("sketch_revolve", lambda: run_ops([
        {"op": "sketch_revolve", "id": "rev",
         "geometry": [{"type": "rect", "x": 5, "y": 0, "w": 3, "h": 10}],
         "angle": 360, "plane": "XZ"}
    ]))

    # ── 4. Sketch → Hole ─────────────────────────────────────
    test("sketch_hole", lambda: run_ops([
        {"op": "make_box", "id": "base", "L": 40, "W": 40, "H": 10},
        {"op": "sketch_hole", "id": "holed",
         "base": "base",
         "geometry": [
             {"type": "circle", "cx": 10, "cy": 10, "r": 2},
             {"type": "circle", "cx": 30, "cy": 10, "r": 2},
             {"type": "circle", "cx": 10, "cy": 30, "r": 2},
             {"type": "circle", "cx": 30, "cy": 30, "r": 2},
         ],
         "diameter": 4, "through_all": True}
    ]))

    # ── 5. PartDesign Body (feature tree) ─────────────────────
    test("partdesign_body", lambda: run_ops([
        {"op": "partdesign_body", "id": "body1",
         "features": [
             {"type": "pad", "length": 20,
              "sketch": {"geometry": [
                  {"type": "rect", "x": -15, "y": -10, "w": 30, "h": 20}
              ]}},
         ]}
    ]))

    # ── 6. Patterns ──────────────────────────────────────────
    test("linear_pattern", lambda: run_ops([
        {"op": "make_cylinder", "id": "pin", "R": 2, "H": 10},
        {"op": "partdesign_linear_pattern", "id": "arr",
         "shape": "pin", "direction": [1, 0, 0],
         "length": 30, "count": 4}
    ]))

    test("polar_pattern", lambda: run_ops([
        {"op": "make_box", "id": "tooth", "L": 3, "W": 2, "H": 5,
         "pos": [10, -1, 0]},
        {"op": "partdesign_polar_pattern", "id": "gear",
         "shape": "tooth", "axis": [0, 0, 1],
         "angle": 360, "count": 12}
    ]))

    test("mirrored", lambda: run_ops([
        {"op": "make_box", "id": "half", "L": 10, "W": 5, "H": 8,
         "pos": [2, 0, 0]},
        {"op": "partdesign_mirrored", "id": "full",
         "shape": "half", "plane": "YZ"}
    ]))

    # ── 7. Assembly ──────────────────────────────────────────
    print("\n── Assembly ──")

    asm_path = str(tmp / "test_asm.fcstd")
    test("assembly + interference check", lambda: run_ops([
        {"op": "make_box", "id": "plate", "L": 50, "W": 30, "H": 5},
        {"op": "make_cylinder", "id": "shaft", "R": 3, "H": 25},
        {"op": "assembly", "id": "asm",
         "parts": [
             {"id": "p1", "shape": "plate", "pos": [0, 0, 0]},
             {"id": "p2", "shape": "shaft", "pos": [25, 15, 5]},
         ],
         "constraints": [],
         "save_path": asm_path}
    ]))

    test("interference_check", lambda: run_ops([
        {"op": "make_box", "id": "a", "L": 10, "W": 10, "H": 10},
        {"op": "make_box", "id": "b", "L": 10, "W": 10, "H": 10,
         "pos": [5, 0, 0]},
        {"op": "interference_check", "id": "chk",
         "shape1": "a", "shape2": "b"}
    ]))

    # ── 8. TechDraw ──────────────────────────────────────────
    print("\n── TechDraw ──")

    svg_path = str(tmp / "test_drawing.svg")
    test("techdraw", lambda: run_ops([
        {"op": "make_box", "id": "part", "L": 30, "W": 20, "H": 15},
        {"op": "techdraw", "id": "td", "shape": "part",
         "output": svg_path, "title": "Test Part Drawing"}
    ]))
    if Path(svg_path).exists():
        print(f"    → SVG: {Path(svg_path).stat().st_size} bytes")

    test("techdraw_section", lambda: run_ops([
        {"op": "make_cylinder", "id": "cyl", "R": 10, "H": 30},
        {"op": "techdraw_section", "id": "sec",
         "shape": "cyl", "plane": "XZ", "offset": 0}
    ]))

    # ── 9. FEM ───────────────────────────────────────────────
    print("\n── FEM ──")

    mesh_path = str(tmp / "test_mesh.stl")
    test("fem_mesh", lambda: run_ops([
        {"op": "make_box", "id": "block", "L": 20, "W": 10, "H": 8},
        {"op": "fem_mesh", "id": "fm", "shape": "block",
         "deflection": 0.2, "path": mesh_path}
    ]))

    test("fem_stress_estimate (steel)", lambda: run_ops([
        {"op": "make_box", "id": "beam", "L": 100, "W": 10, "H": 5},
        {"op": "fem_stress_estimate", "id": "stress",
         "shape": "beam", "force_N": 500, "material": "steel"}
    ]))

    test("fem_stress_estimate (pla)", lambda: run_ops([
        {"op": "make_box", "id": "print", "L": 50, "W": 20, "H": 3},
        {"op": "fem_stress_estimate", "id": "stress2",
         "shape": "print", "force_N": 50, "material": "pla"}
    ]))

    # ── 10. Sketch standalone ────────────────────────────────
    print("\n── Sketch Standalone ──")

    test("sketch_to_face", lambda: run_ops([
        {"op": "sketch_to_face", "id": "face",
         "geometry": [{"type": "polygon",
                       "points": [[0, 0], [20, 0], [20, 15], [10, 20], [0, 15]]}]}
    ]))

    test("sketch_to_wire", lambda: run_ops([
        {"op": "sketch_to_wire", "id": "wire",
         "geometry": [{"type": "circle", "cx": 0, "cy": 0, "r": 10}]}
    ]))

    # ── Summary ──────────────────────────────────────────────
    print()
    print("=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed, {WARN} warnings")
    if FAIL == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"FAILURES: {FAIL}")
    print("=" * 60)

    # Cleanup
    try:
        import shutil
        shutil.rmtree(str(tmp), ignore_errors=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
