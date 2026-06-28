# -*- coding: utf-8 -*-
"""Automated backend verification: the SR6 model must obey real physics + PDF spec.
These tests are the closed loop -- they replace manual visual inspection."""
import os, sys
HERE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import pytest
import validate as V
import mechanism as M

@pytest.mark.parametrize("check", V.CHECKS, ids=[c.__name__ for c in V.CHECKS])
def test_check(check):
    r=check()
    assert r["pass"], f"{r['name']} failed: {r}"

def test_home_rod_exact():
    c=M.closure()
    for k in M.LEGS:
        assert abs(c["rods"][k]-175.0) < 1e-9

def test_all_pass_report():
    assert V.run()["all_pass"] is True
