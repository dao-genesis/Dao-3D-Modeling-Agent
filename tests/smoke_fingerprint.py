"""Fingerprint smoke -- the pose/scale-invariant shape key, cross-checked.

A model-library key is only useful if it is genuinely invariant. We prove it:

  * a box and the SAME box moved+rotated to a generic pose share one shape_key
    and identical invariant fields (the rigid motion changes nothing) ;
  * the same box scaled up (all dims x2) still shares the shape_key -- the key
    is scale-free -- while its volume grows 8x and OBB dims 2x ;
  * the isoperimetric ratio A^3/V^2 is exact: 216 for a cube, 36*pi for a
    sphere (its theoretical minimum) ;
  * a sphere and a cube produce different shape_keys ;
  * a non-single-solid input is refused loudly.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def _close(a, b, rel=3e-3):
    return abs(a - b) <= rel * max(1.0, abs(b))


def main():
    s = new_session("fingerprint")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # ---- pose invariance: move+rotate leaves the key untouched ---------- #
    s.act("solid.box", {"name": "blk", "length": 20, "width": 30, "height": 40})
    f0 = s.act("solid.fingerprint", {"name": "blk"}).data
    s.act("solid.box", {"name": "blk2", "length": 20, "width": 30, "height": 40})
    s.act("solid.rotate", {"name": "blk2", "center": [0, 0, 0],
                           "axis": [1, 2, 3], "angle": 41.0})
    s.act("solid.translate", {"name": "blk2", "vector": [123, -77, 55]})
    f1 = s.act("solid.fingerprint", {"name": "blk2"}).data
    assert f1["shape_key"] == f0["shape_key"], (f0["shape_key"], f1["shape_key"])
    assert f1["obb_dimensions"] == f0["obb_dimensions"], (f0, f1)
    assert _close(f1["volume"], f0["volume"]), (f0["volume"], f1["volume"])
    print("pose-invariant: moved+rotated box keeps key %s" % f0["shape_key"])

    # ---- scale invariance: x2 box keeps the key, size scales ------------ #
    s.act("solid.box", {"name": "big", "length": 40, "width": 60, "height": 80})
    fb = s.act("solid.fingerprint", {"name": "big"}).data
    assert fb["shape_key"] == f0["shape_key"], (f0["shape_key"], fb["shape_key"])
    assert _close(fb["volume"], 8.0 * f0["volume"]), (fb["volume"], f0["volume"])
    assert all(_close(d2, 2.0 * d1) for d1, d2 in zip(f0["obb_dimensions"], fb["obb_dimensions"]))
    print("scale-invariant: x2 box keeps key, volume x%.2f" % (fb["volume"] / f0["volume"]))

    # ---- isoperimetric: cube = 216, sphere = 36*pi (the minimum) -------- #
    s.act("solid.box", {"name": "cube", "length": 10, "width": 10, "height": 10})
    fc = s.act("solid.fingerprint", {"name": "cube"}).data
    assert _close(fc["isoperimetric"], 216.0), fc["isoperimetric"]
    s.act("solid.sphere", {"name": "sph", "radius": 7})
    fs = s.act("solid.fingerprint", {"name": "sph"}).data
    assert _close(fs["isoperimetric"], 36.0 * math.pi), fs["isoperimetric"]
    assert fs["shape_key"] != fc["shape_key"], "sphere and cube must differ"
    print("cube A^3/V^2=%.3f == 216 ; sphere=%.3f == 36pi=%.3f"
          % (fc["isoperimetric"], fs["isoperimetric"], 36.0 * math.pi))

    # ---- a non-single-solid input is refused loudly --------------------- #
    s.act("solid.box", {"name": "p1", "length": 5, "width": 5, "height": 5})
    s.act("solid.box", {"name": "p2", "length": 5, "width": 5, "height": 5})
    s.act("solid.translate", {"name": "p2", "vector": [50, 0, 0]})
    s.act("solid.compound", {"names": ["p1", "p2"], "out": "pair"})
    bad = s.act("solid.fingerprint", {"name": "pair"})
    if not bad.ok:
        assert "single solid" in (bad.error or "").lower(), bad.error
        print("two-solid compound refused: %s" % bad.error)

    missing = s.act("solid.fingerprint", {"name": "nope"})
    assert not missing.ok and "no such solid" in (missing.error or "").lower()
    print("missing solid refused: %s" % missing.error)

    print("FINGERPRINT SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_fingerprint"):
    main()
