#!/usr/bin/env python3
"""Test STEP import via OCP with full shape analysis."""
import os
from OCP.STEPControl import STEPControl_Reader
from OCP.BRepTools import BRepTools
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS_Compound

step_file = os.path.join(os.environ["TEMP"], "e2e_test.step")
brep_out = os.path.join(os.environ["TEMP"], "_ocp_step_v2.brep")

reader = STEPControl_Reader()
reader.ReadFile(step_file)

# Transfer one root at a time
n_roots = reader.NbRootsForTransfer()
for i in range(1, n_roots + 1):
    reader.TransferRoot(i)

n_shapes = reader.NbShapes()
print(f"Shapes: {n_shapes}")

# Get individual shapes
shapes = []
for i in range(1, n_shapes + 1):
    s = reader.Shape(i)
    if not s.IsNull():
        shapes.append(s)
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(s, props)
        vol = props.Mass()
        
        n_solids = 0
        exp = TopExp_Explorer(s, TopAbs_SOLID)
        while exp.More():
            n_solids += 1
            exp.Next()
        
        n_faces = 0
        exp = TopExp_Explorer(s, TopAbs_FACE)
        while exp.More():
            n_faces += 1
            exp.Next()
        
        print(f"  Shape {i}: type={s.ShapeType()}, vol={vol:.4f}, solids={n_solids}, faces={n_faces}")

# Also check OneShape
one = reader.OneShape()
if not one.IsNull():
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(one, props)
    vol = props.Mass()
    print(f"OneShape: type={one.ShapeType()}, vol={vol:.4f}")
    BRepTools.Write_s(one, brep_out)
    print(f"BREP: {os.path.getsize(brep_out)} bytes")

# Export individual shape to BREP 
if shapes:
    brep_out2 = os.path.join(os.environ["TEMP"], "_ocp_step_v2_single.brep")
    BRepTools.Write_s(shapes[0], brep_out2)
    print(f"Single shape BREP: {os.path.getsize(brep_out2)} bytes")

# Now test: can we re-import this BREP back?
from OCP.TopoDS import TopoDS_Shape as TDS
from OCP.BRep import BRep_Builder
shape_back = TDS()
builder = BRep_Builder()
ok = BRepTools.Read_s(shape_back, brep_out, builder)
print(f"Re-read BREP: ok={ok}, null={shape_back.IsNull()}")
if not shape_back.IsNull():
    props2 = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape_back, props2)
    print(f"Re-read vol: {props2.Mass():.4f}")
