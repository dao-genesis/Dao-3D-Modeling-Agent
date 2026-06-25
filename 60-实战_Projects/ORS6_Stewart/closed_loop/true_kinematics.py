#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SR6 (ORS6 Stewart) — TRUE 3D parallel-mechanism kinematics with exact closure.

反者道之动 —— 旧 viewer 的"闭环"是假的: 它把 6 条腿的臂尖和接收器铰点**各自
独立**算出来, 然后在两点之间画一根杆, 杆长是"算出来多少就是多少"(从来不等于
175mm)。叠加 4 处硬编码铰点错误, 模型自然与 PDF / 真实零件对不上。

本模块从根本重建: 把 SR6 当作真正的 **6 腿并联机构**, 对每条腿施加**刚性连杆
长度约束** (rod == 175mm)。几何全部锚定在**实测零件真值**上:

    leg i: 舵机轴 O_i, 旋转轴 a_i, 摇臂长 L_arm,i
           arm_tip_i(theta) = O_i + L_arm * (cos th * u_i + sin th * (a_i x u_i))
    接收器铰点 B_i (随平台刚体运动): B_i^world(pose) = R(pose) @ B_i^local + t
    刚性约束:  |arm_tip_i(theta_i) - B_i^world(pose)| == ROD  (175mm, 所有 i)

真值来源 (见 ../HALLUCINATION_MAP.md):
    L_arm 主臂 = 50, 俯仰臂 = 75   (firmware 2a; STL horn->ball 实测距离)
    ROD = 175                      (firmware sqrt(28125+2500); PDF "175mm apart")
    接收器铰点 B_local             (Receiver STL 圆柱孔 axis 实测, receiver-local mm)
    舵机轴 O_i / 轴向 a_i          (L_Frame STL 实测: 主 X=108 Y=±30, 俯仰 X=45 Y=0,
                                    Z=46=servoPivotH; 轴向 ‖X 朝外, 臂在 YZ 平面摆动)

IK (单腿, 解析精确): 给定平台位姿 -> B_i^world -> 解 theta_i 使杆长 == 175
    (化为"圆-点距离"问题, 闭式 2 解, 取靠近上一解的分支)。
FK (数值): 给定 6 个臂角 -> 臂尖固定 -> 用 6 个杆长残差做最小二乘 (LM) 解 6 自由度位姿。
闭环: pose --IK--> 6θ --FK--> pose'。 ||pose - pose'|| ~ 1e-13 (机器精度),
    因几何自洽而**由构造成立** —— 这才是真正的闭环。
"""
from __future__ import annotations
import math
import numpy as np
from scipy.optimize import least_squares

# ── 不可质疑常数 (firmware + PDF) ──────────────────────────────────────────
ROD = 175.0               # 刚性连杆长 (M4 rod-end 球铰间距); firmware/PDF
HOME_H = 208.48           # home 时接收器主销高度 (servoPivotH 46 + baseH 162.48)
Z_SERVO = 46.0            # 舵机轴所在平面 Z = servoPivotH (frame 内壁 22.3 + servo 24)

# ── 实测舵机轴位置 (L_Frame STL + 标准 servo lug; 见 HALLUCINATION_MAP §2.4) ──
X_MAIN = 108.0            # 主舵机轴 |X| (mount X -51.9..-100.9, 轴 ~ -108)
Y_MAIN = 30.0             # 主舵机轴 |Y| (mount-hole 中心 Y = ±30)
X_PITCH = 45.0            # 俯仰舵机轴 |X| (朝内安装, ~ -45)

# 接收器铰点, receiver-LOCAL mm (Receiver STL 圆柱孔 axis 实测; z=0 取主销平面)
B_LOCAL = {
    "LowerLeft":  np.array([-59.98, 0.0,    0.0]),
    "UpperLeft":  np.array([-59.98, 0.0,    0.0]),
    "LowerRight": np.array([ 59.98, 0.0,    0.0]),
    "UpperRight": np.array([ 59.98, 0.0,    0.0]),
    "LeftPitch":  np.array([-61.0, -14.235, 53.126]),
    "RightPitch": np.array([ 61.0, -14.235, 53.126]),
}
ARMLEN = {"LowerLeft": 50., "UpperLeft": 50., "LowerRight": 50., "UpperRight": 50.,
          "LeftPitch": 75., "RightPitch": 75.}
SERVOS = list(B_LOCAL)

# 舵机轴位置 O_i (world mm)。主 4 个在两侧 frame, 俯仰 2 个朝内。
SERVO_O = {
    "LowerLeft":  np.array([-X_MAIN,   Y_MAIN, Z_SERVO]),
    "UpperLeft":  np.array([-X_MAIN,  -Y_MAIN, Z_SERVO]),
    "LowerRight": np.array([ X_MAIN,   Y_MAIN, Z_SERVO]),
    "UpperRight": np.array([ X_MAIN,  -Y_MAIN, Z_SERVO]),
    "LeftPitch":  np.array([-X_PITCH,  0.0,    Z_SERVO]),
    "RightPitch": np.array([ X_PITCH,  0.0,    Z_SERVO]),
}
# 轴向沿 X 朝外 (arch doc): 臂在竖直 YZ 平面内摆动以驱动 推力/滚转/俯仰。六轴皆 ‖X。
SERVO_AXIS = {s: np.array([1., 0., 0.]) for s in SERVOS}


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def euler_R(roll, pitch, yaw):
    """R = Rz(yaw) Ry(roll) Rx(pitch), 弧度。平台 X=side, Y=fwd, Z=up。"""
    cx, sx = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(roll),  math.sin(roll)
    cz, sz = math.cos(yaw),   math.sin(yaw)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def b_world(servo, pose):
    """接收器铰点世界坐标。pose = (tx, ty, tz, roll, pitch, yaw)。"""
    tx, ty, tz, ro, pi, yw = pose
    return euler_R(ro, pi, yw) @ B_LOCAL[servo] + np.array([tx, ty, tz])


class Leg:
    """一条 舵机+臂+杆 腿: 臂在 ⟂ 轴平面内画圆, 连杆刚性 175mm。"""

    def __init__(self, servo):
        self.servo = servo
        self.O = SERVO_O[servo].astype(float)
        self.a = _unit(SERVO_AXIS[servo].astype(float))
        self.L = ARMLEN[servo]
        ref = np.array([1., 0, 0]) if abs(self.a[0]) < 0.9 else np.array([0, 1., 0])
        self.u0 = _unit(ref - self.a * (self.a @ ref))   # 臂平面基 u0
        self.w0 = np.cross(self.a, self.u0)              # 臂平面基 w0 = a x u0

    def arm_tip(self, theta):
        return self.O + self.L * (math.cos(theta) * self.u0 + math.sin(theta) * self.w0)

    def ik(self, pose, prev=None):
        """解臂角使 |arm_tip - B| == ROD。返回 theta (rad) 或 None(不可达)。

        平面内化简: 把 B 投到臂平面; 臂尖在该平面半径 L 的圆上, 离面分量 h 为常数;
        故需臂尖与 B 投影点的平面内距离 d2d = sqrt(ROD^2 - h^2)。"""
        B = b_world(self.servo, pose)
        rel = B - self.O
        h = self.a @ rel                       # 离面分量 (常数)
        if ROD * ROD - h * h <= 0:
            return None
        d2d = math.sqrt(ROD * ROD - h * h)     # 需要的平面内臂尖<->B 距离
        bu = self.u0 @ rel
        bw = self.w0 @ rel
        rho = math.hypot(bu, bw)               # 平面内 O<->B投影 距离
        if rho < 1e-9:
            return None
        cosd = (self.L * self.L + rho * rho - d2d * d2d) / (2 * self.L * rho)
        if abs(cosd) > 1.0:
            return None                        # 此位姿不可装配
        base = math.atan2(bw, bu)
        delta = math.acos(max(-1., min(1., cosd)))
        cands = [base + delta, base - delta]
        if prev is not None:
            cands.sort(key=lambda t: abs(math.atan2(math.sin(t - prev), math.cos(t - prev))))
        return cands[0]


LEGS = {s: Leg(s) for s in SERVOS}


def ik_all(pose, prev=None):
    """6 腿 IK。任一腿不可达则返回 None。"""
    out = {}
    for s in SERVOS:
        th = LEGS[s].ik(pose, prev[s] if prev else None)
        if th is None:
            return None
        out[s] = th
    return out


def fk(angles, guess=None):
    """给定 6 臂角, 用 6 个杆长残差最小二乘解平台 6 自由度位姿。
    返回 (pose(6,), residuals(6,))。残差应 ~ 0 (机器精度)。"""
    tips = {s: LEGS[s].arm_tip(angles[s]) for s in SERVOS}

    def resid(pose):
        return [np.linalg.norm(tips[s] - b_world(s, pose)) - ROD for s in SERVOS]

    p0 = np.array(guess if guess is not None else (0., 0., HOME_H, 0., 0., 0.))
    sol = least_squares(resid, p0, method="lm", xtol=1e-14, ftol=1e-14, max_nfev=4000)
    return sol.x, np.array(sol.fun)


def home_angles():
    return ik_all((0., 0., HOME_H, 0., 0., 0.))


def rod_lengths(angles, pose):
    """各腿在 (angles, pose) 下的实际杆长 —— 验证恒为 175。"""
    return {s: float(np.linalg.norm(LEGS[s].arm_tip(angles[s]) - b_world(s, pose)))
            for s in SERVOS}


def closure_error(pose):
    """单个位姿的闭环: pose -> IK -> FK -> pose'。
    返回 dict(reachable, dt_mm, dr_deg, max_rod_err) 或 reachable=False。"""
    ang = ik_all(pose)
    if ang is None:
        return {"reachable": False}
    rod_err = max(abs(v - ROD) for v in rod_lengths(ang, pose).values())
    rec, _ = fk(ang, guess=pose)
    dt = float(np.linalg.norm(np.array(rec[:3]) - np.array(pose[:3])))
    dr = float(np.linalg.norm(np.degrees(np.array(rec[3:]) - np.array(pose[3:]))))
    return {"reachable": True, "dt_mm": dt, "dr_deg": dr, "max_rod_err": rod_err,
            "angles": ang, "recovered": tuple(rec)}


def default_workspace():
    """物理工作空间采样位姿 (firmware T-Code 量程内: 推力±60 / 平移±30 / 转角±20°)。"""
    poses = [(0., 0., HOME_H, 0., 0., 0.)]
    for dz in (-60, -30, 30, 60):
        poses.append((0., 0., HOME_H + dz, 0., 0., 0.))
    for dx in (-30, 30):
        poses.append((float(dx), 0., HOME_H, 0., 0., 0.))
    for dy in (-30, 30):
        poses.append((0., float(dy), HOME_H, 0., 0., 0.))
    for dr in (-20, 20):
        poses.append((0., 0., HOME_H, math.radians(dr), 0., 0.))
    for dp in (-20, 20):
        poses.append((0., 0., HOME_H, 0., math.radians(dp), 0.))
    poses.append((20., 15., HOME_H + 30, math.radians(10), math.radians(-8), 0.))
    poses.append((-15., -20., HOME_H - 25, math.radians(-12), math.radians(10), 0.))
    return poses


if __name__ == "__main__":
    ha = home_angles()
    print("home angles (deg):",
          {s: round(math.degrees(v), 2) for s, v in ha.items()})
    print("home assemblable:", ha is not None)
    worst_dt = worst_dr = worst_rod = 0.0
    n_ok = 0
    poses = default_workspace()
    print("\n per-pose closure:")
    for pose in poses:
        r = closure_error(pose)
        disp = tuple(round(x, 1) for x in pose)
        if not r["reachable"]:
            print(f"  {disp} -> UNREACHABLE")
            continue
        n_ok += 1
        worst_dt = max(worst_dt, r["dt_mm"])
        worst_dr = max(worst_dr, r["dr_deg"])
        worst_rod = max(worst_rod, r["max_rod_err"])
        print(f"  {disp} -> dt={r['dt_mm']:.2e}mm dr={r['dr_deg']:.2e}deg "
              f"rod_err={r['max_rod_err']:.2e}mm")
    print(f"\nposes tested: {len(poses)}  reachable: {n_ok}")
    print(f"worst rod-length error: {worst_rod:.3e} mm")
    print(f"worst closure: dt={worst_dt:.3e} mm  dr={worst_dr:.3e} deg")
