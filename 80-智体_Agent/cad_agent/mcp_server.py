#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp_server.py — 工具集的 stdio JSON-RPC 暴露 · "Cursor-like 外部驱动" 接入点
═══════════════════════════════════════════════════════════════════════════════
反者道之动 — 不把 agent 逻辑锁进某宿主, 而以 *标准 JSON-RPC over stdio* 把整套
CAD 工具暴露出去, 让任何外部驱动器 (IDE 插件 / LLM 运行时 / MCP 客户端) 即插即用.
这正是 AI 编程从 "复制粘贴" 进化到 "MCP 工具" 的同一步, 落到三维领域.

协议 (MCP 精简子集, 行分隔 JSON, 一行一帧):
    → {"jsonrpc":"2.0","id":1,"method":"initialize"}
    ← {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{...},"capabilities":{...}}}
    → {"jsonrpc":"2.0","id":2,"method":"tools/list"}
    ← {"jsonrpc":"2.0","id":2,"result":{"tools":[<schema>...]}}
    → {"jsonrpc":"2.0","id":3,"method":"tools/call",
        "params":{"name":"mesh.box","arguments":{"x":10,"y":10,"z":10}}}
    ← {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":...}],
                                         "structured":{...},"isError":false}}
  附加便捷方法: session/state, session/verify, session/undo, perceive.

跑法 (作为子进程被外部驱动):  python -m cad_agent.mcp_server
                            python "80-智体_Agent/cad_agent/mcp_server.py"
自检 (内置回环, 不走 stdio):  python "...mcp_server.py" --selftest
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

# 允许 `python mcp_server.py` 直接运行 (含中文路径时规避 PYTHONPATH 编码坑)
if __package__ in (None, ""):  # pragma: no cover
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    import cad_agent  # noqa: F401
    from cad_agent.session import AgentSession, Check
    from cad_agent import build_default_registry
else:
    from . import build_default_registry
    from .session import AgentSession, Check

SERVER_INFO = {"name": "dao-cad-agent", "version": "0.1.0"}


class MCPServer:
    """承载一个 AgentSession 的 JSON-RPC 处理器 (传输无关)."""

    def __init__(self, session: Optional[AgentSession] = None) -> None:
        if session is None:
            session = AgentSession("mcp", registry=build_default_registry())
        self.session = session

    # —— 单帧分发 ——
    def handle(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rid = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}
        try:
            result = self._dispatch(method, params)
        except _RpcError as e:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": e.code, "message": e.message}}
        except Exception as e:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        if rid is None:  # 通知, 无需回应
            return None
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def _dispatch(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == "initialize":
            return {"protocolVersion": "2024-11-05",
                    "serverInfo": SERVER_INFO,
                    "capabilities": {"tools": {"listChanged": False}}}
        if method in ("tools/list", "tools.list"):
            return {"tools": self.session.registry.schemas()}
        if method in ("tools/call", "tools.call"):
            name = params.get("name")
            if not name:
                raise _RpcError(-32602, "缺少 params.name")
            args = params.get("arguments") or {}
            res = self.session.act(name, args)
            text = json.dumps(res.to_dict(), ensure_ascii=False)
            return {"content": [{"type": "text", "text": text}],
                    "structured": res.to_dict(),
                    "isError": not res.ok}
        if method == "session/state":
            return self.session.state()
        if method == "session/undo":
            return {"undone": self.session.undo()}
        if method == "session/verify":
            checks = [_check_from_dict(c) for c in params.get("checks", [])]
            vr = self.session.verify(checks)
            return {"ok": vr.ok, "passed": vr.passed, "failed": vr.failed,
                    "results": vr.results, "render": vr.render()}
        if method == "perceive":
            res = self.session.perceive(params["name"],
                                        resolution=params.get("resolution", 192),
                                        out_dir=params.get("out_dir"),
                                        save_png=params.get("save_png", False))
            return res.to_dict()
        raise _RpcError(-32601, f"未知方法 '{method}'")

    # —— stdio 主循环 ——
    def serve_stdio(self, stdin=None, stdout=None) -> None:  # pragma: no cover
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                resp = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "解析错误"}}
                stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                stdout.flush()
                continue
            resp = self.handle(req)
            if resp is not None:
                stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                stdout.flush()


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _check_from_dict(d: Dict[str, Any]) -> Check:
    return Check(kind=d.get("kind", ""), obj=d.get("obj"), other=d.get("other"),
                 axis=d.get("axis"), lo=d.get("lo"), hi=d.get("hi"),
                 value=d.get("value"), label=d.get("label", ""))


def _selftest() -> int:
    """不经 stdio 的回环自检: 走一遍 initialize→list→call→verify."""
    srv = MCPServer()
    ok = True

    def call(method, params=None, rid=1):
        return srv.handle({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})

    r = call("initialize")
    ok &= r["result"]["serverInfo"]["name"] == "dao-cad-agent"
    print("initialize:", r["result"]["serverInfo"])

    r = call("tools/list")
    n = len(r["result"]["tools"])
    ok &= n >= 15
    print("tools/list:", n, "tools")

    r = call("tools/call", {"name": "mesh.box", "arguments": {"x": 20, "y": 20, "z": 20, "name": "b"}})
    ok &= not r["result"]["isError"]
    print("tools/call mesh.box isError:", r["result"]["isError"])

    r = call("perceive", {"name": "b", "resolution": 64})
    ok &= r["result"]["ok"]
    print("perceive summary:", r["result"]["data"]["summary"][:60], "...")

    r = call("session/verify", {"checks": [
        {"kind": "exists", "obj": "b"},
        {"kind": "volume", "obj": "b", "lo": 7000, "hi": 9000},
    ]})
    ok &= r["result"]["ok"]
    print("session/verify:", r["result"]["render"].replace("\n", " | "))

    r = call("nope/method")
    ok &= "error" in r
    print("unknown method → error code:", r["error"]["code"])

    print("SELFTEST:", "✅ PASS" if ok else "❌ FAIL")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    MCPServer().serve_stdio()
