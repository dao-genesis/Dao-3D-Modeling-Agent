#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
examples/transition_duct.py — 智体亲手造形 (方转圆过渡风管接头)
═══════════════════════════════════════════════════════════════════════════════
道法自然 · 无为而无不为. 此非"为他人造工具", 而是【智体用自己的工具在底层 BREP 引擎上
亲手造一个真实可制造的零件】, 边造边 perceive→verify, 在真实使用中暴露并修复缺陷.

本例 (闭环 5) 暴露的缺口: 此前无"放样 (loft)", 截面渐变的过渡件 (方口 → 圆口) 造不出.
→ 补 solid.loft (OCC makeLoft 顺次蒙皮成实体), 作其回归:
    外形放样 (方→圆) ∪ 底法兰 − 内腔放样 (掏成等壁) − 法兰螺栓孔.

用法 (须可见 freecadcmd):
    python examples/transition_duct.py [--out 输出目录] [--png]
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
SQ_OUT = 90.0          # 方端外口边长
RND_OUT_R = 28.0       # 圆端外口半径
Z_BASE, Z_TOP = 8.0, 78.0   # 过渡段底/顶高 (法兰面在 z=Z_BASE)
WALL = 6.0             # 名义壁厚
FL_SIZE, FL_T = 120.0, 8.0  # 底法兰边长 / 厚 (z 0..8)
BOLT_R, BOLT_OFS = 4.0, 50.0   # 法兰螺栓孔半径 / 中心距原点 (四角)
SEG = 64               # 圆口分段


def build(out_dir: str, save_png: bool) -> int:
    s = new_session("duct", engine="freecad")

    def act(tool, **a):
        r = s.act(tool, a)
        tag = a.get("result") or a.get("name") or tool
        d = r.data or {}
        flag = "" if r.ok else "  [FAIL] " + str(r.error)
        print("  %-13s %-8s V=%s 水密=%s%s" %
              (tool.split(".")[-1], tag, d.get("volume"), d.get("watertight", d.get("closed")), flag))
        return r

    print("· 外形放样 (方 %gx%g @ z%g → 圆 Ø%g @ z%g)" % (SQ_OUT, SQ_OUT, Z_BASE, 2 * RND_OUT_R, Z_TOP))
    act("solid.loft", name="outer", sections=[
        {"rect": [SQ_OUT, SQ_OUT], "z": Z_BASE},
        {"circle": RND_OUT_R, "z": Z_TOP, "segments": SEG}])

    print("· 底法兰 ∪ 外形")
    act("solid.box", x=FL_SIZE, y=FL_SIZE, z=FL_T, center=[0, 0, FL_T / 2], name="flange")
    act("solid.boolean", op="union", a="outer", b="flange", result="body", consume=True)

    print("· 内腔放样 (掏空成等壁, 贯穿法兰与顶口)")
    act("solid.loft", name="bore", sections=[
        {"rect": [SQ_OUT - 2 * WALL, SQ_OUT - 2 * WALL], "z": -2.0},
        {"circle": RND_OUT_R - WALL, "z": Z_TOP + 2.0, "segments": SEG}])
    act("solid.boolean", op="difference", a="body", b="bore", result="body", consume=True)

    print("· 法兰 4 角螺栓孔")
    for i, (sx, sy) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)]):
        hole = "bolt_%d" % i
        act("solid.cylinder", radius=BOLT_R, height=FL_T * 3,
            center=[sx * BOLT_OFS, sy * BOLT_OFS, FL_T / 2], name=hole)
        act("solid.boolean", op="difference", a="body", b=hole, result="body", consume=True)

    print("· 感知")
    r = s.act("solid.perceive", {"name": "body", "resolution": 288,
                                 "out_dir": out_dir, "save_png": save_png})
    if r.ok:
        print("  " + r.data["summary"].replace("\n", " "))

    print("· 验证设计意图")
    rep = s.verify([
        Check(kind="exists", obj="body"),
        Check(kind="watertight", obj="body"),
        Check(kind="extent", obj="body", axis=0, lo=FL_SIZE - 0.1, hi=FL_SIZE + 0.1, label="法兰边≈120"),
        Check(kind="extent", obj="body", axis=2, lo=Z_TOP - 0.1, hi=Z_TOP + 0.1, label="总高≈78"),
        Check(kind="count", value=1, label="仅余 body"),
    ])
    print(rep.render())

    e = s.act("solid.export", {"name": "body", "path": os.path.join(out_dir, "transition_duct.step")})
    print("· STEP: " + (str(e.data.get("path")) if e.ok else "FAIL " + str(e.error)))

    try:
        s.registry.freecad_kernel.close()
    except Exception:
        pass
    return 0 if rep.ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "transition_duct_out"))
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    print("═══ 智体亲手造形: 方转圆过渡风管接头 (放样 loft, BREP 直连) ═══")
    return build(args.out, args.png)


if __name__ == "__main__":
    raise SystemExit(main())
