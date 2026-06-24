#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_paths.py — 3D建模Agent 路径引导 · 万法归一
══════════════════════════════════════════════════════════════════
道法自然 · 生生不息 · 万物并育而不相害

任何脚本 (无论根目录或子目录) 只需:

    import _paths  # noqa

即可访问五层所有模块:

  00-本源_Origin   → dao_kernel, dao_audit, dao_engine, dao_forge,
                     dao_reverse, 资源探针
  10-反笙_FreeCAD  → fc_reverse, fc_show, fc_model_builder,
                     freecad_backend/bridge/connection,
                     freecad_gui_launcher/macro, _fc_remote_server
  20-万法_Forge    → forge_v3, model_hub, parametric_codegen,
                     design_intent_compiler, geometric_preflight,
                     _playwright_scrapers
  30-验证_Verify   → _test_*, _verify_*, _e2e_*, _run_*, _audit_*,
                     _bench_*, _demo_*, _fc_probe, _本源_verify,
                     _万法归一_build

路径引导通过搜索 `_paths.py` 上行定位 ROOT, 对任何位置均有效.

同时暴露:
  ROOT       — 3D建模Agent 根绝对路径 (Path)
  LAYER_DIRS — 五层目录名字典
  ORIGIN     — 00-本源_Origin 路径
  REVERSE    — 10-反笙_FreeCAD 路径
  FORGE      — 20-万法_Forge 路径
  VERIFY     — 30-验证_Verify 路径
  TEMPLATES  — 40-模板_Templates 路径
  DEMO       — 50-演示_Demo 路径
  PROJECTS   — 60-实战_Projects 路径 (原 projects/ + solidwork建模)
  WORLD      — 70-天下_World 路径 (原 网络资源库/ + downloads + .resource_cache)
  LOGS       — 90-日志_Logs 路径
"""
from __future__ import annotations

import sys
from pathlib import Path

# ─── 定位 ROOT (搜索含 _paths.py 的最近祖先) ─────────────────────────
_HERE = Path(__file__).resolve().parent
ROOT: Path = _HERE  # _paths.py 永远位于 ROOT

# ─── 五层目录 (按序) ──────────────────────────────────────────────────
LAYER_DIRS = {
    "origin":    "00-本源_Origin",
    "reverse":   "10-反笙_FreeCAD",
    "forge":     "20-万法_Forge",
    "verify":    "30-验证_Verify",
    "templates": "40-模板_Templates",
    "demo":      "50-演示_Demo",
    "projects":  "60-实战_Projects",
    "world":     "70-天下_World",
    "logs":      "90-日志_Logs",
}

ORIGIN    = ROOT / LAYER_DIRS["origin"]
REVERSE   = ROOT / LAYER_DIRS["reverse"]
FORGE     = ROOT / LAYER_DIRS["forge"]
VERIFY    = ROOT / LAYER_DIRS["verify"]
TEMPLATES = ROOT / LAYER_DIRS["templates"]
DEMO      = ROOT / LAYER_DIRS["demo"]
PROJECTS  = ROOT / LAYER_DIRS["projects"]
WORLD     = ROOT / LAYER_DIRS["world"]
LOGS      = ROOT / LAYER_DIRS["logs"]

# 兼容层: 原始扁平路径 → 新分层位置
# 保留旧属性名, 使老代码 SCRIPT_DIR / "projects" 的语义仍可定位
LEGACY_ALIAS = {
    "projects":      PROJECTS,           # 旧 SCRIPT_DIR / "projects" → 60-实战_Projects
    "demo":          DEMO,               # 旧 SCRIPT_DIR / "demo"
    "templates":     TEMPLATES,          # 旧 SCRIPT_DIR / "templates"
    "网络资源库":    WORLD / "网络资源库",
    "downloads":     WORLD / "downloads",
    ".resource_cache": WORLD / ".resource_cache",
}

# ─── 注册到 sys.path (幂等, 只插入一次) ───────────────────────────────
_REGISTERED_FLAG = "_DAO_PATHS_REGISTERED"
if not getattr(sys, _REGISTERED_FLAG, False):
    for _sub in (ORIGIN, REVERSE, FORGE, VERIFY):
        _s = str(_sub)
        if _sub.exists() and _s not in sys.path:
            sys.path.insert(0, _s)
    # 根也注册, 以便脚本 `import _paths` 时可找到同级模块
    _r = str(ROOT)
    if _r not in sys.path:
        sys.path.insert(0, _r)
    setattr(sys, _REGISTERED_FLAG, True)


def resolve_legacy(name: str) -> Path:
    """将旧路径名 (projects/demo/templates/网络资源库/downloads/.resource_cache)
    映射到新五层位置. 找不到则按 ROOT / name 回退."""
    return LEGACY_ALIAS.get(name, ROOT / name)


def bootstrap(caller_file: str | None = None) -> Path:
    """供任何脚本调用: 确保 sys.path 就绪, 返回 ROOT.
    外部脚本可写:

        from _paths import bootstrap
        ROOT = bootstrap(__file__)
    """
    return ROOT


__all__ = [
    "ROOT", "LAYER_DIRS",
    "ORIGIN", "REVERSE", "FORGE", "VERIFY",
    "TEMPLATES", "DEMO", "PROJECTS", "WORLD", "LOGS",
    "LEGACY_ALIAS", "resolve_legacy", "bootstrap",
]


if __name__ == "__main__":
    import json
    info = {
        "ROOT": str(ROOT),
        "layers": {k: str(ROOT / v) for k, v in LAYER_DIRS.items()},
        "registered_sys_path": [p for p in sys.path if str(ROOT) in p],
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))
