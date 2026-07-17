"""Direct Sketcher protocol -- official geometry + constraint surface.

The ``param.sketch`` builder covers common closed profiles; this module opens
the official ``Sketcher::SketchObject`` API itself, one geometry / one
constraint at a time, exactly like a user drawing in the Sketcher workbench:

* ``sketch.create``     -- new sketch (optionally on a body / at a placement).
* ``sketch.geometry``   -- list a sketch's geometry with indices.
* ``sketch.add``        -- add line/circle/arc/point geometry (construction ok).
* ``sketch.constrain``  -- add any official constraint by type name.
* ``sketch.constraints``-- list constraints.
* ``sketch.dof``        -- degrees of freedom + solver state.
* ``sketch.remove``     -- delete a geometry or constraint by index.

Runs in both freecadcmd (headless) and the GUI bridge.
"""

import math

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


def _v(p):
    if isinstance(p, dict):
        return V(float(p.get("x", 0)), float(p.get("y", 0)), 0)
    return V(float(p[0]), float(p[1]), 0)


def register(state):

    def _sk(a, key="sketch"):
        name = a[key]
        o = state.doc.getObject(name)
        if o is None or o.TypeId != "Sketcher::SketchObject":
            names = [x.Name for x in state.doc.Objects
                     if x.TypeId == "Sketcher::SketchObject"]
            raise ValueError("no such sketch: %s; sketches: %s" % (name, names))
        return o

    def op_create(a):
        name = a.get("name") or "Sketch"
        body = None
        if a.get("body"):
            body = state.doc.getObject(a["body"])
        if body is not None:
            sk = body.newObject("Sketcher::SketchObject", name)
        else:
            sk = state.doc.addObject("Sketcher::SketchObject", name)
        if a.get("plane"):  # XY / XZ / YZ
            rot = {"XY": App.Rotation(),
                   "XZ": App.Rotation(V(1, 0, 0), 90),
                   "YZ": App.Rotation(V(0, 1, 0), -90).multiply(
                       App.Rotation(V(0, 0, 1), -90))}[a["plane"].upper()]
            sk.Placement = App.Placement(V(0, 0, 0), rot)
        state.doc.recompute()
        return {"sketch": sk.Name}

    def op_add(a):
        sk = _sk(a)
        kind = a["kind"]
        if kind == "line":
            geo = Part.LineSegment(_v(a["start"]), _v(a["end"]))
        elif kind == "circle":
            geo = Part.Circle(_v(a["center"]), V(0, 0, 1), float(a["radius"]))
        elif kind == "arc":
            circ = Part.Circle(_v(a["center"]), V(0, 0, 1), float(a["radius"]))
            geo = Part.ArcOfCircle(circ,
                                   math.radians(float(a.get("start_angle", 0))),
                                   math.radians(float(a.get("end_angle", 90))))
        elif kind == "point":
            geo = Part.Point(_v(a["at"]))
        else:
            raise ValueError("sketch.add: unknown kind %r "
                             "(line/circle/arc/point)" % kind)
        idx = sk.addGeometry(geo, bool(a.get("construction", False)))
        state.doc.recompute()
        return {"sketch": sk.Name, "index": idx, "kind": kind,
                "geometry_count": sk.GeometryCount}

    def op_geometry(a):
        sk = _sk(a)
        out = []
        for i, g in enumerate(sk.Geometry):
            item = {"index": i, "type": type(g).__name__,
                    "construction": bool(sk.getConstruction(i))}
            for attr in ("StartPoint", "EndPoint", "Center"):
                if hasattr(g, attr):
                    p = getattr(g, attr)
                    item[attr] = [round(p.x, 4), round(p.y, 4)]
            if hasattr(g, "Radius"):
                item["Radius"] = round(g.Radius, 4)
            out.append(item)
        return {"sketch": sk.Name, "geometry": out, "count": len(out)}

    def op_constrain(a):
        sk = _sk(a)
        ctype = a["type"]
        args = []
        for k in ("first", "first_pos", "second", "second_pos",
                  "third", "third_pos"):
            if k in a:
                args.append(int(a[k]))
        if "value" in a:
            val = a["value"]
            if ctype.lower() == "angle":
                val = math.radians(float(val))
            args.append(App.Units.Quantity(val) if isinstance(val, str)
                        else float(val))
        idx = sk.addConstraint(Sketcher.Constraint(ctype, *args))
        if a.get("name"):
            sk.renameConstraint(idx, a["name"])
        state.doc.recompute()
        return {"sketch": sk.Name, "index": idx, "type": ctype,
                "dof": _dof(sk)}

    def _dof(sk):
        try:
            sk.solve()
        except Exception:
            pass
        out = {"dof": None}
        try:
            out["dof"] = sk.getDoF() if hasattr(sk, "getDoF") else None
        except Exception:
            pass
        try:
            out["fully_constrained"] = bool(sk.FullyConstrained)
            if out["dof"] is None and out["fully_constrained"]:
                out["dof"] = 0
        except Exception:
            pass
        for attr, key in (("ConflictingConstraints", "conflicting"),
                          ("RedundantConstraints", "redundant")):
            try:
                out[key] = list(getattr(sk.Sketch if hasattr(sk, "Sketch")
                                        else sk, attr, []) or [])
            except Exception:
                pass
        return out

    def op_constraints(a):
        sk = _sk(a)
        out = []
        for i, c in enumerate(sk.Constraints):
            item = {"index": i, "type": c.Type, "name": c.Name,
                    "first": c.First, "second": c.Second}
            if c.Type in ("Distance", "DistanceX", "DistanceY", "Radius",
                          "Diameter", "Angle"):
                v = c.Value
                if c.Type == "Angle":
                    v = math.degrees(v)
                item["value"] = round(v, 6)
            out.append(item)
        return {"sketch": sk.Name, "constraints": out, "count": len(out)}

    def op_dof(a):
        sk = _sk(a)
        return {"sketch": sk.Name, **_dof(sk)}

    def op_external(a):
        """Add external geometry: project an edge/vertex of another object
        (e.g. 'Pad', 'Edge3') into the sketch as reference geometry."""
        sk = _sk(a)
        obj = state.doc.getObject(a["object"])
        if obj is None:
            raise ValueError("sketch.external: no such object: %s" % a["object"])
        sk.addExternal(obj.Name, a["sub"])
        state.doc.recompute()
        return {"sketch": sk.Name, "object": obj.Name, "sub": a["sub"],
                "external_count": len(sk.ExternalGeometry)}

    def op_expression(a):
        """Bind an expression to a named datum constraint
        (e.g. name='width', expr='Params.len*2'); empty expr clears it."""
        sk = _sk(a)
        path = "Constraints.%s" % a["name"]
        expr = a.get("expr")
        try:
            sk.setExpression(path, expr if expr else None)
        except Exception as exc:
            if "parse" in str(exc).lower():
                raise ValueError(
                    "expression parse failed for %r = %r; note single-letter "
                    "identifiers like W/P/A collide with unit tokens in the "
                    "official grammar -- use longer constraint/alias names "
                    "(e.g. 'width')" % (path, expr))
            raise
        state.doc.recompute()
        # engine stores the path with a leading dot (".Constraints.width")
        bound = dict((str(p).lstrip("."), str(e))
                     for p, e in (sk.ExpressionEngine or []))
        return {"sketch": sk.Name, "constraint": a["name"],
                "expression": bound.get(path), "dof": _dof(sk)}

    def op_remove(a):
        sk = _sk(a)
        idx = int(a["index"])
        if a.get("what", "geometry") == "constraint":
            sk.delConstraint(idx)
        else:
            sk.delGeometry(idx)
        state.doc.recompute()
        return {"sketch": sk.Name, "removed": idx,
                "geometry_count": sk.GeometryCount,
                "constraint_count": sk.ConstraintCount}

    return {
        "sketch.create": op_create,
        "sketch.add": op_add,
        "sketch.geometry": op_geometry,
        "sketch.constrain": op_constrain,
        "sketch.constraints": op_constraints,
        "sketch.dof": op_dof,
        "sketch.remove": op_remove,
        "sketch.external": op_external,
        "sketch.expression": op_expression,
    }
