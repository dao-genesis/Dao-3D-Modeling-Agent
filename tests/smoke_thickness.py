"""Wall-thickness smoke — minimum wall DFM check (mould/cast/print thin walls).

``solid.thickness`` fires a ray into the solid along the inward normal from a
grid of face sample points and measures the chord it cuts through the material;
the smallest chord over the whole part is the minimum wall thickness. Validated
against closed-form geometry (the minimum wall of a convex solid is its smallest
width, and a uniformly hollowed shell's wall is its shell thickness):

  * solid box 40x30x20 -> min wall = 20 (smallest dimension);
  * solid cylinder r15 h20 -> min wall = 20 (height < diameter 30);
  * thin plate 50x50x4 -> min wall = 4, fails a 5 mm rule;
  * box hollowed to a 3 mm shell -> min wall = 3 exactly, fails a 5 mm rule.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def main():
    s = new_session("thickness")
    print("FreeCAD", s.registry.kernel.freecad_version)

    s.act("solid.box", {"name": "b", "length": 40, "width": 30, "height": 20})
    b = s.act("solid.thickness", {"name": "b", "min_wall": 5}).data
    print("box 40x30x20 -> min_thickness=%.3f ok=%s" % (b["min_thickness"], b["ok"]))
    assert abs(b["min_thickness"] - 20.0) < 1e-3 and b["ok"], b

    s.act("solid.cylinder", {"name": "c", "radius": 15, "height": 20})
    c = s.act("solid.thickness", {"name": "c", "min_wall": 5}).data
    print("cyl r15 h20  -> min_thickness=%.3f ok=%s" % (c["min_thickness"], c["ok"]))
    assert abs(c["min_thickness"] - 20.0) < 1e-3 and c["ok"], c

    s.act("solid.box", {"name": "p", "length": 50, "width": 50, "height": 4})
    p = s.act("solid.thickness", {"name": "p", "min_wall": 5}).data
    print("plate t4     -> min_thickness=%.3f ok=%s thin=%d"
          % (p["min_thickness"], p["ok"], len(p["thin_walls"])))
    assert abs(p["min_thickness"] - 4.0) < 1e-3 and not p["ok"], p

    # hollow the box into a 3 mm shell (one open face) -> every wall is 3 mm.
    s.act("solid.box", {"name": "h0", "length": 40, "width": 40, "height": 20})
    assert s.act("solid.shell", {"name": "h0", "out": "h", "thickness": -3,
                                 "open_faces": [5]}).ok
    h = s.act("solid.thickness", {"name": "h", "min_wall": 5, "samples": 4}).data
    print("shell wall   -> min_thickness=%.3f ok=%s thin=%d"
          % (h["min_thickness"], h["ok"], len(h["thin_walls"])))
    assert abs(h["min_thickness"] - 3.0) < 1e-3 and not h["ok"], h

    print("THICKNESS SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_thickness"):
    main()
