#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""motion_clearance_sweep.py — 机构运动扫描间隙校核 · 万法归一 60 门

静态干涉只证明"装配好的那一帧"不碰；真实机构要证明的是**整个运动包络**全程
无意外碰撞。本例把一根摆杆 (paddle) 装进方形窗口的壳体, 让它绕中心转过整周,
每一步都复用 (已宽相加速的) asm.interference 做一次间隙校核, 得到运动包络的
碰撞谱, 并对几何闭式预测逐角度比对。

两面校验 (道法自然 · 以解为镜, 既证"不碰"也证"会碰"):
  Case A 间隙: 摆杆半长 L=18 < 窗半宽 S=20 -> 全 360° 任一角度均无碰撞
  Case B 干涉: 摆杆半长 L=24 (S < L < S*sqrt2) -> 杆尖在轴向附近戳出窗口撞壳体,
               在 45° 附近又缩回窗内; 实测碰撞谱必须与闭式
               L*max(|cosθ|,|sinθ|) > S 完全一致 (证明校核是活的, 非恒零)

运行:  python 60-实战_Projects/motion_clearance_sweep.py
"""
import math
import os
import sys
from pathlib import Path

_DAO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "_paths.py").is_file())
sys.path.insert(0, str(_DAO_ROOT))
import _paths  # noqa: E402,F401

from cad_agent import new_session  # noqa: E402

S = 20.0          # window half-width (wall at +/-S in x and y)
W = 3.0           # paddle half-width
HB, HP = 10.0, 6.0  # housing / paddle thickness
STEP = 15         # sweep increment (deg)
TOL = 1e-3


def build(s, L):
    # housing = 80x80 block with a 2S x 2S through-window centered on origin
    s.act("solid.box", {"name": "blk", "length": 80, "width": 80, "height": HB, "pos": [-40, -40, -HB / 2]})
    s.act("solid.box", {"name": "win", "length": 2 * S, "width": 2 * S, "height": HB + 2, "pos": [-S, -S, -HB / 2 - 1]})
    assert s.act("solid.cut", {"a": "blk", "b": "win", "out": "Housing"}).ok
    # paddle: a 2L x 2W bar centered at origin, lying along +x at theta=0
    assert s.act("solid.box", {"name": "Paddle", "length": 2 * L, "width": 2 * W,
                               "height": HP, "pos": [-L, -W, -HP / 2]}).ok
    s.act("asm.create", {"name": "Mech"})
    s.act("asm.add", {"assembly": "Mech", "body": "Housing", "name": "housing", "fixed": True})
    s.act("asm.add", {"assembly": "Mech", "body": "Paddle", "name": "paddle"})


def predict_clash(L, theta_deg):
    th = math.radians(theta_deg)
    return L * max(abs(math.cos(th)), abs(math.sin(th))) > S + TOL


def sweep(label, L):
    s = new_session("sweep_%s" % label)
    print("FreeCAD", s.registry.kernel.freecad_version)
    build(s, L)
    angle = 0
    mism = 0
    hits = []
    while angle < 360:
        d = s.act("asm.interference", {"assembly": "Mech"}).data
        got = d["clash_count"] > 0
        exp = predict_clash(L, angle)
        if got != exp:
            mism += 1
        if got:
            hits.append(angle)
        s.act("asm.rotate", {"name": "paddle", "axis": [0, 0, 1], "angle": STEP, "at": [0, 0, 0]})
        angle += STEP
    print("  [%s] L=%.0f S=%.0f  clash angles=%s" % (label, L, S, hits))
    print("        sweep steps=%d  closed-form mismatches=%d" % (360 // STEP, mism))
    if label == "A":
        out = str(_paths.ROOT / "output" / "fem_demo" / "motion_clearance.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        rr = s.act("view.render", {"assembly": "Mech", "view": "top", "path": out})
        if rr.ok:
            print("        render -> %s (%d bytes)" % (out, rr.data["bytes"]))
    s.registry.kernel.shutdown()
    return mism, hits


def main():
    mA, hitsA = sweep("A", 18.0)   # clearance case: never touches
    assert hitsA == [], ("clearance case should never clash", hitsA)
    assert mA == 0, mA

    mB, hitsB = sweep("B", 24.0)   # interference case: touches near axis-aligned
    assert hitsB, "interference case must clash at some angles"
    assert 45 not in hitsB and 135 not in hitsB, ("must clear near 45-deg diagonal", hitsB)
    assert 0 in hitsB and 90 in hitsB, ("must clash when paddle points at a flat wall", hitsB)
    assert mB == 0, ("closed-form clash spectrum mismatch", mB)

    print("MOTION CLEARANCE SWEEP OK  (A: %d clash-free steps; B: %d clash steps, all matching closed form)"
          % (360 // STEP, len(hitsB)))


if __name__ == "__main__":
    main()
