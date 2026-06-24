#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
道_意图_引擎.py — 反者道之动 · 万法归一

"兵无常势, 水无常形, 能因敌变化而取胜者, 谓之神.
 圣人总而用之, 其数一也."

核心反转:
  旧路: 硬编码(x,y,z) → Transform2.set → 祈祷
  新路: 设计意图 → 几何感知 → 配合约束 → SW求解器 → 几何验证

结构:
  ① MateIntent      — 意图描述 (关系, 非坐标)
  ② Perceiver       — 几何感知 (从B-Rep读活体)
  ③ Executor        — 意图执行 (意图→面→Mate)
  ④ Verifier        — 几何验证 (验关系, 非验坐标)
  ⑤ DaoIntentEngine — 闭环引擎 (诊→感→配→建→验→环)
"""
from __future__ import annotations
import math, sys, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from 道_直连_底层 import Dao, DaoDispatch, MATE, ALIGN, _safe, _ole_of
import 道_直连_底层_facets  # noqa: F401  — 挂载 facets 到 Dao


# ════════════════════════════════════════════════════════════════
# ① 意图描述
# ════════════════════════════════════════════════════════════════
class R:
    COAXIAL     = "coaxial"
    COINCIDENT  = "coincident"
    DISTANCE    = "distance"
    TANGENT     = "tangent"
    PARALLEL    = "parallel"
    ANCHOR      = "anchor"
    LOCK        = "lock"

@dataclass
class GeoSpec:
    type: str = "any"
    radius_mm: Optional[float] = None
    axis: Optional[Tuple[float,float,float]] = None
    normal: Optional[Tuple[float,float,float]] = None
    through_mm: Optional[Tuple[float,float,float]] = None
    tol_mm: float = 2.0
    tol_axis: float = 0.1

@dataclass
class MateIntent:
    source: str
    target: str
    relation: str
    source_geo: Optional[GeoSpec] = None
    target_geo: Optional[GeoSpec] = None
    align: int = ALIGN.CLOSEST
    distance_mm: float = 0.0
    priority: int = 0

def coaxial(src, tgt, radius_mm=None, axis=None, **kw):
    sg = GeoSpec(type="cylinder", radius_mm=radius_mm, axis=axis)
    tg = GeoSpec(type="cylinder", radius_mm=radius_mm, axis=axis)
    return MateIntent(src, tgt, R.COAXIAL, sg, tg, **kw)

def coincident(src, tgt, normal=None, align=ALIGN.ANTI, **kw):
    sg = GeoSpec(type="plane", normal=normal)
    tg = GeoSpec(type="plane", normal=normal)
    return MateIntent(src, tgt, R.COINCIDENT, sg, tg, align=align, **kw)

def distance(src, tgt, dist_mm, normal=None, **kw):
    sg = GeoSpec(type="plane", normal=normal)
    tg = GeoSpec(type="plane", normal=normal)
    return MateIntent(src, tgt, R.DISTANCE, sg, tg, distance_mm=dist_mm, **kw)

def anchor(comp):
    return MateIntent(comp, "", R.ANCHOR)


# ════════════════════════════════════════════════════════════════
# ② 几何感知
# ════════════════════════════════════════════════════════════════
class Perceiver:
    def __init__(self, dao: Dao):
        self.dao = dao
        self._cache: Dict[str, Dict] = {}

    def invalidate(self):
        self._cache.clear()

    def scan(self, comp_name: str) -> Dict[str, Any]:
        if comp_name in self._cache:
            return self._cache[comp_name]
        result = self.dao.face.scan(comp_name)
        self._cache[comp_name] = result
        return result

    def find_face(self, comp_name: str, geo: GeoSpec):
        """严格按 geo.type 查面 · 找不到返 None · 不越界降格."""
        if geo is None:
            return None
        if geo.type == "cylinder":
            return self.dao.face.find_cylinder(
                comp_name, radius_mm=geo.radius_mm, axis=geo.axis,
                through_point_mm=geo.through_mm,
                tol_mm=geo.tol_mm, tol_axis=geo.tol_axis)
        elif geo.type == "plane":
            return self.dao.face.find_plane(
                comp_name, normal=geo.normal, tol_axis=geo.tol_axis)
        # type=="any" → 优先圆柱, 次平面, 末任意面
        f = self.dao.face.find_cylinder(
            comp_name, radius_mm=geo.radius_mm, axis=geo.axis,
            through_point_mm=geo.through_mm,
            tol_mm=geo.tol_mm, tol_axis=geo.tol_axis)
        if f is not None:
            return f
        f = self.dao.face.find_plane(comp_name)
        if f is not None:
            return f
        scan = self.scan(comp_name)
        faces = scan.get("faces", [])
        return faces[0]["face"] if faces else None

    def match_faces(self, intent: MateIntent):
        tg = intent.target_geo or intent.source_geo
        fa = self.find_face(intent.source, intent.source_geo)
        fb = self.find_face(intent.target, tg) if intent.target else None
        return fa, fb

    def cylinder_summary(self, comp_name: str) -> List[Dict]:
        scan = self.scan(comp_name)
        if not scan.get("ok"):
            return []
        return [f for f in scan.get("faces", []) if f.get("type") == "cylinder"]

    def origin_of(self, comp_name: str):
        return self.dao.transform.origin_mm(comp_name)


# ════════════════════════════════════════════════════════════════
# ③ 意图执行
# ════════════════════════════════════════════════════════════════
class Executor:
    # relation → SW mate type 映射 (值来自 MATE 常量 = swconst.h)
    _REL_MATE_TYPES = {
        R.COAXIAL: {MATE.CONCENTRIC},    # swMateCONCENTRIC=1
        R.COINCIDENT: {MATE.COINCIDENT},  # swMateCOINCIDENT=0
        R.DISTANCE: {MATE.DISTANCE},      # swMateDISTANCE=5
        R.TANGENT: {MATE.TANGENT},        # swMateTANGENT=4
        R.PARALLEL: {MATE.PARALLEL},      # swMatePARALLEL=3
    }

    def __init__(self, dao: Dao, per: Perceiver):
        self.dao = dao
        self.per = per
        self._mate_map: Optional[Dict[tuple, set]] = None  # {pair: {mate_types}}
        self._force_pairs: set = set()  # 验证失败的对 · 强制重新执行

    def invalidate_mate_cache(self):
        self._mate_map = None

    def force_rematch(self, pairs: set):
        """标记需要强制重新配合的组件对."""
        self._force_pairs = pairs

    def _get_mate_map(self) -> Dict[tuple, set]:
        """{ (comp_a, comp_b): {mate_type_int, ...} } · 用于类型感知去重."""
        if self._mate_map is not None:
            return self._mate_map
        mapping: Dict[tuple, set] = {}
        mates = self.dao.mate.list_all()
        for m in mates:
            ec = m.get("error_status", -1)
            if ec not in (0, None, -1):
                continue  # 跳过已报错的配合
            comps = m.get("components", [])
            mt = m.get("type", -1)
            if len(comps) >= 2:
                pair = tuple(sorted(comps[:2]))
                mapping.setdefault(pair, set()).add(mt)
        self._mate_map = mapping
        return mapping

    def execute_one(self, intent: MateIntent,
                    skip_if_constrained: bool = True) -> Dict[str, Any]:
        r: Dict[str, Any] = {
            "source": intent.source, "target": intent.target,
            "relation": intent.relation, "ok": False}
        if intent.relation == R.ANCHOR:
            r["ok"] = bool(self.dao.comp.fix(intent.source))
            r["action"] = "fix"
            return r
        if intent.relation == R.LOCK:
            r["ok"] = True; r["action"] = "noop"
            return r
        # 去重: 组件已被完全约束(fully constrained by mates) → 跳过
        if skip_if_constrained:
            cs = self.dao.comp.constrained_status(intent.source)
            # 0=free 1=fully 2=over 3=fixed · 仅 fully(1) 跳过
            if cs == 1:
                r["ok"] = True; r["action"] = "already_constrained"
                r["constrained_status"] = cs
                return r
        # 去重: 检查是否已存在等效配合 (类型感知)
        if intent.target:
            pair = tuple(sorted([intent.source, intent.target]))
            if pair not in self._force_pairs:
                mate_map = self._get_mate_map()
                existing_types = mate_map.get(pair, set())
                expected_types = self._REL_MATE_TYPES.get(intent.relation, set())
                if existing_types & expected_types:
                    r["ok"] = True; r["action"] = "mate_exists"
                    r["existing_types"] = list(existing_types)
                    return r
        fa, fb = self.per.match_faces(intent)
        if fa is None:
            r["error"] = f"source face not found: {intent.source}"
            return r
        if fb is None:
            r["error"] = f"target face not found: {intent.target}"
            return r
        was_fixed = self.dao.comp.is_fixed(intent.source)
        if was_fixed:
            self.dao.comp.unfix(intent.source)
        mr = self._add_mate(intent, fa, fb)
        r.update(mr)
        if not mr.get("ok") and was_fixed:
            self.dao.comp.fix(intent.source)
            r["restored_fix"] = True
        return r

    def _add_mate(self, intent, fa, fb):
        rel = intent.relation
        if rel == R.COAXIAL:
            return self.dao.mate.concentric(fa, fb, align=intent.align)
        elif rel == R.COINCIDENT:
            return self.dao.mate.coincident(fa, fb, align=intent.align)
        elif rel == R.DISTANCE:
            return self.dao.mate.distance(
                fa, fb, distance_mm=intent.distance_mm, align=intent.align)
        elif rel == R.TANGENT:
            return self.dao.mate.tangent(fa, fb, align=intent.align)
        return {"ok": False, "error": f"unknown relation: {rel}"}

    def execute_all(self, intents: List[MateIntent]) -> Dict[str, Any]:
        ordered = sorted(intents, key=lambda i: i.priority)
        results, ok_n, fail_n = [], 0, 0
        for intent in ordered:
            try:
                r = self.execute_one(intent)
            except Exception as e:
                r = {"source": intent.source, "target": intent.target,
                     "relation": intent.relation, "ok": False,
                     "error": f"exception: {e}"}
            results.append(r)
            if r.get("ok"): ok_n += 1
            else: fail_n += 1
        return {"total": len(intents), "ok": ok_n,
                "fail": fail_n, "results": results}


# ════════════════════════════════════════════════════════════════
# ④ 几何验证
# ════════════════════════════════════════════════════════════════
class Verifier:
    def __init__(self, dao: Dao, per: Perceiver):
        self.dao = dao
        self.per = per

    def verify_coaxial(self, comp_a, comp_b,
                       radius_mm=None, tol_mm=1.0):
        ca = self.per.cylinder_summary(comp_a)
        cb = self.per.cylinder_summary(comp_b)
        if not ca or not cb:
            return {"ok": None, "method": "no_cylinders_for_verify"}
        best_dot, best_dist = 0.0, float("inf")
        # 宽松匹配: radius 仅为 hint, 不作硬约束
        # 策略: 先全量匹配, 找最佳同轴对
        for a in ca:
            aa, oa = a.get("axis",(0,0,0)), a.get("origin_mm",(0,0,0))
            for b in cb:
                ab, ob = b.get("axis",(0,0,0)), b.get("origin_mm",(0,0,0))
                dot = abs(sum(aa[i]*ab[i] for i in range(3)))
                if dot > best_dot:
                    best_dot = dot
                    best_dist = _axis_dist(oa, aa, ob)
        return {"ok": best_dot > 0.99 and best_dist < tol_mm,
                "axis_dot": round(best_dot, 4),
                "axis_dist_mm": round(best_dist, 2)}

    def verify_coincident(self, comp_a, comp_b, tol_mm=0.5):
        """验 coincident · 策略: 查是否存在 ec=0 的重合配合."""
        # coincident 使面共面 · 组件原点可能仍远 · 不能用原点距判定
        # 正确路径: 查配合系统中是否有该对的 coincident mate 且无错
        mates = self.dao.mate.list_all()
        pair = tuple(sorted([comp_a, comp_b]))
        for m in mates:
            comps = m.get("components", [])
            if len(comps) >= 2 and tuple(sorted(comps[:2])) == pair:
                if m.get("type") == MATE.COINCIDENT:
                    ec = m.get("error_status", -1)
                    return {"ok": ec in (0, -1, None),
                            "method": "mate_ec_check",
                            "mate_name": m.get("name"),
                            "error_status": ec}
        return {"ok": None, "method": "no_coincident_mate_found"}

    def verify_distance(self, comp_a, comp_b, expect_mm, tol_mm=1.0):
        """验两组件原点距是否符合预期距离."""
        oa = self.per.origin_of(comp_a)
        ob = self.per.origin_of(comp_b)
        if oa is None or ob is None:
            return {"ok": None, "method": "no_origin_for_verify"}
        dist = math.sqrt(sum((oa[i]-ob[i])**2 for i in range(3)))
        return {"ok": abs(dist - expect_mm) < tol_mm,
                "actual_mm": round(dist, 2),
                "expect_mm": expect_mm}

    def verify_intent(self, intent: MateIntent):
        if intent.relation == R.ANCHOR:
            return {"ok": bool(self.dao.comp.is_fixed(intent.source))}
        if intent.relation == R.LOCK:
            return {"ok": True}
        if intent.relation == R.COAXIAL:
            r = intent.source_geo.radius_mm if intent.source_geo else None
            return self.verify_coaxial(intent.source, intent.target, r)
        if intent.relation == R.COINCIDENT:
            return self.verify_coincident(intent.source, intent.target)
        if intent.relation == R.DISTANCE:
            return self.verify_distance(
                intent.source, intent.target, intent.distance_mm)
        # tangent/parallel → 至少检查约束状态
        cs = self.dao.comp.constrained_status(intent.source)
        return {"ok": cs in (1, 2, 3) if cs is not None else None,
                "method": "constrained_status_fallback",
                "constrained_status": cs}

    def verify_all(self, intents):
        self.per.invalidate()
        results = []
        ok = fail = skip = 0
        for i in intents:
            r = self.verify_intent(i)
            r["source"] = i.source; r["target"] = i.target
            results.append(r)
            if r.get("ok") is True: ok += 1
            elif r.get("ok") is False: fail += 1
            else: skip += 1
        return {"ok_count": ok, "fail_count": fail,
                "skip_count": skip, "results": results}


def _axis_dist(p1, d1, p2):
    dx, dy, dz = p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2]
    cx = dy*d1[2] - dz*d1[1]
    cy = dz*d1[0] - dx*d1[2]
    cz = dx*d1[1] - dy*d1[0]
    a = math.sqrt(d1[0]**2 + d1[1]**2 + d1[2]**2)
    if a < 1e-12: return float("inf")
    return math.sqrt(cx*cx + cy*cy + cz*cz) / a


# ════════════════════════════════════════════════════════════════
# ⑤ 闭环引擎
# ════════════════════════════════════════════════════════════════
class DaoIntentEngine:
    def __init__(self, dao: Dao):
        self.dao = dao
        self.per = Perceiver(dao)
        self.exe = Executor(dao, self.per)
        self.ver = Verifier(dao, self.per)

    def diagnose(self):
        mates = self.dao.mate.list_all()
        ec_dist: Dict[int,int] = {}
        for m in mates:
            ec = m.get("error_status", -1)
            ec_dist[ec] = ec_dist.get(ec, 0) + 1
        cmap = self.dao.build_comp_map()
        return {
            "mates_total": len(mates),
            "mates_ec_dist": ec_dist,
            "mates_bad": [m for m in mates
                          if m.get("error_status") not in (0, None, -1)],
            "comps_total": len(cmap),
            "comps_fixed": sum(1 for n in cmap
                               if self.dao.comp.is_fixed(n)),
            "comps_suppressed": sum(1 for n in cmap
                                    if self.dao.comp.is_suppressed(n)),
        }

    def clean_bad_mates(self, diag):
        bad = [m["name"] for m in diag.get("mates_bad", [])
               if m.get("error_status") == 51]
        if not bad: return {"ok": True, "deleted": 0}
        return self.dao.mate.delete_many(bad)

    def rebuild(self):
        t0 = time.time()
        ok = self.dao.rebuild(force=True)
        return {"ok": ok, "elapsed_s": round(time.time() - t0, 2)}

    def run(self, intents: List[MateIntent],
            max_cycles=2, clean_bad=True, verbose=True):
        t0 = time.time()
        history = []
        satisfied: set = set()  # 已满足的意图索引 · 后续轮跳过
        for cycle in range(max_cycles):
            step: Dict[str, Any] = {"cycle": cycle}
            if verbose:
                print(f"\n{'═'*60}")
                print(f"  道·意图引擎 · 第 {cycle+1} 轮 / {max_cycles}")
                print(f"{'═'*60}")
            diag = self.diagnose()
            step["diagnose"] = diag
            if verbose:
                print(f"  ① 诊 · mates={diag['mates_total']} "
                      f"ec={diag['mates_ec_dist']} "
                      f"fixed={diag['comps_fixed']}")
            # 每轮清过约束 (round 2 可能产生 ec=51)
            if clean_bad:
                cr = self.clean_bad_mates(diag)
                step["clean"] = cr
                if verbose and cr.get("deleted", 0):
                    print(f"  清 · 删 {cr['deleted']} 过约束mate")
            self.per.invalidate()
            self.exe.invalidate_mate_cache()
            if verbose:
                print(f"  ② 感 · B-Rep+配合缓存刷新")
            # 仅执行未满足的意图
            pending = [i for idx, i in enumerate(intents)
                       if idx not in satisfied]
            if verbose and satisfied:
                print(f"  跳过 {len(satisfied)} 已满足意图")
            exe = self.exe.execute_all(pending)
            step["execute"] = exe
            if verbose:
                print(f"  ③ 配 · {exe['total']} 意图 · "
                      f"ok={exe['ok']} fail={exe['fail']}")
                for r in exe["results"]:
                    if not r.get("ok"):
                        print(f"     ✗ {r['source']}↔{r['target']}: "
                              f"{r.get('error','?')}")
            rb = self.rebuild()
            step["rebuild"] = rb
            if verbose:
                print(f"  ④ 建 · ok={rb['ok']} ({rb['elapsed_s']}s)")
            ver = self.ver.verify_all(intents)
            step["verify"] = ver
            if verbose:
                print(f"  ⑤ 验 · ok={ver['ok_count']} "
                      f"fail={ver['fail_count']} "
                      f"skip={ver['skip_count']}")
            # 更新已满足集合 + 收集验证失败对
            fail_pairs: set = set()
            for idx, vr in enumerate(ver.get("results", [])):
                if vr.get("ok") is True:
                    satisfied.add(idx)
                elif vr.get("ok") is False and idx < len(intents):
                    it = intents[idx]
                    if it.target:
                        fail_pairs.add(tuple(sorted([it.source, it.target])))
            # 将验证失败对传入下轮强制重新配合
            if fail_pairs:
                self.exe.force_rematch(fail_pairs)
                if verbose:
                    print(f"  ↻ 标记 {len(fail_pairs)} 对强制重配")
            # 收敛条件: 执行全ok + 无过约束mate + 验证无明确fail
            all_exe_ok = exe["fail"] == 0
            no_bad = len(diag.get("mates_bad", [])) == 0
            ver_no_hard_fail = ver["fail_count"] == 0
            step["converged"] = all_exe_ok and no_bad and ver_no_hard_fail
            step["satisfied"] = len(satisfied)
            step["verify_fail_pairs"] = len(fail_pairs)
            history.append(step)
            if step["converged"]:
                if verbose: print(f"\n  ✓ 收敛 · 第{cycle+1}轮")
                break
            elif verbose:
                print(f"  ... 未收敛 · 已满足{len(satisfied)} · "
                      f"验证失败{len(fail_pairs)}对 · 继续")
        return {
            "ok": history[-1]["converged"] if history else False,
            "cycles": len(history),
            "elapsed_s": round(time.time()-t0, 2),
            "final": self.diagnose(),
            "history": history,
        }


# ════════════════════════════════════════════════════════════════
# 锤式破碎机 · 设计意图 (替代全部硬编码坐标)
# ════════════════════════════════════════════════════════════════
def build_crusher_intents() -> List[MateIntent]:
    """零坐标 · 纯几何关系."""
    intents: List[MateIntent] = []
    # 锚
    intents.append(anchor("frame_base-1"))
    # 结构
    intents.append(coaxial("casing_lower-1","frame_base-1",priority=10))
    intents.append(coaxial("casing_upper-1","casing_lower-1",priority=10))
    intents.append(coaxial("motor_mount-1","frame_base-1",priority=10))
    # motor_body 是 box (0 圆柱面) · 用 coincident 贴合 motor_mount (Z法向面)
    intents.append(coincident("motor_body-1","motor_mount-1",
                              normal=(0,0,1), priority=10))
    # 主轴
    intents.append(coaxial("main_shaft-1","casing_lower-1",
                           radius_mm=30, priority=20))
    # 皮带轮
    intents.append(coaxial("driven_pulley-1","main_shaft-1",
                           radius_mm=30, priority=30))
    # drive_pulley 电机侧 · motor_body 无圆柱 · 改挂 main_shaft 同轴
    intents.append(coaxial("drive_pulley-1","main_shaft-1",
                           radius_mm=20, priority=30))
    # 转子盘
    for i in range(1, 5):
        intents.append(coaxial(f"rotor_disc-{i}","main_shaft-1",
                               radius_mm=30, priority=40))
    # 销轴
    for i in range(1, 5):
        intents.append(coaxial(f"hammer_pin-{i}",f"rotor_disc-{i}",
                               radius_mm=15, priority=50))
    # 锤头
    _pin = {1:1,5:1,9:1,13:1, 3:2,7:2,11:2,15:2,
            2:3,6:3,10:3,14:3, 4:4,8:4,12:4,16:4}
    for h, p in _pin.items():
        intents.append(coaxial(f"hammer-{h}",f"hammer_pin-{p}",
                               radius_mm=15, priority=60))
    # V带 (无B-Rep几何 · 保持当前位置)
    for i in range(1, 5):
        belt = f"v_belt_dao_240x190x600_004333-{i}"
        intents.append(MateIntent(belt, "", R.LOCK, priority=70))
    # 筛板
    intents.append(coaxial("screen_plate-1","casing_lower-1",priority=50))
    return intents


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════
def main():
    import json
    print("═══ 道·意图引擎 · 反者道之动 ═══\n")
    dao = Dao().connect()
    rev = _safe(lambda: str(dao.sw.RevisionNumber()), "?")
    title = _safe(lambda: str(dao.doc.GetTitle()), "?")
    print(f"  SW: {rev} · Doc: {title}\n")

    engine = DaoIntentEngine(dao)
    intents = build_crusher_intents()
    print(f"  意图: {len(intents)} 条\n")

    result = engine.run(intents, max_cycles=2)

    print(f"\n{'═'*60}")
    print(f"  结果: ok={result['ok']} "
          f"cycles={result['cycles']} "
          f"elapsed={result['elapsed_s']}s")
    print(f"{'═'*60}")

    # save
    from pathlib import Path
    out = Path(__file__).resolve().parent / "_产物输出"
    out.mkdir(exist_ok=True)
    p = out / "intent_result.json"
    with p.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  → {p.name}")

if __name__ == "__main__":
    main()
