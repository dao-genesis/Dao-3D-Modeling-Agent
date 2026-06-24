"""反者道之动 · 终极解构 · enclosure 装配真相

PDF p.29:
  "Install both halves of the frame into the base and secure them in place
   with 4x M4x16 bolts"

PDF p.30:
  "Install the lid onto the top of the enclosure"
  "Tuck all of the servo wires into the space between the frame and the tray"

实物图: Base + Lid 是外壳, Frame 是内部支架, 整体形如红色三角形结构.

当前 viewer:
  Base    X=±58  Y=2.5-74  Z=±68
  L_Frame X=-110~-47 (在 Base X 外!)
  R_Frame X=+47~+110 (在 Base X 外!)

判别 STL 自身真值 vs viewer placement 错位:
  - 读 STL 自然 bbox (无 placement)
  - 看 STL 是否 X 实际就在 ±50 范围内 (能装进 Base)
  - 或 STL 真的就在 X=±60-110 范围 (那就和 Base 不匹配)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import trimesh
import numpy as np
from ORS6_Stewart.parts import stl_path, PARTS

print("=" * 70)
print("STL 自然 bbox (无任何 placement)")
print("=" * 70)
KEY_PARTS = ["Base", "Lid", "L_Frame", "R_Frame", "Tray", "Receiver",
             "Arm", "L_Pitcher", "R_Pitcher", "WindowLid", "PowerBus", "Spacer"]
data = {}
for name in KEY_PARTS:
    try:
        m = trimesh.load(stl_path(name))
        bb_min = m.vertices.min(axis=0)
        bb_max = m.vertices.max(axis=0)
        size = bb_max - bb_min
        center = (bb_min + bb_max) / 2
        data[name] = (bb_min, bb_max, size, center)
        print(f"{name:14s} bbox X=[{bb_min[0]:+7.2f},{bb_max[0]:+7.2f}] "
              f"Y=[{bb_min[1]:+7.2f},{bb_max[1]:+7.2f}] "
              f"Z=[{bb_min[2]:+7.2f},{bb_max[2]:+7.2f}] "
              f"size=({size[0]:.1f},{size[1]:.1f},{size[2]:.1f}) "
              f"center=({center[0]:+.1f},{center[1]:+.1f},{center[2]:+.1f})")
    except Exception as e:
        print(f"{name:14s} ERROR: {e}")

print()
print("=" * 70)
print("分析关键: Frame 是否 X 自然在 ±50 内 (能装进 Base X=±58)?")
print("=" * 70)
bb_base = data["Base"]
bb_lframe = data["L_Frame"]
bb_rframe = data["R_Frame"]
print(f"Base   X={bb_base[0][0]:+.1f}~{bb_base[1][0]:+.1f}")
print(f"L_Frame X={bb_lframe[0][0]:+.1f}~{bb_lframe[1][0]:+.1f}")
print(f"R_Frame X={bb_rframe[0][0]:+.1f}~{bb_rframe[1][0]:+.1f}")

l_in_base = bb_lframe[0][0] >= bb_base[0][0] and bb_lframe[1][0] <= bb_base[1][0]
r_in_base = bb_rframe[0][0] >= bb_base[0][0] and bb_rframe[1][0] <= bb_base[1][0]
print(f"L_Frame 装进 Base? {l_in_base}")
print(f"R_Frame 装进 Base? {r_in_base}")
if not (l_in_base and r_in_base):
    print(">>> STL 自然位置: Frame 在 Base 外! 这是 STL 自身设计 (装配前位置).")
    print(">>> viewer 需要平移 Frame 进 Base, 或 STL 本来就是装配后位置 (Y 也不在 Base 内)")

print()
print("=" * 70)
print("Y 关系: 谁在谁之上?")
print("=" * 70)
for name in ["Base", "Tray", "L_Frame", "R_Frame", "Lid", "Receiver"]:
    if name in data:
        bb_min, bb_max, size, ctr = data[name]
        print(f"  {name:14s} Y=[{bb_min[1]:+7.2f}, {bb_max[1]:+7.2f}] center_Y={ctr[1]:+7.2f}")

print()
print("=" * 70)
print("Z 关系: Frame Z 跨度多大?")
print("=" * 70)
for name in ["Base", "Tray", "L_Frame", "R_Frame", "Lid", "Receiver"]:
    if name in data:
        bb_min, bb_max, size, ctr = data[name]
        print(f"  {name:14s} Z=[{bb_min[2]:+7.2f}, {bb_max[2]:+7.2f}] size_Z={size[2]:5.1f}")

# 关键判断: STL 是否设计为"装配后位置" (各部件已在世界坐标对位)
# 若是, viewer 应直接显示 STL 自然 bbox, 不再做额外 placement
# 若否, 需根据 PDF 装配步骤计算每个部件的世界位置
