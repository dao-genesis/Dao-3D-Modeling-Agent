"""Advanced-modelling smoke — revolve / loft / shell / helical sweep / pipe sweep,
each validated against a volume closed form (Pappus, frustum, prismatoid, helix).

  revolve : annulus by revolving an offset rectangle   V = pi(ro^2-ri^2) h
  loft    : circular frustum (r1 -> r2 over H)          V = pi H/3 (r1^2+r1 r2+r2^2)
  shell   : thin-walled open box (skin inward)          V = outer - inner void
  helix   : coil spring (circle swept along a helix)    V = A * turns*sqrt((2piR)^2+p^2)
  pipe    : circular section swept along an L polyline   V ~ A * centreline length
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def _chk(tag, vol, closed, tol):
    err = abs(vol / closed - 1.0)
    print("  %-8s V=%.1f  closed=%.1f  err=%.2f%%  (tol %.0f%%)"
          % (tag, vol, closed, err * 100, tol * 100))
    assert err <= tol, (tag, vol, closed)


def main():
    s = new_session("advmodel")
    print("FreeCAD", s.registry.kernel.freecad_version)

    assert s.act("param.body", {"name": "Rev"}).ok
    r = s.act("param.revolve", {"body": "Rev", "feature": "An",
              "profile": {"polygon": [[30, 0], [40, 0], [40, 40], [30, 40]]}, "angle": 360})
    assert r.ok, r.error
    _chk("revolve", r.data["volume"], math.pi * (40 ** 2 - 30 ** 2) * 40, 0.02)

    assert s.act("param.body", {"name": "Lf"}).ok
    r = s.act("param.loft", {"body": "Lf", "feature": "Fr", "sections": [
        {"profile": {"circle": 25}, "offset": 0},
        {"profile": {"circle": 10}, "offset": 40}]})
    assert r.ok, r.error
    _chk("loft", r.data["volume"], math.pi * 40 / 3 * (625 + 250 + 100), 0.03)

    assert s.act("param.body", {"name": "Sh"}).ok
    assert s.act("param.pad", {"body": "Sh", "feature": "Bx",
                               "profile": {"rect": [40, 40]}, "length": 40}).ok
    r = s.act("param.shell", {"body": "Sh", "thickness": 3, "open": "+Z"})
    assert r.ok, r.error
    _chk("shell", r.data["volume"], 64000 - 34 * 34 * 37, 0.03)

    assert s.act("param.body", {"name": "Co"}).ok
    r = s.act("param.sweep", {"body": "Co", "feature": "Coil", "profile": {"circle": 3},
              "path": {"helix": {"radius": 20, "pitch": 10, "height": 50}}})
    assert r.ok, r.error
    assert abs(r.data["turns"] - 5.0) < 1e-6, r.data["turns"]
    L = 5 * math.sqrt((2 * math.pi * 20) ** 2 + 10 ** 2)
    _chk("helix", r.data["volume"], math.pi * 9 * L, 0.04)

    assert s.act("param.body", {"name": "Pi"}).ok
    r = s.act("param.sweep", {"body": "Pi", "feature": "LPipe", "profile": {"circle": 5},
              "path": {"plane": "XZ", "points": [[0, 0], [0, 50], [40, 50]]}})
    assert r.ok, r.error
    _chk("pipe", r.data["volume"], math.pi * 25 * 90, 0.07)

    print("ADVMODEL SMOKE OK")
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_advmodel"):
    main()
