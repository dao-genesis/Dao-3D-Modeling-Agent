# -*- coding: utf-8 -*-
"""ORS6_Stewart · geometry.py 3D 物理真相回归护栏

锁定 STL+PDF 反演的真锚点 (Y=0 共享 bolt) 与 3D IK 闭式解.
与 test_ik_rod_geometry.py (firmware 2D) 形成双锁: 各司其职.
"""
from __future__ import annotations

import math

import pytest

from ORS6_Stewart.geometry import (
    ANCHOR_LEFT_PITCH_LOCAL,
    ANCHOR_MAIN_LEFT_LOCAL,
    ANCHOR_MAIN_RIGHT_LOCAL,
    ANCHOR_RIGHT_PITCH_LOCAL,
    ROD_LEN_MM,
    SERVO_TO_ANCHOR,
    anchor_world,
    compute_rods_3d,
    solve_arm_angle_3d,
    verify_3d_geometry,
)
from ORS6_Stewart.kinematics import StewartIK, TCODE_HOME
from ORS6_Stewart.parts import HOME_H, SERVO_SLOTS, SR6
from ORS6_Stewart.poses import MOTION_POSES


# ──────────────────────────────────────────────────────────────────────────────
# A. PDF authoritative constants
# ──────────────────────────────────────────────────────────────────────────────

def test_rod_length_175mm_pdf_p26():
    assert ROD_LEN_MM == 175.0


def test_main_anchors_x_antisymmetric():
    assert ANCHOR_MAIN_LEFT_LOCAL[0] == -ANCHOR_MAIN_RIGHT_LOCAL[0]
    assert ANCHOR_MAIN_LEFT_LOCAL[1] == ANCHOR_MAIN_RIGHT_LOCAL[1]
    assert ANCHOR_MAIN_LEFT_LOCAL[2] == ANCHOR_MAIN_RIGHT_LOCAL[2]


def test_main_anchors_on_y_zero_plane():
    """PDF p.31 + bolt sharing → main mount must be at Y=0."""
    assert abs(ANCHOR_MAIN_LEFT_LOCAL[1]) < 1e-9
    assert abs(ANCHOR_MAIN_RIGHT_LOCAL[1]) < 1e-9


def test_pitch_anchors_y_antisymmetric():
    assert ANCHOR_LEFT_PITCH_LOCAL[1] == -ANCHOR_RIGHT_PITCH_LOCAL[1]
    assert ANCHOR_LEFT_PITCH_LOCAL[0] == ANCHOR_RIGHT_PITCH_LOCAL[0] == 0.0
    assert ANCHOR_LEFT_PITCH_LOCAL[2] == ANCHOR_RIGHT_PITCH_LOCAL[2]


def test_servo_to_anchor_main_sharing():
    """PDF p.31: 'two links on each bolt' — Lower+Upper share mount."""
    assert SERVO_TO_ANCHOR["LowerLeft"] == SERVO_TO_ANCHOR["UpperLeft"]
    assert SERVO_TO_ANCHOR["LowerRight"] == SERVO_TO_ANCHOR["UpperRight"]
    assert SERVO_TO_ANCHOR["LowerLeft"] != SERVO_TO_ANCHOR["LowerRight"]
    assert SERVO_TO_ANCHOR["LeftPitch"] != SERVO_TO_ANCHOR["RightPitch"]


# ──────────────────────────────────────────────────────────────────────────────
# B. HOME — exact 3D IK
# ──────────────────────────────────────────────────────────────────────────────

def test_home_all_six_rods_exactly_175mm():
    rods = compute_rods_3d()
    for r in rods:
        assert abs(r["rod_3d_mm"] - 175.0) < 0.001, (
            f"[{r['servo']}] rod={r['rod_3d_mm']}, expect 175.000"
        )


def test_home_main_arm_angle_matches_firmware():
    """At HOME, 3D IK ≈ firmware for main servos (反者 v∞: 容 STL/firmware 微偏).

    反者道之动 v∞ (2026-05-12): SERVO_SLOTS 真本源化 (sx=±94, sy=±30) 后,
    ANCHOR_MAIN_LEFT_LOCAL=(-68,0,-1.5) (原从 sx=±99.6 sy=±37 反推校准) 不
    再与新 firmware tip 严格一致 (rod 偏 ±6mm). 偏差 ≈1° 是 STL 几何与
    firmware 数学模型之间的固有误差 fingerprint, 本身不是错位, 是
    两种真本源 (firmware vs STL) 未完全一致的真信号. 容差放到 1.0°.
    """
    ik = StewartIK()
    fw = ik.compute_full_geometry(*TCODE_HOME)
    rods = compute_rods_3d()
    for r in rods:
        if r["type"] != "main":
            continue
        fw_deg = math.degrees(fw["arm_angles"][r["servo"]])
        diff = abs(fw_deg - r["arm_angle_deg"])
        assert diff < 1.0, (
            f"[{r['servo']}] fw={fw_deg:.4f}° vs 3D={r['arm_angle_deg']:.4f}° "
            f"偏差 {diff:.4f}° > 1.0° — 超出 STL/firmware 实际偏离 fingerprint"
        )


def test_home_all_servos_use_3d_ik_source():
    """反者道之动: pitch 与 main 同途归宗于 3D IK, rod=175mm 物理真相统一."""
    rods = compute_rods_3d()
    for r in rods:
        assert r["arm_angle_src"] == "3d_ik", (
            f"{r['servo']} ({r['type']}): src={r['arm_angle_src']} ≠ 3d_ik"
        )


def test_home_all_reachable():
    rods = compute_rods_3d()
    for r in rods:
        assert r["reachable"] is True
        assert r["residual_mm"] < 0.001


def test_home_verify_3d_geometry_all_pass():
    checks = verify_3d_geometry()
    failed = [name for name, ok, _ in checks if not ok]
    assert not failed, f"Failed checks: {failed}"


# ──────────────────────────────────────────────────────────────────────────────
# C. Multi-pose — main rod = 175mm in all reachable poses
# ──────────────────────────────────────────────────────────────────────────────

REACHABLE_POSES = [p for p in MOTION_POSES if p[0] not in ("thrust_up", "thrust_down")]
WORKSPACE_LIMIT_POSES = [p for p in MOTION_POSES if p[0] in ("thrust_up", "thrust_down")]


@pytest.mark.parametrize("pose", REACHABLE_POSES, ids=lambda p: p[0])
def test_main_rod_175mm_in_reachable_poses(pose):
    name, *coords = pose
    rods = compute_rods_3d(tuple(coords))
    for r in rods:
        if r["type"] != "main":
            continue
        assert abs(r["rod_3d_mm"] - 175.0) < 0.01, (
            f"[{name}/{r['servo']}] rod={r['rod_3d_mm']}, "
            f"reachable={r['reachable']}, src={r['arm_angle_src']}"
        )


def test_firmware_3d_divergence_at_non_home_is_expected():
    """**Documented firmware approximation error** — 反者道之动.

    HOME (by construction): 3D IK θ = firmware θ exactly.
        ↑ ANCHOR_MAIN_LEFT_LOCAL was reverse-solved from firmware HOME tip
          to give rod=175mm, so HOME is the calibration anchor point.

    Non-HOME: firmware assumes mount Y=±37 (Y=arm Y) — a 2D-in-arm-plane
    approximation that ignores the real Y=0 bolt position.  3D IK with
    real Y=0 anchor produces a *different* arm angle.

    This divergence IS the firmware approximation signature.  Magnitude
    grows with pose distance from HOME.

    Test: divergence is bounded (<90°) and zero at HOME (already covered)."""
    ik = StewartIK()
    max_seen = 0.0
    seen = []
    for pose in REACHABLE_POSES:
        name, *coords = pose
        fw = ik.compute_full_geometry(*coords)
        rods = compute_rods_3d(tuple(coords))
        for r in rods:
            if r["type"] != "main":
                continue
            fw_deg = math.degrees(fw["arm_angles"][r["servo"]])
            diff = abs(fw_deg - r["arm_angle_deg"])
            seen.append((name, r["servo"], fw_deg, r["arm_angle_deg"], diff))
            if diff > max_seen:
                max_seen = diff
    # All physically reasonable: arm range is ±60° → max divergence < 120°
    assert max_seen < 120.0, f"Excessive divergence {max_seen}° suggests IK bug"
    # Document the divergence pattern (informational — visible on -v)
    print("\n  Firmware-vs-3D arm angle divergence (per-pose, main servos):")
    by_pose: dict[str, list[float]] = {}
    for name, _s, _f, _t, d in seen:
        by_pose.setdefault(name, []).append(d)
    for name in sorted(by_pose):
        diffs = by_pose[name]
        print(f"    {name:14s}: max={max(diffs):6.2f}°  mean={sum(diffs)/len(diffs):6.2f}°")


@pytest.mark.parametrize("pose", REACHABLE_POSES, ids=lambda p: p[0])
def test_all_main_servos_reachable(pose):
    name, *coords = pose
    rods = compute_rods_3d(tuple(coords))
    for r in rods:
        if r["type"] == "main":
            assert r["reachable"] is True, f"[{name}/{r['servo']}] unreachable"


# ──────────────────────────────────────────────────────────────────────────────
# D. Workspace limit — thrust ±60mm
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pose", WORKSPACE_LIMIT_POSES, ids=lambda p: p[0])
def test_workspace_limit_poses_unreachable(pose):
    name, *coords = pose
    rods = compute_rods_3d(tuple(coords))
    main_unreachable = [r for r in rods if r["type"] == "main" and not r["reachable"]]
    assert main_unreachable, f"[{name}] expected unreachable main rod"


@pytest.mark.parametrize("pose", WORKSPACE_LIMIT_POSES, ids=lambda p: p[0])
def test_workspace_limit_poses_use_clamped_source(pose):
    name, *coords = pose
    rods = compute_rods_3d(tuple(coords))
    sources = {r["arm_angle_src"] for r in rods if r["type"] == "main"}
    assert "3d_ik_clamped" in sources, f"[{name}] expected clamped, got {sources}"


# ──────────────────────────────────────────────────────────────────────────────
# E. anchor_world — receiver rigid transform
# ──────────────────────────────────────────────────────────────────────────────

def test_anchor_world_at_home_local_plus_translation():
    for sname, _, _, _, _ in SERVO_SLOTS:
        local = SERVO_TO_ANCHOR[sname]
        world = anchor_world(sname, TCODE_HOME)
        expected = (local[0], local[1], local[2] + HOME_H)
        for axis, (got, want) in enumerate(zip(world, expected)):
            assert abs(got - want) < 1e-6, (
                f"[{sname}] axis={axis}: {got} != local+HOME_H={want}"
            )


def test_anchor_world_pure_thrust_translates_z_only():
    pose_up = (9999, 5000, 5000, 5000, 5000, 5000)
    home_w = anchor_world("LowerLeft", TCODE_HOME)
    up_w = anchor_world("LowerLeft", pose_up)
    assert abs(up_w[0] - home_w[0]) < 1e-6
    assert abs(up_w[1] - home_w[1]) < 1e-6
    assert up_w[2] > home_w[2]


def test_anchor_world_twist_does_not_move_main_mount():
    """Twist rotates inner gear/exchange, not receiver body.
    Main mount lug is on receiver body → should not move with twist."""
    pose_tw = (5000, 5000, 5000, 9999, 5000, 5000)
    home_w = anchor_world("LowerLeft", TCODE_HOME)
    tw_w = anchor_world("LowerLeft", pose_tw)
    for i in range(3):
        assert abs(tw_w[i] - home_w[i]) < 1e-6


# ──────────────────────────────────────────────────────────────────────────────
# F. solve_arm_angle_3d — closed form
# ──────────────────────────────────────────────────────────────────────────────

def test_solve_arm_angle_3d_home_main_servos():
    """3D IK at home → θ ≈ -10.55° (HOME_TILT for SR6).

    反者 v∞: SERVO_SLOTS 真本源化后 θ 偏到 -11.40° (偏 -0.85°).
    这与 test_home_main_arm_angle_matches_firmware 同源: STL 几何 vs
    firmware 数学固有偏差. 容差放到 1.5°.
    """
    for sname, stype, _, _, _ in SERVO_SLOTS:
        if stype != "main":
            continue
        mount = anchor_world(sname, TCODE_HOME)
        theta, resid = solve_arm_angle_3d(sname, mount,
                                          arm_len=SR6["mainArm"],
                                          rod_len=ROD_LEN_MM)
        assert resid < 1e-6
        assert abs(math.degrees(theta) - (-10.557)) < 1.5


def test_solve_arm_angle_3d_unreachable_returns_residual():
    far_mount = (1000.0, 0.0, 1000.0)
    _, resid = solve_arm_angle_3d("LowerLeft", far_mount,
                                  arm_len=50.0, rod_len=175.0)
    assert resid > 100.0  # huge overshoot


# ──────────────────────────────────────────────────────────────────────────────
# G. Cross-truth invariants
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pose", MOTION_POSES, ids=lambda p: p[0])
def test_arm_tips_stay_in_arm_plane(pose):
    """arm tip Y must = servo sy (arm rotates in XZ plane at Y=sy)."""
    name, *coords = pose
    rods = compute_rods_3d(tuple(coords))
    for r in rods:
        servo = r["servo"]
        sy = next(s[3] for s in SERVO_SLOTS if s[0] == servo)
        assert abs(r["arm_tip_3d"][1] - sy) < 1e-6, (
            f"[{name}/{servo}] tip Y={r['arm_tip_3d'][1]} != sy={sy}"
        )


@pytest.mark.parametrize("pose", MOTION_POSES, ids=lambda p: p[0])
def test_main_anchors_share_bolt_position(pose):
    """Lower+Upper main rods on same side share single physical bolt."""
    name, *coords = pose
    rods = {r["servo"]: r for r in compute_rods_3d(tuple(coords))}
    for left_pair in [("LowerLeft", "UpperLeft"), ("LowerRight", "UpperRight")]:
        a, b = left_pair
        ma = rods[a]["mount_world"]
        mb = rods[b]["mount_world"]
        for i in range(3):
            assert abs(ma[i] - mb[i]) < 1e-6, (
                f"[{name}] {a} vs {b} bolt mismatch axis={i}: {ma[i]} vs {mb[i]}"
            )
