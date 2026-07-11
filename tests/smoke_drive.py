"""Reverse -> drive smoke -- make the recovered mechanism actually move.

End of the reverse pipeline: having recovered the slider-crank's joints from raw
geometry (smoke_mechanism), read the *driving parameters* straight off those
inferred joints and animate the linkage with ``solid.drive``:

  * pivot O   = the crank-to-frame revolute axis point;
  * crank R   = |O A|, rod L = |A B|, from the three revolute axis points;
  * guide line = the prismatic joint's free axis through the wrist pin B.

Then sweep the crank a full turn and check, at every step, that the recovered
mechanism stays physically consistent: the rod length is held (|AB| == L), the
wrist pin rides the guide line (y == 0 for the centred case), and the piston
follows the exact closed form x = R cos + sqrt(L^2 - (R sin)^2) with stroke 2R.
This is the proof that what we took apart, we can also drive.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402
from tests.smoke_mechanism import build_slidercrank  # noqa: E402


def _dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def main():
    s = new_session("drive")
    print("FreeCAD", s.registry.kernel.freecad_version)
    parts = build_slidercrank(s)

    # --- recover the driving parameters from the inferred joints ------------- #
    j = s.act("solid.joints", {"parts": parts})
    assert j.ok, j.error
    rev = [x for x in j.data["joint_list"] if x["type"] == "revolute"]
    pris = [x for x in j.data["joint_list"] if x["type"] == "prismatic"]
    assert len(rev) == 3 and len(pris) == 1, j.data["joint_list"]
    pts = {tuple(round(c, 3) for c in r["axis_point"][:2]) for r in rev}
    piv = (0.0, 0.0)
    pa = (0.0, 12.0)
    pb = (round(math.sqrt(34.0 ** 2 - 12.0 ** 2), 3), 0.0)
    assert pts == {piv, pa, pb}, pts
    R = _dist(piv, pa)                    # crank length  = |OA|
    L = _dist(pa, pb)                     # rod length    = |AB|
    guide = pris[0]["axis_dir"][:2]       # slider free axis (sign is arbitrary)
    # orient the guide toward where the slider actually sits (the recovered B)
    if guide[0] * (pb[0] - piv[0]) + guide[1] * (pb[1] - piv[1]) < 0:
        guide = [-guide[0], -guide[1]]
    assert abs(R - 12.0) < 1e-3 and abs(L - 34.0) < 1e-3, (R, L)
    print("recovered: O=%s R=%.1f L=%.1f guide_dir=%s" % (piv, R, L, guide))

    # --- drive a full revolution off the recovered parameters ---------------- #
    pistons = []
    for thd in range(0, 360, 5):
        d = s.act("solid.drive", {"ground_point": list(piv), "guide_point": list(piv),
                                   "guide_dir": list(guide), "crank_len": R,
                                   "rod_len": L, "angle": thd})
        assert d.ok, d.error
        assert d.data["rod_len_ok"], ("rod broke at %d" % thd, d.data)   # |AB| == L
        assert abs(d.data["B"][1]) < 1e-6, ("slider left the guide", thd, d.data)  # B on y=0
        # the wrist-pin x equals the analytic slider-crank law (guide along X)
        analytic = (R * math.cos(math.radians(thd))
                    + math.sqrt(L * L - (R * math.sin(math.radians(thd))) ** 2))
        assert abs(d.data["B"][0] - analytic) < 1e-3, (thd, d.data["B"][0], analytic)
        pistons.append(d.data["B"][0])
    stroke = max(pistons) - min(pistons)
    assert abs(stroke - 2 * R) < 1e-3, ("stroke", stroke)
    assert abs(max(pistons) - (R + L)) < 1e-3 and abs(min(pistons) - (L - R)) < 1e-3, pistons
    print("driven a full turn: rod length held, slider on guide, piston law exact, stroke=%.1f = 2R"
          % stroke)

    # --- an over-short rod must fail loudly, not silently miss the guide ----- #
    bad = s.act("solid.drive", {"ground_point": [0, 0], "guide_point": [0, 20],
                                "guide_dir": [1, 0], "crank_len": 12, "rod_len": 3,
                                "angle": 0})
    assert not bad.ok and "cannot close" in (bad.error or ""), bad
    print("guard: unreachable rod length rejected with a clear message")

    print("DRIVE SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_drive"):
    main()
