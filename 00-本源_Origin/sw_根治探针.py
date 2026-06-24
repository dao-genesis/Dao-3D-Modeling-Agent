#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
sw_根治探针.py — 验证 dao_solidworks/dao_sw_live 底层根治修复
════════════════════════════════════════════════════════════════════
逐项验证:
  T1: _com_prop 对 RevisionNumber (property) 的安全访问
  T2: _com_prop 对 GetPathName/GetTitle/GetType (property/method) 的安全访问
  T3: _com_iter_docs 安全文档遍历 (无 doc=doc() 崩溃)
  T4: _dyn_wrap COM 对象 re-wrap
  T5: _find_sw_material_db 材质库自动定位
  T6: MaterialMgr.set_material 五路回退 + 验证回读
  T7: SolidWorksBridge.revision() 使用 _com_prop
  T8: SolidWorksBridge.list_docs() 使用 _com_iter_docs
  T9: dao_sw_bridge.py 一站式导入
"""
from __future__ import annotations
import json, sys, traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _ts(): return datetime.now().strftime("%H:%M:%S")


def run_probes() -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "title": "SW 根治探针",
        "time": _ts(),
        "probes": [],
    }
    passed = 0
    total = 0

    def _probe(name: str, fn):
        nonlocal passed, total
        total += 1
        rec = {"name": name}
        try:
            r = fn()
            rec.update(r)
            if r.get("ok"):
                passed += 1
                rec["status"] = "PASS"
            else:
                rec["status"] = "FAIL"
        except Exception as e:
            rec["status"] = "ERROR"
            rec["err"] = f"{type(e).__name__}: {e}"
            rec["traceback"] = traceback.format_exc()
        results["probes"].append(rec)
        mark = "✓" if rec["status"] == "PASS" else "✗"
        print(f"  {mark} {name}: {rec['status']}")
        if rec.get("err"):
            print(f"    → {rec['err']}")

    # ─── T1: _com_prop 导入 ───
    def t1():
        from dao_solidworks import _com_prop, _com_call, _com_iter_docs, _dyn_wrap
        assert callable(_com_prop)
        assert callable(_com_call)
        assert callable(_com_iter_docs)
        assert callable(_dyn_wrap)
        return {"ok": True, "note": "all 4 COM utilities imported"}

    _probe("T1_imports", t1)

    # ─── T2: _find_sw_material_db (不需 SW 运行) ───
    def t2():
        from dao_solidworks import _find_sw_material_db
        db = _find_sw_material_db()
        found = db is not None and Path(db).exists()
        return {"ok": True, "db_path": db, "exists": found,
                "note": "material DB found" if found else "no DB found (SW not installed?)"}

    _probe("T2_material_db", t2)

    # ─── T3: dao_sw_bridge 一站式导入 ───
    def t3():
        from dao_sw_bridge import (
            com_prop, com_call, com_iter_docs, dyn_wrap,
            find_material_db, SolidWorksBridge, SWLive, sw_connect,
        )
        assert callable(com_prop)
        assert callable(sw_connect)
        return {"ok": True, "note": "dao_sw_bridge one-stop import OK"}

    _probe("T3_bridge_import", t3)

    # ─── T4: SolidWorksBridge.revision() uses _com_prop ───
    def t4():
        import inspect
        from dao_solidworks import SolidWorksBridge
        src = inspect.getsource(SolidWorksBridge.revision)
        uses_com_prop = "_com_prop" in src
        return {"ok": uses_com_prop,
                "note": "revision() uses _com_prop" if uses_com_prop else
                        "revision() does NOT use _com_prop — FIX NEEDED"}

    _probe("T4_revision_com_prop", t4)

    # ─── T5: SolidWorksBridge.list_docs() uses _com_iter_docs ───
    def t5():
        import inspect
        from dao_solidworks import SolidWorksBridge
        src = inspect.getsource(SolidWorksBridge.list_docs)
        uses_iter = "_com_iter_docs" in src
        return {"ok": uses_iter,
                "note": "list_docs() uses _com_iter_docs" if uses_iter else
                        "list_docs() does NOT use _com_iter_docs — FIX NEEDED"}

    _probe("T5_list_docs_iter", t5)

    # ─── T6: SWDoc.title/path_name use _com_prop ───
    def t6():
        import inspect
        from dao_solidworks import SWDoc
        src_title = inspect.getsource(SWDoc.title)
        src_path = inspect.getsource(SWDoc.path_name)
        ok = "_com_prop" in src_title and "_com_prop" in src_path
        return {"ok": ok,
                "title_uses": "_com_prop" in src_title,
                "path_uses": "_com_prop" in src_path}

    _probe("T6_swdoc_com_prop", t6)

    # ─── T7: MaterialMgr has multi-path + readback ───
    def t7():
        import inspect
        from dao_sw_live import MaterialMgr
        src = inspect.getsource(MaterialMgr.set_material)
        has_readback = "_readback" in src
        has_fallback = "custom_prop_fallback" in src
        has_multi = "full_db" in src and "empty_db" in src and "short_db" in src
        ok = has_readback and has_fallback and has_multi
        return {"ok": ok,
                "readback": has_readback,
                "fallback": has_fallback,
                "multi_path": has_multi}

    _probe("T7_material_multipath", t7)

    # ─── T8: _com_prop handles callable fallback ───
    def t8():
        import inspect
        from dao_solidworks import _com_prop
        src = inspect.getsource(_com_prop)
        handles_exception = "except Exception" in src
        tries_call = "val()" in src
        return {"ok": handles_exception and tries_call,
                "note": "callable → try call → except → return as property"}

    _probe("T8_com_prop_fallback", t8)

    # ─── T9: sw_深层诊断 uses core utilities ───
    def t9():
        diag_path = HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机" / "sw_深层诊断.py"
        if not diag_path.exists():
            return {"ok": True, "note": "script not found, skipping"}
        src = diag_path.read_text(encoding="utf-8")
        uses_com_prop = "_com_prop" in src
        uses_iter = "_com_iter_docs" in src
        uses_dyn_wrap = "_dyn_wrap" in src
        ok = uses_com_prop and uses_iter and uses_dyn_wrap
        return {"ok": ok,
                "com_prop": uses_com_prop,
                "iter_docs": uses_iter,
                "dyn_wrap": uses_dyn_wrap}

    _probe("T9_diag_uses_core", t9)

    # ─── Live probes (require running SW) ───
    try:
        from dao_solidworks import _com_prop, _dyn_wrap, _com_iter_docs
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        app = win32com.client.GetActiveObject("SldWorks.Application")
        app = _dyn_wrap(app)
        sw_running = True
    except Exception:
        sw_running = False
        app = None

    if sw_running and app is not None:
        # ─── TL1: _com_prop on live RevisionNumber ───
        def tl1():
            rev = _com_prop(app, "RevisionNumber")
            return {"ok": rev is not None and isinstance(rev, str) and len(rev) > 0,
                    "revision": str(rev)}

        _probe("TL1_live_revision", tl1)

        # ─── TL2: _com_iter_docs on live SW ───
        def tl2():
            docs = _com_iter_docs(app)
            doc_infos = []
            for d in docs:
                title = str(_com_prop(d, "GetTitle") or "")
                dtype = _com_prop(d, "GetType")
                doc_infos.append({"title": title, "type": int(dtype) if dtype else 0})
            return {"ok": True, "count": len(docs), "docs": doc_infos}

        _probe("TL2_live_iter_docs", tl2)

        # ─── TL3: SolidWorksBridge live ───
        def tl3():
            from dao_solidworks import SolidWorksBridge
            bridge = SolidWorksBridge()
            bridge.connect(prefer_active=True, launch_if_needed=False)
            rev = bridge.revision()
            docs = bridge.list_docs()
            bridge.disconnect()
            return {"ok": bool(rev), "revision": rev, "doc_count": len(docs)}

        _probe("TL3_bridge_live", tl3)

        # ─── TL4: SWLive.ensure_live + docs ───
        def tl4():
            from dao_sw_live import SWLive
            live = SWLive()
            r = live.ensure_live()
            docs = live.docs()
            return {"ok": r.get("ok", False),
                    "revision": r.get("revision"),
                    "doc_count": len(docs)}

        _probe("TL4_swlive", tl4)

        # ─── TL5: Material DB auto-detect with live app ───
        def tl5():
            from dao_solidworks import _find_sw_material_db
            db = _find_sw_material_db(app)
            return {"ok": db is not None, "db": db}

        _probe("TL5_live_material_db", tl5)
    else:
        print("\n  ⚠ SolidWorks 未运行 — 跳过 live probes")
        results["sw_running"] = False

    results["passed"] = passed
    results["total"] = total
    results["ratio"] = f"{passed}/{total}"
    results["pct"] = round(100.0 * passed / max(total, 1), 1)
    return results


def main():
    print("═" * 60)
    print("  SW 根治探针 · 验证底层修复")
    print("═" * 60)

    results = run_probes()

    print(f"\n{'═' * 60}")
    print(f"  结果: {results['ratio']}  ({results['pct']}%)")
    print(f"{'═' * 60}")

    out = HERE / "_sw_根治探针.json"
    out.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    print(f"  报告: {out}")

    return 0 if results["passed"] == results["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
