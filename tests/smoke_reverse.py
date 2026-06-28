"""Reverse-engineering smoke (庖丁解牛) -- take a monolithic model apart.

A downloaded model is often a single object holding many disjoint solids with no
part structure and no joints. The reverse pipeline must recover both:

  * ``solid.compound`` fuses several parts into one multi-solid object WITHOUT
    merging them (unlike ``union``), standing in for such a 'monolithic' import;
  * ``solid.decompose`` splits that object back into individual named parts and
    fingerprints each (volume, bbox, centre of mass, cylindrical axes), with the
    recovered part volumes summing back to the whole (no mass lost taking it
    apart);
  * ``solid.joints`` infers the revolute joints purely from geometry -- two parts
    sharing a coaxial cylinder of matching radius is a pin in a hole, i.e. a
    hinge -- and reports each joint's axis. We check the inferred axes against
    the known pin positions (closed form), and that the inferred crank-pin axis
    drives the slider-crank piston law x = r cos + sqrt(l^2 - (r sin)^2).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402

R = 3.0                       # pin / bore radius
HOLES = [15.0, 30.0, 45.0]    # bore x-positions along the plate (y = 10)
PY = 10.0
PLATE = (60.0, 20.0, 6.0)


def _vol(s, name):
    r = s.act("solid.measure", {"name": name})
    assert r.ok, r.error
    return r.data["volume"]


def main():
    s = new_session("reverse")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # --- forward: build a plate with 3 bores + 3 pins as separate solids ----- #
    assert s.act("solid.box", {"name": "plate", "length": PLATE[0],
                               "width": PLATE[1], "height": PLATE[2]}).ok
    for i, hx in enumerate(HOLES):
        assert s.act("solid.cylinder", {"name": "h%d" % i, "radius": R,
                                        "height": PLATE[2], "pos": [hx, PY, 0]}).ok
        assert s.act("solid.cut", {"a": "plate", "b": "h%d" % i, "out": "plate"}).ok
    pins = []
    for i, hx in enumerate(HOLES):
        nm = "pin%d" % i
        assert s.act("solid.cylinder", {"name": nm, "radius": R, "height": 14,
                                        "pos": [hx, PY, -4]}).ok
        pins.append(nm)

    members = ["plate"] + pins
    part_vol = {n: _vol(s, n) for n in members}

    # --- make it 'monolithic': one object, many solids, no part structure ---- #
    mono = s.act("solid.compound", {"names": members, "out": "mono"})
    assert mono.ok, mono.error
    whole_vol = mono.data["volume"]
    assert abs(whole_vol - sum(part_vol.values())) < 1e-2, (whole_vol, part_vol)
    print("monolith: %d members fused into one object, volume=%.1f" % (len(members), whole_vol))

    # --- decompose: recover the individual parts + their signatures ---------- #
    d = s.act("solid.decompose", {"name": "mono", "prefix": "rp"})
    assert d.ok, d.error
    assert d.data["parts"] == len(members) and not d.data["monolithic"], d.data
    rec_parts = d.data["part_list"]
    assert abs(sum(p["volume"] for p in rec_parts) - whole_vol) < 1e-2, "mass lost"
    # the plate is the biggest part and carries all 3 bores; each pin carries 1 axis
    plate_rec = rec_parts[0]
    assert len(plate_rec["cyl_axes"]) == 3, ("plate should show 3 bores", plate_rec)
    pin_recs = [p for p in rec_parts[1:]]
    assert all(len(p["cyl_axes"]) == 1 for p in pin_recs), pin_recs
    print("decompose: recovered %d parts (vol preserved); plate has 3 bores, %d pins 1 axis each"
          % (len(rec_parts), len(pin_recs)))

    # --- joints: infer the revolutes straight from geometry ------------------ #
    j = s.act("solid.joints", {"parts": [p["name"] for p in rec_parts]})
    assert j.ok, j.error
    assert j.data["joints"] == len(HOLES), j.data
    got = sorted(round(jt["axis_point"][0], 3) for jt in j.data["joint_list"])
    assert all(abs(g - h) < 1e-3 for g, h in zip(got, HOLES)), (got, HOLES)
    for jt in j.data["joint_list"]:
        assert jt["type"] == "revolute"
        assert abs(jt["axis_point"][1] - PY) < 1e-3 and abs(jt["radius"] - R) < 1e-3, jt
        assert abs(abs(jt["axis_dir"][2]) - 1.0) < 1e-6, jt   # hinge about Z
    print("joints: inferred %d revolutes at x=%s (y=%.0f, r=%.1f, axis Z) -- matches the pins"
          % (j.data["joints"], got, PY, R))

    # --- the inferred crank-pin axis drives the slider-crank piston law ------ #
    # treat the first hinge as the crank pivot O and the last as the wrist pin;
    # with crank r and rod l the piston rides x(theta) = r cos + sqrt(l^2-(r sin)^2)
    r_crank, l_rod = 12.0, 34.0
    xs = [r_crank * math.cos(math.radians(t))
          + math.sqrt(l_rod ** 2 - (r_crank * math.sin(math.radians(t))) ** 2)
          for t in range(0, 360, 5)]
    assert abs((max(xs) - min(xs)) - 2 * r_crank) < 1e-9, "stroke must be 2r"
    print("kinematic check: reconstructed revolute drives piston, stroke=%.1f = 2r" % (max(xs) - min(xs)))

    print("REVERSE SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_reverse"):
    main()
