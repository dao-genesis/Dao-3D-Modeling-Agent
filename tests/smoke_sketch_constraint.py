"""Sketcher constraint smoke — DoF arithmetic + fully-constrained freeform.

A real parametric sketch must reach DoF=0 (fully constrained) or the solver
leaves the geometry free to drift. This suite proves the constraint accounting
on real Sketcher solver feedback (``param.diagnose`` reads DoF / conflicting /
redundant / malformed directly off the live sketch object):

  * a freeform polygon is honestly UNDER-constrained by default (DoF = 2n minus
    the coincidence loop) -- diagnose reports it, all_healthy is False;
  * with ``constrain: true`` every vertex is pinned, driving DoF -> 0 with NO
    redundant or conflicting constraint, and the profile still pads to a solid;
  * the canned ``rect`` profile is fully constrained out of the box (DoF 0).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402

POLY = [[0, 0], [50, 0], [50, 30], [20, 45], [0, 30]]  # 5-vertex freeform


def _diag(s, name):
    for sk in s.act("param.diagnose", {}).data["sketches"]:
        if sk["sketch"] == name:
            return sk
    raise AssertionError("sketch %r not found" % name)


def main():
    s = new_session("sketch_constraint")
    print("FreeCAD", s.registry.kernel.freecad_version)
    n = len(POLY)

    # 1) rect: fully constrained out of the box
    s.act("param.body", {"name": "Br"})
    r = s.act("param.sketch", {"body": "Br", "name": "rectsk", "profile": {"rect": [40, 25]}})
    assert r.ok, r.error
    assert r.data["dof"] == 0 and r.data["fully_constrained"], r.data

    # 2) freeform polygon, default: under-constrained, honestly reported
    s.act("param.body", {"name": "Bu"})
    ru = s.act("param.sketch", {"body": "Bu", "name": "polyfree", "profile": {"polygon": POLY}})
    assert ru.ok, ru.error
    free = _diag(s, "polyfree")
    print("  freeform : dof=%d fc=%s  (expected 2n-loop=%d)"
          % (free["dof"], free["fully_constrained"], 2 * n - 0))
    assert free["dof"] == 2 * n, (free, 2 * n)   # 5 vertices x 2 - 0 = 10
    assert not free["fully_constrained"]

    # 3) freeform polygon, constrained: DoF -> 0, no redundant/conflicting
    s.act("param.body", {"name": "Bc"})
    rc = s.act("param.pad", {"body": "Bc", "feature": "Plate", "length": 8,
                             "profile": {"polygon": POLY, "constrain": True}})
    assert rc.ok, rc.error
    con = _diag(s, "Plate_sk")
    print("  constrained: dof=%d fc=%s redun=%s conflict=%s malformed=%s"
          % (con["dof"], con["fully_constrained"], con["redundant"],
             con["conflicting"], con["malformed"]))
    assert con["dof"] == 0, con
    assert con["fully_constrained"], con
    assert not con["redundant"] and not con["conflicting"] and not con["malformed"], con

    # the constrained profile is real geometry: it pads to a solid
    vol = s.act("param.measure", {"body": "Bc"}).data["volume"]
    print("  padded solid volume = %.1f mm^3" % vol)
    assert vol > 0, vol

    print("SKETCH CONSTRAINT SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_sketch_constraint"):
    main()
