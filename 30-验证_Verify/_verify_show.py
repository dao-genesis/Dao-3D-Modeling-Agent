#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_verify_show.py — FCShow 本源验证
═══════════════════════════════════════════════════════════════
反者道之动 · 反之又反 · 笙成笙用

每项 ok=True 计 1 分. 总分 >= 90% 为 S.
"""
from __future__ import annotations
import sys, json, time
from pathlib import Path

HERE = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in HERE.parents if (p / '_paths.py').is_file()), HERE.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

from fc_show import FCShow
from fc_reverse import FCReverse

# ─── 测试素材 ──────────────────────────────────────────
WFG = _dao_paths.PROJECTS / "fc_output" / "_万法归一" / "万法.fcstd"
SLD = _dao_paths.PROJECTS / "南京-吴鸿轩_锤式破碎机" / "output_cq"
SHOT_DIR = _dao_paths.PROJECTS / "fc_output" / "_fc_shots" / "_verify"
SHOT_DIR.mkdir(parents=True, exist_ok=True)


def check(idx, name, cond, detail=""):
    tag = "✓" if cond else "✗"
    print(f"  [{idx:02d}] [{tag}] {name}  {detail}")
    return 1 if cond else 0


def main():
    print("═" * 72)
    print("  FCShow 本源验证 · 笙用无间")
    print("═" * 72)
    score = 0
    total = 0

    # ── GUI 就绪 ──────────────────────────────────────
    total += 1
    gui = FCShow.ensure_gui()
    score += check(1, "GUI 就绪 (HTTP /status)", gui.get("ok"),
                   f"port={gui.get('port', '?')}")

    # ── 基础 API ──────────────────────────────────────
    total += 1
    st = FCShow.status()
    score += check(2, "/status 返回 freecad_version",
                   st.get("ok") and "freecad_version" in st)

    total += 1
    cls = FCShow.clear(close_all=True)
    score += check(3, "close_all 成功", cls.get("ok"),
                   str(cls.get("result"))[:50])

    total += 1
    nd = FCShow.new_document("VerifyShow")
    score += check(4, "new_document 成功", nd.get("ok"))

    # ── 空文档截图 (应成功) ───────────────────────────
    total += 1
    FCShow.view("isometric")
    s1 = FCShow.screenshot(SHOT_DIR / "01_empty.png")
    score += check(5, "空文档截图成功", s1.get("ok"),
                   f"{s1.get('size_bytes', 0)}B")

    # ── 加载 FCStd ────────────────────────────────────
    total += 1
    if WFG.exists():
        load_r = FCShow.open_fcstd(str(WFG))
        score += check(6, f"open_fcstd 万法.fcstd", load_r.get("ok"))
    else:
        score += check(6, "open_fcstd (WFG missing)", False, str(WFG))

    total += 1
    FCShow.view("isometric"); FCShow.fit()
    s2 = FCShow.screenshot(SHOT_DIR / "02_万法.png")
    score += check(7, "万法装配 isometric 截图",
                   s2.get("ok") and s2.get("size_bytes", 0) > 20000,
                   f"{s2.get('size_bytes', 0)}B (>20KB 视为有几何)")

    # ── 多视角循环 ────────────────────────────────────
    views_ok = 0
    for v in ("front", "top", "right", "rear"):
        FCShow.view(v); FCShow.fit(); time.sleep(0.2)
        r = FCShow.screenshot(SHOT_DIR / f"03_{v}.png")
        if r.get("ok") and r.get("size_bytes", 0) > 5000:
            views_ok += 1
    total += 1
    score += check(8, "多视角 (front/top/right/rear) 截图", views_ok == 4,
                   f"{views_ok}/4")

    # ── 加载 STEP ─────────────────────────────────────
    total += 1
    step_path = SLD / "main_shaft.step"
    if step_path.exists():
        FCShow.clear(close_all=True)
        FCShow.new_document("SingleStep")
        r = FCShow.load(str(step_path))
        score += check(9, "load STEP (main_shaft)", r.get("ok"))
    else:
        score += check(9, "load STEP (file missing)", False)

    # ── 截图 STEP 对象 ────────────────────────────────
    total += 1
    FCShow.isometric()
    r = FCShow.screenshot(SHOT_DIR / "04_main_shaft.png")
    score += check(10, "STEP 对象截图",
                   r.get("ok") and r.get("size_bytes", 0) > 5000,
                   f"{r.get('size_bytes', 0)}B")

    # ── 加载 STL (V带) ────────────────────────────────
    total += 1
    stl_path = SLD / "vbelt_all.stl"
    if stl_path.exists():
        FCShow.clear(close_all=True)
        FCShow.new_document("Mesh")
        r = FCShow.load(str(stl_path))
        score += check(11, "load STL (V带)", r.get("ok"))
    else:
        score += check(11, "load STL (file missing)", False)

    total += 1
    FCShow.isometric()
    r = FCShow.screenshot(SHOT_DIR / "05_vbelt.png")
    score += check(12, "STL mesh 截图",
                   r.get("ok") and r.get("size_bytes", 0) > 3000,
                   f"{r.get('size_bytes', 0)}B")

    # ── 批量加载 ──────────────────────────────────────
    total += 1
    paths = [SLD / n for n in ("main_shaft.step", "rotor_disc.step",
                                "hammer.step", "hammer_pin.step")]
    paths = [p for p in paths if p.exists()]
    FCShow.clear(close_all=True)
    FCShow.new_document("Batch")
    r = FCShow.load_many(paths)
    score += check(13, f"load_many ({len(paths)} STEPs)",
                   r.get("ok") and r.get("loaded") == len(paths),
                   f"{r.get('loaded')}/{r.get('total')}")

    total += 1
    FCShow.isometric()
    r = FCShow.screenshot(SHOT_DIR / "06_batch.png")
    score += check(14, "批量 STEP 截图",
                   r.get("ok") and r.get("size_bytes", 0) > 10000,
                   f"{r.get('size_bytes', 0)}B")

    # ── 反演后 STEP 产物送 GUI ────────────────────────
    total += 1
    if WFG.exists():
        adapt = FCReverse.adapt(str(WFG),
                                 patch={"PDBox.L": 120, "PDCyl.R": 25})
        score += check(15, "fc_reverse.adapt 改参成功",
                       adapt.get("ok"), f"stage={adapt.get('stage')}")
    else:
        score += check(15, "fc_reverse.adapt (WFG missing)", False)

    total += 1
    exports = adapt.get("replay", {}).get("exports", []) if WFG.exists() else []
    step_out = next((e["path"] for e in exports if e.get("op") == "export_step"), None)
    if step_out and Path(step_out).exists():
        FCShow.clear(close_all=True)
        FCShow.new_document("AdaptOut")
        FCShow.load(step_out)
        FCShow.isometric()
        r = FCShow.screenshot(SHOT_DIR / "07_adapt.png")
        score += check(16, "改参后 STEP → GUI 展示",
                       r.get("ok") and r.get("size_bytes", 0) > 10000,
                       f"{Path(step_out).stat().st_size} bytes STEP → {r.get('size_bytes', 0)}B 截图")
    else:
        score += check(16, "改参后 STEP (missing)", False)

    # ── 视图动作多样性 ────────────────────────────────
    total += 1
    actions = ("isometric", "front", "rear", "top", "bottom", "left", "right")
    ok_acts = sum(1 for a in actions if FCShow.view(a).get("ok"))
    score += check(17, "视图动作全通 (7种)", ok_acts == 7, f"{ok_acts}/7")

    # ── 投影切换 ──────────────────────────────────────
    total += 1
    p1 = FCShow.view("perspective").get("ok")
    p2 = FCShow.view("orthographic").get("ok")
    score += check(18, "perspective/orthographic 切换", p1 and p2)

    # ── 保存 + 重打开 ────────────────────────────────
    total += 1
    fcstd_out = SHOT_DIR / "verify.FCStd"
    sv = FCShow.save_as(str(fcstd_out))
    score += check(19, "save_as FCStd", sv.get("ok"))

    total += 1
    if fcstd_out.exists():
        FCShow.clear(close_all=True)
        re = FCShow.open_fcstd(str(fcstd_out))
        score += check(20, "重新 open 保存过的 FCStd", re.get("ok"))
    else:
        score += check(20, "FCStd missing", False)

    # ── 汇总 ──────────────────────────────────────────
    print("\n" + "═" * 72)
    pct = 100.0 * score / total
    grade = "S" if pct >= 95 else ("A" if pct >= 85 else ("B" if pct >= 70 else "C"))
    print(f"  {score}/{total} = {pct:.1f}%   等级: {grade}")
    print(f"  截图目录: {SHOT_DIR}")
    print("═" * 72)

    # 输出 JSON
    report = {
        "score": score, "total": total, "pct": round(pct, 1), "grade": grade,
        "shot_dir": str(SHOT_DIR),
    }
    (SHOT_DIR / "_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if grade in ("S", "A") else 1


if __name__ == "__main__":
    sys.exit(main())
