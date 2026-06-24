#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ORS6_Stewart · Cascade ↔ FreeCAD GUI 后端代理 (XML-RPC client).

后端直连 FreeCAD GUI 的 FreeCADMCP RPC server (port 9875),
所有 GUI 操作走主线程任务队列 (rpc_request_queue + QTimer),
用户在 FreeCAD 窗口内实时可见.

API:
    fc = FCClient()                        # localhost:9875
    fc.ping()                              # → True 若 FreeCAD GUI 在
    fc.list_docs()                         # → ['ORS6_home', ...]
    fc.open_pose('home')                   # → 打开 output/ORS6_home.FCStd
    fc.screenshot(view='Isometric')        # → bytes (PNG)
    fc.execute(python_code)                # → {success, message}
    fc.state()                             # → 综合状态 dict
    fc.audit_all_poses()                   # → 5 pose 自检全报告

用法 (CLI):
    python -m ORS6_Stewart.tools.dao_fc ping
    python -m ORS6_Stewart.tools.dao_fc state
    python -m ORS6_Stewart.tools.dao_fc open home
    python -m ORS6_Stewart.tools.dao_fc shoot              # 当前视图截图
    python -m ORS6_Stewart.tools.dao_fc audit              # 5 pose 全自检

道法自然 · 无为而无不为 · 后端直连 GUI 而不再需用户手动操作.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import sys
import time
import xmlrpc.client
from pathlib import Path
from typing import Any

# ── Bootstrap ───────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent           # tools/
PKG = HERE.parent                                 # ORS6_Stewart/
PROJECTS_DIR = PKG.parent                         # 60-实战_Projects/
OUT = PKG / "output"

if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

POSES = ["home", "forward", "side_right", "pitch_up", "roll_left"]
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9875


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    """Lightweight TCP probe — does not raise."""
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


class FCError(RuntimeError):
    """FreeCAD RPC 操作失败."""


class _TimeoutTransport(xmlrpc.client.Transport):
    """xmlrpc.client.Transport variant with socket-level timeout."""

    def __init__(self, timeout: float = 30.0):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class FCClient:
    """FreeCAD GUI XML-RPC 客户端 (FreeCADMCP server).

    All operations are dispatched onto FreeCAD's GUI main thread; the user
    sees changes in real time. Connection is lazy — `ping()` is the canonical
    aliveness check.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 timeout: float = 30.0):
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}"
        self._timeout = timeout
        # allow_none=True is required because rpc_server returns None for some calls.
        # Custom transport adds a socket-level timeout so a dead RPC never blocks the
        # viewer thread (xmlrpc.client.ServerProxy alone has no timeout knob).
        self._proxy = xmlrpc.client.ServerProxy(
            self.url, allow_none=True,
            transport=_TimeoutTransport(timeout=timeout),
        )

    def _ensure_alive(self) -> None:
        """Cheap port probe — raises FCError fast instead of blocking on XMLRPC."""
        if not _port_open(self.host, self.port):
            raise FCError(
                f"RPC unreachable at {self.url} "
                "(FreeCAD GUI not started or auto-RPC hook not yet loaded — "
                "restart FreeCAD GUI to pick up ~AppData/FreeCAD/InitGui.py)"
            )

    # ── core ────────────────────────────────────────────────────────────────
    def ping(self) -> bool:
        """Return True iff RPC server reachable AND ping() returns truthy."""
        if not _port_open(self.host, self.port):
            return False
        try:
            return bool(self._proxy.ping())
        except Exception:
            return False

    def list_docs(self) -> list[str]:
        self._ensure_alive()
        return list(self._proxy.list_documents() or [])

    def get_objects(self, doc: str) -> list[dict]:
        self._ensure_alive()
        return list(self._proxy.get_objects(doc) or [])

    def execute(self, code: str) -> dict:
        """Run arbitrary Python code in FreeCAD GUI main thread."""
        self._ensure_alive()
        return dict(self._proxy.execute_code(code))

    def screenshot(self, view: str = "Isometric") -> bytes | None:
        """Capture active view as PNG bytes (None if no active 3D view)."""
        self._ensure_alive()
        b64 = self._proxy.get_active_screenshot(view)
        if not b64:
            return None
        return base64.b64decode(b64)

    # ── ORS6 high-level ─────────────────────────────────────────────────────
    def open_pose(self, pose: str) -> dict:
        """Open output/ORS6_<pose>.FCStd in FreeCAD GUI.

        反者道之动: headless build 中 ViewObject=None, ShapeColor 不能保存,
        但 build_freecad 已写入 DesignColor 自定义属性. GUI 加载后此处读取
        DesignColor 应用到 ShapeColor, 还原 STL 设计色彩 + Receiver 半透明.
        """
        if pose not in POSES:
            raise ValueError(f"unknown pose: {pose} (need one of {POSES})")
        fc_path = OUT / f"ORS6_{pose}.FCStd"
        if not fc_path.is_file():
            raise FCError(f"FCStd not found: {fc_path}")
        # Use forward slashes inside the python literal to dodge backslash escapes
        path_str = str(fc_path).replace("\\", "/")
        doc_name = f"ORS6_{pose}"
        code = (
            "import FreeCAD as App, FreeCADGui as Gui\n"
            # Close any existing duplicate to avoid 'ORS6_home1' etc.
            f"_n = '{doc_name}'\n"
            "if _n in App.listDocuments(): App.closeDocument(_n)\n"
            f"_doc = App.openDocument(r'{path_str}')\n"
            "App.setActiveDocument(_doc.Name)\n"
            "# Restore design colors (persisted in DesignColor App::PropertyColor)\n"
            "for _o in _doc.Objects:\n"
            "    if hasattr(_o, 'DesignColor') and getattr(_o, 'ViewObject', None):\n"
            "        try:\n"
            "            _c = _o.DesignColor\n"
            "            _o.ViewObject.ShapeColor = (_c[0], _c[1], _c[2])\n"
            "            if len(_c) > 3:\n"
            "                _o.ViewObject.Transparency = int(round(_c[3] * 100))\n"
            "        except Exception:\n"
            "            pass\n"
            "    if _o.Label == 'Receiver' and getattr(_o, 'ViewObject', None):\n"
            "        try: _o.ViewObject.Transparency = 30\n"
            "        except Exception: pass\n"
            "Gui.SendMsgToActiveView('ViewFit')\n"
            "try:\n"
            "    Gui.ActiveDocument.ActiveView.viewIsometric()\n"
            "    Gui.ActiveDocument.ActiveView.fitAll()\n"
            "except Exception:\n"
            "    pass\n"
        )
        res = self.execute(code)
        res["pose"] = pose
        res["path"] = str(fc_path)
        return res

    def screenshot_to_file(self, dest: Path | str, view: str = "Isometric") -> Path:
        png = self.screenshot(view)
        if png is None:
            raise FCError("active view does not support screenshot")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(png)
        return dest

    def state(self) -> dict:
        """Lightweight composite state for the front-end status badge."""
        info: dict[str, Any] = {
            "host": self.host, "port": self.port, "url": self.url,
            "alive": False, "documents": [], "active_doc": None,
            "objects_in_active": 0,
            "fc_macro_dir": None,
        }
        if not self.ping():
            info["error"] = "RPC unreachable (FreeCAD GUI not started or auto-RPC failed)"
            return info
        info["alive"] = True
        try:
            docs = self.list_docs()
            info["documents"] = docs
            if docs:
                # active doc heuristic: last-opened (rpc returns dict)
                # fall back to iterating list
                info["active_doc"] = docs[-1]
                try:
                    info["objects_in_active"] = len(self.get_objects(docs[-1]))
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001
            info["warn"] = repr(e)
        return info

    def audit_all_poses(self, timeout_per: float = 5.0) -> dict:
        """Verify all 5 pose FCStd files can be opened in GUI.

        For each pose: open → list objects → close. Returns summary dict.
        """
        report = {"timestamp": int(time.time()), "poses": []}
        if not self.ping():
            report["error"] = "RPC unreachable"
            return report

        for pose in POSES:
            entry = {"pose": pose, "ok": False}
            t0 = time.time()
            try:
                self.open_pose(pose)
                # give FreeCAD a moment to open
                time.sleep(0.4)
                docs = self.list_docs()
                target = f"ORS6_{pose}"
                if target in docs:
                    objs = self.get_objects(target)
                    entry.update({
                        "ok": True,
                        "objects": len(objs),
                        "doc": target,
                    })
                else:
                    entry["error"] = f"opened doc not in list: {docs}"
            except Exception as e:  # noqa: BLE001
                entry["error"] = repr(e)
            entry["duration_s"] = round(time.time() - t0, 2)
            report["poses"].append(entry)

        report["pass"] = sum(1 for p in report["poses"] if p["ok"])
        report["total"] = len(POSES)
        return report


# ── singleton helper for viewer/server.py ───────────────────────────────────
_default_client: FCClient | None = None


def get_client() -> FCClient:
    """Cached client for in-process re-use (viewer/server.py)."""
    global _default_client
    if _default_client is None:
        _default_client = FCClient()
    return _default_client


# ── CLI ─────────────────────────────────────────────────────────────────────
def _cli():
    p = argparse.ArgumentParser(description="ORS6 ↔ FreeCAD RPC client")
    p.add_argument("cmd", choices=[
        "ping", "state", "list", "open", "shoot", "audit", "exec",
    ])
    p.add_argument("arg", nargs="?", default=None,
                   help="pose name (open) | view (shoot) | python code (exec)")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--out", default=None, help="screenshot output path")
    args = p.parse_args()

    fc = FCClient(args.host, args.port)

    if args.cmd == "ping":
        ok = fc.ping()
        print(json.dumps({"alive": ok, "url": fc.url}))
        sys.exit(0 if ok else 1)

    if args.cmd == "state":
        print(json.dumps(fc.state(), indent=2, ensure_ascii=False))
        return

    if args.cmd == "list":
        print(json.dumps(fc.list_docs(), indent=2, ensure_ascii=False))
        return

    if args.cmd == "open":
        if not args.arg:
            sys.exit("open requires pose name")
        print(json.dumps(fc.open_pose(args.arg), indent=2, ensure_ascii=False))
        return

    if args.cmd == "shoot":
        view = args.arg or "Isometric"
        out = args.out or str(OUT / f"_dao_fc_shot_{int(time.time())}.png")
        try:
            path = fc.screenshot_to_file(out, view)
            print(json.dumps({"ok": True, "path": str(path),
                              "size_kb": round(path.stat().st_size / 1024, 1)}))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": repr(e)}))
            sys.exit(1)
        return

    if args.cmd == "audit":
        rep = fc.audit_all_poses()
        out = OUT / "_dao_fc_audit.json"
        out.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        print(f"\n→ saved to {out}")
        if rep.get("pass") != rep.get("total"):
            sys.exit(2)
        return

    if args.cmd == "exec":
        if not args.arg:
            sys.exit("exec requires python code")
        print(json.dumps(fc.execute(args.arg), indent=2, ensure_ascii=False))
        return


if __name__ == "__main__":
    _cli()
