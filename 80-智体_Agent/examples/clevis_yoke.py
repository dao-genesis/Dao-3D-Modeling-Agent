#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
examples/clevis_yoke.py — 智体亲手造形 (U 形叉头 / clevis yoke)
═══════════════════════════════════════════════════════════════════════════════
道法自然 · 无为而无不为. 此非"为他人造工具", 而是【智体用自己的工具在底层 BREP 引擎上
亲手造一个真实可制造的零件】, 边造边 perceive→verify, 在真实使用中暴露并修复缺陷.

本例 (闭环 8) 暴露的缺口: 此前无"镜像 (mirror)", 对称件须左右各造一遍 (易不一致/费力).
→ 补 solid.mirror (OCC shape.mirror 关于平面反射成新对象), 作其回归:
    只造【一侧耳板+轴销凸台】, 镜像出对侧, 与底座并集, 再沿销轴钻通孔. 天然左右对称.

用法 (须可见 freecadcmd):
    python examples/clevis_yoke.py [--out 输出目录] [--png]
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
BASE = (50.0, 40.0, 16.0)     # 底座 x/y/z
EAR_X = 20.0                  # 耳板中心 X (镜像得 ±EAR_X)
EAR_T = 10.0                  # 耳板厚 (X 向)
EAR_TOP = 58.0               # 耳板矩形段顶 Z
BOSS_R = 14.0                 # 轴销凸台半径
BOSS_Z = 54.0                # 销轴中心 Z
PIN_R = 7.0                  # 销孔半径
BOSS_TOP = BOSS_Z + BOSS_R    # 凸台最高点 (z)


def build(out_dir: str, save_png: bool) -> int:
    s = new_session("yoke", engine="freecad")

    def act(tool, **a):
        r = s.act(tool, a)
        tag = a.get("result") or a.get("name") or tool
        d = r.data or {}
        flag = "" if r.ok else "  [FAIL] " + str(r.error)
        print("  %-13s %-8s V=%s 水密=%s%s" %
              (tool.split(".")[-1], tag, d.get("volume"), d.get("watertight", d.get("closed")), flag))
        return r

    print("· 底座 + 一侧耳板矩形段")
    act("solid.box", x=BASE[0], y=BASE[1], z=BASE[2], center=[0, 0, BASE[2] / 2], name="base")
    act("solid.box", x=EAR_T, y=BASE[1], z=EAR_TOP - BASE[2],
        center=[EAR_X, 0, (EAR_TOP + BASE[2]) / 2], name="ear")

    print("· 耳顶轴销凸台 (圆柱绕 Y 转成 X 轴向) ∪ 耳板")
    act("solid.cylinder", radius=BOSS_R, height=EAR_T, center=[EAR_X, 0, BOSS_Z], name="boss")
    act("solid.rotate", name="boss", angle_deg=90, axis=[0, 1, 0], center=[EAR_X, 0, BOSS_Z])
    act("solid.boolean", op="union", a="ear", b="boss", result="ear", consume=True)

    print("· 镜像出对侧耳板 (关于 YZ 平面) ∪ 底座")
    act("solid.mirror", name="ear", normal=[1, 0, 0], base=[0, 0, 0], result="ear2")
    act("solid.boolean", op="union", a="base", b="ear", result="yoke", consume=True)
    act("solid.boolean", op="union", a="yoke", b="ear2", result="yoke", consume=True)

    print("· 沿销轴 (X) 钻通孔, 贯穿两耳")
    act("solid.cylinder", radius=PIN_R, height=2 * EAR_X + EAR_T + 10, center=[0, 0, BOSS_Z], name="pin")
    act("solid.rotate", name="pin", angle_deg=90, axis=[0, 1, 0], center=[0, 0, BOSS_Z])
    act("solid.boolean", op="difference", a="yoke", b="pin", result="yoke", consume=True)

    print("· 感知")
    r = s.act("solid.perceive", {"name": "yoke", "resolution": 288,
                                 "out_dir": out_dir, "save_png": save_png})
    if r.ok:
        print("  " + r.data["summary"].replace("\n", " "))

    print("· 验证设计意图")
    rep = s.verify([
        Check(kind="exists", obj="yoke"),
        Check(kind="watertight", obj="yoke"),
        Check(kind="count", value=1, label="单连通叉头"),
        Check(kind="extent", obj="yoke", axis=0, lo=BASE[0] - 0.5, hi=BASE[0] + 0.5, label="底座宽≈%.0f" % BASE[0]),
        Check(kind="extent", obj="yoke", axis=2, lo=BOSS_TOP - 0.6, hi=BOSS_TOP + 0.6, label="总高≈%.0f" % BOSS_TOP),
    ])
    print(rep.render())

    e = s.act("solid.export", {"name": "yoke", "path": os.path.join(out_dir, "clevis_yoke.step")})
    print("· STEP: " + (str(e.data.get("path")) if e.ok else "FAIL " + str(e.error)))

    try:
        s.registry.freecad_kernel.close()
    except Exception:
        pass
    return 0 if rep.ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "clevis_yoke_out"))
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    print("═══ 智体亲手造形: U 形叉头 (镜像 mirror, BREP 直连) ═══")
    return build(args.out, args.png)


if __name__ == "__main__":
    raise SystemExit(main())
