#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_dao_intent_e2e.py — 道·意图引擎 E2E 全链路实践

"实践到底, 操作一切, 使用到底, 完善一切, 闭环审视, 测验一切."

五阶段:
  Phase 0: 连接 + 诊断 (只读, 不改动)
  Phase 1: 几何感知探测 (扫描关键组件 B-Rep, 只读)
  Phase 2: 单点配合测试 (anchor frame_base + 1 个 coaxial)
  Phase 3: 全量意图引擎 (build_crusher_intents → engine.run)
  Phase 4: 产物 + 验证报告

每阶段独立, 前一阶段失败可跳过后续.
"""
from __future__ import annotations
import json, sys, time, traceback
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from 道_直连_底层 import Dao, _safe
import 道_直连_底层_facets  # noqa

OUT = Path(__file__).resolve().parent / "_产物输出"
OUT.mkdir(exist_ok=True)

report: Dict[str, Any] = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "phases": {}}


def phase(name: str, fn):
    """安全执行阶段 · 异常不崩."""
    print(f"\n{'━'*60}")
    print(f"  Phase: {name}")
    print(f"{'━'*60}")
    t0 = time.time()
    try:
        result = fn()
        elapsed = round(time.time() - t0, 2)
        result["elapsed_s"] = elapsed
        result["ok"] = result.get("ok", True)
        report["phases"][name] = result
        tag = "✓" if result["ok"] else "✗"
        print(f"\n  {tag} {name} · {elapsed}s")
        return result
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        tb = traceback.format_exc()
        report["phases"][name] = {"ok": False, "error": str(e),
                                   "traceback": tb, "elapsed_s": elapsed}
        print(f"\n  ✗ {name} · {e}")
        print(f"    {tb.splitlines()[-1]}")
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# Phase 0: 连接 + 诊断
# ═══════════════════════════════════════════════════════════════
def phase_0_connect():
    dao = Dao().connect()
    rev = _safe(lambda: str(dao.sw.RevisionNumber()), "?")
    title = _safe(lambda: str(dao.doc.GetTitle()), "?")
    doc_path = _safe(lambda: str(dao.doc.GetPathName()), "?")
    is_asm = dao.asm is not None
    print(f"  SW: {rev}")
    print(f"  Doc: {title}")
    print(f"  Path: {doc_path}")
    print(f"  Assembly: {is_asm}")

    if not is_asm:
        return {"ok": False, "error": "当前非装配体",
                "sw": rev, "doc": title}

    # 诊断
    cmap = dao.build_comp_map()
    mates = dao.mate.list_all()
    ec_dist = {}
    for m in mates:
        ec = m.get("error_status", -1)
        ec_dist[ec] = ec_dist.get(ec, 0) + 1
    bad = [m for m in mates if m.get("error_status") not in (0, None, -1)]

    comp_names = sorted(cmap.keys())
    fixed_n = sum(1 for n in comp_names if dao.comp.is_fixed(n))
    supp_n = sum(1 for n in comp_names if dao.comp.is_suppressed(n))

    print(f"  Components: {len(comp_names)} (fixed={fixed_n} supp={supp_n})")
    print(f"  Mates: {len(mates)} ec={ec_dist}")
    if bad:
        print(f"  Bad mates: {len(bad)}")
        for m in bad[:5]:
            print(f"    · {m['name']} ec={m['error_status']}")

    return {
        "ok": True, "sw": rev, "doc": title, "doc_path": doc_path,
        "comps": len(comp_names), "comp_names": comp_names,
        "fixed": fixed_n, "suppressed": supp_n,
        "mates_total": len(mates), "mates_ec": ec_dist,
        "mates_bad": len(bad),
    }


# ═══════════════════════════════════════════════════════════════
# Phase 1: 几何感知探测
# ═══════════════════════════════════════════════════════════════
def phase_1_perceive():
    from 道_意图_引擎 import Perceiver
    dao = Dao()
    per = Perceiver(dao)

    # 扫描关键组件
    targets = [
        "main_shaft-1", "casing_lower-1", "frame_base-1",
        "hammer_pin-1", "hammer-1", "rotor_disc-1",
        "driven_pulley-1", "motor_body-1",
    ]
    scans: Dict[str, Any] = {}
    for comp in targets:
        scan = per.scan(comp)
        ok = scan.get("ok", False)
        n_faces = scan.get("n", 0)
        cyls = [f for f in scan.get("faces", []) if f.get("type") == "cylinder"]
        planes = [f for f in scan.get("faces", []) if f.get("type") == "plane"]
        scans[comp] = {
            "ok": ok, "n_faces": n_faces,
            "cylinders": len(cyls), "planes": len(planes),
        }
        if ok:
            print(f"  {comp:25s} faces={n_faces:3d} "
                  f"cyl={len(cyls):2d} plane={len(planes):2d}")
            # 列前3个圆柱半径
            for c in cyls[:3]:
                r = c.get("radius_mm", "?")
                ax = c.get("axis", "?")
                print(f"    cyl r={r}mm axis={ax}")
        else:
            print(f"  {comp:25s} FAIL: {scan.get('error','?')}")

    ok_count = sum(1 for v in scans.values() if v["ok"])
    print(f"\n  扫描: {ok_count}/{len(targets)} 成功")

    return {"ok": ok_count > 0, "scanned": len(targets),
            "ok_count": ok_count, "details": scans}


# ═══════════════════════════════════════════════════════════════
# Phase 2: 单点配合测试
# ═══════════════════════════════════════════════════════════════
def phase_2_single_test():
    from 道_意图_引擎 import (
        DaoIntentEngine, MateIntent, GeoSpec, R, anchor, coaxial
    )
    dao = Dao()
    engine = DaoIntentEngine(dao)

    # 仅 anchor + 1 个 coaxial (main_shaft ↔ casing_lower)
    test_intents = [
        anchor("frame_base-1"),
        coaxial("main_shaft-1", "casing_lower-1", radius_mm=30, priority=20),
    ]

    print(f"  测试意图: {len(test_intents)} 条")

    # 先诊断
    diag = engine.diagnose()
    print(f"  诊断: mates={diag['mates_total']} "
          f"fixed={diag['comps_fixed']}")

    # 仅执行 (不循环)
    exe = engine.exe.execute_all(test_intents)
    print(f"  执行: ok={exe['ok']} fail={exe['fail']}")
    for r in exe["results"]:
        tag = "✓" if r.get("ok") else "✗"
        print(f"    {tag} {r['source']}↔{r.get('target','')} "
              f"→ {r.get('action', r.get('name', r.get('error', '?')))}")

    # rebuild
    rb = engine.rebuild()
    print(f"  Rebuild: ok={rb['ok']} ({rb['elapsed_s']}s)")

    # verify
    ver = engine.ver.verify_all(test_intents)
    print(f"  验证: ok={ver['ok_count']} fail={ver['fail_count']} "
          f"skip={ver['skip_count']}")

    return {
        "ok": exe["fail"] == 0 or exe["ok"] > 0,
        "execute": exe, "rebuild": rb, "verify": ver,
    }


# ═══════════════════════════════════════════════════════════════
# Phase 3: 全量意图引擎
# ═══════════════════════════════════════════════════════════════
def phase_3_full_engine():
    from 道_意图_引擎 import DaoIntentEngine, build_crusher_intents
    dao = Dao()
    engine = DaoIntentEngine(dao)
    intents = build_crusher_intents()
    print(f"  意图: {len(intents)} 条")

    result = engine.run(intents, max_cycles=3, clean_bad=True, verbose=True)

    print(f"\n  结果: ok={result['ok']} cycles={result['cycles']} "
          f"elapsed={result['elapsed_s']}s")

    # final diagnosis
    fin = result.get("final", {})
    print(f"  最终: mates={fin.get('mates_total')} "
          f"ec={fin.get('mates_ec_dist')} "
          f"fixed={fin.get('comps_fixed')}")

    return result


# ═══════════════════════════════════════════════════════════════
# Phase 4: 产物 + 验证报告
# ═══════════════════════════════════════════════════════════════
def phase_4_products():
    dao = Dao()

    # Save
    sv = dao.save()
    print(f"  Save: ok={sv.get('ok')} err={sv.get('errors')} "
          f"warn={sv.get('warnings')}")

    # 4 视图
    try:
        dao.doc.ClearSelection2(True)
    except Exception:
        pass
    views = []
    for key, vid in {"iso": 7, "front": 1, "top": 5, "right": 3}.items():
        try:
            dao.doc.ShowNamedView2("", vid)
            time.sleep(0.15)
            dao.doc.ViewZoomtofit2()
            time.sleep(0.3)
            bmp = OUT / f"intent_{key}.bmp"
            dao.doc.SaveBMP(str(bmp), 1600, 1000)
            views.append(str(bmp))
            print(f"  {key} → {bmp.name}")
        except Exception as e:
            print(f"  {key}: {e}")

    return {"ok": True, "save": sv, "views": views}


# ═══════════════════════════════════════════════════════════════
# 主流
# ═══════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    print("═══ 道·意图引擎 · E2E 全链路实践 ═══")
    print("═══ 实践到底 · 操作一切 · 闭环审视 ═══\n")

    # Phase 0
    r0 = phase("0_connect", phase_0_connect)
    if not r0.get("ok"):
        print("\n  !! Phase 0 失败 · 无法继续")
        _save_report(t0)
        return

    # Phase 1
    r1 = phase("1_perceive", phase_1_perceive)

    # Phase 2 (仅当 Phase 1 有至少部分成功时)
    if r1.get("ok"):
        r2 = phase("2_single_test", phase_2_single_test)
    else:
        print("\n  跳过 Phase 2 (几何感知失败)")
        r2 = {"ok": False, "skipped": True}
        report["phases"]["2_single_test"] = r2

    # Phase 3 (仅当 Phase 2 有成功时)
    if r2.get("ok"):
        r3 = phase("3_full_engine", phase_3_full_engine)
    else:
        print("\n  跳过 Phase 3 (单点测试失败)")
        r3 = {"ok": False, "skipped": True}
        report["phases"]["3_full_engine"] = r3

    # Phase 4 (产物, 始终尝试)
    r4 = phase("4_products", phase_4_products)

    _save_report(t0)


def _save_report(t0):
    elapsed = round(time.time() - t0, 2)
    report["total_elapsed_s"] = elapsed

    # 汇总
    phases = report["phases"]
    total = len(phases)
    ok_n = sum(1 for v in phases.values() if v.get("ok"))
    skip_n = sum(1 for v in phases.values() if v.get("skipped"))

    print(f"\n{'═'*60}")
    print(f"  ═══ E2E 汇总 ═══")
    print(f"  总: {total} 阶段 · 成功: {ok_n} · 跳过: {skip_n} · "
          f"耗时: {elapsed}s")
    for name, r in phases.items():
        tag = "✓" if r.get("ok") else ("⊘" if r.get("skipped") else "✗")
        el = r.get("elapsed_s", "?")
        print(f"    {tag} {name:20s} {el}s")
    print(f"{'═'*60}")

    report["summary"] = {
        "total": total, "ok": ok_n, "skip": skip_n,
        "elapsed_s": elapsed,
    }

    p = OUT / "intent_e2e_report.json"
    with p.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  → {p.name}")


if __name__ == "__main__":
    main()
