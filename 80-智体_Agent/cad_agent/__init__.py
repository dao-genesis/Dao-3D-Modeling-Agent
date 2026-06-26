#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cad_agent — AI + CAD 通用智体本源
═══════════════════════════════════════════════════════════════════════════════
道法自然 · 无为而无不为.

把 "AI 全程参与三维建模" 拆成与 AI 编程同构的三层:
    perception   三维感知   (看见 + 读懂几何)        ← AI 的 "眼"
    tools        工具协议   (引擎无关的标准动作)      ← AI 的 "手" (MCP-for-CAD)
    session      智体会话   (perceive→act→verify 闭环) ← AI 的 "神"

后端 (backends/) 以同一份工具契约接入任意 CAD 引擎; mesh 后端为零外依赖参考实现.
mcp_server 以 stdio JSON-RPC 把工具集暴露给外部驱动器 (Cursor-like).
"""
from __future__ import annotations

__version__ = "0.1.0"


def build_default_registry():
    """构造默认工具登记处 (当前装载 mesh 后端)."""
    from .tools import ToolRegistry
    from .backends import register_mesh_tools
    reg = ToolRegistry()
    register_mesh_tools(reg)
    return reg


def new_session(name: str = "session"):
    """便捷工厂: 建一个装载默认工具集的智体会话."""
    from .session import AgentSession
    return AgentSession(name=name, registry=build_default_registry())


__all__ = ["__version__", "build_default_registry", "new_session"]
