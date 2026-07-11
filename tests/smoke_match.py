"""Match smoke -- fingerprint retrieval ranks reuse candidates correctly.

反者道之动: before modelling a part from zero, find the one you already have.
``solid.match`` ranks candidates by a scale-invariant fingerprint distance, so:

  * a query box, matched against {same box rotated, same box scaled x2, a
    sphere, a cylinder}, ranks the two boxes first with distance ~0 and
    ``same_key`` true, while the sphere/cylinder fall far behind ;
  * the scaled box reports ``volume_ratio`` = 8 -- how much to scale the reuse ;
  * the ordering is strict: every box-family distance < every non-box distance ;
  * an empty candidate set and a missing query are refused loudly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def _close(a, b, rel=3e-3):
    return abs(a - b) <= rel * max(1.0, abs(b))


def main():
    s = new_session("match")
    print("FreeCAD", s.registry.kernel.freecad_version)

    s.act("solid.box", {"name": "query", "length": 20, "width": 30, "height": 40})

    # same box, generic pose
    s.act("solid.box", {"name": "box_posed", "length": 20, "width": 30, "height": 40})
    s.act("solid.rotate", {"name": "box_posed", "center": [0, 0, 0], "axis": [1, 2, 3], "angle": 41})
    s.act("solid.translate", {"name": "box_posed", "vector": [100, -50, 25]})
    # same box, x2
    s.act("solid.box", {"name": "box_big", "length": 40, "width": 60, "height": 80})
    # decoys
    s.act("solid.sphere", {"name": "ball", "radius": 15})
    s.act("solid.cylinder", {"name": "rod", "radius": 10, "height": 60})

    cand = ["box_posed", "box_big", "ball", "rod"]
    r = s.act("solid.match", {"name": "query", "against": cand}).data
    rank = r["ranking"]
    print("ranking:", [(x["name"], x["distance"], x["same_key"]) for x in rank])

    top2 = {rank[0]["name"], rank[1]["name"]}
    assert top2 == {"box_posed", "box_big"}, top2
    assert rank[0]["same_key"] and rank[1]["same_key"], rank
    assert rank[0]["distance"] < 1e-3 and rank[1]["distance"] < 1e-3, rank

    # the scaled box reports volume_ratio 8
    vr = {x["name"]: x["volume_ratio"] for x in rank}
    assert _close(vr["box_big"], 8.0), vr
    assert _close(vr["box_posed"], 1.0), vr

    # strict separation: box family strictly closer than the round decoys
    box_d = max(x["distance"] for x in rank if x["name"].startswith("box"))
    other_d = min(x["distance"] for x in rank if not x["name"].startswith("box"))
    assert box_d < other_d, (box_d, other_d)
    print("box family d<=%.4g  <<  nearest decoy d=%.4g" % (box_d, other_d))

    # ---- guards --------------------------------------------------------- #
    empty = s.act("solid.match", {"name": "query", "against": []})
    assert not empty.ok and "nothing to compare" in (empty.error or "").lower(), empty.error
    print("empty candidate set refused: %s" % empty.error)

    missing = s.act("solid.match", {"name": "nope", "against": ["query"]})
    assert not missing.ok and "no such solid" in (missing.error or "").lower()
    print("missing query refused: %s" % missing.error)

    print("MATCH SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_match"):
    main()
