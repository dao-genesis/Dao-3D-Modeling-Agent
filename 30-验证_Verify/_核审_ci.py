#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核·审 CI 门 — dao_kernel 全项自验 + dao_audit 八层审核最小闭环.

冷启动依赖: pip install cadquery-ocp trimesh numpy
用法: python 30-验证_Verify/_核审_ci.py   (任一项不达标即非零退出)
"""
import sys
from pathlib import Path

_DAO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / '_paths.py').is_file())
sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401

import dao_kernel  # noqa: E402
from dao_kernel import DaoKernel  # noqa: E402
import dao_audit  # noqa: E402


def main() -> int:
    failures = []

    # ── 门 A · 内核全项自验 ──────────────────────────────
    res = dao_kernel._verify_all()
    passed = res.get("passed", 0)
    failed = res.get("failed", 0)
    print(f"[核] kernel verify: {passed} passed / {failed} failed")
    if failed:
        failures.append(f"kernel verify failed={failed}")

    # ── 门 B · 八层审核最小闭环 (box→audit 必达 A) ─────────
    sh = DaoKernel.box(30, 20, 10)
    r = dao_audit.full_audit(sh)
    grade, score = r.get("grade"), r.get("score")
    print(f"[审] full_audit(box): grade={grade} score={score}")
    if grade not in ("S", "A"):
        failures.append(f"audit grade {grade} < A")

    # ── 门 C · 布尔+修饰后仍可审 ───────────────────────────
    tool = DaoKernel.translate(DaoKernel.cylinder(5, 40), (15, 10, -5))
    cut = DaoKernel.cut(sh, tool)
    r2 = dao_audit.full_audit(cut)
    print(f"[审] full_audit(box-cut-cyl): grade={r2.get('grade')} score={r2.get('score')}")
    if r2.get("grade") not in ("S", "A", "B"):
        failures.append(f"cut audit grade {r2.get('grade')} < B")

    if failures:
        print("核审门 FAIL:", "; ".join(failures))
        return 1
    print("核审门 PASS · 道法自然")
    return 0


if __name__ == "__main__":
    sys.exit(main())
