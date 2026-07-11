"""Hertzian contact smoke -- point & line contact peak pressure vs closed form.

Independent checks (not a recompute of the same call):

  * steel ball R=10 on a flat, F=100, E=200 GPa, nu=0.3 -> a~=0.1897 mm,
    p_max~=1327 MPa (hand value), and the Hertz identity p_max = 1.5 p_mean ;
  * contact radius scales as F^(1/3) and p_max as F^(1/3) (point) ;
  * two equal balls R=10 give an effective radius Re=5 ;
  * line contact (roller on flat) obeys p_max = (4/pi) p_mean and p_max ~ sqrt(F) ;
  * a concave non-convex pairing and missing inputs are refused.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def _close(a, b, rel=1e-2, abs_=1e-9):
    return abs(a - b) <= max(abs_, rel * abs(b))


def main():
    s = new_session("contact_stress")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # steel ball on flat plate
    base = {"kind": "point", "R1": 10.0, "modulus": 200000.0,
            "poisson": 0.3, "load": 100.0}
    d = s.act("solid.contact_stress", base).data
    assert _close(d["effective_radius"], 10.0), d
    assert _close(d["contact_radius"], 0.18968, rel=2e-3), d["contact_radius"]
    assert _close(d["max_pressure"], 1327.0, rel=2e-3), d["max_pressure"]
    # Hertz point identity: peak = 1.5 x mean
    assert _close(d["max_pressure"], 1.5 * d["mean_pressure"]), d
    assert _close(d["approach"], d["contact_radius"] ** 2 / 10.0), d
    print("ball/flat: a=%.5f mm  p_max=%.1f MPa  (=1.5 p_mean)"
          % (d["contact_radius"], d["max_pressure"]))

    # load scaling F^(1/3)
    d8 = s.act("solid.contact_stress", dict(base, load=800.0)).data
    assert _close(d8["contact_radius"] / d["contact_radius"], 2.0), (d8, d)  # 8^(1/3)=2
    assert _close(d8["max_pressure"] / d["max_pressure"], 2.0), (d8, d)
    print("scaling: 8x load -> 2x contact radius & 2x p_max (F^1/3)")

    # two equal balls -> Re = R/2
    dd = s.act("solid.contact_stress", dict(base, R2=10.0)).data
    assert _close(dd["effective_radius"], 5.0), dd
    print("ball/ball R=10 each -> Re=5.0")

    # line contact: roller on flat
    ln = {"kind": "line", "R1": 10.0, "modulus": 200000.0, "poisson": 0.3,
          "load": 500.0, "length": 20.0}
    dl = s.act("solid.contact_stress", ln).data
    assert _close(dl["max_pressure"], (4.0 / math.pi) * dl["mean_pressure"]), dl
    dl4 = s.act("solid.contact_stress", dict(ln, load=2000.0)).data
    assert _close(dl4["max_pressure"] / dl["max_pressure"], 2.0), (dl4, dl)  # sqrt(4)=2
    print("line: p_max=%.1f MPa (=4/pi p_mean), 4x load -> 2x p_max (sqrt F)"
          % dl["max_pressure"])

    # guards
    bad = s.act("solid.contact_stress", {"kind": "point", "R1": 10.0, "load": 100.0})
    assert not bad.ok and "modulus" in (bad.error or ""), bad.error
    noL = s.act("solid.contact_stress", {"kind": "line", "R1": 10.0,
                                         "modulus": 200000.0, "load": 100.0})
    assert not noL.ok and "length" in (noL.error or ""), noL.error
    conc = s.act("solid.contact_stress", {"R1": 10.0, "R2": -10.0,
                                          "modulus": 200000.0, "load": 100.0})
    assert not conc.ok and "convex" in (conc.error or ""), conc.error
    print("guards: missing modulus / line length / non-convex pairing refused")

    # zero modulus / zero load used to leak a raw ZeroDivisionError.
    zm = s.act("solid.contact_stress", {"R1": 10.0, "modulus": 0, "load": 100.0})
    assert not zm.ok and "positive" in (zm.error or "") and "ZeroDivision" not in (zm.error or ""), zm.error
    zl = s.act("solid.contact_stress", {"R1": 10.0, "modulus": 200000.0, "load": 0})
    assert not zl.ok and "positive" in (zl.error or "") and "ZeroDivision" not in (zl.error or ""), zl.error
    print("zero modulus/load refused:", zm.error, "|", zl.error)

    print("CONTACT STRESS SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_contact_stress"):
    main()
