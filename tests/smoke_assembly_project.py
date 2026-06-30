"""多零件装配体 capstone -- one bolted spacer-stack, six instanced components,
mated geometrically, then verified as an assembly (not just modelled parts).

This is the assembly counterpart to ``smoke_project`` (which proved one NL brief
-> one multi-step *part*). Here the orchestration crosses TWO workbenches and
exercises real assembly fusion:

    solid.*  -> model four distinct source parts (plate / washer / bolt / nut),
                each a bored boolean whose result is a Compound;
    asm.*    -> instance them into an Assembly::AssemblyObject (the washer is
                instanced THREE times -- genuine part reuse), mate them by
                geometry (stack on +Z faces, coaxial into the centre bore), then
                roll up bill-of-materials, all-pairs interference and the
                mass / centroid / moment-of-inertia of the whole stack.

The point is the *coupling*: the BOM and inertia consume the modelled solids
through the assembly's placements, the clash check both passes (clearance fit)
and -- when a part is deliberately driven into another -- catches the overlap,
and the moment of inertia obeys the parallel-axis theorem about a shifted axis.
Any break in that chain fails the suite.

Closed-form references (unit volume, mm^3):
    plate  = 60*60*10 - pi*6^2*10            = 34869.03
    washer = pi*20^2*8 - pi*6^2*8            =  9148.32
    bolt   = pi*5^2*44                       =  3455.75
    nut    = pi*9^2*8 - pi*6^2*8             =  1130.97
"""
import math

from cad_agent import new_session

RHO = 0.00785  # steel, g/mm^3


def _approx(a, b, tol=1.0):
    return abs(a - b) < tol


def main():
    s = new_session("asm_project")
    print("FreeCAD", s.registry.kernel.freecad_version)

    def act(tool, args):
        r = s.act(tool, args)
        assert r.ok, "%s %s -> %s" % (tool, args, r.error)
        return r.data

    # ---- model four source parts (each a bored boolean = a Compound) ------ #
    act("solid.box", {"name": "base_blank", "length": 60, "width": 60, "height": 10})
    act("solid.cylinder", {"name": "base_bore", "radius": 6, "height": 30, "pos": [30, 30, -10]})
    act("solid.cut", {"a": "base_blank", "b": "base_bore", "out": "base"})

    act("solid.cylinder", {"name": "sp_out", "radius": 20, "height": 8})
    act("solid.cylinder", {"name": "sp_bore", "radius": 6, "height": 24, "pos": [0, 0, -8]})
    act("solid.cut", {"a": "sp_out", "b": "sp_bore", "out": "spacer"})

    act("solid.cylinder", {"name": "bolt", "radius": 5, "height": 44})

    act("solid.cylinder", {"name": "nut_out", "radius": 9, "height": 8})
    act("solid.cylinder", {"name": "nut_bore", "radius": 6, "height": 24, "pos": [0, 0, -8]})
    act("solid.cut", {"a": "nut_out", "b": "nut_bore", "out": "nut"})

    # ---- instance + mate into a real assembly ----------------------------- #
    act("asm.create", {"name": "Stack"})
    act("asm.add", {"body": "base", "name": "Base", "fixed": True})
    for inst in ("S1", "S2", "S3"):       # one source, three instances
        act("asm.add", {"body": "spacer", "name": inst})
    act("asm.add", {"body": "bolt", "name": "Bolt"})
    act("asm.add", {"body": "nut", "name": "Nut"})

    # stack the washers up the +Z faces; each centres in XY on the part below.
    act("asm.stack", {"base": "Base", "top": "S1"})
    act("asm.stack", {"base": "S1", "top": "S2"})
    act("asm.stack", {"base": "S2", "top": "S3"})
    # bolt threads coaxially into the central bore, flush at the bottom; nut
    # seats on the top washer (z = 10 + 3*8 = 34) on the same axis.
    act("asm.coaxial", {"hole": "Base", "pin": "Bolt", "seat": "bottom"})
    act("asm.coaxial", {"hole": "Base", "pin": "Nut", "seat": 34})

    # every component centred on the (30,30) bore axis.
    tree = act("asm.tree", {})
    assert len(tree["components"]) == 6, tree
    for c in tree["components"]:
        if c["name"] != "Base":
            assert c["pos"][0] == 30 and c["pos"][1] == 30, c

    # ---- bill of materials: the washer must read as 3-of-a-kind ----------- #
    bom = act("asm.bom", {"density": RHO})
    assert bom["component_count"] == 6, bom
    items = bom["line_items"]
    assert items["spacer"]["count"] == 3, bom
    assert items["base"]["count"] == 1 and items["bolt"]["count"] == 1, bom
    assert items["nut"]["count"] == 1, bom
    v_plate = 60 * 60 * 10 - math.pi * 36 * 10
    v_wash = math.pi * 400 * 8 - math.pi * 36 * 8
    v_bolt = math.pi * 25 * 44
    v_nut = math.pi * 81 * 8 - math.pi * 36 * 8
    assert _approx(items["base"]["unit_volume"], v_plate), items
    assert _approx(items["spacer"]["unit_volume"], v_wash), items
    assert _approx(items["bolt"]["unit_volume"], v_bolt), items
    assert _approx(items["nut"]["unit_volume"], v_nut), items

    # ---- clearance fit: NO clashes (bolt r5 in bore r6, faces only touch) -- #
    clash = act("asm.interference", {})
    assert clash["clash_count"] == 0, clash
    assert clash["pairs_checked"] == 15, clash      # C(6,2)

    # ---- whole-stack mass properties consume the placed solids ------------ #
    total_v = v_plate + 3 * v_wash + v_bolt + v_nut
    m = act("asm.measure", {"density": RHO,
                            "inertia_axis": {"point": [30, 30, 0], "dir": [0, 0, 1]}})
    assert m["components"] == 6, m
    assert _approx(m["volume"], total_v), (m["volume"], total_v)
    assert m["bbox_size"] == [60, 60, 44], m          # plate..bolt tip on Z
    # uniform material -> centre of mass coincides with the geometric centroid,
    # and sits on the bore axis in XY.
    assert _approx(m["center_of_mass"][0], 30) and _approx(m["center_of_mass"][1], 30), m
    assert _approx(m["center_of_mass"][2], m["centroid"][2]), m
    assert _approx(m["mass"], total_v * RHO, tol=0.5), m
    i0 = m["inertia_axis"]
    assert i0 > 0, m

    # parallel-axis theorem: shifting the spin axis 10 mm off the CoM in X must
    # add exactly M*d^2 to the moment of inertia -- a physics check on the
    # inertia machinery that needs no hard-coded absolute value.
    m2 = act("asm.measure", {"density": RHO,
                             "inertia_axis": {"point": [40, 30, 0], "dir": [0, 0, 1]}})
    expect = i0 + m["mass"] * (10 ** 2)
    assert _approx(m2["inertia_axis"], expect, tol=1.0), (m2["inertia_axis"], expect)

    # ---- and the checker CATCHES a real clash when one is introduced ------ #
    # drive the nut 6 mm down into the top washer; their solids now overlap.
    act("asm.move", {"name": "Nut", "vector": [0, 0, -6]})
    clash2 = act("asm.interference", {})
    assert clash2["clash_count"] >= 1, clash2
    assert any({"Nut", "S3"} == {c["a"], c["b"]} for c in clash2["clashes"]), clash2
    act("asm.move", {"name": "Nut", "vector": [0, 0, 6]})       # restore
    assert act("asm.interference", {})["clash_count"] == 0, "restore failed"

    print("assembly capstone: 6-component bolted stack -- BOM 3x washer, "
          "vol %.2f, mass %.2f, CoM z=%.2f, Izz=%.1f, parallel-axis ok, "
          "clearance clash-free & clash caught" % (
              m["volume"], m["mass"], m["center_of_mass"][2], i0))
    print("ASSEMBLY PROJECT SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ == "__main__":
    main()
