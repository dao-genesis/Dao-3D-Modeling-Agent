"""核审门 (the ``verify.*`` tool group) — expose ``dao_audit`` over the tool surface.

The八层核审 (``00-本源_Origin/dao_audit.full_audit``) is the project's signature
verification gate, but it runs on the OCP/OCCT kernel while the live FreeCAD
kernel produces ``Part.Shape`` objects. This module bridges the two: it exports a
named object's shape to a transient BREP and reads it back as an OCP
``TopoDS_Shape``, then runs the full eight-layer audit — so both the MCP surface
(Devin Cloud path) and the native tool surface (Cascade path) can call the核审门.

Runs inside freecadcmd (headless); OCP ships alongside FreeCAD.
"""
import os
import sys
import tempfile


def _repo_root():
    # <root>/cad_agent/backends/freecad_verify.py -> up 3.
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def _load_dao_audit():
    """Import ``dao_audit`` off the五层 path (via ``_paths``); raise if OCP absent."""
    root = _repo_root()
    for p in (root, os.path.join(root, "00-本源_Origin")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import _paths  # noqa: F401  (registers 五层 sys.path)
    import dao_audit
    return dao_audit


def _part_to_topods(shape):
    """FreeCAD ``Part.Shape`` → OCP ``TopoDS_Shape`` via a transient BREP round-trip."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Shape

    f = tempfile.NamedTemporaryFile(suffix=".brep", delete=False)
    f.close()
    try:
        shape.exportBrep(f.name)
        topo = TopoDS_Shape()
        builder = BRep_Builder()
        if not BRepTools.Read_s(topo, f.name, builder):
            raise RuntimeError("BREP read failed (Part→OCP bridge)")
        if topo.IsNull():
            raise RuntimeError("bridged shape is null")
        return topo
    finally:
        try:
            os.unlink(f.name)
        except OSError:
            pass


def _slim_layers(layers):
    """Keep the per-layer verdict compact for a tool result (drop bulky detail)."""
    out = []
    for ly in layers:
        out.append({
            "layer": ly.get("layer"),
            "name": ly.get("name"),
            "score": ly.get("score"),
            "issues": ly.get("issues", []),
        })
    return out


def _native_audit(name, shape, vol_range):
    """OCP-free audit on FreeCAD's own Part kernel: validity, closure,
    solids/shells/faces census, volume window. Same return contract."""
    issues = []
    layers = []

    valid = bool(shape.isValid())
    layers.append({"layer": 1, "name": "topology", "score": 100 if valid else 0,
                   "issues": [] if valid else ["shape is not valid (BRepCheck)"]})
    if not valid:
        issues.append("invalid topology")

    solids = len(shape.Solids)
    closed = bool(shape.isClosed()) if solids == 0 else all(
        s.isClosed() for s in shape.Solids)
    geo_issues = []
    if solids == 0:
        geo_issues.append("no solid (open shell / wire only)")
    if not closed:
        geo_issues.append("not watertight")
    layers.append({"layer": 2, "name": "geometry",
                   "score": 100 - 50 * len(geo_issues), "issues": geo_issues})
    issues.extend(geo_issues)

    vol = float(shape.Volume)
    eng_issues = []
    if vol_range and not (vol_range[0] <= vol <= vol_range[1]):
        eng_issues.append("volume %.2f outside [%s, %s]"
                          % (vol, vol_range[0], vol_range[1]))
    layers.append({"layer": 3, "name": "engineering",
                   "score": 100 if not eng_issues else 40, "issues": eng_issues})
    issues.extend(eng_issues)

    score = sum(ly["score"] for ly in layers) / len(layers)
    grade = ("A" if score >= 95 else "B" if score >= 80 else
             "C" if score >= 60 else "D")
    return {"object": name, "grade": grade, "score": round(score, 1),
            "layers": layers, "issues": issues, "engine": "freecad-native",
            "volume": round(vol, 3), "solids": solids,
            "faces": len(shape.Faces)}


def register(state):
    def audit(a):
        """八层核审一个对象: 拓扑/几何/工程/格式/参数/意图/感知 → grade + score。"""
        name = a.get("object") or a.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("verify.audit 'object' must be an object name string")
        obj = state.doc.getObject(name)
        if obj is None:
            raise ValueError("no such object %r" % name)
        shape = getattr(obj, "Shape", None)
        if shape is None or shape.isNull():
            raise ValueError("object %r has no solid shape to audit" % name)

        vol_range = a.get("vol_range")
        if isinstance(vol_range, list) and len(vol_range) == 2:
            vol_range = (float(vol_range[0]), float(vol_range[1]))
        else:
            vol_range = None

        try:
            dao_audit = _load_dao_audit()
            topo = _part_to_topods(shape)
        except ImportError:
            # OCP not installed alongside this FreeCAD: audit natively on the
            # Part kernel so the gate still gives a real verdict.
            return _native_audit(name, shape, vol_range)

        r = dao_audit.full_audit(
            topo,
            name=name,
            vol_range=vol_range,
            specs=a.get("specs") or None,
            intent=a.get("intent") or None,
            process=a.get("process", "fdm"),
        )
        return {
            "object": name,
            "grade": r.get("grade"),
            "score": r.get("score"),
            "layers": _slim_layers(r.get("layers", [])),
            "issues": r.get("issues", []),
            "audit_ms": r.get("total_time_ms"),
        }

    return {"verify.audit": audit}
