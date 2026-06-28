#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI smoke tests for the universal 8-dimension assembly verifier."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import verifier as V


def _good():
    return V.sample_good_assembly()


def test_eight_dimensions_present():
    rep = V.audit(_good())
    dims = [r.dim for r in rep.results]
    assert dims == ["topology", "geometry", "manufacture", "assembly",
                    "stackup", "strength", "load_dist", "stiffness"]


def test_good_assembly_passes_all():
    rep = V.audit(_good())
    assert rep.ok is True
    assert rep.score == pytest.approx(1.0, abs=1e-9)
    assert all(r.status == "PASS" for r in rep.results)


def test_interference_is_caught():
    a = _good()
    # drop the beam straight down into the posts -> AABB penetration
    for i, p in enumerate(a.parts):
        if p.name == "beam":
            a.parts[i] = V.Part(p.name, (p.pos[0], p.pos[1], 60.0), p.size,
                                 p.volume_mm3, min_wall_mm=p.min_wall_mm)
    rep = V.audit(a)
    asm = next(r for r in rep.results if r.dim == "assembly")
    assert asm.status == "FAIL"
    assert rep.ok is False


def test_thin_wall_is_caught():
    a = _good()
    for i, p in enumerate(a.parts):
        if p.name == "beam":
            a.parts[i] = V.Part(p.name, p.pos, p.size, p.volume_mm3, min_wall_mm=0.3)
    rep = V.audit(a)
    man = next(r for r in rep.results if r.dim == "manufacture")
    assert man.status == "FAIL"


def test_overstress_is_caught():
    a = _good()
    a.load_paths = [V.LoadPath(lp.name, lp.members, force_n=lp.force_n,
                               area_mm2=0.5, length_mm=lp.length_mm)
                    for lp in a.load_paths]
    rep = V.audit(a)
    stg = next(r for r in rep.results if r.dim == "strength")
    assert stg.status == "FAIL"
