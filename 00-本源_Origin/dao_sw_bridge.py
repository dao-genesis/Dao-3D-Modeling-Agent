#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dao_sw_bridge.py — SolidWorks COM 底层直连桥 · 一站式导入
════════════════════════════════════════════════════════════════════
道法自然 · 无为而无不为

统一导出所有 COM 底层工具, 供下游脚本一行导入:

    from dao_sw_bridge import (
        sw_connect, com_prop, com_call, com_iter_docs, dyn_wrap,
        find_material_db, SolidWorksBridge, SWLive, SWOmni,
    )

核心修复:
  1. _com_prop: property vs method 二义性根治 (callable → try call → fallback)
  2. _dyn_wrap: COM 对象 re-wrap 为 dynamic.Dispatch (绕 gencache 污染)
  3. _com_iter_docs: 安全文档遍历 (不再 doc=doc() 崩溃)
  4. _com_call: 带参数 COM 方法多路回退
  5. _find_sw_material_db: 自动定位材质库完整路径
"""
from __future__ import annotations

from dao_solidworks import (
    # COM 底层工具
    _com_prop      as com_prop,
    _com_call      as com_call,
    _com_iter_docs as com_iter_docs,
    _dyn_wrap      as dyn_wrap,
    _find_sw_material_db as find_material_db,
    # Bridge + Doc
    SolidWorksBridge,
    SWDoc,
    SWComError,
    SW_DOC_TYPE,
    SW_EXPORT_FMT,
    sw_info,
    win32_int,
)

from dao_sw_live import (
    SWLive,
    LiveDoc,
    LiveError,
    # Builders
    SketchBuilder,
    FeatureBuilder,
    AssemblyBuilder,
    DrawingBuilder,
    # Managers
    PropertyMgr,
    EquationMgr,
    MaterialMgr,
    SelectionMgr,
    CommandRunner,
    MacroRunner,
    # Constants
    SW_PLANE,
    SW_VIEW,
    SW_TEMPLATE,
    SW_SEL,
    SW_MATE,
    SW_MATE_ALIGN,
    SW_FEATURE,
    SW_CMD,
)

from dao_sw_omni import SWOmni


def sw_connect(*, visible: bool = True, launch: bool = True) -> SWLive:
    """一键连接 SolidWorks · 返回 SWLive 活体.

    用法:
        live = sw_connect()
        doc = live.active()
        doc.material.set_material("AISI 1020")
    """
    live = SWLive()
    r = live.ensure_live(visible=visible, launch_timeout_s=120.0
                         if launch else 0.0)
    if not r.get("ok"):
        raise LiveError(f"SW 连接失败: {r}")
    return live


__all__ = [
    # 一键连接
    "sw_connect",
    # COM 底层工具
    "com_prop", "com_call", "com_iter_docs", "dyn_wrap",
    "find_material_db",
    # Bridge 层
    "SolidWorksBridge", "SWDoc", "SWComError",
    "SW_DOC_TYPE", "SW_EXPORT_FMT", "sw_info", "win32_int",
    # Live 层
    "SWLive", "LiveDoc", "LiveError",
    "SketchBuilder", "FeatureBuilder", "AssemblyBuilder", "DrawingBuilder",
    "PropertyMgr", "EquationMgr", "MaterialMgr", "SelectionMgr",
    "CommandRunner", "MacroRunner",
    # Constants
    "SW_PLANE", "SW_VIEW", "SW_TEMPLATE", "SW_SEL",
    "SW_MATE", "SW_MATE_ALIGN", "SW_FEATURE", "SW_CMD",
    # Omni 层
    "SWOmni",
]
