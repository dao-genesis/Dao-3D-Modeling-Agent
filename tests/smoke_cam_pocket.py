"""CAM pocket smoke — clear a real recess and emit inspectable G-code.

Exposes/locks two fixes the pocketing path needed to actually cut material:
  * face selection combines a ``normal`` filter with an ``axis`` extreme, so the
    recess *floor* (an upward +Z face that is NOT the topmost +Z face) can be
    isolated -- neither predicate alone can pick it;
  * ``path.pocket`` binds StartDepth/FinalDepth/StepDown from geometry, else a
    flat selected face yields StartDepth==FinalDepth and an empty path.

Closed form: a PW x PD pocket cleared with a tool of diameter T leaves the tool
*centre* path bounded by (PW/2 - T/2, PD/2 - T/2); the depth is cleared in
ceil(depth / step_down) layers; the post emits real G0/G1 moves.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402

W, D, H, T = 60.0, 40.0, 12.0, 6.0
PW, PD, PDEPTH, STEP = 40.0, 24.0, 6.0, 2.0


def main():
    s = new_session("cam_pocket")
    print("FreeCAD", s.registry.kernel.freecad_version)
    if "path.pocket" not in s.tools():
        print("CAM POCKET SMOKE SKIP (Path workbench not available)")
        return

    # blank with a top-centred rectangular recess (floor faces +Z at z=H-PDEPTH)
    assert s.act("solid.box", {"name": "blank", "length": W, "width": D, "height": H,
                               "pos": [-W / 2, -D / 2, 0]}).ok
    assert s.act("solid.box", {"name": "cutter", "length": PW, "width": PD,
                               "height": PDEPTH + 1, "pos": [-PW / 2, -PD / 2, H - PDEPTH]}).ok
    assert s.act("solid.cut", {"a": "blank", "b": "cutter", "out": "part"}).ok

    rj = s.act("path.job", {"target": "part", "tool_diameter": T})
    assert rj.ok and rj.data["tool_diameter_mm"] == T, rj.data

    rp = s.act("path.pocket", {"select": {"normal": [0, 0, 1], "axis": "z", "side": "min"},
                               "step_down": STEP})
    assert rp.ok, rp.error
    d = rp.data
    print("pocket: floor=%s  commands=%d  passes=%s  depth %.1f->%.1f step %.1f  bbox=%s"
          % (d["faces"], d["commands"], d["passes"], d["start_depth"], d["final_depth"],
             d["step_down"], d["path_bbox"]))
    assert d["commands"] > 20, ("pocket emitted no real path", d)

    bb = d["path_bbox"]
    ex, ey = PW / 2 - T / 2, PD / 2 - T / 2
    assert abs(bb[3] - ex) < 1e-3 and abs(bb[0] + ex) < 1e-3, ("X off tool-comp inset", bb, ex)
    assert abs(bb[4] - ey) < 1e-3 and abs(bb[1] + ey) < 1e-3, ("Y off tool-comp inset", bb, ey)

    assert abs(d["final_depth"] - (H - PDEPTH)) < 1e-6, d
    assert d["passes"] >= math.ceil(PDEPTH / STEP), d

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out", "smoke_pocket.nc")
    rg = s.act("path.gcode", {"path": out})
    assert rg.ok, rg.error
    assert rg.data["feeds_g1"] >= 10 and rg.data["rapids_g0"] >= 1, rg.data
    print("gcode: %d lines  G0=%d  G1=%d  -> %s"
          % (rg.data["lines"], rg.data["rapids_g0"], rg.data["feeds_g1"], out))

    print("CAM POCKET SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_cam_pocket"):
    main()
