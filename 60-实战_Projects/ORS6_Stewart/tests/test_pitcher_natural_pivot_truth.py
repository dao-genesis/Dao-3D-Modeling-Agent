# -*- coding: utf-8 -*-
"""
ORS6_Stewart · 本源 STL 自然 pivot 真相锁 (v∞ 2026-05-12)

反者道之动 · 道法自然:
  以 trimesh axis-SVD 直接提取 L/R_Pitcher STL 圆柱孔 axis (非 bbox 边界).
  PITCHER_PIVOT_STL 与 STL 实测 horn axis 一致.

  本源真相 (trimesh axis-SVD 实测 L_Pitcher.stl):
    bbox: X=[-46.7, +13.5], Y=[+9.0, +104.7], Z=[+45.0, +58.5]
    但 horn 端不在 Y_min=9.0 (那是 STL 边界凸起, 非 horn 轴).
    真 horn = 两个 R=3.68mm 圆柱孔 (servo horn flange) axis 中心
    Y=30.0 处, pivot @ (X=-7.5, Y=30.0, Z=51.75).
    R_Pitcher: 镜像 X (pivot @ +7.5, 其余同).

  v2.2.4 错位根: 误以 firmware shaft X=-99.6 是世界 servo, 背离 STL.
  v2.2.5 假归位 (Y=9): 误以 STL bbox Y_min 为 horn (bbox 边界非轴).
  v∞ 真归位 (Y=30): trimesh axis-SVD 是轴几何真中心.
  验证: horn(Y=30) → ball(Y=97.72) 距离 = 75.00mm = firmware pitchArm ✓
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Locate dao_mesh in 本源 (00-本源_Origin) for STL byte-level verification.
PROJECTS_DIR = Path(__file__).resolve().parents[2]  # 60-实战_Projects
AGENT_ROOT = PROJECTS_DIR.parent  # 3D建模Agent
DAO_ORIGIN = AGENT_ROOT / "00-本源_Origin"
if str(DAO_ORIGIN) not in sys.path:
    sys.path.insert(0, str(DAO_ORIGIN))

from ORS6_Stewart.kinematics import PITCHER_PIVOT_STL
from ORS6_Stewart.parts import stl_path


def _stl_bbox(name: str):
    """Read STL bbox using 本源 dao_mesh (zero-dep STL parser)."""
    import dao_mesh
    stats = dao_mesh.read_stl(stl_path(name))
    assert stats is not None, f"{name}: dao_mesh.read_stl returned None"
    return stats.bbox_min, stats.bbox_max


def test_l_pitcher_horn_y_within_stl_bounds():
    """L_Pitcher pivot.Y 必在 STL Y bbox 内 (但不需贴 Y_min).

    v∞ (2026-05-12): 旧测试错误地要求 horn 在 Y_min, 但 trimesh axis-SVD
    表明 horn axis 在 Y=30 (在 STL Y 范围 [9, 105] 内门部, 非边界).
    旧认为 Y_min=9 是 horn 端 是 bbox 边界凸起造成的幻觉.
    """
    bb_min, bb_max = _stl_bbox("L_Pitcher")
    piv = PITCHER_PIVOT_STL["L_Pitcher"]
    assert bb_min[1] <= piv[1] <= bb_max[1], (
        f"L_Pitcher pivot.Y={piv[1]} 越出 STL Y bbox="
        f"[{bb_min[1]:.2f}, {bb_max[1]:.2f}]"
    )


def test_r_pitcher_horn_y_within_stl_bounds():
    """R_Pitcher pivot.Y 必在 STL Y bbox 内."""
    bb_min, bb_max = _stl_bbox("R_Pitcher")
    piv = PITCHER_PIVOT_STL["R_Pitcher"]
    assert bb_min[1] <= piv[1] <= bb_max[1], (
        f"R_Pitcher pivot.Y={piv[1]} 越出 STL Y bbox="
        f"[{bb_min[1]:.2f}, {bb_max[1]:.2f}]"
    )


def test_pitcher_pivot_z_within_stl_bounds():
    """Natural pivot Z 必须在 STL Z bbox 内 (servoPivotH 附近)."""
    for name, piv in PITCHER_PIVOT_STL.items():
        bb_min, bb_max = _stl_bbox(name)
        assert bb_min[2] <= piv[2] <= bb_max[2], (
            f"{name} pivot.Z={piv[2]} 越出 STL bbox Z=[{bb_min[2]:.1f}, "
            f"{bb_max[2]:.1f}]"
        )
        # Pivot Z 应在 STL Z 中线附近 (horn 端水平方向)
        z_mid = (bb_min[2] + bb_max[2]) / 2
        assert abs(piv[2] - z_mid) < 5.0, (
            f"{name} pivot.Z={piv[2]} 偏离 STL Z 中线 {z_mid:.1f} 过远"
        )


def test_pitcher_pivot_x_mirror_symmetry():
    """L_Pitcher 与 R_Pitcher pivot.X 必为镜像."""
    l_piv = PITCHER_PIVOT_STL["L_Pitcher"]
    r_piv = PITCHER_PIVOT_STL["R_Pitcher"]
    assert l_piv[0] == -r_piv[0], (
        f"L_Pitcher pivot.X={l_piv[0]} 与 R_Pitcher pivot.X={r_piv[0]} "
        f"非镜像对称 (左右应 X 反号)."
    )
    assert l_piv[1] == r_piv[1], "Y 应相同 (镜像在 X=0 平面)"
    assert l_piv[2] == r_piv[2], "Z 应相同 (镜像在 X=0 平面)"


def test_pitcher_pivot_inside_natural_stl_x_range():
    """v2.2.5 核心反向审视: natural pivot.X 必须在 STL X bbox 内.

    曾经的 v2.2.4 错位假设 'pivot 在 firmware shaft X=∓99.6'. 但 L_Pitcher
    STL X bbox = [-46.7, +13.5] 根本不包含 X=-99.6 — 强行平移到 -99.6
    令 STL 飞出 frame outer wall (X=-109.9). 本测试锁此真相.
    """
    bb_min, bb_max = _stl_bbox("L_Pitcher")
    piv = PITCHER_PIVOT_STL["L_Pitcher"]
    assert bb_min[0] <= piv[0] <= bb_max[0], (
        f"L_Pitcher pivot.X={piv[0]} 越出 STL X bbox=[{bb_min[0]:.1f}, "
        f"{bb_max[0]:.1f}] — 视觉错位前兆."
    )

    bb_min, bb_max = _stl_bbox("R_Pitcher")
    piv = PITCHER_PIVOT_STL["R_Pitcher"]
    assert bb_min[0] <= piv[0] <= bb_max[0], (
        f"R_Pitcher pivot.X={piv[0]} 越出 STL X bbox=[{bb_min[0]:.1f}, "
        f"{bb_max[0]:.1f}] — 视觉错位前兆."
    )


def test_pitcher_pivot_distinct_from_firmware_shaft():
    """反者道之动: 本源 pivot ≠ firmware shaft, 两者职责分立.

    pivot — STL 圆柱孔 axis 真 horn 中心 (X=∓7.5).
    shaft — SERVO_SLOTS 中 servo axle 真 X (v∞ 真值 ∓45).
    若二者相等则 viewer 误用 shaft 当 horn 锚点 = v2.2.4 错位回归.

    v∞ (2026-05-12): SERVO_SLOTS 真值化后 gap 从 ~92mm 缩到 ~37.5mm (=45-7.5),
    仍足分立. 测试改为 gap > 30 (留余地).
    """
    from ORS6_Stewart.parts import SERVO_SLOTS
    firmware_shaft_x = {
        "L_Pitcher": next(s[2] for s in SERVO_SLOTS if s[0] == "LeftPitch"),
        "R_Pitcher": next(s[2] for s in SERVO_SLOTS if s[0] == "RightPitch"),
    }
    for name, piv in PITCHER_PIVOT_STL.items():
        sx = firmware_shaft_x[name]
        gap = abs(piv[0] - sx)
        assert gap > 30.0, (
            f"{name}: pivot.X={piv[0]} 与 servo shaft.X={sx} 相距 "
            f"{gap:.1f}mm < 30mm — 两者疑似混用, 错位回归."
        )
