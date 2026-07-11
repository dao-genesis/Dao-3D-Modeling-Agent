"""Beam-theory closed loop — geometry -> section I -> FEM, cross-validated.

This is a full-stack self-consistency check that ties three layers of the agent
together on one part and demands they agree:

  1. geometry: build a slender cantilever box (L=200, b=20, h=10);
  2. ``solid.section``: cut perpendicular to the beam axis and *measure* the
     second moment of area I = b*h^3/12 about the bending axis;
  3. that measured I feeds the Euler-Bernoulli tip deflection of an end-loaded
     cantilever, delta = P*L^3 / (3*E*I);
  4. ``fem.*``: run a real CalculiX static solve of the same solid with the same
     load and read back the tip displacement.

The analytic prediction (driven by the *measured* section property, not a magic
number) and the independent FEM solve must agree — for this slenderness they
land within a few percent, so the suite asserts a tight 8% band. This is the
agent verifying its own physics across geometry and FEM, not just one tool.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def main():
    s = new_session("beam_theory")
    print("FreeCAD", s.registry.kernel.freecad_version)

    L, b, h, P, E = 200.0, 20.0, 10.0, 100.0, 210000.0  # mm, mm, mm, N, MPa
    s.act("solid.box", {"name": "beam", "length": L, "width": b, "height": h})

    # measure the section's second moment of area about the bending (y) axis:
    # for a cut normal to x, Ix = int z^2 dA = b*h^3/12.
    sec = s.act("solid.section", {"name": "beam", "normal": [1, 0, 0], "d": L / 2}).data
    Ibend = sec["Ix"]
    assert abs(Ibend - b * h**3 / 12) <= 1e-3 * (b * h**3 / 12), sec

    delta_eb = P * L**3 / (3.0 * E * Ibend)            # Euler-Bernoulli tip defl.

    r = s.act("fem.setup", {"target": "beam", "material": "steel", "order": 2})
    assert r.ok, r.error
    print("mesh nodes=%d elems=%d  I=%.3f  EB delta=%.5f mm"
          % (r.data["nodes"], r.data["elements"], Ibend, delta_eb))

    assert s.act("fem.fix", {"select": {"axis": "x", "side": "min"}}).ok
    ld = s.act("fem.load", {"select": {"axis": "x", "side": "max"},
                            "kind": "force", "value": P, "direction": [0, 0, -1]})
    assert ld.ok and ld.data["effective_dir"][2] < -0.99, ld.data

    sol = s.act("fem.solve", {})
    assert sol.ok, sol.error
    fem_disp = sol.data["max_disp_mm"]
    ratio = fem_disp / delta_eb
    print("FEM tip disp=%.5f mm  FEM/EB ratio=%.3f" % (fem_disp, ratio))
    assert 0.92 <= ratio <= 1.08, (fem_disp, delta_eb, ratio)

    print("BEAM THEORY SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_beam_theory"):
    main()
