"""Coaxial-backbone smoke -- find the rotational spindle of a real assembly.

Motivated by butchering a real downloaded gearmotor: its parts are a stack
threaded onto one output shaft (shaft + gears + bearing), which ``joints`` only
partly catches because gears on a shaft are coaxial but *not* equal-radius
pin-in-hole pairs. ``solid.coaxial`` groups any parts whose cylindrical faces
are collinear, regardless of radius -- recovering the spindle as one group and
listing the radii present (shaft bore vs. gear hubs).

We build a shaft carrying three bored gear-disks on a common Z axis, plus an
off-axis idler that must NOT join the spindle group.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def _gear(s, name, z, ro, ri):
    s.act("solid.cylinder", {"name": name + "o", "radius": ro, "height": 4, "pos": [0, 0, z]})
    s.act("solid.cylinder", {"name": name + "i", "radius": ri, "height": 4, "pos": [0, 0, z]})
    s.act("solid.cut", {"a": name + "o", "b": name + "i", "out": name})


def main():
    s = new_session("coaxial")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # shaft + three bored gears all on the Z axis at x=y=0
    s.act("solid.cylinder", {"name": "shaft", "radius": 3, "height": 60, "pos": [0, 0, 0]})
    _gear(s, "g1", 8, 12, 3)
    _gear(s, "g2", 24, 16, 3)
    _gear(s, "g3", 40, 10, 3)
    # an idler on a parallel but offset axis (x=50) -- a different spindle
    s.act("solid.cylinder", {"name": "idler", "radius": 6, "height": 4, "pos": [50, 0, 20]})

    parts = ["shaft", "g1", "g2", "g3", "idler"]
    cx = s.act("solid.coaxial", {"parts": parts})
    assert cx.ok, cx.error
    groups = cx.data["group_list"]
    # exactly one spindle: shaft + the three gears, all on Z; idler excluded
    assert cx.data["groups"] == 1, groups
    g = groups[0]
    assert sorted(g["parts"]) == ["g1", "g2", "g3", "shaft"], g["parts"]
    assert abs(abs(g["axis_dir"][2]) - 1.0) < 1e-6, g["axis_dir"]
    # the radii present include the shaft/bore (3) and the gear ODs (10,12,16)
    assert 3.0 in g["radii"] and 16.0 in g["radii"], g["radii"]
    print("spindle recovered: %s on axis %s, radii %s" % (sorted(g["parts"]), g["axis_dir"], g["radii"]))

    # the idler is coaxial with nothing -> never appears as a group of its own
    assert all("idler" not in gg["parts"] for gg in groups), groups
    print("off-axis idler correctly excluded from the spindle")

    # and it shows up in the reverse capstone output
    rv = s.act("solid.reverse", {"parts": parts})
    assert rv.ok and len(rv.data["coaxial_groups"]) == 1, rv.data.get("coaxial_groups")
    print("COAXIAL SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_coaxial"):
    main()
