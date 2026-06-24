#!/usr/bin/env python3
"""Test STEP import via CadQuery's OCP (OpenCascade Python)."""
import os
from OCP.STEPControl import STEPControl_Reader
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS_Shape
from OCP.BRepTools import BRepTools

step_file = os.path.join(os.environ["TEMP"], "e2e_test.step")
brep_out = os.path.join(os.environ["TEMP"], "_ocp_step_import.brep")
print(f"STEP: {step_file}")

reader = STEPControl_Reader()
status = reader.ReadFile(step_file)
print(f"ReadFile status: {status}")

n_roots = reader.NbRootsForTransfer()
print(f"Roots for transfer: {n_roots}")

# Try TransferRoot one by one
for i in range(1, n_roots + 1):
    ok = reader.TransferRoot(i)
    print(f"  TransferRoot({i}): {ok}")

n_shapes = reader.NbShapes()
print(f"Total shapes after transfer: {n_shapes}")

shape = reader.OneShape()
print(f"OneShape null: {shape.IsNull()}")
print(f"OneShape type: {shape.ShapeType()}")

if not shape.IsNull():
    # Export to BREP
    BRepTools.Write_s(shape, brep_out)
    print(f"BREP exported: {os.path.getsize(brep_out)} bytes")
else:
    # Try Shape(1) 
    for i in range(1, n_shapes + 1):
        s = reader.Shape(i)
        print(f"  Shape({i}): null={s.IsNull()}, type={s.ShapeType()}")
        if not s.IsNull():
            BRepTools.Write_s(s, brep_out)
            print(f"  BREP exported: {os.path.getsize(brep_out)} bytes")
            break
