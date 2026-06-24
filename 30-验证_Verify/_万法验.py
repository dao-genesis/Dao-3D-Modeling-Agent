#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
_万法验.py — 萬法驗 · 懶加載煙霧測
═══════════════════════════════════════════════════════════════════════════════

    天下難事, 必作於易; 天下大事, 必作於細.  ——《道德經》六十三

驗 `萬法.道` 之十三妙門皆可觸達.

本測不求活體 (SW/FreeCAD GUI) 可連, 只驗:
    ① import 路徑正確 (五層 sys.path 就緒)
    ② 每一 facet 懶加載可 import 對應模組
    ③ 統一 Res 契約完整
    ④ summary()/意()/manifest_path() 返值正確形態

退出碼:
    0 — 全相 PASS (依賴缺失計 WARN 不影響)
    1 — 任一相 FAIL
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
ROOT = next(
    (p for p in HERE.parents if (p / "_paths.py").is_file() and
     (p / "万法.py").is_file()),
    HERE.parent,
)
sys.path.insert(0, str(ROOT))

try:
    import _paths as _P  # noqa: F401
except Exception:
    _P = None

try:
    from 万法 import 道, Res  # noqa: N813
except Exception as e:
    print(f"FATAL: 無法導入 万法.道: {e}")
    traceback.print_exc()
    sys.exit(2)


PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
_ICON = {PASS: "✓", WARN: "⚠", FAIL: "✗"}


class PhaseResult(dict):
    @classmethod
    def ok(cls, tag, msg, data=None):
        return cls(tag=tag, status=PASS, message=msg, data=data)

    @classmethod
    def warn(cls, tag, msg, data=None):
        return cls(tag=tag, status=WARN, message=msg, data=data)

    @classmethod
    def fail(cls, tag, msg, data=None):
        return cls(tag=tag, status=FAIL, message=msg, data=data)


def _try(tag: str, fn, *, heavy_dep_ok: bool = True) -> PhaseResult:
    t0 = time.time()
    try:
        out = fn()
        el = round(time.time() - t0, 3)
        if isinstance(out, PhaseResult):
            out["elapsed_s"] = el
            return out
        return PhaseResult(tag=tag, status=PASS, message="ok",
                           data=out, elapsed_s=el)
    except ImportError as e:
        el = round(time.time() - t0, 3)
        st = WARN if heavy_dep_ok else FAIL
        return PhaseResult(tag=tag, status=st,
                           message=f"import 缺失 ({e})", data=None,
                           elapsed_s=el)
    except Exception as e:
        el = round(time.time() - t0, 3)
        return PhaseResult(tag=tag, status=FAIL,
                           message=f"{type(e).__name__}: {e}",
                           data={"traceback": traceback.format_exc()[-400:]},
                           elapsed_s=el)


# ───────────────────────────────────────────────────────────────────────────
# P0 — 基礎
# ───────────────────────────────────────────────────────────────────────────
def p0_foundation() -> List[PhaseResult]:
    out = []

    def _p0_1():
        from 万法 import 道 as 道2
        if 道 is not 道2:
            raise RuntimeError("道 單例失效")
        return {"singleton": True, "repr": repr(道)}
    out.append(_try("P0.1/道單例", _p0_1, heavy_dep_ok=False))

    def _p0_2():
        r_ok = Res.succ(data=42)
        r_er = Res.fail("oops")
        assert r_ok.ok is True and r_ok.data == 42 and r_ok.error is None
        assert r_er.ok is False and r_er.error == "oops"
        return {"ok_keys": sorted(r_ok.keys()), "fail_keys": sorted(r_er.keys())}
    out.append(_try("P0.2/Res契約", _p0_2, heavy_dep_ok=False))

    def _p0_3():
        s = 道.summary()
        for k in ("root", "version", "layers", "loaded_caps",
                  "uptime_s", "sw_alive", "fc_gui_alive"):
            if k not in s:
                raise RuntimeError(f"summary 缺 {k}")
        return {"keys": sorted(s.keys()), "layers_n": len(s["layers"])}
    out.append(_try("P0.3/summary", _p0_3, heavy_dep_ok=False))

    def _p0_4():
        mf = 道.manifest_path()
        return {"path": str(mf), "exists": mf.exists()}
    out.append(_try("P0.4/manifest", _p0_4, heavy_dep_ok=False))

    def _p0_5():
        from 万法 import LAYERS
        needed = {"origin", "reverse", "forge", "verify"}
        missing = needed - set(LAYERS.keys())
        if missing:
            raise RuntimeError(f"五層缺: {missing}")
        return {"layers": sorted(LAYERS.keys())}
    out.append(_try("P0.5/五層", _p0_5, heavy_dep_ok=False))

    return out


# ───────────────────────────────────────────────────────────────────────────
# P1 — 零依賴六相
# ───────────────────────────────────────────────────────────────────────────
def p1_zero_dep() -> List[PhaseResult]:
    out = []

    def _p1_1():
        m = 道.网格._load()
        for n in ("read_mesh", "read_stl", "write_stl_binary"):
            if not hasattr(m, n):
                raise RuntimeError(f"dao_mesh 缺 {n}")
        return {"api": 3}
    out.append(_try("P1.1/網格", _p1_1, heavy_dep_ok=False))

    def _p1_2():
        m = 道.图纸._load()
        return {"module": m.__name__}
    out.append(_try("P1.2/圖紙", _p1_2, heavy_dep_ok=False))

    def _p1_3():
        m = 道.文档._load()
        return {"module": m.__name__}
    out.append(_try("P1.3/文檔", _p1_3, heavy_dep_ok=False))

    def _p1_4():
        v = 道.验.new("萬法驗·自驗")
        if not hasattr(v, "phase"):
            raise RuntimeError("Verifier 缺 phase")
        with v.phase("selftest") as ph:
            ph.ok("trivial", "ok")
        return {"ok": True}
    out.append(_try("P1.4/驗", _p1_4, heavy_dep_ok=False))

    def _p1_5():
        env = 道.循.snapshot_env(modules=("json", "pathlib"))
        if "json" not in env.modules_present:
            raise RuntimeError("Environment.snapshot 異常")
        return {"py": env.python}
    out.append(_try("P1.5/循", _p1_5, heavy_dep_ok=False))

    def _p1_6():
        mech = 道.运动.Mechanism("test")
        se3 = 道.运动.SE3()
        return {"mech": mech.name, "SE3": se3 is not None}
    out.append(_try("P1.6/運動", _p1_6, heavy_dep_ok=False))

    return out


# ───────────────────────────────────────────────────────────────────────────
# P2 — OCP 依賴
# ───────────────────────────────────────────────────────────────────────────
def p2_ocp() -> List[PhaseResult]:
    out = []

    def _p2_1():
        k = 道.核.instance()
        has_box = any(hasattr(k, n) for n in ("make_box", "box"))
        if not has_box:
            raise RuntimeError("DaoKernel 缺 box 原語")
        return {"cls": type(k).__name__}
    out.append(_try("P2.1/核", _p2_1))

    def _p2_2():
        import dao_audit
        for n in ("audit_topology", "audit_geometry", "full_audit"):
            if not hasattr(dao_audit, n):
                raise RuntimeError(f"dao_audit 缺 {n}")
        return {"layers": 8}
    out.append(_try("P2.2/審", _p2_2))

    return out


# ───────────────────────────────────────────────────────────────────────────
# P3 — FreeCAD
# ───────────────────────────────────────────────────────────────────────────
def p3_freecad() -> List[PhaseResult]:
    out = []

    def _p3_1():
        FC = 道.反._load_inner()
        for n in ("reverse", "patch", "replay", "adapt", "probe",
                  "index", "search"):
            if not hasattr(FC, n):
                raise RuntimeError(f"FCReverse 缺 {n}")
        return {"methods": 7}
    out.append(_try("P3.1/反·內", _p3_1))

    def _p3_2():
        FC = 道.秀._load()
        for n in ("alive", "ensure_gui", "status", "load",
                  "screenshot", "view", "live_show", "exec_py"):
            if not hasattr(FC, n):
                raise RuntimeError(f"FCShow 缺 {n}")
        return {"methods": 8, "alive": bool(FC.alive())}
    out.append(_try("P3.2/秀", _p3_2))

    return out


# ───────────────────────────────────────────────────────────────────────────
# P4 — SolidWorks
# ───────────────────────────────────────────────────────────────────────────
def p4_solidworks() -> List[PhaseResult]:
    out = []

    def _p4_1():
        import 道_直连_底层 as M  # noqa: N813
        import 道_直连_底层_facets  # noqa: F401
        for n in ("Dao", "DaoDispatch", "MemidTable",
                  "MATE", "ALIGN", "SEL", "SURF", "DOC"):
            if not hasattr(M, n):
                raise RuntimeError(f"道_直連_底層 缺 {n}")
        return {"facets": True}
    out.append(_try("P4.1/活體·模組", _p4_1))

    def _p4_2():
        from 道_直连_底层 import MemidTable
        mt = MemidTable()
        ok = mt.load()
        if not ok:
            return PhaseResult.warn("P4.2/tlb", "sldworks.tlb 未找到", None)
        st = mt.stats()
        if st.get("interfaces", 0) < 100:
            raise RuntimeError(f"tlb 接口過少: {st}")
        return PhaseResult.ok("P4.2/tlb", "tlb 載入", st)
    out.append(_try("P4.2/tlb", _p4_2))

    def _p4_3():
        alive = 道.活体.is_alive()
        if alive:
            return PhaseResult.ok("P4.3/活體", "SW 連接", {"alive": True})
        return PhaseResult.warn("P4.3/活體", "SW 未運行", {"alive": False})
    out.append(_try("P4.3/活體", _p4_3))

    return out


# ───────────────────────────────────────────────────────────────────────────
# P5 — 反·外 + 鍛 + 執
# ───────────────────────────────────────────────────────────────────────────
def p5_reverse_forge() -> List[PhaseResult]:
    out = []

    def _p5_1():
        import dao_reverse
        for c in ("DaoReverse", "IntentParser", "WorldSearch",
                  "ResultRanker", "Adapter"):
            if not hasattr(dao_reverse, c):
                raise RuntimeError(f"dao_reverse 缺 {c}")
        return {"classes": 5}
    out.append(_try("P5.1/反·外", _p5_1))

    def _p5_2():
        cls = 道.锻._load()
        return {"DaoForge": cls.__name__}
    out.append(_try("P5.2/鍛", _p5_2))

    def _p5_3():
        cls = 道.执._load()
        return {"DaoEngine": cls.__name__}
    out.append(_try("P5.3/執", _p5_3))

    return out


# ───────────────────────────────────────────────────────────────────────────
# P6 — 意·面 dispatcher
# ───────────────────────────────────────────────────────────────────────────
def p6_intent() -> List[PhaseResult]:
    out = []

    def _p6_1():
        # 'create' 模式不動網絡, 只驗 dispatcher 形態
        r = 道.意("smoke test · phone stand 70mm", mode="create")
        if not isinstance(r, dict) or "ok" not in r:
            raise RuntimeError(f"意() 返類型異常: {type(r)}")
        return {"route": r.get("route"), "ok": r.get("ok")}
    out.append(_try("P6.1/意·create", _p6_1))

    def _p6_2():
        # adapt 無 path 應返 fail · 驗 dispatcher 錯誤處理
        r = 道.意("need shape", mode="adapt")
        if r.get("ok") is True:
            raise RuntimeError("意(adapt, 無 path) 應返 ok=False")
        if "error" not in r or not r["error"]:
            raise RuntimeError("意(adapt, 無 path) 應返 error")
        return {"route": r.get("route"), "error": r.get("error")}
    out.append(_try("P6.2/意·adapt_err", _p6_2))

    return out


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("═══ 萬法驗 · 懶加載煙霧測 ═══")
    print("═══ 天下難事 必作於易 ═══\n")

    all_phases: List[Tuple[str, List[PhaseResult]]] = []
    sections = [
        ("P0 — 基礎", p0_foundation),
        ("P1 — 零依賴", p1_zero_dep),
        ("P2 — OCP", p2_ocp),
        ("P3 — FreeCAD", p3_freecad),
        ("P4 — SolidWorks", p4_solidworks),
        ("P5 — 反·外/鍛/執", p5_reverse_forge),
        ("P6 — 意", p6_intent),
    ]

    for title, fn in sections:
        print(f"\n─── {title} ───")
        results = fn()
        for r in results:
            icon = _ICON.get(r["status"], "?")
            el = r.get("elapsed_s", 0.0)
            print(f"  {icon} {r['tag']:28s}  {el:>5.2f}s  {r['message']}")
        all_phases.append((title, results))

    # 彙總
    n_pass = sum(1 for _, rs in all_phases for r in rs if r["status"] == PASS)
    n_warn = sum(1 for _, rs in all_phases for r in rs if r["status"] == WARN)
    n_fail = sum(1 for _, rs in all_phases for r in rs if r["status"] == FAIL)
    n_tot = n_pass + n_warn + n_fail

    print(f"\n{'═'*60}")
    print(f"  萬法驗彙總: PASS={n_pass}  WARN={n_warn}  FAIL={n_fail}  "
          f"TOTAL={n_tot}")
    print(f"{'═'*60}")

    # 產物輸出
    out_dir = ROOT / "00-本源_Origin" / "_产物输出"
    try:
        out_dir.mkdir(exist_ok=True, parents=True)
        report = {
            "version": "1.0.0",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "summary": {"pass": n_pass, "warn": n_warn, "fail": n_fail,
                        "total": n_tot},
            "道_summary": 道.summary(),
            "sections": [
                {"title": t, "results": [dict(r) for r in rs]}
                for t, rs in all_phases
            ],
        }
        rp = out_dir / "_万法验_report.json"
        rp.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                  default=str), encoding="utf-8")
        print(f"  → {rp.relative_to(ROOT)}")
    except Exception as e:
        print(f"  ⚠ 產物寫入失敗: {e}")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
