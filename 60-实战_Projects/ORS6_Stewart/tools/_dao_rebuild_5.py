# -*- coding: utf-8 -*-
"""Rebuild 5 key poses with current (v2.2.4) assembly logic."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ORS6_Stewart.assembly import build_cadquery
from ORS6_Stewart.poses import MOTION_POSES

POSES_5 = {"home", "forward", "side_right", "pitch_up", "roll_left"}
results = []
for entry in MOTION_POSES:
    name = entry[0]
    coords = entry[1:]
    if name not in POSES_5:
        continue
    r = build_cadquery(pose=tuple(coords), label=name)
    results.append((name, r["stl_kb"], r["step_kb"]))
    print(f"  built {name}: stl={r['stl_kb']}KB step={r['step_kb']}KB")
print(f"TOTAL: {len(results)}/5")
