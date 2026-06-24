#!/usr/bin/env python3
"""Test STEP import via CadQuery high-level API + raw OCP fix."""
import os, tempfile

step_file = os.path.join(os.environ["TEMP"], "e2e_test.step")
brep_out = os.path.join(os.environ["TEMP"], "_cq_step_import.brep")

# ── Method A: CadQuery importStep ──
print("=== Method A: CadQuery importStep ===")
try:
    import cadquery as cq
    result = cq.importers.importStep(step_file)
    print(f"  CQ result type: {type(result)}")
    bb = result.val().BoundingBox()
    print(f"  BBox: x={bb.xlen:.2f} y={bb.ylen:.2f} z={bb.zlen:.2f}")
    # Export to BREP via CQ
    cq.exporters.export(result, brep_out, exportType="BREP")
    print(f"  BREP: {os.path.getsize(brep_out)} bytes")
    print("  METHOD A: SUCCESS")
except Exception as e:
    print(f"  METHOD A FAIL: {e}")

# ── Method B: OCP with XDE reader ──
print("\n=== Method B: OCP XDE/XSControl ===")
try:
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_ShapeTool
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.BRepTools import BRepTools
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    reader = STEPCAFControl_Reader()
    reader.ReadFile(step_file)
    reader.Transfer(doc)
    
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    labels = shape_tool.GetFreeShapes()
    print(f"  Free shapes: {labels.Size()}")
    
    for i in range(labels.Size()):
        label = labels.Value(i + 1)
        shape = shape_tool.GetShape(label)
        if shape and not shape.IsNull():
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(shape, props)
            print(f"  Shape {i}: type={shape.ShapeType()}, vol={props.Mass():.4f}")
            brep_b = os.path.join(os.environ["TEMP"], f"_xde_shape_{i}.brep")
            BRepTools.Write_s(shape, brep_b)
            print(f"  BREP: {os.path.getsize(brep_b)} bytes")
    print("  METHOD B: done")
except Exception as e:
    print(f"  METHOD B FAIL: {e}")

# ── Method C: Create a test STEP from CadQuery, then reimport ──
print("\n=== Method C: CQ roundtrip test ===")
try:
    import cadquery as cq
    box = cq.Workplane("XY").box(10, 10, 10)
    cq_step = os.path.join(os.environ["TEMP"], "_cq_roundtrip.step")
    cq.exporters.export(box, cq_step, exportType="STEP")
    print(f"  CQ STEP export: {os.path.getsize(cq_step)} bytes")
    
    reimport = cq.importers.importStep(cq_step)
    bb = reimport.val().BoundingBox()
    print(f"  CQ reimport BBox: x={bb.xlen:.2f} y={bb.ylen:.2f} z={bb.zlen:.2f}")
    
    # Now try reimport of FreeCAD-exported STEP
    reimport2 = cq.importers.importStep(step_file)
    bb2 = reimport2.val().BoundingBox()
    print(f"  FC STEP reimport BBox: x={bb2.xlen:.2f} y={bb2.ylen:.2f} z={bb2.zlen:.2f}")
    print("  METHOD C: SUCCESS")
except Exception as e:
    print(f"  METHOD C FAIL: {e}")
