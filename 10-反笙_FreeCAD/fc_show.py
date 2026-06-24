#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fc_show.py — 反向锚定 · FreeCAD GUI 天生展示台
════════════════════════════════════════════════════════════════════
"得鱼而忘笙，复得返用笙" — 以 ops 为舟渡河 (笙)，既到，忘舟；
再欲渡新河，复取其舟。

本源命题: 一切产物 (FCStd/STEP/BREP/STL/OBJ/IGES/ops) 皆可直达 GUI。
         反演成果 (fc_reverse) 与外世成果 (dao_reverse) 皆归于此。

依赖链:
  本机 (Python3)            →  HTTP  →  FreeCAD GUI (18920)
  ─────────────────────────       ──────     ─────────────────────────────
  fc_show.FCShow             ←→    ←→       _fc_remote_server.py

典型用法:
  from fc_show import FCShow

  # 0. 确保 GUI 就绪 (自动启动 if needed)
  FCShow.ensure_gui()

  # 1. 加载任意格式
  FCShow.load("model.FCStd")
  FCShow.load("part.step")
  FCShow.load_ops(ops)                        # 来自 fc_reverse.reverse()

  # 2. 视图控制
  FCShow.view("isometric")  FCShow.fit()

  # 3. 截图
  FCShow.screenshot("snap.png", size=(1920,1080))

  # 4. 一键 live_show: 加载 + 多角度截图
  FCShow.live_show("model.FCStd", shots=["iso","front","top","right"])

  # 5. 清空
  FCShow.clear()

CLI:
  python fc_show.py launch                   # 启动GUI
  python fc_show.py status                   # 当前状态
  python fc_show.py show <file>              # 加载并显示 + 截图
  python fc_show.py screenshot <name.png>    # 截屏当前视图
  python fc_show.py view <isometric|front..> # 视图
  python fc_show.py clear                    # 清空当前文档
  python fc_show.py reload                   # 关闭并重新打开当前文档
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ─── 路径与端口 ──────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
ROOT_DIR = _DAO_ROOT
# ═══════════════════════════════════════════════════════════════════

REMOTE_SRV  = SCRIPT_DIR / "_fc_remote_server.py"   # 同层 10-反笙_FreeCAD
PORT        = int(os.environ.get("FC_REMOTE_PORT", "18920"))
HOST        = os.environ.get("FC_REMOTE_HOST", "127.0.0.1")
REMOTE      = f"http://{HOST}:{PORT}"

# ─── FreeCAD 可执行候选 ───────────────────────────────────────────────
_FC_CANDIDATES = [
    r"D:\安装的软件\FreeCAD 1.0\bin\freecad.exe",
    r"D:\安装的软件\FreeCAD 0.21\bin\FreeCAD.exe",
    r"C:\Program Files\FreeCAD 1.0\bin\freecad.exe",
    r"C:\Program Files\FreeCAD\bin\freecad.exe",
]

# ─── 视图动作 ─────────────────────────────────────────────────────────
VIEW_ACTIONS = (
    "fit_all", "isometric", "front", "rear", "top", "bottom",
    "left", "right", "home", "perspective", "orthographic",
)


# ═══════════════════════════════════════════════════════════════════
# HTTP 通信层 (最小化) — 不抛异常, 所有错误回传 dict
# ═══════════════════════════════════════════════════════════════════

def _http(method: str, path: str, body: Optional[Dict[str, Any]] = None,
          timeout: int = 300) -> Dict[str, Any]:
    url = REMOTE + path
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {"ok": False, "error": "non-JSON response",
                        "raw": raw[:500].decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}", "url": url}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"URL error: {e.reason}", "url": url}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "url": url}


def _get(path: str, timeout: int = 30) -> Dict[str, Any]:
    return _http("GET", path, timeout=timeout)


def _post(path: str, body: Dict[str, Any], timeout: int = 300) -> Dict[str, Any]:
    return _http("POST", path, body=body, timeout=timeout)


# ═══════════════════════════════════════════════════════════════════
# 探测与启动
# ═══════════════════════════════════════════════════════════════════

def _server_alive(timeout: int = 2) -> bool:
    r = _get("/status", timeout=timeout)
    return bool(r.get("ok"))


def _find_freecad() -> Optional[str]:
    for p in _FC_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def _launch_server(wait_seconds: int = 90) -> Dict[str, Any]:
    """启动 FreeCAD GUI + 自动执行 _fc_remote_server.py."""
    if _server_alive():
        return {"ok": True, "already_running": True, "port": PORT}
    fc = _find_freecad()
    if not fc:
        return {"ok": False, "error": "FreeCAD executable not found",
                "candidates": _FC_CANDIDATES}
    if not REMOTE_SRV.exists():
        return {"ok": False, "error": f"remote server script missing: {REMOTE_SRV}"}
    try:
        # DETACHED_PROCESS 让 FreeCAD 独立于本 Python 进程
        if os.name == "nt":
            DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                [fc, str(REMOTE_SRV)],
                creationflags=DETACHED,
                close_fds=True,
            )
        else:
            subprocess.Popen([fc, str(REMOTE_SRV)], start_new_session=True)
    except Exception as e:
        return {"ok": False, "error": f"Popen failed: {e}"}

    # 轮询等待服务器就绪
    t0 = time.time()
    while time.time() - t0 < wait_seconds:
        if _server_alive(timeout=3):
            return {"ok": True, "started": True, "elapsed_s": round(time.time() - t0, 1),
                    "port": PORT, "executable": fc}
        time.sleep(2)
    return {"ok": False, "error": f"timeout after {wait_seconds}s",
            "hint": "手动检查 FreeCAD 窗口是否打开 / 错误弹窗"}


# ═══════════════════════════════════════════════════════════════════
# FCShow — 对外 API 门面
# ═══════════════════════════════════════════════════════════════════

class FCShow:
    """反向锚定: 一切产物的 FreeCAD GUI 展示门面."""

    # ── 生命周期 ────────────────────────────────────────────────────
    @staticmethod
    def alive() -> bool:
        return _server_alive()

    @staticmethod
    def ensure_gui(wait_seconds: int = 90) -> Dict[str, Any]:
        """若 GUI 未就绪, 自动启动; 返回 status."""
        return _launch_server(wait_seconds=wait_seconds)

    @staticmethod
    def status() -> Dict[str, Any]:
        return _get("/status")

    @staticmethod
    def documents() -> Dict[str, Any]:
        return _get("/documents")

    @staticmethod
    def document() -> Dict[str, Any]:
        return _get("/document")

    # ── 文档操作 ────────────────────────────────────────────────────
    @staticmethod
    def new_document(name: str = "Show", set_active: bool = True) -> Dict[str, Any]:
        """新建文档并置为活动."""
        code = (
            f"import FreeCAD as App\n"
            f"doc = App.newDocument({name!r})\n"
            f"App.setActiveDocument({name!r})\n"
            f"doc.recompute()\n"
            f"__result__ = doc.Name"
        )
        return _post("/exec", {"code": code})

    @staticmethod
    def clear(close_all: bool = False) -> Dict[str, Any]:
        """
        清空当前文档的所有对象 (默认保留文档).
        close_all=True: 关闭所有文档并新建空白.
        """
        if close_all:
            code = (
                "import FreeCAD as App\n"
                "for name in list(App.listDocuments().keys()):\n"
                "    App.closeDocument(name)\n"
                "doc = App.newDocument('Show')\n"
                "doc.recompute()\n"
                "__result__ = 'all_closed_new_opened'"
            )
        else:
            code = (
                "import FreeCAD as App\n"
                "doc = App.ActiveDocument\n"
                "if doc is None:\n"
                "    doc = App.newDocument('Show')\n"
                "removed = 0\n"
                "for o in list(doc.Objects):\n"
                "    doc.removeObject(o.Name); removed += 1\n"
                "doc.recompute()\n"
                "__result__ = f'removed={removed}'"
            )
        return _post("/exec", {"code": code})

    @staticmethod
    def save_as(path: Union[str, Path]) -> Dict[str, Any]:
        """保存当前文档为 FCStd."""
        p = str(Path(path)).replace("\\", "/")
        code = (
            "import FreeCAD as App\n"
            "doc = App.ActiveDocument\n"
            "if doc is None: raise RuntimeError('no active document')\n"
            f"doc.saveAs({p!r})\n"
            "__result__ = doc.FileName"
        )
        return _post("/exec", {"code": code})

    # ── 加载: 一切皆可来 ────────────────────────────────────────────
    @staticmethod
    def load(path: Union[str, Path]) -> Dict[str, Any]:
        """
        加载任意文件到 GUI (自动识别).
        支持: .FCStd/.step/.stp/.iges/.igs/.brep/.brp/.stl/.obj/.ply/.off
        """
        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": f"file not found: {p}"}
        r = _post("/import_file", {"path": str(p)})
        # 加载后自动 fit
        if r.get("ok"):
            FCShow.fit()
        return r

    @staticmethod
    def load_many(paths: List[Union[str, Path]], fit: bool = True,
                  label_with_filename: bool = True) -> Dict[str, Any]:
        """
        批量加载多个文件 → 每个成为一个 Part::Feature / Mesh.
        所有加载到当前活动文档.
        """
        results: List[Dict[str, Any]] = []
        for path in paths:
            p = Path(path)
            if not p.exists():
                results.append({"path": str(p), "ok": False, "error": "not found"})
                continue
            r = _post("/import_file", {"path": str(p)})
            r["path"] = str(p)
            r["stem"] = p.stem
            results.append(r)
            # 若要重命名对象 = 文件名, 在 GUI 内 exec
            if label_with_filename and r.get("ok") and r.get("object"):
                safe_label = p.stem.replace("'", "_")
                exec_code = (
                    "import FreeCAD as App\n"
                    "doc = App.ActiveDocument\n"
                    f"obj = doc.getObject({r['object']!r})\n"
                    f"if obj: obj.Label = {safe_label!r}\n"
                )
                _post("/exec", {"code": exec_code})
        if fit:
            FCShow.fit()
        ok_count = sum(1 for x in results if x.get("ok"))
        return {"ok": ok_count > 0, "loaded": ok_count, "total": len(results),
                "details": results}

    @staticmethod
    def load_ops(ops: List[Dict[str, Any]], timeout: int = 300) -> Dict[str, Any]:
        """
        把 ops 序列送到 GUI (经 freecad_backend.run_ops 在 GUI 线程执行).
        适用场景: fc_reverse 反演后直接送 GUI 展示而非 headless 导出.
        """
        r = _post("/ops", {"ops": ops}, timeout=timeout)
        if r.get("ok"):
            FCShow.fit()
        return r

    # ── 视图 ────────────────────────────────────────────────────────
    @staticmethod
    def view(action: str = "isometric") -> Dict[str, Any]:
        if action not in VIEW_ACTIONS:
            return {"ok": False, "error": f"unknown action: {action}",
                    "valid": list(VIEW_ACTIONS)}
        return _post("/view", {"action": action})

    @staticmethod
    def fit() -> Dict[str, Any]:
        return _post("/view", {"action": "fit_all"})

    @staticmethod
    def isometric() -> Dict[str, Any]:
        r = _post("/view", {"action": "isometric"})
        FCShow.fit()
        return r

    # ── 截图 ────────────────────────────────────────────────────────
    @staticmethod
    def screenshot(out_path: Union[str, Path],
                   width: int = 1920, height: int = 1080) -> Dict[str, Any]:
        """截图并保存为 PNG."""
        r = _get("/screenshot", timeout=30)
        if not r.get("ok") or not r.get("data"):
            return {"ok": False, "error": r.get("error", "screenshot failed")}
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(base64.b64decode(r["data"]))
        return {"ok": True, "path": str(p), "size_bytes": p.stat().st_size,
                "width": r.get("width", width), "height": r.get("height", height)}

    # ── 一键秀 ──────────────────────────────────────────────────────
    @staticmethod
    def live_show(src: Union[str, Path, List[Dict[str, Any]]],
                  shots: Optional[List[str]] = None,
                  shot_dir: Union[str, Path, None] = None,
                  shot_prefix: Optional[str] = None,
                  clear_first: bool = True) -> Dict[str, Any]:
        """
        一键: 清空 → 加载 → fit → 多角度截图.
        shots: 默认 ["isometric","front","top","right"].
        shot_dir: 默认 SCRIPT_DIR/projects/fc_output/_fc_shots.
        """
        if shots is None:
            shots = ["isometric", "front", "top", "right"]
        if shot_dir is None:
            shot_dir = _dao_paths.PROJECTS / "fc_output" / "_fc_shots"
        shot_dir = Path(shot_dir)
        shot_dir.mkdir(parents=True, exist_ok=True)

        # 派生 prefix
        if shot_prefix is None:
            if isinstance(src, (str, Path)):
                shot_prefix = Path(src).stem
            else:
                shot_prefix = "ops"

        out: Dict[str, Any] = {"ok": False, "shots": []}

        # 确保 GUI
        alive = FCShow.ensure_gui()
        out["gui"] = alive
        if not alive.get("ok"):
            out["error"] = alive.get("error")
            return out

        if clear_first:
            out["clear"] = FCShow.clear()

        # 加载
        if isinstance(src, (str, Path)):
            load_r = FCShow.load(src)
        else:
            load_r = FCShow.load_ops(src)
        out["load"] = {k: load_r.get(k) for k in ("ok", "document", "objects", "object")}
        if not load_r.get("ok"):
            out["error"] = load_r.get("error", "load failed")
            return out

        # 多角度截图
        for a in shots:
            FCShow.view(a)
            # 让 GUI 刷新
            time.sleep(0.3)
            FCShow.fit()
            time.sleep(0.2)
            p = shot_dir / f"{shot_prefix}_{a}.png"
            sr = FCShow.screenshot(p)
            out["shots"].append({
                "view": a, "ok": sr.get("ok"),
                "path": sr.get("path"), "size_bytes": sr.get("size_bytes"),
            })

        out["ok"] = all(s.get("ok") for s in out["shots"]) and load_r.get("ok")
        out["shot_dir"] = str(shot_dir)
        return out

    # ── 打开已有 FCStd (打开而非导入) ───────────────────────────────
    @staticmethod
    def open_fcstd(path: Union[str, Path]) -> Dict[str, Any]:
        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": f"not found: {p}"}
        code = (
            "import FreeCAD as App\n"
            f"doc = App.openDocument({str(p)!r})\n"
            "App.setActiveDocument(doc.Name)\n"
            "doc.recompute()\n"
            "__result__ = doc.Name"
        )
        r = _post("/exec", {"code": code})
        if r.get("ok"):
            FCShow.fit()
        return r

    # ── 执行 Python (便捷) ──────────────────────────────────────────
    @staticmethod
    def exec_py(code: str, timeout: int = 60) -> Dict[str, Any]:
        return _post("/exec", {"code": code}, timeout=timeout)


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

_USAGE = """fc_show — 反向锚定 · FreeCAD GUI 天生展示台

  python fc_show.py launch                       # 启动 GUI + 远程服务器
  python fc_show.py status                       # 当前 GUI 状态
  python fc_show.py show <file> [--shots A,B,C]  # 加载+截图 (默认 iso/front/top/right)
  python fc_show.py load <file>                  # 仅加载
  python fc_show.py load-many <f1> <f2> ...      # 批量加载 (装配展示)
  python fc_show.py shot <name.png>              # 截屏当前视图
  python fc_show.py view <action>                # 视图 (isometric/front/top/right/home...)
  python fc_show.py clear                        # 清空当前文档
  python fc_show.py close-all                    # 关闭所有文档
  python fc_show.py save <path.FCStd>            # 保存当前文档
  python fc_show.py open <file.FCStd>            # 打开 FCStd (而非导入)
  python fc_show.py exec '<python code>'         # 执行 python (便捷调试)
"""


def _cli_status() -> int:
    r = FCShow.status()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cli_launch() -> int:
    print("[fc_show] Ensuring GUI + remote server is up …")
    r = FCShow.ensure_gui()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cli_show(args: List[str]) -> int:
    if not args:
        print(_USAGE); return 1
    file_path = args[0]
    shots = ["isometric", "front", "top", "right"]
    rest = args[1:]
    i = 0
    while i < len(rest):
        if rest[i] == "--shots" and i + 1 < len(rest):
            shots = [s.strip() for s in rest[i + 1].split(",") if s.strip()]
            i += 2; continue
        i += 1
    r = FCShow.live_show(file_path, shots=shots)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cli_load(args: List[str]) -> int:
    if not args:
        print(_USAGE); return 1
    r = FCShow.load(args[0])
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cli_load_many(args: List[str]) -> int:
    if not args:
        print(_USAGE); return 1
    r = FCShow.load_many(args)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cli_shot(args: List[str]) -> int:
    if not args:
        print(_USAGE); return 1
    r = FCShow.screenshot(args[0])
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cli_view(args: List[str]) -> int:
    if not args:
        print(_USAGE); return 1
    r = FCShow.view(args[0])
    FCShow.fit()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cli_clear(close_all: bool = False) -> int:
    r = FCShow.clear(close_all=close_all)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cli_save(args: List[str]) -> int:
    if not args:
        print(_USAGE); return 1
    r = FCShow.save_as(args[0])
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cli_open(args: List[str]) -> int:
    if not args:
        print(_USAGE); return 1
    r = FCShow.open_fcstd(args[0])
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cli_exec(args: List[str]) -> int:
    if not args:
        print(_USAGE); return 1
    code = " ".join(args)
    r = FCShow.exec_py(code)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE); return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "launch":     return _cli_launch()
    if cmd == "status":     return _cli_status()
    if cmd == "show":       return _cli_show(rest)
    if cmd == "load":       return _cli_load(rest)
    if cmd in ("load-many", "load_many"): return _cli_load_many(rest)
    if cmd in ("shot", "screenshot"): return _cli_shot(rest)
    if cmd == "view":       return _cli_view(rest)
    if cmd == "clear":      return _cli_clear(close_all=False)
    if cmd in ("close-all", "close_all"): return _cli_clear(close_all=True)
    if cmd == "save":       return _cli_save(rest)
    if cmd == "open":       return _cli_open(rest)
    if cmd == "exec":       return _cli_exec(rest)
    print(f"Unknown command: {cmd}\n\n{_USAGE}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
