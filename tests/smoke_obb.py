"""OBB smoke -- oriented bounding box / natural-frame recovery vs closed form.

A real reverse job starts from a part sitting at some arbitrary placement; its
axis-aligned box is meaningless. ``solid.obb`` must recover the part's own frame
and true size regardless of orientation:

  * a box L x W x H rotated to a generic pose: the OBB edge lengths come back as
    exactly {L,W,H} and the fill ratio Vol/Vol_obb = 1, while the naive AABB is
    strictly larger -- proving the oriented box is the tight one ;
  * a cylinder (R,H): OBB is 2R x 2R x H and the fill ratio is pi/4 ;
  * a sphere (R): OBB is the cube (2R)^3 and the fill ratio is pi/6 ;
  * the three recovered axes are orthonormal ;
  * a non-solid and a missing solid are refused loudly.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def _close(a, b, rel=3e-3):
    return abs(a - b) <= rel * max(1.0, abs(b))


def _dot(u, v):
    return sum(x * y for x, y in zip(u, v))


def main():
    s = new_session("obb")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # ---- arbitrarily rotated box: dims + frame recovered, AABB inflated -- #
    L, W, H = 30.0, 18.0, 7.0
    s.act("solid.box", {"name": "blk", "length": L, "width": W, "height": H})
    s.act("solid.rotate", {"name": "blk", "center": [0, 0, 0],
                           "axis": [1, 1, 1], "angle": 37.0, "out": "rot"})
    r = s.act("solid.obb", {"name": "rot"}).data
    assert all(_close(g, e) for g, e in zip(r["sorted_dimensions"], sorted([L, W, H]))), r
    assert _close(r["fill_ratio"], 1.0), r["fill_ratio"]
    assert _close(r["obb_volume"], L * W * H), r["obb_volume"]
    aabb_vol = r["aabb_size"][0] * r["aabb_size"][1] * r["aabb_size"][2]
    assert aabb_vol > r["obb_volume"] * 1.05, (aabb_vol, r["obb_volume"])
    ax = r["axes"]
    for i in range(3):
        assert _close(_dot(ax[i], ax[i]), 1.0), ax           # unit
    assert _close(_dot(ax[0], ax[1]), 0.0) and _close(_dot(ax[0], ax[2]), 0.0) \
        and _close(_dot(ax[1], ax[2]), 0.0), ax              # orthogonal
    print("rotated box: OBB dims %s == {L,W,H}, fill=1.0, AABB vol %.0f > OBB %.0f"
          % (r["sorted_dimensions"], aabb_vol, r["obb_volume"]))

    # ---- cylinder: 2R x 2R x H, fill = pi/4 ----------------------------- #
    R, Hc = 8.0, 40.0
    s.act("solid.cylinder", {"name": "cyl", "radius": R, "height": Hc})
    rc = s.act("solid.obb", {"name": "cyl"}).data
    assert all(_close(g, e) for g, e in zip(rc["sorted_dimensions"],
                                            sorted([2 * R, 2 * R, Hc]))), rc
    assert _close(rc["fill_ratio"], math.pi / 4.0), rc["fill_ratio"]
    print("cylinder: OBB %s == {2R,2R,H}, fill=%.4f == pi/4"
          % (rc["sorted_dimensions"], rc["fill_ratio"]))

    # ---- sphere: (2R)^3 cube, fill = pi/6 ------------------------------- #
    Rs = 12.0
    s.act("solid.sphere", {"name": "sph", "radius": Rs})
    rs = s.act("solid.obb", {"name": "sph"}).data
    assert all(_close(d, 2 * Rs) for d in rs["sorted_dimensions"]), rs
    assert _close(rs["fill_ratio"], math.pi / 6.0), rs["fill_ratio"]
    print("sphere: OBB %s == (2R)^3 cube, fill=%.4f == pi/6"
          % (rs["sorted_dimensions"], rs["fill_ratio"]))

    # ---- single-solid Part.Compound (a boolean result, like an imported   #
    #      STEP) must work, not crash on the missing PrincipalProperties --- #
    s.act("solid.box", {"name": "ba", "length": 30, "width": 18, "height": 7})
    s.act("solid.box", {"name": "bb", "length": 30, "width": 18, "height": 7})
    s.act("solid.translate", {"name": "bb", "vector": [10, 0, 0]})
    s.act("solid.union", {"a": "ba", "b": "bb", "out": "merged"})  # -> 1-solid compound
    s.act("solid.rotate", {"name": "merged", "center": [0, 0, 0],
                           "axis": [1, 2, 3], "angle": 41.0})
    rm = s.act("solid.obb", {"name": "merged"})
    assert rm.ok, "obb crashed on single-solid compound: %s" % rm.error
    # the merged block is 40 x 18 x 7
    assert all(_close(g, e) for g, e in zip(rm.data["sorted_dimensions"],
                                            sorted([40.0, 18.0, 7.0]))), rm.data
    assert _close(rm.data["fill_ratio"], 1.0), rm.data["fill_ratio"]
    print("single-solid compound (boolean/STEP-like): OBB %s, fill=1.0"
          % rm.data["sorted_dimensions"])

    # ---- a genuine multi-solid compound is refused loudly --------------- #
    s.act("solid.box", {"name": "m1", "length": 8, "width": 8, "height": 8})
    s.act("solid.box", {"name": "m2", "length": 8, "width": 8, "height": 8})
    s.act("solid.translate", {"name": "m2", "vector": [40, 0, 0]})
    s.act("solid.compound", {"names": ["m1", "m2"], "out": "two"})
    bad_multi = s.act("solid.obb", {"name": "two"})
    assert not bad_multi.ok and "single solid" in (bad_multi.error or "").lower(), bad_multi.error
    print("multi-solid compound refused: %s" % bad_multi.error)

    # ---- a non-solid shell is refused loudly ---------------------------- #
    s.act("solid.box", {"name": "sbx", "length": 20, "width": 20, "height": 20})
    s.act("solid.shell", {"name": "sbx", "thickness": -2, "open_faces": [0, 1],
                          "out": "openshell"})
    bad_shell = s.act("solid.obb", {"name": "openshell"})
    if not bad_shell.ok:
        assert "needs a solid" in (bad_shell.error or "").lower(), bad_shell.error
        print("open shell refused: %s" % bad_shell.error)

    # ---- a missing solid is refused loudly ------------------------------ #
    bad = s.act("solid.obb", {"name": "nope"})
    assert not bad.ok and "no such solid" in (bad.error or "").lower()
    print("missing solid refused: %s" % bad.error)

    print("OBB SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_obb"):
    main()
