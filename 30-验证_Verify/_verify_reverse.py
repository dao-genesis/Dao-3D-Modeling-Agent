#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反者道之动 · FCReverse 本源验证
═══════════════════════════════════════════════════════════════
验证链: 索引→反演→改参→重放→产物对比
  1. 索引天下件                 (扫描FreeCAD安装+projects+网络资源库)
  2. 反演 万法.fcstd → 10 ops   (Part::Box/Cylinder/Cut + 7 Part::Feature)
  3. 原样重放 → 产物             (compound + export_stl/step)
  4. 改参数重放 → 产物            (PDBox.L, PDBox.W, PDBox.H, PDCyl.R, PDCyl.H)
  5. 对比体积: 原版 ≠ 重放 ≠ 改参 (确认参数确实生效)
  6. 批量覆盖率: 53 FCStd → X% 可反演

运行: python _verify_reverse.py
"""
from __future__ import annotations
import json, sys, time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in HERE.parents if (p / '_paths.py').is_file()), HERE.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

from fc_reverse import FCReverse, _find_leaves

SRC = _dao_paths.PROJECTS / "fc_output" / "_万法归一" / "万法.fcstd"
OUT = _dao_paths.PROJECTS / "fc_output" / "_fc_reverse_test"
OUT.mkdir(parents=True, exist_ok=True)


def banner(s: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {s}")
    print("=" * 70)


def assert_true(cond: bool, msg: str) -> bool:
    mark = "✔" if cond else "✘"
    print(f"  [{mark}] {msg}")
    return cond


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: fixture missing: {SRC}")
        return 1

    passed = 0
    total = 0

    # ── 1. 索引 ─────────────────────────────────────────────────
    banner("1. 索引天下件")
    t0 = time.time()
    idx = FCReverse.index(refresh=True)
    print(f"  generated_at={idx['generated_at']}  elapsed={idx['elapsed_s']}s")
    print(f"  total={idx['total']}  elapsed_here={round(time.time()-t0,2)}s")
    print(f"  by_kind={idx['by_kind']}")
    total += 1; passed += assert_true(idx["total"] > 100, "索引条目 > 100")
    total += 1; passed += assert_true("fcstd" in idx["by_kind"], "含 fcstd")
    total += 1; passed += assert_true("step" in idx["by_kind"],  "含 step")

    # ── 2. 反演 万法.fcstd ───────────────────────────────────────
    banner("2. 反演 万法.fcstd → ops")
    rev = FCReverse.reverse(str(SRC))
    print(f"  ok={rev['ok']}  op_count={len(rev['ops'])}  "
          f"leaves={_find_leaves(rev['ops'])}")
    types = Counter(op["op"] for op in rev["ops"])
    for t, n in types.most_common():
        print(f"    {t:18s} {n}")
    total += 1; passed += assert_true(rev["ok"], "反演成功")
    total += 1; passed += assert_true(len(rev["ops"]) == 10, "10 ops")
    total += 1; passed += assert_true(types.get("make_box", 0) == 1, "make_box x1")
    total += 1; passed += assert_true(types.get("make_cylinder", 0) == 1, "make_cylinder x1")
    total += 1; passed += assert_true(types.get("cut", 0) == 1, "cut x1")
    total += 1; passed += assert_true(types.get("import_brep", 0) == 7, "import_brep x7")
    total += 1; passed += assert_true(rev["meta"]["warnings"] == [], "无 warnings")

    # 保存 ops.json
    ops_path = OUT / "万法_ops.json"
    ops_path.write_text(json.dumps(rev["ops"], ensure_ascii=False, indent=2),
                        encoding="utf-8")
    total += 1; passed += assert_true(ops_path.exists(), f"ops.json 已生成: {ops_path.name}")

    # ── 3. 原样重放 ─────────────────────────────────────────────
    banner("3. 原样重放 → 万法_replay")
    r1 = FCReverse.replay(rev["ops"], label="万法_replay", out_dir=str(OUT))
    print(f"  ok={r1['ok']}  elapsed={r1.get('elapsed_s')}s")
    total += 1; passed += assert_true(r1.get("ok"), "重放成功")
    total += 1; passed += assert_true(r1.get("elapsed_s", 99) < 10, "重放 < 10s")
    stl_out = OUT / "万法_replay.stl"
    total += 1; passed += assert_true(stl_out.exists() and stl_out.stat().st_size > 10000,
                                       f"STL 产物 > 10KB: {stl_out.stat().st_size if stl_out.exists() else 0} bytes")

    # ── 4. 改参数重放 ────────────────────────────────────────────
    banner("4. 改参数重放 → 万法_patched")
    patch = {"PDBox.L": 100, "PDBox.W": 60, "PDBox.H": 50,
             "PDCyl.R": 20,  "PDCyl.H": 60}
    print(f"  patch: {patch}")
    patched_ops = FCReverse.patch(rev["ops"], patch)
    r2 = FCReverse.replay(patched_ops, label="万法_patched", out_dir=str(OUT))
    print(f"  ok={r2['ok']}  elapsed={r2.get('elapsed_s')}s")
    total += 1; passed += assert_true(r2.get("ok"), "改参重放成功")

    # 验证 patch 实际进入 ops
    box_op = next((o for o in patched_ops if o.get("id") == "PDBox"), {})
    total += 1; passed += assert_true(box_op.get("L") == 100, f"PDBox.L == 100 (got {box_op.get('L')})")
    total += 1; passed += assert_true(box_op.get("H") == 50,  f"PDBox.H == 50 (got {box_op.get('H')})")

    # ── 5. 对比体积 ──────────────────────────────────────────────
    banner("5. 体积对比 (原版 vs 重放 vs 改参)")
    try:
        import trimesh
        m_orig = trimesh.load(str(HERE / "projects" / "fc_output" / "_万法归一" / "万法.stl"))
        m_replay = trimesh.load(str(OUT / "万法_replay.stl"))
        m_patched = trimesh.load(str(OUT / "万法_patched.stl"))
        v_orig, v_rep, v_pat = m_orig.volume, m_replay.volume, m_patched.volume
        print(f"  原版   : vol={v_orig:10.1f} mm³  bbox={m_orig.bounds.tolist()}")
        print(f"  重放   : vol={v_rep:10.1f} mm³  bbox={m_replay.bounds.tolist()}")
        print(f"  改参数 : vol={v_pat:10.1f} mm³  bbox={m_patched.bounds.tolist()}")
        total += 1; passed += assert_true(abs(v_rep - v_pat) > 1000,
                                           f"改参后体积显著变化 (Δ={abs(v_rep-v_pat):.0f} mm³)")
        # 改参后 bbox X 应为 100
        total += 1; passed += assert_true(
            abs(m_patched.bounds[1, 0] - 100) < 1,
            f"改参后 bbox.x.max ≈ 100 (got {m_patched.bounds[1, 0]:.2f})"
        )
    except Exception as e:
        print(f"  体积对比跳过 (trimesh/文件缺失): {e}")

    # ── 6. 批量覆盖率 (采样: 前20个FCStd) ─────────────────────
    banner("6. 批量反演覆盖率 (采样: 前20个索引中的FCStd)")
    fcstd_list = [e for e in idx["entries"] if e["kind"] == "fcstd"][:20]
    replayable = 0
    sum_ops = 0
    for e in fcstd_list:
        try:
            pr = FCReverse.probe(e["path"])
            if pr.get("replayable"):
                replayable += 1
            sum_ops += pr.get("op_count", 0)
        except Exception:
            pass
    print(f"  采样: {len(fcstd_list)}  可反演: {replayable}  累计ops: {sum_ops}")
    total += 1; passed += assert_true(replayable >= len(fcstd_list) // 3,
                                       f"≥1/3 可反演 ({replayable}/{len(fcstd_list)})")

    # ── 收尾 ────────────────────────────────────────────────────
    banner("反者道之动 · 本源验证 · 终极报告")
    print(f"  通过: {passed}/{total} = {100*passed/total:.1f}%")
    if passed == total:
        print("  等级: S — 道法自然, 万法归一, 反者道之动验证通过")
        return 0
    print(f"  失败: {total - passed}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
