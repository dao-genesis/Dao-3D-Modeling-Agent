"""Cam-follower smoke -- programmed rise-dwell-fall-dwell motion.

A disc cam turns rotation into a designed follower lift. We verify the two
classic smooth laws against closed form:

  * boundary values: lift starts at 0, reaches the full rise S at the top of the
    rise, holds through the dwell, returns to 0 after the fall;
  * monotonic rise / fall (no overshoot);
  * end-conditions that motivate each law -- BOTH have zero *velocity* at the
    rise ends, but only the cycloidal law also has zero *acceleration* there
    (shock-free), while the harmonic law has a finite acceleration step;
  * conservation: the full revolution returns to base (periodic).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402

S = 10.0
RISE, DWELL, FALL = 120.0, 60.0, 120.0
BASE = 25.0


def cam(s, law, ang):
    return s.act("solid.cam", {"rise": S, "law": law, "rise_angle": RISE,
                               "dwell_angle": DWELL, "fall_angle": FALL,
                               "base_radius": BASE, "angle": ang}).data


def main():
    s = new_session("cam")
    print("FreeCAD", s.registry.kernel.freecad_version)

    for law in ("harmonic", "cycloidal"):
        start = cam(s, law, 0)
        top = cam(s, law, RISE)
        middwell = cam(s, law, RISE + DWELL / 2)
        end = cam(s, law, RISE + DWELL + FALL)
        assert abs(start["lift"]) < 1e-6 and start["segment"] == "rise", start
        assert abs(top["lift"] - S) < 1e-6, top
        assert middwell["segment"] == "dwell-top" and abs(middwell["lift"] - S) < 1e-6, middwell
        assert abs(end["lift"]) < 1e-6, end
        assert abs(top["cam_radius"] - (BASE + S)) < 1e-6, top

        # monotonic rise
        lifts = [cam(s, law, a)["lift"] for a in range(0, int(RISE) + 1, 5)]
        assert all(b >= a - 1e-9 for a, b in zip(lifts, lifts[1:])), (law, lifts)

        # both laws: zero velocity at rise start & top
        assert abs(start["velocity"]) < 1e-6 and abs(top["velocity"]) < 1e-6, (law, start, top)
        print("%s: lift 0->%.0f->dwell->0, monotonic, zero end-velocity" % (law, S))

    # the distinguishing property: end acceleration
    h0 = cam(s, "harmonic", 0)
    c0 = cam(s, "cycloidal", 0)
    assert abs(c0["acceleration"]) < 1e-6, c0           # cycloidal: shock-free
    assert abs(h0["acceleration"]) > 1e-3, h0           # harmonic: finite step
    print("end acceleration: cycloidal=%.4f (smooth) vs harmonic=%.4f (step)"
          % (c0["acceleration"], h0["acceleration"]))

    # periodic: 360 deg == 0 deg
    assert cam(s, "cycloidal", 360)["lift"] == cam(s, "cycloidal", 0)["lift"]
    # unknown law rejected
    assert not s.act("solid.cam", {"rise": 5, "law": "bogus", "angle": 10}).ok
    # a zero rise/fall span over a non-zero lift used to silently mislabel the
    # segment at full lift (infinite-velocity follower); it must fail loud.
    zr = s.act("solid.cam", {"rise": 10, "angle": 15, "rise_angle": 0})
    assert not zr.ok and "infinite-velocity" in (zr.error or ""), zr.error
    zf = s.act("solid.cam", {"rise": 10, "angle": 200, "rise_angle": 90,
                             "dwell_angle": 30, "fall_angle": 0})
    assert not zf.ok and "infinite-velocity" in (zf.error or ""), zf.error
    # segment spans must be non-negative and fit one revolution.
    neg = s.act("solid.cam", {"rise": 10, "angle": 15, "rise_angle": -90})
    assert not neg.ok and "non-negative" in (neg.error or ""), neg.error
    over = s.act("solid.cam", {"rise": 10, "angle": 15, "rise_angle": 200,
                               "dwell_angle": 120, "fall_angle": 120})
    assert not over.ok and "360" in (over.error or ""), over.error
    print("degenerate cam spans refused:", zr.error)
    print("CAM SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_cam"):
    main()
