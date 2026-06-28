"""Modal (eigenfrequency) smoke — a cantilever's natural frequencies validated
against the Euler-Bernoulli closed form.

For a clamped-free prismatic beam the n-th bending frequency is
    f_n = (beta_n^2 / 2*pi) * sqrt(E*I / (rho*A*L^4)),  beta_1*L = 1.875104
The lowest mode bends about the cross-section's smallest second moment of area;
a 2:1 rectangular section therefore puts the second mode (bending about the
stiff axis) at exactly 2x the first (I ratio = (b/h)^2 = 4 -> sqrt = 2).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402

E, RHO = 210000.0, 7.9e-9  # MPa, t/mm^3


def main():
    L, b, h = 200.0, 20.0, 10.0
    s = new_session("modal")
    print("FreeCAD", s.registry.kernel.freecad_version)
    assert s.act("solid.box", {"name": "beam", "length": b, "width": h, "height": L}).ok
    st = s.act("fem.setup", {"target": "beam", "material": "steel", "order": 2, "mesh_size": 6})
    assert st.ok, st.error
    assert s.act("fem.fix", {"select": {"axis": "z", "side": "min"}}).ok
    m = s.act("fem.modal", {"modes": 6})
    assert m.ok, m.error
    freqs = m.data["frequencies_hz"]
    assert len(freqs) >= 2, freqs

    Imin = max(b, h) * min(b, h) ** 3 / 12.0
    A = b * h
    f1 = (1.875104 ** 2 / (2 * math.pi)) * math.sqrt(E * Imin / (RHO * A * L ** 4))
    err = abs(freqs[0] / f1 - 1.0)
    print("  f1 FEM=%.2f Hz  closed=%.2f Hz  err=%.2f%%" % (freqs[0], f1, err * 100))
    assert err < 0.05, ("first mode off closed form", freqs[0], f1)

    # second bending mode is about the stiff axis -> ratio sqrt((b/h)^2) = b/h = 2
    ratio = freqs[1] / freqs[0]
    print("  f2/f1 = %.3f  (expected b/h = %.3f)" % (ratio, b / h))
    assert abs(ratio / (b / h) - 1.0) < 0.05, ("mode-2/mode-1 ratio off", ratio)

    print("MODAL SMOKE OK")
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_modal"):
    main()
