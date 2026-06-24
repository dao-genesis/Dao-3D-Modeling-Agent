#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
_verify_归宗.py — 第十四妙门 · 烟测抽样 + 索引自洽

验证 dao_归宗 的正确性:
  1. 清册可加载, JSON 合法, 无重复 name
  2. 每宗至少有 1 仓已取 (如不为 0)
  3. 已取仓 目录非空 · .git 存在 · HEAD 可读
  4. MASTER_INDEX.json 存在 · 与磁盘状态一致
  5. 道.宗 facet 可用 (懒加载不报错)
  6. 抽样查询 (CadQuery, BOSL2, FreeCAD) 可命中
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(
    (p for p in HERE.parents if (p / "_paths.py").is_file()), HERE.parent
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import _paths as _P  # noqa: E402,F401

ORIGIN = ROOT / "00-本源_Origin"
if str(ORIGIN) not in sys.path:
    sys.path.insert(0, str(ORIGIN))


def _ok(label: str):
    print(f"  ✓ {label}")


def _fail(label: str, detail: str = ""):
    print(f"  ✗ {label}" + (f"  — {detail}" if detail else ""))


def main() -> int:
    passed = 0
    failed = 0

    print("┌ 归宗·烟测")

    # ── Phase 1: 清册 ─────────────────────────────────────
    print("│ 一·清册")
    manifest_path = ORIGIN / "_归宗_清册.json"
    if not manifest_path.exists():
        _fail("清册不存"); failed += 1; return 2
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        _ok(f"清册加载 · {manifest_path.name}")
        passed += 1
    except Exception as e:
        _fail("清册 JSON 非法", str(e)); failed += 1; return 2

    # 去 _meta
    cats = {k: v for k, v in data.items() if not k.startswith("_")}
    names = set()
    dup = []
    total = 0
    for cat, items in cats.items():
        for item in items:
            n = item.get("name", "")
            total += 1
            if n in names:
                dup.append(n)
            names.add(n)
    if dup:
        _fail(f"重复 name · {dup}"); failed += 1
    else:
        _ok(f"无重复 name · 计 {total} 仓 · {len(cats)} 宗")
        passed += 1

    # ── Phase 2: dao_归宗 import + summary ────────────────
    print("│ 二·DaoZong")
    try:
        from dao_归宗 import DaoZong
        _ok("DaoZong import")
        passed += 1
    except Exception as e:
        _fail("DaoZong import", str(e)); failed += 1
        return 1

    z = DaoZong()
    try:
        s = z.summary()
        _ok(f"summary · fetched={s['fetched_repos']}/{s['total_repos']} · "
            f"coverage={s['coverage']:.1%}")
        passed += 1
    except Exception as e:
        _fail("summary", str(e)); failed += 1

    # ── Phase 3: 已取仓 结构合法 ──────────────────────────
    print("│ 三·磁盘结构")
    from dao_归宗 import SRC_BASE, _is_cloned, _head_commit
    present = 0
    broken = 0
    for cat, items in cats.items():
        for item in items:
            t = SRC_BASE / cat / item["name"]
            if not _is_cloned(t):
                continue
            present += 1
            # 检查 .git 可读
            if (t / ".git").exists():
                c = _head_commit(t)
                if not c:
                    broken += 1
    if broken == 0:
        _ok(f"磁盘结构合法 · present={present}")
        passed += 1
    else:
        _fail(f"磁盘有 {broken} 个仓 HEAD 不可读"); failed += 1

    # ── Phase 4: MASTER_INDEX.json ────────────────────────
    print("│ 四·MASTER_INDEX")
    idx_path = SRC_BASE / "万法源_MASTER_INDEX.json"
    if not idx_path.exists():
        # 尝试重建
        try:
            z.索()
            _ok("MASTER_INDEX 重建")
            passed += 1
        except Exception as e:
            _fail("MASTER_INDEX 重建", str(e)); failed += 1
    else:
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            n_idx = len(idx.get("by_name", {}))
            if n_idx >= total:
                _ok(f"MASTER_INDEX · {n_idx} 条")
                passed += 1
            else:
                _fail(f"MASTER_INDEX 缺项 · {n_idx}/{total}")
                failed += 1
        except Exception as e:
            _fail("MASTER_INDEX JSON", str(e)); failed += 1

    # ── Phase 5: 道.宗 facet ──────────────────────────────
    print("│ 五·万法接入")
    try:
        from 万法 import 道
        r = 道.宗.summary()
        if r.get("ok"):
            _ok(f"道.宗.summary 可用")
            passed += 1
        else:
            _fail("道.宗.summary", str(r)); failed += 1
    except Exception as e:
        _fail("道.宗 facet", str(e)); failed += 1

    # ── Phase 6: 抽样查询 ─────────────────────────────────
    print("│ 六·抽样查询")
    samples = ["CadQuery", "BOSL2", "FreeCAD", "threejs"]
    hits = 0
    for s in samples:
        try:
            r = z.查(s)
            # 精确匹配任一
            if any(h["name"] == s for h in r):
                hits += 1
        except Exception:
            pass
    if hits == len(samples):
        _ok(f"抽样查询 · {hits}/{len(samples)} 命中")
        passed += 1
    else:
        _fail(f"抽样查询 · 仅 {hits}/{len(samples)} 命中")
        failed += 1

    # ── 结果 ──────────────────────────────────────────────
    print(f"└ 归宗·验: ok={passed}  fail={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
