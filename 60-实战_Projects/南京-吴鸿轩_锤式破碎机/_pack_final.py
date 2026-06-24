#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
_pack_final.py — 道法自然 · 整理所有成果, 输出最终 ZIP 包

使用:
    python _pack_final.py             # 默认输出到上一级目录
    python _pack_final.py --here      # 输出到本目录

哲学: 无为而无不为 · 不动现状 (源文件全留), 唯于本目录之外凝结一 ZIP.

排除规则 (噪音, 可再生, 锁文件):
  · _archive/                  ← 510 项历史归档 (146.5 MB, 纯过程产物)
  · __pycache__/  .pytest_cache/  ← Python 字节码缓存
  · ~$*.SLDPRT/SLDASM          ← SolidWorks 打开锁文件
  · sw_api/gen/                ← win32com 类型库绑定 (~7 MB, 可重生)
  · sw_api/INDEX.json          ← 类型库索引 (~3 MB, 可重生)
  · _pack_final.py             ← 本脚本本身
  · *.zip                      ← 历史 zip 产物

结构: ZIP 内顶层 = `南京-吴鸿轩_锤式破碎机/` (解压后即得完整可运行项目).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_NAME = ROOT.name  # 南京-吴鸿轩_锤式破碎机

# ── 排除规则 ──────────────────────────────────────────────
EXCLUDE_DIR_NAMES = {"_archive", "__pycache__", ".pytest_cache", "gen"}
EXCLUDE_REL_DIRS = {Path("sw_api/gen")}
EXCLUDE_REL_FILES = {Path("sw_api/INDEX.json"), Path("_pack_final.py")}


def is_excluded(rel: Path) -> bool:
    """判断相对路径是否应排除. rel 是 ROOT 下的相对路径."""
    parts = set(rel.parts)
    # 任一目录组件命中黑名单
    if parts & EXCLUDE_DIR_NAMES:
        return True
    # 整路径命中
    if rel in EXCLUDE_REL_FILES or rel in EXCLUDE_REL_DIRS:
        return True
    # 子路径前缀命中
    for d in EXCLUDE_REL_DIRS:
        try:
            rel.relative_to(d)
            return True
        except ValueError:
            pass
    name = rel.name
    # SW 锁文件
    if name.startswith("~$"):
        return True
    # zip 自身循环
    if name.endswith(".zip"):
        return True
    # Python 字节码
    if name.endswith(".pyc"):
        return True
    return False


def collect_files() -> list[Path]:
    files: list[Path] = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if is_excluded(rel):
            continue
        files.append(p)
    return sorted(files)


def fmt_size(n: int) -> str:
    units = ("B", "KB", "MB", "GB")
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.2f}{u}"
        f /= 1024
    return f"{n}B"


def sha256sum(p: Path, buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while chunk := fh.read(buf):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--here",
        action="store_true",
        help="输出到本目录 (默认输出到父目录, 避免污染源)",
    )
    ap.add_argument("--name", default=None, help="自定义 ZIP 文件名 (不含 .zip)")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = args.name or f"{PROJECT_NAME}_v6.3_FINAL_{ts}"
    out_dir = ROOT if args.here else ROOT.parent
    zip_path = out_dir / f"{base}.zip"

    print(f"[道法自然] 项目根: {ROOT}")
    print(f"[道法自然] 目标 ZIP: {zip_path}")
    print(f"[道法自然] ZIP 内顶层: {PROJECT_NAME}/")

    t0 = time.time()
    files = collect_files()
    total_raw = sum(f.stat().st_size for f in files)
    print(
        f"[道法自然] 待入册: {len(files)} 文件 · 原始合计 {fmt_size(total_raw)}"
    )

    # 写入 ZIP
    inventory: list[dict] = []
    with zipfile.ZipFile(
        zip_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as zf:
        for i, p in enumerate(files, 1):
            rel = p.relative_to(ROOT)
            arc = (Path(PROJECT_NAME) / rel).as_posix()
            zf.write(p, arcname=arc)
            sz = p.stat().st_size
            inventory.append({"path": rel.as_posix(), "size": sz})
            if i % 50 == 0 or i == len(files):
                pct = 100 * i / len(files)
                print(f"  · [{i:4d}/{len(files)}] {pct:5.1f}% · {arc}")

        # 顶层 README 注释 (zip 内 metadata)
        readme = (
            "# 南京-吴鸿轩 锤式破碎机 · 最终交付 ZIP\n\n"
            f"打包时间: {datetime.now().isoformat(timespec='seconds')}\n"
            f"项目版本: v6.3 · 大制不割 · 全链路打通\n"
            f"文件总数: {len(files)}\n"
            f"原始体量: {fmt_size(total_raw)}\n\n"
            "## 解压后入口\n"
            f"- `{PROJECT_NAME}/README.md` · 项目总览\n"
            f"- `{PROJECT_NAME}/MANIFEST.md` · 资产清单\n"
            f"- `{PROJECT_NAME}/CHANGELOG.md` · 演进记录\n"
            f"- `{PROJECT_NAME}/交付包_最终/` · 主交付 (SLDASM/STEP/SLDPRT/工程图/渲染图)\n"
            f"- `{PROJECT_NAME}/dao_full_loop.py` · 五阶段全链路统一入口\n\n"
            "*道法自然 · 万法归宗 · 无为而无不为*\n"
        )
        zf.writestr(f"{PROJECT_NAME}/_PACKAGE_README.txt", readme)
        # 内置清单 (JSON)
        zf.writestr(
            f"{PROJECT_NAME}/_PACKAGE_INVENTORY.json",
            json.dumps(
                {
                    "project": PROJECT_NAME,
                    "version": "v6.3",
                    "packed_at": datetime.now().isoformat(),
                    "file_count": len(files),
                    "total_raw_bytes": total_raw,
                    "files": inventory,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    t1 = time.time()
    zip_size = zip_path.stat().st_size
    ratio = (1 - zip_size / total_raw) * 100 if total_raw else 0.0
    sha = sha256sum(zip_path)

    print()
    print("════════════════════════════════════════════════════════════")
    print(f"  ✅ 打包完成 · 耗时 {t1 - t0:.2f}s")
    print(f"  ZIP : {zip_path}")
    print(f"  大小: {fmt_size(zip_size)} (压缩率 {ratio:.1f}%)")
    print(f"  SHA-256: {sha}")
    print("════════════════════════════════════════════════════════════")
    print()
    print("解压验证:")
    print(f"  Expand-Archive -Path '{zip_path}' -DestinationPath . -Force")
    return 0


if __name__ == "__main__":
    sys.exit(main())
