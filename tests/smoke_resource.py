"""天下资源接入 (``resource.*``) smoke.

Search the world's 3D-model libraries as first-class ops. The guard assertions
are offline-safe (no request leaves the box); the live search is *network
tolerant* -- if the CI host has no outbound network every platform fault is
contained and the op still returns ``ok`` with ``total == 0``, so this suite
never flakes on connectivity. When network is present it asserts the result
schema and popularity ranking.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402

_RAW = ("TypeError", "AttributeError", "could not convert", "has no attribute",
        "KeyError", "OCCError", "Standard_", "NullShape", "NoneType")


def _guided(r, token):
    err = r.error or ""
    assert not r.ok, "expected failure, got %r" % (r.data,)
    assert not any(x in err for x in _RAW), "raw leak: %r" % err
    assert token in err, "error %r lacks %r" % (err, token)


def main():
    s = new_session("resource")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # platforms registry is always available (pure-python, no network).
    p = s.act("resource.platforms", {})
    assert p.ok, p.error
    plats = p.data["platforms"]
    assert "printables" in plats and "github" in plats, plats
    assert p.data["default"], p.data
    print("resource.platforms -> %d platforms, default %s"
          % (p.data["count"], p.data["default"]))

    # malformed input is refused before any request goes out -- all guided.
    _guided(s.act("resource.search", {"query": "  "}), "query")
    _guided(s.act("resource.search", {"query": "x", "platforms": []}), "platforms")
    _guided(s.act("resource.search", {"query": "x", "platforms": ["nope"]}), "unknown")
    _guided(s.act("resource.search", {"query": "x", "limit": "many"}), "limit")
    _guided(s.act("resource.search", {"query": "x", "timeout": "soon"}), "timeout")
    _guided(s.act("resource.download", {"platform": "printables"}), "id")
    _guided(s.act("resource.download", {"platform": "nope", "id": "1"}), "unknown")
    _guided(s.act("resource.download", {"platform": "sketchfab", "id": "1"}),
            "does not support")
    print("malformed resource input all guided (no raw leaks)")

    # live search -- network tolerant. Faults are contained per-platform, so the
    # op is ok even offline; when hits come back, verify schema + ranking.
    r = s.act("resource.search", {"query": "planetary gear",
              "platforms": ["printables", "github"], "limit": 5})
    assert r.ok, r.error
    assert isinstance(r.data["results"], list)
    assert "printables" in r.data["platforms"], r.data["platforms"]
    if r.data["total"] > 0:
        hits = r.data["results"]
        for h in hits:
            assert h["url"] and h["title"], h
            assert isinstance(h["downloads"], int), h
        # ranked by popularity (downloads desc)
        dls = [h["downloads"] for h in hits]
        assert dls == sorted(dls, reverse=True), dls
        print("resource.search live -> %d hits, top: [%s] %s ↓%d"
              % (r.data["total"], hits[0]["platform"],
                 hits[0]["title"][:40], hits[0]["downloads"]))
    else:
        print("resource.search live -> no network on host; faults contained, op ok")

    print("RESOURCE SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_resource"):
    main()
