#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""道 · 八维装配审核器 (universal, dependency-light).

从根本底层逆向"人类如何审视一个三维装配是否成立", 提炼出 8 个正交维度。
完整内核版 (00-本源_Origin/dao_audit.py) 直连 OCCT 做 BRep 级拓扑/壁厚 ray-cast;
本模块是其**可冷启动、纯 numpy** 的等价提炼, 作用于解析装配描述 (AABB + 载荷路径),
可在任意干净环境 (pip install numpy) 上自证, 并供自愈闭环 (self_heal.py) 驱动。

八维 (与内核 Layer 0-7 对应):
  1 topology       拓扑完整   每个零件闭合(watertight)、连通
  2 geometry       几何健全   体积>0、包围盒有限、质心落在盒内
  3 manufacture    工程适用   最小壁厚/特征 >= 工艺下限
  4 assembly       装配验证   两两零件干涉量 <= 许用 (留间隙)
  5 stackup        尺寸链     公差累积 <= 配合许用间隙
  6 strength       单路径强度 每承载件 应力 = F/A <= 屈服/安全系数
  7 load_dist      载荷分布   载荷由 N 条路径分担, 无单路径过载
  8 stiffness      刚度挠度   轴向/悬臂变形 <= 许用

每维返回 (status, score in [0,1], detail)。status ∈ {PASS, WARN, FAIL}。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


@dataclass
class Part:
    name: str
    pos: Tuple[float, float, float]            # 世界位置 (mm)
    size: Tuple[float, float, float]           # 包围盒尺寸 (mm)
    volume_mm3: float                          # 实体体积 (< bbox 体积)
    min_wall_mm: float                         # 最小壁厚/特征
    watertight: bool = True
    material_yield_mpa: float = 250.0          # 屈服强度
    youngs_gpa: float = 200.0                  # 弹性模量

    def aabb(self):
        p = np.array(self.pos, float); s = np.array(self.size, float)
        return p - s / 2, p + s / 2

    def centroid(self):
        return np.array(self.pos, float)


@dataclass
class LoadPath:
    """一条承载路径: 经过若干零件, 截面积 area_mm2, 长度 length_mm。"""
    name: str
    members: List[str]
    force_n: float
    area_mm2: float
    length_mm: float


@dataclass
class Assembly:
    parts: List[Part]
    clearance_mm: float = 0.2                   # 许用装配间隙
    tol_per_part_mm: float = 0.05               # 单件公差
    stack_gap_mm: float = 0.5                   # 尺寸链总许用间隙
    load_paths: List[LoadPath] = field(default_factory=list)
    total_load_n: float = 0.0                   # 外载 (用于分布检查)
    safety_factor: float = 2.0
    min_wall_mm: float = 1.0                    # 工艺最小壁厚
    max_deflection_mm: float = 1.0

    def by_name(self, n) -> Optional[Part]:
        return next((p for p in self.parts if p.name == n), None)


@dataclass
class DimResult:
    dim: str
    status: str
    score: float
    detail: str


@dataclass
class AuditReport:
    results: List[DimResult]

    @property
    def ok(self) -> bool:
        return all(r.status != FAIL for r in self.results)

    @property
    def score(self) -> float:
        return float(np.mean([r.score for r in self.results])) if self.results else 0.0

    def failures(self) -> List[DimResult]:
        return [r for r in self.results if r.status == FAIL]

    def summary(self) -> str:
        head = f"AuditReport ok={self.ok} score={self.score:.3f}"
        lines = [f"  [{r.status}] {r.dim:<12} {r.score:.2f}  {r.detail}" for r in self.results]
        return head + "\n" + "\n".join(lines)


# ── 八维 ─────────────────────────────────────────────────────────────────────
def _topology(a: Assembly) -> DimResult:
    bad = [p.name for p in a.parts if not p.watertight]
    if bad:
        return DimResult("topology", FAIL, 0.0, f"non-watertight: {bad}")
    return DimResult("topology", PASS, 1.0, f"{len(a.parts)} parts watertight")


def _geometry(a: Assembly) -> DimResult:
    issues = []
    for p in a.parts:
        bbox_vol = float(np.prod(p.size))
        if p.volume_mm3 <= 0 or not np.isfinite(p.volume_mm3):
            issues.append(f"{p.name}:vol<=0")
        elif p.volume_mm3 > bbox_vol * 1.0001:
            issues.append(f"{p.name}:vol>bbox")
        lo, hi = p.aabb()
        if not (np.all(lo <= p.centroid()) and np.all(p.centroid() <= hi)):
            issues.append(f"{p.name}:centroid_outside")
    if issues:
        return DimResult("geometry", FAIL, 0.0, "; ".join(issues))
    return DimResult("geometry", PASS, 1.0, "volumes/centroids sane")


def _manufacture(a: Assembly) -> DimResult:
    thin = [(p.name, p.min_wall_mm) for p in a.parts if p.min_wall_mm < a.min_wall_mm]
    if thin:
        worst = min(t[1] for t in thin)
        score = max(0.0, worst / a.min_wall_mm)
        return DimResult("manufacture", FAIL, score, f"thin walls < {a.min_wall_mm}: {thin}")
    return DimResult("manufacture", PASS, 1.0, f"min wall >= {a.min_wall_mm}mm")


def _overlap(p: Part, q: Part) -> float:
    """AABB 贯穿深度 (mm), 标准分离轴判据。
    全部三轴 ov>0 才相交, 此时贯穿深度 = min(ov) (正); 任一轴 ov<=0 即分离,
    min(ov) 自然 <=0 (沿最分离轴的负间隙)。abut(贴面) 时 min(ov)==0。"""
    lo1, hi1 = p.aabb(); lo2, hi2 = q.aabb()
    ov = np.minimum(hi1, hi2) - np.maximum(lo1, lo2)
    return float(np.min(ov))


def _assembly(a: Assembly) -> DimResult:
    clashes = []
    for i in range(len(a.parts)):
        for j in range(i + 1, len(a.parts)):
            d = _overlap(a.parts[i], a.parts[j])
            if d > a.clearance_mm:
                clashes.append((a.parts[i].name, a.parts[j].name, round(d, 3)))
    if clashes:
        return DimResult("assembly", FAIL, 0.0, f"interference > {a.clearance_mm}mm: {clashes}")
    return DimResult("assembly", PASS, 1.0, "no interference")


def _stackup(a: Assembly) -> DimResult:
    longest = max((lp.members for lp in a.load_paths), key=len, default=[])
    n = len(longest) if longest else len(a.parts)
    rss = a.tol_per_part_mm * (n ** 0.5)        # 统计 (RSS) 公差累积
    worst = a.tol_per_part_mm * n               # 最坏算术累积
    if worst > a.stack_gap_mm:
        score = max(0.0, a.stack_gap_mm / worst)
        st = WARN if rss <= a.stack_gap_mm else FAIL
        return DimResult("stackup", st, score,
                         f"worst-case stack {worst:.3f} > gap {a.stack_gap_mm} (RSS {rss:.3f})")
    return DimResult("stackup", PASS, 1.0, f"stack worst {worst:.3f} <= gap {a.stack_gap_mm}")


def _strength(a: Assembly) -> DimResult:
    bad = []
    min_margin = 1e9
    for lp in a.load_paths:
        if lp.area_mm2 <= 0:
            bad.append(f"{lp.name}:area<=0"); continue
        stress = abs(lp.force_n) / lp.area_mm2                # MPa (N/mm^2)
        member_yield = min((a.by_name(m).material_yield_mpa
                            for m in lp.members if a.by_name(m)), default=250.0)
        allow = member_yield / a.safety_factor
        margin = allow / stress if stress > 0 else 1e9
        min_margin = min(min_margin, margin)
        if stress > allow:
            bad.append(f"{lp.name}:{stress:.1f}>{allow:.1f}MPa")
    if bad:
        return DimResult("strength", FAIL, max(0.0, min(1.0, min_margin)),
                         f"overstressed (SF={a.safety_factor}): {bad}")
    sc = 1.0 if min_margin >= 1 else max(0.0, min_margin)
    return DimResult("strength", PASS, sc, f"all paths within yield/SF (min margin {min_margin:.2f}x)")


def _load_dist(a: Assembly) -> DimResult:
    if not a.load_paths or a.total_load_n <= 0:
        return DimResult("load_dist", PASS, 1.0, "no external load specified")
    n = len(a.load_paths)
    fair = a.total_load_n / n
    carried = [lp.force_n for lp in a.load_paths]
    worst = max(carried)
    ratio = worst / fair if fair > 0 else 1e9
    if ratio > 1.5:
        return DimResult("load_dist", WARN, max(0.0, 1.5 / ratio),
                         f"uneven: one path carries {ratio:.2f}x fair share over {n} paths")
    return DimResult("load_dist", PASS, 1.0, f"load shared across {n} paths (peak {ratio:.2f}x fair)")


def _stiffness(a: Assembly) -> DimResult:
    worst_defl = 0.0; worst_name = None
    for lp in a.load_paths:
        E = min((a.by_name(m).youngs_gpa for m in lp.members if a.by_name(m)), default=200.0) * 1e3  # MPa
        if lp.area_mm2 <= 0:
            continue
        defl = abs(lp.force_n) * lp.length_mm / (lp.area_mm2 * E)      # 轴向 dL = FL/AE (mm)
        if defl > worst_defl:
            worst_defl, worst_name = defl, lp.name
    if worst_defl > a.max_deflection_mm:
        return DimResult("stiffness", FAIL, max(0.0, a.max_deflection_mm / worst_defl),
                         f"{worst_name} deflects {worst_defl:.3f} > {a.max_deflection_mm}mm")
    return DimResult("stiffness", PASS, 1.0, f"max deflection {worst_defl:.4f} <= {a.max_deflection_mm}mm")


DIMENSIONS = [_topology, _geometry, _manufacture, _assembly,
              _stackup, _strength, _load_dist, _stiffness]


def audit(a: Assembly) -> AuditReport:
    """对装配运行全部 8 维审核。"""
    return AuditReport([fn(a) for fn in DIMENSIONS])


# ── 自证样例 ─────────────────────────────────────────────────────────────────
def sample_good_assembly() -> Assembly:
    """一个 8 维全过的健全装配 (一根受拉杆挂在两个支座上, 双路径分担)。"""
    parts = [
        Part("base",   (0, 0, 0),   (120, 80, 10), volume_mm3=60000, min_wall_mm=3.0),
        Part("postL",  (-40, 0, 35), (12, 12, 60), volume_mm3=8000,  min_wall_mm=4.0),
        Part("postR",  (40, 0, 35),  (12, 12, 60), volume_mm3=8000,  min_wall_mm=4.0),
        Part("beam",   (0, 0, 71),   (110, 12, 12), volume_mm3=14000, min_wall_mm=4.0),
    ]
    paths = [
        LoadPath("left",  ["beam", "postL", "base"], force_n=500, area_mm2=144, length_mm=60),
        LoadPath("right", ["beam", "postR", "base"], force_n=500, area_mm2=144, length_mm=60),
    ]
    return Assembly(parts=parts, load_paths=paths, total_load_n=1000.0,
                    clearance_mm=0.2, min_wall_mm=1.0, max_deflection_mm=1.0)


if __name__ == "__main__":
    rep = audit(sample_good_assembly())
    print(rep.summary())
    print("\nOK:", rep.ok, " score:", round(rep.score, 3))
