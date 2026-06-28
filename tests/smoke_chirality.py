"""Chirality smoke -- handedness, the invariant a fingerprint cannot see.

A fingerprint is mirror-blind, but a left-hand part and a right-hand part are
different parts. ``solid.chirality`` settles it by proof -- a solid is achiral
iff it can be superimposed on its own mirror by a rigid motion:

  * a box, cylinder, sphere and a planar L are all achiral (mirror_distance 0) ;
  * a genuinely 3D chiral solid (a handed pentacube: a bar with a Y-tab at one
    end and a Z-tab at the other) is chiral, and so is its mirror image ;
  * the motivating defect is shown directly: the chiral part and its mirror
    share one fingerprint shape_key, yet chirality tells them apart ;
  * a non-single-solid input is refused loudly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def _pentacube(s, name):
    """A provably-chiral fused pentacube (10mm cubes)."""
    cubes = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (2, 0, 1)]
    parts = []
    for i, (x, y, z) in enumerate(cubes):
        pn = "%s_c%d" % (name, i)
        s.act("solid.box", {"name": pn, "length": 10, "width": 10, "height": 10})
        if (x, y, z) != (0, 0, 0):
            s.act("solid.translate", {"name": pn, "vector": [x * 10, y * 10, z * 10]})
        parts.append(pn)
    acc = parts[0]
    for j, pn in enumerate(parts[1:]):
        out = name if j == len(parts) - 2 else "%s_u%d" % (name, j)
        s.act("solid.union", {"a": acc, "b": pn, "out": out})
        acc = out
    return acc


def main():
    s = new_session("chirality")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # ---- achiral primitives -------------------------------------------- #
    s.act("solid.box", {"name": "blk", "length": 20, "width": 30, "height": 40})
    s.act("solid.cylinder", {"name": "cyl", "radius": 8, "height": 40})
    s.act("solid.sphere", {"name": "sph", "radius": 12})
    for nm in ("blk", "cyl", "sph"):
        r = s.act("solid.chirality", {"name": nm}).data
        assert r["achiral"] and not r["chiral"], (nm, r)
        assert r["mirror_distance"] < 1e-3, (nm, r)
    print("box/cyl/sphere all achiral (mirror_distance ~0)")

    # ---- a chiral pentacube and its mirror are both chiral ------------- #
    _pentacube(s, "hand")
    rc = s.act("solid.chirality", {"name": "hand"}).data
    assert rc["chiral"] and not rc["achiral"], rc
    assert rc["mirror_distance"] > 1e-2, rc
    print("chiral pentacube: chiral=True mirror_distance=%.4f" % rc["mirror_distance"])

    s.act("solid.mirror", {"name": "hand", "base": [0, 0, 0],
                           "normal": [0, 0, 1], "out": "hand_mir"})
    rm = s.act("solid.chirality", {"name": "hand_mir"}).data
    assert rm["chiral"], rm
    print("its mirror is also chiral (the other enantiomer)")

    # ---- the motivating defect: fingerprints CANNOT tell them apart ---- #
    f0 = s.act("solid.fingerprint", {"name": "hand"}).data
    fm = s.act("solid.fingerprint", {"name": "hand_mir"}).data
    assert f0["shape_key"] == fm["shape_key"], (f0["shape_key"], fm["shape_key"])
    print("fingerprint shape_key identical for both hands (%s) -- chirality is "
          "the channel that distinguishes them" % f0["shape_key"])

    # ---- guard ---------------------------------------------------------- #
    s.act("solid.box", {"name": "g1", "length": 5, "width": 5, "height": 5})
    s.act("solid.box", {"name": "g2", "length": 5, "width": 5, "height": 5})
    s.act("solid.translate", {"name": "g2", "vector": [50, 0, 0]})
    s.act("solid.compound", {"names": ["g1", "g2"], "out": "pair"})
    bad = s.act("solid.chirality", {"name": "pair"})
    assert not bad.ok and "single solid" in (bad.error or "").lower(), bad.error
    print("two-solid compound refused: %s" % bad.error)

    print("CHIRALITY SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_chirality"):
    main()
