#!/usr/bin/env python3
"""
FreeCAD Bridge — 完全逆向接口层
FreeCAD 1.0 / 0.21 Python API 全能封装

支持两种模式:
  1. 嵌入模式 (embedded): 直接 import FreeCAD — 速度最快
  2. 子进程模式 (subprocess): 通过 freecadcmd.exe — 隔离性好

用法:
    bridge = FreeCADBridge()
    bridge.setup()

    # 嵌入模式
    doc = bridge.new_doc("test")
    box = bridge.make_box(doc, 20, 10, 5)
    bridge.export_step(doc, "output.step")

    # 子进程模式
    result = bridge.run_script("myscript.py")

    # 无 FreeCAD 依赖的 FCStd 解析
    info = bridge.parse_fcstd("model.FCStd")
"""

import os
import sys
import json
import zipfile
import subprocess
import tempfile
import math
import shutil
from pathlib import Path
from typing import Optional, Union, List, Dict, Any, Tuple

# Pre-import ET before FreeCAD path injection to avoid expat DLL conflicts
import xml.etree.ElementTree as _ET_PRELOADED

FREECAD_BIN_1_0  = r"D:\安装的软件\FreeCAD 1.0\bin"
FREECAD_LIB_1_0  = r"D:\安装的软件\FreeCAD 1.0\lib"
FREECAD_MOD_1_0  = r"D:\安装的软件\FreeCAD 1.0\Mod"
FREECAD_EXT_1_0  = r"D:\安装的软件\FreeCAD 1.0\Ext"
FREECAD_DATA_1_0 = r"D:\安装的软件\FreeCAD 1.0\data"
FREECAD_MAT_DIR  = r"D:\安装的软件\FreeCAD 1.0\data\Mod\Material\Resources\Materials"

FREECAD_BIN_021  = r"D:\安装的软件\FreeCAD 0.21\bin"
FREECAD_LIB_021  = r"D:\安装的软件\FreeCAD 0.21\lib"
FREECAD_MOD_021  = r"D:\安装的软件\FreeCAD 0.21\Mod"
FREECAD_EXT_021  = r"D:\安装的软件\FreeCAD 0.21\Ext"

CMD_1_0 = r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe"
CMD_021 = r"D:\安装的软件\FreeCAD 0.21\bin\FreeCADCmd.exe"


class FreeCADBridge:
    """
    FreeCAD 完全接口层

    属性:
        mode (str): "embedded" | "subprocess" | "fcstd_only"
        fc_available (bool): FreeCAD 是否可用
        version (str): "1.0" | "0.21" | None
    """

    def __init__(self, prefer_version: str = "1.0"):
        self.prefer_version = prefer_version
        self.mode = "fcstd_only"
        self.fc_available = False
        self.version = None
        self._App = None
        self._Part = None
        self._Mesh = None
        self._cmd_path = None

    def setup(self, mode: str = "auto") -> bool:
        """
        初始化 FreeCAD 环境

        Args:
            mode: "embedded" / "subprocess" / "auto"
        Returns:
            True if FreeCAD available
        """
        if mode in ("embedded", "auto"):
            if self._try_embedded():
                self.mode = "embedded"
                self.fc_available = True
                return True

        if mode in ("subprocess", "auto"):
            if self._try_subprocess():
                self.mode = "subprocess"
                self.fc_available = True
                return True

        self.mode = "fcstd_only"
        self.fc_available = False
        return False

    def _try_embedded(self) -> bool:
        """尝试嵌入式导入 FreeCAD"""
        candidates = []
        if self.prefer_version == "1.0":
            candidates = [
                (FREECAD_BIN_1_0, FREECAD_LIB_1_0, FREECAD_MOD_1_0, FREECAD_EXT_1_0, "1.0"),
                (FREECAD_BIN_021, FREECAD_LIB_021, FREECAD_MOD_021, FREECAD_EXT_021, "0.21"),
            ]
        else:
            candidates = [
                (FREECAD_BIN_021, FREECAD_LIB_021, FREECAD_MOD_021, FREECAD_EXT_021, "0.21"),
                (FREECAD_BIN_1_0, FREECAD_LIB_1_0, FREECAD_MOD_1_0, FREECAD_EXT_1_0, "1.0"),
            ]

        for bin_dir, lib_dir, mod_dir, ext_dir, ver in candidates:
            if not Path(bin_dir).exists():
                continue
            try:
                for p in [bin_dir, lib_dir, mod_dir, ext_dir]:
                    if p not in sys.path:
                        sys.path.insert(0, p)
                if sys.platform == "win32":
                    os.add_dll_directory(bin_dir)
                import FreeCAD as App
                import Part
                self._App = App
                self._Part = Part
                self.version = ver
                try:
                    import Mesh
                    self._Mesh = Mesh
                except ImportError:
                    pass
                return True
            except Exception:
                continue
        return False

    def _try_subprocess(self) -> bool:
        """尝试通过 freecadcmd.exe 子进程模式"""
        for cmd, ver in [(CMD_1_0, "1.0"), (CMD_021, "0.21")]:
            if Path(cmd).exists():
                self._cmd_path = cmd
                self.version = ver
                return True
        found = shutil.which("FreeCADCmd") or shutil.which("freecadcmd")
        if found:
            self._cmd_path = found
            self.version = "unknown"
            return True
        return False

    @property
    def App(self):
        if self._App is None:
            raise RuntimeError("FreeCAD not available in embedded mode. Call setup() first.")
        return self._App

    @property
    def Part(self):
        if self._Part is None:
            raise RuntimeError("Part module not available. Call setup() first.")
        return self._Part

    # ──────────────────────────────────────────────────────────────
    # 文档操作
    # ──────────────────────────────────────────────────────────────

    def new_doc(self, name: str = "Unnamed"):
        """创建新文档"""
        return self.App.newDocument(name)

    def open_doc(self, path: str):
        """打开 FCStd 文档"""
        return self.App.openDocument(str(path))

    def save_doc(self, doc, path: str):
        """保存文档"""
        doc.saveAs(str(path))

    def recompute(self, doc):
        """重新计算文档依赖图"""
        doc.recompute()

    def close_doc(self, doc):
        """关闭文档"""
        self.App.closeDocument(doc.Name)

    # ──────────────────────────────────────────────────────────────
    # 几何体素创建
    # ──────────────────────────────────────────────────────────────

    def make_box(self, doc, L: float, W: float, H: float,
                 pos: tuple = (0, 0, 0), name: str = "Box"):
        """创建长方体"""
        from FreeCAD import Base
        box = self.Part.makeBox(L, W, H,
                                Base.Vector(*pos),
                                Base.Vector(0, 0, 1))
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = box
        return obj

    def make_cylinder(self, doc, R: float, H: float,
                      pos: tuple = (0, 0, 0), name: str = "Cylinder"):
        """创建圆柱"""
        from FreeCAD import Base
        cyl = self.Part.makeCylinder(R, H,
                                     Base.Vector(*pos),
                                     Base.Vector(0, 0, 1))
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = cyl
        return obj

    def make_sphere(self, doc, R: float,
                    pos: tuple = (0, 0, 0), name: str = "Sphere"):
        """创建球体"""
        from FreeCAD import Base
        sph = self.Part.makeSphere(R, Base.Vector(*pos))
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = sph
        return obj

    def make_cone(self, doc, R1: float, R2: float, H: float,
                  pos: tuple = (0, 0, 0), name: str = "Cone"):
        """创建圆锥/圆台"""
        from FreeCAD import Base
        cone = self.Part.makeCone(R1, R2, H, Base.Vector(*pos))
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = cone
        return obj

    def make_torus(self, doc, R1: float, R2: float,
                   pos: tuple = (0, 0, 0), name: str = "Torus"):
        """创建圆环体 (R1=主半径, R2=管半径)"""
        from FreeCAD import Base
        tor = self.Part.makeTorus(R1, R2)
        tor.translate(Base.Vector(*pos))
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = tor
        return obj

    # ──────────────────────────────────────────────────────────────
    # 布尔运算
    # ──────────────────────────────────────────────────────────────

    def fuse(self, doc, obj1, obj2, name: str = "Fuse"):
        """布尔并集"""
        shape = obj1.Shape.fuse(obj2.Shape)
        shape = shape.removeSplitter()
        result = doc.addObject("Part::Feature", name)
        result.Shape = shape
        return result

    def cut(self, doc, base_obj, tool_obj, name: str = "Cut"):
        """布尔差集"""
        shape = base_obj.Shape.cut(tool_obj.Shape)
        result = doc.addObject("Part::Feature", name)
        result.Shape = shape
        return result

    def common(self, doc, obj1, obj2, name: str = "Common"):
        """布尔交集"""
        shape = obj1.Shape.common(obj2.Shape)
        result = doc.addObject("Part::Feature", name)
        result.Shape = shape
        return result

    def fuse_many(self, doc, objects: list, name: str = "Fusion"):
        """多体布尔并集"""
        if len(objects) < 1:
            raise ValueError("需要至少1个对象")
        shape = objects[0].Shape
        for obj in objects[1:]:
            shape = shape.fuse(obj.Shape)
        shape = shape.removeSplitter()
        result = doc.addObject("Part::Feature", name)
        result.Shape = shape
        return result

    # ──────────────────────────────────────────────────────────────
    # 高级造型
    # ──────────────────────────────────────────────────────────────

    def extrude(self, doc, face_obj, direction: tuple, name: str = "Extrusion"):
        """拉伸面"""
        from FreeCAD import Base
        shape = face_obj.Shape.extrude(Base.Vector(*direction))
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = shape
        return obj

    def revolve(self, doc, face_obj,
                axis_origin: tuple = (0, 0, 0),
                axis_dir: tuple = (0, 0, 1),
                angle: float = 360.0,
                name: str = "Revolution"):
        """旋转体"""
        from FreeCAD import Base
        shape = face_obj.Shape.revolve(
            Base.Vector(*axis_origin),
            Base.Vector(*axis_dir),
            angle
        )
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = shape
        return obj

    def loft(self, doc, wire_objects: list,
             solid: bool = True, ruled: bool = False,
             name: str = "Loft"):
        """放样"""
        wires = [o.Shape if hasattr(o, 'Shape') else o for o in wire_objects]
        shape = self.Part.makeLoft(wires, solid, ruled)
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = shape
        return obj

    def make_polygon_wire(self, doc, points: list, closed: bool = True, name: str = "Wire"):
        """由点列表创建多边形线框"""
        from FreeCAD import Base
        pts = [Base.Vector(*p) if not isinstance(p, Base.Vector) else p for p in points]
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        wire = self.Part.makePolygon(pts)
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = wire
        return obj

    def make_face_from_wire(self, doc, wire_obj, name: str = "Face"):
        """由线框创建面"""
        wire = wire_obj.Shape if hasattr(wire_obj, 'Shape') else wire_obj
        face = self.Part.Face(wire)
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = face
        return obj

    def fillet(self, doc, solid_obj, radius: float,
               edge_indices: list = None, name: str = "Fillet"):
        """圆角 (edge_indices=None 则对所有边)"""
        shape = solid_obj.Shape
        edges = shape.Edges
        if edge_indices is not None:
            edges = [edges[i] for i in edge_indices]
        fillet_shape = shape.makeFillet(radius, edges)
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = fillet_shape
        return obj

    def chamfer(self, doc, solid_obj, size: float,
                edge_indices: list = None, name: str = "Chamfer"):
        """倒角"""
        shape = solid_obj.Shape
        edges = shape.Edges
        if edge_indices is not None:
            edges = [edges[i] for i in edge_indices]
        chamfer_shape = shape.makeChamfer(size, edges)
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = chamfer_shape
        return obj

    def offset3d(self, doc, solid_obj, offset: float,
                 tolerance: float = 0.001, name: str = "Offset"):
        """3D 偏移"""
        shape = solid_obj.Shape.makeOffsetShape(offset, tolerance)
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = shape
        return obj

    def mirror(self, doc, obj, plane: str = "XY", name: str = "Mirror"):
        """镜像 (plane: XY / XZ / YZ)"""
        from FreeCAD import Base
        planes = {
            "XY": (Base.Vector(0, 0, 0), Base.Vector(0, 0, 1)),
            "XZ": (Base.Vector(0, 0, 0), Base.Vector(0, 1, 0)),
            "YZ": (Base.Vector(0, 0, 0), Base.Vector(1, 0, 0)),
        }
        origin, normal = planes.get(plane.upper(), planes["XY"])
        shape = obj.Shape.mirror(origin, normal)
        result = doc.addObject("Part::Feature", name)
        result.Shape = shape
        return result

    # ──────────────────────────────────────────────────────────────
    # 变换
    # ──────────────────────────────────────────────────────────────

    def translate(self, obj, dx: float, dy: float, dz: float):
        """平移对象 (原地修改 Placement)"""
        import FreeCAD as App
        p = obj.Placement
        v = p.Base + App.Vector(dx, dy, dz)
        obj.Placement = App.Placement(v, p.Rotation)
        return obj

    def rotate(self, obj, axis: tuple, angle_deg: float):
        """旋转对象 (原地修改 Placement)"""
        import FreeCAD as App
        r = App.Rotation(App.Vector(*axis), angle_deg)
        obj.Placement = App.Placement(obj.Placement.Base, r)
        return obj

    def set_placement(self, obj, pos: tuple = (0, 0, 0),
                      axis: tuple = (0, 0, 1), angle: float = 0.0):
        """设置完整位姿"""
        import FreeCAD as App
        obj.Placement = App.Placement(
            App.Vector(*pos),
            App.Rotation(App.Vector(*axis), angle)
        )
        return obj

    # ──────────────────────────────────────────────────────────────
    # 导入/导出
    # ──────────────────────────────────────────────────────────────

    def export_step(self, doc_or_objects, path: str):
        """导出 STEP"""
        objects = self._resolve_export_objects(doc_or_objects)
        self.Part.export(objects, str(path))

    def export_brep(self, doc_or_objects, path: str):
        """导出 BREP"""
        objects = self._resolve_export_objects(doc_or_objects)
        self.Part.export(objects, str(path))

    def export_stl(self, doc_or_objects, path: str, mesh_deflection: float = 0.1):
        """导出 STL"""
        if self._Mesh is None:
            raise RuntimeError("Mesh module not available")
        objects = self._resolve_export_objects(doc_or_objects)
        self._Mesh.export(objects, str(path))

    def export_obj(self, doc_or_objects, path: str):
        """导出 OBJ"""
        if self._Mesh is None:
            raise RuntimeError("Mesh module not available")
        objects = self._resolve_export_objects(doc_or_objects)
        self._Mesh.export(objects, str(path))

    def import_step(self, doc, path: str):
        """导入 STEP 到文档"""
        shape = self.Part.Shape()
        shape.read(str(path))
        obj = doc.addObject("Part::Feature", Path(path).stem)
        obj.Shape = shape
        return obj

    def import_brep(self, doc, path: str):
        """导入 BREP 到文档"""
        shape = self.Part.Shape()
        shape.importBrep(str(path))
        obj = doc.addObject("Part::Feature", Path(path).stem)
        obj.Shape = shape
        return obj

    def import_stl(self, doc, path: str):
        """导入 STL 为 Mesh"""
        if self._Mesh is None:
            raise RuntimeError("Mesh module not available")
        mesh = self._Mesh.Mesh()
        mesh.read(str(path))
        obj = doc.addObject("Mesh::Feature", Path(path).stem)
        obj.Mesh = mesh
        return obj

    def _resolve_export_objects(self, doc_or_objects) -> list:
        """将 doc 或 object list 统一为 list"""
        if hasattr(doc_or_objects, 'Objects'):
            return [o for o in doc_or_objects.Objects
                    if hasattr(o, 'Shape') and not o.Shape.isNull()]
        return list(doc_or_objects)

    # ──────────────────────────────────────────────────────────────
    # 形状分析
    # ──────────────────────────────────────────────────────────────

    def shape_info(self, obj) -> Dict[str, Any]:
        """获取形状完整信息"""
        shape = obj.Shape if hasattr(obj, 'Shape') else obj
        bb = shape.BoundBox
        info = {
            "type":         shape.ShapeType,
            "valid":        shape.isValid(),
            "null":         shape.isNull(),
            "closed":       shape.isClosed(),
            "volume_mm3":   round(shape.Volume, 4),
            "area_mm2":     round(shape.Area, 4),
            "bounding_box": {
                "x": [round(bb.XMin, 4), round(bb.XMax, 4)],
                "y": [round(bb.YMin, 4), round(bb.YMax, 4)],
                "z": [round(bb.ZMin, 4), round(bb.ZMax, 4)],
                "size": [round(bb.XLength, 4), round(bb.YLength, 4), round(bb.ZLength, 4)],
                "diagonal": round(bb.DiagonalLength, 4),
                "center": [round(bb.Center.x, 4), round(bb.Center.y, 4), round(bb.Center.z, 4)],
            },
            "counts": {
                "vertices": len(shape.Vertexes),
                "edges":    len(shape.Edges),
                "faces":    len(shape.Faces),
                "shells":   len(shape.Shells),
                "solids":   len(shape.Solids),
            },
        }
        try:
            com = shape.CenterOfMass
            info["center_of_mass"] = [round(com.x, 4), round(com.y, 4), round(com.z, 4)]
        except Exception:
            pass
        return info

    def check_shape(self, obj) -> Dict[str, Any]:
        """检查形状有效性"""
        shape = obj.Shape if hasattr(obj, 'Shape') else obj
        issues = []
        if not shape.isValid():
            issues.append("invalid_shape")
        if shape.isNull():
            issues.append("null_shape")
        try:
            shape.check(True)
        except Exception as e:
            issues.append(f"check_failed: {e}")
        return {"ok": len(issues) == 0, "issues": issues}

    def tessellate(self, obj, deflection: float = 0.1) -> Dict[str, Any]:
        """将形状网格化，返回 vertices + triangles"""
        shape = obj.Shape if hasattr(obj, 'Shape') else obj
        verts, tris = shape.tessellate(deflection)
        return {
            "vertices": [[v.x, v.y, v.z] for v in verts],
            "triangles": list(tris),
            "vertex_count": len(verts),
            "triangle_count": len(tris),
        }

    def brep_to_string(self, obj) -> str:
        """形状序列化为 BREP 字符串"""
        shape = obj.Shape if hasattr(obj, 'Shape') else obj
        return shape.exportBrepToString()

    def brep_from_string(self, doc, brep_str: str, name: str = "Shape"):
        """从 BREP 字符串恢复形状"""
        shape = self.Part.Shape()
        shape.importBrepFromString(brep_str)
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = shape
        return obj

    # ──────────────────────────────────────────────────────────────
    # 子进程模式
    # ──────────────────────────────────────────────────────────────

    def run_script(self, script_path: str, timeout: int = 120) -> Dict[str, Any]:
        """通过 freecadcmd.exe 执行脚本"""
        if not self._cmd_path:
            raise RuntimeError("freecadcmd.exe not found. Call setup() first.")
        try:
            result = subprocess.run(
                [self._cmd_path, str(script_path)],
                capture_output=True, text=True,
                timeout=timeout,
                creationflags=0x08000000 if sys.platform == "win32" else 0
            )
            return {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Timeout after {timeout}s"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def run_code(self, code: str, timeout: int = 120) -> Dict[str, Any]:
        """在 freecadcmd.exe 中执行 Python 代码字符串"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                         delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp = f.name
        try:
            return self.run_script(tmp, timeout=timeout)
        finally:
            Path(tmp).unlink(missing_ok=True)

    # ──────────────────────────────────────────────────────────────
    # FCStd 解析 (无需 FreeCAD 进程)
    # ──────────────────────────────────────────────────────────────

    def parse_fcstd(self, path: str) -> Dict[str, Any]:
        """
        解析 FCStd 文件结构，无需 FreeCAD 进程。
        返回完整的文档信息字典。
        """
        import xml.etree.ElementTree as ET

        result = {
            "path": str(path),
            "valid": False,
            "entries": [],
            "document": {},
            "objects": [],
            "shapes": [],
            "gui": {},
        }

        try:
            with zipfile.ZipFile(path) as z:
                result["entries"] = z.namelist()

                for name in z.namelist():
                    if name.endswith('.brp'):
                        result["shapes"].append({
                            "file": name,
                            "size_bytes": z.getinfo(name).file_size,
                            "compressed_bytes": z.getinfo(name).compress_size,
                        })

                if "Document.xml" in z.namelist():
                    xml_data = z.read("Document.xml").decode("utf-8")
                    doc_info, objects = self._parse_document_xml(xml_data)
                    result["document"] = doc_info
                    result["objects"] = objects

                if "GuiDocument.xml" in z.namelist():
                    gui_xml = z.read("GuiDocument.xml").decode("utf-8")
                    result["gui"] = self._parse_gui_xml(gui_xml)

                result["valid"] = True

        except zipfile.BadZipFile:
            result["error"] = "Not a valid FCStd file (bad zip)"
        except Exception as e:
            result["error"] = str(e)

        return result

    def _parse_document_xml(self, xml_str: str) -> Tuple[Dict, List]:
        """解析 Document.xml"""
        root = _ET_PRELOADED.fromstring(xml_str)

        doc_info = {
            "schema_version": root.get("SchemaVersion"),
            "program_version": root.get("ProgramVersion"),
            "properties": {},
        }

        for prop in root.findall("./Properties/Property"):
            name = prop.get("name")
            ptype = prop.get("type")
            value = None
            for child in prop:
                value = child.get("value") or child.text
            doc_info["properties"][name] = {"type": ptype, "value": value}

        objects = []
        for obj in root.findall("./Objects/Object"):
            objects.append({
                "name":    obj.get("name"),
                "type":    obj.get("type"),
                "id":      obj.get("id"),
                "touched": obj.get("Touched") == "1",
            })

        deps = {}
        for dep_node in root.findall("./Objects/ObjectDeps"):
            obj_name = dep_node.get("Name")
            dep_list = [d.get("Name") for d in dep_node.findall("Dep")]
            if dep_list:
                deps[obj_name] = dep_list
        doc_info["dependencies"] = deps

        object_data = {}
        for obj in root.findall("./ObjectData/Object"):
            name = obj.get("name")
            props = {}
            for prop in obj.findall(".//Properties/Property"):
                pname = prop.get("name")
                ptype = prop.get("type")
                props[pname] = ptype
            object_data[name] = props

        for o in objects:
            if o["name"] in object_data:
                o["properties"] = object_data[o["name"]]

        return doc_info, objects

    def _parse_gui_xml(self, xml_str: str) -> Dict:
        """解析 GuiDocument.xml"""
        try:
            root = _ET_PRELOADED.fromstring(xml_str)
            views = []
            for vp in root.findall(".//ViewProvider"):
                name = vp.get("name")
                visible = None
                for prop in vp.findall(".//Property[@name='Visibility']"):
                    visible = prop.find("Bool") is not None and \
                              prop.find("Bool").get("value") == "true"
                views.append({"name": name, "visible": visible})
            return {"view_providers": views}
        except Exception:
            return {}

    def extract_shapes_from_fcstd(self, path: str, output_dir: str = None) -> List[str]:
        """
        从 FCStd 提取所有 BREP 形状文件到目录。
        无需 FreeCAD 进程。
        返回提取的文件路径列表。
        """
        if output_dir is None:
            output_dir = str(Path(path).parent / (Path(path).stem + "_shapes"))
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        extracted = []
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.endswith('.brp'):
                    out_path = Path(output_dir) / name.replace('/', '_')
                    data = z.read(name)
                    out_path.write_bytes(data)
                    extracted.append(str(out_path))
        return extracted

    def extract_thumbnail(self, path: str, output_path: str = None) -> Optional[str]:
        """提取 FCStd 预览图"""
        if output_path is None:
            output_path = str(Path(path).with_suffix('.png'))
        with zipfile.ZipFile(path) as z:
            if "thumbnails/Thumbnail.png" in z.namelist():
                data = z.read("thumbnails/Thumbnail.png")
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(data)
                return output_path
        return None

    # ──────────────────────────────────────────────────────────────
    # 材料数据库
    # ──────────────────────────────────────────────────────────────

    def list_materials(self, version: str = "1.0") -> List[str]:
        """列出所有可用材料"""
        mat_dir = Path(FREECAD_MAT_DIR)
        if not mat_dir.exists():
            mat_dir = Path(FREECAD_DATA_1_0) / "Mod" / "Material"
        if not mat_dir.exists():
            return []
        return [f.stem for f in sorted(mat_dir.rglob("*.FCMat"))]

    def get_material(self, name: str, version: str = "1.0") -> Optional[Dict]:
        """获取材料属性 (.FCMat 格式解析)"""
        import configparser
        mat_dir = Path(FREECAD_MAT_DIR)
        if not mat_dir.exists():
            mat_dir = Path(FREECAD_DATA_1_0) / "Mod" / "Material"
        mat_file = mat_dir / f"{name}.FCMat"
        if not mat_file.exists():
            for f in mat_dir.rglob("*.FCMat"):
                if f.stem.lower() == name.lower():
                    mat_file = f
                    break
        if not mat_file.exists():
            return None

        content = mat_file.read_text(encoding="utf-8", errors="ignore")
        try:
            import yaml
            data = yaml.safe_load(content)
            return data if isinstance(data, dict) else {"raw": content}
        except ImportError:
            pass
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read_string(content)
            result = {}
            for section in config.sections():
                result[section] = dict(config[section])
            return result if result else {"raw": content[:500]}
        except Exception:
            pass
        result = {}
        current_section = None
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#') or line == '---':
                continue
            if line.endswith(':') and not line.startswith(' '):
                current_section = line[:-1]
                result[current_section] = {}
            elif ':' in line and current_section:
                k, _, v = line.partition(':')
                result[current_section][k.strip()] = v.strip().strip('"\'')
        return result or {"raw": content[:500]}

    # ──────────────────────────────────────────────────────────────
    # 批量转换工具
    # ──────────────────────────────────────────────────────────────

    def convert(self, input_path: str, output_path: str) -> bool:
        """
        格式转换：自动选择方式
        支持: .FCStd / .brep / .step / .iges → .step / .brep / .stl / .obj
        """
        in_path = Path(input_path)
        out_path = Path(output_path)
        in_ext = in_path.suffix.lower()
        out_ext = out_path.suffix.lower()

        if self.mode == "embedded":
            return self._convert_embedded(str(in_path), str(out_path), in_ext, out_ext)
        elif self.mode == "subprocess":
            return self._convert_subprocess(str(in_path), str(out_path), in_ext, out_ext)
        else:
            if in_ext == ".fcstd" and out_ext in (".brep", ".brp"):
                shapes = self.extract_shapes_from_fcstd(str(in_path))
                if shapes:
                    shutil.copy(shapes[0], str(out_path))
                    return True
            return False

    def _convert_embedded(self, src: str, dst: str, in_ext: str, out_ext: str) -> bool:
        try:
            doc = self.new_doc("_convert")
            if in_ext in (".step", ".stp"):
                self.import_step(doc, src)
            elif in_ext in (".brep", ".brp"):
                self.import_brep(doc, src)
            elif in_ext == ".fcstd":
                self.close_doc(doc)
                doc = self.open_doc(src)
            elif in_ext in (".stl",):
                self.import_stl(doc, src)
            else:
                return False

            if out_ext in (".step", ".stp"):
                self.export_step(doc, dst)
            elif out_ext in (".brep", ".brp"):
                self.export_brep(doc, dst)
            elif out_ext == ".stl":
                self.export_stl(doc, dst)
            elif out_ext == ".obj":
                self.export_obj(doc, dst)
            else:
                return False

            try:
                self.close_doc(doc)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _convert_subprocess(self, src: str, dst: str, in_ext: str, out_ext: str) -> bool:
        code = f"""
import sys
sys.path.insert(0, r"{FREECAD_MOD_1_0}")
import FreeCAD, Part, Mesh

doc = FreeCAD.newDocument("convert")
try:
    if r"{in_ext}" in (".step", ".stp"):
        s = Part.Shape(); s.read(r"{src}")
        o = doc.addObject("Part::Feature", "Shape"); o.Shape = s
    elif r"{in_ext}" in (".brep", ".brp"):
        s = Part.Shape(); s.importBrep(r"{src}")
        o = doc.addObject("Part::Feature", "Shape"); o.Shape = s
    elif r"{in_ext}" == ".fcstd":
        doc = FreeCAD.openDocument(r"{src}")
    elif r"{in_ext}" == ".stl":
        m = Mesh.Mesh(); m.read(r"{src}")
        o = doc.addObject("Mesh::Feature", "Mesh"); o.Mesh = m

    objs = [o for o in doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()]
    if not objs:
        objs = [o for o in doc.Objects if hasattr(o, "Mesh")]

    if r"{out_ext}" in (".step", ".stp"):
        Part.export(objs, r"{dst}")
    elif r"{out_ext}" in (".brep", ".brp"):
        Part.export(objs, r"{dst}")
    elif r"{out_ext}" == ".stl":
        Mesh.export(objs, r"{dst}")
    elif r"{out_ext}" == ".obj":
        Mesh.export(objs, r"{dst}")
    print("OK")
except Exception as e:
    print(f"ERROR: {{e}}")
"""
        result = self.run_code(code)
        return result.get("ok") and "OK" in result.get("stdout", "")

    # ──────────────────────────────────────────────────────────────
    # 环境诊断
    # ──────────────────────────────────────────────────────────────

    def diagnostics(self) -> Dict[str, Any]:
        """完整环境诊断报告"""
        info = {
            "mode": self.mode,
            "version": self.version,
            "fc_available": self.fc_available,
            "cmd_path": self._cmd_path,
            "installations": {},
        }

        for ver, bin_dir, cmd in [
            ("1.0", FREECAD_BIN_1_0, CMD_1_0),
            ("0.21", FREECAD_BIN_021, CMD_021),
        ]:
            info["installations"][ver] = {
                "bin_exists": Path(bin_dir).exists(),
                "cmd_exists": Path(cmd).exists(),
                "pyd_count": len(list(Path(bin_dir.replace("bin", "lib")).glob("*.pyd")))
                             if Path(bin_dir.replace("bin", "lib")).exists() else 0,
            }

        if self.mode == "embedded" and self._App:
            try:
                info["freecad_version_string"] = self._App.Version
            except Exception:
                pass

        return info


# ──────────────────────────────────────────────────────────────────────────────
# 便捷顶层函数
# ──────────────────────────────────────────────────────────────────────────────

_default_bridge: Optional[FreeCADBridge] = None


def get_bridge(mode: str = "auto") -> FreeCADBridge:
    """获取全局 Bridge 实例 (懒初始化)"""
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = FreeCADBridge()
        _default_bridge.setup(mode)
    return _default_bridge


def parse_fcstd(path: str) -> Dict:
    """快速解析 FCStd (无需 FreeCAD 进程)"""
    b = FreeCADBridge()
    return b.parse_fcstd(path)


def convert_file(src: str, dst: str, mode: str = "auto") -> bool:
    """快速格式转换"""
    b = get_bridge(mode)
    return b.convert(src, dst)


def shape_from_step(path: str) -> Optional[Any]:
    """读取 STEP 文件返回 Part.Shape (embedded模式)"""
    b = get_bridge("embedded")
    if not b.fc_available:
        return None
    shape = b.Part.Shape()
    shape.read(str(path))
    return shape


def shape_from_brep(path: str) -> Optional[Any]:
    """读取 BREP 文件返回 Part.Shape (embedded模式)"""
    b = get_bridge("embedded")
    if not b.fc_available:
        return None
    shape = b.Part.Shape()
    shape.importBrep(str(path))
    return shape


# ──────────────────────────────────────────────────────────────────────────────
# CLI 接口
# ──────────────────────────────────────────────────────────────────────────────

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="FreeCAD Bridge CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("check", help="环境诊断")

    p_parse = sub.add_parser("parse", help="解析 FCStd 文件结构")
    p_parse.add_argument("file")
    p_parse.add_argument("--shapes", action="store_true", help="同时列出形状文件")

    p_convert = sub.add_parser("convert", help="格式转换")
    p_convert.add_argument("input")
    p_convert.add_argument("output")

    p_extract = sub.add_parser("extract", help="提取 FCStd 中的 BREP 形状")
    p_extract.add_argument("file")
    p_extract.add_argument("--out", default=None)

    p_thumb = sub.add_parser("thumbnail", help="提取 FCStd 预览图")
    p_thumb.add_argument("file")
    p_thumb.add_argument("--out", default=None)

    p_mat = sub.add_parser("material", help="查询材料数据库")
    p_mat.add_argument("name", nargs="?", default=None, help="材料名，不填则列出所有")

    p_run = sub.add_parser("run", help="通过 freecadcmd 执行脚本")
    p_run.add_argument("script")

    args = parser.parse_args()

    bridge = FreeCADBridge()
    bridge.setup()

    if args.cmd == "check":
        print(json.dumps(bridge.diagnostics(), indent=2, ensure_ascii=False))

    elif args.cmd == "parse":
        info = bridge.parse_fcstd(args.file)
        if not args.shapes and "shapes" in info:
            info.pop("shapes")
        print(json.dumps(info, indent=2, ensure_ascii=False))

    elif args.cmd == "convert":
        ok = bridge.convert(args.input, args.output)
        print(json.dumps({"ok": ok, "output": args.output}))

    elif args.cmd == "extract":
        shapes = bridge.extract_shapes_from_fcstd(args.file, args.out)
        print(json.dumps({"extracted": shapes, "count": len(shapes)}, indent=2))

    elif args.cmd == "thumbnail":
        out = bridge.extract_thumbnail(args.file, args.out)
        print(json.dumps({"thumbnail": out}))

    elif args.cmd == "material":
        if args.name:
            mat = bridge.get_material(args.name)
            print(json.dumps(mat or {"error": "not found"}, indent=2, ensure_ascii=False))
        else:
            mats = bridge.list_materials()
            print(json.dumps({"count": len(mats), "materials": sorted(mats)}, indent=2))

    elif args.cmd == "run":
        result = bridge.run_script(args.script)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
