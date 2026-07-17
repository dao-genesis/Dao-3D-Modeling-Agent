# -*- coding: utf-8 -*-
"""fc_dag 特征依赖图单测 (纯 Python · 无需 FreeCAD)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "10-反笙_FreeCAD"))

from fc_dag import FCDag  # noqa: E402

# 两条独立链 + 一次汇聚:
#   A → C(cut base=A tool=B) → E(fillet shape=C)
#   B ↗
#   D (独立旁支)
OPS = [
    {"op": "box", "id": "A", "length": 10},
    {"op": "cylinder", "id": "B", "radius": 3},
    {"op": "cut", "id": "C", "base": "A", "tool": "B"},
    {"op": "fillet", "id": "E", "shape": "C", "radius": 1},
    {"op": "box", "id": "D", "length": 5},
]


def test_build_graph():
    g = FCDag.build(OPS)
    assert g["deps"]["C"] == ["A", "B"] and g["deps"]["E"] == ["C"]
    assert g["rdeps"]["A"] == ["C"] and g["rdeps"]["C"] == ["E"]
    assert g["roots"] == ["A", "B", "D"] and g["leaves"] == ["E", "D"]
    assert g["cycles"] == []
    o = g["order"]
    assert o.index("A") < o.index("C") < o.index("E")
    assert o.index("B") < o.index("C")


def test_affected_downstream_only():
    assert FCDag.affected(OPS, ["A"]) == ["A", "C", "E"]
    assert FCDag.affected(OPS, ["C"]) == ["C", "E"]
    assert FCDag.affected(OPS, ["D"]) == ["D"]


def test_subset_upstream_closure():
    ids = [o["id"] for o in FCDag.subset(OPS, ["E"])]
    assert ids == ["A", "B", "C", "E"]  # 不含无关旁支 D
    assert [o["id"] for o in FCDag.subset(OPS, ["D"])] == ["D"]


def test_patch_plan_incremental():
    plan = FCDag.patch_plan(OPS, {"A.length": 20})
    assert plan["changed"] == ["A"]
    assert plan["affected"] == ["A", "C", "E"]
    ids = [o["id"] for o in plan["replay_ops"]]
    assert ids == ["A", "B", "C", "E"]  # B 是上游依赖必须带上, D 被跳过
    assert plan["skipped"] == 1
    assert next(o for o in plan["replay_ops"] if o["id"] == "A")["length"] == 20.0


def test_patch_plan_side_branch_skips_chain():
    plan = FCDag.patch_plan(OPS, {"D.length": 8})
    assert plan["affected"] == ["D"]
    assert [o["id"] for o in plan["replay_ops"]] == ["D"]
    assert plan["skipped"] == 4


def test_cycle_detected():
    g = FCDag.build([
        {"op": "x", "id": "P", "base": "Q"},
        {"op": "x", "id": "Q", "base": "P"},
    ])
    assert g["cycles"] == ["P", "Q"]
