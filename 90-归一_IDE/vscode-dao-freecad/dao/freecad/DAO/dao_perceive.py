"""DAO perception — the AI's eyes and structured understanding *inside* the GUI.

The headless ``view.*`` group tessellates shapes and paints them with matplotlib;
that is the offscreen optical channel. This module is different: it reads the
**real FreeCAD GUI** — the very viewport, selection and document state the human
is looking at — so the agent perceives exactly what the user perceives, and a bit
more (every object's pose, bounding box, mass properties and error state).

Registered as the ``gui.*`` tool group. Only available in a true ``freecad.exe``
session (it needs ``FreeCADGui``); headless callers simply won't see these ops.
"""
import os
import time

import FreeCAD as App

try:
    import FreeCADGui as Gui
    _HAVE_GUI = True
except Exception:                       # pragma: no cover - headless
    _HAVE_GUI = False

_SNAP_DIR = os.path.join(App.getUserAppDataDir(), "DAO_perception")

_STD_VIEWS = {
    "iso": "viewIsometric", "isometric": "viewIsometric",
    "axo": "viewAxonometric", "axonometric": "viewAxonometric",
    "front": "viewFront", "rear": "viewRear", "back": "viewRear",
    "top": "viewTop", "bottom": "viewBottom",
    "left": "viewLeft", "right": "viewRight",
}


def _round(x, n=4):
    try:
        return round(float(x), n)
    except Exception:
        return None


def register(state):
    if not _HAVE_GUI:
        return {}
    doc = state.doc
    os.makedirs(_SNAP_DIR, exist_ok=True)

    def _active_view():
        gdoc = Gui.getDocument(doc.Name) if doc else Gui.ActiveDocument
        if gdoc is None:
            raise RuntimeError("no active GUI document")
        return gdoc.ActiveView

    # ---- optical: capture the real viewport ----------------------------- #
    def op_snapshot(a):
        """Save the live 3D viewport to a PNG — what the human actually sees."""
        view = a.get("view")
        if a.get("fit", True) or view:
            try:
                av = _active_view()
                if view and view.lower() in _STD_VIEWS:
                    getattr(av, _STD_VIEWS[view.lower()])()
                Gui.SendMsgToActiveView("ViewFit")
            except Exception as exc:
                App.Console.PrintWarning("DAO snapshot view setup: %r\n" % (exc,))
        w = int(a.get("width", 1024))
        h = int(a.get("height", 768))
        bg = a.get("background", "Current")
        path = a.get("path") or os.path.join(
            _SNAP_DIR, "view_%s.png" % time.strftime("%H%M%S"))
        av = _active_view()
        av.saveImage(path, w, h, bg)
        return {"path": path, "width": w, "height": h,
                "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
                "view": view or "current"}

    def op_view(a):
        """Orient the camera to a standard view and fit (no capture)."""
        name = (a.get("view") or "iso").lower()
        av = _active_view()
        if name in _STD_VIEWS:
            getattr(av, _STD_VIEWS[name])()
        Gui.SendMsgToActiveView("ViewFit")
        return {"view": name}

    def op_fit(a):
        Gui.SendMsgToActiveView("ViewFit")
        return {"fit": True}

    # ---- appearance: the official ViewObject surface --------------------- #
    def op_appearance(a):
        """Read/write an object's visual state (ViewObject): visibility, shape
        color [r,g,b] 0-1, transparency 0-100, line width, display mode."""
        o = doc.getObject(a["object"])
        if o is None:
            raise ValueError("gui.appearance: no such object: %s" % a["object"])
        vo = o.ViewObject
        if "visible" in a:
            vo.Visibility = bool(a["visible"])
        if "color" in a:
            c = a["color"]
            vo.ShapeColor = (float(c[0]), float(c[1]), float(c[2]))
        if "transparency" in a:
            vo.Transparency = int(a["transparency"])
        if "line_width" in a:
            vo.LineWidth = float(a["line_width"])
        if "display_mode" in a:
            vo.DisplayMode = str(a["display_mode"])
        out = {"object": o.Name, "visible": bool(vo.Visibility)}
        try:
            out["color"] = [_round(x) for x in vo.ShapeColor[:3]]
            out["transparency"] = int(vo.Transparency)
        except Exception:
            pass
        try:
            out["display_mode"] = str(vo.DisplayMode)
            out["display_modes"] = list(vo.listDisplayModes())
        except Exception:
            pass
        return out

    def op_camera(a):
        """Read or set the live camera: position/orientation/focal distance;
        orthographic|perspective; or zoom onto one object."""
        av = _active_view()
        if a.get("projection"):
            av.setCameraType("Orthographic"
                             if a["projection"].lower().startswith("ortho")
                             else "Perspective")
        if a.get("focus"):
            o = doc.getObject(a["focus"])
            if o is None:
                raise ValueError("gui.camera: no such object: %s" % a["focus"])
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(o)
            Gui.SendMsgToActiveView("ViewSelection")
            Gui.Selection.clearSelection()
        cam = av.getCameraNode()
        if a.get("position"):
            p = a["position"]
            cam.position.setValue(float(p[0]), float(p[1]), float(p[2]))
        if a.get("orientation"):
            q = a["orientation"]
            cam.orientation.setValue(float(q[0]), float(q[1]),
                                     float(q[2]), float(q[3]))
        if a.get("fit"):
            Gui.SendMsgToActiveView("ViewFit")
        pos = cam.position.getValue()
        rot = cam.orientation.getValue().getValue()
        return {"type": av.getCameraType(),
                "position": [_round(pos[0]), _round(pos[1]), _round(pos[2])],
                "orientation": [_round(x) for x in rot]}

    # ---- structured understanding of the whole document ----------------- #
    def _describe(o):
        d = {"name": o.Name, "label": o.Label, "type": getattr(o, "TypeId", "")}
        try:
            d["visible"] = bool(o.ViewObject.Visibility)
        except Exception:
            d["visible"] = None
        try:
            d["state"] = list(o.State)
        except Exception:
            d["state"] = []
        pl = getattr(o, "Placement", None)
        if pl is not None:
            d["placement"] = {
                "pos": [_round(c) for c in pl.Base],
                "axis": [_round(c) for c in pl.Rotation.Axis],
                "angle_deg": _round(pl.Rotation.Angle * 57.29577951308232),
            }
        shp = getattr(o, "Shape", None)
        if shp is not None and not shp.isNull():
            bb = shp.BoundBox
            valid = True
            try:
                valid = bool(bb.isValid())
            except Exception:
                valid = abs(bb.XMin) < 1e99 and abs(bb.XMax) < 1e99
            if valid:
                d["bbox"] = {
                    "min": [_round(bb.XMin), _round(bb.YMin), _round(bb.ZMin)],
                    "max": [_round(bb.XMax), _round(bb.YMax), _round(bb.ZMax)],
                    "dims": [_round(bb.XLength), _round(bb.YLength), _round(bb.ZLength)],
                    "center": [_round(bb.Center.x), _round(bb.Center.y), _round(bb.Center.z)],
                }
            d["solids"] = len(shp.Solids)
            d["faces"] = len(shp.Faces)
            d["edges"] = len(shp.Edges)
            if shp.Solids:
                d["volume"] = _round(shp.Volume, 3)
                d["area"] = _round(shp.Area, 3)
        return d

    def op_scene(a):
        """Full structured scene graph of the live document."""
        objs = [_describe(o) for o in doc.Objects]
        errs = [o["name"] for o in objs
                if any(s in ("Error", "Invalid") for s in o.get("state", []))]
        gmn = [float("inf")] * 3
        gmx = [float("-inf")] * 3
        for o in objs:
            bb = o.get("bbox")
            if not bb:
                continue
            for i in range(3):
                lo, hi = bb["min"][i], bb["max"][i]
                if lo is not None and abs(lo) < 1e99 and abs(hi) < 1e99:
                    gmn[i] = min(gmn[i], lo)
                    gmx[i] = max(gmx[i], hi)
        bbox = None
        if gmn[0] != float("inf"):
            bbox = {"min": [_round(v) for v in gmn], "max": [_round(v) for v in gmx],
                    "dims": [_round(gmx[i] - gmn[i]) for i in range(3)]}
        return {"document": doc.Name, "count": len(objs), "objects": objs,
                "bbox": bbox, "errors": errs}

    # ---- what the human is pointing at ---------------------------------- #
    def op_selection(a):
        """Read the human's current selection: objects + sub-elements + points."""
        out = []
        for s in Gui.Selection.getSelectionEx():
            picked = []
            try:
                picked = [[_round(p.x), _round(p.y), _round(p.z)] for p in s.PickedPoints]
            except Exception:
                pass
            out.append({"object": s.ObjectName,
                        "label": getattr(s.Object, "Label", s.ObjectName),
                        "subs": list(s.SubElementNames),
                        "picked": picked})
        return {"selected": out, "count": len(out)}

    def op_select(a):
        """Drive the official selection: add objects (with optional
        sub-element names like Face3/Edge1) or clear when nothing given."""
        if not a.get("objects") and not a.get("object"):
            Gui.Selection.clearSelection()
            return {"selected": [], "count": 0}
        if a.get("clear", True):
            Gui.Selection.clearSelection()
        items = a.get("objects") or [{"object": a["object"],
                                      "subs": a.get("subs") or []}]
        for it in items:
            name = it["object"] if isinstance(it, dict) else it
            subs = (it.get("subs") or []) if isinstance(it, dict) else []
            o = doc.getObject(name)
            if o is None:
                raise ValueError("gui.select: no such object: %s" % name)
            if subs:
                for s in subs:
                    Gui.Selection.addSelection(o, s)
            else:
                Gui.Selection.addSelection(o)
        return op_selection({})

    def op_status(a):
        """One cheap call -> the live IDE heartbeat: document, counts,
        selection, active workbench, undo depth. No tessellation, no render;
        safe to poll every second from a dashboard or a remote agent."""
        sel = [s.ObjectName for s in Gui.Selection.getSelectionEx()]
        errors = 0
        for o in doc.Objects:
            try:
                if any(s in ("Error", "Invalid") for s in o.State):
                    errors += 1
            except Exception:
                pass
        try:
            wb = Gui.activeWorkbench().name()
        except Exception:
            wb = None
        return {"document": doc.Name,
                "path": getattr(doc, "FileName", ""),
                "objects": len(doc.Objects),
                "selection": sel,
                "workbench": wb,
                "undo_depth": getattr(doc, "UndoCount", 0),
                "redo_depth": getattr(doc, "RedoCount", 0),
                "errors": errors,
                "time": time.strftime("%Y-%m-%d %H:%M:%S")}

    def op_errors(a):
        bad = []
        for o in doc.Objects:
            try:
                st = list(o.State)
            except Exception:
                st = []
            if any(s in ("Error", "Invalid", "Touched") for s in st):
                bad.append({"name": o.Name, "label": o.Label, "state": st})
        return {"problems": bad, "count": len(bad)}

    # ---- official command surface: enumerate + dispatch ------------------ #
    def op_commands(a):
        """Enumerate the official GUI command surface (optionally filtered).

        Every toolbar button / menu entry in FreeCAD is a named command; this
        is the complete list of what the application itself can do."""
        names = sorted(Gui.listCommands())
        q = (a.get("query") or "").lower()
        if q:
            names = [n for n in names if q in n.lower()]
        return {"commands": names, "count": len(names)}

    def op_command(a):
        """Dispatch an official GUI command by name (``Gui.runCommand``) —
        the same path a human's toolbar click takes."""
        name = a["name"]
        known = name in Gui.listCommands()
        Gui.runCommand(name, int(a.get("index", 0)))
        doc.recompute()
        return {"command": name, "known": known,
                "objects": len(doc.Objects)}

    def op_workbench(a):
        """Report all workbenches, or activate one when ``name`` is given."""
        wbs = Gui.listWorkbenches()
        name = a.get("name")
        if name:
            match = next((k for k in wbs
                          if k.lower() == name.lower()
                          or k.lower() == (name + "Workbench").lower()), None)
            if match is None:
                return {"error": "No such workbench: %s" % name,
                        "available": sorted(wbs)}
            Gui.activateWorkbench(match)
        try:
            active = Gui.activeWorkbench().name()
        except Exception:
            active = None
        return {"active": active, "available": sorted(wbs)}

    return {
        "gui.snapshot": op_snapshot,
        "gui.commands": op_commands,
        "gui.command": op_command,
        "gui.workbench": op_workbench,
        "gui.view": op_view,
        "gui.fit": op_fit,
        "gui.appearance": op_appearance,
        "gui.camera": op_camera,
        "gui.scene": op_scene,
        "gui.selection": op_selection,
        "gui.select": op_select,
        "gui.status": op_status,
        "gui.errors": op_errors,
    }
