"""Reverse-pipeline capstone -- the whole 'butcher the ox' in one call.

``solid.reverse`` is to the reverse layer what ``solid.dfm_report`` is to DFM:
a single editorial front that runs decompose -> recognize (parametric BOM) ->
joints -> Kutzbach mobility and hands back one structured model.

Two ends of the spectrum are exercised:

1. A parametric BOM: a compound of clean primitives (box + cylinder + tube)
   comes back with each part named and dimensioned, ready to re-emit.
2. A real mechanism: the slider-crank (frame/crank/rod/slider) comes back with
   every machined part honestly ``freeform`` (they are blocks-with-bores, not
   primitives) yet the *kinematics* are fully recovered -- 3 revolute + 1
   prismatic, a closed 4-link loop at Kutzbach planar mobility 1.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402
from tests.smoke_mechanism import build_slidercrank  # noqa: E402


def main():
    s = new_session("reverse_pipeline")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # ---- 1. parametric BOM from a monolithic compound of primitives ------- #
    s.act("solid.box", {"name": "b", "length": 12, "width": 8, "height": 6, "pos": [0, 0, 0]})
    s.act("solid.cylinder", {"name": "c", "radius": 4, "height": 14, "pos": [40, 0, 0]})
    s.act("solid.cylinder", {"name": "to", "radius": 7, "height": 10, "pos": [0, 40, 0]})
    s.act("solid.cylinder", {"name": "ti", "radius": 4, "height": 10, "pos": [0, 40, 0]})
    s.act("solid.cut", {"a": "to", "b": "ti", "out": "t"})
    s.act("solid.compound", {"names": ["b", "c", "t"], "out": "blob"})
    rv = s.act("solid.reverse", {"name": "blob"})
    assert rv.ok, rv.error
    assert rv.data["parts"] == 3, rv.data
    assert rv.data["part_types"] == {"box": 1, "cylinder": 1, "tube": 1}, rv.data["part_types"]
    # every BOM entry carries recovered driving dimensions
    by = {e["type"]: e["params"] for e in rv.data["bom"]}
    assert abs(by["tube"]["outer_radius"] - 7) < 1e-6 and abs(by["tube"]["inner_radius"] - 4) < 1e-6, by
    assert abs(by["cylinder"]["radius"] - 4) < 1e-6 and abs(by["cylinder"]["height"] - 14) < 1e-6, by
    assert sorted(by["box"][k] for k in ("length", "width", "height")) == [6.0, 8.0, 12.0], by
    print("parametric BOM: %s" % rv.data["part_types"])

    # ---- 2. full reverse of the slider-crank (kinematics recovered) ------- #
    parts = build_slidercrank(s)
    rv2 = s.act("solid.reverse", {"parts": parts})
    assert rv2.ok, rv2.error
    # machined parts are honestly freeform, not faked primitives
    assert rv2.data["part_types"].get("freeform") == 4, rv2.data["part_types"]
    # ...but the mechanism is fully recovered
    assert rv2.data["joint_types"] == {"revolute": 3, "prismatic": 1}, rv2.data["joint_types"]
    assert rv2.data["mobility_planar"] == 1, rv2.data
    print("slider-crank reverse: %d parts (all freeform), joints %s, mobility = %d"
          % (rv2.data["parts"], rv2.data["joint_types"], rv2.data["mobility_planar"]))

    print("REVERSE-PIPELINE SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_reverse_pipeline"):
    main()
