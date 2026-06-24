#!/usr/bin/env python3
"""
FreeCAD GUI Macro v2.0 — 动态链接架构

核心原理：
  GUI macro 不再复制 backend 的 ops 引擎代码。
  而是动态导入 freecad_backend.py 的 run_ops()，逐 op 执行，
  每步执行后将新生成的 shape 添加到 FreeCAD GUI 文档中并着色。

  这实现了：
  - 100% ops 兼容（backend 支持 60+ ops，GUI 全部可用）
  - 零代码重复（所有 ops 逻辑只在 backend 中维护一份）
  - GUI 只负责可视化层：创建文档对象、着色、控制可见性

用法（由 launcher / fc_model_builder 自动调用）:
    freecad.exe freecad_gui_macro.py

环境变量:
    FC_GUI_CMD_FILE    — ops JSON 文件路径
    FC_GUI_RESULT_FILE — 结果 JSON 文件路径
    FC_GUI_FCSTD_PATH  — 保存的 FCStd 文件路径（可选）
    FC_GUI_AUTO_CLOSE  — 设为 "1" 则自动关闭（默认保持打开供查看）
"""

import sys
import os
import json
import time
import traceback
from pathlib import Path

# ─── 动态链接 backend ──────────────────────────────────────────────────
# freecad_backend.py 被复制到与本 macro 相同的临时目录
_MACRO_DIR = Path(__file__).parent.resolve()
if str(_MACRO_DIR) not in sys.path:
    sys.path.insert(0, str(_MACRO_DIR))

from freecad_backend import run_ops, _shape_summary as _backend_shape_summary

# ─── 颜色表：让每个零件都有独特颜色 ─────────────────────────────────────
COLORS = [
    (0.2, 0.6, 1.0),    # 天蓝
    (1.0, 0.4, 0.2),    # 橙红
    (0.3, 0.8, 0.3),    # 翠绿
    (0.9, 0.7, 0.1),    # 金黄
    (0.7, 0.3, 0.9),    # 紫罗兰
    (0.1, 0.8, 0.8),    # 青色
    (1.0, 0.5, 0.7),    # 粉红
    (0.5, 0.5, 0.5),    # 银灰
    (0.8, 0.2, 0.2),    # 深红
    (0.2, 0.4, 0.8),    # 宝蓝
]
RESULT_COLOR = (0.3, 0.7, 1.0)        # 最终结果：亮蓝
WIRE_COLOR = (1.0, 1.0, 0.0)          # 线框：黄色
METALLIC_COLOR = (0.7, 0.7, 0.7)      # 金属件：银灰
GEAR_COLOR = (0.8, 0.6, 0.2)          # 齿轮：铜色

# ─── Op 分类（用于自动着色和消耗追踪） ────────────────────────────────
_BOOLEAN_OPS = frozenset({"fuse", "cut", "common", "section", "occ_boolean"})
_MODIFIER_OPS = frozenset({
    "fillet", "chamfer", "shell", "offset3d", "occ_fillet",
    "occ_thick_solid", "partdesign_fillet", "partdesign_pad",
    "partdesign_pocket", "boolean_split", "make_shell_from_solid",
})
_TRANSFORM_OPS = frozenset({
    "translate", "rotate", "scale", "mirror", "make_scale",
})
_CONSUME_SOURCE_OPS = frozenset({
    "extrude", "revolve", "extrude_taper",
})
_WIRE_OPS = frozenset({
    "make_polygon_wire", "make_circle_wire", "make_bspline",
    "make_spiral", "make_helix", "make_long_helix",
    "make_polygon_3d", "make_bezier_curve", "make_catenary",
    "make_torus_knot",
})
_METALLIC_OPS = frozenset({
    "make_hex_bolt", "make_hex_nut", "make_bearing_seat",
    "make_thread", "make_spring",
})
_GEAR_OPS = frozenset({"make_gear_spur", "make_gear_rack"})
_ENCLOSURE_OPS = frozenset({"make_enclosure"})
_EXPORT_OPS = frozenset({
    "export_stl", "export_step", "export_brep", "export_obj",
    "export_dxf", "export_svg", "export_iges", "export_fcstd",
    "write_fcstd",
})
_ANALYSIS_OPS = frozenset({
    "shape_info", "check_shape", "brep_string",
    "mass_properties", "draft_angle", "shape_analysis_3dprint",
    "measure_distance",
})


def _get_consumed_ids(op_spec):
    """Determine which shape IDs are consumed (become intermediate) by this op."""
    op = op_spec.get("op", "")
    consumed = set()

    if op in _BOOLEAN_OPS:
        if op in ("fuse", "common", "section"):
            for sid in op_spec.get("shapes", []):
                consumed.add(sid)
        elif op in ("cut", "occ_boolean"):
            base = op_spec.get("base")
            if base:
                consumed.add(base)
            for tid in op_spec.get("tools", op_spec.get("tool_ids", [])):
                if isinstance(tid, str):
                    consumed.add(tid)
    elif op in _MODIFIER_OPS:
        sh_id = op_spec.get("shape", op_spec.get("base"))
        if sh_id:
            consumed.add(sh_id)
        if op == "partdesign_pocket":
            prof = op_spec.get("profile")
            if prof:
                consumed.add(prof)
    elif op in _TRANSFORM_OPS:
        sh_id = op_spec.get("shape")
        if sh_id:
            consumed.add(sh_id)
    elif op in _CONSUME_SOURCE_OPS:
        sh_id = op_spec.get("shape")
        if sh_id:
            consumed.add(sh_id)
    elif op == "loft":
        for sid in op_spec.get("sections", []):
            consumed.add(sid)
    elif op == "make_loft_multi":
        for sid in op_spec.get("profiles", []):
            consumed.add(sid)
    elif op == "partdesign_pad":
        face = op_spec.get("face")
        if face:
            consumed.add(face)

    return consumed


def _get_op_color(op):
    """Determine visualization color and transparency for an op type."""
    if op in _BOOLEAN_OPS or op in _MODIFIER_OPS:
        return RESULT_COLOR, 0
    elif op in _METALLIC_OPS:
        return METALLIC_COLOR, 0
    elif op in _GEAR_OPS:
        return GEAR_COLOR, 0
    elif op in _WIRE_OPS:
        return WIRE_COLOR, 0
    elif op in _ENCLOSURE_OPS:
        return None, 30  # use cycling color with transparency
    else:
        return None, 0  # use cycling color


def _set_view_object_color(doc, obj_name, color_rgb, transparency=0):
    """设置对象的显示颜色和透明度"""
    try:
        import FreeCADGui as Gui
        vobj = Gui.getDocument(doc.Name).getObject(obj_name)
        if vobj is not None:
            vobj.ShapeColor = color_rgb[:3]
            if transparency > 0:
                vobj.Transparency = int(transparency)
            vobj.LineWidth = 1.5
    except Exception:
        pass


def _set_visibility(doc, obj_name, visible=True):
    """设置对象的可见性"""
    try:
        import FreeCADGui as Gui
        vobj = Gui.getDocument(doc.Name).getObject(obj_name)
        if vobj is not None:
            vobj.Visibility = visible
    except Exception:
        pass


def _setup_3d_view():
    """设置3D视口：适配所有对象 + 等轴测视角"""
    try:
        import FreeCADGui as Gui
        view = Gui.ActiveDocument.ActiveView
        view.viewIsometric()
        view.fitAll()
        import FreeCAD as App
        pref = App.ParamGet("User parameter:BaseApp/Preferences/View")
        pref.SetUnsigned("BackgroundColor3", 0x1a1a2e00)
        pref.SetUnsigned("BackgroundColor4", 0x16213e00)
    except Exception:
        pass


def run_gui_ops(ops, doc_name="DaoModel"):
    """
    核心: 在 FreeCAD GUI 中执行操作序列，逐步构建并可视化

    动态链接架构：
      1. 逐 op 调用 backend 的 run_ops([op], shapes, results)
      2. 检测新增的 shape
      3. 将新 shape 添加到 GUI 文档并着色
      4. 追踪消耗关系，最终隐藏中间体

    返回 (doc, results) — 与旧版兼容
    """
    import FreeCAD as App
    import Part

    # 共享状态 — 传递给 backend 的 run_ops
    shapes = {}       # id → Part.Shape (backend 直接操作此 dict)
    results = {
        "ok": True,
        "shapes": {},
        "exports": [],
        "analyses": [],
        "errors": [],
        "gui_mode": True,
    }

    # GUI 状态
    doc = App.newDocument(doc_name)
    doc_objects = {}   # id → FreeCAD Document Object
    color_idx = 0
    consumed_ids = set()
    final_shape_ids = set()

    for i, op_spec in enumerate(ops):
        op = op_spec.get("op", "")
        op_id = op_spec.get("id")

        # ── Snapshot: shapes before execution ──────────────────────
        prev_shape_ids = set(shapes.keys())

        # ── Execute op through backend's COMPLETE engine ──────────
        # run_ops processes [op_spec] with shared shapes/results dicts
        run_ops([op_spec], shapes=shapes, results=results)

        # ── Detect new shapes ─────────────────────────────────────
        new_shape_ids = set(shapes.keys()) - prev_shape_ids

        # ── Track consumed shapes ─────────────────────────────────
        consumed_ids.update(_get_consumed_ids(op_spec))

        # ── Track final shapes (exported/analyzed) ────────────────
        if op in _EXPORT_OPS:
            sh_id = op_spec.get("shape")
            if sh_id:
                final_shape_ids.add(sh_id)
        elif op in _ANALYSIS_OPS:
            sh_id = op_spec.get("shape")
            if sh_id:
                final_shape_ids.add(sh_id)

        # ── Add new shapes to GUI document with visualization ─────
        for new_id in new_shape_ids:
            sh = shapes.get(new_id)
            if sh is None:
                continue
            # Skip non-shape entries (analysis results stored as dicts)
            if not hasattr(sh, 'isNull'):
                continue
            if sh.isNull():
                continue

            # Sanitize name for FreeCAD document object
            safe_name = str(new_id).replace(" ", "_")[:40]
            try:
                obj = doc.addObject("Part::Feature", safe_name)
                obj.Shape = sh
                doc_objects[new_id] = obj
            except Exception as e:
                results.setdefault("warnings", []).append(
                    f"GUI: failed to add '{new_id}' to document: {e}")
                continue

            # Determine color
            color, transparency = _get_op_color(op)
            if color is None:
                color = COLORS[color_idx % len(COLORS)]
                color_idx += 1
            _set_view_object_color(doc, safe_name, color, transparency)

    # ── 视觉优化：隐藏中间体，突出最终结果 ──────────────────────────
    doc.recompute()

    all_ids = set(doc_objects.keys())
    unconsumed = all_ids - consumed_ids
    final_ids = unconsumed | final_shape_ids

    for sid in all_ids:
        safe_name = str(sid).replace(" ", "_")[:40]
        if sid in final_ids:
            _set_visibility(doc, safe_name, True)
            if sid not in final_shape_ids:
                _set_view_object_color(doc, safe_name, RESULT_COLOR)
        else:
            _set_visibility(doc, safe_name, False)

    # 设置3D视角
    _setup_3d_view()

    return doc, results


def main():
    """主入口：从环境变量读取配置，执行操作，写入结果"""
    import FreeCAD as App

    cmd_file = os.environ.get("FC_GUI_CMD_FILE", "")
    result_file = os.environ.get("FC_GUI_RESULT_FILE", "")
    fcstd_path = os.environ.get("FC_GUI_FCSTD_PATH", "")
    auto_close = os.environ.get("FC_GUI_AUTO_CLOSE", "0") == "1"
    doc_name = os.environ.get("FC_GUI_DOC_NAME", "DaoModel")

    if not cmd_file or not Path(cmd_file).exists():
        print(f"[FreeCAD GUI Macro] ERROR: FC_GUI_CMD_FILE not set or not found: {cmd_file}")
        return

    try:
        cmd_data = json.loads(Path(cmd_file).read_text(encoding="utf-8"))
        ops = cmd_data.get("ops", [])
    except Exception as e:
        print(f"[FreeCAD GUI Macro] ERROR: Failed to read cmd file: {e}")
        return

    print(f"[FreeCAD GUI Macro] v2.0 Dynamic Linking | {len(ops)} ops")
    t0 = time.time()

    doc, results = run_gui_ops(ops, doc_name)
    results["elapsed_s"] = round(time.time() - t0, 2)

    # 保存 FCStd
    if fcstd_path:
        try:
            Path(fcstd_path).parent.mkdir(parents=True, exist_ok=True)
            doc.saveAs(fcstd_path)
            results["fcstd_path"] = fcstd_path
            results["fcstd_ok"] = Path(fcstd_path).exists()
            print(f"[FreeCAD GUI Macro] Saved: {fcstd_path}")
        except Exception as e:
            results["errors"].append(f"Failed to save FCStd: {e}")

    # 写入结果 JSON
    if result_file:
        try:
            Path(result_file).parent.mkdir(parents=True, exist_ok=True)
            Path(result_file).write_text(
                json.dumps(results, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"[FreeCAD GUI Macro] Result written: {result_file}")
        except Exception as e:
            print(f"[FreeCAD GUI Macro] ERROR writing result: {e}")

    print(f"[FreeCAD GUI Macro] Done in {results['elapsed_s']}s | "
          f"ok={results['ok']} | shapes={len(results['shapes'])} | "
          f"exports={len(results['exports'])} | errors={len(results['errors'])}")

    if auto_close:
        try:
            import FreeCADGui as Gui
            Gui.getMainWindow().close()
        except Exception:
            pass


# FreeCAD 启动时自动执行
try:
    main()
except Exception as e:
    print(f"[FreeCAD GUI Macro] FATAL: {e}")
    traceback.print_exc()
