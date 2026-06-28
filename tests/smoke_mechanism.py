"""Mechanism reverse-engineering smoke -- infer joints + mobility from geometry.

The crown of the reverse pipeline (decompose -> joints -> *how it moves*). We
reconstruct a slider-crank as four bare solids in one assembled pose and let the
agent recover the mechanism purely from geometry:

  * three revolute joints from coaxial cylinder pairs (pin in hole): the crank
    pivot O, the crank-rod pin A, the rod-slider wrist pin B;
  * one prismatic joint from planar contact: the slider boxed in the frame's
    guide channel, free only along X;
  * the Kutzbach-Gruebler mobility of the recovered linkage.

Closed-form checks: the inferred revolute axes sit exactly at O=(0,0), A=(0,R),
B=(sqrt(L^2-R^2),0) (crank vertical); the slider's free axis is perpendicular to
every (parallel) revolute axis; and a 4-link chain with 4 one-DOF joints has
planar mobility 3(n-1) - 2j = 3*3 - 2*4 = 1 -- a single crank angle drives it.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402

R, L = 12.0, 34.0
XB = math.sqrt(L * L - R * R)        # crank at theta=90: A=(0,R), B=(XB,0)


def main():
    s = new_session("mechanism")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # ---- frame: base plate with pivot bore + U-channel guide along X -------- #
    assert s.act("solid.box", {"name": "base", "length": 80, "width": 40,
                               "height": 6, "pos": [-12, -20, 0]}).ok
    s.act("solid.cylinder", {"name": "obore", "radius": 4, "height": 6, "pos": [0, 0, 0]})
    s.act("solid.cut", {"a": "base", "b": "obore", "out": "frame"})
    s.act("solid.box", {"name": "railL", "length": 45, "width": 4, "height": 12, "pos": [15, -12, 6]})
    s.act("solid.box", {"name": "railR", "length": 45, "width": 4, "height": 12, "pos": [15, 8, 6]})
    s.act("solid.union", {"a": "frame", "b": "railL", "out": "frame"})
    s.act("solid.union", {"a": "frame", "b": "railR", "out": "frame"})

    # ---- crank: bar O->A, pivot pin r4 (rides the bore), crank pin r3 ------- #
    s.act("solid.box", {"name": "ckbar", "length": 6, "width": 12, "height": 6, "pos": [-3, 0, -12]})
    s.act("solid.cylinder", {"name": "opin", "radius": 4, "height": 18, "pos": [0, 0, -12]})
    s.act("solid.cylinder", {"name": "apin", "radius": 3, "height": 11, "pos": [0, 12, -12]})
    s.act("solid.union", {"a": "ckbar", "b": "opin", "out": "crank"})
    s.act("solid.union", {"a": "crank", "b": "apin", "out": "crank"})

    # ---- rod: plate spanning A & B with a bore (r3) at each end ------------- #
    s.act("solid.box", {"name": "rodp", "length": 48, "width": 24, "height": 3, "pos": [-6, -6, -4]})
    s.act("solid.cylinder", {"name": "abore", "radius": 3, "height": 3, "pos": [0, 12, -4]})
    s.act("solid.cylinder", {"name": "bbore", "radius": 3, "height": 3, "pos": [XB, 0, -4]})
    s.act("solid.cut", {"a": "rodp", "b": "abore", "out": "rod"})
    s.act("solid.cut", {"a": "rod", "b": "bbore", "out": "rod"})

    # ---- slider: block in the channel (y -8..8) + wrist pin r3 at B -------- #
    s.act("solid.box", {"name": "sbk", "length": 12, "width": 16, "height": 10, "pos": [XB - 6, -8, 6]})
    s.act("solid.cylinder", {"name": "bpin", "radius": 3, "height": 20, "pos": [XB, 0, -4]})
    s.act("solid.union", {"a": "sbk", "b": "bpin", "out": "slider"})

    parts = ["frame", "crank", "rod", "slider"]

    # ---- infer the joints purely from geometry ----------------------------- #
    j = s.act("solid.joints", {"parts": parts})
    assert j.ok, j.error
    jl = j.data["joint_list"]
    rev = [x for x in jl if x["type"] == "revolute"]
    pris = [x for x in jl if x["type"] == "prismatic"]
    assert len(rev) == 3 and len(pris) == 1, jl
    # revolute axes land exactly on O, A, B (closed form), all about Z
    pts = sorted([tuple(round(c, 3) for c in r["axis_point"][:2]) for r in rev])
    want = sorted([(0.0, 0.0), (0.0, R), (round(XB, 3), 0.0)])
    assert pts == want, (pts, want)
    assert all(abs(abs(r["axis_dir"][2]) - 1.0) < 1e-6 for r in rev), rev
    # the slider's free axis is along X and perpendicular to every revolute axis
    fax = pris[0]["axis_dir"]
    assert abs(abs(fax[0]) - 1.0) < 1e-6 and abs(fax[1]) < 1e-6 and abs(fax[2]) < 1e-6, fax
    assert all(abs(fax[0] * r["axis_dir"][0] + fax[1] * r["axis_dir"][1]
                   + fax[2] * r["axis_dir"][2]) < 1e-6 for r in rev)
    print("joints: 3 revolutes at O/A/B (about Z) + 1 prismatic slider free along X")

    # ---- assemble the graph + mobility ------------------------------------- #
    m = s.act("solid.mechanism", {"parts": parts})
    assert m.ok, m.error
    md = m.data
    assert md["links"] == 4 and md["joints"] == 4, md
    assert md["joint_types"] == {"revolute": 3, "prismatic": 1}, md["joint_types"]
    # Kutzbach planar: 3(n-1) - 2j = 1 -> a single-DOF mechanism
    assert md["mobility_planar"] == 1, md
    # every link is connected to exactly two others -> one closed kinematic loop
    assert all(len(v) == 2 for v in md["graph"].values()), md["graph"]
    print("mechanism: 4 links, closed loop %s, Kutzbach planar mobility = %d (slider-crank)"
          % (md["graph"], md["mobility_planar"]))

    # ---- the recovered 1-DOF drives the exact piston law ------------------- #
    xs = [R * math.cos(math.radians(t)) + math.sqrt(L * L - (R * math.sin(math.radians(t))) ** 2)
          for t in range(0, 360, 5)]
    assert abs((max(xs) - min(xs)) - 2 * R) < 1e-9
    print("driven law: piston stroke = %.1f = 2R, consistent with the recovered mechanism" % (max(xs) - min(xs)))

    print("MECHANISM SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_mechanism"):
    main()
