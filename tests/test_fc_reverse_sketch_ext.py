# -*- coding: utf-8 -*-
"""Sketcher 反演扩展几何单测 (纯 Python · 无需 FreeCAD).

fixture: tests/fixtures/sketch_ext_fixture.FCStd — FreeCAD 0.19 生成,
含 Sketch(椭圆 10x4 @原点 + 椭圆弧 (法向 -Z, 0..π/2) + B样条 4控制点 3次).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "10-反笙_FreeCAD"))
sys.path.insert(0, str(ROOT))

from fc_reverse import FCReverse  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sketch_ext_fixture.FCStd"


def _sketch_op():
    r = FCReverse.reverse(str(FIXTURE))
    assert r["ok"], r
    return next(o for o in r["ops"] if o["op"] == "sketch")


def test_ext_geometry_all_supported():
    sk = _sketch_op()
    kinds = [g["type"] for g in sk["geometry"]]
    assert kinds == ["ellipse", "arc_of_ellipse", "bspline"]


def test_ellipse_fields():
    sk = _sketch_op()
    e = next(g for g in sk["geometry"] if g["type"] == "ellipse")
    assert e["center"] == [0.0, 0.0]
    assert e["major_radius"] == 10.0 and e["minor_radius"] == 4.0
    assert e["normal_z"] == 1.0


def test_arc_of_ellipse_fields():
    sk = _sketch_op()
    a = next(g for g in sk["geometry"] if g["type"] == "arc_of_ellipse")
    assert a["center"] == [20.0, 20.0]
    assert abs(a["major_radius"] - 23.3238075793812) < 1e-9
    assert abs(a["minor_radius"] - 8.40343067198293) < 1e-9
    assert a["normal_z"] == -1.0
    assert a["start_angle"] == 0.0
    assert abs(a["end_angle"] - 1.5707963267948966) < 1e-12


def test_bspline_fields():
    sk = _sketch_op()
    b = next(g for g in sk["geometry"] if g["type"] == "bspline")
    assert b["degree"] == 3 and not b["periodic"]
    assert b["poles"] == [[0.0, 0.0], [5.0, 10.0], [10.0, -5.0], [15.0, 5.0]]
    assert b["weights"] == [1.0] * 4
    assert b["knots"] == [0.0, 1.0] and b["mults"] == [4, 4]
