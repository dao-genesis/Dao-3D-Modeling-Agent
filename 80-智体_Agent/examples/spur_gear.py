#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
examples/spur_gear.py — 智体亲手造形 (正齿轮 / spur gear)
═══════════════════════════════════════════════════════════════════════════════
道法自然 · 无为而无不为. 此非"为他人造工具", 而是【智体用自己的工具在底层 BREP 引擎上
亲手造一个真实可制造的零件】, 边造边 perceive→verify, 在真实使用中暴露并修复缺陷.

本例 (闭环 9) 与前 8 轮不同: 不再新增图元, 而是【检验已积累的工具词汇是否已能组合出复杂件】.
正齿轮 = 齿根圆柱 ∪ (单齿 extrude → pattern_polar 环阵 Z 齿) − 中心镗孔 − 键槽.
若全链路水密单体、齿数/外径吻合, 即证 extrude+pattern_polar+boolean 的组合已成熟 (反者道之动:
以更难之件回检既有之得). 如暴露缺陷 (如多齿并集非流形), 则就地修.

用法 (须可见 freecadcmd):
    python examples/spur_gear.py [--out 输出目录] [--png]
退出码 0 = 设计意图全部验证通过.
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session
from cad_agent.session import Check

# ── 设计意图 (参数化, 单位 mm) ── 模数制 ────────────────────────────────
MODULE = 3.0
TEETH = 18
FACE = 12.0                       # 齿宽 (Z)
BORE_R = 8.0                      # 中心孔半径
RP = MODULE * TEETH / 2.0         # 分度圆半径 = 27
RA = RP + MODULE                  # 齿顶圆半径 = 30
RF = RP - 1.25 * MODULE           # 齿根圆半径 = 23.25
OD = 2 * RA                       # 齿顶外径 = 60
W_ROOT, W_TIP = 5.6, 2.6          # 齿根/齿顶弦宽 (梯形齿廓近似)


def build(out_dir: str, save_png: bool) -> int:
    s = new_session("gear", engine="freecad")

    def act(tool, **a):
        r = s.act(tool, a)
        tag = a.get("result") or a.get("name") or tool
        d = r.data or {}
        flag = "" if r.ok else "  [FAIL] " + str(r.error)
        print("  %-14s %-8s V=%s 水密=%s%s" %
              (tool.split(".")[-1], tag, d.get("volume"), d.get("watertight", d.get("closed")), flag))
        return r

    print("· 齿根圆柱体 (轮坯)")
    act("solid.cylinder", radius=RF, height=FACE, center=[0, 0, FACE / 2], name="gear")

    print("· 单齿 (梯形齿廓 extrude) → 极阵 %d 齿 ∪ 轮坯" % TEETH)
    tooth = [[RF - 1.0, -W_ROOT / 2], [RA, -W_TIP / 2], [RA, W_TIP / 2], [RF - 1.0, W_ROOT / 2]]
    act("solid.extrude", points=tooth, height=FACE, name="tooth")
    act("solid.pattern_polar", name="tooth", count=TEETH, angle=360, result="teeth", consume=True)
    act("solid.boolean", op="union", a="gear", b="teeth", result="gear", consume=True)

    print("· 中心镗孔 + 键槽")
    act("solid.cylinder", radius=BORE_R, height=FACE + 8, center=[0, 0, FACE / 2], name="bore")
    act("solid.boolean", op="difference", a="gear", b="bore", result="gear", consume=True)
    act("solid.box", x=3.6, y=BORE_R + 3.2, z=FACE + 8, center=[0, BORE_R, FACE / 2], name="key")
    act("solid.boolean", op="difference", a="gear", b="key", result="gear", consume=True)

    print("· 感知")
    r = s.act("solid.perceive", {"name": "gear", "resolution": 320,
                                 "out_dir": out_dir, "save_png": save_png})
    if r.ok:
        print("  " + r.data["summary"].replace("\n", " "))

    print("· 验证设计意图")
    rep = s.verify([
        Check(kind="exists", obj="gear"),
        Check(kind="watertight", obj="gear"),
        Check(kind="count", value=1, label="单连通齿轮 (多齿并集成流形)"),
        Check(kind="extent", obj="gear", axis=0, lo=OD - 0.6, hi=OD + 0.6, label="齿顶外径≈%.0f" % OD),
        Check(kind="extent", obj="gear", axis=2, lo=FACE - 0.4, hi=FACE + 0.4, label="齿宽≈%.0f" % FACE),
    ])
    print(rep.render())

    e = s.act("solid.export", {"name": "gear", "path": os.path.join(out_dir, "spur_gear.step")})
    print("· STEP: " + (str(e.data.get("path")) if e.ok else "FAIL " + str(e.error)))

    try:
        s.registry.freecad_kernel.close()
    except Exception:
        pass
    return 0 if rep.ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "spur_gear_out"))
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    print("═══ 智体亲手造形: 正齿轮 %d 齿 模数 %g (组合既有工具, BREP 直连) ═══" % (TEETH, MODULE))
    return build(args.out, args.png)


if __name__ == "__main__":
    raise SystemExit(main())
