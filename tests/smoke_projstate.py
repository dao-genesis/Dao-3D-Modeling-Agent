"""Whole-project awareness smoke -- project.state / project.brief closed loop.

Builds a real multi-part scene (a plate with a circular 4-hole pattern, a
detached second part, and a deliberately interfering pair), then asserts that
ONE ``project.state`` call reads the whole thing back like a source file:
objects with dims/volume, the recognized hole pattern, the spatial relations,
and the interference surfaced as a diagnosed issue. ``project.brief`` must
render the same truth as markdown, and ``project.save_brief`` must persist it.
"""
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def main():
    s = new_session("projstate")

    r = s.act("solid.box", {"name": "plate", "length": 60, "width": 60,
                            "height": 8})
    assert r.ok, r.error
    for i in range(4):
        a = math.radians(90 * i)
        r = s.act("solid.cylinder", {
            "name": "h%d" % i, "radius": 3, "height": 20,
            "pos": [30 + 20 * math.cos(a), 30 + 20 * math.sin(a), -5]})
        assert r.ok, r.error
        r = s.act("solid.cut", {"a": "plate", "b": "h%d" % i, "out": "plate"})
        assert r.ok, r.error
    r = s.act("solid.box", {"name": "sidecar", "length": 10, "width": 10,
                            "height": 10, "pos": [100, 0, 0]})
    assert r.ok, r.error
    r = s.act("solid.box", {"name": "clash", "length": 10, "width": 10,
                            "height": 10, "pos": [95, 0, 0]})
    assert r.ok, r.error

    r = s.act("project.state", {})
    assert r.ok, r.error
    st = r.data
    meta = st["meta"]
    assert meta["solid_count"] >= 3, meta
    plate = next(o for o in st["objects"] if o["name"] == "plate")
    assert plate["dims"] == [60.0, 60.0, 8.0], plate["dims"]
    feats = plate["features"]
    assert feats["counts"].get("through_hole", 0) >= 4, feats
    assert any(p.get("type") == "circular_pattern" and p.get("count") == 4
               for p in feats["patterns"]), feats["patterns"]
    assert st["relations"], "expected pairwise relations"
    assert any(i["kind"] == "interference" for i in st["issues"]), st["issues"]
    assert st["ok"] is False  # the clash must fail the health check

    r = s.act("project.brief", {})
    assert r.ok, r.error
    md = r.data["markdown"]
    for token in ("plate", "60x60x8", "circular_pattern", "interference"):
        assert token in md, "brief missing %r\n%s" % (token, md)
    assert r.data["ok"] is False

    path = os.path.join(tempfile.gettempdir(), "dao_projstate_brief.md")
    r = s.act("project.save_brief", {"path": path})
    assert r.ok, r.error
    with open(path, "r", encoding="utf-8") as f:
        assert "circular_pattern" in f.read()

    # heal the clash -> the project must report healthy again.
    r = s.act("solid.translate", {"name": "clash", "vector": [50, 0, 0]})
    assert r.ok, r.error
    r = s.act("project.state", {})
    assert r.ok, r.error
    assert r.data["ok"] is True, r.data["issues"]

    print("smoke_projstate: whole-project awareness closed loop OK")


if __name__ == "__main__":
    main()
