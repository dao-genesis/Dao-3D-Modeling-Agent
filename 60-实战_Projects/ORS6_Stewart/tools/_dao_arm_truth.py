# -*- coding: utf-8 -*-
"""反者道之动 · Arm STL 真实形状探测.

诘问: Arm STL 的 50mm arm 几何在哪? horn 在 X=67.5, 但 X-spread 只 28mm,
不够装 50mm arm. 难道 arm 长 bar 在 Y 方向?
若 Y 方向, 与 firmware IK arm 旋转(绕 Y 轴, arm 在 XZ 平面)矛盾.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import trimesh
from ORS6_Stewart.parts import stl_path

print("=== Arm STL 顶点云分析 ===")
m = trimesh.load(stl_path("Arm"))
v = m.vertices
print(f"  vertices: {len(v)}")
print(f"  bbox: X={v[:,0].min():.1f}..{v[:,0].max():.1f}  Y={v[:,1].min():.1f}..{v[:,1].max():.1f}  Z={v[:,2].min():.1f}..{v[:,2].max():.1f}")

# horn cluster: small stub at X=53..82, Y around 0
import numpy as np
HORN_X_RANGE = (53, 82)
HORN_Y_RANGE = (-15, 15)
mask_horn = (v[:,0] >= HORN_X_RANGE[0]) & (v[:,0] <= HORN_X_RANGE[1]) & (v[:,1] >= HORN_Y_RANGE[0]) & (v[:,1] <= HORN_Y_RANGE[1])
horn = v[mask_horn]
print(f"\n  Horn cluster (X:{HORN_X_RANGE},Y:{HORN_Y_RANGE}): {len(horn)} pts")
if len(horn):
    print(f"    range  X={horn[:,0].min():.1f}..{horn[:,0].max():.1f}  Y={horn[:,1].min():.1f}..{horn[:,1].max():.1f}  Z={horn[:,2].min():.1f}..{horn[:,2].max():.1f}")
    print(f"    center ({horn[:,0].mean():.1f}, {horn[:,1].mean():.1f}, {horn[:,2].mean():.1f})")

# Find the FAR end (rod attachment / arm tip)
# arm should be 50mm from horn. let's check Y direction first
print(f"\n  Arm tip search (far from horn center 67.5,0,51.5 by ~50mm):")
horn_center = np.array([67.5, 0, 51.5])
dist = np.linalg.norm(v - horn_center, axis=1)
print(f"    distance range: {dist.min():.1f}..{dist.max():.1f}")
# Far cluster (>40mm from horn)
far_mask = dist > 40
far = v[far_mask]
if len(far):
    print(f"    Far points (>40mm): {len(far)}")
    print(f"    range  X={far[:,0].min():.1f}..{far[:,0].max():.1f}  Y={far[:,1].min():.1f}..{far[:,1].max():.1f}  Z={far[:,2].min():.1f}..{far[:,2].max():.1f}")
    print(f"    center ({far[:,0].mean():.1f}, {far[:,1].mean():.1f}, {far[:,2].mean():.1f})")
# Find specifically the tip (max distance to horn)
tip_idx = np.argmax(dist)
tip = v[tip_idx]
print(f"    farthest single pt: ({tip[0]:.1f}, {tip[1]:.1f}, {tip[2]:.1f}) dist={dist[tip_idx]:.1f}mm")

# Cluster of small radius around the farthest point — find rod-end small cluster
TIP_RADIUS = 5
near_tip = np.linalg.norm(v - tip, axis=1) < TIP_RADIUS
tip_cluster = v[near_tip]
print(f"    tip cluster (R<{TIP_RADIUS}mm of farthest): {len(tip_cluster)} pts")
if len(tip_cluster):
    print(f"    cluster  X={tip_cluster[:,0].min():.1f}..{tip_cluster[:,0].max():.1f}  Y={tip_cluster[:,1].min():.1f}..{tip_cluster[:,1].max():.1f}  Z={tip_cluster[:,2].min():.1f}..{tip_cluster[:,2].max():.1f}")
    cx, cy, cz = tip_cluster[:,0].mean(), tip_cluster[:,1].mean(), tip_cluster[:,2].mean()
    print(f"    cluster center ({cx:.1f}, {cy:.1f}, {cz:.1f})")
    
    # Now compute: what's the arm angle from horn (67.5,0,51.5) to this tip?
    # arm rotates around Y axis. arm vector in XZ plane: (cx-67.5, cz-51.5)
    import math
    dx = cx - 67.5
    dz = cz - 51.5
    arm_len_xz = math.sqrt(dx*dx + dz*dz)
    arm_angle_deg = math.degrees(math.atan2(dz, dx))
    print(f"    → arm length in XZ plane: {arm_len_xz:.1f}mm")
    print(f"    → arm angle (XZ): {arm_angle_deg:.2f}° (firmware home: -10.55°)")
    print(f"    → tip Y: {cy:.1f} (rod plane Y? expected 0 ?)")

# Also check: is there a clear "spline horn" point (cylindrical bore)?
print("\n=== L_Pitcher STL 顶点云分析 ===")
m2 = trimesh.load(stl_path("L_Pitcher"))
v2 = m2.vertices
print(f"  vertices: {len(v2)}")
print(f"  bbox: X={v2[:,0].min():.1f}..{v2[:,0].max():.1f}  Y={v2[:,1].min():.1f}..{v2[:,1].max():.1f}  Z={v2[:,2].min():.1f}..{v2[:,2].max():.1f}")

# horn at (-7.5, 9.5, 51.75) per assembly.py PITCHER_PIVOT_STL (mirrored for L)
horn2 = np.array([-7.5, 9.5, 51.75])
dist2 = np.linalg.norm(v2 - horn2, axis=1)
print(f"  pitcher arm — distance from horn ({horn2[0]:.1f},{horn2[1]:.1f},{horn2[2]:.1f}):")
print(f"    range: {dist2.min():.1f}..{dist2.max():.1f}")
tip2_idx = np.argmax(dist2)
tip2 = v2[tip2_idx]
print(f"    farthest: ({tip2[0]:.1f}, {tip2[1]:.1f}, {tip2[2]:.1f}) dist={dist2[tip2_idx]:.1f}mm")
near_tip2 = np.linalg.norm(v2 - tip2, axis=1) < 5
tip_cluster2 = v2[near_tip2]
if len(tip_cluster2):
    cx2, cy2, cz2 = tip_cluster2[:,0].mean(), tip_cluster2[:,1].mean(), tip_cluster2[:,2].mean()
    import math
    dx2 = cx2 - horn2[0]
    dy2 = cy2 - horn2[1]
    dz2 = cz2 - horn2[2]
    print(f"    tip cluster center: ({cx2:.1f}, {cy2:.1f}, {cz2:.1f})")
    print(f"    delta from horn: ({dx2:+.1f}, {dy2:+.1f}, {dz2:+.1f})")
    # Pitcher rotates around STL Y axis (assembly.py uses Base.Vector(0,1,0)).
    # So arm vector in XZ plane:
    arm_xz = math.sqrt(dx2*dx2 + dz2*dz2)
    arm_angle = math.degrees(math.atan2(dz2, dx2))
    print(f"    arm length in XZ: {arm_xz:.1f}mm  (firmware pitchArm=75mm)")
    print(f"    arm angle in XZ: {arm_angle:.2f}° (firmware home: +16.35°)")
    print(f"    arm Y component: {dy2:+.1f} (would not move under Y-rot)")
