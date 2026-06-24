# -*- coding: utf-8 -*-
"""
ORS6_Stewart · 回归护栏 · 反者道之动根因锁

本源锚点 (来自 2026-04-18 法医诊断):
    firmware 2D IK 在 arm plane 内计算, arm plane 定义:
        - 经过 servo (sx, sy, servoPivotH)
        - 法向 = 世界 X 轴 (arm 绕 X 轴旋转)
        - 即 Y = sy 的竖直平面
    rod 物理长度 = √(mainRod² - mainArm² + mainArm²) = mainRod = 175mm (firmware).
    为了让 3D rod 恒 = 175, 必须 mount 与 tip 同在 Y = sy 平面.

曾经的错位:
    mount = (sx - sign_x * y, 0.0, servoPivotH + x)   ← 错, Y=0
    导致 |mount - tip| = √(175² + 37²) = 178.87mm ≠ 175mm
    视觉表现: rod 球头悬在空中, 受力铰接无法合拢.

已修复:
    mount = (sx - sign_x * y, sy, servoPivotH + x)    ← 对, Y=sy

此测试锁定本源, 确保修复永不回退.
"""
from __future__ import annotations

import math

import pytest

import ORS6_Stewart as S
from ORS6_Stewart.kinematics import StewartIK, TCODE_HOME, compute_rods
from ORS6_Stewart.parts import SERVO_SLOTS, SR6


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

# 姿态分类:
#   Z_ZERO_POSES: side = roll = 0 → pitch rod Z 方向无位移, 2D IK 精确
#   ANY_POSES:    所有代表性姿态, 用于验证 main rod 的 3D=175 铁律
Z_ZERO_POSES = {
    "home":        (5000, 5000, 5000, 5000, 5000, 5000),
    "thrust_up":   (9999, 5000, 5000, 5000, 5000, 5000),
    "thrust_down": (0,    5000, 5000, 5000, 5000, 5000),
    "fwd_max":     (5000, 9999, 5000, 5000, 5000, 5000),
    "fwd_min":     (5000, 0,    5000, 5000, 5000, 5000),
    "pitch_max":   (5000, 5000, 5000, 5000, 5000, 9999),
}
ANY_POSES = {
    **Z_ZERO_POSES,
    "side_max":    (5000, 5000, 9999, 5000, 5000, 5000),
    "side_min":    (5000, 5000, 0,    5000, 5000, 5000),
    "roll_max":    (5000, 5000, 5000, 5000, 9999, 5000),
    "extreme":     (9999, 9999, 9999, 9999, 9999, 9999),
}

ROD_TOLERANCE_MM = 0.05     # firmware IK 应精确到 0.01mm, 余量 5x
ARM_PLANE_TOLERANCE = 1e-9  # mount 与 tip 严格共面 (Y=sy)

SLOT_MAP = {name: (sx, sy, stype) for name, stype, sx, sy, _s in SERVO_SLOTS}
MAIN_SERVOS = [n for n, _t, _x, _y, _s in SERVO_SLOTS if _t == "main"]
PITCH_SERVOS = [n for n, _t, _x, _y, _s in SERVO_SLOTS if _t == "pitch"]


# ──────────────────────────────────────────────────────────────────────────────
# A. SR6 常数锚定 (硬编码防污染)
# ──────────────────────────────────────────────────────────────────────────────

def test_sr6_mainRod_is_175():
    """firmware hex sign: mainRod = 175mm (PDF p.26)."""
    assert SR6["mainRod"] == 175.0


def test_sr6_mainArm_is_50():
    assert SR6["mainArm"] == 50.0


def test_sr6_pitchArm_is_75():
    assert SR6["pitchArm"] == 75.0


def test_firmware_constant_28125():
    """firmware 2D IK magic: 28125 = mainRod² − mainArm² = 175² − 50²."""
    got = SR6["mainRod"] ** 2 - SR6["mainArm"] ** 2
    assert abs(got - 28125.0) < 0.1, f"rod²-arm² = {got}, firmware expects 28125"


def test_firmware_constant_36250():
    """firmware pitch IK magic: 36250 = pitchArm² + pitchRod² (pitchRod == mainRod)."""
    got = SR6["pitchArm"] ** 2 + SR6["mainRod"] ** 2
    assert abs(got - 36250.0) < 0.1, f"pitchArm²+rod² = {got}, firmware expects 36250"


def test_servo_slots_y_coords():
    """Main servos in two Y planes: ±37mm. Pitch servos on Y=0."""
    y_by_type = {"main": set(), "pitch": set()}
    for name, stype, _sx, sy, _sign in SERVO_SLOTS:
        y_by_type[stype].add(sy)
    assert y_by_type["main"] == {37.0, -37.0}
    assert y_by_type["pitch"] == {0.0}


# ──────────────────────────────────────────────────────────────────────────────
# B. 反者道之动 · 本源定律 (mount Y = sy)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pose_name", list(ANY_POSES.keys()))
@pytest.mark.parametrize("servo", list(SLOT_MAP.keys()))
def test_mount_y_equals_servo_sy(pose_name, servo):
    """反者道之动铁律: mount[1] 恒等于 servo_sy (不是 0).
    所有 servo × 所有姿态 · 不变量."""
    pose = ANY_POSES[pose_name]
    ik = StewartIK()
    geom = ik.compute_full_geometry(*pose)
    mount = geom["recv_mounts"][servo]
    _sx, sy, _t = SLOT_MAP[servo]
    assert abs(mount[1] - sy) < ARM_PLANE_TOLERANCE, (
        f"[{pose_name}/{servo}] mount.Y={mount[1]:.6f} 应=sy={sy}, 本源错位"
    )


@pytest.mark.parametrize("pose_name", list(ANY_POSES.keys()))
@pytest.mark.parametrize("servo", list(SLOT_MAP.keys()))
def test_arm_tip_y_equals_servo_sy(pose_name, servo):
    """arm tip 必在 Y = sy plane (arm 绕 X 旋转, 不跑出平面)."""
    pose = ANY_POSES[pose_name]
    ik = StewartIK()
    geom = ik.compute_full_geometry(*pose)
    tip = geom["arm_tips"][servo]
    _sx, sy, _t = SLOT_MAP[servo]
    assert abs(tip[1] - sy) < ARM_PLANE_TOLERANCE, (
        f"[{pose_name}/{servo}] tip.Y={tip[1]:.6f} 应=sy={sy}"
    )


@pytest.mark.parametrize("pose_name", list(ANY_POSES.keys()))
@pytest.mark.parametrize("servo", list(SLOT_MAP.keys()))
def test_rod_bay_offset_is_zero(pose_name, servo):
    """rod 端点 Y 差 = 0, 即 rod 端点共面 (必要条件)."""
    pose = ANY_POSES[pose_name]
    ik = StewartIK()
    geom = ik.compute_full_geometry(*pose)
    tip = geom["arm_tips"][servo]
    mount = geom["recv_mounts"][servo]
    dy = mount[1] - tip[1]
    assert abs(dy) < ARM_PLANE_TOLERANCE, (
        f"[{pose_name}/{servo}] rod bay offset = {dy:.6f}mm, 应 = 0"
    )


# ──────────────────────────────────────────────────────────────────────────────
# C. rod 物理长度 = 175mm (firmware 2D IK 恒等)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pose_name", list(ANY_POSES.keys()))
@pytest.mark.parametrize("servo", MAIN_SERVOS)
def test_main_rod_3d_length_is_175_any_pose(pose_name, servo):
    """main rod 铁律: 3D = 175mm for ALL reachable poses.
    main arm 只受 thrust/fwd/roll 影响, 共面在 Y=sy plane, 所以 3D=2D."""
    pose = ANY_POSES[pose_name]
    ik = StewartIK()
    geom = ik.compute_full_geometry(*pose)
    tip = geom["arm_tips"][servo]
    mount = geom["recv_mounts"][servo]
    rod_3d = math.sqrt(sum((m - t) ** 2 for m, t in zip(mount, tip)))
    assert abs(rod_3d - 175.0) < ROD_TOLERANCE_MM, (
        f"[{pose_name}/{servo}] rod_3d = {rod_3d:.4f}mm, 应 = 175.00 ± {ROD_TOLERANCE_MM}"
    )


@pytest.mark.parametrize("pose_name", list(Z_ZERO_POSES.keys()))
@pytest.mark.parametrize("servo", PITCH_SERVOS)
def test_pitch_rod_3d_length_is_175_when_z_zero(pose_name, servo):
    """pitch rod = 175mm 当 side=roll=0 (Z 平面无位移).
    side/roll ≠ 0 时 firmware 2D IK 用 dynamic bsq, 3D 长度会变化, 此为 firmware 固有近似."""
    pose = Z_ZERO_POSES[pose_name]
    ik = StewartIK()
    geom = ik.compute_full_geometry(*pose)
    tip = geom["arm_tips"][servo]
    mount = geom["recv_mounts"][servo]
    rod_3d = math.sqrt(sum((m - t) ** 2 for m, t in zip(mount, tip)))
    assert abs(rod_3d - 175.0) < ROD_TOLERANCE_MM, (
        f"[{pose_name}/{servo}] rod_3d = {rod_3d:.4f}mm, 应 = 175.00 ± {ROD_TOLERANCE_MM}"
    )


@pytest.mark.parametrize("pose_name", list(Z_ZERO_POSES.keys()))
def test_compute_rods_stress_zero_at_z_zero_poses(pose_name):
    """compute_rods API: side=roll=0 时所有 servo stress = 0%."""
    pose = Z_ZERO_POSES[pose_name]
    rods = compute_rods(pose)
    assert len(rods) == 6, f"应返回 6 根 rod, 得到 {len(rods)}"
    for r in rods:
        assert r["stress_pct"] < 0.05, (
            f"[{pose_name}/{r['servo']}] stress={r['stress_pct']}%, 应 < 0.05"
        )
        assert r["bay_offset_mm"] < 0.01, (
            f"[{pose_name}/{r['servo']}] bay_offset={r['bay_offset_mm']}mm, 应 < 0.01"
        )
        assert abs(r["rod_3d_mm"] - 175.0) < ROD_TOLERANCE_MM
        assert abs(r["rod_2d_mm"] - 175.0) < ROD_TOLERANCE_MM


@pytest.mark.parametrize("pose_name", list(ANY_POSES.keys()))
def test_compute_rods_main_stress_zero_any_pose(pose_name):
    """main rod stress = 0 对所有姿态成立 (main 只在 Y=sy 平面内)."""
    pose = ANY_POSES[pose_name]
    rods = compute_rods(pose)
    for r in rods:
        if r["type"] != "main":
            continue
        assert r["stress_pct"] < 0.05, (
            f"[{pose_name}/{r['servo']}] main stress={r['stress_pct']}%"
        )
        assert abs(r["rod_3d_mm"] - 175.0) < ROD_TOLERANCE_MM


# ──────────────────────────────────────────────────────────────────────────────
# D. 反者道之动 · 显式回归锁 (明确挡 mount Y=0 重新潜入)
# ──────────────────────────────────────────────────────────────────────────────

def test_regression_main_servo_mount_not_at_y0():
    """Lower/Upper 主舵机 mount Y != 0 (会在 Y=±37).
    若未来有人误改回 `mount = (.., 0.0, ..)`, 此测试 FAIL."""
    ik = StewartIK()
    geom = ik.compute_full_geometry(*TCODE_HOME)
    for name in ("LowerLeft", "UpperLeft", "UpperRight", "LowerRight"):
        mount = geom["recv_mounts"][name]
        assert abs(mount[1]) > 30, (
            f"[{name}] mount.Y={mount[1]} 看起来退回 Y=0, 违反 arm plane 共面律"
        )


def test_regression_wrong_mount_would_give_178_87mm():
    """对比教学: 若 mount 错放 Y=0, |mount - tip| 会是 178.87mm (不可达).
    此测试构造错误值, 证明 '175 vs 178.87' 差距 = 本源错位标志."""
    ik = StewartIK()
    geom = ik.compute_full_geometry(*TCODE_HOME)
    tip = geom["arm_tips"]["LowerLeft"]  # tip.Y = +37
    mount_right = geom["recv_mounts"]["LowerLeft"]  # mount.Y = +37

    # Correct: dy = 0, rod = 175
    rod_correct = math.sqrt(sum((m - t) ** 2 for m, t in zip(mount_right, tip)))
    assert abs(rod_correct - 175.0) < ROD_TOLERANCE_MM

    # Buggy version: mount.Y forced to 0, dy = -37
    mount_buggy = (mount_right[0], 0.0, mount_right[2])
    rod_buggy = math.sqrt(sum((m - t) ** 2 for m, t in zip(mount_buggy, tip)))
    assert abs(rod_buggy - 178.87) < 0.05, (
        f"错位版应给出 178.87mm (本源 bug 特征值), 实得 {rod_buggy:.4f}"
    )
    # 差距是 arm plane 错位的 fingerprint
    assert rod_buggy - rod_correct > 3.85, "本源错位应让 rod 虚长 ~3.87mm"


# ──────────────────────────────────────────────────────────────────────────────
# E. home 姿态绝对值 (硬编码护栏)
# ──────────────────────────────────────────────────────────────────────────────

# Main rods 在 home 时 (thrust=fwd=0): x_fw=162.48, y_fw=15 → mount_x 偏移 ±15
# Pitch rods 在 home 时因 5500·sin/cos(15°) 偏移 mount 到 (~±107.73, 0, 222.72)
HOME_EXPECTED_MOUNT = {
    "LowerLeft":  (-84.60,   37.0, 208.48),
    "UpperLeft":  (-84.60,  -37.0, 208.48),
    "LeftPitch":  (-107.73,  0.0, 222.72),
    "RightPitch":  (107.73,  0.0, 222.72),
    "UpperRight":  (84.60,  -37.0, 208.48),
    "LowerRight":  (84.60,   37.0, 208.48),
}


@pytest.mark.parametrize("servo", list(HOME_EXPECTED_MOUNT.keys()))
def test_home_mount_coordinates_exact(servo):
    """home 姿态 mount 绝对坐标 (法医诊断时人工验证过的真值)."""
    ik = StewartIK()
    mount = ik.compute_full_geometry(*TCODE_HOME)["recv_mounts"][servo]
    expected = HOME_EXPECTED_MOUNT[servo]
    for axis, (got, want) in enumerate(zip(mount, expected)):
        assert abs(got - want) < 0.05, (
            f"[{servo}] axis={axis}: got={got:.4f}, want={want}"
        )


def test_home_receiver_z_208_48():
    """home Z = HOME_H = servoPivotH + baseH = 46 + 162.48 = 208.48mm."""
    ik = StewartIK()
    _, _, tz, *_ = ik.compute_receiver_pose(*TCODE_HOME)
    assert abs(tz - 208.48) < 0.01


# ──────────────────────────────────────────────────────────────────────────────
# F. 三源交叉 (verify + ik-verify + compute_rods 互洽)
# ──────────────────────────────────────────────────────────────────────────────

def test_verify_assembly_all_pass():
    """verify_assembly V1-V8 全 PASS."""
    results = S.verify_assembly()
    failed = []
    for row in results:
        # 兼容 2-tuple / 3-tuple / dict
        if isinstance(row, dict):
            ok = row.get("ok") or row.get("passed") or row.get("pass")
            name = row.get("name") or row.get("check") or str(row)
        elif len(row) >= 2:
            name, ok = row[0], row[1]
        else:
            continue
        if not ok:
            failed.append(name)
    assert not failed, f"verify_assembly 失败: {failed}"


def test_verify_ik_standalone_all_pass():
    """IK 独立 11 项全 PASS (包含 28125 / 36250 / 常数)."""
    results = S.verify_ik_standalone()
    failed = [name for name, ok, _ in results if not ok]
    assert not failed, f"verify_ik_standalone 失败: {failed}"
