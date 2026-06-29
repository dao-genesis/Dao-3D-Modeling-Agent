"""Fillets smoke -- recover edge blends (fillets/rounds), the "break every sharp
edge" channel of reverse engineering.

``holes`` recovers full-round bores and turned bosses; the other pervasive
manufacturing intent is rounding edges. ``solid.fillets`` reads the blends off
analytic surfaces and the answers are cross-checked closed-form against parts we
build with a known blend radius:

  * round all 12 edges of an L x W x H box at radius r -> 12 cylindrical *round*
    features (one per edge) plus 8 spherical corner rounds, all radius r, and a
    total blended edge length of sum(edge - 2r) (each corner eats r off both
    ends of the three edges meeting there) ;
  * a boss standing on a plate, filleted at its foot -> the re-entrant circular
    edge yields a *toroidal fillet* (concave) whose minor radius is r, told
    apart from the convex rounds by the true outward-normal sign ;
  * a plain (un-blended) block has no blends ;
  * a non-solid / multi-solid input is refused loudly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def main():
    s = new_session("fillets")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # ---- round every edge of a box: 12 cylinders + 8 sphere corners -------- #
    L, W, H, r = 40.0, 30.0, 20.0, 2.0
    s.act("solid.box", {"name": "b", "length": L, "width": W, "height": H})
    s.act("solid.fillet", {"name": "b", "radius": r, "out": "bf"})
    d = s.act("solid.fillets", {"name": "bf"}).data
    assert d["fillet_count"] == 0, d            # every box edge is convex -> rounds
    assert d["round_count"] == 20, d            # 12 edges + 8 corners
    assert d["radii"] == [r], d
    cyl = [g for g in d["blend_groups"] if g["geom"] == "cylinder"]
    sph = [g for g in d["blend_groups"] if g["geom"] == "sphere"]
    assert len(cyl) == 1 and cyl[0]["count"] == 12, cyl
    assert len(sph) == 1 and sph[0]["count"] == 8, sph
    # each of the 8 corners eats r off both ends of the 3 edges meeting there,
    # so every edge is shortened by 2r: total blended length = sum(edge - 2r).
    expect_len = 4 * ((L - 2 * r) + (W - 2 * r) + (H - 2 * r))
    assert abs(cyl[0]["edge_length"] - expect_len) < 1e-3, (cyl[0]["edge_length"], expect_len)
    print("box rounds: 12 cyl + 8 sphere @ r%g, blended edge length=%g (expect %g)"
          % (r, cyl[0]["edge_length"], expect_len))

    # ---- a boss on a plate, filleted at its foot -> a concave torus fillet -- #
    s.act("solid.box", {"name": "pl", "length": 40, "width": 40, "height": 6})
    s.act("solid.cylinder", {"name": "bo", "radius": 6, "height": 14, "pos": [20, 20, 6]})
    s.act("solid.union", {"a": "pl", "b": "bo", "out": "pl"})
    s.act("solid.fillet", {"name": "pl", "radius": r, "out": "plf"})
    df = s.act("solid.fillets", {"name": "plf"}).data
    fil = [g for g in df["blend_groups"] if g["kind"] == "fillet"]
    assert len(fil) == 1 and fil[0]["geom"] == "torus", df
    assert abs(fil[0]["radius"] - r) < 1e-6 and fil[0]["count"] == 1, fil[0]
    assert df["round_count"] >= 12, df          # the box edges remain convex rounds
    print("boss+plate: re-entrant foot -> 1 concave torus fillet r%g (+%d rounds)"
          % (fil[0]["radius"], df["round_count"]))

    # ---- a plain block has no blends --------------------------------------- #
    s.act("solid.box", {"name": "blk", "length": 10, "width": 10, "height": 10})
    rb = s.act("solid.fillets", {"name": "blk"}).data
    assert rb["round_count"] == 0 and rb["fillet_count"] == 0, rb
    print("plain block: no blends")

    # ---- loud guards ------------------------------------------------------- #
    s.act("solid.box", {"name": "g1", "length": 5, "width": 5, "height": 5})
    s.act("solid.box", {"name": "g2", "length": 5, "width": 5, "height": 5, "pos": [40, 0, 0]})
    s.act("solid.compound", {"names": ["g1", "g2"], "out": "asm"})
    bad = s.act("solid.fillets", {"name": "asm"})
    assert not bad.ok and "single solid" in (bad.error or "").lower(), bad.error
    print("multi-solid refused: %s" % bad.error)

    print("FILLETS SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_fillets"):
    main()
