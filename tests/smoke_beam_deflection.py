"""Beam-deflection smoke -- Euler-Bernoulli deflection/stress vs closed form.

The solid is used as a beam of length L bending about its strong axis. We check
all four standard cases against the textbook formulas for a rectangular section
(I = b h^3/12 about the strong axis, extreme fibre c = h/2):

  cantilever  point P : d = P L^3/(3EI),   M = P L,      sigma = M c/I
  cantilever  udl   w : d = w L^4/(8EI),   M = w L^2/2
  simply-supp point P : d = P L^3/(48EI),  M = P L/4
  simply-supp udl   w : d = 5 w L^4/(384EI), M = w L^2/8

Plus: strong axis carries less deflection than the weak axis, and missing
modulus/load is refused.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def _close(a, b, rel=1e-4, abs_=1e-9):
    return abs(a - b) <= max(abs_, rel * abs(b))


def main():
    s = new_session("beam_deflection")
    print("FreeCAD", s.registry.kernel.freecad_version)

    b, h, L, E = 20.0, 50.0, 800.0, 210000.0   # mm, mm, mm, MPa (steel)
    s.act("solid.box", {"name": "beam", "length": b, "width": h, "height": L})
    Istrong = b * h ** 3 / 12.0                 # strong axis (tall side)
    c = h / 2.0
    P, w = 1500.0, 5.0                          # N ; N/mm

    cases = {
        ("cantilever", "point"): (P * L ** 3 / (3 * E * Istrong), P * L),
        ("cantilever", "udl"): (w * L ** 4 / (8 * E * Istrong), w * L ** 2 / 2),
        ("simply_supported", "point"): (P * L ** 3 / (48 * E * Istrong), P * L / 4),
        ("simply_supported", "udl"): (5 * w * L ** 4 / (384 * E * Istrong), w * L ** 2 / 8),
    }
    for (sup, lt), (d_exp, m_exp) in cases.items():
        load = P if lt == "point" else w
        r = s.act("solid.beam_deflection",
                  {"name": "beam", "modulus": E, "load": load,
                   "support": sup, "load_type": lt})
        assert r.ok, r.error
        d = r.data
        assert _close(d["I"], Istrong), (d["I"], Istrong)
        assert _close(d["extreme_fiber"], c), (d["extreme_fiber"], c)
        assert _close(d["max_deflection"], d_exp, rel=1e-3), (sup, lt, d["max_deflection"], d_exp)
        assert _close(d["max_moment"], m_exp, rel=1e-3), (sup, lt, d["max_moment"], m_exp)
        assert _close(d["max_bending_stress"], m_exp * c / Istrong, rel=1e-3), d
        print("%-16s %-5s d=%.4f mm  M=%.0f N.mm  sigma=%.2f MPa (closed form)"
              % (sup, lt, d["max_deflection"], d["max_moment"], d["max_bending_stress"]))

    # ---- weak axis deflects more than strong axis under the same load --- #
    rs = s.act("solid.beam_deflection", {"name": "beam", "modulus": E, "load": P}).data
    rw = s.act("solid.beam_deflection",
               {"name": "beam", "modulus": E, "load": P, "bending": "min"}).data
    assert rw["max_deflection"] > rs["max_deflection"], (rw, rs)
    assert _close(rw["I"], h * b ** 3 / 12.0), rw["I"]
    print("weak axis deflects more: %.4f > %.4f mm (I %.0f < %.0f)"
          % (rw["max_deflection"], rs["max_deflection"], rw["I"], rs["I"]))

    # ---- guards --------------------------------------------------------- #
    bad = s.act("solid.beam_deflection", {"name": "beam", "load": P})
    assert not bad.ok and "modulus" in (bad.error or "").lower(), bad.error
    bad2 = s.act("solid.beam_deflection",
                 {"name": "beam", "modulus": E, "load": P, "support": "fixed_fixed"})
    assert not bad2.ok and "unsupported" in (bad2.error or "").lower(), bad2.error
    print("guards: missing modulus and bad support refused")

    # a zero modulus used to leak a raw ZeroDivisionError from PL^3/(EI).
    ze = s.act("solid.beam_deflection", {"name": "beam", "modulus": 0, "load": P})
    assert not ze.ok and "positive" in (ze.error or "") and "ZeroDivision" not in (ze.error or ""), ze.error
    print("zero modulus refused:", ze.error)

    print("BEAM DEFLECTION SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_beam_deflection"):
    main()
