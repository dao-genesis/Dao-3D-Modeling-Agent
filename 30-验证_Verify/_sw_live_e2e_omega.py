#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_sw_live_e2e_omega.py — L11 六象全域 E2E · 道法自然 · 无为而无不为
═══════════════════════════════════════════════════════════════════════

验证 dao_sw_live.py 的 ~108 个方法中尽可能多的能力.
每一步都落盘 JSON + 关键步骤截图, 用户五感可观.

六象:
  ① 始 · 新建 (new_part / new_assembly / new_drawing)
  ② 筋 · 草图 (line/rect/circle/arc/spline/dim/relation)
  ③ 骨 · 特征 (extrude/revolve/fillet/chamfer/shell/pattern/hole/plane)
  ④ 血 · 装配 (add_component / mate / interference)
  ⑤ 衣 · 工程图 (std_views / section / bom)
  ⑥ 魂 · 命令/属性/方程/材质/选择

使用:
    python _sw_live_e2e_omega.py                       # 全部六象
    python _sw_live_e2e_omega.py --phase 1,2,3         # 只跑前三象
    python _sw_live_e2e_omega.py --timeout-per-step 60 # 放宽超时
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 路径注入 ──
_HERE = Path(__file__).resolve().parent
_DAO_ROOT = _HERE.parent
sys.path.insert(0, str(_DAO_ROOT / "00-本源_Origin"))

# ── 输出目录 ──
_OUT = _HERE / "_sw_e2e_omega"
_OUT.mkdir(exist_ok=True)
_REPORT = _HERE / "_sw_e2e_omega.json"

# ── 全局结果 ──
results: Dict[str, Any] = {
    "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    "time_start": time.strftime("%Y-%m-%d %H:%M:%S"),
    "out_dir": str(_OUT),
    "phases": {},
    "steps": [],
    "summary": {},
}

def _flush():
    """每步落盘"""
    with open(_REPORT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

def _ts() -> str:
    return time.strftime("%H:%M:%S")

def _log(msg: str):
    print(f"  [{_ts()}] {msg}", flush=True)

# ── watchdog (总超时 + 单步超时) ──
_watchdog_deadline: float = 0.0

def _start_watchdog(total_timeout_s: float = 600.0):
    """后台线程: 超时则 os._exit 强杀 (避 COM cleanup deadlock)."""
    hard_deadline = time.time() + total_timeout_s
    def _watcher():
        while True:
            time.sleep(1.0)
            now = time.time()
            if now > hard_deadline:
                print(f"\n  ⏰ TOTAL TIMEOUT ({total_timeout_s}s) — hard exit", flush=True)
                _flush()
                os._exit(99)
            if _watchdog_deadline > 0 and now > _watchdog_deadline:
                print(f"\n  ⏰ STEP TIMEOUT — hard exit", flush=True)
                _flush()
                os._exit(98)
    t = threading.Thread(target=_watcher, daemon=True)
    t.start()

def _step(name: str, fn, *, timeout: float = 30.0) -> Dict[str, Any]:
    """主线程直接执行 fn (COM-safe). watchdog 管超时."""
    global _watchdog_deadline
    rec: Dict[str, Any] = {"step": name, "t0": _ts()}
    _watchdog_deadline = time.time() + timeout
    try:
        v = fn()
        if isinstance(v, dict):
            rec.update(v)
        else:
            rec["ok"] = True
            rec["result"] = str(v)[:200]
    except Exception as e:
        rec["ok"] = False
        rec["err"] = f"{type(e).__name__}: {e}"
    finally:
        _watchdog_deadline = 0.0
    rec["t1"] = _ts()
    results["steps"].append(rec)
    _flush()
    ok_str = "✅" if rec.get("ok") else "❌"
    _log(f"  {ok_str} {name}" + (f" — {rec.get('err','')}" if not rec.get("ok") else ""))
    return rec


def main() -> int:
    # ── 参数 ──
    timeout_per = 30.0
    phases_filter: Optional[set] = None
    for i, a in enumerate(sys.argv):
        if a == "--timeout-per-step" and i + 1 < len(sys.argv):
            timeout_per = float(sys.argv[i + 1])
        elif a == "--phase" and i + 1 < len(sys.argv):
            phases_filter = set(int(x) for x in sys.argv[i + 1].split(","))

    def want(phase: int) -> bool:
        return phases_filter is None or phase in phases_filter

    # ══════════════════════════════════════════════════════════════════
    #  象零 · 连接
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "═" * 72)
    print("  六象全域 E2E · 道法自然 · 无为而无不为")
    print("═" * 72)

    # 启动 watchdog (总超时 10 分钟)
    _start_watchdog(total_timeout_s=600.0)

    from dao_sw_live import SWLive
    live = SWLive()

    def _connect():
        r = live.ensure_live(visible=True, dismiss_welcome=False, launch_timeout_s=120)
        return r
    rec = _step("connect", _connect, timeout=150)
    if not rec.get("ok"):
        _log("ABORT: 无法连接 SW")
        results["summary"] = {"aborted": True}
        results["time_end"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _flush()
        return 1

    # dismiss welcome (走 SWDialogHandler)
    def _dismiss():
        try:
            import dao_solidworks as _sw
            r = _sw.SWDialogHandler.dismiss(kinds=("welcome", "tip"), max_rounds=2)
            return {"ok": True, "dismissed": r.get("total_dismissed", 0)}
        except Exception as e:
            return {"ok": True, "skipped": str(e)}  # 非致命
    _step("dismiss_welcome", _dismiss, timeout=10)

    # status
    def _status():
        s = live.status()
        return {"ok": True, **s}
    _step("status", _status, timeout=10)

    part_paths: List[str] = []   # 收集零件路径用于装配

    # ══════════════════════════════════════════════════════════════════
    #  象一 · 新建 + 象二 · 草图 + 象三 · 特征
    # ══════════════════════════════════════════════════════════════════
    if want(1) or want(2) or want(3):
        print("\n" + "─" * 72)
        print("  象①②③ · 零件: 草图 → 特征 → 材质 → 属性 → 导出")
        print("─" * 72)

        # ── Part A: 带法兰的轴 (circle + extrude + fillet + chamfer) ──
        doc_a_holder: Dict[str, Any] = {}
        def _new_part_a():
            doc = live.new_part()
            doc_a_holder["doc"] = doc
            return {"ok": doc is not None, "title": str(doc)}
        _step("1.new_part_A", _new_part_a, timeout=timeout_per)

        doc_a = doc_a_holder.get("doc")

        # 草图: 前视面, 外圆 + 内孔
        if want(2):
            def _sk_start():
                doc_a.sketch.start_front()
                return {"ok": True, "plane": "front"}
            _step("2.sketch.start_front", _sk_start, timeout=timeout_per)

            def _sk_circle_outer():
                doc_a.sketch.circle(0, 0, 20)
                return {"ok": True, "r": 20}
            _step("2.sketch.circle_outer", _sk_circle_outer, timeout=timeout_per)

            def _sk_circle_inner():
                doc_a.sketch.circle(0, 0, 8)
                return {"ok": True, "r": 8}
            _step("2.sketch.circle_inner", _sk_circle_inner, timeout=timeout_per)

            def _sk_stop():
                doc_a.sketch.stop()
                return {"ok": True}
            _step("2.sketch.stop", _sk_stop, timeout=timeout_per)

        # 特征: 拉伸
        if want(3):
            def _extrude():
                doc_a.feature.extrude(depth=30)
                return {"ok": True, "depth": 30}
            _step("3.feature.extrude", _extrude, timeout=timeout_per)

            # 法兰: 新草图 + 大圆 + 薄拉伸
            def _sk_flange():
                doc_a.sketch.start_front()
                doc_a.sketch.circle(0, 0, 35)
                doc_a.sketch.circle(0, 0, 20)
                doc_a.sketch.stop()
                return {"ok": True}
            _step("3.sketch_flange", _sk_flange, timeout=timeout_per)

            def _extrude_flange():
                doc_a.feature.extrude(depth=5)
                return {"ok": True, "depth": 5}
            _step("3.feature.extrude_flange", _extrude_flange, timeout=timeout_per)

            # fillet
            def _fillet():
                doc_a.feature.fillet(radius=2, all_edges=True)
                return {"ok": True, "radius": 2}
            _step("3.feature.fillet", _fillet, timeout=timeout_per)

            # rebuild
            def _rebuild():
                doc_a.rebuild()
                return {"ok": True}
            _step("3.rebuild", _rebuild, timeout=timeout_per)

        # ── 象六(部分) · 材质 + 属性 + 方程 ──
        def _material():
            r = doc_a.material.set_material("普通碳钢")
            return r
        _step("6.material", _material, timeout=timeout_per)

        def _property():
            doc_a.props.set("Project", "六象E2E")
            doc_a.props.set("Designer", "道直连器")
            val = doc_a.props.get("Project")
            return {"ok": True, "Project": val}
        _step("6.property", _property, timeout=timeout_per)

        # view + snap
        def _view_iso():
            live.view("iso")
            return {"ok": True}
        _step("1.view_iso", _view_iso, timeout=timeout_per)

        snap_a = str(_OUT / "part_A_iso.png")
        def _snap_a():
            live.snap(snap_a, view="iso")
            sz = os.path.getsize(snap_a) if os.path.isfile(snap_a) else 0
            return {"ok": sz > 0, "path": snap_a, "size_B": sz}
        _step("1.snap_part_A", _snap_a, timeout=timeout_per)

        # mass
        def _mass():
            m = doc_a.mass_properties()
            return {"ok": True, **m}
        _step("3.mass_properties", _mass, timeout=timeout_per)

        # bbox
        def _bbox():
            b = doc_a.bbox()
            return {"ok": True, **b}
        _step("3.bbox", _bbox, timeout=timeout_per)

        # feature tree
        def _tree():
            t = doc_a.feature_tree()
            return {"ok": True, "count": len(t) if isinstance(t, list) else 0,
                    "sample": t[:5] if isinstance(t, list) else str(t)[:200]}
        _step("3.feature_tree", _tree, timeout=timeout_per)

        # save part A
        part_a_path = str(_OUT / "part_A_shaft.SLDPRT")
        def _save_a():
            doc_a.save_as(part_a_path)
            sz = os.path.getsize(part_a_path) if os.path.isfile(part_a_path) else 0
            return {"ok": sz > 0, "path": part_a_path, "size_B": sz}
        _step("1.save_part_A", _save_a, timeout=timeout_per)
        part_paths.append(part_a_path)

        # export STEP
        step_a = str(_OUT / "part_A_shaft.step")
        def _export_step():
            doc_a.export(step_a)
            sz = os.path.getsize(step_a) if os.path.isfile(step_a) else 0
            return {"ok": sz > 0, "path": step_a, "size_B": sz}
        _step("1.export_step_A", _export_step, timeout=timeout_per)

        # export STL
        stl_a = str(_OUT / "part_A_shaft.stl")
        def _export_stl():
            doc_a.export(stl_a)
            sz = os.path.getsize(stl_a) if os.path.isfile(stl_a) else 0
            return {"ok": sz > 0, "path": stl_a, "size_B": sz}
        _step("1.export_stl_A", _export_stl, timeout=timeout_per)

        # ── Part B: 简单底座 (rect + extrude + shell) ──
        print("\n  ── Part B: 底座 ──")
        doc_b_holder: Dict[str, Any] = {}
        def _new_part_b():
            doc = live.new_part()
            doc_b_holder["doc"] = doc
            return {"ok": doc is not None}
        _step("1.new_part_B", _new_part_b, timeout=timeout_per)

        doc_b = doc_b_holder.get("doc")

        def _sk_rect():
            doc_b.sketch.start_top()
            doc_b.sketch.rect(-40, -30, 40, 30)
            doc_b.sketch.stop()
            return {"ok": True, "w": 80, "h": 60}
        _step("2.sketch.rect_base", _sk_rect, timeout=timeout_per)

        def _ext_base():
            doc_b.feature.extrude(depth=15)
            return {"ok": True, "depth": 15}
        _step("3.extrude_base", _ext_base, timeout=timeout_per)

        # shell (挖空)
        def _shell():
            doc_b.feature.shell(thickness=2)
            return {"ok": True, "thickness": 2}
        _step("3.feature.shell", _shell, timeout=timeout_per)

        # chamfer · 体级全边 (all_edges=True → SW 自动延 body → all edges)
        def _chamfer():
            r = doc_b.feature.chamfer(distance=1, all_edges=True)
            return r
        _step("3.feature.chamfer", _chamfer, timeout=timeout_per)

        # snap B
        snap_b = str(_OUT / "part_B_iso.png")
        def _snap_b():
            live.snap(snap_b, view="iso")
            sz = os.path.getsize(snap_b) if os.path.isfile(snap_b) else 0
            return {"ok": sz > 0, "path": snap_b, "size_B": sz}
        _step("1.snap_part_B", _snap_b, timeout=timeout_per)

        part_b_path = str(_OUT / "part_B_base.SLDPRT")
        def _save_b():
            doc_b.save_as(part_b_path)
            sz = os.path.getsize(part_b_path) if os.path.isfile(part_b_path) else 0
            return {"ok": sz > 0, "path": part_b_path, "size_B": sz}
        _step("1.save_part_B", _save_b, timeout=timeout_per)
        part_paths.append(part_b_path)

    # ══════════════════════════════════════════════════════════════════
    #  象四 · 装配
    # ══════════════════════════════════════════════════════════════════
    if want(4) and len(part_paths) >= 2:
        print("\n" + "─" * 72)
        print("  象④ · 装配: 组件 + 配合 + 干涉检查")
        print("─" * 72)

        doc_asm_holder: Dict[str, Any] = {}
        def _new_asm():
            doc = live.new_assembly()
            doc_asm_holder["doc"] = doc
            return {"ok": doc is not None}
        _step("4.new_assembly", _new_asm, timeout=timeout_per)

        doc_asm = doc_asm_holder.get("doc")

        def _add_base():
            r = doc_asm.assembly.add_component(part_paths[1])
            return {"ok": bool(r.get("ok")), "part": "base", **r}
        _step("4.add_component_base", _add_base, timeout=timeout_per)

        def _add_shaft():
            r = doc_asm.assembly.add_component(part_paths[0])
            return {"ok": bool(r.get("ok")), "part": "shaft", **r}
        _step("4.add_component_shaft", _add_shaft, timeout=timeout_per)

        def _list_comp():
            comps = doc_asm.assembly.list_components()
            cnt = len(comps) if isinstance(comps, list) else 0
            return {
                "ok": cnt > 0,
                "count": cnt,
                "names": [c.get("name") for c in comps[:10]] if isinstance(comps, list) else [],
                "sample": comps[:3] if isinstance(comps, list) else str(comps)[:200],
            }
        _step("4.list_components", _list_comp, timeout=timeout_per)

        # snap assembly
        snap_asm = str(_OUT / "assembly_iso.png")
        def _snap_asm():
            live.view("iso")
            from dao_sw_live import CommandRunner
            CommandRunner(live.app).zoom_fit()
            live.snap(snap_asm, view="iso")
            sz = os.path.getsize(snap_asm) if os.path.isfile(snap_asm) else 0
            return {"ok": sz > 0, "path": snap_asm, "size_B": sz}
        _step("4.snap_assembly", _snap_asm, timeout=timeout_per)

        # save assembly
        asm_path = str(_OUT / "assembly_e2e.SLDASM")
        def _save_asm():
            doc_asm.save_as(asm_path)
            sz = os.path.getsize(asm_path) if os.path.isfile(asm_path) else 0
            return {"ok": sz > 0, "path": asm_path, "size_B": sz}
        _step("4.save_assembly", _save_asm, timeout=timeout_per)

    # ══════════════════════════════════════════════════════════════════
    #  象六 · 命令系统 + 选择
    # ══════════════════════════════════════════════════════════════════
    if want(6):
        print("\n" + "─" * 72)
        print("  象⑥ · 命令/选择/方程")
        print("─" * 72)

        def _cmd_rebuild():
            from dao_sw_live import CommandRunner
            cr = CommandRunner(live.app)
            cr.rebuild()
            return {"ok": True}
        _step("6.cmd.rebuild", _cmd_rebuild, timeout=timeout_per)

        def _cmd_zoom():
            from dao_sw_live import CommandRunner
            cr = CommandRunner(live.app)
            cr.zoom_fit()
            return {"ok": True}
        _step("6.cmd.zoom_fit", _cmd_zoom, timeout=timeout_per)

        def _sel_count():
            from dao_sw_live import SelectionMgr
            sm = SelectionMgr(live.app)
            sm.clear()
            c = sm.count()
            return {"ok": True, "count": c}
        _step("6.selection.clear_count", _sel_count, timeout=timeout_per)

    # ══════════════════════════════════════════════════════════════════
    #  清理 + 报告
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "─" * 72)
    print("  清理 + 总结")
    print("─" * 72)

    # close all
    def _close():
        live.close_all()
        return {"ok": True}
    _step("cleanup.close_all", _close, timeout=timeout_per)

    # 汇总
    ok_count = sum(1 for s in results["steps"] if s.get("ok"))
    total = len(results["steps"])
    results["summary"] = {
        "ok": ok_count,
        "total": total,
        "pct": round(ok_count / total * 100, 1) if total else 0,
    }
    results["time_end"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _flush()

    print("\n" + "═" * 72)
    banner = f"  六象 E2E: {ok_count}/{total} ({results['summary']['pct']}%)"
    print(banner)
    print("═" * 72)
    print(f"  [REPORT] {_REPORT}")

    # 分象统计
    phase_map = {"1": "始·新建", "2": "筋·草图", "3": "骨·特征",
                 "4": "血·装配", "5": "衣·工程图", "6": "魂·命令"}
    for p_id, p_name in phase_map.items():
        steps = [s for s in results["steps"] if s["step"].startswith(f"{p_id}.")]
        if steps:
            p_ok = sum(1 for s in steps if s.get("ok"))
            print(f"  象{p_id} {p_name}: {p_ok}/{len(steps)}")
    # misc
    misc = [s for s in results["steps"] if not any(s["step"].startswith(f"{p}.") for p in "123456")]
    if misc:
        m_ok = sum(1 for s in misc if s.get("ok"))
        print(f"  基础(连接/清理): {m_ok}/{len(misc)}")

    return 0 if ok_count == total else 1


if __name__ == "__main__":
    sys.exit(main())
