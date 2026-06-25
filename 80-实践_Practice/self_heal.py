#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""道 · 自愈闭环 (build -> audit -> diagnose -> heal -> re-audit).

无为而无不为 —— 不靠人工逐个改尺寸, 而是给一个**参数化装配** + **八维审核器**,
让闭环自己把违反的维度逐轮收敛到全过 (score -> 1.0)。这是 00-本源_Origin/dao_loop.py
自愈引擎的可冷启动提炼版, 直接驱动 verifier.py。

机理: 每个可失败维度登记一个**单调修复策略** (heal), 它朝"满足约束"方向微调参数;
loop 反复 audit, 对每个 FAIL/WARN 维度施加其 heal, 直到 ok 或到达 max_iter。
记录每轮 score 形成收敛轨迹 (CI 据此断言 严格单调上升且终值=1.0)。
"""
from __future__ import annotations
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verifier import (Assembly, AuditReport, LoadPath, Part, audit)


# ── 参数化装配 (一根受拉横梁挂在两立柱上) ──────────────────────────────────────
def build(params: Dict[str, float]) -> Assembly:
    wall = params["wall_mm"]
    area = params["beam_area_mm2"]
    sf = params["safety_factor"]
    beam_z = params["beam_z"]                 # 横梁中心高度 (调它消干涉)
    side = 12.0
    parts = [
        Part("base",  (0, 0, 0),       (120, 80, 10), 60000, min_wall_mm=3.0),
        Part("postL", (-40, 0, 35),    (side, side, 60), 8000, min_wall_mm=wall),
        Part("postR", (40, 0, 35),     (side, side, 60), 8000, min_wall_mm=wall),
        Part("beam",  (0, 0, beam_z),  (110, side, side), 14000, min_wall_mm=wall),
    ]
    paths = [
        LoadPath("left",  ["beam", "postL", "base"], force_n=500, area_mm2=area, length_mm=60),
        LoadPath("right", ["beam", "postR", "base"], force_n=500, area_mm2=area, length_mm=60),
    ]
    return Assembly(parts=parts, load_paths=paths, total_load_n=1000.0,
                    clearance_mm=0.2, min_wall_mm=1.0, safety_factor=sf,
                    max_deflection_mm=1.0)


# ── 修复策略: dim -> (params -> params') 单调朝可行域 ──────────────────────────
def _heal_manufacture(p):  # 壁太薄 -> 每轮加厚 50% (单调收敛, 非一步到位)
    p["wall_mm"] = p["wall_mm"] * 1.5; return p


def _heal_assembly(p):     # 横梁压住立柱 -> 抬高到贴面 (post top = 5+60=65, beam half=6)
    p["beam_z"] = 65.0 + 12.0 / 2.0; return p


def _heal_strength(p):     # 应力超许用 -> 加大截面积
    p["beam_area_mm2"] = p["beam_area_mm2"] * 1.6; return p


HEALERS: Dict[str, Callable[[dict], dict]] = {
    "manufacture": _heal_manufacture,
    "assembly": _heal_assembly,
    "strength": _heal_strength,
}


@dataclass
class HealTrace:
    scores: List[float] = field(default_factory=list)
    actions: List[List[str]] = field(default_factory=list)
    final_report: AuditReport = None
    converged: bool = False
    iters: int = 0


def self_heal(params: Dict[str, float], max_iter: int = 12, verbose: bool = False) -> HealTrace:
    """从(可能违规的)初始参数出发, 闭环自愈至 8 维全过。返回收敛轨迹。"""
    p = dict(params)
    tr = HealTrace()
    for it in range(1, max_iter + 1):
        rep = audit(build(p))
        tr.scores.append(rep.score)
        tr.final_report = rep
        tr.iters = it
        if verbose:
            print(f"  iter {it}: score={rep.score:.3f} ok={rep.ok} "
                  f"fails={[r.dim for r in rep.results if r.status != 'PASS']}")
        if rep.ok:
            tr.converged = True
            break
        acted = []
        for r in rep.results:
            if r.status != "PASS" and r.dim in HEALERS:
                p = HEALERS[r.dim](p)
                acted.append(r.dim)
        tr.actions.append(acted)
        if not acted:                        # 无策略可救 -> 停 (避免空转)
            break
    return tr


def broken_params() -> Dict[str, float]:
    """蓄意三重违规: 壁过薄 + 横梁压住立柱(干涉) + 截面过小(应力超限)。"""
    return {"wall_mm": 0.4, "beam_area_mm2": 3.0, "safety_factor": 2.0, "beam_z": 64.0}


if __name__ == "__main__":
    print("self-heal from deliberately broken assembly:")
    tr = self_heal(broken_params(), verbose=True)
    print(f"\nconverged={tr.converged} in {tr.iters} iters")
    print("score trajectory:", [round(s, 3) for s in tr.scores])
    print(tr.final_report.summary())
