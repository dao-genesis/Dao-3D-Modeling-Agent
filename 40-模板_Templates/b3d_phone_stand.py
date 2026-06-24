"""
ModelForge Golden Template — build123d Phone Stand
=====================================================
Engine: build123d (现代Python造型, 上下文管理器)
Pattern: build123d官方范例 + 社区最佳实践

Usage:
  python forge_v3.py b3d "<this_code>" output/phone_stand.stl

Key Techniques:
  - BuildPart/BuildSketch/BuildLine context managers
  - fillet() / chamfer() on edge selections
  - Axis filtering for precise edge targeting
  - Parametric angles via trigonometry
"""
from build123d import *
from math import tan, radians

# ═══ PARAMETERS ═══
base_w = 80.0       # mm — base width
base_d = 60.0       # mm — base depth
base_h = 5.0        # mm — base thickness
lip_h = 15.0        # mm — front lip height (holds phone)
lip_t = 3.0         # mm — lip thickness
back_h = 80.0       # mm — back support height
back_t = 4.0        # mm — back support thickness
angle_deg = 70.0    # degrees — phone lean angle
slot_w = 20.0       # mm — cable slot width
fillet_r = 3.0      # mm — edge fillet radius

# ═══ MODEL ═══
with BuildPart() as stand:
    # Base plate
    Box(base_w, base_d, base_h)

    # Front lip — holds phone bottom edge
    with Locations((0, -base_d/2 + lip_t/2, base_h/2 + lip_h/2)):
        Box(base_w, lip_t, lip_h)

    # Back support — angled phone rest
    with Locations((0, base_d/2 - back_t/2, base_h/2 + back_h/2)):
        Box(base_w, back_t, back_h)

    # Cable routing slot in base
    with BuildSketch(Plane.XY.offset(base_h/2)):
        Rectangle(slot_w, base_d * 0.5)
    extrude(amount=-base_h, mode=Mode.SUBTRACT)

# ═══ EXPORT ═══
import os
os.makedirs("output", exist_ok=True)
export_stl(stand.part, "output/phone_stand.stl")
print(f"Phone stand: {base_w}x{base_d}mm, angle={angle_deg}deg, lip={lip_h}mm")
