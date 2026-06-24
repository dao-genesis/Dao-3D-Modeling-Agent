#!/usr/bin/env python3
"""
FreeCAD GUI Launcher — 从系统Python启动FreeCAD GUI进行可视化建模

核心能力:
  1. launch_gui(ops)     — 构建ops → 启动FreeCAD GUI → 可视化展示全过程
  2. build_gui(type, p)  — 参数化建模 → GUI展示
  3. demo()              — 演示：构建复杂装配体并在GUI中展示

用法:
  python freecad_gui_launcher.py demo                    # 启动演示
  python freecad_gui_launcher.py build box --params '{}'  # 参数化建模
  python freecad_gui_launcher.py ops ops.json            # 执行ops文件

架构:
  系统Python (本文件)
       ↓ 写入 cmd.json + 设置环境变量
  freecad.exe freecad_gui_macro.py
       ↓ 在FreeCAD GUI内执行建模
  结果写入 result.json + 保存 .FCStd
       ↓ 系统Python读取结果
  返回给调用者
"""

import os
import sys
import json
import subprocess
import tempfile
import time
import shutil
import uuid
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

SCRIPT_DIR = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
ROOT_DIR = _DAO_ROOT
# ═══════════════════════════════════════════════════════════════════

MACRO_SCRIPT = SCRIPT_DIR / "freecad_gui_macro.py"   # 同层 10-反笙_FreeCAD

# FreeCAD GUI 可执行文件路径
FREECAD_GUI_PATHS = [
    r"D:\安装的软件\FreeCAD 1.0\bin\freecad.exe",
    r"D:\安装的软件\FreeCAD 0.21\bin\FreeCAD.exe",
    r"C:\Program Files\FreeCAD 1.0\bin\freecad.exe",
    r"C:\Program Files\FreeCAD\bin\FreeCAD.exe",
]

OUTPUT_DIR = _dao_paths.PROJECTS / "fc_output"


def find_freecad_gui() -> Optional[str]:
    """查找 FreeCAD GUI 可执行文件"""
    for p in FREECAD_GUI_PATHS:
        if Path(p).exists():
            return p
    found = shutil.which("freecad") or shutil.which("FreeCAD")
    return found


class FreeCADGUILauncher:
    """FreeCAD GUI 启动器 — 直接依赖 FreeCAD 底层，可视化展示全过程"""

    def __init__(self, freecad_gui: str = None, output_dir: str = None):
        self.gui_exe = freecad_gui or find_freecad_gui()
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.macro_path = MACRO_SCRIPT

    def available(self) -> bool:
        return self.gui_exe is not None and Path(self.gui_exe).exists()

    def launch_gui(self, ops: List[Dict], label: str = "model",
                   auto_close: bool = False, wait: bool = True,
                   timeout: int = 600, save_fcstd: bool = True) -> Dict:
        """
        核心方法：启动 FreeCAD GUI 执行操作序列

        Args:
            ops: 操作列表（与 freecad_backend.py 兼容）
            label: 模型标签
            auto_close: 执行完是否自动关闭 FreeCAD
            wait: 是否等待 FreeCAD 退出
            timeout: 超时秒数
            save_fcstd: 是否保存 FCStd 文件

        Returns:
            结果字典
        """
        if not self.available():
            return {"ok": False, "error": "FreeCAD GUI not found",
                    "searched": FREECAD_GUI_PATHS}

        t0 = time.time()
        session_id = uuid.uuid4().hex[:8]
        tmp_dir = Path(tempfile.gettempdir()) / f"fcg_{session_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 准备文件路径
            cmd_file = tmp_dir / "cmd.json"
            result_file = tmp_dir / "result.json"
            fcstd_path = str(self.output_dir / f"{label}.FCStd") if save_fcstd else ""
            macro_copy = tmp_dir / "freecad_gui_macro.py"

            # 复制 macro + backend 到临时目录（避免中文路径）
            shutil.copy2(str(self.macro_path), str(macro_copy))
            # 动态链接：复制 backend 到同一目录，供 macro 导入
            backend_src = SCRIPT_DIR / "freecad_backend.py"
            if backend_src.exists():
                shutil.copy2(str(backend_src), str(tmp_dir / "freecad_backend.py"))

            # 写入 ops
            cmd_file.write_text(
                json.dumps({"ops": ops}, indent=2, ensure_ascii=True),
                encoding="utf-8"
            )

            # 构建环境变量
            env = os.environ.copy()
            env["FC_GUI_CMD_FILE"] = str(cmd_file)
            env["FC_GUI_RESULT_FILE"] = str(result_file)
            env["FC_GUI_FCSTD_PATH"] = fcstd_path
            env["FC_GUI_AUTO_CLOSE"] = "1" if auto_close else "0"
            env["FC_GUI_DOC_NAME"] = label.replace(" ", "_")[:20]

            # 启动 FreeCAD GUI
            print(f"[Launcher] Starting FreeCAD GUI: {self.gui_exe}")
            print(f"[Launcher] Macro: {macro_copy}")
            print(f"[Launcher] Ops: {len(ops)} operations")

            proc = subprocess.Popen(
                [self.gui_exe, str(macro_copy)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            if wait:
                try:
                    stdout, stderr = proc.communicate(timeout=timeout)
                    stdout_text = stdout.decode("utf-8", errors="replace").strip()
                    stderr_text = stderr.decode("utf-8", errors="replace").strip()
                except subprocess.TimeoutExpired:
                    proc.kill()
                    return {"ok": False, "error": f"Timeout after {timeout}s",
                            "label": label}

                elapsed = round(time.time() - t0, 2)

                # 读取结果
                if result_file.exists():
                    try:
                        result = json.loads(result_file.read_text(encoding="utf-8"))
                        result["elapsed_s"] = elapsed
                        result["label"] = label
                        result["gui_mode"] = True
                        return result
                    except json.JSONDecodeError as e:
                        return {"ok": False, "error": f"Bad result JSON: {e}",
                                "stdout": stdout_text[:500],
                                "stderr": stderr_text[:500],
                                "elapsed_s": elapsed, "label": label}

                return {
                    "ok": False,
                    "error": "No result file produced",
                    "returncode": proc.returncode,
                    "stdout": stdout_text[:1000] if 'stdout_text' in dir() else "",
                    "stderr": stderr_text[:500] if 'stderr_text' in dir() else "",
                    "elapsed_s": elapsed,
                    "label": label,
                }
            else:
                # 非阻塞模式：启动后立即返回
                print(f"[Launcher] FreeCAD GUI launched (PID: {proc.pid}), not waiting.")
                return {
                    "ok": True,
                    "pid": proc.pid,
                    "label": label,
                    "gui_mode": True,
                    "blocking": False,
                    "result_file": str(result_file),
                    "fcstd_path": fcstd_path,
                    "message": "FreeCAD GUI is running. Close it when done viewing.",
                }

        except Exception as e:
            return {"ok": False, "error": str(e), "label": label}
        finally:
            if wait:
                shutil.rmtree(str(tmp_dir), ignore_errors=True)

    def build_gui(self, model_type: str, params: Dict = None,
                  formats: List[str] = None, auto_close: bool = False) -> Dict:
        """
        参数化建模 + GUI 可视化

        与 FCModelBuilder.build() 兼容的参数，但使用 GUI 模式展示
        """
        if params is None:
            params = {}
        if formats is None:
            formats = ["stl", "step"]

        # 导入 fc_model_builder 来生成 ops（复用已有逻辑）
        sys.path.insert(0, str(SCRIPT_DIR))
        try:
            from fc_model_builder import FCModelBuilder
            builder = FCModelBuilder()
            # 使用 _build_xxx 方法获取 ops
            builders_map = {
                "box": builder._build_box,
                "rounded_box": builder._build_rounded_box,
                "cylinder": builder._build_cylinder,
                "sphere": builder._build_sphere,
                "cone": builder._build_cone,
                "torus": builder._build_torus,
                "tube": builder._build_tube,
                "hex_bolt": builder._build_hex_bolt,
                "hex_nut": builder._build_hex_nut,
                "washer": builder._build_washer,
                "bracket": builder._build_bracket,
                "enclosure": builder._build_enclosure,
                "gear_spur": builder._build_gear_spur,
                "bearing_seat": builder._build_bearing_seat,
            }
            fn = builders_map.get(model_type.lower())
            if fn is None:
                return {"ok": False,
                        "error": f"Unknown model type: '{model_type}'. "
                                 f"Available: {list(builders_map.keys())}"}
            ops, paths = fn(params, formats)
        except ImportError:
            # Fallback: 构建基本 ops
            ops, paths = self._basic_ops(model_type, params, formats)

        # 添加 FCStd 导出
        fcstd_path = str(self.output_dir / f"{model_type}.FCStd")
        ops.append({"op": "export_fcstd", "path": fcstd_path})

        result = self.launch_gui(ops, label=model_type, auto_close=auto_close,
                                 wait=not auto_close, save_fcstd=True)
        result["model_type"] = model_type
        result["params"] = params
        result["output_files"] = paths
        return result

    def _basic_ops(self, model_type: str, params: Dict,
                   formats: List[str]) -> tuple:
        """基本 ops 构建（fallback）"""
        ops = []
        paths = {}
        shape_id = model_type

        if model_type == "box":
            ops.append({"op": "make_box", "id": shape_id,
                        "L": params.get("L", 20),
                        "W": params.get("W", 15),
                        "H": params.get("H", 10)})
        elif model_type == "cylinder":
            ops.append({"op": "make_cylinder", "id": shape_id,
                        "R": params.get("R", 10),
                        "H": params.get("H", 20)})
        elif model_type == "sphere":
            ops.append({"op": "make_sphere", "id": shape_id,
                        "R": params.get("R", 10)})
        else:
            ops.append({"op": "make_box", "id": shape_id,
                        "L": 20, "W": 15, "H": 10})

        for fmt in formats:
            p = str(self.output_dir / f"{model_type}.{fmt}")
            paths[fmt] = p
            ops.append({"op": f"export_{fmt}", "shape": shape_id, "path": p})

        ops.append({"op": "shape_info", "shape": shape_id})
        return ops, paths

    def demo_assembly(self) -> Dict:
        """
        演示：在 FreeCAD GUI 中构建复杂装配体

        展示：六角螺栓 + 螺母 + 外壳 + 齿轮 + 布尔运算
        """
        output_base = str(self.output_dir / "demo_assembly")

        ops = [
            # 底板
            {"op": "make_box", "id": "base_plate",
             "L": 100, "W": 80, "H": 5, "pos": [0, 0, 0]},

            # 外壳（透明展示内部）
            {"op": "make_enclosure", "id": "enclosure",
             "L": 80, "W": 60, "H": 40, "wall": 2, "open_top": True},
            {"op": "translate", "id": "enclosure_placed",
             "shape": "enclosure", "delta": [10, 10, 5]},

            # 四个安装孔
            {"op": "make_cylinder", "id": "hole1", "R": 2, "H": 10,
             "pos": [10, 10, -2]},
            {"op": "make_cylinder", "id": "hole2", "R": 2, "H": 10,
             "pos": [90, 10, -2]},
            {"op": "make_cylinder", "id": "hole3", "R": 2, "H": 10,
             "pos": [10, 70, -2]},
            {"op": "make_cylinder", "id": "hole4", "R": 2, "H": 10,
             "pos": [90, 70, -2]},
            {"op": "cut", "id": "base_drilled", "base": "base_plate",
             "tools": ["hole1", "hole2", "hole3", "hole4"]},

            # 圆角底板
            {"op": "fillet", "id": "base_final", "shape": "base_drilled",
             "radius": 2},

            # 中心轴
            {"op": "make_cylinder", "id": "shaft",
             "R": 5, "H": 35, "pos": [50, 40, 5]},

            # 齿轮（在轴上）
            {"op": "make_gear_spur", "id": "gear",
             "teeth": 16, "module": 1.5, "width": 8, "hub_r": 5.2},
            {"op": "translate", "id": "gear_placed",
             "shape": "gear", "delta": [50, 40, 20]},

            # 螺栓
            {"op": "make_hex_bolt", "id": "bolt1",
             "diameter": 4, "length": 12},
            {"op": "translate", "id": "bolt1_placed",
             "shape": "bolt1", "delta": [10, 10, 5]},

            # 螺母
            {"op": "make_hex_nut", "id": "nut1",
             "diameter": 4, "thickness": 3},
            {"op": "translate", "id": "nut1_placed",
             "shape": "nut1", "delta": [10, 10, -5]},

            # 导出
            {"op": "export_step", "shape": "base_final",
             "path": f"{output_base}_base.step"},
            {"op": "export_stl", "shape": "base_final",
             "path": f"{output_base}_base.stl"},
            {"op": "export_step", "shape": "gear_placed",
             "path": f"{output_base}_gear.step"},
            {"op": "export_stl", "shape": "gear_placed",
             "path": f"{output_base}_gear.stl"},

            # 分析
            {"op": "shape_info", "shape": "base_final"},
            {"op": "shape_info", "shape": "gear_placed"},
            {"op": "shape_info", "shape": "enclosure_placed"},
        ]

        print("=" * 60)
        print("  FreeCAD GUI Demo — 装配体可视化展示")
        print("  底板 + 外壳 + 轴 + 齿轮 + 螺栓螺母")
        print("=" * 60)

        return self.launch_gui(ops, label="demo_assembly",
                               auto_close=False, wait=False)

    def check_environment(self) -> Dict:
        """环境检查"""
        result = {
            "gui_available": self.available(),
            "gui_exe": self.gui_exe,
            "macro_path": str(self.macro_path),
            "macro_exists": self.macro_path.exists(),
            "output_dir": str(self.output_dir),
        }
        # 检查所有已知路径
        for p in FREECAD_GUI_PATHS:
            result[f"path_{Path(p).stem}"] = Path(p).exists()
        return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(
        description="FreeCAD GUI Launcher — 可视化3D建模")
    sub = parser.add_subparsers(dest="cmd")

    # check
    sub.add_parser("check", help="环境检查")

    # demo
    sub.add_parser("demo", help="启动装配体演示")

    # build
    bp = sub.add_parser("build", help="参数化建模 + GUI展示")
    bp.add_argument("type", help="模型类型 (box/cylinder/enclosure/gear_spur/...)")
    bp.add_argument("--params", default="{}", help="JSON 参数")
    bp.add_argument("--formats", default="stl,step", help="导出格式")
    bp.add_argument("--auto-close", action="store_true", help="完成后自动关闭")

    # ops
    op = sub.add_parser("ops", help="执行 ops JSON 文件")
    op.add_argument("file", help="JSON 文件路径")
    op.add_argument("--label", default="custom", help="标签")
    op.add_argument("--auto-close", action="store_true")

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    launcher = FreeCADGUILauncher()

    if args.cmd == "check":
        info = launcher.check_environment()
        print(json.dumps(info, indent=2, ensure_ascii=False))

    elif args.cmd == "demo":
        result = launcher.demo_assembly()
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.cmd == "build":
        params = json.loads(args.params)
        formats = [f.strip() for f in args.formats.split(",")]
        result = launcher.build_gui(args.type, params, formats,
                                    auto_close=args.auto_close)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.cmd == "ops":
        with open(args.file, encoding="utf-8") as f:
            data = json.load(f)
        ops = data if isinstance(data, list) else data.get("ops", [])
        result = launcher.launch_gui(ops, label=args.label,
                                     auto_close=args.auto_close,
                                     wait=not args.auto_close)
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
