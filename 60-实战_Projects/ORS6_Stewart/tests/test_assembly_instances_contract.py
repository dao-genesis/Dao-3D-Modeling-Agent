# -*- coding: utf-8 -*-
"""
ORS6_Stewart · viewer API contract guard

反者道之动 · 锁 viewer/index.html loadAssemblyInstances() 与 kinematics.py
assembly_instances() 的契约, 防 pitcher 错位再现:

  v2.2.0~v2.2.3 错位:
    viewer 完全不处理 data.pitcher_arms, L/R_Pitcher 滞留 STL 自坐.
  v2.2.4 错位:
    viewer 误信 firmware shaft (X=±99.6) 是世界 servo, 强行平移
    L_Pitcher pivot→(-99.6,0,46), 致 STL 飞出 frame outer (X=-110), 完全错位.
  v2.2.5 假归位 (Y=9.0):
    误用 STL bbox Y_min=9 当 horn axis (实为 STL 边界, 非 servo horn 真位置).
    导致 horn-ball 距离 78mm, 偏 firmware pitchArm=75 的 4%.

  v∞ 真归位 (2026-05-12, Y=30.0):
    trimesh _dao_axis_v2.py SVD 找到真 horn axis = 两个 R=3.68mm 圆柱孔
    (servo horn flange) 中心, Y=30.0. 真 ball axis (M4 rod end pin) =
    (-39.74, 97.72, 50.25). horn-ball 距离 = √(32.24²+67.72²+1.5²) =
    75.00mm = firmware pitchArm ✓ (公理对齐).

  本测试锁:
    1. assembly_instances() 在 home pose 必返回 2 个 pitcher_arms 项
    2. 每项必含 stl/pivot/shaft/arm_angle_deg + angle_delta_deg
    3. pivot = STL trimesh axis-SVD 真 horn (X=∓7.5, Y=30.0, Z=51.75)
    4. shaft = firmware servo coord (X=±99.6, Y=0, Z=46) — kept for compat
    5. home pose 下 angle_delta_deg = 0.0
    6. 非 home pose 时 angle_delta_deg ≠ 0
    7. horn → ball 距离 = 75mm (firmware pitchArm 公理对齐)
"""
from __future__ import annotations

import pytest

from ORS6_Stewart.kinematics import (
    StewartIK, TCODE_HOME, assembly_instances, PITCHER_PIVOT_STL,
)


def test_assembly_instances_returns_two_pitcher_arms_at_home():
    inst = assembly_instances(TCODE_HOME)
    assert "pitcher_arms" in inst, "API must expose pitcher_arms list"
    pa = inst["pitcher_arms"]
    assert len(pa) == 2, f"expected 2 pitcher arms (Left+Right), got {len(pa)}"
    servos = {p["servo"] for p in pa}
    assert servos == {"LeftPitch", "RightPitch"}


def test_pitcher_arms_have_required_keys_for_viewer():
    """viewer/index.html loadAssemblyInstances() 依赖的 6 个字段 (v2.2.5)."""
    REQUIRED = {"servo", "stl", "pivot", "shaft", "arm_angle_deg", "angle_delta_deg"}
    pa = assembly_instances(TCODE_HOME)["pitcher_arms"]
    for p in pa:
        missing = REQUIRED - p.keys()
        assert not missing, (
            f"{p['servo']}: pitcher_arms entry missing keys {missing} — "
            f"viewer 端 placement (natural pivot rotation) 将无法计算, "
            f"视觉错位回归. 见 v2.2.5 本源归位."
        )


def test_pitcher_shaft_at_frame_top_servo_position():
    """Pitcher servo shaft (X=±45, Y=0, Z=46) — 真本源 SERVO_SLOTS.

    反者道之动 v∞: 旧 ±99.6 是硬编码幻觉, 真值 ±45 (PDF p.22 pitch axle
    朝 frame 内, 距 frame 内壁 X=∓47 约 2mm, axle 突入 receiver 空间).
    """
    pa = {p["servo"]: p for p in assembly_instances(TCODE_HOME)["pitcher_arms"]}
    assert pa["LeftPitch"]["shaft"] == [-45.0, 0.0, 46.0], (
        f"LeftPitch shaft 真值 (-45.0, 0, 46), 实得 {pa['LeftPitch']['shaft']}"
    )
    assert pa["RightPitch"]["shaft"] == [45.0, 0.0, 46.0]


def test_pitcher_pivot_is_stl_natural_world_position():
    """反者道之动 v∞: pivot = STL trimesh 真 horn axis (圆柱孔 SVD 实测).

    核心断言: pivot ≠ shaft, 且 pivot Y=30.0 (旧 v2.2.5 用 Y=9.0=bbox_Y_min 是
    幻觉, 非真 horn axis). 修订动机: 旧 Y=9 致 horn-ball 距离 78mm 偏 firmware
    pitchArm=75 的 4%, 用 trimesh axis-SVD 真值 Y=30 后 距离精确 75.00mm.
    """
    pa = {p["servo"]: p for p in assembly_instances(TCODE_HOME)["pitcher_arms"]}
    assert pa["LeftPitch"]["pivot"] == [-7.5, 30.0, 51.75], (
        f"L_Pitcher 真 horn axis 必须是 (-7.5, 30.0, 51.75), 实得 "
        f"{pa['LeftPitch']['pivot']} (旧 v2.2.5 错值 Y=9.0 已废)"
    )
    assert pa["RightPitch"]["pivot"] == [7.5, 30.0, 51.75], (
        f"R_Pitcher 真 horn axis 必须是 (7.5, 30.0, 51.75), 实得 "
        f"{pa['RightPitch']['pivot']}"
    )
    # Crucial: pivot ≠ shaft. 这两者分离是必须保持的觉悟.
    for p in pa.values():
        assert p["pivot"] != p["shaft"], (
            f"{p['servo']}: pivot == shaft 意味着回归 v2.2.4 错位. "
            f"pivot 是 STL 真 horn axis, shaft 是 firmware IK; 两者必须分立."
        )


def test_pitcher_pivot_consistent_with_module_constant():
    """API 输出的 pivot 与 kinematics.PITCHER_PIVOT_STL 单源真理一致."""
    pa = {p["servo"]: p for p in assembly_instances(TCODE_HOME)["pitcher_arms"]}
    for stl_name, expected in PITCHER_PIVOT_STL.items():
        srv = "LeftPitch" if stl_name.startswith("L_") else "RightPitch"
        assert tuple(pa[srv]["pivot"]) == expected, (
            f"{stl_name} pivot inconsistent: API={pa[srv]['pivot']} "
            f"vs PITCHER_PIVOT_STL[{stl_name}]={expected}"
        )


def test_pitcher_stl_correctly_assigned_per_side():
    pa = {p["servo"]: p for p in assembly_instances(TCODE_HOME)["pitcher_arms"]}
    assert pa["LeftPitch"]["stl"] == "L_Pitcher"
    assert pa["RightPitch"]["stl"] == "R_Pitcher"


def test_home_pose_has_zero_angle_delta_deg():
    """STL 自然形状已含 +16.35° home tilt, home 时 viewer 端不应再旋转.

    v2.2.4 反向审视: 我曾错用 arm_angle_deg (绝对 16.35°) 旋转 STL,
    令 STL 在 home 时被多转 16.35° → 视觉错位仍在.
    正解: 用 angle_delta_deg (相对 home 的偏离) 与 main arm 一致.
    """
    pa = assembly_instances(TCODE_HOME)["pitcher_arms"]
    for p in pa:
        assert abs(p["angle_delta_deg"]) < 0.01, (
            f"{p['servo']}: home pose angle_delta_deg={p['angle_delta_deg']} "
            f"应为 0.0 (STL 自然形状已含 home tilt)"
        )


def test_pitcher_angle_delta_changes_at_non_home_pose():
    """Pitch slider 偏离 home 时, angle_delta_deg 必须随之偏离 0."""
    # R2 (pitch axis) up extreme → both pitchers rotate
    pose = (5000, 5000, 5000, 5000, 5000, 9999)
    pa = assembly_instances(pose)["pitcher_arms"]
    deltas = [p["angle_delta_deg"] for p in pa]
    assert any(abs(d) > 0.5 for d in deltas), (
        f"non-home pose angle_delta_deg={deltas} 全部 ≈ 0, "
        f"viewer 将无法响应 IK pose 变化"
    )


def test_pitcher_arm_angle_deg_at_home_is_firmware_tilt():
    """firmware home pitch arm tilt = +16.35° (HOME_TILT for pitchers)."""
    pa = assembly_instances(TCODE_HOME)["pitcher_arms"]
    for p in pa:
        assert abs(p["arm_angle_deg"] - 16.35) < 0.05, (
            f"{p['servo']}: firmware home tilt {p['arm_angle_deg']}° ≠ +16.35°"
        )


def test_consistency_with_main_arm_contract():
    """pitcher_arms 与 arms 必须采用相同的 (arm_angle_deg, angle_delta_deg) 双字段
    契约, 否则 viewer 端无法用统一逻辑处理两类 servo."""
    inst = assembly_instances(TCODE_HOME)
    arm_keys = set(inst["arms"][0].keys())
    pitcher_keys = set(inst["pitcher_arms"][0].keys())
    SHARED = {"servo", "shaft", "arm_angle_deg", "angle_delta_deg"}
    assert SHARED <= arm_keys, f"arms 缺字段: {SHARED - arm_keys}"
    assert SHARED <= pitcher_keys, f"pitcher_arms 缺字段: {SHARED - pitcher_keys}"
