"""
ModelForge Golden Template — CadQuery Parametric Bracket
=========================================================
Engine: CadQuery (精密参数化, 圆角/倒角/STEP导出)
Pattern: Text-to-CadQuery 最佳实践 (Xie et al. 2025, Guan et al. 2025)

Usage:
  python forge_v3.py cq "<this_code>" output/bracket.stl
  python forge_v3.py cq "<this_code>" output/bracket.step

Key Techniques:
  - Fluent API chain: Workplane → sketch → extrude → select → modify
  - Face/edge selectors: ">Z", "|Z", "<X" for precise geometry targeting
  - Parametric: all dimensions as top-level variables
  - STEP-ready: result.val().exportStep() preserves BREP precision
"""
import cadquery as cq

# ═══ PARAMETERS ═══
width = 60.0        # mm — bracket width
height = 40.0       # mm — bracket height
thickness = 5.0     # mm — plate thickness
hole_d = 5.5        # mm — M5 clearance hole
hole_spacing = 40.0 # mm — center-to-center
fillet_r = 3.0      # mm — edge fillet
slot_w = 10.0       # mm — cable routing slot width
slot_h = 20.0       # mm — cable routing slot height

# ═══ MODEL ═══
result = (
    cq.Workplane("XY")
    .box(width, height, thickness)
    # Mounting holes — symmetric pair
    .faces(">Z").workplane()
    .pushPoints([(-hole_spacing/2, 0), (hole_spacing/2, 0)])
    .hole(hole_d)
    # Central cable routing slot (rounded rect)
    .faces(">Z").workplane()
    .rect(slot_w, slot_h).cutThruAll()
    # Fillet all vertical edges
    .edges("|Z").fillet(fillet_r)
    # Chamfer top edges for deburring
    .edges(">Z").chamfer(0.5)
)

# ═══ EXPORT ═══
cq.exporters.export(result, "output/bracket.stl")
cq.exporters.export(result, "output/bracket.step")
print(f"Bracket: {width}x{height}x{thickness}mm, holes M{hole_d:.0f}@{hole_spacing}mm")
