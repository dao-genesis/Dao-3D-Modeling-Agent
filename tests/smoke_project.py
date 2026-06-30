"""复杂项目 capstone -- one natural-language brief, one real multi-step part.

The other suites prove single ops and a fixed pipeline. This proves the
*orchestration* the brief keeps asking for: a genuinely complex project
(a flanged mounting bracket -- plate + boss, a central bore, a four-hole
mounting pattern) is described as one multi-intent NL script and executed as a
single fused build on the live FreeCAD kernel, threading object names across
nineteen steps. Then the recovered solid is *perceived* (measure + bbox) and
*sectioned*, proving the modelling and analysis workbenches stay coupled.

The final volume is checked against the closed form, so a regression anywhere
in the planner -> kernel chain (a mis-threaded name, a dropped boolean) moves
the number and fails the suite:

    plate 80x50x10                         = 40000.00
    + boss r8 h24 protruding above plate   + pi*8^2*14  = +2814.87
    - central bore r4 h24                  - pi*4^2*24  = -1206.37
    - 4x mounting holes r3 h10             - 4*pi*3^2*10 = -1130.97
                                           = 40477.53
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402

_RAW = ("TypeError", "AttributeError", "could not convert", "has no attribute",
        "KeyError", "OCCError", "Standard_", "NullShape", "NoneType")


def main():
    s = new_session("project")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # one human brief -> nineteen kernel steps, names threaded throughout.
    brief = (
        "box length 80 width 50 height 10 name plate; "      # base plate
        "cylinder r=8 h=24 name boss; "                       # raised boss
        "move boss by 40 25 0; "                              # centre it
        "fuse boss and plate; "                               # weld boss->plate
        "cylinder r=4 h=24 name bore; "                       # central bore
        "move bore by 40 25 0; "
        "cut bore from boss; "                                # drill it through
        "cylinder r=3 h=10 name m1; move m1 by 10 10 0; cut m1 from boss; "
        "cylinder r=3 h=10 name m2; move m2 by 70 10 0; cut m2 from boss; "
        "cylinder r=3 h=10 name m3; move m3 by 10 40 0; cut m3 from boss; "
        "cylinder r=3 h=10 name m4; move m4 by 70 40 0; cut m4 from boss")
    r = s.build(brief)
    assert r.ok, r.error
    assert r.data["lines"] == 19, r.data
    assert r.data["executed"] == 19 and r.data["failed"] == 0, r.data
    # every recorded step must be guided, never a raw kernel leak.
    for e in r.data["transcript"]:
        for st in e["steps"]:
            err = st.get("error") or ""
            assert not any(x in err for x in _RAW), "raw leak: %r" % err

    # the build threaded to a single valid solid named after the fuse target.
    expect = (40000.0 + math.pi * 8 * 8 * 14
              - math.pi * 4 * 4 * 24 - 4 * math.pi * 3 * 3 * 10)
    m = s.act("solid.measure", {"name": "boss"})
    assert m.ok, m.error
    assert m.data["valid"], m.data
    assert abs(m.data["volume"] - expect) < 1.0, (m.data["volume"], expect)

    # perception fuses with modelling: bbox reflects plate footprint + boss tip.
    bb = s.act("analyze.bbox", {"name": "boss"})
    assert bb.ok and bb.data["size"] == [80, 50, 24], bb.data

    # and the part can be sectioned (analysis workbench consumes the product).
    sec = s.act("analyze.section", {"name": "boss", "plane": "XY", "offset": 5})
    assert sec.ok, sec.error

    print("project capstone: 19-step bracket -> vol %.2f (exp %.2f) bbox %s, "
          "sectioned ok" % (m.data["volume"], expect, bb.data["size"]))
    print("PROJECT SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_project"):
    main()
