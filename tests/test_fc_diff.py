# -*- coding: utf-8 -*-
"""fc_diff 模型级语义 diff/merge 单测 (纯 Python · 无需 FreeCAD)."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "10-反笙_FreeCAD"))

from fc_diff import FCDiff  # noqa: E402
from fc_reverse import FCReverse  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def _ops(name):
    return FCReverse.reverse(str(FIX / name))["ops"]


def test_identical_same_file():
    d = FCDiff.diff_files(str(FIX / "sketch_ext_fixture.FCStd"),
                          str(FIX / "sketch_ext_fixture.FCStd"))
    assert d["identical"]
    assert d["summary"] == {"added": 0, "removed": 0, "changed": 0}


def test_numeric_tolerance():
    a = _ops("sketch_ext_fixture.FCStd")
    b = copy.deepcopy(a)
    g = next(g for g in b[0]["geometry"] if g["type"] == "ellipse")
    g["major_radius"] += 1e-12
    assert FCDiff.diff(a, b)["identical"]


def test_param_change_and_sketch_diff():
    a = _ops("sketch_ext_fixture.FCStd")
    b = copy.deepcopy(a)
    g = next(g for g in b[0]["geometry"] if g["type"] == "ellipse")
    g["major_radius"] = 15.0
    d = FCDiff.diff(a, b)
    assert not d["identical"] and d["summary"]["changed"] == 1
    ch = d["changed"][0]
    assert ch["op"] == "sketch"
    sk = ch["sketch"]["geometry"]
    assert sk["added"] == [] and sk["removed"] == []
    assert sk["changed"][0]["key"] == "ellipse#1"
    c = sk["changed"][0]["changes"][0]
    assert c["path"] == "major_radius" and c["before"] == 10.0 and c["after"] == 15.0


def test_geometry_add_remove():
    a = _ops("sketch_ext_fixture.FCStd")
    b = copy.deepcopy(a)
    b[0]["geometry"] = [g for g in b[0]["geometry"] if g["type"] != "bspline"]
    b[0]["geometry"].append({"type": "circle", "center": [1, 1], "radius": 2.0})
    sk = FCDiff.diff(a, b)["changed"][0]["sketch"]["geometry"]
    assert sk["added"] == ["circle#1"] and sk["removed"] == ["bspline#1"]


def test_object_add_remove():
    a = _ops("sketch_ext_fixture.FCStd")
    b = copy.deepcopy(a) + [{"op": "box", "id": "B1", "length": 10}]
    d = FCDiff.diff(a, b)
    assert d["added"] == [{"id": "B1", "op": "box"}]
    d2 = FCDiff.diff(b, a)
    assert d2["removed"] == [{"id": "B1", "op": "box"}]


def test_merge3_non_overlapping():
    base = _ops("sketch_ext_fixture.FCStd") + [{"op": "box", "id": "B1", "length": 10}]
    ours = copy.deepcopy(base)
    next(g for g in ours[0]["geometry"] if g["type"] == "ellipse")["major_radius"] = 12.0
    theirs = copy.deepcopy(base)
    theirs[1]["length"] = 20
    m = FCDiff.merge3(base, ours, theirs)
    assert m["clean"]
    ops = {o["id"]: o for o in m["ops"]}
    assert next(g for g in ops["Sk"]["geometry"] if g["type"] == "ellipse")["major_radius"] == 12.0
    assert ops["B1"]["length"] == 20


def test_merge3_conflict():
    base = [{"op": "box", "id": "B1", "length": 10}]
    ours = [{"op": "box", "id": "B1", "length": 20}]
    theirs = [{"op": "box", "id": "B1", "length": 30}]
    m = FCDiff.merge3(base, ours, theirs)
    assert not m["clean"]
    c = m["conflicts"][0]
    assert c["id"] == "B1"
    assert c["ours_changes"][0]["after"] == 20
    assert c["theirs_changes"][0]["after"] == 30
    assert m["ops"][0]["length"] == 20  # 冲突默认保留 ours


def test_merge3_add_delete():
    base = [{"op": "box", "id": "B1", "length": 10}]
    ours = base + [{"op": "cyl", "id": "C1", "radius": 3}]
    theirs = []  # 删除 B1
    m = FCDiff.merge3(base, ours, theirs)
    assert m["clean"]
    ids = [o["id"] for o in m["ops"]]
    assert ids == ["C1"]
