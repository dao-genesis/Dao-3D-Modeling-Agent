#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
examples/siphon_trap.py — 智体亲手造形 (U 形存水弯管 / siphon trap)
═══════════════════════════════════════════════════════════════════════════════
道法自然 · 无为而无不为. 此非"为他人造工具", 而是【智体用自己的工具在底层 BREP 引擎上
亲手造一个真实可制造的零件】, 边造边 perceive→verify, 在真实使用中暴露并修复缺陷.

本例 (闭环 6) 暴露的缺口: 此前无"沿路径扫掠 (sweep)", 弯管/U 形管的中心线扫掠造不出.
→ 补 solid.sweep (OCC makePipeShell 沿【精确 直线+相切弧】路径扫圆截面成管), 作其回归:
    沿 U 形中心线扫外径 − 扫内径 (掏成等壁管) + 两端立口加承插环.
真实使用中暴露的子缺陷: 路径用 BSpline 插值点列时, 在直↔弧过渡处过冲自交 → 扫掠体退化
(体积锐减、网格爆裂成数十万碎片). 改为转折控制点 + bend_radius 切弧成精确路径, 根除.

用法 (须可见 freecadcmd):
    python examples/siphon_trap.py [--out 输出目录] [--png]
退出码 0 = 设计意图全部验证通过.
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session
from cad_agent.session import Check

# ── 设计意图 (参数化, 单位 mm) ────────────────────────────────────────
R_OUT, R_IN = 12.0, 9.0     # 管外/内半径 (壁厚 3)
BEND_R = 25.0               # U 弯半径 (中心线)
SPAN = 2 * BEND_R           # 两立管间距 = 50 (= 2·BEND_R → 底两弧相接成半圆)
TOP_Z = 80.0               # 立管顶 (外形)
RING_R, RING_H = 16.0, 8.0  # 承插环外半径 / 高


def _route(top_z: float):
    """U 形中心线转折控制点: 左立管顶 → 底拐角 → 底拐角 → 右立管顶 (XZ 平面, y=0).
    交 sweep 的 bend_radius=BEND_R 在两底拐角切弧 (此处恰相接成半圆)."""
    return [[0.0, 0.0, top_z], [0.0, 0.0, 0.0], [SPAN, 0.0, 0.0], [SPAN, 0.0, top_z]]


def build(out_dir: str, save_png: bool) -> int:
    s = new_session("trap", engine="freecad")

    def act(tool, **a):
        r = s.act(tool, a)
        tag = a.get("result") or a.get("name") or tool
        d = r.data or {}
        flag = "" if r.ok else "  [FAIL] " + str(r.error)
        print("  %-13s %-8s V=%s 水密=%s%s" %
              (tool.split(".")[-1], tag, d.get("volume"), d.get("watertight", d.get("closed")), flag))
        return r

    print("· 沿 U 形中心线扫外径 (sweep, bend_radius 切弧)")
    act("solid.sweep", name="outer", path=_route(TOP_Z), profile_radius=R_OUT, bend_radius=BEND_R)

    print("· 两端立口承插环 ∪ 外形")
    for i, x in enumerate([0.0, SPAN]):
        ring = "ring_%d" % i
        act("solid.cylinder", radius=RING_R, height=RING_H, center=[x, 0, TOP_Z + RING_H / 2 - 1], name=ring)
        act("solid.boolean", op="union", a="outer", b=ring, result="outer", consume=True)

    print("· 扫内径 (掏成等壁管, 两端延伸贯穿承插环)")
    act("solid.sweep", name="bore", path=_route(TOP_Z + RING_H + 2), profile_radius=R_IN, bend_radius=BEND_R)
    act("solid.boolean", op="difference", a="outer", b="bore", result="trap", consume=True)

    print("· 感知")
    r = s.act("solid.perceive", {"name": "trap", "resolution": 288,
                                 "out_dir": out_dir, "save_png": save_png})
    if r.ok:
        print("  " + r.data["summary"].replace("\n", " "))

    print("· 验证设计意图")
    rep = s.verify([
        Check(kind="exists", obj="trap"),
        Check(kind="watertight", obj="trap"),
        Check(kind="count", value=1, label="仅余 trap (单连通管体)"),
        Check(kind="extent", obj="trap", axis=0,
              lo=SPAN + 2 * R_OUT - 1, hi=SPAN + 2 * RING_R + 1, label="跨度含端环"),
    ])
    print(rep.render())

    e = s.act("solid.export", {"name": "trap", "path": os.path.join(out_dir, "siphon_trap.step")})
    print("· STEP: " + (str(e.data.get("path")) if e.ok else "FAIL " + str(e.error)))

    try:
        s.registry.freecad_kernel.close()
    except Exception:
        pass
    return 0 if rep.ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "siphon_trap_out"))
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    print("═══ 智体亲手造形: U 形存水弯管 (沿路径扫掠 sweep, BREP 直连) ═══")
    return build(args.out, args.png)


if __name__ == "__main__":
    raise SystemExit(main())
