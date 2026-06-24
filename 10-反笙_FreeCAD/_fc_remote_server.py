#!/usr/bin/env python3
"""
道法自然 — FreeCAD GUI 远程控制服务器 v1.0

在 FreeCAD GUI 内部启动一个 HTTP 服务器，实现实时远程控制。
一切用户操作按钮功能，皆可通过 HTTP API 调用。
无为而无不为 — 用户于可感一切而无感一切操作。

API:
  GET  /status          — 实例状态
  GET  /commands         — 全部注册命令列表
  GET  /commands/<name>  — 单个命令详情
  GET  /workbenches      — 工作台列表
  GET  /document         — 当前文档状态
  GET  /documents        — 全部打开文档
  GET  /selection        — 当前选择
  GET  /screenshot       — 捕获3D视图截图 (PNG base64)
  POST /run_command      — 执行GUI命令 {"command": "Part_Box"}
  POST /exec             — 执行任意Python代码 {"code": "..."}
  POST /ops              — 执行backend ops序列
  POST /select           — 选择对象 {"doc": "...", "obj": "...", "sub": "..."}
  POST /view             — 视图操作 {"action": "fit_all|isometric|front|..."}
  POST /workbench        — 切换工作台 {"name": "PartWorkbench"}
  POST /property         — 读写属性 {"doc":"...", "obj":"...", "prop":"...", "value":...}
  POST /create_object    — 创建参数化对象 {"type":"Part::Box", "name":"MyBox", "props":{}}
  POST /export           — 导出 {"doc":"...", "format":"step", "path":"..."}
  POST /import_file      — 导入文件 {"path":"...", "format":"auto"}
  POST /sketch_pad       — Sketch→Pad {"geometry":[...], "length":10}
  POST /partdesign_body  — 完整参数化Body {"features":[...]}
  POST /assembly         — 多零件装配 {"pre_ops":[...], "parts":[...], "constraints":[...]}
  POST /techdraw         — 工程图生成 {"pre_ops":[...], "shape":"...", "output":"..."}
  POST /fem              — 有限元分析 {"pre_ops":[...], "shape":"...", "material":"steel"}

启动方式:
  1. freecad.exe _fc_remote_server.py
  2. 在FreeCAD Python控制台中:
     exec(open(r"E:\\道\\道生一\\一生二\\3D建模Agent\\_fc_remote_server.py").read())

默认端口: 18920
"""

import json
import sys
import os
import time
import threading
import traceback
import io
import base64
import queue
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ─── Configuration ────────────────────────────────────────────────────────────
PORT = int(os.environ.get("FC_REMOTE_PORT", "18920"))
HOST = os.environ.get("FC_REMOTE_HOST", "127.0.0.1")
SCRIPT_DIR = Path(__file__).parent.resolve()

# ─── Thread-safe command queue for GUI-thread execution ───────────────────────
_cmd_queue = queue.Queue()
_result_map = {}
_result_lock = threading.Lock()
_cmd_counter = 0
_counter_lock = threading.Lock()


def _next_cmd_id():
    global _cmd_counter
    with _counter_lock:
        _cmd_counter += 1
        return _cmd_counter


def _exec_in_gui_thread(fn, timeout=30):
    """
    Schedule a function to run in FreeCAD's main/GUI thread via QTimer.
    Returns the result.
    """
    cmd_id = _next_cmd_id()
    event = threading.Event()

    _cmd_queue.put((cmd_id, fn, event))

    if event.wait(timeout=timeout):
        with _result_lock:
            return _result_map.pop(cmd_id, {"ok": False, "error": "no result"})
    else:
        return {"ok": False, "error": f"timeout after {timeout}s"}


def _gui_thread_worker():
    """
    Called periodically by QTimer in the main thread.
    Processes one command from the queue.
    """
    try:
        while not _cmd_queue.empty():
            cmd_id, fn, event = _cmd_queue.get_nowait()
            try:
                result = fn()
                if not isinstance(result, dict):
                    result = {"ok": True, "result": result}
            except Exception as e:
                result = {"ok": False, "error": str(e), "traceback": traceback.format_exc()}
            with _result_lock:
                _result_map[cmd_id] = result
            event.set()
    except queue.Empty:
        pass


# ─── API Handlers ─────────────────────────────────────────────────────────────

def _handle_status():
    """GET /status"""
    def _fn():
        import FreeCAD as App
        import FreeCADGui as Gui

        docs = list(App.listDocuments().keys())
        active_doc = App.ActiveDocument.Name if App.ActiveDocument else None
        active_wb = ""
        try:
            active_wb = Gui.activeWorkbench().name()
        except Exception:
            pass

        return {
            "ok": True,
            "freecad_version": App.Version(),
            "port": PORT,
            "documents": docs,
            "active_document": active_doc,
            "active_workbench": active_wb,
            "object_count": len(App.ActiveDocument.Objects) if App.ActiveDocument else 0,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    return _exec_in_gui_thread(_fn)


def _handle_commands():
    """GET /commands"""
    def _fn():
        import FreeCADGui as Gui
        from PySide2 import QtWidgets

        commands = {}
        mw = Gui.getMainWindow()
        for act in mw.findChildren(QtWidgets.QAction):
            name = act.objectName()
            text = act.text().replace("&", "")
            if not name and not text:
                continue
            key = name or text
            commands[key] = {
                "text": text,
                "tooltip": (act.toolTip() or "")[:200],
                "shortcut": act.shortcut().toString() if act.shortcut() else "",
                "enabled": act.isEnabled(),
                "checkable": act.isCheckable(),
            }
        return {"ok": True, "commands": commands, "count": len(commands)}
    return _exec_in_gui_thread(_fn)


def _handle_workbenches():
    """GET /workbenches"""
    def _fn():
        import FreeCADGui as Gui
        wb_dict = Gui.listWorkbenches()
        active = ""
        try:
            active = Gui.activeWorkbench().name()
        except Exception:
            pass
        wbs = {}
        for name, cls in wb_dict.items():
            wbs[name] = {"class": str(cls)}
            try:
                wb = Gui.getWorkbench(name)
                if wb:
                    try:
                        wbs[name]["toolbars"] = list(wb.listToolbars())
                    except Exception:
                        pass
            except Exception:
                pass
        return {"ok": True, "workbenches": wbs, "active": active, "count": len(wbs)}
    return _exec_in_gui_thread(_fn)


def _handle_document():
    """GET /document"""
    def _fn():
        import FreeCAD as App
        doc = App.ActiveDocument
        if not doc:
            return {"ok": True, "document": None}
        objects = []
        for obj in doc.Objects:
            o = {
                "name": obj.Name, "label": obj.Label, "type": obj.TypeId,
                "properties": obj.PropertiesList[:80],
            }
            try:
                if hasattr(obj, 'Shape') and obj.Shape and not obj.Shape.isNull():
                    o["volume"] = round(obj.Shape.Volume, 4)
                    o["faces"] = len(obj.Shape.Faces)
                    o["valid"] = obj.Shape.isValid()
            except Exception:
                pass
            objects.append(o)
        return {
            "ok": True,
            "document": {
                "name": doc.Name, "label": doc.Label, "file": doc.FileName,
                "objects": objects, "object_count": len(objects),
            }
        }
    return _exec_in_gui_thread(_fn)


def _handle_documents():
    """GET /documents"""
    def _fn():
        import FreeCAD as App
        docs = {}
        for name, doc in App.listDocuments().items():
            docs[name] = {
                "label": doc.Label, "file": doc.FileName,
                "object_count": len(doc.Objects),
                "modified": getattr(doc, 'Modified', None),
            }
        return {"ok": True, "documents": docs, "count": len(docs)}
    return _exec_in_gui_thread(_fn)


def _handle_selection():
    """GET /selection"""
    def _fn():
        import FreeCADGui as Gui
        sel = Gui.Selection.getSelectionEx()
        items = []
        for s in sel:
            item = {
                "object": s.ObjectName,
                "document": s.DocumentName,
                "sub_elements": [str(se) for se in s.SubElementNames],
            }
            try:
                item["type"] = s.Object.TypeId
            except Exception:
                pass
            items.append(item)
        return {"ok": True, "selection": items, "count": len(items)}
    return _exec_in_gui_thread(_fn)


def _handle_screenshot():
    """GET /screenshot"""
    def _fn():
        import FreeCADGui as Gui
        import tempfile
        view = Gui.ActiveDocument.ActiveView if Gui.ActiveDocument else None
        if not view:
            return {"ok": False, "error": "no active view"}
        tmp = os.path.join(tempfile.gettempdir(), "_fc_screenshot.png")
        view.saveImage(tmp, 1920, 1080, "Current")
        if os.path.exists(tmp):
            with open(tmp, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            os.remove(tmp)
            return {"ok": True, "format": "png", "width": 1920, "height": 1080,
                    "data": b64, "size": len(b64)}
        return {"ok": False, "error": "screenshot failed"}
    return _exec_in_gui_thread(_fn)


def _handle_run_command(body):
    """POST /run_command"""
    cmd_name = body.get("command", "")
    if not cmd_name:
        return {"ok": False, "error": "command required"}

    def _fn():
        import FreeCADGui as Gui
        Gui.runCommand(cmd_name)
        return {"ok": True, "command": cmd_name, "executed": True}
    return _exec_in_gui_thread(_fn)


def _handle_exec(body):
    """POST /exec"""
    code = body.get("code", "")
    if not code:
        return {"ok": False, "error": "code required"}

    def _fn():
        import FreeCAD as App
        import FreeCADGui as Gui
        import Part
        from FreeCAD import Base

        local_ns = {
            "App": App, "Gui": Gui, "Part": Part, "Base": Base,
            "FreeCAD": App, "FreeCADGui": Gui,
            "__result__": None,
        }
        exec(code, local_ns)
        result_val = local_ns.get("__result__")
        if result_val is not None:
            return {"ok": True, "result": str(result_val)[:10000]}
        return {"ok": True, "executed": True}
    return _exec_in_gui_thread(_fn)


def _handle_ops(body):
    """POST /ops"""
    ops = body.get("ops", [])
    if not ops:
        return {"ok": False, "error": "ops required"}

    def _fn():
        # Import backend
        sys.path.insert(0, str(SCRIPT_DIR))
        from freecad_backend import run_ops
        result = run_ops(ops)
        return result
    return _exec_in_gui_thread(_fn, timeout=120)


def _handle_select(body):
    """POST /select"""
    def _fn():
        import FreeCAD as App
        import FreeCADGui as Gui

        action = body.get("action", "add")  # add / remove / clear / toggle
        doc_name = body.get("doc", "")
        obj_name = body.get("obj", "")
        sub = body.get("sub", "")

        if action == "clear":
            Gui.Selection.clearSelection()
            return {"ok": True, "action": "clear"}

        doc = App.getDocument(doc_name) if doc_name else App.ActiveDocument
        if not doc:
            return {"ok": False, "error": "no document"}

        if action == "add":
            Gui.Selection.addSelection(doc.Name, obj_name, sub)
        elif action == "remove":
            Gui.Selection.removeSelection(doc.Name, obj_name, sub)
        elif action == "toggle":
            # Check if selected, then toggle
            sel = Gui.Selection.getSelection(doc.Name)
            names = [s.Name for s in sel]
            if obj_name in names:
                Gui.Selection.removeSelection(doc.Name, obj_name)
            else:
                Gui.Selection.addSelection(doc.Name, obj_name, sub)

        return {"ok": True, "action": action, "obj": obj_name}
    return _exec_in_gui_thread(_fn)


def _handle_view(body):
    """POST /view"""
    action = body.get("action", "fit_all")

    def _fn():
        import FreeCAD as App
        import FreeCADGui as Gui
        if not Gui.ActiveDocument:
            # GUI 运行时 App.newDocument 会自动创建 Gui.Document
            # (FreeCAD 1.0 中无 Gui.showDocument 方法)
            doc = App.newDocument("Default")
            doc.recompute()
            try:
                Gui.updateGui()
            except Exception:
                pass
        view = Gui.ActiveDocument.ActiveView if Gui.ActiveDocument else None
        if not view:
            return {"ok": False, "error": "no active view"}

        VIEW_ACTIONS = {
            "fit_all": "fitAll",
            "isometric": "viewIsometric",
            "front": "viewFront",
            "rear": "viewRear",
            "top": "viewTop",
            "bottom": "viewBottom",
            "left": "viewLeft",
            "right": "viewRight",
            "home": "viewHome",
        }

        fn_name = VIEW_ACTIONS.get(action)
        if fn_name:
            getattr(view, fn_name)()
            return {"ok": True, "action": action}

        if action == "set_camera":
            # {"action": "set_camera", "position": [x,y,z], "direction": [x,y,z]}
            pos = body.get("position")
            dirn = body.get("direction")
            if pos and dirn:
                from FreeCAD import Base
                view.setViewDirection(Base.Vector(*dirn))
                return {"ok": True, "action": "set_camera"}

        if action == "perspective":
            view.setCameraType("Perspective")
            return {"ok": True, "action": "perspective"}
        elif action == "orthographic":
            view.setCameraType("Orthographic")
            return {"ok": True, "action": "orthographic"}

        return {"ok": False, "error": f"unknown view action: {action}"}
    return _exec_in_gui_thread(_fn)


def _handle_workbench(body):
    """POST /workbench"""
    name = body.get("name", "")
    if not name:
        return {"ok": False, "error": "workbench name required"}

    def _fn():
        import FreeCADGui as Gui
        Gui.activateWorkbench(name)
        return {"ok": True, "workbench": name}
    return _exec_in_gui_thread(_fn)


def _handle_property(body):
    """POST /property"""
    def _fn():
        import FreeCAD as App

        doc_name = body.get("doc", "")
        obj_name = body.get("obj", "")
        prop_name = body.get("prop", "")
        value = body.get("value", None)

        doc = App.getDocument(doc_name) if doc_name else App.ActiveDocument
        if not doc:
            return {"ok": False, "error": "no document"}
        obj = doc.getObject(obj_name)
        if not obj:
            return {"ok": False, "error": f"object '{obj_name}' not found"}
        if not prop_name:
            # Return all properties
            props = {}
            for p in obj.PropertiesList:
                try:
                    props[p] = repr(getattr(obj, p))[:200]
                except Exception:
                    props[p] = "<error>"
            return {"ok": True, "properties": props}

        if value is not None:
            # Write property
            setattr(obj, prop_name, value)
            doc.recompute()
            return {"ok": True, "set": prop_name, "value": repr(value)[:200]}
        else:
            # Read property
            val = getattr(obj, prop_name)
            return {"ok": True, "prop": prop_name, "value": repr(val)[:500]}
    return _exec_in_gui_thread(_fn)


def _handle_create_object(body):
    """POST /create_object"""
    def _fn():
        import FreeCAD as App

        type_id = body.get("type", "Part::Box")
        name = body.get("name", "Object")
        props = body.get("props", {})
        doc_name = body.get("doc", "")

        doc = App.getDocument(doc_name) if doc_name else App.ActiveDocument
        if not doc:
            doc = App.newDocument("Unnamed")

        obj = doc.addObject(type_id, name)
        for k, v in props.items():
            try:
                setattr(obj, k, v)
            except Exception:
                pass
        doc.recompute()

        return {
            "ok": True, "object": obj.Name, "type": type_id,
            "document": doc.Name,
        }
    return _exec_in_gui_thread(_fn)


def _handle_export(body):
    """POST /export"""
    def _fn():
        import FreeCAD as App
        import Part

        doc_name = body.get("doc", "")
        obj_names = body.get("objects", [])
        path = body.get("path", "")
        fmt = body.get("format", "step")

        doc = App.getDocument(doc_name) if doc_name else App.ActiveDocument
        if not doc:
            return {"ok": False, "error": "no document"}
        if not path:
            return {"ok": False, "error": "path required"}

        # Collect both objects (for Mesh.export) and shapes (for Part.export)
        export_objs = []
        shapes = []
        for obj_name in (obj_names or [o.Name for o in doc.Objects]):
            obj = doc.getObject(obj_name)
            if obj and hasattr(obj, 'Shape') and obj.Shape and not obj.Shape.isNull():
                export_objs.append(obj)
                shapes.append(obj.Shape)

        if not shapes:
            return {"ok": False, "error": "no shapes to export"}

        compound = shapes[0] if len(shapes) == 1 else Part.makeCompound(shapes)

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if fmt.lower() in ("step", "stp"):
            Part.export(shapes, path)
        elif fmt.lower() == "stl":
            import Mesh
            try:
                # Best method: Mesh.export with document objects
                Mesh.export(export_objs, path)
            except Exception:
                try:
                    # Fallback: MeshPart.meshFromShape
                    import MeshPart
                    combined = MeshPart.meshFromShape(Shape=compound,
                                                      LinearDeflection=0.1,
                                                      AngularDeflection=0.5)
                    combined.write(path)
                except Exception as e2:
                    return {"ok": False, "error": f"STL export failed: {e2}"}
        elif fmt.lower() in ("brep", "brp"):
            compound.exportBrep(path)
        elif fmt.lower() in ("iges", "igs"):
            Part.export(shapes, path)
        elif fmt.lower() == "fcstd":
            doc.saveAs(path)
        else:
            return {"ok": False, "error": f"unsupported format: {fmt}"}

        size = os.path.getsize(path) if os.path.exists(path) else 0
        return {"ok": True, "path": path, "format": fmt, "size": size}
    return _exec_in_gui_thread(_fn)


def _handle_sketch_pad(body):
    """POST /sketch_pad  — Convenience: Sketch → Pad in one call"""
    geometry = body.get("geometry", [])
    if not geometry:
        return {"ok": False, "error": "geometry required"}
    ops = [{"op": "sketch_pad", "id": "result",
            "geometry": geometry,
            "length": body.get("length", 10),
            "plane": body.get("plane", "XY"),
            "constraints": body.get("constraints", []),
            "symmetric": body.get("symmetric", False),
            "taper": body.get("taper", 0)}]
    if body.get("export_stl"):
        ops.append({"op": "export_stl", "shape": "result",
                     "path": body["export_stl"]})
    if body.get("export_step"):
        ops.append({"op": "export_step", "shape": "result",
                     "path": body["export_step"]})
    return _handle_ops({"ops": ops})


def _handle_partdesign_body(body):
    """POST /partdesign_body  — Full parametric body with feature tree"""
    features = body.get("features", [])
    if not features:
        return {"ok": False, "error": "features list required"}
    ops = [{"op": "partdesign_body", "id": "result", "features": features}]
    if body.get("export_stl"):
        ops.append({"op": "export_stl", "shape": "result",
                     "path": body["export_stl"]})
    if body.get("export_step"):
        ops.append({"op": "export_step", "shape": "result",
                     "path": body["export_step"]})
    if body.get("techdraw"):
        td = body["techdraw"]
        ops.append({"op": "techdraw", "shape": "result",
                     "output": td.get("output", "drawing.svg"),
                     "title": td.get("title", "Drawing")})
    return _handle_ops({"ops": ops})


def _handle_assembly(body):
    """POST /assembly  — Multi-part assembly with constraints"""
    # Pre-ops to create parts
    pre_ops = body.get("pre_ops", [])
    parts = body.get("parts", [])
    constraints = body.get("constraints", [])
    if not parts:
        return {"ok": False, "error": "parts list required"}
    ops = list(pre_ops)
    ops.append({"op": "assembly", "id": "asm",
                "parts": parts, "constraints": constraints,
                "save_path": body.get("save_path")})
    if body.get("export_step"):
        ops.append({"op": "export_step", "shape": "asm",
                     "path": body["export_step"]})
    return _handle_ops({"ops": ops})


def _handle_techdraw(body):
    """POST /techdraw  — Generate technical drawing SVG"""
    pre_ops = body.get("pre_ops", [])
    shape_id = body.get("shape", "")
    output = body.get("output", "")
    if not shape_id or not output:
        return {"ok": False, "error": "shape and output required"}
    ops = list(pre_ops)
    ops.append({"op": "techdraw", "id": "td", "shape": shape_id,
                "output": output,
                "views": body.get("views"),
                "title": body.get("title", "Technical Drawing"),
                "scale": body.get("scale", 1.0)})
    return _handle_ops({"ops": ops})


def _handle_fem(body):
    """POST /fem  — FEM analysis (mesh + stress estimate)"""
    pre_ops = body.get("pre_ops", [])
    shape_id = body.get("shape", "")
    if not shape_id:
        return {"ok": False, "error": "shape id required"}
    ops = list(pre_ops)
    if body.get("mesh", True):
        mesh_op = {"op": "fem_mesh", "id": "mesh", "shape": shape_id,
                   "deflection": body.get("deflection", 0.1)}
        if body.get("mesh_path"):
            mesh_op["path"] = body["mesh_path"]
        ops.append(mesh_op)
    if body.get("stress", False):
        ops.append({"op": "fem_stress_estimate", "id": "stress",
                     "shape": shape_id,
                     "force_N": body.get("force_N", 100),
                     "material": body.get("material", "steel")})
    return _handle_ops({"ops": ops})


def _handle_import_file(body):
    """POST /import_file"""
    def _fn():
        import FreeCAD as App

        path = body.get("path", "")
        if not path or not os.path.exists(path):
            return {"ok": False, "error": f"file not found: {path}"}

        ext = Path(path).suffix.lower()
        if ext == ".fcstd":
            doc = App.openDocument(path)
            return {"ok": True, "document": doc.Name, "objects": len(doc.Objects)}
        elif ext in (".step", ".stp", ".iges", ".igs", ".brep", ".brp"):
            import Part
            shape = Part.read(path)
            doc = App.ActiveDocument or App.newDocument("Imported")
            obj = doc.addObject("Part::Feature", Path(path).stem)
            obj.Shape = shape
            doc.recompute()
            return {"ok": True, "object": obj.Name, "document": doc.Name}
        elif ext in (".stl", ".obj", ".ply", ".off"):
            import Mesh
            doc = App.ActiveDocument or App.newDocument("Imported")
            Mesh.insert(path, doc.Name)
            doc.recompute()
            return {"ok": True, "document": doc.Name}
        else:
            # Try generic import
            App.openDocument(path)
            return {"ok": True}
    return _exec_in_gui_thread(_fn)


# ─── HTTP Request Handler ────────────────────────────────────────────────────

class FreeCADRemoteHandler(BaseHTTPRequestHandler):
    """HTTP handler for FreeCAD remote control"""

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        try:
            if path == "" or path == "/status":
                self._json_response(_handle_status())
            elif path == "/commands":
                self._json_response(_handle_commands())
            elif path == "/workbenches":
                self._json_response(_handle_workbenches())
            elif path == "/document":
                self._json_response(_handle_document())
            elif path == "/documents":
                self._json_response(_handle_documents())
            elif path == "/selection":
                self._json_response(_handle_selection())
            elif path == "/screenshot":
                self._json_response(_handle_screenshot())
            else:
                self._json_response({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)}, 500)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json_response({"ok": False, "error": "invalid JSON"}, 400)
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        try:
            if path == "/run_command":
                self._json_response(_handle_run_command(body))
            elif path == "/exec":
                self._json_response(_handle_exec(body))
            elif path == "/ops":
                self._json_response(_handle_ops(body))
            elif path == "/select":
                self._json_response(_handle_select(body))
            elif path == "/view":
                self._json_response(_handle_view(body))
            elif path == "/workbench":
                self._json_response(_handle_workbench(body))
            elif path == "/property":
                self._json_response(_handle_property(body))
            elif path == "/create_object":
                self._json_response(_handle_create_object(body))
            elif path == "/export":
                self._json_response(_handle_export(body))
            elif path == "/import_file":
                self._json_response(_handle_import_file(body))
            elif path == "/sketch_pad":
                self._json_response(_handle_sketch_pad(body))
            elif path == "/partdesign_body":
                self._json_response(_handle_partdesign_body(body))
            elif path == "/assembly":
                self._json_response(_handle_assembly(body))
            elif path == "/techdraw":
                self._json_response(_handle_techdraw(body))
            elif path == "/fem":
                self._json_response(_handle_fem(body))
            else:
                self._json_response({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)}, 500)


# ─── Server Lifecycle ─────────────────────────────────────────────────────────

_server = None
_timer = None


def start_server(port=None, host=None):
    """
    启动远程控制服务器

    在FreeCAD Python控制台中一行启动:
        exec(open(r"path/to/_fc_remote_server.py").read())
    """
    global _server, _timer, PORT, HOST

    if port:
        PORT = port
    if host:
        HOST = host

    # Start HTTP server in daemon thread
    _server = HTTPServer((HOST, PORT), FreeCADRemoteHandler)
    _server.timeout = 0.5

    def _serve():
        while _server:
            try:
                _server.handle_request()
            except Exception:
                break

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    # Start QTimer for GUI-thread command processing
    try:
        from PySide2 import QtCore
        _timer = QtCore.QTimer()
        _timer.timeout.connect(_gui_thread_worker)
        _timer.start(50)  # 50ms polling interval
    except Exception as e:
        print(f"[RemoteServer] WARNING: QTimer failed: {e}")
        print("[RemoteServer] GUI-thread commands will not work properly.")

    print(f"")
    print(f"  {'='*56}")
    print(f"  FreeCAD Remote Control Server v1.0")
    print(f"  {'='*56}")
    print(f"  Status:    http://{HOST}:{PORT}/status")
    print(f"  Commands:  http://{HOST}:{PORT}/commands")
    print(f"  Document:  http://{HOST}:{PORT}/document")
    print(f"  Screenshot:http://{HOST}:{PORT}/screenshot")
    print(f"  {'='*56}")
    print(f"  POST /run_command  {'{'}\"command\": \"Part_Box\"{'}'}")
    print(f"  POST /exec         {'{'}\"code\": \"print(1+1)\"{'}'}")
    print(f"  POST /view         {'{'}\"action\": \"isometric\"{'}'}")
    print(f"  {'='*56}")
    print(f"")

    return _server


def stop_server():
    """停止服务器"""
    global _server, _timer
    if _timer:
        _timer.stop()
        _timer = None
    if _server:
        _server.shutdown()
        _server = None
    print("[RemoteServer] Stopped.")


# ─── Auto-start when executed ─────────────────────────────────────────────────
try:
    start_server()
except Exception as e:
    print(f"[RemoteServer] FATAL: {e}")
    traceback.print_exc()
