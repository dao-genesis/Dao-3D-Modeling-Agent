#!/usr/bin/env python3
"""
反者道之动 — FreeCAD 逆向探针 v1.0

在 freecadcmd 内部运行，从根本底层逆向解构 FreeCAD 软件本源：
  1. 枚举所有可用 Python 模块 (Part, Mesh, Draft, Sketcher, PartDesign, FEM, Path, TechDraw, ...)
  2. 逆向每个模块的类/函数/属性完整拓扑
  3. 探测所有参数化对象类型 (Part::Box, PartDesign::Pad, ...)
  4. 映射所有导入/导出格式
  5. 探测 OCC 底层能力
  6. 测试核心功能
  7. 输出完整 JSON 能力图谱

道生一，一生二，二生三，三生万物。
从一个 probe 脚本，映射 FreeCAD 一切能力。
"""

import json
import sys
import os
import traceback
import time
from pathlib import Path
import sys as _sys

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), Path(__file__).resolve().parent.parent)
if str(_DAO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

RESULT_PATH = os.environ.get("FC_PROBE_RESULT",
    str(_dao_paths.PROJECTS / "fc_output" / "_fc_probe_result.json"))


def _safe_dir(obj, max_depth=1, _depth=0):
    """Safe introspection of an object."""
    if _depth > max_depth:
        return "..."
    items = {}
    try:
        members = sorted(dir(obj))
    except Exception:
        return {"_error": "dir() failed"}
    for name in members:
        if name.startswith("__") and name.endswith("__"):
            continue
        try:
            attr = getattr(obj, name)
            t = type(attr).__name__
            if callable(attr):
                # Get signature if possible
                doc = ""
                try:
                    doc = (attr.__doc__ or "")[:200]
                except Exception:
                    pass
                items[name] = {"type": "callable", "kind": t, "doc": doc}
            else:
                items[name] = {"type": t, "value": repr(attr)[:100]}
        except Exception as e:
            items[name] = {"type": "inaccessible", "error": str(e)[:80]}
    return items


def probe_version():
    """探测 FreeCAD 版本信息"""
    import FreeCAD
    info = {
        "version": FreeCAD.Version(),
        "home_path": FreeCAD.getHomePath(),
        "user_home": FreeCAD.getUserAppDataDir(),
        "resource_dir": FreeCAD.getResourceDir(),
        "temp_path": FreeCAD.getUserCachePath() if hasattr(FreeCAD, "getUserCachePath") else "N/A",
    }
    try:
        info["config_dump"] = {k: str(v)[:200] for k, v in FreeCAD.ConfigDump().items()}
    except Exception:
        info["config_dump"] = {}
    return info


def probe_modules():
    """逆向探测所有可用模块"""
    import FreeCAD
    # Known FreeCAD module names to probe
    MODULE_NAMES = [
        "FreeCAD", "FreeCADGui", "Part", "Mesh", "MeshPart",
        "Draft", "Sketcher", "PartDesign", "FEM",
        "Path", "TechDraw", "Arch", "BIM",
        "Spreadsheet", "Drawing", "Image", "Points",
        "ReverseEngineering", "Robot", "Surface",
        "OpenSCAD", "Assembly", "CAM",
        "Import", "importDXF", "importSVG",
        "BOPTools", "CompoundTools",
        "BasicShapes", "Measure",
        "Materials", "AddonManager",
    ]
    results = {}
    for name in MODULE_NAMES:
        try:
            mod = __import__(name)
            members = {}
            for attr_name in sorted(dir(mod)):
                if attr_name.startswith("__"):
                    continue
                try:
                    attr = getattr(mod, attr_name)
                    t = type(attr).__name__
                    if t == "type" or t == "class":
                        # It's a class — get its methods
                        methods = [m for m in dir(attr)
                                   if not m.startswith("_") and callable(getattr(attr, m, None))]
                        members[attr_name] = {
                            "kind": "class",
                            "methods": methods[:50],
                            "method_count": len(methods)
                        }
                    elif callable(attr):
                        doc = (getattr(attr, "__doc__", "") or "")[:150]
                        members[attr_name] = {"kind": "function", "doc": doc}
                    else:
                        members[attr_name] = {"kind": t, "value": repr(attr)[:80]}
                except Exception as e:
                    members[attr_name] = {"kind": "error", "msg": str(e)[:60]}
            results[name] = {
                "available": True,
                "member_count": len(members),
                "members": members
            }
        except ImportError as e:
            results[name] = {"available": False, "error": str(e)[:100]}
        except Exception as e:
            results[name] = {"available": False, "error": str(e)[:100]}
    return results


def probe_part_deep():
    """深度逆向 Part 模块 — FreeCAD 几何核心"""
    import Part
    from FreeCAD import Base

    result = {
        "module_functions": [],
        "shape_types": [],
        "geom_types": [],
        "topo_types": [],
        "make_functions": [],
        "all_part_classes": [],
    }

    # All module-level functions
    for name in sorted(dir(Part)):
        if name.startswith("_"):
            continue
        attr = getattr(Part, name, None)
        if attr is None:
            continue
        t = type(attr).__name__
        if callable(attr) and t != "type":
            doc = (getattr(attr, "__doc__", "") or "")[:200]
            result["module_functions"].append({"name": name, "doc": doc})
            if name.startswith("make"):
                result["make_functions"].append(name)
        elif t == "type":
            # It's a class
            methods = [m for m in dir(attr) if not m.startswith("_")]
            result["all_part_classes"].append({
                "name": name,
                "methods": methods[:30],
                "method_count": len(methods),
            })

    # Shape class deep introspection
    try:
        shape = Part.Shape()
        shape_methods = []
        for m in sorted(dir(shape)):
            if m.startswith("_"):
                continue
            try:
                attr = getattr(shape, m)
                doc = (getattr(attr, "__doc__", "") or "")[:150] if callable(attr) else ""
                shape_methods.append({
                    "name": m,
                    "callable": callable(attr),
                    "type": type(attr).__name__,
                    "doc": doc
                })
            except Exception:
                pass
        result["Shape_methods"] = shape_methods
    except Exception as e:
        result["Shape_error"] = str(e)

    # TopoShape types
    result["topo_types"] = [
        "Vertex", "Edge", "Wire", "Face", "Shell", "Solid",
        "CompSolid", "Compound"
    ]

    # Geometry types available
    geom_names = [n for n in dir(Part) if not n.startswith("_")
                  and type(getattr(Part, n, None)).__name__ == "type"]
    result["geom_types"] = geom_names

    return result


def probe_parametric_objects():
    """探测所有可用的参数化对象类型"""
    import FreeCAD as App

    doc = App.newDocument("_probe_types")
    result = {"types_tested": [], "types_available": [], "types_failed": []}

    # Known parametric type prefixes
    TYPE_NAMES = [
        # Part
        "Part::Box", "Part::Cylinder", "Part::Sphere", "Part::Cone",
        "Part::Torus", "Part::Ellipsoid", "Part::Prism", "Part::Wedge",
        "Part::Helix", "Part::Spiral", "Part::Plane",
        "Part::Extrusion", "Part::Revolution", "Part::Loft", "Part::Sweep",
        "Part::Offset3DSurface", "Part::Thickness",
        "Part::Fuse", "Part::Cut", "Part::Common", "Part::Section",
        "Part::MultiCommon", "Part::MultiFuse",
        "Part::Fillet", "Part::Chamfer",
        "Part::Mirror", "Part::Compound",
        "Part::Feature", "Part::FeaturePython",
        "Part::Part2DObjectPython",
        # PartDesign
        "PartDesign::Body", "PartDesign::Pad", "PartDesign::Pocket",
        "PartDesign::Revolution", "PartDesign::Groove",
        "PartDesign::Fillet", "PartDesign::Chamfer",
        "PartDesign::Hole", "PartDesign::Mirrored",
        "PartDesign::LinearPattern", "PartDesign::PolarPattern",
        "PartDesign::MultiTransform",
        "PartDesign::AdditivePipe", "PartDesign::SubtractivePipe",
        "PartDesign::AdditiveLoft", "PartDesign::SubtractiveLoft",
        "PartDesign::AdditivePrism", "PartDesign::SubtractivePrism",
        "PartDesign::AdditiveBox", "PartDesign::SubtractiveBox",
        "PartDesign::AdditiveCylinder", "PartDesign::SubtractiveCylinder",
        "PartDesign::AdditiveSphere", "PartDesign::SubtractiveSphere",
        "PartDesign::AdditiveCone", "PartDesign::SubtractiveCone",
        "PartDesign::AdditiveTorus", "PartDesign::SubtractiveTorus",
        "PartDesign::AdditiveWedge", "PartDesign::SubtractiveWedge",
        "PartDesign::AdditiveEllipsoid", "PartDesign::SubtractiveEllipsoid",
        "PartDesign::AdditiveHelix", "PartDesign::SubtractiveHelix",
        "PartDesign::Thickness", "PartDesign::Draft",
        "PartDesign::Boolean",
        # Sketcher
        "Sketcher::SketchObject", "Sketcher::SketchObjectPython",
        # Mesh
        "Mesh::Feature", "Mesh::FeaturePython",
        "Mesh::Cube", "Mesh::Cylinder", "Mesh::Sphere",
        "Mesh::Cone", "Mesh::Torus", "Mesh::Ellipsoid",
        # Spreadsheet
        "Spreadsheet::Sheet",
        # FEM
        "Fem::FemAnalysis", "Fem::FemMeshObject",
        "Fem::ConstraintFixed", "Fem::ConstraintForce",
        "Fem::FemMeshShapeNetgenObject",
        # TechDraw
        "TechDraw::DrawPage", "TechDraw::DrawSVGTemplate",
        "TechDraw::DrawViewPart", "TechDraw::DrawViewDimension",
        # Draft-like
        "App::Line", "App::Plane",
        "App::FeaturePython", "App::DocumentObjectGroup",
        "App::Part", "App::Origin",
    ]

    for type_name in TYPE_NAMES:
        result["types_tested"].append(type_name)
        try:
            obj = doc.addObject(type_name, "_test")
            props = []
            for p in obj.PropertiesList:
                try:
                    val = getattr(obj, p)
                    props.append({
                        "name": p,
                        "type": obj.getTypeIdOfProperty(p),
                        "value": repr(val)[:80],
                    })
                except Exception:
                    props.append({"name": p, "type": "unknown"})
            result["types_available"].append({
                "type": type_name,
                "property_count": len(props),
                "properties": props,
            })
            doc.removeObject(obj.Name)
        except Exception as e:
            result["types_failed"].append({
                "type": type_name,
                "error": str(e)[:100]
            })

    App.closeDocument("_probe_types")
    return result


def probe_import_export():
    """探测所有支持的导入/导出格式"""
    import FreeCAD as App

    result = {"formats": {}}

    # Try to get the format list from Import module
    try:
        import Import
        result["Import_module"] = {
            "available": True,
            "members": [m for m in dir(Import) if not m.startswith("_")]
        }
    except ImportError:
        result["Import_module"] = {"available": False}

    # Known format extensions and their handler modules
    FORMAT_MAP = {
        "STL":   {"ext": ".stl",   "module": "Mesh"},
        "STEP":  {"ext": ".step",  "module": "Part"},
        "STP":   {"ext": ".stp",   "module": "Part"},
        "IGES":  {"ext": ".iges",  "module": "Part"},
        "IGS":   {"ext": ".igs",   "module": "Part"},
        "BREP":  {"ext": ".brep",  "module": "Part"},
        "BRP":   {"ext": ".brp",   "module": "Part"},
        "OBJ":   {"ext": ".obj",   "module": "Mesh"},
        "PLY":   {"ext": ".ply",   "module": "Mesh"},
        "OFF":   {"ext": ".off",   "module": "Mesh"},
        "SMF":   {"ext": ".smf",   "module": "Mesh"},
        "DAE":   {"ext": ".dae",   "module": "Mesh"},
        "3MF":   {"ext": ".3mf",   "module": "Mesh"},
        "AMF":   {"ext": ".amf",   "module": "Mesh"},
        "FCStd": {"ext": ".FCStd", "module": "FreeCAD"},
        "DXF":   {"ext": ".dxf",   "module": "importDXF"},
        "SVG":   {"ext": ".svg",   "module": "importSVG"},
        "IFC":   {"ext": ".ifc",   "module": "importIFC"},
        "JSON":  {"ext": ".json",  "module": "Mesh"},
        "AST":   {"ext": ".ast",   "module": "Mesh"},
        "BMS":   {"ext": ".bms",   "module": "Mesh"},
        "IV":    {"ext": ".iv",    "module": "Part"},
        "VRML":  {"ext": ".wrl",   "module": "FreeCAD"},
        "CSG":   {"ext": ".csg",   "module": "OpenSCAD"},
        "SCAD":  {"ext": ".scad",  "module": "OpenSCAD"},
        "INP":   {"ext": ".inp",   "module": "FEM"},
        "UNV":   {"ext": ".unv",   "module": "FEM"},
        "YAML":  {"ext": ".yaml",  "module": "Materials"},
        "GCODE": {"ext": ".gcode", "module": "Path"},
    }

    # Test actual Part.export / Mesh.export capabilities
    import Part, Mesh
    # Create test shape
    box = Part.makeBox(10, 10, 10)

    import tempfile
    tmp = Path(tempfile.gettempdir()) / "_fc_probe_export"
    tmp.mkdir(exist_ok=True)

    for fmt_name, info in FORMAT_MAP.items():
        ext = info["ext"]
        test_path = str(tmp / f"_test{ext}")
        export_ok = False
        import_ok = False
        export_err = ""
        import_err = ""

        # Test export
        try:
            if info["module"] == "Mesh":
                mesh = Mesh.Mesh()
                mesh.addFacets(box.tessellate(0.5)[0], box.tessellate(0.5)[1])
                # Some formats might not be available
                try:
                    mesh.write(test_path)
                    export_ok = Path(test_path).exists() and Path(test_path).stat().st_size > 0
                except Exception as me:
                    export_err = str(me)[:80]
            elif info["module"] == "Part":
                try:
                    Part.export([box], test_path)
                    export_ok = Path(test_path).exists() and Path(test_path).stat().st_size > 0
                except Exception as pe:
                    export_err = str(pe)[:80]
            elif info["module"] == "FreeCAD":
                # FCStd export via document
                if ext == ".FCStd":
                    import FreeCAD as App
                    doc = App.newDocument("_exp_test")
                    f = doc.addObject("Part::Feature", "box")
                    f.Shape = box
                    doc.recompute()
                    doc.saveAs(test_path)
                    App.closeDocument("_exp_test")
                    export_ok = Path(test_path).exists()
            else:
                try:
                    mod = __import__(info["module"])
                    export_ok = hasattr(mod, "export")
                except ImportError:
                    export_err = f"Module {info['module']} not available"
        except Exception as e:
            export_err = str(e)[:80]

        # Test import (only for formats we exported)
        if export_ok and Path(test_path).exists():
            try:
                if info["module"] == "Mesh":
                    m = Mesh.Mesh(test_path)
                    import_ok = m.CountPoints > 0
                elif info["module"] == "Part":
                    sh = Part.read(test_path)
                    import_ok = not sh.isNull()
            except Exception as ie:
                import_err = str(ie)[:80]

        result["formats"][fmt_name] = {
            "ext": ext,
            "handler": info["module"],
            "export_ok": export_ok,
            "import_ok": import_ok,
            "export_error": export_err,
            "import_error": import_err,
        }

    # Cleanup
    try:
        import shutil
        shutil.rmtree(str(tmp), ignore_errors=True)
    except Exception:
        pass

    return result


def probe_occ():
    """探测 OpenCASCADE 底层能力"""
    result = {"available": False, "modules": {}, "version": "unknown"}

    # Check if OCC is available via FreeCAD
    try:
        import Part
        # Part wraps OCC — get OCC version
        try:
            result["version"] = Part.OCC_VERSION if hasattr(Part, "OCC_VERSION") else "wrapped"
        except Exception:
            pass
    except Exception:
        pass

    # Try direct OCC access
    OCC_MODULES = [
        "OCC.Core.gp", "OCC.Core.TopoDS", "OCC.Core.BRep",
        "OCC.Core.BRepBuilderAPI", "OCC.Core.BRepAlgoAPI",
        "OCC.Core.BRepFilletAPI", "OCC.Core.BRepOffsetAPI",
        "OCC.Core.BRepPrimAPI", "OCC.Core.BRepTools",
        "OCC.Core.GeomAPI", "OCC.Core.GC", "OCC.Core.Geom",
        "OCC.Core.TColgp", "OCC.Core.TopExp", "OCC.Core.TopAbs",
        "OCC.Core.STEPControl", "OCC.Core.IGESControl",
        "OCC.Core.ShapeAnalysis", "OCC.Core.ShapeFix",
        "OCC.Core.ShapeUpgrade", "OCC.Core.BOPAlgo",
        "OCC.Core.BRepCheck", "OCC.Core.BRepMesh",
    ]
    for mod_name in OCC_MODULES:
        try:
            mod = __import__(mod_name, fromlist=[""])
            members = [m for m in dir(mod) if not m.startswith("_")]
            result["modules"][mod_name] = {
                "available": True,
                "member_count": len(members),
                "members": members[:30]
            }
            result["available"] = True
        except ImportError:
            result["modules"][mod_name] = {"available": False}
        except Exception as e:
            result["modules"][mod_name] = {"available": False, "error": str(e)[:80]}

    return result


def probe_shape_methods():
    """逆向 Part.Shape 的所有可用操作方法 — FreeCAD 几何操作的根"""
    import Part
    from FreeCAD import Base

    box = Part.makeBox(20, 15, 10)
    cyl = Part.makeCylinder(5, 20)

    methods = {}
    for name in sorted(dir(box)):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(box, name)
            info = {
                "callable": callable(attr),
                "type": type(attr).__name__,
            }
            if callable(attr):
                info["doc"] = (getattr(attr, "__doc__", "") or "")[:300]
            else:
                info["value_sample"] = repr(attr)[:100]
            methods[name] = info
        except Exception as e:
            methods[name] = {"error": str(e)[:80]}

    return methods


def probe_base_vector():
    """探测 Base.Vector 和 Base.Matrix 能力"""
    from FreeCAD import Base

    vec_methods = [m for m in dir(Base.Vector(0, 0, 0)) if not m.startswith("_")]
    mat_methods = [m for m in dir(Base.Matrix()) if not m.startswith("_")]
    placement_methods = [m for m in dir(Base.Placement()) if not m.startswith("_")]
    rotation_methods = [m for m in dir(Base.Rotation()) if not m.startswith("_")]

    return {
        "Vector_methods": vec_methods,
        "Matrix_methods": mat_methods,
        "Placement_methods": placement_methods,
        "Rotation_methods": rotation_methods,
    }


def probe_functional_tests():
    """功能性测试 — 验证核心能力"""
    import FreeCAD as App
    import Part
    from FreeCAD import Base

    tests = {}

    # 1. Primitives
    try:
        primitives = {
            "Box": Part.makeBox(10, 10, 10),
            "Cylinder": Part.makeCylinder(5, 20),
            "Sphere": Part.makeSphere(10),
            "Cone": Part.makeCone(10, 5, 20),
            "Torus": Part.makeTorus(10, 3),
            "Wedge": Part.makeWedge(0, 0, 0, 5, 5, 20, 15, 10),
        }
        for name, sh in primitives.items():
            tests[f"primitive_{name}"] = {
                "ok": not sh.isNull() and sh.Volume > 0,
                "volume": round(sh.Volume, 2),
                "faces": len(sh.Faces),
                "edges": len(sh.Edges),
            }
    except Exception as e:
        tests["primitives_error"] = str(e)

    # 2. Boolean operations
    try:
        a = Part.makeBox(20, 20, 20)
        b = Part.makeCylinder(5, 30, Base.Vector(10, 10, 0))
        fused = a.fuse(b)
        cut = a.cut(b)
        common = a.common(b)
        tests["boolean_fuse"] = {"ok": fused.Volume > 0, "volume": round(fused.Volume, 2)}
        tests["boolean_cut"] = {"ok": cut.Volume > 0, "volume": round(cut.Volume, 2)}
        tests["boolean_common"] = {"ok": common.Volume > 0, "volume": round(common.Volume, 2)}
    except Exception as e:
        tests["boolean_error"] = str(e)

    # 3. Modifiers
    try:
        box = Part.makeBox(20, 15, 10)
        filleted = box.makeFillet(2, box.Edges)
        tests["fillet"] = {"ok": filleted.Volume > 0, "volume": round(filleted.Volume, 2)}
        chamfered = box.makeChamfer(1.5, box.Edges)
        tests["chamfer"] = {"ok": chamfered.Volume > 0, "volume": round(chamfered.Volume, 2)}
    except Exception as e:
        tests["modifier_error"] = str(e)

    # 4. Transforms
    try:
        box = Part.makeBox(10, 10, 10)
        cp = box.copy()
        cp.translate(Base.Vector(20, 0, 0))
        tests["translate"] = {"ok": cp.BoundBox.XMin > 15}
        cp2 = box.copy()
        cp2.rotate(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 45)
        tests["rotate"] = {"ok": True}
        cp3 = box.mirror(Base.Vector(0, 0, 0), Base.Vector(1, 0, 0))
        tests["mirror"] = {"ok": cp3.Volume > 0}
        mat = App.Matrix()
        mat.scale(2, 1, 1)
        scaled = box.transformGeometry(mat)
        tests["scale_transform"] = {"ok": abs(scaled.Volume - 2000) < 1}
    except Exception as e:
        tests["transform_error"] = str(e)

    # 5. Extrude / Revolve / Loft / Sweep
    try:
        wire = Part.makePolygon([Base.Vector(0,0,0), Base.Vector(10,0,0),
                                  Base.Vector(10,10,0), Base.Vector(0,10,0),
                                  Base.Vector(0,0,0)])
        face = Part.Face(wire)
        extruded = face.extrude(Base.Vector(0, 0, 15))
        tests["extrude"] = {"ok": extruded.Volume > 0, "volume": round(extruded.Volume, 2)}

        # Revolve
        pts = [Base.Vector(5, 0, 0), Base.Vector(10, 0, 0),
               Base.Vector(10, 0, 10), Base.Vector(5, 0, 10), Base.Vector(5, 0, 0)]
        wire_r = Part.makePolygon(pts)
        face_r = Part.Face(wire_r)
        revolved = face_r.revolve(Base.Vector(0,0,0), Base.Vector(0,0,1), 360)
        tests["revolve"] = {"ok": revolved.Volume > 0, "volume": round(revolved.Volume, 2)}

        # Loft
        w1 = Part.makeCircle(5, Base.Vector(0,0,0))
        w2 = Part.makeCircle(10, Base.Vector(0,0,20))
        lofted = Part.makeLoft([Part.Wire([w1]), Part.Wire([w2])], True)
        tests["loft"] = {"ok": lofted.Volume > 0, "volume": round(lofted.Volume, 2)}

        # Helix + Pipe
        helix = Part.makeHelix(5, 30, 10)
        e0 = helix.Edges[0]
        start = helix.Vertexes[0].Point
        tang = e0.tangentAt(e0.FirstParameter)
        prof = Part.Wire([Part.makeCircle(1.5, start, tang)])
        pipe = Part.Wire([helix]).makePipeShell([prof], True, False)
        tests["helix_pipe"] = {"ok": not pipe.isNull() and pipe.Volume > 0,
                                "volume": round(pipe.Volume, 2)}
    except Exception as e:
        tests["advanced_ops_error"] = str(e)

    # 6. Parametric document objects
    try:
        doc = App.newDocument("_func_test")
        box_obj = doc.addObject("Part::Box", "Box")
        box_obj.Length = 30
        box_obj.Width = 20
        box_obj.Height = 10
        doc.recompute()
        tests["parametric_box"] = {
            "ok": box_obj.Shape.Volume > 0,
            "volume": round(box_obj.Shape.Volume, 2),
            "props": box_obj.PropertiesList[:20],
        }
        # PartDesign Body + Pad
        try:
            body = doc.addObject("PartDesign::Body", "Body")
            tests["partdesign_body"] = {"ok": True}
        except Exception as pde:
            tests["partdesign_body"] = {"ok": False, "error": str(pde)[:80]}
        App.closeDocument("_func_test")
    except Exception as e:
        tests["parametric_error"] = str(e)

    # 7. Shape analysis
    try:
        box = Part.makeBox(20, 15, 10)
        tests["shape_analysis"] = {
            "volume": round(box.Volume, 4),
            "area": round(box.Area, 4),
            "center_of_mass": [round(c, 4) for c in [box.CenterOfMass.x, box.CenterOfMass.y, box.CenterOfMass.z]],
            "is_closed": box.isClosed(),
            "is_valid": box.isValid(),
            "bounding_box": {
                "x": [round(box.BoundBox.XMin, 2), round(box.BoundBox.XMax, 2)],
                "y": [round(box.BoundBox.YMin, 2), round(box.BoundBox.YMax, 2)],
                "z": [round(box.BoundBox.ZMin, 2), round(box.BoundBox.ZMax, 2)],
            },
            "faces": len(box.Faces),
            "edges": len(box.Edges),
            "vertexes": len(box.Vertexes),
            "solids": len(box.Solids),
            "shells": len(box.Shells),
            "ok": True,
        }
    except Exception as e:
        tests["shape_analysis_error"] = str(e)

    # 8. Distance measurement
    try:
        a = Part.makeBox(10, 10, 10)
        b = Part.makeBox(10, 10, 10, Base.Vector(20, 0, 0))
        dist = a.distToShape(b)
        tests["distance"] = {"ok": True, "min_dist": round(dist[0], 4)}
    except Exception as e:
        tests["distance_error"] = str(e)

    # 9. Tessellation (mesh generation from solid)
    try:
        box = Part.makeBox(10, 10, 10)
        verts, faces = box.tessellate(0.5)
        tests["tessellation"] = {
            "ok": len(verts) > 0 and len(faces) > 0,
            "vertices": len(verts),
            "triangles": len(faces),
        }
    except Exception as e:
        tests["tessellation_error"] = str(e)

    # 10. BSpline / Bezier
    try:
        pts = [Base.Vector(0,0,0), Base.Vector(10,10,0),
               Base.Vector(20,5,0), Base.Vector(30,15,0)]
        bsp = Part.BSplineCurve()
        bsp.interpolate(pts)
        sh = bsp.toShape()
        tests["bspline"] = {"ok": sh.Length > 0, "length": round(sh.Length, 2)}

        bz = Part.BezierCurve()
        bz.setPoles(pts)
        sh_bz = bz.toShape()
        tests["bezier"] = {"ok": sh_bz.Length > 0, "length": round(sh_bz.Length, 2)}
    except Exception as e:
        tests["curve_error"] = str(e)

    return tests


def probe_sketcher():
    """探测 Sketcher 能力"""
    result = {"available": False}
    try:
        import Sketcher
        import FreeCAD as App
        from FreeCAD import Base

        result["available"] = True
        result["constraint_types"] = [m for m in dir(Sketcher) if "Constraint" in m]
        result["members"] = [m for m in dir(Sketcher) if not m.startswith("_")]

        # Test sketch creation
        doc = App.newDocument("_sketch_test")
        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        # Add a line
        sketch.addGeometry(Part.LineSegment(Base.Vector(0,0,0), Base.Vector(10,0,0)))
        # Add a circle
        import Part
        sketch.addGeometry(Part.Circle(Base.Vector(5,5,0), Base.Vector(0,0,1), 3))
        doc.recompute()
        result["test_sketch"] = {
            "ok": True,
            "geometry_count": sketch.GeometryCount,
            "constraint_count": sketch.ConstraintCount,
        }
        App.closeDocument("_sketch_test")
    except ImportError:
        result["error"] = "Sketcher module not available"
    except Exception as e:
        result["error"] = str(e)[:200]
    return result


def probe_mesh():
    """探测 Mesh 模块能力"""
    result = {"available": False}
    try:
        import Mesh
        import Part
        result["available"] = True
        result["members"] = [m for m in dir(Mesh) if not m.startswith("_")]

        # Mesh from solid
        box = Part.makeBox(10, 10, 10)
        verts, faces = box.tessellate(0.5)
        mesh = Mesh.Mesh()
        mesh.addFacets(verts, faces)
        result["test_mesh"] = {
            "ok": mesh.CountPoints > 0,
            "points": mesh.CountPoints,
            "facets": mesh.CountFacets,
        }

        # Mesh class methods
        mesh_methods = [m for m in dir(mesh) if not m.startswith("_")]
        result["Mesh_methods"] = mesh_methods
    except ImportError:
        result["error"] = "Mesh module not available"
    except Exception as e:
        result["error"] = str(e)[:200]
    return result


def main():
    """主探针入口"""
    t0 = time.time()
    report = {
        "probe_version": "1.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sections": {},
        "errors": [],
    }

    sections = [
        ("version",            probe_version),
        ("modules",            probe_modules),
        ("part_deep",          probe_part_deep),
        ("shape_methods",      probe_shape_methods),
        ("base_types",         probe_base_vector),
        ("parametric_objects", probe_parametric_objects),
        ("import_export",      probe_import_export),
        ("occ",                probe_occ),
        ("functional_tests",   probe_functional_tests),
        ("sketcher",           probe_sketcher),
        ("mesh",               probe_mesh),
    ]

    for name, fn in sections:
        print(f"[probe] {name}...", flush=True)
        try:
            report["sections"][name] = fn()
        except Exception as e:
            report["errors"].append(f"{name}: {e}\n{traceback.format_exc()}")
            report["sections"][name] = {"_error": str(e)}

    report["elapsed_s"] = round(time.time() - t0, 2)

    # Summary
    summary = {
        "freecad_available": True,
        "sections_ok": len(report["sections"]) - len(report["errors"]),
        "sections_failed": len(report["errors"]),
        "elapsed_s": report["elapsed_s"],
    }
    if "functional_tests" in report["sections"]:
        ft = report["sections"]["functional_tests"]
        total = len(ft)
        passed = sum(1 for v in ft.values() if isinstance(v, dict) and v.get("ok"))
        summary["functional_tests"] = {"total": total, "passed": passed, "failed": total - passed}

    if "parametric_objects" in report["sections"]:
        po = report["sections"]["parametric_objects"]
        summary["parametric_types_available"] = len(po.get("types_available", []))
        summary["parametric_types_failed"] = len(po.get("types_failed", []))

    if "import_export" in report["sections"]:
        ie = report["sections"]["import_export"]
        fmts = ie.get("formats", {})
        summary["export_formats_ok"] = sum(1 for v in fmts.values() if v.get("export_ok"))
        summary["import_formats_ok"] = sum(1 for v in fmts.values() if v.get("import_ok"))

    if "modules" in report["sections"]:
        mods = report["sections"]["modules"]
        summary["modules_available"] = [k for k, v in mods.items() if v.get("available")]
        summary["modules_unavailable"] = [k for k, v in mods.items() if not v.get("available")]

    report["summary"] = summary

    # Write result
    Path(RESULT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'='*60}")
    print(f"[probe] 完成 — {report['elapsed_s']}s")
    print(f"[probe] 模块: {len(summary.get('modules_available', []))} 可用")
    print(f"[probe] 参数化类型: {summary.get('parametric_types_available', 0)} 可用")
    print(f"[probe] 导出格式: {summary.get('export_formats_ok', 0)} 可用")
    print(f"[probe] 功能测试: {summary.get('functional_tests', {}).get('passed', 0)}/{summary.get('functional_tests', {}).get('total', 0)} 通过")
    print(f"[probe] 结果: {RESULT_PATH}")
    print(f"{'='*60}")
    print("PROBE_COMPLETE")


if __name__ == "__main__":
    main()
