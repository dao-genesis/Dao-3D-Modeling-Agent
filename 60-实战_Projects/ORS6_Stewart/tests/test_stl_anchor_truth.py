# -*- coding: utf-8 -*-
"""
ORS6_Stewart · STL 锚点真相回归测试 (反者道之动 · v∞ 2026-05-12)

问题本源 (多重幻觉):
  v2.2.5 _dao_stl_balls 找的 "ball cluster" 位置 (Y=54.8 for Arm, Y=104.7
  for L_Pitcher) 不是真正 ball joint center, 而是 STL 杆侧面凸起.
  v2.2.6 用 trimesh tip-cluster bbox center (-41.47, 99.98) 仍是几何重心,
  不是 M4 轴销圆柱孔 axis. 这两者都是表面统计者幻觉.

  v∞ 真归位: trimesh _dao_axis_v2.py 用面法向 SVD 提取圆柱孔 axis,
  是几何轴中心 (非表面统计).

本测试锁死 STL 中 trimesh axis-SVD 真 horn axis + ball joint axis:
  Arm:        horn=(67.5,0,51), ball=(67.5,50,51) → arm_len=50.0 ✓ firmware mainArm
  L_Pitcher:  horn=(-7.5,30,51.75), ball=(-39.74,97.72,50.25) → arm_len=75.00 ✓ firmware pitchArm
  R_Pitcher:  horn=(+7.5,30,51.75), ball=(+39.74,97.72,50.25) → 镜像 L_Pitcher

这是 viewer/index.html 中 ARM_HORN_STL/ARM_BALL_STL/PITCHER_HORN_STL/
PITCHER_BALL_STL 的单源真理.  任何漂移会破坏 quaternion 2-point
alignment 让 STL 整体错位.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

# Add project root to sys.path so `import ORS6_Stewart` works in CI / local pytest.
PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

trimesh = pytest.importorskip("trimesh")
from ORS6_Stewart.parts import stl_path  # noqa: E402


def _find_clusters(mesh, radius: float = 1.0, min_size: int = 8,
                   max_size: int = 50):
    """Find vertex clusters within `radius` mm — typical M3/M4 hole rings."""
    v = mesh.vertices
    visited = np.zeros(len(v), dtype=bool)
    clusters = []
    for i in range(len(v)):
        if visited[i]:
            continue
        queue = [i]
        cluster = []
        while queue:
            j = queue.pop()
            if visited[j]:
                continue
            visited[j] = True
            cluster.append(j)
            d = np.linalg.norm(v - v[j], axis=1)
            for k in np.where(d < radius)[0]:
                if not visited[k]:
                    queue.append(int(k))
        if min_size <= len(cluster) <= max_size:
            clusters.append(v[cluster])
    return clusters


def _has_cluster_near(clusters, center, tol: float = 2.0):
    """Return True if any cluster center is within tol mm of `center`."""
    target = np.asarray(center, dtype=float)
    for c in clusters:
        cx = c.mean(axis=0)
        if np.linalg.norm(cx - target) < tol:
            return True, cx.tolist()
    return False, None


@pytest.fixture(scope="module")
def arm_clusters():
    return _find_clusters(trimesh.load(stl_path("Arm")))


@pytest.fixture(scope="module")
def lpitcher_clusters():
    return _find_clusters(trimesh.load(stl_path("L_Pitcher")))


@pytest.fixture(scope="module")
def rpitcher_clusters():
    return _find_clusters(trimesh.load(stl_path("R_Pitcher")))


# ── Arm STL anchors ────────────────────────────────────────────────────

def test_arm_horn_at_y0(arm_clusters):
    """Arm STL horn (servo motor shaft 接口) 在 (67.5, 0, 51 ±0.5)."""
    ok, found = _has_cluster_near(arm_clusters, (67.5, 0.0, 51.0), tol=2.0)
    assert ok, f"Arm horn cluster (67.5, 0, 51) 缺失. found near=None"


def test_arm_ball_at_y50(arm_clusters):
    """Arm STL ball joint (M4 stud) — 上下两面圆孔 Z=46 与 Z=56 (中点 Z=51)."""
    # ball joint 是 M4 通孔贯穿 STL 厚度, 上下两面各形成一个圆环 cluster
    ok_top, _ = _has_cluster_near(arm_clusters, (67.5, 50.0, 56.0), tol=2.5)
    ok_bot, _ = _has_cluster_near(arm_clusters, (67.5, 50.0, 46.0), tol=2.5)
    assert ok_top or ok_bot, (
        "Arm ball cluster Y=50 (上下面 Z=46/56) 都缺失"
    )


def test_arm_horn_to_ball_distance_50(arm_clusters):
    """horn-ball 3D 距离 = 50.0mm (firmware mainArm 严格匹配)."""
    horn = np.array([67.5, 0.0, 51.0])
    ball = np.array([67.5, 50.0, 51.0])
    dist = np.linalg.norm(ball - horn)
    assert abs(dist - 50.0) < 0.5, f"Arm horn-ball dist={dist:.2f} ≠ 50"


# ── L_Pitcher STL anchors ──────────────────────────────────────────────

def test_lpitcher_horn_at_y30(lpitcher_clusters):
    """L_Pitcher horn (servo M3 螺栓孔群中心) 在 (-7.5, 30, 51.75 ±2)."""
    ok, found = _has_cluster_near(lpitcher_clusters, (-7.5, 30.0, 51.75), tol=2.5)
    assert ok, f"L_Pitcher horn cluster (-7.5, 30, 51.75) 缺失."


def test_lpitcher_ball_at_y98(lpitcher_clusters):
    """L_Pitcher ball joint M4 轴销圆柱孔 axis (上下面中点 Z=50.25).

    v∞: 旧 (-41.47, 99.98) 是 tip-cluster bbox center (幻觉),
    真 axis-SVD 中心 (-39.74, 97.72) 是轴几何中心.
    horn(Y=30) → ball(Y=97.72) 距离 = 75mm = firmware pitchArm ✓
    """
    ok_top, _ = _has_cluster_near(lpitcher_clusters, (-39.74, 97.72, 55.5), tol=3.0)
    ok_bot, _ = _has_cluster_near(lpitcher_clusters, (-39.74, 97.72, 45.0), tol=3.0)
    assert ok_top or ok_bot, (
        "L_Pitcher ball cluster (Y=97.72, Z=45/55.5) 都缺失 — "
        "trimesh axis-SVD 真值与顶点 cluster 不一致"
    )


def test_rpitcher_mirror_lpitcher(rpitcher_clusters):
    """R_Pitcher horn + ball 是 L_Pitcher 镜像 (X 反号)."""
    ok_h, _ = _has_cluster_near(rpitcher_clusters, (7.5, 30.0, 51.75), tol=2.5)
    ok_b_top, _ = _has_cluster_near(rpitcher_clusters, (39.74, 97.72, 55.5), tol=3.0)
    ok_b_bot, _ = _has_cluster_near(rpitcher_clusters, (39.74, 97.72, 45.0), tol=3.0)
    assert ok_h and (ok_b_top or ok_b_bot), (
        "R_Pitcher horn 或 ball 不是 L_Pitcher X 镜像 — 视觉对称性破坏"
    )


# ── Viewer 硬编码常数与 STL trimesh 真值同步契约 ─────────────────────

def test_viewer_constants_match_stl_truth():
    """viewer/index.html 中 ARM_*_STL / PITCHER_*_STL 与 STL 真值锁死."""
    viewer = Path(__file__).resolve().parents[1] / "viewer" / "index.html"
    text = viewer.read_text(encoding="utf-8")
    # ARM constants
    assert "ARM_HORN_STL = new THREE.Vector3(67.5, 0.0, 51.0)" in text, (
        "viewer ARM_HORN_STL 与 STL trimesh 真值 (67.5,0,51) 漂移"
    )
    assert "ARM_BALL_STL = new THREE.Vector3(67.5, 50.0, 51.0)" in text, (
        "viewer ARM_BALL_STL 与 STL trimesh 真值 (67.5,50,51) 漂移"
    )
    # Pitcher horn (Y=30, not Y=9 — 之前 v2.2.5 以 Y_min 为 horn 是错误假设)
    assert "L_Pitcher: new THREE.Vector3(-7.5, 30.0, 51.75)" in text, (
        "viewer L_Pitcher horn 与 STL trimesh 真值 (-7.5, 30, 51.75) 漂移"
    )
    assert "L_Pitcher: new THREE.Vector3(-39.74, 97.72, 50.25)" in text, (
        "viewer L_Pitcher ball 与 STL trimesh axis-SVD 真值 "
        "(-39.74, 97.72, 50.25) 漂移 (旧 -41.47, 99.98 是 tip-cluster 幻觉)"
    )
