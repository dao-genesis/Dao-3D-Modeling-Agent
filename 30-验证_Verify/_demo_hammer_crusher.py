#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实战 · 南京吴鸿轩 锤式破碎机 · 全零件 FreeCAD GUI 展示
反者道之动 · 反之又反 · 得鱼而忘笙 · 复得返用笙

本脚本展示三场实战:
  1. 打开现成 assembly_full_v6.FCStd    (28 对象完整装配)
  2. 批量加载 11 个独立 STEP 零件       (scene explosion)
  3. V带 (STL mesh) + 单零件 STEP 混合  (多格式协同)

产物: projects/fc_output/_fc_shots/hammer_crusher_*.png
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

SLD_DIR = _dao_paths.PROJECTS / "南京-吴鸿轩_锤式破碎机"   # 原 solidwork建模/南京-吴鸿轩
OUT_CQ  = SLD_DIR / "output_cq"
SHOT    = _dao_paths.PROJECTS / "fc_output" / "_fc_shots"
SHOT.mkdir(parents=True, exist_ok=True)

STEP_PARTS = [
    OUT_CQ / "main_shaft.step",
    OUT_CQ / "rotor_disc.step",
    OUT_CQ / "hammer.step",
    OUT_CQ / "hammer_pin.step",
    OUT_CQ / "driven_pulley.step",
    OUT_CQ / "drive_pulley.step",
    OUT_CQ / "casing_lower.step",
    OUT_CQ / "casing_upper.step",
    OUT_CQ / "motor_body.step",
    OUT_CQ / "frame_base.step",
    OUT_CQ / "screen_plate.step",
]
VBELT_STL   = OUT_CQ / "vbelt_all.stl"
ASSEMBLY_V6 = OUT_CQ / "assembly_full_v6.FCStd"


def banner(s):
    print("\n" + "═" * 72)
    print(f"  {s}")
    print("═" * 72)


def _shot(label, views=("isometric", "front", "top", "right")):
    results = []
    for v in views:
        FCShow.view(v)
        time.sleep(0.25)
        FCShow.fit()
        time.sleep(0.2)
        p = SHOT / f"hammer_crusher_{label}_{v}.png"
        r = FCShow.screenshot(p)
        results.append({"view": v, "ok": r.get("ok"),
                        "kb": round(r.get("size_bytes", 0) / 1024, 1)})
    return results


def demo1_full_assembly():
    banner("[1] 打开完整装配体 · assembly_full_v6.FCStd (28 对象)")
    FCShow.clear(close_all=True)
    r = FCShow.open_fcstd(str(ASSEMBLY_V6))
    print(f"  open: {r}")
    doc_info = FCShow.document()
    obj_count = doc_info.get("document", {}).get("object_count", 0)
    print(f"  documents: {FCShow.documents().get('count')}  obj={obj_count}")
    shots = _shot("assembly", views=("isometric", "front", "top", "right"))
    for s in shots:
        print(f"    [{'v' if s['ok'] else 'x'}] {s['view']:10s} {s['kb']} KB")
    return {"stage": "assembly", "obj_count": obj_count, "shots": shots}


def demo2_scene_explosion():
    banner(f"[2] 批量加载 {len(STEP_PARTS)} 个独立 STEP 零件")
    FCShow.clear(close_all=True)
    FCShow.new_document("Explosion")
    paths = [p for p in STEP_PARTS if p.exists()]
    r = FCShow.load_many(paths, label_with_filename=True, fit=True)
    print(f"  load_many: {r['loaded']}/{r['total']} 成功")
    for d in r["details"]:
        mark = "v" if d.get("ok") else "x"
        sz = Path(d["path"]).stat().st_size // 1024 if Path(d["path"]).exists() else 0
        print(f"    [{mark}] {d['stem']:20s} {sz} KB")
    shots = _shot("explosion", views=("isometric", "front", "top", "right"))
    for s in shots:
        print(f"    [{'v' if s['ok'] else 'x'}] {s['view']:10s} {s['kb']} KB")
    return {"stage": "explosion", "loaded": r["loaded"], "total": r["total"],
            "shots": shots}


def demo3_mixed_formats():
    banner("[3] 多格式协同 · STEP (11件) + STL (V带)")
    FCShow.clear(close_all=True)
    FCShow.new_document("Mixed")
    paths = [p for p in STEP_PARTS if p.exists()]
    if VBELT_STL.exists():
        paths.append(VBELT_STL)
    r = FCShow.load_many(paths, label_with_filename=True, fit=True)
    print(f"  loaded: {r['loaded']}/{r['total']}  (含 STL mesh)")
    shots = _shot("mixed", views=("isometric", "perspective"))
    # perspective 可能不改view, 补做一次 ortho
    FCShow.view("orthographic")
    FCShow.fit()
    extra = FCShow.screenshot(SHOT / "hammer_crusher_mixed_ortho.png")
    shots.append({"view": "orthographic", "ok": extra.get("ok"),
                  "kb": round(extra.get("size_bytes", 0) / 1024, 1)})
    for s in shots:
        print(f"    [{'v' if s['ok'] else 'x'}] {s['view']:13s} {s['kb']} KB")
    # 保存 FCStd 快照
    save_p = SHOT / "hammer_crusher_mixed.FCStd"
    sr = FCShow.save_as(str(save_p))
    print(f"  save: ok={sr.get('ok')}  → {save_p.name}")
    return {"stage": "mixed", "loaded": r["loaded"], "shots": shots,
            "fcstd": str(save_p)}


def main():
    print("═" * 72)
    print("  反者道之动 · 反之又反")
    print("  南京吴鸿轩 锤式破碎机 · FreeCAD GUI 三场实战")
    print("═" * 72)

    if not FCShow.alive():
        print("\n  [启动] FreeCAD GUI …")
        r = FCShow.ensure_gui()
        if not r.get("ok"):
            print(f"  ✘ GUI 启动失败: {r}")
            return 1
        print(f"  ✔ GUI 就绪 ({r.get('elapsed_s','?')}s)")

    results = {}
    for key, fn in [("demo1", demo1_full_assembly),
                    ("demo2", demo2_scene_explosion),
                    ("demo3", demo3_mixed_formats)]:
        try:
            results[key] = fn()
        except Exception as e:
            import traceback
            print(f"\n  ✘ {key} FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()
            results[key] = {"error": str(e)}

    banner("实战总结")
    total_shots = sum(len(d.get("shots", [])) for d in results.values())
    ok_shots = sum(sum(1 for s in d.get("shots", []) if s.get("ok"))
                   for d in results.values())
    print(f"  场次: 3   截图: {ok_shots}/{total_shots}  产出目录: {SHOT}")
    print(f"  demo1: 装配 · {results['demo1'].get('obj_count')} 对象")
    print(f"  demo2: 散装 · {results['demo2'].get('loaded')}/{results['demo2'].get('total')}")
    print(f"  demo3: 混合 · {results['demo3'].get('loaded')} loaded, FCStd 已保存")

    # 保存 JSON
    rpt = SHOT / "hammer_crusher_demo_report.json"
    rpt.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str),
                   encoding="utf-8")
    print(f"\n  详细报告: {rpt}")
    print("\n  得鱼忘笙, 复得返用笙 ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
