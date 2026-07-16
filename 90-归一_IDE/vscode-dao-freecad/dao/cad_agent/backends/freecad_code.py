"""代码化 CAD 语义层 (the ``code.*`` tool group) — CadQuery/build123d 经脉.

AI 生成的不是专用命令序列, 而是通用 Python CAD 代码 (吃到 LLM 代码能力的全部
红利); 代码跑在 OCCT 上, 产物经瞬态 BREP 落回 live FreeCAD 文档, 与 solid.* /
param.* / verify.audit 同一工作区 — 「AI → 代码 → 几何内核」的间接路径, 而非
端到端直接生成几何.

  code.env  — 语义层可用性 (cadquery/build123d 版本探针)
  code.run  — 执行一段 CadQuery/build123d 脚本; 脚本把最终形体赋给 ``result``;
              形体落入文档成为命名对象, 返回几何量化指标

Runs inside freecadcmd (headless); cadquery/build123d import OCP alongside.
"""
import os
import tempfile

import Part  # provided by freecadcmd


def _probe():
    envs = {}
    try:
        import cadquery
        envs["cadquery"] = getattr(cadquery, "__version__", "?")
    except Exception as exc:
        envs["cadquery"] = "unavailable: %r" % (exc,)
    try:
        import build123d
        envs["build123d"] = getattr(build123d, "__version__", "?")
    except Exception as exc:
        envs["build123d"] = "unavailable: %r" % (exc,)
    return envs


def _result_to_topods(result):
    """Normalise a script ``result`` into an OCP ``TopoDS_Shape``.

    Accepts a CadQuery ``Workplane``/``Shape``, a build123d object, or a bare
    ``TopoDS_Shape`` — anything carrying ``.wrapped`` or ``.val()``.
    """
    obj = result
    if hasattr(obj, "val") and callable(obj.val):  # cq.Workplane
        obj = obj.val()
    if hasattr(obj, "wrapped"):  # cq.Shape / build123d Shape
        obj = obj.wrapped
    if obj is None:
        raise ValueError("script 'result' resolved to no shape")
    if not type(obj).__name__.startswith("TopoDS"):
        raise ValueError(
            "script 'result' must be a CadQuery/build123d shape or TopoDS_Shape "
            "(got %s)" % type(result).__name__)
    return obj


def _topods_to_part(topo):
    """OCP ``TopoDS_Shape`` → FreeCAD ``Part.Shape`` via a transient BREP.

    Newer OCCT writes BREP format 3+ which older FreeCAD kernels read as null,
    so ask for format VERSION_1 explicitly (readable by every OCCT).
    """
    from OCP.BRepTools import BRepTools

    f = tempfile.NamedTemporaryFile(suffix=".brep", delete=False)
    f.close()
    try:
        try:
            from OCP.TopTools import TopTools_FormatVersion
            BRepTools.Write_s(topo, f.name, False, False,
                              TopTools_FormatVersion.TopTools_FormatVersion_VERSION_1)
        except (ImportError, TypeError):
            BRepTools.Write_s(topo, f.name)
        sh = Part.Shape()
        sh.importBrep(f.name)
        if sh.isNull():
            raise RuntimeError("BREP import produced a null shape (OCP→Part bridge)")
        return sh
    finally:
        try:
            os.unlink(f.name)
        except OSError:
            pass


def _metrics(shape):
    bb = shape.BoundBox
    r = lambda x: round(float(x), 4)  # noqa: E731
    return {
        "valid": bool(shape.isValid()),
        "volume": r(shape.Volume),
        "area": r(shape.Area),
        "solids": len(shape.Solids),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
        "bbox": [r(bb.XMin), r(bb.YMin), r(bb.ZMin),
                 r(bb.XMax), r(bb.YMax), r(bb.ZMax)],
    }


def register(state):
    doc = state.doc

    def _put(name, shape):
        if not isinstance(name, str) or not name:
            raise ValueError("code.run 'name'/'out' must be a non-empty string")
        if name not in state.shapes and name in state.bodies:
            raise ValueError(
                "%r is a parametric body; pass a different 'out' name" % name)
        existing = state.shapes.get(name)
        obj = doc.getObject(existing) if existing else None
        if obj is None:
            obj = doc.addObject("Part::Feature", name)
            state.shapes[name] = obj.Name
        obj.Shape = shape
        doc.recompute()
        return obj

    def env(a):
        """语义层探针: cadquery/build123d 是否可用及版本。"""
        return {"engines": _probe()}

    def run(a):
        """执行 CadQuery/build123d 脚本, ``result`` 形体落入文档。"""
        code = a.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code.run needs 'code' (a python CAD script)")
        out = a.get("out") or a.get("name") or "CodeResult"

        ns = {"__builtins__": __builtins__}
        try:
            import cadquery as cq
            ns["cq"] = ns["cadquery"] = cq
        except Exception:
            pass
        try:
            import build123d as b3d
            ns["b3d"] = ns["build123d"] = b3d
        except Exception:
            pass
        if "cq" not in ns and "b3d" not in ns:
            raise RuntimeError(
                "no code-CAD engine available (pip install cadquery / build123d)")

        exec(compile(code, "<code.run>", "exec"), ns)
        if "result" not in ns:
            raise ValueError(
                "script must assign the final shape to a variable named 'result'")

        topo = _result_to_topods(ns["result"])
        part_shape = _topods_to_part(topo)
        obj = _put(out, part_shape)

        data = {"object": obj.Name, "engine": "cadquery" if "cq" in ns else "build123d"}
        data.update(_metrics(part_shape))

        export = a.get("export")
        if isinstance(export, str) and export:
            part_shape.exportStep(export) if export.lower().endswith(
                (".step", ".stp")) else part_shape.exportStl(export)
            data["exported"] = export
        return data

    return {"code.env": env, "code.run": run}
