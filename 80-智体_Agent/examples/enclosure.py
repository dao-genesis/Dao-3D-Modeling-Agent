#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
examples/enclosure.py — 智体亲手造形 (电子设备外壳 / 开口薄壁盒)
═══════════════════════════════════════════════════════════════════════════════
道法自然 · 无为而无不为. 此非"为他人造工具", 而是【智体用自己的工具在底层 BREP 引擎上
亲手造一个真实可制造的零件】, 边造边 perceive→verify, 在真实使用中暴露并修复缺陷.

本例 (闭环 4) 暴露的缺口: 此前无"抽壳/薄壁挖空", 真实外壳须把实心块掏空成等壁厚的盒.
→ 补 solid.shell (OCC makeThickness 向内偏置, 指定顶面为开口), 作其回归:
    实心外形 → 圆角竖棱 → 顶面抽壳留 2.5mm 壁 → 内部 4 角螺柱 → 螺柱钻孔.

用法 (须可见 freecadcmd):
    python examples/enclosure.py [--out 输出目录] [--png]
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
L, W, H = 90.0, 64.0, 32.0     # 外形长 / 宽 / 高
WALL = 2.5                     # 壁厚
CORNER_R = 6.0                 # 竖棱圆角
BOSS_R, BOSS_H = 4.0, 26.0     # 内螺柱半径 / 高
PILOT_R = 1.6                  # 螺柱中心导孔半径
INSET = 11.0                   # 螺柱中心距侧壁内缘
# 螺柱中心 (落在内腔四角)
BOSS_XY = [(L / 2 - INSET, W / 2 - INSET), (L / 2 - INSET, -(W / 2 - INSET)),
           (-(L / 2 - INSET), W / 2 - INSET), (-(L / 2 - INSET), -(W / 2 - INSET))]


def build(out_dir: str, save_png: bool) -> int:
    s = new_session("enclosure", engine="freecad")

    def act(tool, **a):
        r = s.act(tool, a)
        tag = a.get("result") or a.get("name") or tool
        d = r.data or {}
        flag = "" if r.ok else "  [FAIL] " + str(r.error)
        print("  %-13s %-8s V=%s 水密=%s%s" %
              (tool.split(".")[-1], tag, d.get("volume"), d.get("watertight", d.get("closed")), flag))
        return r

    def cut(target, tool):
        act("solid.boolean", op="difference", a=target, b=tool, result=target, consume=True)

    print("· 实心外形")
    act("solid.box", x=L, y=W, z=H, center=[0, 0, H / 2], name="case")

    print("· 圆角 4 条竖棱 (定向选棱, 逐角)")
    for cx, cy in [(L / 2, W / 2), (L / 2, -W / 2), (-L / 2, W / 2), (-L / 2, -W / 2)]:
        act("solid.fillet", name="case", radius=CORNER_R, near=[cx, cy, H / 2], within=1.0)

    print("· 顶面抽壳 (open_dir=+Z, 留 %.1fmm 壁)" % WALL)
    act("solid.shell", name="case", thickness=WALL, open_dir=[0, 0, 1])

    print("· 内部 4 角螺柱 (∪ 到壳) + 中心导孔")
    for i, (bx, by) in enumerate(BOSS_XY):
        boss = "boss_%d" % i
        act("solid.cylinder", radius=BOSS_R, height=BOSS_H, center=[bx, by, WALL + BOSS_H / 2], name=boss)
        act("solid.boolean", op="union", a="case", b=boss, result="case", consume=True)
    for i, (bx, by) in enumerate(BOSS_XY):
        pilot = "pilot_%d" % i
        act("solid.cylinder", radius=PILOT_R, height=BOSS_H, center=[bx, by, WALL + BOSS_H / 2 + 2], name=pilot)
        cut("case", pilot)

    print("· 感知")
    r = s.act("solid.perceive", {"name": "case", "resolution": 288,
                                 "out_dir": out_dir, "save_png": save_png})
    if r.ok:
        print("  " + r.data["summary"].replace("\n", " "))

    print("· 验证设计意图")
    rep = s.verify([
        Check(kind="exists", obj="case"),
        Check(kind="watertight", obj="case"),
        Check(kind="extent", obj="case", axis=0, lo=L - 0.1, hi=L + 0.1, label="L≈90"),
        Check(kind="extent", obj="case", axis=1, lo=W - 0.1, hi=W + 0.1, label="W≈64"),
        Check(kind="extent", obj="case", axis=2, lo=H - 0.1, hi=H + 0.1, label="H≈32"),
        Check(kind="count", value=1, label="仅余 case"),
    ])
    print(rep.render())

    e = s.act("solid.export", {"name": "case", "path": os.path.join(out_dir, "enclosure.step")})
    print("· STEP: " + (str(e.data.get("path")) if e.ok else "FAIL " + str(e.error)))

    try:
        s.registry.freecad_kernel.close()
    except Exception:
        pass
    return 0 if rep.ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "enclosure_out"))
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    print("═══ 智体亲手造形: 电子设备外壳 (顶面抽壳 + 内螺柱, BREP 直连) ═══")
    return build(args.out, args.png)


if __name__ == "__main__":
    raise SystemExit(main())
