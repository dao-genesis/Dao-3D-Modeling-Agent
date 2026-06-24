#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_fc_direct_client.py · 直连 FreeCAD 远程服务器的最薄客户端
════════════════════════════════════════════════════════════════════
道直连器 · 无可无不可 · 让 Cascade 直接控 FreeCAD.

使用:
  python _fc_direct_client.py status
  python _fc_direct_client.py doc
  python _fc_direct_client.py exec <py_code_or_@file.py>
  python _fc_direct_client.py screenshot out.png
  python _fc_direct_client.py view iso|front|top|right|fit
  python _fc_direct_client.py --raw GET /status
  python _fc_direct_client.py --raw POST /exec '{"code":"..."}'

作为库:
  from _fc_direct_client import FC
  fc = FC()
  fc.status()
  fc.exec_py("import FreeCAD; print(FreeCAD.ActiveDocument)")
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_BASE = "http://127.0.0.1:18920"


class FC:
    """最薄的 FreeCAD 远程客户端 (仅 urllib)."""

    def __init__(self, base: str = DEFAULT_BASE, timeout: float = 30.0):
        self.base = base.rstrip("/")
        self.timeout = timeout

    # ── HTTP primitives ──────────────────────────────────────────────
    def _get(self, path: str) -> Dict[str, Any]:
        req = urllib.request.Request(self.base + path, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=data, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    # ── Convenience ──────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:         return self._get("/status")
    def document(self) -> Dict[str, Any]:       return self._get("/document")
    def documents(self) -> Dict[str, Any]:      return self._get("/documents")
    def selection(self) -> Dict[str, Any]:      return self._get("/selection")
    def commands(self) -> Dict[str, Any]:       return self._get("/commands")
    def screenshot_b64(self) -> Dict[str, Any]: return self._get("/screenshot")

    def exec_py(self, code: str, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Run Python in FC GUI main thread. Code should set __result__ for return value."""
        t = timeout if timeout is not None else self.timeout
        # Temporarily bump timeout for heavy ops
        old_t = self.timeout
        self.timeout = t
        try:
            return self._post("/exec", {"code": code})
        finally:
            self.timeout = old_t

    # View action shortcuts (iso → isometric per server VIEW_ACTIONS map)
    _VIEW_ALIASES = {
        "iso": "isometric", "axonometric": "isometric",
        "fit": "fit_all", "all": "fit_all",
    }

    def view(self, action: str) -> Dict[str, Any]:
        """action: isometric|front|rear|top|bottom|left|right|home|fit_all"""
        a = self._VIEW_ALIASES.get(action, action)
        return self._post("/view", {"action": a})

    def run_command(self, command: str) -> Dict[str, Any]:
        return self._post("/run_command", {"command": command})

    def create_object(self, type_id: str, name: str, props: Dict[str, Any] | None = None,
                      doc: Optional[str] = None) -> Dict[str, Any]:
        payload = {"type": type_id, "name": name, "props": props or {}}
        if doc:
            payload["doc"] = doc
        return self._post("/create_object", payload)

    def export(self, format_: str, out_path: str,
               doc: Optional[str] = None, obj: Optional[str] = None) -> Dict[str, Any]:
        payload = {"format": format_, "path": out_path}
        if doc: payload["doc"] = doc
        if obj: payload["obj"] = obj
        return self._post("/export", payload)

    def screenshot_to(self, out_path: str) -> Path:
        """Take a screenshot and save to out_path. Returns the path."""
        import base64
        r = self.screenshot_b64()
        if not r.get("ok"):
            raise RuntimeError(f"screenshot failed: {r}")
        # Server returns key "data" (see _handle_screenshot in _fc_remote_server.py)
        b64 = r.get("data") or r.get("image_base64")
        if not b64:
            raise RuntimeError(f"screenshot has no image data: keys={list(r)}")
        data = base64.b64decode(b64)
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

    if not argv:
        print(__doc__); return 1

    fc = FC()

    if argv[0] == "--raw":
        method, path = argv[1].upper(), argv[2]
        if method == "GET":
            _print_json(fc._get(path)); return 0
        if method == "POST":
            body = json.loads(argv[3]) if len(argv) > 3 else {}
            _print_json(fc._post(path, body)); return 0
        print(f"Unknown method: {method}"); return 2

    cmd, rest = argv[0], argv[1:]

    if cmd == "status":
        _print_json(fc.status()); return 0
    if cmd == "doc" or cmd == "document":
        _print_json(fc.document()); return 0
    if cmd == "docs" or cmd == "documents":
        _print_json(fc.documents()); return 0
    if cmd == "selection":
        _print_json(fc.selection()); return 0
    if cmd == "commands":
        _print_json(fc.commands()); return 0
    if cmd == "view":
        action = rest[0] if rest else "fit_all"
        _print_json(fc.view(action)); return 0
    if cmd == "screenshot":
        out = rest[0] if rest else "_fc_screenshot.png"
        p = fc.screenshot_to(out)
        print(f"Saved: {p}  ({p.stat().st_size//1024}KB)"); return 0
    if cmd == "exec":
        if not rest:
            print("usage: exec <code_or_@file.py>"); return 2
        code_arg = rest[0]
        if code_arg.startswith("@"):
            code = Path(code_arg[1:]).read_text(encoding="utf-8")
        else:
            code = code_arg
        _print_json(fc.exec_py(code, timeout=120.0))
        return 0

    print(f"Unknown command: {cmd}"); return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
