"""Minimal MCP (Model Context Protocol) server over stdio.

Exposes the whole CAD tool surface to any MCP client (Devin/Cascade, Claude
Desktop, Cursor, a cloud agent) as discoverable, callable tools — no
third-party MCP SDK needed, just JSON-RPC 2.0 framed one object per line on
stdin/stdout.

Two backends, one protocol:

* **Live bridge proxy (preferred)** — when the GUI bridge (:18920) is up, the
  tool list comes from its ``/toolspec`` (the complete, self-described op
  surface) and calls go to ``/tool``, so MCP clients drive the *same live
  document* the human sees in FreeCAD. ``DAO_BRIDGE_URL`` overrides the base.
* **Resident kernel (fallback)** — headless freecadcmd registry, used when no
  bridge is reachable (or ``DAO_MOCK=1`` for a FreeCAD-free mock).

MCP tool names must match ``[a-zA-Z0-9_-]``, so ``solid.box`` is published as
``solid_box``; both spellings are accepted on call.

Run:  python -m cad_agent.mcp_server          # bridge proxy or live kernel
      DAO_MOCK=1 python -m cad_agent.mcp_server  # FreeCAD-free mock
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any, Dict, Optional

PROTOCOL_VERSION = "2024-11-05"


def _bridge_base() -> str:
    return os.environ.get("DAO_BRIDGE_URL") or "http://127.0.0.1:%s" % (
        os.environ.get("FC_REMOTE_PORT") or "18920")


class BridgeProxy:
    """Registry-shaped adapter over the live GUI bridge (/toolspec + /tool)."""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    @classmethod
    def probe(cls, base: str) -> Optional["BridgeProxy"]:
        try:
            with urllib.request.urlopen(base.rstrip("/") + "/status",
                                        timeout=3) as r:
                if json.load(r).get("ok"):
                    return cls(base)
        except Exception:
            pass
        return None

    def manifest(self):
        with urllib.request.urlopen(self.base + "/toolspec", timeout=60) as r:
            cat = json.load(r)
        tools = []
        for grp in cat.get("groups") or []:
            for t in grp.get("tools") or []:
                tools.append({"name": t["name"],
                              "summary": t.get("description") or t["name"],
                              "schema": t.get("parameters") or {}})
        return tools

    def call(self, op: str, args: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps({"op": op, "args": args or {}}).encode()
        req = urllib.request.Request(
            self.base + "/tool", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)


def _build_kernel_registry():
    if os.environ.get("DAO_MOCK") == "1":
        from .backends.mock_backend import build_mock_registry
        return build_mock_registry()
    from . import build_freecad_registry
    return build_freecad_registry()


def _mcp_name(op: str) -> str:
    return op.replace(".", "_")


def _tool_to_mcp(t: Dict[str, Any]) -> Dict[str, Any]:
    schema = t.get("schema") or {}
    if "type" not in schema:
        schema = {"type": "object", "properties": schema.get("properties", {}),
                  "additionalProperties": True}
    return {"name": _mcp_name(t["name"]),
            "description": t.get("summary") or t["name"],
            "inputSchema": schema}


class MCPServer:
    def __init__(self, backend=None) -> None:
        self.initialized = False
        self._backend = backend
        self._names: Dict[str, str] = {}  # mcp name -> op

    def backend(self):
        if self._backend is None:
            self._backend = (BridgeProxy.probe(_bridge_base())
                             if os.environ.get("DAO_MOCK") != "1" else None)
            if self._backend is None:
                self._backend = _build_kernel_registry()
        return self._backend

    def _tools(self):
        tools = []
        for t in self.backend().manifest():
            self._names[_mcp_name(t["name"])] = t["name"]
            tools.append(_tool_to_mcp(t))
        return tools

    def handle(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = req.get("method")
        rid = req.get("id")
        params = req.get("params") or {}
        if method == "initialize":
            return self._ok(rid, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "dao-freecad-agent", "version": "2.0.0"},
            })
        if method == "notifications/initialized":
            self.initialized = True
            return None
        if method == "tools/list":
            try:
                return self._ok(rid, {"tools": self._tools()})
            except Exception as exc:
                return self._err(rid, -32000, "tool listing failed: %s" % exc)
        if method == "tools/call":
            name = params.get("name") or ""
            if name in self._names:
                op = self._names[name]
            elif "." in name:
                op = name
            else:
                op = name.replace("_", ".", 1)
            args = params.get("arguments") or {}
            try:
                result = self.backend().call(op, args)
            except Exception as exc:
                return self._ok(rid, {
                    "content": [{"type": "text",
                                 "text": json.dumps({"ok": False,
                                                     "error": str(exc)},
                                                    ensure_ascii=False)}],
                    "isError": True,
                })
            if hasattr(result, "to_dict"):
                result = result.to_dict()
            payload = json.dumps(result, ensure_ascii=False, indent=2)
            return self._ok(rid, {
                "content": [{"type": "text", "text": payload}],
                "isError": not result.get("ok", True),
            })
        if method == "ping":
            return self._ok(rid, {})
        return self._err(rid, -32601, "method not found: %s" % method)

    @staticmethod
    def _ok(rid: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    @staticmethod
    def _err(rid: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def main() -> None:
    server = MCPServer()  # backend resolved lazily: bridge proxy, else kernel
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = server.handle(req)
        if resp is not None:
            out.write(json.dumps(resp, ensure_ascii=False) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
