# -*- coding: utf-8 -*-
"""Sketcher 反演单测 (纯 Python · 无需 FreeCAD).

fixture: tests/fixtures/sketch_fixture.FCStd — FreeCAD 0.19 生成,
含 Sketch(4线框 60x40 + 圆 r8 + 构造对角线 + 圆弧 + 构造点, 6 约束)
+ PartDesign::Body/Pad(Length=15).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "10-反笙_FreeCAD"))
sys.path.insert(0, str(ROOT))

from fc_reverse import FCReverse  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sketch_fixture.FCStd"


def _reverse():
    r = FCReverse.reverse(str(FIXTURE))
    assert r["ok"], r
    return r["ops"], r["meta"]


def test_sketch_op_emitted():
    ops, _ = _reverse()
    sk = [o for o in ops if o["op"] == "sketch"]
    assert len(sk) == 1
    assert sk[0]["id"] == "Sketch"


def test_sketch_geometry():
    ops, _ = _reverse()
    sk = next(o for o in ops if o["op"] == "sketch")
    geos = sk["geometry"]
    assert len(geos) == 8
    kinds = [g["type"] for g in geos]
    assert kinds.count("line") == 5
    assert kinds.count("circle") == 1
    assert kinds.count("arc") == 1
    assert kinds.count("point") == 1
    circle = next(g for g in geos if g["type"] == "circle")
    assert circle["center"] == [30.0, 20.0] and circle["radius"] == 8.0
    arc = next(g for g in geos if g["type"] == "arc")
    assert arc["radius"] == 10.0 and abs(arc["end_angle"] - 1.5707963) < 1e-5
    # 构造几何: 对角线 + 点
    cons_geo = [g for g in geos if g.get("construction")]
    assert len(cons_geo) == 2
    assert {g["type"] for g in cons_geo} == {"line", "point"}


def test_sketch_constraints():
    ops, _ = _reverse()
    sk = next(o for o in ops if o["op"] == "sketch")
    cons = sk["constraints"]
    types = [c["type"] for c in cons]
    assert types.count("Coincident") == 2
    for expected in ("Horizontal", "Vertical", "Distance", "Radius"):
        assert expected in types
    dist = next(c for c in cons if c["type"] == "Distance")
    assert dist["value"] == 60.0 and dist["first"] == 0
    rad = next(c for c in cons if c["type"] == "Radius")
    assert rad["value"] == 8.0 and rad["first"] == 4
    coin = next(c for c in cons if c["type"] == "Coincident")
    assert coin["first_pos"] == 2 and coin["second_pos"] == 1


def test_pad_links_sketch():
    ops, _ = _reverse()
    pad = next(o for o in ops if o["op"] == "partdesign_pad")
    assert pad["face"] == "Sketch"
    assert pad["length"] == 15.0
    # sketch 先于 pad (依赖拓扑序)
    idx = {o["id"]: i for i, o in enumerate(ops) if "id" in o}
    assert idx["Sketch"] < idx["Pad"]


def test_patch_pad_length():
    ops, _ = _reverse()
    patched = FCReverse.patch(ops, {"Pad.length": 30})
    pad = next(o for o in patched if o["op"] == "partdesign_pad")
    assert pad["length"] == 30.0
    # 原 ops 不被修改
    assert next(o for o in ops if o["op"] == "partdesign_pad")["length"] == 15.0
