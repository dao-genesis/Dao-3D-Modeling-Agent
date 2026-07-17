# -*- coding: utf-8 -*-
"""单源消漂移: 内嵌 dao 运行时副本与仓库正源的一致性闸门/同步器.

正源 → 内嵌副本 (构建期复制, 手工再也不用 cp):
  cad_agent/            → 90-归一_IDE/vscode-dao-freecad/dao/cad_agent/    (全树)
  freecad/DAO/          → 90-归一_IDE/vscode-dao-freecad/dao/freecad/DAO/  (全树)
  10-反笙_FreeCAD/*.py  → 90-归一_IDE/vscode-dao-freecad/tools/            (内嵌已收录子集)
  00-本源_Origin/*.py   → 90-归一_IDE/vscode-dao-freecad/dao/00-本源_Origin/ (内嵌已收录子集)

用法:
  python scripts/sync_embedded.py --check   # CI 闸门: 漂移即退出 1 并列出差异
  python scripts/sync_embedded.py --sync    # 正源覆写内嵌副本
"""
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDE_DAO = ROOT / "90-归一_IDE" / "vscode-dao-freecad" / "dao"

IGNORE = {"__pycache__", ".pytest_cache", "README.md"}


def _tree_files(base: Path):
    for p in sorted(base.rglob("*")):
        if p.is_file() and not (set(p.relative_to(base).parts) & IGNORE):
            yield p.relative_to(base)


def _pairs():
    """(正源文件, 内嵌副本文件) 清单."""
    out = []
    # 全树镜像: 正源目录整体对应内嵌目录
    for src_dir, dst_dir in (
        (ROOT / "cad_agent", IDE_DAO / "cad_agent"),
        (ROOT / "freecad" / "DAO", IDE_DAO / "freecad" / "DAO"),
    ):
        for rel in _tree_files(src_dir):
            out.append((src_dir / rel, dst_dir / rel))
    # 子集镜像: 只同步内嵌侧已收录的同名文件 (插件自包含子集)
    for src_dir, dst_dir in (
        (ROOT / "10-反笙_FreeCAD", ROOT / "90-归一_IDE" / "vscode-dao-freecad" / "tools"),
        (ROOT / "00-本源_Origin", IDE_DAO / "00-本源_Origin"),
    ):
        if dst_dir.is_dir():
            for dst in sorted(dst_dir.glob("*.py")):
                src = src_dir / dst.name
                if src.is_file():
                    out.append((src, dst))
    return out


def check() -> int:
    drift = []
    for src, dst in _pairs():
        if not dst.is_file():
            drift.append(f"MISSING  {dst.relative_to(ROOT)}")
        elif not filecmp.cmp(src, dst, shallow=False):
            drift.append(f"DIFFERS  {dst.relative_to(ROOT)}  (源: {src.relative_to(ROOT)})")
    if drift:
        print("内嵌副本漂移 (运行 python scripts/sync_embedded.py --sync 校正):")
        print("\n".join("  " + d for d in drift))
        return 1
    print(f"单源一致: {len(_pairs())} 个内嵌副本与正源零漂移")
    return 0


def sync() -> int:
    n = 0
    for src, dst in _pairs():
        if not dst.is_file() or not filecmp.cmp(src, dst, shallow=False):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"sync {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")
            n += 1
    print(f"已同步 {n} 个文件")
    return 0


if __name__ == "__main__":
    if "--sync" in sys.argv:
        sys.exit(sync())
    sys.exit(check())
