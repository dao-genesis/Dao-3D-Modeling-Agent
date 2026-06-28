#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the committed SR6 assembly solution (no STL access required).

Re-derives the 6 link lengths from the stored ball/pivot world coordinates and
asserts they equal the design targets (175mm main / 186mm pitch), and checks the
receiver home pose is a proper rigid transform.  This is the CI gate for the
physical-assembly closure: the geometry that puts every real STL in place is
captured in ``assembly_transforms.json`` and is validated here deterministically.
"""
import os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
JSON = os.path.join(HERE, "assembly_transforms.json")

MAIN_TARGET, PITCH_TARGET = 175.0, 186.0
TOL = 1e-3


def load():
    return json.load(open(JSON, encoding="utf-8"))


def link_lengths(asm):
    out = {}
    for k, leg in asm["legs"].items():
        d = float(np.linalg.norm(np.array(leg["pivot"]) - np.array(leg["ball"])))
        out[k] = (d, leg["target"])
    return out


def is_rigid(M, allow_reflection=False):
    M = np.array(M)
    R = M[:3, :3]
    det_ok = (abs(abs(np.linalg.det(R)) - 1.0) < 1e-6 if allow_reflection
              else abs(np.linalg.det(R) - 1.0) < 1e-6)
    return (np.allclose(R @ R.T, np.eye(3), atol=1e-6)
            and det_ok and np.allclose(M[3], [0, 0, 0, 1]))


def verify(verbose=True):
    asm = load()
    ll = link_lengths(asm)
    worst = 0.0
    for k, (d, tgt) in sorted(ll.items()):
        err = abs(d - tgt)
        worst = max(worst, err)
        if verbose:
            print(f"  {k:5s} len={d:8.3f} mm  target={tgt:.0f}  err={d-tgt:+.4f}")
        assert err < TOL, f"link {k} length {d} != target {tgt}"
        exp = PITCH_TARGET if k.endswith("_p") else MAIN_TARGET
        assert abs(tgt - exp) < 1e-9, f"link {k} target {tgt} != design {exp}"

    assert is_rigid(asm["receiver_M"]), "receiver pose is not a rigid transform"
    for k, M in asm["arm_xforms"].items():
        # left arms place the shared symmetric arm STL by X-mirror (det -1)
        assert is_rigid(M, allow_reflection=True), f"arm {k} transform not orthonormal"

    if verbose:
        print(f"  receiver home pose: rigid OK   worst link error = {worst:.2e} mm")
        print("ASSEMBLY CLOSURE: PASS")
    return worst


if __name__ == "__main__":
    verify()
