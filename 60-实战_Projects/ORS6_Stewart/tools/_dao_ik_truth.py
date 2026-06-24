"""反者道之动 · 测 IK 在 HOME 与极姿下的几何真相."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ORS6_Stewart.kinematics import StewartIK, TCODE_HOME
from ORS6_Stewart.parts import SERVO_SLOTS, SR6, HOME_H

ik = StewartIK()


def report(label, pose):
    g = ik.compute_full_geometry(*pose)
    print(f"=== {label} pose={pose} ===")
    for s, t, sx, sy, _ in SERVO_SLOTS:
        tip = g["arm_tips"][s]
        mt = g["recv_mounts"][s]
        ang = math.degrees(g["arm_angles"][s])
        rod = math.sqrt(sum((tip[i] - mt[i]) ** 2 for i in range(3)))
        print(
            f"  {s:11s} type={t:5s} servo=({sx:+6.1f},{sy:+5.1f},46) "
            f"tip=({tip[0]:+7.2f},{tip[1]:+6.2f},{tip[2]:+6.2f}) "
            f"mount=({mt[0]:+7.2f},{mt[1]:+6.2f},{mt[2]:+6.2f}) "
            f"ang={ang:+7.2f}deg rod={rod:.2f}"
        )


print(f"HOME_H = {HOME_H}")
print(f"mainArm = {SR6['mainArm']}, pitchArm = {SR6['pitchArm']}, mainRod = {SR6['mainRod']}")
print()
report("HOME", TCODE_HOME)
print()
report("MAX_LIFT", (9999, 5000, 5000, 9999, 5000, 5000))
print()
report("FORWARD", (5000, 9999, 5000, 5000, 9999, 5000))
