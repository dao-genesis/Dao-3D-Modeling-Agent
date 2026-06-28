#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI smoke tests for the self-heal closed loop (build -> audit -> heal -> converge)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import self_heal as SH
import verifier as V


def test_broken_starts_failing():
    rep = V.audit(SH.build(SH.broken_params()))
    assert rep.ok is False


def test_self_heal_converges_to_full_pass():
    tr = SH.self_heal(SH.broken_params(), max_iter=12)
    assert tr.converged is True
    assert tr.final_report.ok is True
    assert tr.final_report.score == 1.0


def test_score_trajectory_monotonic():
    """每一轮 score 不下降, 终值=1.0 (收敛证据)。"""
    tr = SH.self_heal(SH.broken_params(), max_iter=12)
    s = tr.scores
    assert len(s) >= 2
    assert all(s[i + 1] >= s[i] - 1e-12 for i in range(len(s) - 1))
    assert s[-1] == 1.0
    assert s[0] < 1.0
