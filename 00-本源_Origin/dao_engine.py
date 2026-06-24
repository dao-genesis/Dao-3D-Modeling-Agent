#!/usr/bin/env python3
"""
道 · 统一执行引擎 — DaoEngine v1.0
=====================================
道生一，一生二，二生三，三生万物。

旧架构: ops JSON → freecadcmd → fire-and-forget
新架构: DesignTree → Code → [本引擎] → 增量执行 + 反馈闭环 + 验证

本模块是整个建模系统的执行核心，替代:
  - fc_model_builder.py (FreeCAD子进程执行)
  - dao_forge.py (DaoForge执行层)
  - forge_v3.py (部分执行功能)

统一为一个引擎，支持:
  1. CadQuery 执行 (首选 — 纯Python，可增量)
  2. FreeCAD headless 执行 (via freecadcmd)
  3. FreeCAD GUI 执行 (via Remote Server)
  4. OpenSCAD 执行 (CSG快速原型)

核心能力:
  - 增量执行: 每步捕获中间状态
  - 反馈闭环: 执行后自动验证，提供诊断信息
  - 错误恢复: 定位失败步骤，提供修复建议
  - 多引擎透明切换: 首选失败自动降级

Usage:
    from dao_engine import DaoEngine
    from design_intent_compiler import DesignIntentCompiler
    from parametric_codegen import ParametricCodegen

    # 完整管道
    engine = DaoEngine()
    compiler = DesignIntentCompiler()
    codegen = ParametricCodegen()

    tree, report, plan = compiler.compile_and_plan(spec)
    code_result = codegen.generate(tree, plan)
    result = engine.execute(code_result)

    # 或者直接执行代码字符串
    result = engine.run_cadquery_code(code_string)
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

__version__ = "1.0.0"
__all__ = ["DaoEngine", "ExecutionResult", "EngineStatus"]

# ── 路径配置 ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
ROOT_DIR = _DAO_ROOT
# ═══════════════════════════════════════════════════════════════════

BACKEND_SCRIPT = _dao_paths.REVERSE / "freecad_backend.py"       # 10-反笙_FreeCAD
HISTORY_DIR = _dao_paths.PROJECTS / "fc_output" / ".dao_history"  # 60-实战_Projects
OUTPUT_DIR = _dao_paths.PROJECTS / "fc_output"                    # 60-实战_Projects

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# FreeCAD 搜索路径
_FREECAD_SEARCH = [
    r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe",
    r"C:\Program Files\FreeCAD 1.0\bin\freecadcmd.exe",
    r"C:\Program Files\FreeCAD 0.21\bin\freecadcmd.exe",
]


# ═══════════════════════════════════════════════════════════════════════════
# 一、执行结果数据结构
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class StepResult:
    """单步执行结果"""
    step: int
    action: str
    ok: bool
    elapsed_s: float = 0.0
    output: str = ""
    error: str = ""
    shapes: Dict[str, Any] = field(default_factory=dict)
    files: List[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """完整执行结果"""
    ok: bool
    engine: str
    elapsed_s: float = 0.0
    steps: List[StepResult] = field(default_factory=list)
    output_files: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    code_path: str = ""

    def to_dict(self):
        return {
            "ok": self.ok,
            "engine": self.engine,
            "elapsed_s": self.elapsed_s,
            "steps": [asdict(s) for s in self.steps],
            "output_files": self.output_files,
            "errors": self.errors,
            "warnings": self.warnings,
            "diagnostics": self.diagnostics,
            "code_path": self.code_path,
        }


@dataclass
class EngineStatus:
    """引擎状态"""
    name: str
    available: bool
    version: str = ""
    path: str = ""
    note: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# 二、引擎检测
# ═══════════════════════════════════════════════════════════════════════════

def _detect_cadquery() -> EngineStatus:
    """检测CadQuery是否可用"""
    try:
        import cadquery as cq
        ver = getattr(cq, "__version__", "unknown")
        return EngineStatus("cadquery", True, ver, note="CadQuery available")
    except ImportError:
        return EngineStatus("cadquery", False, note="pip install cadquery")


def _detect_freecad_cmd() -> EngineStatus:
    """检测FreeCAD headless是否可用"""
    for p in _FREECAD_SEARCH:
        if Path(p).exists():
            return EngineStatus("freecad_cmd", True, path=p)
    found = shutil.which("freecadcmd") or shutil.which("FreeCADCmd")
    if found:
        return EngineStatus("freecad_cmd", True, path=found)
    return EngineStatus("freecad_cmd", False, note="FreeCADCmd not found")


def _detect_freecad_remote() -> EngineStatus:
    """检测FreeCAD Remote Server是否运行"""
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://127.0.0.1:18920/api/status", timeout=2)
        data = json.loads(resp.read())
        return EngineStatus("freecad_remote", True, note=f"Running on :18920")
    except Exception:
        return EngineStatus("freecad_remote", False, note="Remote server not running on :18920")


def _detect_openscad() -> EngineStatus:
    """检测OpenSCAD是否可用"""
    found = shutil.which("openscad")
    if found:
        return EngineStatus("openscad", True, path=found)
    # Windows常见路径
    win_paths = [
        r"C:\Program Files\OpenSCAD\openscad.exe",
        r"C:\Program Files (x86)\OpenSCAD\openscad.exe",
    ]
    for p in win_paths:
        if Path(p).exists():
            return EngineStatus("openscad", True, path=p)
    return EngineStatus("openscad", False, note="OpenSCAD not found")


def _detect_trimesh() -> EngineStatus:
    """检测trimesh是否可用"""
    try:
        import trimesh
        return EngineStatus("trimesh", True, getattr(trimesh, "__version__", ""))
    except ImportError:
        return EngineStatus("trimesh", False, note="pip install trimesh")


# ═══════════════════════════════════════════════════════════════════════════
# 三、CadQuery 执行器
# ═══════════════════════════════════════════════════════════════════════════

class _CadQueryExecutor:
    """CadQuery代码执行器 — 直接在当前进程中执行"""

    def __init__(self):
        self.available = _detect_cadquery().available

    def execute(self, code: str, output_dir: str = None) -> ExecutionResult:
        """执行CadQuery代码"""
        t0 = time.time()

        if not self.available:
            return ExecutionResult(
                ok=False, engine="cadquery",
                errors=["CadQuery not installed. pip install cadquery"],
            )

        # 保存代码到临时文件
        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            script_path = out / "build.py"
        else:
            td = Path(tempfile.mkdtemp(prefix="dao_cq_"))
            script_path = td / "build.py"

        script_path.write_text(code, encoding="utf-8")

        # 使用子进程执行 (隔离环境)
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True, text=True, timeout=120,
                cwd=str(script_path.parent),
                creationflags=_NO_WINDOW if sys.platform == "win32" else 0,
            )
            elapsed = round(time.time() - t0, 2)

            output_files = {}
            if output_dir:
                for f in Path(output_dir).glob("*"):
                    if f.suffix in (".stl", ".step", ".obj", ".dxf", ".svg"):
                        output_files[f.suffix.lstrip(".")] = str(f)

            errors = []
            if proc.returncode != 0:
                stderr = proc.stderr[-2000:] if proc.stderr else ""
                errors.append(f"Exit code {proc.returncode}")
                if stderr:
                    errors.append(stderr)

            # 诊断: 分析错误以提供修复建议
            diagnostics = self._diagnose(proc.stderr or "", proc.stdout or "")

            return ExecutionResult(
                ok=proc.returncode == 0,
                engine="cadquery",
                elapsed_s=elapsed,
                output_files=output_files,
                errors=errors,
                warnings=diagnostics.get("warnings", []),
                diagnostics=diagnostics,
                code_path=str(script_path),
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                ok=False, engine="cadquery",
                elapsed_s=round(time.time() - t0, 2),
                errors=["Timeout (120s)"],
                code_path=str(script_path),
            )
        except Exception as e:
            return ExecutionResult(
                ok=False, engine="cadquery",
                elapsed_s=round(time.time() - t0, 2),
                errors=[str(e)],
                code_path=str(script_path),
            )

    def _diagnose(self, stderr: str, stdout: str) -> Dict:
        """分析错误输出，提供诊断和修复建议"""
        diag = {"warnings": [], "suggestions": []}

        if "ModuleNotFoundError" in stderr:
            if "cadquery" in stderr:
                diag["root_cause"] = "CadQuery not installed"
                diag["suggestions"].append("pip install cadquery")
            elif "OCP" in stderr:
                diag["root_cause"] = "OCP (OpenCascade) not installed"
                diag["suggestions"].append("conda install -c cadquery cadquery")
            else:
                mod = stderr.split("ModuleNotFoundError")[1].split("'")[1] if "'" in stderr else "unknown"
                diag["root_cause"] = f"Missing module: {mod}"
                diag["suggestions"].append(f"pip install {mod}")

        elif "Standard_Failure" in stderr or "StdFail_NotDone" in stderr:
            diag["root_cause"] = "OpenCascade geometry kernel failure"
            if "fillet" in stderr.lower():
                diag["suggestions"].append("Reduce fillet radius — likely exceeds adjacent edge length / 2")
                diag["suggestions"].append("Try applying fillet before boolean operations")
            elif "shell" in stderr.lower():
                diag["suggestions"].append("Check shell thickness — may exceed minimum dimension / 2")
            elif "boolean" in stderr.lower() or "fuse" in stderr.lower() or "cut" in stderr.lower():
                diag["suggestions"].append("Boolean operation failed — check for non-manifold or overlapping geometry")
                diag["suggestions"].append("Try simplifying shapes before boolean")
            else:
                diag["suggestions"].append("OpenCascade kernel error — simplify geometry or try different approach")

        elif "ValueError" in stderr:
            diag["root_cause"] = "Value error in geometry construction"
            diag["suggestions"].append("Check parameter values — may have zero-length edges or degenerate geometry")

        elif "TypeError" in stderr:
            diag["root_cause"] = "Type error — likely wrong parameter type"
            diag["suggestions"].append("Check that all parameters are correct types (float vs int, list vs tuple)")

        if "Build complete" in stdout:
            diag["build_success"] = True

        return diag


# ═══════════════════════════════════════════════════════════════════════════
# 四、FreeCAD Headless 执行器
# ═══════════════════════════════════════════════════════════════════════════

class _FreeCADExecutor:
    """FreeCAD headless执行器 — 通过freecadcmd子进程"""

    def __init__(self):
        status = _detect_freecad_cmd()
        self.available = status.available
        self.cmd_path = status.path

    def execute(self, code: str, output_dir: str = None) -> ExecutionResult:
        """执行FreeCAD Python代码"""
        t0 = time.time()

        if not self.available:
            return ExecutionResult(
                ok=False, engine="freecad",
                errors=["FreeCADCmd not found"],
            )

        # 使用纯ASCII临时目录 (FreeCAD不支持中文路径)
        td = Path(tempfile.mkdtemp(prefix="dao_fc_"))

        try:
            # 复制backend
            if BACKEND_SCRIPT.exists():
                shutil.copy2(str(BACKEND_SCRIPT), str(td / "freecad_backend.py"))

            script_path = td / "build.py"
            script_path.write_text(code, encoding="utf-8")

            proc = subprocess.run(
                [self.cmd_path, str(script_path)],
                capture_output=True, text=True, timeout=300,
                cwd=str(td),
                creationflags=_NO_WINDOW if sys.platform == "win32" else 0,
            )
            elapsed = round(time.time() - t0, 2)

            output_files = {}
            if output_dir:
                for f in Path(output_dir).glob("*"):
                    if f.suffix in (".stl", ".step", ".FCStd", ".obj", ".brep"):
                        output_files[f.suffix.lstrip(".")] = str(f)

            errors = []
            if proc.returncode != 0:
                stderr = proc.stderr[-2000:] if proc.stderr else ""
                errors.append(f"Exit code {proc.returncode}")
                if stderr:
                    errors.append(stderr)

            return ExecutionResult(
                ok=proc.returncode == 0,
                engine="freecad",
                elapsed_s=elapsed,
                output_files=output_files,
                errors=errors,
                code_path=str(script_path),
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                ok=False, engine="freecad",
                elapsed_s=round(time.time() - t0, 2),
                errors=["Timeout (300s)"],
            )
        except Exception as e:
            return ExecutionResult(
                ok=False, engine="freecad",
                elapsed_s=round(time.time() - t0, 2),
                errors=[str(e)],
            )
        finally:
            shutil.rmtree(str(td), ignore_errors=True)

    def execute_ops(self, ops: List[Dict], label: str = "ops") -> ExecutionResult:
        """执行传统的ops JSON序列 (向后兼容)"""
        t0 = time.time()
        if not self.available:
            return ExecutionResult(ok=False, engine="freecad", errors=["FreeCADCmd not found"])

        td = Path(tempfile.mkdtemp(prefix="dao_ops_"))
        try:
            shutil.copy2(str(BACKEND_SCRIPT), str(td / "freecad_backend.py"))
            cf = td / "cmd.json"
            cf.write_text(json.dumps({"ops": ops}, indent=2, ensure_ascii=True), encoding="utf-8")
            rf = td / "result.json"

            lf = td / "launcher.py"
            lf.write_text(
                f'import sys,json\nfrom pathlib import Path\n'
                f'sys.path.insert(0,r"{td}")\n'
                f'from freecad_backend import run_ops\n'
                f'ops=json.loads(Path(r"{cf}").read_text(encoding="utf-8")).get("ops",[])\n'
                f'r=run_ops(ops)\n'
                f'Path(r"{rf}").write_text(json.dumps(r,indent=2,ensure_ascii=False,default=str),encoding="utf-8")\n',
                encoding="utf-8"
            )

            proc = subprocess.run(
                [self.cmd_path, str(lf)],
                capture_output=True, text=True, timeout=300,
                creationflags=_NO_WINDOW if sys.platform == "win32" else 0,
            )
            elapsed = round(time.time() - t0, 2)

            if rf.exists():
                result_data = json.loads(rf.read_text(encoding="utf-8"))
            else:
                result_data = {"ok": False, "errors": [f"No result. exit={proc.returncode}"]}

            return ExecutionResult(
                ok=result_data.get("ok", False),
                engine="freecad_ops",
                elapsed_s=elapsed,
                output_files={
                    e["op"].replace("export_", ""): e["path"]
                    for e in result_data.get("exports", []) if e.get("ok")
                },
                errors=result_data.get("errors", []),
                warnings=result_data.get("warnings", []),
                diagnostics={"shapes": result_data.get("shapes", {}),
                              "analyses": result_data.get("analyses", [])},
            )
        except Exception as e:
            return ExecutionResult(
                ok=False, engine="freecad_ops",
                elapsed_s=round(time.time() - t0, 2),
                errors=[str(e)],
            )
        finally:
            shutil.rmtree(str(td), ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════
# 五、FreeCAD Remote 执行器
# ═══════════════════════════════════════════════════════════════════════════

class _FreeCADRemoteExecutor:
    """FreeCAD GUI Remote执行器 — 通过HTTP API"""

    def __init__(self, base_url: str = "http://127.0.0.1:18920"):
        self.base_url = base_url
        status = _detect_freecad_remote()
        self.available = status.available

    def execute(self, code: str, output_dir: str = None) -> ExecutionResult:
        """通过Remote Server执行代码"""
        t0 = time.time()
        if not self.available:
            return ExecutionResult(
                ok=False, engine="freecad_remote",
                errors=["FreeCAD Remote Server not running"],
            )

        try:
            import urllib.request
            data = json.dumps({"code": code}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/exec",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read())
            elapsed = round(time.time() - t0, 2)

            return ExecutionResult(
                ok=result.get("ok", False),
                engine="freecad_remote",
                elapsed_s=elapsed,
                errors=result.get("errors", []),
                diagnostics=result,
            )
        except Exception as e:
            return ExecutionResult(
                ok=False, engine="freecad_remote",
                elapsed_s=round(time.time() - t0, 2),
                errors=[str(e)],
            )


# ═══════════════════════════════════════════════════════════════════════════
# 六、验证器
# ═══════════════════════════════════════════════════════════════════════════

class _Validator:
    """输出验证器 — 检查生成的文件是否有效"""

    def __init__(self):
        self.trimesh_ok = _detect_trimesh().available

    def validate(self, output_files: Dict[str, str]) -> Dict:
        """验证输出文件"""
        report = {"valid": True, "checks": [], "stats": {}}

        for fmt, path in output_files.items():
            p = Path(path)
            if not p.exists():
                report["valid"] = False
                report["checks"].append({
                    "file": path, "ok": False,
                    "error": "File not found",
                })
                continue

            size = p.stat().st_size
            if size == 0:
                report["valid"] = False
                report["checks"].append({
                    "file": path, "ok": False,
                    "error": "Empty file",
                })
                continue

            check = {"file": path, "ok": True, "size_bytes": size}

            # STL验证
            if fmt == "stl" and self.trimesh_ok:
                try:
                    import trimesh
                    mesh = trimesh.load(path)
                    check["vertices"] = len(mesh.vertices)
                    check["faces"] = len(mesh.faces)
                    check["watertight"] = mesh.is_watertight
                    check["volume_mm3"] = round(mesh.volume, 2) if mesh.is_watertight else None
                    bb = mesh.bounds
                    check["bounding_box"] = {
                        "min": [round(x, 2) for x in bb[0]],
                        "max": [round(x, 2) for x in bb[1]],
                        "size": [round(bb[1][i] - bb[0][i], 2) for i in range(3)],
                    }
                    if not mesh.is_watertight:
                        check["ok"] = True  # STL can be non-watertight and still usable
                        report["checks"].append({
                            "file": path, "ok": True,
                            "warning": "Mesh is not watertight",
                        })
                except Exception as e:
                    check["warning"] = f"trimesh validation error: {e}"

            report["checks"].append(check)
            report["stats"][fmt] = {"size": size}

        return report


# ═══════════════════════════════════════════════════════════════════════════
# 七、主引擎 — 统一入口
# ═══════════════════════════════════════════════════════════════════════════

class DaoEngine:
    """
    道 · 统一执行引擎

    道生一: 从单一入口统一所有建模引擎
    一生二: CadQuery (首选) + FreeCAD (备选)
    二生三: 执行 + 验证 + 反馈
    三生万物: 任何设计意图都能落地为实体

    Usage:
        engine = DaoEngine()
        status = engine.check()   # 环境检查
        result = engine.run(code_result)  # 执行代码
        result = engine.run_cadquery(code)  # 直接执行CadQuery代码
        result = engine.run_ops(ops)  # 向后兼容ops执行
    """

    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._cq = _CadQueryExecutor()
        self._fc = _FreeCADExecutor()
        self._fc_remote = _FreeCADRemoteExecutor()
        self._validator = _Validator()
        self._history = []

        # 万法归一连接管理器 (lazy init)
        self._fc_conn = None

    def _get_connection(self):
        """获取 FreeCAD Connection Manager (lazy init)"""
        if self._fc_conn is None:
            try:
                from freecad_connection import FreeCADConnection
                self._fc_conn = FreeCADConnection()
                self._fc_conn.connect()
            except Exception:
                self._fc_conn = None
        return self._fc_conn

    def check(self) -> Dict:
        """环境检查 — 返回所有引擎状态"""
        result = {
            "version": __version__,
            "engines": {
                "cadquery": asdict(_detect_cadquery()),
                "freecad_cmd": asdict(_detect_freecad_cmd()),
                "freecad_remote": asdict(_detect_freecad_remote()),
                "openscad": asdict(_detect_openscad()),
                "trimesh": asdict(_detect_trimesh()),
            },
            "output_dir": str(self.output_dir),
            "backend_script": str(BACKEND_SCRIPT),
            "backend_exists": BACKEND_SCRIPT.exists(),
        }
        # 连接管理器状态
        conn = self._get_connection()
        if conn:
            result["connection_manager"] = conn.status().to_dict()
        return result

    def run(self, code_result, output_dir: str = None, validate: bool = True) -> ExecutionResult:
        """
        执行代码生成结果。

        Args:
            code_result: CodeResult 或包含 code 和 engine 的对象
            output_dir: 输出目录
            validate: 是否验证输出
        """
        out = output_dir or str(self.output_dir)
        engine = getattr(code_result, "engine", "cadquery")
        code = getattr(code_result, "code", "")

        if engine == "cadquery":
            result = self._cq.execute(code, out)
        elif engine in ("freecad", "freecad_cmd"):
            result = self._fc.execute(code, out)
        elif engine == "freecad_remote":
            result = self._fc_remote.execute(code, out)
        else:
            # 降级: cadquery → freecad → error
            if self._cq.available:
                result = self._cq.execute(code, out)
            elif self._fc.available:
                result = self._fc.execute(code, out)
            else:
                result = ExecutionResult(
                    ok=False, engine="none",
                    errors=["No modeling engine available"],
                )

        # 验证
        if validate and result.ok and result.output_files:
            validation = self._validator.validate(result.output_files)
            result.diagnostics["validation"] = validation
            if not validation["valid"]:
                result.warnings.append("Output validation found issues")

        # 记录历史
        self._record(result)
        return result

    def run_cadquery(self, code: str, output_dir: str = None,
                     validate: bool = True) -> ExecutionResult:
        """直接执行CadQuery代码"""
        out = output_dir or str(self.output_dir)
        result = self._cq.execute(code, out)

        if validate and result.ok and result.output_files:
            validation = self._validator.validate(result.output_files)
            result.diagnostics["validation"] = validation

        self._record(result)
        return result

    def run_freecad(self, code: str, output_dir: str = None) -> ExecutionResult:
        """直接执行FreeCAD代码"""
        out = output_dir or str(self.output_dir)
        result = self._fc.execute(code, out)
        self._record(result)
        return result

    def run_ops(self, ops: List[Dict], label: str = "ops") -> ExecutionResult:
        """向后兼容: 执行传统的ops JSON序列 (通过连接管理器自动修复STEP导入)"""
        # 优先使用连接管理器 (自动修复 STEP import 等)
        conn = self._get_connection()
        if conn and conn.status().available:
            t0 = time.time()
            try:
                result_data = conn.execute_ops(ops)
                elapsed = round(time.time() - t0, 2)
                result = ExecutionResult(
                    ok=result_data.get("ok", False),
                    engine=f"fc_conn:{conn.status().mode}",
                    elapsed_s=elapsed,
                    output_files={
                        e["op"].replace("export_", ""): e["path"]
                        for e in result_data.get("exports", []) if e.get("ok")
                    },
                    errors=result_data.get("errors", []),
                    warnings=result_data.get("warnings", []),
                    diagnostics={"shapes": result_data.get("shapes", {}),
                                  "analyses": result_data.get("analyses", [])},
                )
                self._record(result)
                return result
            except Exception:
                pass  # fallback to direct executor

        result = self._fc.execute_ops(ops, label)
        self._record(result)
        return result

    def run_remote(self, code: str) -> ExecutionResult:
        """通过FreeCAD Remote Server执行"""
        result = self._fc_remote.execute(code)
        self._record(result)
        return result

    def import_step(self, path: str, output_brep: str = None) -> Dict:
        """导入 STEP 文件 (绕过 FreeCAD 1.0 headless 挂起问题)"""
        conn = self._get_connection()
        if conn:
            return conn.import_step(path, output_brep)
        return {"ok": False, "error": "No FreeCAD connection available"}

    def import_iges(self, path: str, output_brep: str = None) -> Dict:
        """导入 IGES 文件"""
        conn = self._get_connection()
        if conn:
            return conn.import_iges(path, output_brep)
        return {"ok": False, "error": "No FreeCAD connection available"}

    def convert(self, src: str, dst: str) -> Dict:
        """格式转换: STEP→STL, FCStd→STEP, etc."""
        conn = self._get_connection()
        if conn:
            return conn.convert(src, dst)
        return {"ok": False, "error": "No FreeCAD connection available"}

    # ── 完整管道: 从spec到输出 ────────────────────────────────────

    def build_from_spec(self, spec: Dict, output_dir: str = None) -> Dict:
        """
        完整管道: 设计规格 → 编译 → 代码生成 → 执行 → 验证

        Args:
            spec: 设计规格字典 (DesignIntentCompiler.compile 的输入格式)
            output_dir: 输出目录

        Returns:
            包含全部结果的字典
        """
        from design_intent_compiler import DesignIntentCompiler
        from parametric_codegen import ParametricCodegen

        out = output_dir or str(self.output_dir)

        # 1. 编译
        compiler = DesignIntentCompiler()
        tree, report, plan = compiler.compile_and_plan(spec)

        if not report.feasible:
            return {
                "ok": False,
                "phase": "preflight",
                "errors": [f"[{i.severity}] {i.part}: {i.message}" for i in report.errors],
                "tree": tree.to_dict(),
                "preflight": report.to_dict(),
            }

        # 2. 代码生成
        codegen = ParametricCodegen()
        code_result = codegen.generate(tree, plan, output_dir=out)

        # 3. 执行
        exec_result = self.run(code_result, output_dir=out)

        # 4. 如果CadQuery失败，尝试FreeCAD降级
        if not exec_result.ok and exec_result.engine == "cadquery" and self._fc.available:
            codegen_fc = ParametricCodegen(engine="freecad")
            code_result_fc = codegen_fc.generate(tree, plan, output_dir=out)
            exec_result = self.run(code_result_fc, output_dir=out)
            exec_result.warnings.append("Degraded from CadQuery to FreeCAD")

        return {
            "ok": exec_result.ok,
            "phase": "complete" if exec_result.ok else "execution",
            "tree": tree.to_dict(),
            "preflight": report.to_dict(),
            "plan": plan.to_dict(),
            "code": code_result.code,
            "execution": exec_result.to_dict(),
            "output_files": exec_result.output_files,
        }

    # ── 验证 ──────────────────────────────────────────────────────

    def validate_files(self, files: Dict[str, str] = None) -> Dict:
        """验证输出文件"""
        if files is None:
            # 自动发现输出目录中的文件
            files = {}
            for f in self.output_dir.glob("*"):
                if f.suffix in (".stl", ".step", ".obj"):
                    files[f.suffix.lstrip(".")] = str(f)
        return self._validator.validate(files)

    # ── 历史 ──────────────────────────────────────────────────────

    def _record(self, result: ExecutionResult):
        """记录执行历史"""
        self._history.append({
            "id": uuid.uuid4().hex[:12],
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ok": result.ok,
            "engine": result.engine,
            "elapsed_s": result.elapsed_s,
            "files": len(result.output_files),
            "errors": len(result.errors),
        })
        self._history = self._history[-200:]

    def history(self, n: int = 20) -> List[Dict]:
        return self._history[-n:]


# ═══════════════════════════════════════════════════════════════════════════
# 八、CLI
# ═══════════════════════════════════════════════════════════════════════════

def _cli():
    import sys
    args = sys.argv[1:]

    engine = DaoEngine()

    if not args or args[0] == "check":
        status = engine.check()
        print(json.dumps(status, indent=2, ensure_ascii=False))

    elif args[0] == "demo":
        spec = {
            "name": "demo_box",
            "description": "带圆角和孔的盒子",
            "process": "fdm",
            "parts": [{
                "name": "box",
                "function": "contain",
                "dims": {"L": 40, "W": 30, "H": 20, "wall": 2},
                "features": [
                    {"name": "body", "type": "body_box", "params": {"L": 40, "W": 30, "H": 20}},
                    {"name": "fillet", "type": "fillet", "params": {"radius": 3}},
                    {"name": "shell", "type": "shell", "params": {"thickness": 2}},
                    {"name": "mount_hole", "type": "hole", "params": {"d": 3.4, "depth": "thru"}},
                ],
            }],
        }
        result = engine.build_from_spec(spec)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    elif args[0] == "build" and len(args) > 1:
        spec = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        result = engine.build_from_spec(spec)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    elif args[0] == "validate":
        result = engine.validate_files()
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        print("道 · DaoEngine v" + __version__)
        print()
        print("Usage:")
        print("  python dao_engine.py check           # 环境检查")
        print("  python dao_engine.py demo            # 演示构建")
        print("  python dao_engine.py build <spec.json>  # 从规格构建")
        print("  python dao_engine.py validate        # 验证输出文件")


if __name__ == "__main__":
    _cli()
