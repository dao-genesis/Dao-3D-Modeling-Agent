"""反者道之动 · 测所有关键 STL 真实 bbox.""" 
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import trimesh
from ORS6_Stewart.parts import stl_path

for n in ["Receiver", "L_Frame", "R_Frame", "Base", "Lid",
          "Tray", "L_Pitcher", "R_Pitcher", "Arm",
          "Twist_Body", "Twist_Base", "Twist_Lid", "RingGear"]:
    try:
        m = trimesh.load(stl_path(n))
    except Exception as e:
        print(f"{n}: load err {e}")
        continue
    b = m.bounds
    sz = b[1] - b[0]
    print(f"{n:12s} X=[{b[0][0]:+7.1f},{b[1][0]:+7.1f}] "
          f"Y=[{b[0][1]:+7.1f},{b[1][1]:+7.1f}] "
          f"Z=[{b[0][2]:+7.1f},{b[1][2]:+7.1f}]  "
          f"size=({sz[0]:5.1f},{sz[1]:5.1f},{sz[2]:5.1f})")
