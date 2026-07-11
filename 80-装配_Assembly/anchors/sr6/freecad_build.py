#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Materialise the solved SR6 home assembly as a REAL FreeCAD document.

Run under freecadcmd (headless):
  FREECADCMD -c "import sys; sys.argv=['x']; exec(open('anchors/sr6/freecad_build.py').read())"
or:
  freecadcmd anchors/sr6/freecad_build.py

Reads results/sr6_home_poses.json (from solve_home_poses.py) and builds
results/SR6_home.FCStd: one Mesh::Feature per part instance, each with its
solved world Placement, grouped by subsystem.  This is the deliverable the
whole 80-装配 stack aims at -- the assembled machine living inside FreeCAD,
poseable and inspectable, not a matplotlib picture.
"""
import json
import os

import FreeCAD  # noqa: F401
import Mesh

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
STL = os.path.join(ROOT, "ground_truth", "stl")
OUT = os.path.join(ROOT, "results")
POSES = os.path.join(OUT, "sr6_home_poses.json")


def placement_from_T(T):
    m = FreeCAD.Matrix(
        T[0][0], T[0][1], T[0][2], T[0][3],
        T[1][0], T[1][1], T[1][2], T[1][3],
        T[2][0], T[2][1], T[2][2], T[2][3],
        0, 0, 0, 1)
    return FreeCAD.Placement(m)


def build():
    with open(POSES) as f:
        data = json.load(f)
    doc = FreeCAD.newDocument("SR6_home")
    groups = {}

    def group(name):
        if name not in groups:
            groups[name] = doc.addObject("App::DocumentObjectGroup", name)
        return groups[name]

    for name, p in data["parts"].items():
        mesh = Mesh.Mesh(os.path.join(STL, p["stl"]))
        obj = doc.addObject("Mesh::Feature", name.replace("::", "_").replace("-", "_"))
        obj.Mesh = mesh
        obj.Placement = placement_from_T(p["T"])
        obj.Label = name
        g = ("Shell" if name in ("Base", "LFrame", "RFrame", "Lid")
             else "Receiver" if name == "Receiver"
             else "Arms" if name.startswith(("Arm::", "Pitcher::"))
             else "Links")
        group(g).addObject(obj)

    doc.recompute()
    os.makedirs(OUT, exist_ok=True)
    fcstd = os.path.join(OUT, "SR6_home.FCStd")
    doc.saveAs(fcstd)

    # composite mesh export for downstream viewers / validation
    merged = Mesh.Mesh()
    for obj in doc.Objects:
        if obj.TypeId == "Mesh::Feature":
            m = obj.Mesh.copy()
            m.transform(obj.Placement.toMatrix())
            merged.addMesh(m)
    stl_out = os.path.join(OUT, "SR6_home.stl")
    merged.write(stl_out)
    n = len([o for o in doc.Objects if o.TypeId == "Mesh::Feature"])
    print(f"SR6_home: {n} placed part instances")
    print(f"saved {fcstd}")
    print(f"saved {stl_out} ({merged.CountFacets} facets)")
    return fcstd


# freecadcmd executes scripts with __name__ != "__main__"; always build.
build()
