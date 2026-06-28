"""Geneva-wheel smoke -- intermittent indexing from continuous rotation.

An n-slot external Geneva indexes the driven wheel one step (360/n) per drive
revolution then locks it. We verify against closed form for a 4-slot wheel:

  * geometry: r = d sin(pi/n), so a centre distance of 50 gives crank r = 50 sin45;
  * each index is exactly 360/n = 90 deg (driven swings -45 -> +45);
  * the crank is engaged only for |alpha| <= 90 - 180/n = 45 deg, locked beyond;
  * the velocity ratio peaks at 1/(m-1) at centre (m = 1/sin(pi/n));
  * symmetry: phi(-a) = -phi(a).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def main():
    s = new_session("geneva")
    print("FreeCAD", s.registry.kernel.freecad_version)

    n, d = 4, 50.0
    sp = math.sin(math.pi / n)
    m = 1.0 / sp

    g = s.act("solid.geneva", {"slots": n, "center_distance": d}).data
    assert abs(g["crank_radius"] - d * sp) < 1e-3, g
    assert abs(g["index_angle"] - 90.0) < 1e-6, g
    assert abs(g["engagement_angle"] - 90.0) < 1e-6, g            # 2*(90-180/4)=90
    assert abs(g["max_velocity_ratio"] - 1.0 / (m - 1.0)) < 1e-3, g
    print("4-slot: r=%.3f, index %.0f deg, engagement %.0f deg, vr_max=%.3f"
          % (g["crank_radius"], g["index_angle"], g["engagement_angle"], g["max_velocity_ratio"]))

    # endpoints of engagement: driven swings exactly +/- 180/n
    edge = s.act("solid.geneva", {"slots": n, "center_distance": d, "angle": 45.0}).data
    assert edge["engaged"] and abs(edge["driven_angle"] - 45.0) < 1e-4, edge
    neg = s.act("solid.geneva", {"slots": n, "center_distance": d, "angle": -45.0}).data
    assert abs(neg["driven_angle"] + 45.0) < 1e-4, neg            # antisymmetric
    # centre: zero driven angle, peak velocity ratio
    mid = s.act("solid.geneva", {"slots": n, "center_distance": d, "angle": 0.0}).data
    assert abs(mid["driven_angle"]) < 1e-9, mid
    assert abs(mid["velocity_ratio"] - 1.0 / (m - 1.0)) < 1e-3, mid
    print("engagement: phi(+/-45)=+/-45 deg, phi(0)=0 at peak vr %.3f" % mid["velocity_ratio"])

    # beyond engagement the wheel is locked (dwell)
    lock = s.act("solid.geneva", {"slots": n, "center_distance": d, "angle": 90.0}).data
    assert (not lock["engaged"]) and lock["velocity_ratio"] == 0.0, lock
    assert abs(lock["driven_angle"] - 45.0) < 1e-6, lock          # held at index edge
    print("beyond engagement (alpha=90): locked, velocity ratio 0")

    # a 6-slot wheel indexes 60 deg; <3 slots rejected
    g6 = s.act("solid.geneva", {"slots": 6, "crank_radius": 20}).data
    assert abs(g6["index_angle"] - 60.0) < 1e-6, g6
    assert not s.act("solid.geneva", {"slots": 2, "crank_radius": 10}).ok
    print("6-slot indexes 60 deg; 2-slot rejected")

    print("GENEVA SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_geneva"):
    main()
