#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_sw_live_smoke.py — L11 真机 E2E 冒烟测试 (不依赖 PowerShell 重定向).

直接调用 dao_sw_live 的 Python API, 把完整结果 JSON 写到 _sw_smoke.json.
绕开 Cascade 的终端串扰 / PSReadLine 自动补全等. 幂等.

Usage:
    python 30-验证_Verify/_sw_live_smoke.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))
try:
    import _paths  # noqa: F401
except Exception:
    pass


def main() -> int:
    # —— 立即留痕 (证明脚本被调用) ——
    trace_path = _HERE / "_sw_smoke_trace.log"
    trace_path.write_text(
        f"[{time.strftime('%H:%M:%S')}] smoke script started (pid={sys.argv})\n",
        encoding="utf-8",
    )

    def _trace(msg: str) -> None:
        with trace_path.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    _trace("importing dao_sw_live ...")
    try:
        from dao_sw_live import SWLive, SW_VIEW
    except Exception as e:
        _trace(f"IMPORT FAIL: {type(e).__name__}: {e}")
        raise

    out_dir = _HERE / "_sw_live_demo"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = _HERE / "_sw_smoke.json"
    _trace(f"out_dir={out_dir}")

    stem = f"washer_smoke_{int(time.time())}"
    results = {
        "stem": stem,
        "out_dir": str(out_dir),
        "python": sys.version.split()[0],
        "steps": [],
        "time_start": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    def _log(step: str, r: dict):
        r2 = {"step": step}
        r2.update(r)
        results["steps"].append(r2)
        msg = f"[{step:<28}] ok={r.get('ok')} {r.get('err') or r.get('path') or ''}"
        print(msg)
        _trace(msg)
        # 每步同时刷到 smoke.json, 防 Python 挂在下一步时丢失
        try:
            report_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass

    live = SWLive()
    try:
        _trace("calling ensure_live (no dismiss) ...")
        _log("ensure_live", live.ensure_live(visible=True,
                                              dismiss_welcome=False,
                                              launch_timeout_s=60))
        _trace("ensure_live returned")
        part = live.new_part()
        _log("new_part", {"ok": True, "title": part.title()})
        _trace("new_part returned")

        _log("sketch.start_front", part.sketch.start_front())
        _log("sketch.circle_outer", part.sketch.circle(0, 0, 30))
        _log("sketch.circle_inner", part.sketch.circle(0, 0, 15))
        _log("sketch.stop", part.sketch.stop())

        _log("feature.extrude(5mm)", part.feature.extrude(depth=5))
        _log("rebuild_force", part.rebuild(force=True))
        _log("material", part.material.set_material("普通碳钢"))
        _log("props.Designer", part.props.set("Designer", "ModelForge L11"))

        live.view(SW_VIEW.ISOMETRIC)
        _log("snap_iso", live.snap(out_dir / f"{stem}_iso.png", view="iso"))

        _log("save_as_sldprt", part.save_as(out_dir / f"{stem}.sldprt"))
        _log("export_step",    part.export(out_dir / f"{stem}.step", fmt="step"))
        _log("export_stl",     part.export(out_dir / f"{stem}.stl",  fmt="stl"))

        try:
            results["mass_properties"] = part.mass_properties()
        except Exception as e:
            results["mass_err"] = f"{type(e).__name__}: {e}"

        # 汇总
        oks = sum(1 for s in results["steps"] if s.get("ok"))
        total = len(results["steps"])
        results["summary"] = {"ok": oks, "total": total,
                               "pct": round(oks * 100 / total, 1)}
        results["time_end"] = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n=========  E2E: {oks}/{total}  =========")
    except Exception as e:
        results["fatal"] = f"{type(e).__name__}: {e}"
        print(f"[FATAL] {e}")

    report_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[SAVED] {report_path}  ({report_path.stat().st_size} B)")
    return 0 if results.get("summary", {}).get("ok", 0) > 8 else 1


if __name__ == "__main__":
    sys.exit(main())
