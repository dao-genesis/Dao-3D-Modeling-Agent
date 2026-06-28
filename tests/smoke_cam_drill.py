"""CAM drilling smoke — geometry-selected hole drilling cycle.

Profiling and pocketing clear material in a plane; real parts also need *holes*
drilled. ``path.drill`` finds cylindrical bores by axis (+ optional diameter),
binds the drill depth from the bore geometry (through-drill = full thickness),
and emits a drilling cycle at every hole center. Validated against the known
hole pattern: 4 corner holes of a 50x30 rectangle, drilled through a 12 mm
plate.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402

L, W, H = 80.0, 60.0, 12.0
DH = 6.0                                  # hole diameter
PAT = [(-25, -15), (25, -15), (25, 15), (-25, 15)]


def main():
    s = new_session("cam_drill")
    print("FreeCAD", s.registry.kernel.freecad_version)
    if "path.drill" not in s.tools():
        print("CAM DRILL SMOKE SKIP (Path not available)")
        return

    s.act("solid.box", {"name": "plate", "length": L, "width": W, "height": H, "pos": [-L / 2, -W / 2, 0]})
    for i, (x, y) in enumerate(PAT):
        s.act("solid.cylinder", {"name": "h%d" % i, "radius": DH / 2, "height": H + 2, "pos": [x, y, -1]})
        assert s.act("solid.cut", {"a": "plate", "b": "h%d" % i, "out": "plate"}).ok

    assert s.act("path.job", {"target": "plate", "tool_diameter": DH}).ok
    r = s.act("path.drill", {"select": {"axis_dir": [0, 0, 1], "diameter": DH}, "peck": 3.0})
    assert r.ok, r.error
    d = r.data
    print("drill: holes=%d  commands=%d  depth=%.1f  peck=%s  centers=%s"
          % (d["holes"], d["commands"], d["depth"], d["peck"], d["centers"]))

    assert d["holes"] == 4, ("expected 4 holes", d)
    assert abs(d["depth"] - H) < 1e-6, ("through-drill should span plate thickness", d)
    got = {(round(x, 1), round(y, 1)) for x, y in d["centers"]}
    assert got == {(float(x), float(y)) for x, y in PAT}, ("hole pattern mismatch", got)
    assert d["commands"] > 0, d

    g = s.act("path.gcode", {"path": os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "_out", "smoke_drill.nc")})
    assert g.ok, g.error
    print("gcode: %d lines  G0=%d  G1=%d  -> %s"
          % (g.data["lines"], g.data["rapids_g0"], g.data["feeds_g1"], g.data["path"]))
    assert g.data["lines"] > 0 and g.data["rapids_g0"] >= 4, g.data

    print("CAM DRILL SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_cam_drill"):
    main()
