"""Gear-mesh inference smoke -- recover meshing pairs from geometry alone.

The inter-axis complement to ``coaxial``. We lay out gear blanks (cylinders) on
parallel axes and assert that ``gearmesh`` finds exactly the pairs whose centre
distance equals the sum of their radii, ignores a gear stacked coaxially on the
same shaft, and ignores a gear too far away to mesh. The recovered ratios are
then fed straight into ``geartrain`` to confirm the two ops compose.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def main():
    s = new_session("gearmesh")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # three gears in a line on parallel Z axes:
    #   g1 r=20 @ x=0 , g2 r=30 @ x=50 (=20+30) , g3 r=10 @ x=90 (=50+40)
    s.act("solid.cylinder", {"name": "g1", "radius": 20, "height": 6, "pos": [0, 0, 0]})
    s.act("solid.cylinder", {"name": "g2", "radius": 30, "height": 6, "pos": [50, 0, 0]})
    s.act("solid.cylinder", {"name": "g3", "radius": 10, "height": 6, "pos": [90, 0, 0]})
    # a gear stacked on g1's own shaft (coaxial -> NOT a mesh)
    s.act("solid.cylinder", {"name": "stk", "radius": 8, "height": 6, "pos": [0, 0, 10]})
    # a far-away gear that meshes with nothing
    s.act("solid.cylinder", {"name": "far", "radius": 5, "height": 6, "pos": [0, 300, 0]})

    r = s.act("solid.gearmesh", {"parts": ["g1", "g2", "g3", "stk", "far"]}).data
    pairs = {tuple(sorted(m["gears"])): m for m in r["mesh_list"]}
    assert r["meshes"] == 2, r
    assert ("g1", "g2") in pairs and ("g2", "g3") in pairs, pairs
    assert all(m["type"] == "external" for m in r["mesh_list"]), r
    assert abs(pairs[("g1", "g2")]["center_distance"] - 50) < 1e-6, pairs
    assert abs(pairs[("g2", "g3")]["center_distance"] - 40) < 1e-6, pairs
    # coaxial stack and far gear are not meshes
    assert not any("stk" in k or "far" in k for k in pairs), pairs
    print("gearmesh found 2 external meshes (g1-g2, g2-g3); coaxial stack & far gear excluded")

    # compose with geartrain: g1->g2->g3 train value = product of r_drv/r_dvn
    meshes = [{"driver_radius": 20, "driven_radius": 30},
              {"driver_radius": 30, "driven_radius": 10}]
    e = s.act("solid.geartrain", {"meshes": meshes, "input_rpm": 300}).data
    # 20/30 * 30/10 = 2.0 ; two external flips -> positive
    assert abs(e["train_value"] - 2.0) < 1e-9 and abs(e["output_rpm"] - 600) < 1e-9, e
    print("gearmesh radii -> geartrain: e=%.3f, 300->%.0f rpm" % (e["train_value"], e["output_rpm"]))

    print("GEARMESH SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_gearmesh"):
    main()
