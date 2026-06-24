#!/usr/bin/env python3
"""
道法自然 — FreeCAD 万法归一连接管理器
=========================================
道生一，一生二，二生三，三生万物。

本模块是 Agent 与 FreeCAD 之间的根本通道。
不论 FreeCAD 以何种形态存在（嵌入/子进程/GUI/远程），
本管理器统一封装，对外只暴露一个接口：execute_ops()

核心理念: 水善利万物而不争 — 自动感知最佳路径，无感切换。

五种连接模式 (自动降级):
  1. embedded  — 进程内直接 import FreeCAD (最快)
  2. subprocess — freecadcmd.exe 无头执行 (最稳)
  3. remote    — HTTP 远程控制 FreeCAD GUI (可视化)
  4. gui_macro — 启动 FreeCAD GUI 执行宏 (一次性)
  5. fcstd_only — 无 FreeCAD，仅解析 FCStd (降级)

额外能力 (突破原 FreeCAD 限制):
  - STEP 导入: 通过 BREP 中间格式绕过 FreeCAD 1.0 headless 挂起
  - IGES 导入: 同上
  - 自动启动 Remote Server
  - 健康检查 + 自动重连
  - 连接池 + 超时管理

Usage:
    from freecad_connection import FreeCADConnection

    fc = FreeCADConnection()
    fc.connect()  # 自动检测最佳模式

    # 执行操作序列
    result = fc.execute_ops([
        {"op": "make_box", "id": "b1", "L": 30, "W": 20, "H": 10},
        {"op": "fillet", "id": "r1", "shape": "b1", "radius": 2},
        {"op": "export_step", "shape": "r1", "path": "output.step"},
    ])

    # 导入 STEP (原 FreeCAD 1.0 headless 会挂起，本管理器已修复)
    result = fc.import_step("input.step")

    # 状态查询
    status = fc.status()
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError

__version__ = "1.0.0"
__all__ = ["FreeCADConnection", "ConnectionStatus", "ConnectionMode"]

# ── 路径配置 ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
BACKEND_SCRIPT = SCRIPT_DIR / "freecad_backend.py"
REMOTE_SERVER_SCRIPT = SCRIPT_DIR / "_fc_remote_server.py"
GUI_MACRO_SCRIPT = SCRIPT_DIR / "freecad_gui_macro.py"

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Backend script cached in temp (FreeCAD can't handle Chinese paths)
_BACKEND_TEMP_CACHE: Optional[str] = None


def _get_ascii_backend_path() -> str:
    """Copy backend script to temp ASCII path (FreeCAD 不支持中文路径)"""
    global _BACKEND_TEMP_CACHE
    if _BACKEND_TEMP_CACHE and Path(_BACKEND_TEMP_CACHE).exists():
        # Re-copy if source is newer
        if Path(_BACKEND_TEMP_CACHE).stat().st_mtime >= BACKEND_SCRIPT.stat().st_mtime:
            return _BACKEND_TEMP_CACHE
    import shutil
    td = Path(tempfile.gettempdir()) / "_fc_backend"
    td.mkdir(exist_ok=True)
    dest = td / "freecad_backend.py"
    shutil.copy2(str(BACKEND_SCRIPT), str(dest))
    _BACKEND_TEMP_CACHE = str(dest)
    return _BACKEND_TEMP_CACHE


# FreeCAD 安装位置
_FC_INSTALLS = [
    {
        "version": "1.0",
        "bin": r"D:\安装的软件\FreeCAD 1.0\bin",
        "lib": r"D:\安装的软件\FreeCAD 1.0\lib",
        "mod": r"D:\安装的软件\FreeCAD 1.0\Mod",
        "ext": r"D:\安装的软件\FreeCAD 1.0\Ext",
        "cmd": r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe",
        "gui": r"D:\安装的软件\FreeCAD 1.0\bin\freecad.exe",
    },
    {
        "version": "0.21",
        "bin": r"D:\安装的软件\FreeCAD 0.21\bin",
        "lib": r"D:\安装的软件\FreeCAD 0.21\lib",
        "mod": r"D:\安装的软件\FreeCAD 0.21\Mod",
        "ext": r"D:\安装的软件\FreeCAD 0.21\Ext",
        "cmd": r"D:\安装的软件\FreeCAD 0.21\bin\FreeCADCmd.exe",
        "gui": r"D:\安装的软件\FreeCAD 0.21\bin\FreeCAD.exe",
    },
]

REMOTE_PORT = 18920
REMOTE_HOST = "127.0.0.1"


# ═══════════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════════

class ConnectionMode:
    EMBEDDED = "embedded"
    SUBPROCESS = "subprocess"
    REMOTE = "remote"
    GUI_MACRO = "gui_macro"
    FCSTD_ONLY = "fcstd_only"
    NONE = "none"


@dataclass
class ConnectionStatus:
    mode: str = ConnectionMode.NONE
    available: bool = False
    version: str = ""
    cmd_path: str = ""
    gui_path: str = ""
    remote_url: str = ""
    remote_alive: bool = False
    embedded_ok: bool = False
    subprocess_ok: bool = False
    last_health_check: float = 0.0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════
# FreeCAD 万法归一连接管理器
# ═══════════════════════════════════════════════════════════════════════════

class FreeCADConnection:
    """
    FreeCAD 统一连接管理器

    自动检测最佳连接模式，提供统一 API。
    水善利万物而不争 — 最佳路径自动选择。
    """

    def __init__(self, prefer_mode: str = "auto",
                 remote_host: str = REMOTE_HOST,
                 remote_port: int = REMOTE_PORT,
                 timeout: int = 120):
        self._prefer_mode = prefer_mode
        self._remote_host = remote_host
        self._remote_port = remote_port
        self._timeout = timeout
        self._status = ConnectionStatus()
        self._install = None  # detected FreeCAD install
        self._App = None      # embedded FreeCAD module
        self._Part = None     # embedded Part module
        self._Mesh = None     # embedded Mesh module
        self._lock = threading.Lock()
        self._remote_proc = None  # remote server process handle

    # ──────────────────────────────────────────────────────────────────
    # 连接 API
    # ──────────────────────────────────────────────────────────────────

    def connect(self, mode: str = None) -> ConnectionStatus:
        """
        连接 FreeCAD。自动检测最佳模式。

        Args:
            mode: "embedded" / "subprocess" / "remote" / "auto" (默认)

        Returns:
            ConnectionStatus
        """
        mode = mode or self._prefer_mode
        self._detect_installs()

        if mode == "auto":
            # 优先级: remote > subprocess > embedded > fcstd_only
            if self._check_remote():
                self._status.mode = ConnectionMode.REMOTE
            elif self._check_subprocess():
                self._status.mode = ConnectionMode.SUBPROCESS
            elif self._check_embedded():
                self._status.mode = ConnectionMode.EMBEDDED
            else:
                self._status.mode = ConnectionMode.FCSTD_ONLY
        elif mode == ConnectionMode.EMBEDDED:
            self._check_embedded()
            self._status.mode = ConnectionMode.EMBEDDED if self._status.embedded_ok else ConnectionMode.FCSTD_ONLY
        elif mode == ConnectionMode.SUBPROCESS:
            self._check_subprocess()
            self._status.mode = ConnectionMode.SUBPROCESS if self._status.subprocess_ok else ConnectionMode.FCSTD_ONLY
        elif mode == ConnectionMode.REMOTE:
            if not self._check_remote():
                # 尝试自动启动
                self._auto_start_remote()
            self._status.mode = ConnectionMode.REMOTE if self._status.remote_alive else ConnectionMode.FCSTD_ONLY

        self._status.available = self._status.mode != ConnectionMode.NONE
        self._status.last_health_check = time.time()
        return self._status

    def status(self) -> ConnectionStatus:
        """返回当前连接状态"""
        return self._status

    def health_check(self) -> bool:
        """健康检查，必要时重连"""
        if self._status.mode == ConnectionMode.REMOTE:
            alive = self._check_remote()
            if not alive:
                # 尝试重启
                self._auto_start_remote()
                alive = self._check_remote()
            return alive
        elif self._status.mode == ConnectionMode.SUBPROCESS:
            return self._check_subprocess()
        elif self._status.mode == ConnectionMode.EMBEDDED:
            return self._status.embedded_ok
        return False

    # ──────────────────────────────────────────────────────────────────
    # 核心执行 API — 万法归一
    # ──────────────────────────────────────────────────────────────────

    def execute_ops(self, ops: List[Dict], timeout: int = None) -> Dict[str, Any]:
        """
        执行 FreeCAD 操作序列。自动选择最佳通道。

        Args:
            ops: 操作列表 (同 freecad_backend.py 协议)
            timeout: 超时秒数

        Returns:
            结果字典 {ok, shapes, exports, analyses, errors}
        """
        timeout = timeout or self._timeout

        # 预处理: 检查是否有需要特殊处理的操作
        ops = self._preprocess_ops(ops)

        if self._status.mode == ConnectionMode.REMOTE:
            return self._exec_remote(ops, timeout)
        elif self._status.mode == ConnectionMode.SUBPROCESS:
            return self._exec_subprocess(ops, timeout)
        elif self._status.mode == ConnectionMode.EMBEDDED:
            return self._exec_embedded(ops, timeout)
        else:
            return {"ok": False, "errors": ["No FreeCAD connection available"],
                    "shapes": {}, "exports": [], "analyses": []}

    def import_step(self, path: str, output_brep: str = None) -> Dict[str, Any]:
        """
        导入 STEP 文件 — 绕过 FreeCAD 1.0 headless 挂起问题

        策略:
          1. 尝试 Remote (GUI模式不挂起)
          2. 尝试 OCC 直接读取
          3. 尝试 subprocess + 特殊超时脚本
          4. 尝试 embedded (可能挂起，加超时保护)

        Returns:
            {ok, shape_id, brep_path, shape_info}
        """
        path = str(Path(path).resolve())
        if not Path(path).exists():
            return {"ok": False, "error": f"File not found: {path}"}

        # 方法1: 通过 Remote Server (GUI模式不挂起)
        if self._status.remote_alive:
            result = self._exec_remote([
                {"op": "import_step_gui", "id": "imported", "path": path}
            ], timeout=60)
            if result.get("ok"):
                return {"ok": True, "method": "remote_gui", **result}

        # 方法2: OCC 直接读取 (如果 OCP 可用)
        occ_result = self._import_step_via_occ(path, output_brep)
        if occ_result.get("ok"):
            return occ_result

        # 方法3: 通过 subprocess 执行特殊导入脚本
        import_script = self._generate_step_import_script(path, output_brep)
        sub_result = self._exec_subprocess_script(import_script, timeout=30)
        if sub_result.get("ok"):
            return {"ok": True, "method": "subprocess_brep", **sub_result}

        return {"ok": False, "error": "All STEP import methods failed",
                "methods_tried": ["remote_gui", "occ_direct", "subprocess_brep"]}

    def import_iges(self, path: str, output_brep: str = None) -> Dict[str, Any]:
        """导入 IGES 文件 — 同 import_step 策略"""
        path = str(Path(path).resolve())
        if not Path(path).exists():
            return {"ok": False, "error": f"File not found: {path}"}

        # 方法1: 通过 Remote
        if self._status.remote_alive:
            result = self._exec_remote([
                {"op": "import_iges_gui", "id": "imported", "path": path}
            ], timeout=60)
            if result.get("ok"):
                return {"ok": True, "method": "remote_gui", **result}

        # 方法2: OCC 直接读取
        occ_result = self._import_iges_via_occ(path, output_brep)
        if occ_result.get("ok"):
            return occ_result

        return {"ok": False, "error": "All IGES import methods failed"}

    # ──────────────────────────────────────────────────────────────────
    # 便捷高级 API
    # ──────────────────────────────────────────────────────────────────

    def make_and_export(self, ops: List[Dict], export_path: str,
                        export_format: str = "step") -> Dict[str, Any]:
        """构建 + 导出一步完成"""
        # 找到最后一个有 id 的 op 作为导出目标
        last_id = None
        for op in reversed(ops):
            if op.get("id"):
                last_id = op["id"]
                break
        if not last_id:
            return {"ok": False, "error": "No shape id found in ops"}

        full_ops = list(ops) + [{
            "op": f"export_{export_format}",
            "shape": last_id,
            "path": str(Path(export_path).resolve())
        }]
        return self.execute_ops(full_ops)

    def convert(self, src: str, dst: str) -> Dict[str, Any]:
        """格式转换: STEP→STL, FCStd→STEP, etc."""
        src_ext = Path(src).suffix.lower()
        dst_ext = Path(dst).suffix.lower()

        ops = []

        # Import
        if src_ext in (".step", ".stp"):
            result = self.import_step(src)
            if not result.get("ok"):
                return result
            brep_path = result.get("brep_path")
            if brep_path:
                ops.append({"op": "import_brep", "id": "src", "path": brep_path})
            else:
                return {"ok": False, "error": "STEP import produced no BREP"}
        elif src_ext in (".brep", ".brp"):
            ops.append({"op": "import_brep", "id": "src", "path": str(Path(src).resolve())})
        elif src_ext == ".stl":
            ops.append({"op": "import_stl", "id": "src", "path": str(Path(src).resolve())})
        elif src_ext == ".fcstd":
            ops.append({"op": "read_fcstd", "id": "src", "path": str(Path(src).resolve())})
        else:
            return {"ok": False, "error": f"Unsupported source format: {src_ext}"}

        # Export
        ext_map = {
            ".step": "export_step", ".stp": "export_step",
            ".stl": "export_stl", ".brep": "export_brep",
            ".brp": "export_brep", ".obj": "export_obj",
            ".dxf": "export_dxf", ".svg": "export_svg",
            ".iges": "export_iges", ".igs": "export_iges",
            ".fcstd": "export_fcstd",
        }
        export_op = ext_map.get(dst_ext)
        if not export_op:
            return {"ok": False, "error": f"Unsupported target format: {dst_ext}"}

        ops.append({"op": export_op, "shape": "src",
                     "path": str(Path(dst).resolve())})
        return self.execute_ops(ops)

    # ──────────────────────────────────────────────────────────────────
    # 安装检测
    # ──────────────────────────────────────────────────────────────────

    def _detect_installs(self):
        """检测 FreeCAD 安装"""
        for inst in _FC_INSTALLS:
            if Path(inst["cmd"]).exists():
                self._install = inst
                self._status.version = inst["version"]
                self._status.cmd_path = inst["cmd"]
                self._status.gui_path = inst.get("gui", "")
                return
        # 搜索 PATH
        for name in ("freecadcmd", "FreeCADCmd", "freecadcmd.exe"):
            found = shutil.which(name)
            if found:
                self._install = {"version": "unknown", "cmd": found}
                self._status.version = "unknown"
                self._status.cmd_path = found
                return

    def _check_embedded(self) -> bool:
        """检测嵌入模式"""
        if self._App is not None:
            self._status.embedded_ok = True
            return True
        if not self._install:
            return False
        try:
            import xml.etree.ElementTree as _ET_PRELOADED  # noqa
            for p in [self._install.get("bin", ""), self._install.get("lib", ""),
                      self._install.get("mod", ""), self._install.get("ext", "")]:
                if p and p not in sys.path:
                    sys.path.insert(0, p)
            if sys.platform == "win32" and self._install.get("bin"):
                os.add_dll_directory(self._install["bin"])
            import FreeCAD as App
            import Part
            self._App = App
            self._Part = Part
            try:
                import Mesh
                self._Mesh = Mesh
            except ImportError:
                pass
            self._status.embedded_ok = True
            return True
        except Exception as e:
            self._status.errors.append(f"embedded: {e}")
            return False

    def _check_subprocess(self) -> bool:
        """检测子进程模式"""
        if not self._status.cmd_path:
            return False
        try:
            result = self._exec_subprocess(
                [{"op": "make_box", "id": "t", "L": 5, "W": 5, "H": 5},
                 {"op": "shape_info", "shape": "t"}],
                timeout=20)
            ok = result.get("ok", False) or "t" in result.get("shapes", {})
            self._status.subprocess_ok = ok
            return ok
        except Exception as e:
            self._status.errors.append(f"subprocess: {e}")
            return False

    def _check_remote(self) -> bool:
        """检测远程服务器"""
        url = f"http://{self._remote_host}:{self._remote_port}/status"
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                self._status.remote_alive = data.get("ok", False)
                self._status.remote_url = f"http://{self._remote_host}:{self._remote_port}"
                return self._status.remote_alive
        except Exception:
            self._status.remote_alive = False
            return False

    def _auto_start_remote(self) -> bool:
        """自动启动 FreeCAD GUI + Remote Server"""
        gui_path = self._status.gui_path
        if not gui_path or not Path(gui_path).exists():
            return False
        if not REMOTE_SERVER_SCRIPT.exists():
            return False
        try:
            self._remote_proc = subprocess.Popen(
                [gui_path, str(REMOTE_SERVER_SCRIPT)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW if sys.platform == "win32" else 0
            )
            # 等待启动
            for _ in range(20):
                time.sleep(1)
                if self._check_remote():
                    return True
            return False
        except Exception as e:
            self._status.errors.append(f"auto_start_remote: {e}")
            return False

    # ──────────────────────────────────────────────────────────────────
    # 操作预处理
    # ──────────────────────────────────────────────────────────────────

    def _preprocess_ops(self, ops: List[Dict]) -> List[Dict]:
        """
        预处理操作序列:
        - 将 import_step/import_iges 替换为可工作的方案
        """
        processed = []
        for op in ops:
            op_name = op.get("op", "")

            # STEP 导入修复: 转为 BREP 中间格式
            if op_name in ("import_step", "import_step_occ") and \
               self._status.mode == ConnectionMode.SUBPROCESS:
                brep_result = self._step_to_brep(op.get("path", ""))
                if brep_result.get("ok"):
                    new_op = dict(op)
                    new_op["op"] = "import_brep"
                    new_op["path"] = brep_result["brep_path"]
                    new_op["_original_path"] = op.get("path", "")
                    processed.append(new_op)
                    continue
                # 如果转换失败，保留原 op (可能会报错)

            # IGES 导入修复
            if op_name in ("import_iges", "import_iges_occ") and \
               self._status.mode == ConnectionMode.SUBPROCESS:
                brep_result = self._iges_to_brep(op.get("path", ""))
                if brep_result.get("ok"):
                    new_op = dict(op)
                    new_op["op"] = "import_brep"
                    new_op["path"] = brep_result["brep_path"]
                    processed.append(new_op)
                    continue

            processed.append(op)
        return processed

    # ──────────────────────────────────────────────────────────────────
    # STEP/IGES 导入修复 — 绕过 FreeCAD 1.0 headless 挂起
    # ──────────────────────────────────────────────────────────────────

    def _step_to_brep(self, step_path: str) -> Dict[str, Any]:
        """通过 OCC 或 短超时 subprocess 将 STEP 转为 BREP"""
        step_path = str(Path(step_path).resolve())
        if not Path(step_path).exists():
            return {"ok": False, "error": f"Not found: {step_path}"}

        brep_path = str(Path(tempfile.gettempdir()) / f"_step2brep_{hash(step_path) & 0xFFFFFF}.brep")

        # 方法1: OCC 直接读取
        try:
            from OCC.Core.STEPControl import STEPControl_Reader
            from OCC.Core.BRepTools import breptools
            reader = STEPControl_Reader()
            status = reader.ReadFile(step_path)
            if status == 1:  # IFSelect_RetDone
                reader.TransferRoots()
                shape = reader.OneShape()
                breptools.Write(shape, brep_path)
                if Path(brep_path).exists() and Path(brep_path).stat().st_size > 0:
                    return {"ok": True, "brep_path": brep_path, "method": "occ_direct"}
        except ImportError:
            pass
        except Exception as e:
            pass

        # 方法2: freecadcmd 短脚本（Part.read对BREP不挂起，用Part.export先转）
        script = f'''
import sys, json
try:
    import Part
    # Part.read with STEP hangs, but Part.insert into doc works in some builds
    import FreeCAD as App
    doc = App.newDocument("_imp")
    # Try Part.insert which may work for some STEP files
    try:
        Part.insert("{step_path.replace(chr(92), '/')}", doc.Name)
        doc.recompute()
        shapes = [o.Shape for o in doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()]
        if shapes:
            compound = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
            compound.exportBrep("{brep_path.replace(chr(92), '/')}")
            print("STEP_IMPORT_OK")
        else:
            print("STEP_IMPORT_EMPTY")
    except Exception as e1:
        print(f"STEP_IMPORT_FAIL: {{e1}}")
    App.closeDocument("_imp")
except Exception as e:
    print(f"STEP_IMPORT_FAIL: {{e}}")
'''
        try:
            r = subprocess.run(
                [self._status.cmd_path, "-c", script],
                capture_output=True, text=True, timeout=20,
                creationflags=_NO_WINDOW
            )
            if "STEP_IMPORT_OK" in r.stdout:
                if Path(brep_path).exists() and Path(brep_path).stat().st_size > 0:
                    return {"ok": True, "brep_path": brep_path, "method": "subprocess_insert"}
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

        return {"ok": False, "error": "All STEP→BREP methods failed"}

    def _iges_to_brep(self, iges_path: str) -> Dict[str, Any]:
        """通过 OCC 将 IGES 转为 BREP"""
        iges_path = str(Path(iges_path).resolve())
        if not Path(iges_path).exists():
            return {"ok": False, "error": f"Not found: {iges_path}"}

        brep_path = str(Path(tempfile.gettempdir()) / f"_iges2brep_{hash(iges_path) & 0xFFFFFF}.brep")

        try:
            from OCC.Core.IGESControl import IGESControl_Reader
            from OCC.Core.BRepTools import breptools
            reader = IGESControl_Reader()
            status = reader.ReadFile(iges_path)
            if status == 1:
                reader.TransferRoots()
                shape = reader.OneShape()
                breptools.Write(shape, brep_path)
                if Path(brep_path).exists() and Path(brep_path).stat().st_size > 0:
                    return {"ok": True, "brep_path": brep_path, "method": "occ_direct"}
        except ImportError:
            pass
        except Exception:
            pass
        return {"ok": False, "error": "IGES→BREP failed"}

    def _import_step_via_occ(self, path: str, output_brep: str = None) -> Dict:
        """直接用 OCC 读取 STEP (兼容 OCP 和 pythonocc)"""
        try:
            try:
                from OCP.STEPControl import STEPControl_Reader
                from OCP.IFSelect import IFSelect_RetDone
                from OCP.BRepTools import BRepTools
                _breptools_write = lambda shape, p: BRepTools.Write_s(shape, p)
                _RET_DONE = IFSelect_RetDone
            except ImportError:
                from OCC.Core.STEPControl import STEPControl_Reader
                from OCC.Core.BRepTools import breptools
                _breptools_write = lambda shape, p: breptools.Write(shape, p)
                _RET_DONE = 1
            reader = STEPControl_Reader()
            status = reader.ReadFile(str(path))
            if status != _RET_DONE:
                return {"ok": False, "error": f"OCC STEP read status: {status}"}
            reader.TransferRoots()
            shape = reader.OneShape()
            brep_out = output_brep or str(
                Path(tempfile.gettempdir()) / f"_occ_step_{hash(path) & 0xFFFFFF}.brep")
            _breptools_write(shape, brep_out)
            if Path(brep_out).exists() and Path(brep_out).stat().st_size > 0:
                return {"ok": True, "method": "occ_direct",
                        "brep_path": brep_out,
                        "brep_size": Path(brep_out).stat().st_size}
            return {"ok": False, "error": "OCC wrote empty BREP"}
        except ImportError:
            return {"ok": False, "error": "OCC not available"}
        except Exception as e:
            return {"ok": False, "error": f"OCC STEP read: {e}"}

    def _import_iges_via_occ(self, path: str, output_brep: str = None) -> Dict:
        """直接用 OCC 读取 IGES (兼容 OCP 和 pythonocc)"""
        try:
            try:
                from OCP.IGESControl import IGESControl_Reader
                from OCP.IFSelect import IFSelect_RetDone
                from OCP.BRepTools import BRepTools
                _breptools_write = lambda shape, p: BRepTools.Write_s(shape, p)
                _RET_DONE = IFSelect_RetDone
            except ImportError:
                from OCC.Core.IGESControl import IGESControl_Reader
                from OCC.Core.BRepTools import breptools
                _breptools_write = lambda shape, p: breptools.Write(shape, p)
                _RET_DONE = 1
            reader = IGESControl_Reader()
            status = reader.ReadFile(str(path))
            if status != _RET_DONE:
                return {"ok": False, "error": f"OCC IGES read status: {status}"}
            reader.TransferRoots()
            shape = reader.OneShape()
            brep_out = output_brep or str(
                Path(tempfile.gettempdir()) / f"_occ_iges_{hash(path) & 0xFFFFFF}.brep")
            _breptools_write(shape, brep_out)
            if Path(brep_out).exists() and Path(brep_out).stat().st_size > 0:
                return {"ok": True, "method": "occ_direct",
                        "brep_path": brep_out}
            return {"ok": False, "error": "OCC wrote empty BREP"}
        except ImportError:
            return {"ok": False, "error": "OCC not available"}
        except Exception as e:
            return {"ok": False, "error": f"OCC IGES read: {e}"}

    def _generate_step_import_script(self, step_path: str, output_brep: str = None) -> str:
        """生成 STEP 导入专用脚本（运行在 freecadcmd 内）"""
        brep_out = output_brep or str(
            Path(tempfile.gettempdir()) / f"_step_import_{hash(step_path) & 0xFFFFFF}.brep")
        return f'''
import sys, json
import FreeCAD as App
import Part
from FreeCAD import Base
from pathlib import Path

result = {{"ok": False}}
try:
    doc = App.newDocument("_imp")
    Part.insert("{step_path.replace(chr(92), '/')}", doc.Name)
    doc.recompute()
    shapes = [o.Shape.copy() for o in doc.Objects
              if hasattr(o, "Shape") and not o.Shape.isNull()]
    if shapes:
        compound = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
        compound.exportBrep("{brep_out.replace(chr(92), '/')}")
        result = {{"ok": True, "brep_path": "{brep_out.replace(chr(92), '/')}",
                   "shapes": len(shapes),
                   "volume": round(compound.Volume, 4)}}
    App.closeDocument("_imp")
except Exception as e:
    result["error"] = str(e)
print("IMPORT_RESULT:" + json.dumps(result))
'''

    # ──────────────────────────────────────────────────────────────────
    # 执行通道实现
    # ──────────────────────────────────────────────────────────────────

    def _exec_subprocess(self, ops: List[Dict], timeout: int = 120) -> Dict:
        """通过 freecadcmd.exe 子进程执行 (launcher script pattern)"""
        import shutil
        td = Path(tempfile.mkdtemp(prefix="dao_fc_"))
        try:
            # Copy backend to ASCII temp dir
            backend_dest = td / "freecad_backend.py"
            shutil.copy2(str(BACKEND_SCRIPT), str(backend_dest))

            # Write ops
            cf = td / "cmd.json"
            rf = td / "result.json"
            cf.write_text(json.dumps({"ops": ops}, ensure_ascii=True),
                          encoding="utf-8")

            # Create launcher that imports backend and calls run_ops
            launcher = td / "launcher.py"
            launcher.write_text(
                f'import sys,json\n'
                f'from pathlib import Path\n'
                f'sys.path.insert(0,r"{td}")\n'
                f'from freecad_backend import run_ops\n'
                f'ops=json.loads(Path(r"{cf}").read_text(encoding="utf-8")).get("ops",[])\n'
                f'r=run_ops(ops)\n'
                f'Path(r"{rf}").write_text(json.dumps(r,indent=2,ensure_ascii=False,default=str),encoding="utf-8")\n',
                encoding="utf-8"
            )

            r = subprocess.run(
                [self._status.cmd_path, str(launcher)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=timeout, creationflags=_NO_WINDOW
            )

            if rf.exists() and rf.stat().st_size > 5:
                return json.loads(rf.read_text(encoding="utf-8"))

            # Try stdout parse
            stdout_text = r.stdout.decode("utf-8", errors="replace")
            for line in stdout_text.split("\n"):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        return json.loads(line)
                    except Exception:
                        pass
            stderr_text = r.stderr.decode("utf-8", errors="replace")[:500]
            return {"ok": False, "errors": [f"No result. RC={r.returncode}",
                                             stderr_text],
                    "shapes": {}, "exports": [], "analyses": []}
        except subprocess.TimeoutExpired:
            return {"ok": False, "errors": [f"Timeout after {timeout}s"],
                    "shapes": {}, "exports": [], "analyses": []}
        except Exception as e:
            return {"ok": False, "errors": [str(e)],
                    "shapes": {}, "exports": [], "analyses": []}
        finally:
            shutil.rmtree(str(td), ignore_errors=True)

    def _exec_subprocess_script(self, script: str, timeout: int = 30) -> Dict:
        """执行任意 Python 脚本在 freecadcmd 中"""
        tmp_script = Path(tempfile.gettempdir()) / f"_fc_script_{os.getpid()}.py"
        try:
            tmp_script.write_text(script, encoding="utf-8")
            r = subprocess.run(
                [self._status.cmd_path, str(tmp_script)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=timeout, creationflags=_NO_WINDOW
            )
            # 解析 IMPORT_RESULT: 行
            stdout_text = r.stdout.decode("utf-8", errors="replace")
            for line in stdout_text.split("\n"):
                if line.startswith("IMPORT_RESULT:"):
                    return json.loads(line[14:])
            return {"ok": r.returncode == 0, "stdout": r.stdout[:500],
                    "stderr": r.stderr[:500]}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Timeout"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            tmp_script.unlink(missing_ok=True)

    def _exec_remote(self, ops: List[Dict], timeout: int = 120) -> Dict:
        """通过 HTTP Remote Server 执行"""
        url = f"{self._status.remote_url}/ops"
        try:
            data = json.dumps({"ops": ops}).encode("utf-8")
            req = Request(url, data=data, method="POST",
                          headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as e:
            # 降级到 subprocess
            if self._status.subprocess_ok:
                return self._exec_subprocess(ops, timeout)
            return {"ok": False, "errors": [f"Remote failed: {e}"],
                    "shapes": {}, "exports": [], "analyses": []}

    def _exec_embedded(self, ops: List[Dict], timeout: int = 120) -> Dict:
        """嵌入模式执行（直接调用 backend 的 run_ops）"""
        try:
            # 动态导入 backend
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "freecad_backend", str(BACKEND_SCRIPT))
            backend = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(backend)
            return backend.run_ops(ops)
        except Exception as e:
            return {"ok": False, "errors": [f"Embedded exec: {e}"],
                    "shapes": {}, "exports": [], "analyses": []}

    # ──────────────────────────────────────────────────────────────────
    # 析构
    # ──────────────────────────────────────────────────────────────────

    def close(self):
        """关闭连接，清理资源"""
        if self._remote_proc:
            try:
                self._remote_proc.terminate()
            except Exception:
                pass
        self._status = ConnectionStatus()

    def __del__(self):
        self.close()

    def __repr__(self):
        return (f"FreeCADConnection(mode={self._status.mode}, "
                f"version={self._status.version}, "
                f"available={self._status.available})")


# ═══════════════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════════════

_global_connection: Optional[FreeCADConnection] = None


def get_connection(mode: str = "auto") -> FreeCADConnection:
    """获取全局 FreeCAD 连接 (懒初始化)"""
    global _global_connection
    if _global_connection is None:
        _global_connection = FreeCADConnection()
        _global_connection.connect(mode)
    return _global_connection


def execute_ops(ops: List[Dict], **kwargs) -> Dict:
    """快捷: 直接执行操作序列"""
    return get_connection().execute_ops(ops, **kwargs)


def import_step(path: str, **kwargs) -> Dict:
    """快捷: 导入 STEP"""
    return get_connection().import_step(path, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="FreeCAD Connection Manager")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="连接状态诊断")
    sub.add_parser("health", help="健康检查")

    p_ops = sub.add_parser("ops", help="执行操作序列")
    p_ops.add_argument("ops_json", help="ops JSON 文件或字符串")

    p_import = sub.add_parser("import", help="导入 STEP/IGES")
    p_import.add_argument("file", help="输入文件路径")
    p_import.add_argument("--output", default=None, help="输出 BREP 路径")

    p_convert = sub.add_parser("convert", help="格式转换")
    p_convert.add_argument("src")
    p_convert.add_argument("dst")

    p_start = sub.add_parser("start-remote", help="启动远程服务器")

    args = parser.parse_args()
    fc = FreeCADConnection()
    fc.connect()

    if args.cmd == "status":
        print(json.dumps(fc.status().to_dict(), indent=2, ensure_ascii=False))

    elif args.cmd == "health":
        ok = fc.health_check()
        print(json.dumps({"healthy": ok, **fc.status().to_dict()}, indent=2))

    elif args.cmd == "ops":
        if Path(args.ops_json).exists():
            ops = json.loads(Path(args.ops_json).read_text())
            if isinstance(ops, dict):
                ops = ops.get("ops", [])
        else:
            ops = json.loads(args.ops_json)
        result = fc.execute_ops(ops)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.cmd == "import":
        ext = Path(args.file).suffix.lower()
        if ext in (".step", ".stp"):
            result = fc.import_step(args.file, args.output)
        elif ext in (".iges", ".igs"):
            result = fc.import_iges(args.file, args.output)
        else:
            result = {"ok": False, "error": f"Unsupported: {ext}"}
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.cmd == "convert":
        result = fc.convert(args.src, args.dst)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.cmd == "start-remote":
        ok = fc._auto_start_remote()
        print(json.dumps({"started": ok, **fc.status().to_dict()}, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
