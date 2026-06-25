#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI gate for the SR6 physical-assembly closure (no STL access required)."""
import os, sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assembly"))
import verify_assembly as va


def test_link_lengths_exact():
    asm = va.load()
    for k, leg in asm["legs"].items():
        d = np.linalg.norm(np.array(leg["pivot"]) - np.array(leg["ball"]))
        assert abs(d - leg["target"]) < 1e-3, (k, d, leg["target"])


def test_design_targets():
    asm = va.load()
    for k, leg in asm["legs"].items():
        exp = 186.0 if k.endswith("_p") else 175.0
        assert abs(leg["target"] - exp) < 1e-9, (k, leg["target"])


def test_six_legs():
    asm = va.load()
    assert set(asm["legs"]) == {"R_up", "R_lo", "L_up", "L_lo", "R_p", "L_p"}


def test_receiver_pose_rigid():
    asm = va.load()
    assert va.is_rigid(asm["receiver_M"])


def test_arm_transforms_orthonormal():
    asm = va.load()
    for k, M in asm["arm_xforms"].items():
        assert va.is_rigid(M, allow_reflection=True), k


def test_verify_passes():
    assert va.verify(verbose=False) < 1e-3
