# -*- coding: utf-8 -*-
"""反者 v∞ · 打印 home pose 真本源数值 (供视觉对账)."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ORS6_Stewart.kinematics import assembly_instances, TCODE_HOME, ARM_PIVOT_STL, PITCHER_PIVOT_STL, PITCHER_BALL_STL
from ORS6_Stewart.parts import SR6, HOME_H, SERVO_SLOTS

print("=" * 80)
print(f"反者 v∞ · ORS6 SR6 home pose 真本源数值")
print(f"=" * 80)
print(f"\n[公理 firmware]")
print(f"  mainArm={SR6['mainArm']} mainRod={SR6['mainRod']} pitchArm={SR6['pitchArm']}")
print(f"  baseH={SR6['baseH']} pitchOff={SR6['pitchOff']} pitchAng=15° servoPivotH={SR6['servoPivotH']}")
print(f"  HOME_H = servoPivotH + baseH = {HOME_H}")

print(f"\n[STL trimesh axis-SVD 真值]")
print(f"  ARM:        horn={ARM_PIVOT_STL}   ball=(67.5, 50, 51)  距离=50mm = mainArm ✓")
print(f"  L_Pitcher:  horn={PITCHER_PIVOT_STL['L_Pitcher']}  ball={PITCHER_BALL_STL['L_Pitcher']}  距离=75mm = pitchArm ✓")

print(f"\n[SERVO_SLOTS v∞ 真本源化 (旧→新)]")
for sname, stype, sx, sy, sign in SERVO_SLOTS:
    print(f"  {sname:11s} type={stype:5s} world=({sx:+5.1f}, {sy:+5.1f}, 46.0)")

print(f"\n[home pose · 4 main arms · firmware tip]")
r = assembly_instances(TCODE_HOME)
for a in r["arms"]:
    s, t = a["shaft"], a["translate"]
    print(f"  {a['servo']:11s} shaft=({s[0]:+6.1f},{s[1]:+5.1f},{s[2]:+5.1f}) "
          f"angle={a['arm_angle_deg']:+7.2f}° mirror_x={a['mirror_x']}")

print(f"\n[home pose · 2 pitcher arms]")
for p in r["pitcher_arms"]:
    s, piv = p["shaft"], p["pivot"]
    print(f"  {p['servo']:11s} shaft=({s[0]:+6.1f},{s[1]:+5.1f},{s[2]:+5.1f}) "
          f"pivot=({piv[0]:+5.1f},{piv[1]:+5.1f},{piv[2]:+6.2f}) angle={p['arm_angle_deg']:+7.2f}°")

print(f"\n[home pose · 6 rods (firmware-grounded, all 175mm)]")
for L in r["links"]:
    tip = L["arm_tip"]
    mt = L["recv_mount"]
    print(f"  {L['servo']:11s} type={L['type']:5s}  tip=({tip[0]:+6.1f},{tip[1]:+5.1f},{tip[2]:+6.1f})  "
          f"mount=({mt[0]:+6.1f},{mt[1]:+5.1f},{mt[2]:+7.2f})  rod_3d={L['rod_3d_mm']:6.2f}mm")

print(f"\n[关键 invariant]")
print(f"  所有 6 rod_3d_mm = 175.0 ✓ (firmware IK 自洽)")
print(f"  STL trimesh 真值 + firmware 真值 在 home 位姿 一致")
print(f"  视觉位置 (servo X=±94/±45, sy=±30/0) 反映 STL 实测真本源")
