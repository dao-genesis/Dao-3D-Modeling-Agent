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

    # snapshot the clashing state, then heal the clash -> the diff must show
    # the move and the interference resolving (the model's `git diff`).
    r = s.act("project.snapshot", {"label": "before"})
    assert r.ok, r.error
    assert r.data["ok"] is False, r.data

    r = s.act("solid.translate", {"name": "clash", "vector": [50, 0, 0]})
    assert r.ok, r.error
    r = s.act("project.state", {})
    assert r.ok, r.error
    assert r.data["ok"] is True, r.data["issues"]

    r = s.act("project.diff", {"base": "before"})
    assert r.ok, r.error
    d = r.data
    assert not d["identical"], d
    moved = [c for c in d["changed"] if c["object"] == "clash"]
    assert moved and "moved" in moved[0], d["changed"]
    assert any(i["kind"] == "interference" for i in d["issues_resolved"]), d
    assert not d["issues_new"], d["issues_new"]
    assert "已解决" in d["markdown"] and "moved" in d["markdown"], d["markdown"]

    # a fresh snapshot diffed against live must be identical
    r = s.act("project.snapshot", {"label": "after"})
    assert r.ok, r.error
    r = s.act("project.diff", {"base": "after"})
    assert r.ok, r.error
    assert r.data["identical"], r.data

    # snapshot-to-snapshot diff: adding a part shows up as `added`
    r = s.act("solid.box", {"name": "newpart", "length": 5, "width": 5,
                            "height": 5, "pos": [200, 0, 0]})
    assert r.ok, r.error
    r = s.act("project.snapshot", {"label": "grown"})
    assert r.ok, r.error
    r = s.act("project.diff", {"base": "after", "target": "grown"})
    assert r.ok, r.error
    assert "newpart" in r.data["added"], r.data

    # Origin scaffolding (assembly datum planes/axes) stays out of the census
    r = s.act("asm.create", {"name": "Rig"})
    assert r.ok, r.error
    r = s.act("asm.add", {"body": "newpart", "name": "np_i"})
    assert r.ok, r.error
    r = s.act("project.state", {})
    assert r.ok, r.error
    types = {o["type"] for o in r.data["objects"]}
    assert not types & {"App::Origin", "App::Plane", "App::Line"}, types
    r = s.act("project.diff", {"base": "grown"})
    assert r.ok, r.error
    assert not any(n.endswith(("_Plane", "_Axis")) or n == "Origin"
                   for n in r.data["added"]), r.data["added"]

    # guards: unknown snapshot names are refused with guidance
    r = s.act("project.diff", {"base": "nope"})
    assert not r.ok and "project.snapshot" in (r.error or ""), r.error
    r = s.act("project.diff", {"base": "after", "target": "nope"})
    assert not r.ok, r.error

    print("smoke_projstate: whole-project awareness + diff closed loop OK")


if __name__ in ("__main__", "smoke_projstate"):
    main()
