"""Catch-all: no solid.* op may leak a raw interpreter/OCC exception.

The kernel dispatch converts a bare missing-argument ``KeyError`` into a guided
``ValueError`` ("<op> missing required argument '<key>'"). This sweep calls
*every* registered ``solid.*`` op with empty args and asserts that whatever
comes back is never a raw ``KeyError``/``TypeError``/``OCCError`` etc. -- so new
ops cannot silently re-introduce the cryptic-error footgun. Descriptive lookups
(``_get`` "no such solid: X") stay readable too.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402
import cad_agent.backends.freecad_backend as fb  # noqa: E402

_RAW = ("KeyError", "TypeError", "AttributeError", "IndexError",
        "FreeCADError", "OCCError", "StdFail", "OCCDomainError")


def main():
    s = new_session("no_raw_leak")
    print("FreeCAD", s.registry.kernel.freecad_version)
    s.act("solid.box", {"name": "A", "length": 10, "width": 10, "height": 10})

    leaked = []
    n = 0
    for op in sorted(fb._SOLID_OPS):
        r = s.act("solid." + op, {})
        n += 1
        if not r.ok:
            err = r.error or ""
            if any(t in err for t in _RAW):
                leaked.append((op, err[:80]))
    assert not leaked, "raw exceptions leaked: %s" % leaked
    print("swept %d solid.* ops with empty args: none leaks a raw exception" % n)

    # a missing arg gives actionable guidance ...
    r = s.act("solid.cylinder", {"height": 5})
    assert not r.ok and "missing required argument" in (r.error or "") and "radius" in r.error, r.error
    # ... and a bad solid name stays readable (not a raw KeyError type).
    r = s.act("solid.measure", {"name": "ghost"})
    assert not r.ok and "KeyError" not in (r.error or "") and "ghost" in r.error, r.error
    print("missing-arg guidance and unknown-solid message both clean")

    print("NO RAW LEAK SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_no_raw_leak"):
    main()
