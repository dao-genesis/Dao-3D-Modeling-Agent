#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_sw_live_smoke_v2.py — L11 真机 smoke · 自带超时保护 · 道法自然

相较 v1:
  · 每个活体步骤都用 threading.Thread + join(timeout) 包装
  · 超时即硬退 (os._exit 绕过 COM cleanup deadlock)
  · dismiss_welcome 走 win32 EnumWindows 而非 COM (避模态死循环)
  · 默认自启 SW (launch_timeout 120s), --no-launch 可关
  · 每步落盘 _sw_smoke.json, 不依赖终端

使用:
    # 默认: 自启 SW, 每步 30s, 连接最多 150s
    python 30-验证_Verify/_sw_live_smoke_v2.py
    # 只快探 (SW 需已在跑)
    python 30-验证_Verify/_sw_live_smoke_v2.py --no-launch
    # 放宽每步超时
    python 30-验证_Verify/_sw_live_smoke_v2.py --timeout-per-step 60
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))
try:
    import _paths  # noqa: F401
except Exception:
    pass


class StepTimeout(Exception):
    pass


# ── Watchdog: 守护线程, 单步/总超时自动 os._exit ──
_watchdog_deadline: float = 0.0   # 当前步骤的 deadline (主线程设)
_watchdog_total: float = 0.0      # 总 deadline

def _start_watchdog(total_timeout_s: float = 600.0):
    """启动全局看门狗. 每秒检查: 单步超时或总超时 → os._exit(42)."""
    global _watchdog_total
    _watchdog_total = time.time() + total_timeout_s

    def _watcher():
        while True:
            time.sleep(1.0)
            now = time.time()
            if now > _watchdog_total:
                print(f"\n[WATCHDOG] 总超时 ({total_timeout_s}s) · os._exit(42)", flush=True)
                os._exit(42)
            if _watchdog_deadline > 0 and now > _watchdog_deadline:
                print(f"\n[WATCHDOG] 单步超时 · os._exit(43)", flush=True)
                os._exit(43)

    t = threading.Thread(target=_watcher, daemon=True)
    t.start()


def _dismiss_welcome_win32(timeout_s: float = 5.0) -> Dict[str, Any]:
    """win32 EnumWindows 找 SW Welcome 弹窗, 发 WM_CLOSE. 不走 COM."""
    try:
        import win32gui
        import win32con
    except Exception as e:
        return {"ok": False, "err": f"no win32gui: {e}"}
    hits: list[int] = []
    t0 = time.time()

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = (win32gui.GetWindowText(hwnd) or "").strip()
            cls = win32gui.GetClassName(hwnd) or ""
            low = title.lower()
            if any(k in low for k in ("welcome", "欢迎", "what's new", "tip of")):
                hits.append(hwnd)
            elif "SwCefDialog" in cls and title:
                hits.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception as e:
        return {"ok": False, "err": f"EnumWindows: {e}", "elapsed": time.time() - t0}
    closed = []
    for hwnd in hits:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            closed.append(hwnd)
        except Exception:
            pass
    return {"ok": True, "found": len(hits), "closed": len(closed),
            "elapsed": round(time.time() - t0, 2)}


def main() -> int:
    # ── 参数 ──
    timeout_per = 30.0
    connect_timeout = 150.0
    want_launch = True
    for i, a in enumerate(sys.argv):
        if a == "--timeout-per-step" and i + 1 < len(sys.argv):
            timeout_per = float(sys.argv[i + 1])
        elif a == "--connect-timeout" and i + 1 < len(sys.argv):
            connect_timeout = float(sys.argv[i + 1])
        elif a == "--no-launch":
            want_launch = False

    # ── 立即留痕 ──
    trace_path = _HERE / "_sw_smoke_trace.log"
    report_path = _HERE / "_sw_smoke.json"
    trace_path.write_text(
        f"[{time.strftime('%H:%M:%S')}] smoke v2 start (pid={os.getpid()}, timeout={timeout_per}s)\n",
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
        return 2

    out_dir = _HERE / "_sw_live_demo"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"washer_v2_{int(time.time())}"
    results: Dict[str, Any] = {
        "stem": stem,
        "out_dir": str(out_dir),
        "python": sys.version.split()[0],
        "timeout_per_step": timeout_per,
        "time_start": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps": [],
    }

    def _flush():
        try:
            report_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass

    # 启动 watchdog (总超时 10 分钟)
    _start_watchdog(total_timeout_s=600.0)

    def _step(name: str, fn: Callable, *a, **kw):
        """主线程直接跑 fn (COM safe). watchdog 管超时."""
        global _watchdog_deadline
        _trace(f"→ {name}")
        _watchdog_deadline = time.time() + timeout_per  # 设单步 deadline
        rec: Dict[str, Any] = {"step": name, "t0": time.strftime("%H:%M:%S")}
        try:
            v = fn(*a, **kw)
            if isinstance(v, dict):
                rec.update(v)
            else:
                rec["ok"] = True
                rec["value"] = str(v)[:200]
        except Exception as e:
            rec["ok"] = False
            rec["err"] = f"{type(e).__name__}: {e}"
            _trace(f"  ERR {name}: {rec['err']}")
        finally:
            _watchdog_deadline = 0.0  # 解除单步 deadline
        results["steps"].append(rec)
        _flush()
        ok = rec.get("ok")
        _trace(f"  {name} ok={ok}")
        return rec

    # ── 1. 连接 (主线程 COM, 避 cross-apartment deadlock) ──
    live = SWLive()
    _trace(f"connect (launch={want_launch}, timeout={connect_timeout}s)")

    rec_conn: Dict[str, Any] = {"step": "connect", "t0": time.strftime("%H:%M:%S")}
    try:
        # 主线程直接 ensure_live — COM proxy 留在主 STA apartment
        r = live.ensure_live(
            visible=True,
            dismiss_welcome=False,  # 后面走 win32
            launch_timeout_s=connect_timeout,
        )
        rec_conn.update(r)
        if r.get("ok"):
            try:
                rec_conn["title"] = live.app.ActiveDoc.GetTitle() if live.app.ActiveDoc else "(no doc)"
            except Exception:
                rec_conn["title"] = "(no active doc)"
    except Exception as e:
        rec_conn["ok"] = False
        rec_conn["err"] = f"{type(e).__name__}: {e}"
        _trace(f"  ERR connect: {rec_conn['err']}")
    results["steps"].append(rec_conn)
    _flush()
    _trace(f"  connect ok={rec_conn.get('ok')}")

    if not rec_conn.get("ok"):
        _trace("ABORT: cannot connect SW")
        results["summary"] = {"aborted": True}
        results["time_end"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _flush()
        return 1

    # ── 1.5. 关 Welcome 弹窗 (win32, 不碰 COM) ──
    _step("dismiss_welcome_win32", _dismiss_welcome_win32)

    # ── 1.7. 等 SW 主窗口就绪 (纯 win32, 避 STA deadlock) ──
    def _wait_sw_ready(timeout_s: float = 60.0, poll: float = 0.5) -> Dict[str, Any]:
        """用 win32 探 SW 主窗口活体, 不走 COM (避 STA apartment deadlock).

        判据: 找到 SW 主窗口 + visible + 非 HungAppWindow.
        """
        try:
            import win32gui, win32process, win32api, ctypes
        except Exception as e:
            return {"ok": False, "err": f"no win32: {e}"}

        user32 = ctypes.windll.user32
        is_hung = user32.IsHungAppWindow

        # 先拿到 SLDWORKS.exe 的 PID
        import subprocess
        try:
            out = subprocess.check_output(
                ["tasklist", "/fi", "IMAGENAME eq SLDWORKS.exe", "/fo", "csv"],
                text=True, encoding="gbk", errors="ignore",
            )
            pids = []
            for ln in out.splitlines()[1:]:
                parts = [p.strip('"') for p in ln.split(",")]
                if len(parts) >= 2 and parts[0].lower().startswith("sldworks"):
                    try: pids.append(int(parts[1]))
                    except ValueError: pass
        except Exception as e:
            return {"ok": False, "err": f"tasklist: {e}"}
        if not pids:
            return {"ok": False, "err": "SLDWORKS.exe 未运行"}

        target_pids = set(pids)

        def _find_sw_main() -> Optional[int]:
            hits = []
            def _cb(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid not in target_pids:
                        return True
                    title = (win32gui.GetWindowText(hwnd) or "")
                    cls = (win32gui.GetClassName(hwnd) or "")
                    # SW 主窗口标题通常含 "SOLIDWORKS"
                    if "SOLIDWORKS" in title.upper() or cls.startswith("#32770") is False and "SldWorks" in cls:
                        hits.append(hwnd)
                    elif "SOLIDWORKS" in title.upper():
                        hits.append(hwnd)
                except Exception:
                    pass
                return True
            try:
                win32gui.EnumWindows(_cb, None)
            except Exception:
                return None
            # 取最大 rect 的那个 (主窗口)
            best = None; best_area = 0
            for h in hits:
                try:
                    l, t, r, b = win32gui.GetWindowRect(h)
                    area = max(0, r - l) * max(0, b - t)
                    if area > best_area:
                        best = h; best_area = area
                except Exception:
                    pass
            return best

        t0 = time.time()
        while time.time() - t0 < timeout_s:
            hwnd = _find_sw_main()
            if hwnd:
                hung = bool(is_hung(hwnd))
                if not hung:
                    title = win32gui.GetWindowText(hwnd)
                    return {"ok": True, "hwnd": hwnd, "title": title,
                            "pids": list(target_pids),
                            "elapsed": round(time.time() - t0, 1)}
            time.sleep(poll)
        return {"ok": False, "elapsed": round(time.time() - t0, 1),
                "pids": list(target_pids),
                "hint": "SW 主窗口未就绪或 HungAppWindow"}

    _step("wait_sw_ready", lambda: _wait_sw_ready(timeout_s=60.0))
    # 再给一口气: 让 paint thread 渲染完 UI
    time.sleep(2.0)

    # ── 2. 新建零件 ──
    part_holder: Dict[str, Any] = {}

    def _new_part():
        part_holder["part"] = live.new_part()
        return {"ok": True, "title": part_holder["part"].title()}

    _step("new_part", _new_part)
    if "part" not in part_holder:
        _flush(); return 1
    part = part_holder["part"]

    # ── 3. 草图 + 特征 ──
    _step("sketch.start_front", part.sketch.start_front)
    _step("sketch.circle_outer", lambda: part.sketch.circle(0, 0, 30))
    _step("sketch.circle_inner", lambda: part.sketch.circle(0, 0, 15))
    _step("sketch.stop", part.sketch.stop)
    _step("feature.extrude", lambda: part.feature.extrude(depth=5))
    _step("rebuild", lambda: part.rebuild(force=True))

    # ── 4. 材质/属性 ──
    _step("material", lambda: part.material.set_material("普通碳钢"))
    _step("prop_designer", lambda: part.props.set("Designer", "ModelForge L11"))

    # ── 5. 截图 ──
    _step("view_iso", lambda: live.view(SW_VIEW.ISOMETRIC))
    _step("snap_iso", lambda: live.snap(out_dir / f"{stem}_iso.png", view="iso"))

    # ── 6. 保存 ──
    _step("save_sldprt", lambda: part.save_as(out_dir / f"{stem}.sldprt"))
    _step("export_step", lambda: part.export(out_dir / f"{stem}.step", fmt="step"))
    _step("export_stl",  lambda: part.export(out_dir / f"{stem}.stl",  fmt="stl"))

    # ── 7. mass ──
    rec_mass = _step("mass_properties", part.mass_properties)
    # 碳钢垫片 (OD60 ID30 5mm) 理论质量 ~83g; 若 mass < 10g 则索引映射仍有误
    if rec_mass.get("ok"):
        m = rec_mass.get("mass_kg", 0)
        if m < 0.01:
            _trace(f"  ⚠ mass_kg={m} 不合理 (应 ≈ 0.083 kg) — 索引映射可能有误")
            rec_mass["sanity_warn"] = f"mass_kg={m} < 0.01 kg"

    # ── 8. 总结 ──
    oks = sum(1 for s in results["steps"] if s.get("ok"))
    total = len(results["steps"])
    results["summary"] = {
        "ok": oks, "total": total,
        "pct": round(oks * 100 / max(total, 1), 1),
    }
    results["time_end"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _flush()
    _trace(f"E2E: {oks}/{total}")
    print(f"\n========= L11 E2E: {oks}/{total} ({results['summary']['pct']}%) =========")
    print(f"[REPORT] {report_path}")
    return 0 if oks >= total - 1 else 1


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        print(f"[FATAL] {type(e).__name__}: {e}")
        rc = 3
    # 硬退, 绕开可能挂死的 COM 线程
    os._exit(rc)
