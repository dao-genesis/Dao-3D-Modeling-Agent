"""Catch-all: no solid.* op may leak a raw interpreter/OCC exception.

The kernel dispatch converts a bare missing-argument ``KeyError`` into a guided
``ValueError`` ("<op> missing required argument '<key>'"). This sweep calls
*every* registered ``solid.*`` op with empty args and asserts that whatever
comes back is never a raw ``KeyError``/``TypeError``/``OCCError`` etc. -- so new
ops cannot silently re-introduce the cryptic-error footgun. Descriptive lookups
(``_get`` "no such solid: X") stay readable too.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402
import cad_agent.backends.freecad_backend as fb  # noqa: E402

_RAW = ("KeyError", "TypeError", "AttributeError", "IndexError",
        "FreeCADError", "OCCError", "StdFail", "OCCDomainError")

# raw numeric-coercion footguns surfaced only when a *value* is malformed
# (a bare float()/int() on a non-numeric string), not when an arg is missing.
_RAW_VALUE = _RAW + ("could not convert", "invalid literal",
                     "must be real number", "ZeroDivisionError",
                     "object is not subscriptable", "string indices")

# every numeric/list arg name used across solid.* ops, all set malformed, so a
# single sweep drives each op past its required-arg guards onto its coercions.
_BAD = {k: "x" for k in (
    "length width height radius radius1 radius2 angle count size thickness "
    "depth distance value scale factor spacing offset tolerance clearance "
    "density grid tol cte delta_t k pitch modulus teeth crank_len rod_len "
    "crank coupler rocker ground links slots center_distance crank_radius "
    "teeth_sun teeth_ring sun_rpm rise rise_angle dwell_angle fall_angle "
    "base_radius pitch_radius module travel center load torque shear_modulus "
    "conductivity film_coefficient heat_flow temperature_drop R1 R2 modulus2 "
    "stress_max stress_min ultimate endurance yield fatigue_coeff fatigue_exp "
    "pressure yield_strength stress_alt stress_mean se_factor poisson force "
    "temperature samples diam_tol radius_tol axis_tol parallel_tol min_draft "
    "min_wall sigma sun_teeth nominal plus minus".split())}
_BAD["vector"] = _BAD["axis"] = _BAD["normal"] = _BAD["dir"] = "x"


def main():
    s = new_session("no_raw_leak")
    print("FreeCAD", s.registry.kernel.freecad_version)
    s.act("solid.box", {"name": "A", "length": 10, "width": 10, "height": 10})

    leaked = []
    n = 0
    for op in sorted(fb._SOLID_OPS):
        r = s.act("solid." + op, {})
        n += 1
        if not r.ok:
            err = r.error or ""
            if any(t in err for t in _RAW):
                leaked.append((op, err[:80]))
    assert not leaked, "raw exceptions leaked: %s" % leaked
    print("swept %d solid.* ops with empty args: none leaks a raw exception" % n)

    # second sweep: object refs anchored valid, every numeric/list arg malformed,
    # so each op is driven past its required-arg guards onto its bare float()/
    # int() coercions -- which must guide, never leak 'could not convert' etc.
    s.act("solid.box", {"name": "B", "length": 8, "width": 8, "height": 8})
    leaked_v = []
    for op in sorted(fb._SOLID_OPS):
        args = dict(_BAD)
        args.update({"name": "A", "names": ["A", "B"], "parts": ["A", "B"],
                     "a": "A", "b": "B", "out": "OUT"})
        try:
            r = s.act("solid." + op, args)
        except Exception as e:  # a dispatch-level raise is itself a leak
            leaked_v.append((op, "%s: %s" % (type(e).__name__, e)))
            continue
        if not r.ok:
            err = r.error or ""
            if any(t in err for t in _RAW_VALUE):
                leaked_v.append((op, err[:80]))
    assert not leaked_v, "raw value-coercion leaks: %s" % leaked_v
    print("swept %d solid.* ops with malformed values: none leaks a raw "
          "exception" % n)

    # a missing arg gives actionable guidance ...
    r = s.act("solid.cylinder", {"height": 5})
    assert not r.ok and "missing required argument" in (r.error or "") and "radius" in r.error, r.error
    # ... and a bad solid name stays readable (not a raw KeyError type).
    r = s.act("solid.measure", {"name": "ghost"})
    assert not r.ok and "KeyError" not in (r.error or "") and "ghost" in r.error, r.error
    print("missing-arg guidance and unknown-solid message both clean")

    print("NO RAW LEAK SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_no_raw_leak"):
    main()
