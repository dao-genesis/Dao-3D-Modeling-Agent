"""Generic object protocol -- every document object's full official surface.

The curated groups (``solid.*``, ``param.*``, ...) wrap common recipes and
``reflect.*`` opens the raw Python surface, but the *property system* is where a
FreeCAD user actually lives: every object is a bag of typed properties shown in
the property editor, driven by the expression engine, organised in the tree,
and backed by the application-wide preference/unit systems. This module makes
that whole layer first-class:

* ``obj.list``   -- all objects (name/label/type), optionally filtered.
* ``obj.get``    -- one object's full property map (or a subset).
* ``obj.set``    -- write any properties (numbers, strings, vectors, placements,
                    booleans, enums, links) exactly like the property editor.
* ``obj.add``    -- add any object by official type string (``Part::Box``, ...).
* ``obj.delete`` -- remove objects.
* ``obj.copy``   -- duplicate an object within the document.
* ``obj.expr``   -- bind/read/clear the expression engine on any property.
* ``pref.get`` / ``pref.set`` / ``pref.list`` -- the App.ParamGet preference tree.
* ``units.convert`` / ``units.parse`` -- the official quantity/unit engine.

Runs in both freecadcmd (headless) and the GUI bridge.
"""

import FreeCAD as App

V = App.Vector


def _enc(v, depth=0):
    """Encode a property value to JSON-friendly form."""
    if depth > 3:
        return str(v)
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if isinstance(v, App.Vector):
        return [round(v.x, 6), round(v.y, 6), round(v.z, 6)]
    if isinstance(v, App.Rotation):
        return {"axis": _enc(v.Axis), "angle": round(v.Angle * 180.0 / 3.141592653589793, 6)}
    if isinstance(v, App.Placement):
        return {"base": _enc(v.Base), "rotation": _enc(v.Rotation, depth + 1)}
    if hasattr(v, "Value") and hasattr(v, "Unit"):  # Quantity
        return {"value": v.Value, "unit": str(v.Unit)}
    if isinstance(v, (list, tuple)):
        return [_enc(x, depth + 1) for x in v]
    if hasattr(v, "Name") and hasattr(v, "TypeId"):  # DocumentObject link
        return {"$obj": v.Name}
    return str(v)


def _dec(v, doc):
    """Decode a JSON value into a live property value."""
    if isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v):
        return V(*[float(x) for x in v])
    if isinstance(v, dict):
        if "$obj" in v:
            return doc.getObject(v["$obj"])
        if "base" in v and "rotation" in v:
            rot = v["rotation"]
            r = App.Rotation(_dec(rot.get("axis", [0, 0, 1]), doc), rot.get("angle", 0))
            return App.Placement(_dec(v["base"], doc), r)
        if "axis" in v and "angle" in v:
            return App.Rotation(_dec(v["axis"], doc), v["angle"])
    return v


def register(state):

    def _obj(a, key="name"):
        name = a[key]
        o = state.doc.getObject(name)
        if o is None:
            for cand in state.doc.Objects:
                if cand.Label == name:
                    return cand
            raise KeyError("no such object: %s" % name)
        return o

    def op_list(a):
        q = (a.get("query") or "").lower()
        typ = a.get("type") or ""
        out = []
        for o in state.doc.Objects:
            if typ and not o.TypeId.startswith(typ):
                continue
            if q and q not in o.Name.lower() and q not in o.Label.lower():
                continue
            out.append({"name": o.Name, "label": o.Label, "type": o.TypeId,
                        "visible": bool(getattr(o, "Visibility", True))})
        return {"objects": out, "count": len(out)}

    def op_get(a):
        o = _obj(a)
        props = a.get("props") or o.PropertiesList
        vals, meta = {}, {}
        for p in props:
            try:
                vals[p] = _enc(getattr(o, p))
                meta[p] = {"type": o.getTypeIdOfProperty(p),
                           "group": o.getGroupOfProperty(p)}
                if o.getEnumerationsOfProperty(p):
                    meta[p]["enum"] = list(o.getEnumerationsOfProperty(p))
            except Exception as exc:
                vals[p] = "<error: %s>" % exc
        return {"name": o.Name, "label": o.Label, "type": o.TypeId,
                "properties": vals, "meta": meta}

    def op_set(a):
        o = _obj(a)
        done, errors = [], {}
        for p, v in (a.get("props") or {}).items():
            try:
                if p == "Label":
                    o.Label = str(v)
                else:
                    setattr(o, p, _dec(v, state.doc))
                done.append(p)
            except Exception as exc:
                errors[p] = str(exc)
        state.doc.recompute()
        out = {"name": o.Name, "set": done}
        if errors:
            out["errors"] = errors
        return out

    def op_add(a):
        o = state.doc.addObject(a["type"], a.get("name") or "Object")
        if a.get("props"):
            op_set({"name": o.Name, "props": a["props"]})
        state.doc.recompute()
        return {"name": o.Name, "label": o.Label, "type": o.TypeId}

    def op_delete(a):
        names = a.get("names") or [a["name"]]
        removed = []
        for n in names:
            o = _obj({"name": n})
            removed.append(o.Name)
            state.doc.removeObject(o.Name)
        state.doc.recompute()
        state.sync_from_doc()
        return {"removed": removed}

    def op_copy(a):
        o = _obj(a)
        c = state.doc.copyObject(o, bool(a.get("with_dependencies", False)))
        if a.get("new_label"):
            c.Label = a["new_label"]
        state.doc.recompute()
        return {"name": c.Name, "label": c.Label, "source": o.Name}

    def op_expr(a):
        o = _obj(a)
        prop = a.get("prop")
        if "expression" in a:  # bind or clear
            o.setExpression(prop, a["expression"])  # None clears
            state.doc.recompute()
        exprs = {p: e for p, e, *_ in getattr(o, "ExpressionEngine", [])}
        out = {"name": o.Name, "expressions": exprs}
        if prop:
            out["prop"] = prop
            out["value"] = _enc(getattr(o, prop.split(".")[0], None))
        return out

    def op_import(a):
        """Import any supported file into the live document by extension
        (STEP/IGES/BREP via Import, STL/OBJ/PLY via Mesh, else FreeCAD's
        registered importer)."""
        import os as _os
        path = a["path"]
        if not _os.path.isfile(path):
            raise ValueError("doc.import: no such file: %s" % path)
        before = {o.Name for o in state.doc.Objects}
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in ("step", "stp", "iges", "igs", "brep", "brp"):
            import Import
            Import.insert(path, state.doc.Name)
        elif ext in ("stl", "obj", "ply", "ast", "off"):
            import Mesh
            Mesh.insert(path, state.doc.Name)
        else:
            App.loadFile(path)
        state.doc.recompute()
        state.sync_from_doc()
        new = [{"name": o.Name, "label": o.Label, "type": o.TypeId}
               for o in state.doc.Objects if o.Name not in before]
        return {"path": path, "imported": new, "count": len(new)}

    # ---- preference tree (App.ParamGet) ---------------------------------- #
    _KINDS = (("Int", int), ("Float", float), ("Bool", bool), ("String", str))

    def _grp(path):
        p = path if path.startswith("User parameter:") else "User parameter:BaseApp/" + path
        return App.ParamGet(p)

    def op_pref_list(a):
        g = _grp(a["path"])
        c = g.GetContents() or []
        return {"path": a["path"],
                "groups": g.GetGroups(),
                "values": [{"kind": k, "name": n, "value": v} for k, n, v in c]}

    def op_pref_get(a):
        g = _grp(a["path"])
        for kind, _ in _KINDS:
            names = [n for k, n, v in (g.GetContents() or []) if n == a["name"]]
            if names:
                for k, n, v in g.GetContents():
                    if n == a["name"]:
                        return {"path": a["path"], "name": n, "kind": k, "value": v}
        return {"path": a["path"], "name": a["name"], "value": None}

    def op_pref_set(a):
        g = _grp(a["path"])
        v = a["value"]
        if isinstance(v, bool):
            g.SetBool(a["name"], v)
        elif isinstance(v, int):
            g.SetInt(a["name"], v)
        elif isinstance(v, float):
            g.SetFloat(a["name"], v)
        else:
            g.SetString(a["name"], str(v))
        return {"path": a["path"], "name": a["name"], "value": v}

    def op_export(a):
        """Export named objects to any supported format by extension:
        STEP/IGES/BREP via Import, STL/OBJ/PLY via Mesh, else App export."""
        import os as _os
        path = a["path"]
        names = a.get("objects") or ([a["object"]] if a.get("object") else None)
        if names is None:
            objs = [o for o in state.doc.Objects
                    if getattr(o, "Shape", None) is not None]
        else:
            objs = []
            for n in names:
                o = state.doc.getObject(n)
                if o is None:
                    raise ValueError("doc.export: no such object: %s" % n)
                objs.append(o)
        if not objs:
            raise ValueError("doc.export: nothing to export")
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in ("step", "stp", "iges", "igs", "brep", "brp"):
            import Import
            Import.export(objs, path)
        elif ext in ("stl", "obj", "ply", "ast", "off", "amf"):
            import Mesh
            Mesh.export(objs, path)
        else:
            App.ActiveDocument = state.doc
            import importlib
            mod = None
            for cand in ("importDXF", "importSVG"):
                if ext in ("dxf",) and cand == "importDXF":
                    mod = importlib.import_module(cand)
                elif ext in ("svg",) and cand == "importSVG":
                    mod = importlib.import_module(cand)
            if mod is None:
                raise ValueError("doc.export: unsupported extension %r" % ext)
            mod.export(objs, path)
        return {"path": path, "objects": [o.Name for o in objs],
                "bytes": _os.path.getsize(path) if _os.path.isfile(path) else 0}

    def op_expressions(a):
        """Document-wide expression census: every property bound to the
        expression engine, across all objects."""
        out = []
        for o in state.doc.Objects:
            try:
                exprs = o.ExpressionEngine or []
            except Exception:
                continue
            for pth, ex in exprs:
                out.append({"object": o.Name, "label": o.Label,
                            "property": str(pth), "expression": str(ex)})
        return {"expressions": out, "count": len(out)}

    # ---- official quantity/unit engine ----------------------------------- #
    def op_units_parse(a):
        q = App.Units.Quantity(a["quantity"])
        return {"value": q.Value, "unit": str(q.Unit),
                "user_string": q.UserString}

    def op_units_convert(a):
        q = App.Units.Quantity(a["quantity"])
        return {"quantity": a["quantity"], "to": a["to"],
                "value": float(q.getValueAs(a["to"]))}

    return {
        "obj.list": op_list,
        "obj.get": op_get,
        "obj.set": op_set,
        "obj.add": op_add,
        "obj.delete": op_delete,
        "obj.copy": op_copy,
        "obj.expr": op_expr,
        "doc.import": op_import,
        "doc.export": op_export,
        "obj.expressions": op_expressions,
        "pref.list": op_pref_list,
        "pref.get": op_pref_get,
        "pref.set": op_pref_set,
        "units.parse": op_units_parse,
        "units.convert": op_units_convert,
    }
