#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORS6_Stewart · poses — 15 standard T-Code poses for motion verification.

Each pose is (name, L0, L1, L2, R0, R1, R2) in range [0, 9999] with 5000 = home.
Used by assembly.motion_sequence() and viewer preview system.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

Pose = Tuple[str, int, int, int, int, int, int]

MOTION_POSES: List[Pose] = [
    ("home",         5000, 5000, 5000, 5000, 5000, 5000),
    ("thrust_up",    9999, 5000, 5000, 5000, 5000, 5000),
    ("thrust_down",     0, 5000, 5000, 5000, 5000, 5000),
    ("forward",      5000, 9999, 5000, 5000, 5000, 5000),
    ("backward",     5000,    0, 5000, 5000, 5000, 5000),
    ("side_right",   5000, 5000, 9999, 5000, 5000, 5000),
    ("side_left",    5000, 5000,    0, 5000, 5000, 5000),
    ("roll_right",   5000, 5000, 5000, 5000, 9999, 5000),
    ("roll_left",    5000, 5000, 5000, 5000,    0, 5000),
    ("pitch_up",     5000, 5000, 5000, 5000, 5000, 9999),
    ("pitch_down",   5000, 5000, 5000, 5000, 5000,    0),
    ("twist_cw",     5000, 5000, 5000, 9999, 5000, 5000),
    ("twist_ccw",    5000, 5000, 5000,    0, 5000, 5000),
    ("combo_diag",   7000, 7000, 3000, 6000, 7000, 6000),
    ("extreme",      8000, 7500, 2500, 8000, 7500, 7000),
]


def pose_by_name(name: str) -> Optional[Tuple[int, int, int, int, int, int]]:
    """Look up pose tuple by name. Returns (L0,...,R2) or None."""
    for p in MOTION_POSES:
        if p[0] == name:
            return p[1:]
    return None
