#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools.py — 通用 CAD 工具协议 · "MCP-for-CAD" 本源
═══════════════════════════════════════════════════════════════════════════════
反者道之动 — 不为某个 CAD 软件写死流程, 而先立一套 *引擎无关* 的工具契约,
让任何后端 (mesh / FreeCAD / SolidWorks…) 以同一份 JSON schema 暴露能力.

与 AI 编程的同构对照:
    代码 agent: read_file / write_file / edit / run / grep   (对 *文本工作区* 的标准动作)
    CAD  agent: create / transform / boolean / measure / perceive / export
                                                        (对 *几何工作区* 的标准动作)

三个抽象:
    · Tool          —— 一个带 JSON schema 的可调用能力 (名/描述/参/返回/处理函数)
    · Workspace     —— 几何工作区 (具名对象表 = "文档/场景"), 工具的操作对象
    · ToolRegistry  —— 工具登记处; 统一 call(name, args) → 结构化结果 + 错误归一

后端通过 register_*_tools(registry) 把自己的能力注入同一 registry;
agent / MCP server 只面向 registry, 不关心底层引擎. 此即 "万法归一" 在工具层的落地.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np

__all__ = [
    "ToolParam", "Tool", "ToolResult", "Workspace", "ToolRegistry",
]


# ═══════════════════════════════════════════════════════════════════════════
# 一、工具签名 (JSON-schema 友好)
# ═══════════════════════════════════════════════════════════════════════════
_JSON_TYPES = {"string", "number", "integer", "boolean", "array", "object"}


@dataclass
class ToolParam:
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None

    def json_schema(self) -> Dict[str, Any]:
        t = self.type if self.type in _JSON_TYPES else "string"
        s: Dict[str, Any] = {"type": t, "description": self.description}
        if not self.required and self.default is not None:
            s["default"] = self.default
        return s


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[["Workspace", Dict[str, Any]], Dict[str, Any]]
    params: List[ToolParam] = field(default_factory=list)
    category: str = "general"
    mutates: bool = False  # 是否改变工作区状态 (用于历史/撤销/感知触发)

    def json_schema(self) -> Dict[str, Any]:
        """MCP/OpenAI 兼容的工具声明."""
        props = {p.name: p.json_schema() for p in self.params}
        required = [p.name for p in self.params if p.required]
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "mutates": self.mutates,
            "inputSchema": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        }

    def validate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """校验/补默认值; 缺必填则抛 ValueError."""
        out: Dict[str, Any] = {}
        for p in self.params:
            if p.name in args and args[p.name] is not None:
                out[p.name] = args[p.name]
            elif p.required:
                raise ValueError(f"缺少必填参数 '{p.name}'")
            else:
                out[p.name] = p.default
        return out


@dataclass
class ToolResult:
    ok: bool
    tool: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = {"ok": self.ok, "tool": self.tool, "elapsed_ms": round(self.elapsed_ms, 2)}
        if self.ok:
            d["data"] = self.data
        else:
            d["error"] = self.error
        return d


# ═══════════════════════════════════════════════════════════════════════════
# 二、几何工作区 · 具名对象表 (= 文档 / 场景)
# ═══════════════════════════════════════════════════════════════════════════
class Workspace:
    """AI 操作的 "几何文档": 一组具名几何对象 + 自增命名.

    对象统一以 (vertices, faces) 形式存放 (引擎无关); 各后端负责与自身原生
    表示互转. 这与代码 agent 的 "文件树工作区" 同构 —— 此处对象即 "文件"."""

    def __init__(self, name: str = "workspace") -> None:
        self.name = name
        self._objs: Dict[str, Dict[str, Any]] = {}
        self._counter: Dict[str, int] = {}

    # —— 命名 ——
    def fresh_name(self, prefix: str) -> str:
        self._counter[prefix] = self._counter.get(prefix, 0) + 1
        cand = f"{prefix}{self._counter[prefix]}"
        while cand in self._objs:
            self._counter[prefix] += 1
            cand = f"{prefix}{self._counter[prefix]}"
        return cand

    # —— 存取 ——
    def put(self, name: str, vertices: np.ndarray, faces: np.ndarray,
            meta: Optional[Dict[str, Any]] = None) -> str:
        self._objs[name] = {
            "vertices": np.asarray(vertices, float),
            "faces": np.asarray(faces, int),
            "meta": meta or {},
        }
        return name

    def get(self, name: str) -> Dict[str, Any]:
        if name not in self._objs:
            raise KeyError(f"对象 '{name}' 不存在; 现有: {self.names()}")
        return self._objs[name]

    def has(self, name: str) -> bool:
        return name in self._objs

    def delete(self, name: str) -> None:
        self.get(name)
        del self._objs[name]

    def rename(self, old: str, new: str) -> None:
        obj = self.get(old)
        if new in self._objs:
            raise ValueError(f"目标名 '{new}' 已存在")
        self._objs[new] = obj
        del self._objs[old]

    def names(self) -> List[str]:
        return list(self._objs.keys())

    def __len__(self) -> int:
        return len(self._objs)

    def snapshot(self) -> Dict[str, Any]:
        """轻量状态快照 (供撤销/对比); 深拷贝几何数组."""
        return {
            n: {
                "vertices": o["vertices"].copy(),
                "faces": o["faces"].copy(),
                "meta": dict(o["meta"]),
            }
            for n, o in self._objs.items()
        }

    def restore(self, snap: Dict[str, Any]) -> None:
        self._objs = {
            n: {
                "vertices": o["vertices"].copy(),
                "faces": o["faces"].copy(),
                "meta": dict(o["meta"]),
            }
            for n, o in snap.items()
        }


# ═══════════════════════════════════════════════════════════════════════════
# 三、工具登记处 · 统一调用面
# ═══════════════════════════════════════════════════════════════════════════
class ToolRegistry:
    """所有后端工具的统一登记与调用入口."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具 '{tool.name}' 已登记")
        self._tools[tool.name] = tool

    def add(self, name: str, description: str,
            handler: Callable[["Workspace", Dict[str, Any]], Dict[str, Any]],
            params: Optional[List[ToolParam]] = None,
            category: str = "general", mutates: bool = False) -> Tool:
        t = Tool(name=name, description=description, handler=handler,
                 params=params or [], category=category, mutates=mutates)
        self.register(t)
        return t

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"未知工具 '{name}'")
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> List[str]:
        return sorted(self._tools.keys())

    def schemas(self) -> List[Dict[str, Any]]:
        return [self._tools[n].json_schema() for n in self.names()]

    def call(self, name: str, args: Optional[Dict[str, Any]],
             workspace: Workspace) -> ToolResult:
        """调用一个工具; 所有异常归一为 ToolResult.error (永不外泄栈到调用方)."""
        t0 = time.time()
        if name not in self._tools:
            return ToolResult(False, name, error=f"未知工具 '{name}'",
                              elapsed_ms=(time.time() - t0) * 1000)
        tool = self._tools[name]
        try:
            clean = tool.validate(args or {})
            data = tool.handler(workspace, clean)
            if not isinstance(data, dict):
                data = {"result": data}
            return ToolResult(True, name, data=data,
                              elapsed_ms=(time.time() - t0) * 1000)
        except Exception as e:  # noqa: BLE001 — 边界归一
            return ToolResult(False, name,
                              error=f"{type(e).__name__}: {e}",
                              data={"trace": traceback.format_exc(limit=3)},
                              elapsed_ms=(time.time() - t0) * 1000)
