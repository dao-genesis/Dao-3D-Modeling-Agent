#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ORS6_Stewart · final regression — pytest + CLI health + viewer API + deliverables.

One-shot end-to-end verification, output to stdout (no PS pollution).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PKG = TOOLS.parent
ROOT = PKG.parent
sys.path.insert(0, str(ROOT))

PYTHON = sys.executable

results = []


def step(name, fn):
    print(f"\n═══ {name} ═══")
    try:
        ok, msg = fn()
        mark = "✓" if ok else "✗"
        print(f"  [{mark}] {msg}")
        results.append((name, ok, msg))
    except Exception as e:
        print(f"  [✗] EXCEPTION: {e!r}")
        results.append((name, False, f"EXC: {e!r}"))


def s_pytest():
    r = subprocess.run([PYTHON, "-m", "pytest", "ORS6_Stewart/tests/", "-q", "--tb=no"],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    last = (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else "no output"
    return r.returncode == 0, last


def s_health():
    # 反者道之动 (2026-05-09): subprocess.run with 17s health command
    # was deadlocking in shared-tty environments; in-process call is robust.
    import io
    import contextlib
    from ORS6_Stewart import cli as _cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _cli.cmd_health()
    out = buf.getvalue()
    last = [ln for ln in out.splitlines() if "Health" in ln or "Grade" in ln]
    return ("Grade S" in out), (last[-1] if last else "no Health line")


def s_viewer():
    import ORS6_Stewart.viewer.server as srv
    PORT = 8893
    srv.PORT = PORT
    server = srv.ThreadedHTTPServer(("127.0.0.1", PORT), srv.StudioHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    try:
        BASE = f"http://127.0.0.1:{PORT}"
        def get(p): return json.loads(urllib.request.urlopen(f"{BASE}{p}", timeout=5).read())

        h = get("/api/health")
        ins = get("/api/instances")
        rods = get("/api/rods_3d")
        gv = get("/api/geometry_verify")
        parts = get("/api/parts")

        max_dev = max(abs(L["rod_3d_mm"] - 175.0) for L in ins.get("links", []))
        gv_ok = sum(1 for c in gv if c.get("ok"))

        all_ok = (h.get("status") == "ok"
                  and ins.get("rod_model") == "physical_3d"
                  and max_dev < 0.001
                  and gv_ok == len(gv)
                  and len(parts) == 31)
        msg = (f"health=ok · instances rod_model={ins.get('rod_model')} "
               f"6 rods max Δ={max_dev:.6f}mm · geom V1-V12 {gv_ok}/{len(gv)} OK · "
               f"parts {len(parts)}/31")
        return all_ok, msg
    finally:
        server.shutdown()
        server.server_close()


def s_deliverables():
    out_dir = PKG / "output"
    files = {
        "BOM.md":              PKG / "BOM.md",
        "DELIVERY.md":         PKG / "DELIVERY.md",
        "_5pose_summary.json": out_dir / "_5pose_summary.json",
        "_freecad_5pose_summary.json": out_dir / "_freecad_5pose_summary.json",
    }
    parts = []
    for name, p in files.items():
        if not p.exists():
            return False, f"{name} MISSING"
        parts.append(f"{name}={p.stat().st_size}B")
    # Verify summaries
    cq = json.loads((out_dir / "_5pose_summary.json").read_text(encoding="utf-8"))
    fc = json.loads((out_dir / "_freecad_5pose_summary.json").read_text(encoding="utf-8"))
    cq_ok = cq.get("ok_count")
    cq_tot = cq.get("total")
    fc_ok = fc.get("ok_count")
    fc_tot = fc.get("total")
    return ((cq_ok == cq_tot == 5) and (fc_ok == fc_tot == 5),
            f"CadQuery {cq_ok}/{cq_tot} · FreeCAD {fc_ok}/{fc_tot} · " + ", ".join(parts))


def s_freecad_artifacts():
    out_dir = PKG / "output"
    poses = ["home", "forward", "side_right", "pitch_up", "roll_left"]
    rows = []
    total = 0
    for p in poses:
        fc = out_dir / f"ORS6_{p}.FCStd"
        st = out_dir / f"ORS6_{p}.step"
        if not (fc.exists() and st.exists()):
            return False, f"{p}: FCStd or step missing"
        rows.append(f"{p}={fc.stat().st_size//1024}KB")
        total += fc.stat().st_size + st.stat().st_size
    return True, f"5 pose · " + " · ".join(rows) + f" · total={total/1024/1024:.1f}MB"


def s_freecad_screenshots():
    """FreeCAD GUI screenshots — visual truth proof of Stewart assembly."""
    out_dir = PKG / "output"
    sdir = out_dir / "screenshots"
    if not sdir.exists():
        return False, f"screenshots dir missing: {sdir}"
    poses = ["home", "forward", "side_right", "pitch_up", "roll_left"]
    rows = []
    total = 0
    for p in poses:
        png = sdir / f"ORS6_{p}.png"
        if not png.exists():
            return False, f"{p}: PNG missing"
        sz = png.stat().st_size
        if sz < 10_000:  # Sanity: even an empty viewport > 10KB
            return False, f"{p}: PNG too small ({sz}B)"
        rows.append(f"{p}={sz//1024}KB")
        total += sz
    # Summary JSON also exists
    sumj = out_dir / "_freecad_gui_summary.json"
    if not sumj.exists():
        return False, "_freecad_gui_summary.json missing"
    g = json.loads(sumj.read_text(encoding="utf-8"))
    if g.get("ok_count") != g.get("total"):
        return False, f"GUI summary: {g.get('ok_count')}/{g.get('total')}"
    return True, f"5 PNG · " + " · ".join(rows) + f" · total={total/1024:.0f}KB · summary {g.get('ok_count')}/{g.get('total')}"


def s_repo_clean():
    """Verify ORS6_Stewart top-level is clean (only source + 4 dirs + BOM/DELIVERY/README/_AGENTS)."""
    expected_files = {
        "__init__.py", "__main__.py", "_AGENTS.md", "_stl_bounds.json",
        "analysis.py", "assembly.py", "cli.py", "geometry.py", "kinematics.py",
        "parts.py", "poses.py", "verify.py",
        "BOM.md", "DELIVERY.md", "README.md",
    }
    expected_dirs = {"_archive", "output", "tests", "tools", "viewer"}
    # 反者道之动: 工具自来副产物 (Python/pytest/mypy/ruff 缓存) 不当作仓库脏物.
    _TOOL_CACHES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    actual_files = {p.name for p in PKG.iterdir() if p.is_file()}
    actual_dirs = {p.name for p in PKG.iterdir() if p.is_dir() and p.name not in _TOOL_CACHES}

    extra_files = actual_files - expected_files
    extra_dirs = actual_dirs - expected_dirs
    missing = (expected_files - actual_files) | (expected_dirs - actual_dirs)

    if missing:
        return False, f"missing: {sorted(missing)}"
    if extra_files:
        return False, f"unexpected files: {sorted(extra_files)}"
    if extra_dirs:
        return False, f"unexpected dirs: {sorted(extra_dirs)}"
    return True, f"{len(actual_files)} files + {len(actual_dirs)} dirs · 道生一 clean"


try:
    from ORS6_Stewart import __version__ as _ORS6_VERSION
except Exception:
    _ORS6_VERSION = "?"

print("=" * 70)
print(f"ORS6_Stewart · v{_ORS6_VERSION} final regression (道法自然)")
print("=" * 70)

step("一 · pytest 341",       s_pytest)
step("二 · CLI health",       s_health)
step("三 · Viewer API",       s_viewer)
step("四 · CadQuery + FC summaries", s_deliverables)
step("五 · FreeCAD 5 FCStd artifacts", s_freecad_artifacts)
step("六 · FreeCAD GUI 5 PNG screenshots", s_freecad_screenshots)
step("七 · Repo top-level clean", s_repo_clean)

print()
print("=" * 70)
ok = sum(1 for _, o, _ in results if o)
print(f"FINAL: {ok}/{len(results)} pass")
for n, o, m in results:
    print(f"  [{'✓' if o else '✗'}] {n}")
sys.exit(0 if ok == len(results) else 1)
