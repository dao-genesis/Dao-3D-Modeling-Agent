#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SR6 TRUE 3D closure — CI smoke test.

证明: 真·3D 并联机构 IK->FK 严格闭环, 全工作空间内连杆恒为 175mm。
这是旧模型(假闭环, 连杆长度自由漂移)的根治。
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import true_kinematics as tk  # noqa: E402


def test_home_assemblable():
    ha = tk.home_angles()
    assert ha is not None, "home pose must be assemblable"
    assert len(ha) == 6


def test_home_rods_are_175():
    """Home 位姿 6 根杆必须严格 175mm (刚性约束, 非漂移)。"""
    ha = tk.home_angles()
    pose = (0., 0., tk.HOME_H, 0., 0., 0.)
    for s, L in tk.rod_lengths(ha, pose).items():
        assert abs(L - tk.ROD) < 1e-6, f"{s} rod={L} != 175"


@pytest.mark.parametrize("pose", tk.default_workspace())
def test_closure_per_pose(pose):
    """每个可达位姿: pose -> IK -> FK -> pose' 残差 ~ 0, 且杆长恒 175。"""
    r = tk.closure_error(pose)
    if not r["reachable"]:
        pytest.skip("pose outside reachable workspace (arm+rod reach limit)")
    assert r["max_rod_err"] < 1e-6, f"rod length drifted: {r['max_rod_err']}"
    assert r["dt_mm"] < 1e-6, f"translation closure error {r['dt_mm']} mm"
    assert r["dr_deg"] < 1e-6, f"rotation closure error {r['dr_deg']} deg"


def test_workspace_closure_aggregate():
    """聚合: 工作空间内至少 10 个位姿可达, 最坏闭环误差 < 1e-6。"""
    worst_dt = worst_dr = worst_rod = 0.0
    n_ok = 0
    for pose in tk.default_workspace():
        r = tk.closure_error(pose)
        if not r["reachable"]:
            continue
        n_ok += 1
        worst_dt = max(worst_dt, r["dt_mm"])
        worst_dr = max(worst_dr, r["dr_deg"])
        worst_rod = max(worst_rod, r["max_rod_err"])
    assert n_ok >= 10, f"only {n_ok} reachable poses"
    assert worst_rod < 1e-6
    assert worst_dt < 1e-6
    assert worst_dr < 1e-6


def test_ik_returns_none_outside_workspace():
    """远超量程的位姿必须判不可达 (返回 None), 而非给出错误解。"""
    assert tk.ik_all((0., 0., 1000., 0., 0., 0.)) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
