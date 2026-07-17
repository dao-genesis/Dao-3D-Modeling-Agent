"""Framework unit tests — no FreeCAD required."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cad_agent.tools import ToolRegistry, ToolResult  # noqa: E402


def test_toolresult_envelope():
    r = ToolResult.success(volume=10)
    assert r.ok and r.data["volume"] == 10 and r.error is None
    d = r.to_dict()
    assert d["ok"] and d["data"]["volume"] == 10
    f = ToolResult.failure("boom", code=3)
    assert not f.ok and f.error == "boom" and f.data["code"] == 3


def test_register_and_call():
    reg = ToolRegistry()
    reg.register("solid.box", lambda a: ToolResult.success(v=a["l"] ** 3), "cube")
    r = reg.call("solid.box", {"l": 2})
    assert r.ok and r.data["v"] == 8
    assert r.tool == "solid.box" and r.args == {"l": 2}
    assert r.elapsed_ms >= 0


def test_duplicate_registration_rejected():
    reg = ToolRegistry()
    reg.register("a.b", lambda a: ToolResult.success())
    with pytest.raises(ValueError):
        reg.register("a.b", lambda a: ToolResult.success())


def test_unknown_tool():
    reg = ToolRegistry()
    r = reg.call("nope", {})
    assert not r.ok and "unknown tool" in r.error


def test_synonym_resolves_transparently():
    reg = ToolRegistry()
    reg.register("solid.union", lambda a: ToolResult.success(v=1))
    r = reg.call("solid.fuse", {"a": "x", "b": "y"})
    assert r.ok and r.data["v"] == 1
    assert r.tool == "solid.union" and r.data["alias"] == "solid.fuse"


def test_synonym_without_target_falls_back_to_hint():
    reg = ToolRegistry()
    r = reg.call("solid.fuse", {})
    assert not r.ok and "unknown tool" in r.error


def test_handler_exception_is_caught():
    reg = ToolRegistry()

    def boom(a):
        raise RuntimeError("kaboom")

    reg.register("x.y", boom)
    r = reg.call("x.y", {})
    assert not r.ok and "kaboom" in r.error


def test_groups_and_first_matching():
    reg = ToolRegistry()
    reg.register("solid.box", lambda a: ToolResult.success())
    reg.register("param.pad", lambda a: ToolResult.success())
    g = reg.groups()
    assert set(g) == {"solid", "param"}
    assert reg.first_matching("mesh.measure", "solid.box") == "solid.box"
    assert reg.first_matching("nope") is None


def test_manifest():
    reg = ToolRegistry()
    reg.register("solid.box", lambda a: ToolResult.success(), "make a box")
    m = reg.manifest()
    assert m[0]["name"] == "solid.box" and m[0]["group"] == "solid"
    assert m[0]["summary"] == "make a box"


def test_gui_state_mirrors_kernel_state_surface():
    """dao_engine.GuiState must expose the same bookkeeping attributes as the
    kernel State (mates included) or GUI-bridge ops like asm.dof crash with
    AttributeError."""
    import ast
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "freecad", "DAO", "dao_engine.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "GuiState")
    init = next(n for n in cls.body
                if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    attrs = {t.attr for stmt in ast.walk(init) if isinstance(stmt, ast.Assign)
             for t in stmt.targets
             if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
             and t.value.id == "self"}
    for required in ("shapes", "bodies", "params", "assembly",
                     "components", "joints", "mates", "_undo"):
        assert required in attrs, "GuiState.__init__ missing self.%s" % required


def test_gui_engine_registers_kernel_module_surface():
    """The GUI bridge engine (dao_engine._build_handlers) must register the
    same optional op modules as the headless kernel (fem/path/surface/arch/
    bop/code included), or the /toolspec surface silently loses whole groups."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "freecad", "DAO", "dao_engine.py"),
               encoding="utf-8").read()
    for mod in ("freecad_parametric", "freecad_assembly", "freecad_perceive",
                "freecad_advanced", "freecad_measure", "freecad_percept",
                "freecad_project", "freecad_resource", "freecad_fem",
                "freecad_path", "freecad_surface", "freecad_arch",
                "freecad_bop", "freecad_code",
                "freecad_reflect", "freecad_verify", "freecad_wire",
                "freecad_object"):
        assert '"%s"' % mod in src, "dao_engine missing module %s" % mod


def test_bridge_tool_keyerror_is_guided():
    """POST /tool must never leak a bare KeyError('name') for a missing
    documented argument; the server maps it to the kernel-style guidance."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "10-反笙_FreeCAD", "_fc_remote_server.py"),
               encoding="utf-8").read()
    assert "missing required argument" in src


def test_object_protocol_ops_registered():
    """The generic object protocol (property system / expressions / prefs /
    units) must be registered in the kernel backend and self-described in the
    tool catalog."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "cad_agent", "backends", "freecad_object.py"),
               encoding="utf-8").read()
    for op in ('"obj.list"', '"obj.get"', '"obj.set"', '"obj.add"',
               '"obj.delete"', '"obj.copy"', '"obj.expr"',
               '"pref.list"', '"pref.get"', '"pref.set"',
               '"units.parse"', '"units.convert"'):
        assert op in src, "freecad_object missing %s" % op
    sys.path.insert(0, root)
    from cad_agent import tool_catalog
    for op in ("obj.set", "obj.expr", "pref.set", "units.convert"):
        spec = tool_catalog.spec_for(op)
        assert spec["parameters"]["properties"], "no schema for %s" % op
    assert "obj" in tool_catalog.CATEGORIES


def test_sketch_protocol_and_mcp_bridge_proxy():
    """Wave-5: the direct Sketcher protocol must be registered, gui.select must
    drive the official selection, doc.import must exist, verify must fall back
    natively without OCP, and the MCP server must proxy the live bridge with
    sanitized tool names."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sk = open(os.path.join(root, "cad_agent", "backends", "freecad_sketch.py"),
              encoding="utf-8").read()
    for op in ('"sketch.create"', '"sketch.add"', '"sketch.constrain"',
               '"sketch.geometry"', '"sketch.constraints"', '"sketch.dof"',
               '"sketch.remove"'):
        assert op in sk, "freecad_sketch missing %s" % op
    per = open(os.path.join(root, "freecad", "DAO", "dao_perceive.py"),
               encoding="utf-8").read()
    assert '"gui.select"' in per
    objmod = open(os.path.join(root, "cad_agent", "backends",
                               "freecad_object.py"), encoding="utf-8").read()
    assert '"doc.import"' in objmod
    ver = open(os.path.join(root, "cad_agent", "backends",
                            "freecad_verify.py"), encoding="utf-8").read()
    assert "_native_audit" in ver and "ImportError" in ver
    sys.path.insert(0, root)
    from cad_agent import mcp_server
    assert mcp_server._mcp_name("solid.box") == "solid_box"
    assert hasattr(mcp_server, "BridgeProxy")


def test_engine_has_doc_lifecycle_and_command_dispatch():
    """The unified protocol needs official doc lifecycle + undo/redo on the
    engine and command enumeration/dispatch + workbench switching in gui.*."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    eng = open(os.path.join(root, "freecad", "DAO", "dao_engine.py"),
               encoding="utf-8").read()
    for op in ('"doc.new"', '"doc.open"', '"doc.close"', '"doc.list"',
               '"doc.undo"', '"doc.redo"'):
        assert op in eng, "dao_engine missing %s" % op
    per = open(os.path.join(root, "freecad", "DAO", "dao_perceive.py"),
               encoding="utf-8").read()
    for op in ('"gui.commands"', '"gui.command"', '"gui.workbench"'):
        assert op in per, "dao_perceive missing %s" % op


def test_wave6_appearance_camera_draw_export_expressions():
    """Wave-6: appearance/camera on the live GUI surface, true TechDraw
    dimensions + page export, generic doc.export, expression census, external
    sketch geometry, and ss.create honoring its requested name."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    per = open(os.path.join(root, "freecad", "DAO", "dao_perceive.py"),
               encoding="utf-8").read()
    assert '"gui.appearance"' in per and '"gui.camera"' in per
    adv = open(os.path.join(root, "cad_agent", "backends",
                            "freecad_advanced.py"), encoding="utf-8").read()
    assert '"draw.dimension"' in adv and '"draw.export"' in adv
    # ss.create must honor its requested name instead of a cached singleton
    assert "doc.getObject(name)" in adv
    objmod = open(os.path.join(root, "cad_agent", "backends",
                               "freecad_object.py"), encoding="utf-8").read()
    assert '"doc.export"' in objmod and '"obj.expressions"' in objmod
    sk = open(os.path.join(root, "cad_agent", "backends",
                           "freecad_sketch.py"), encoding="utf-8").read()
    assert '"sketch.external"' in sk and '"sketch.expression"' in sk
    # the expression parse guidance for unit-token collisions must exist
    assert "unit tokens" in sk
    sys.path.insert(0, root)
    from cad_agent import tool_catalog
    for op in ("gui.appearance", "gui.camera", "draw.dimension",
               "draw.export", "doc.export", "obj.expressions",
               "sketch.external", "sketch.expression"):
        spec = tool_catalog.spec_for(op)
        assert spec, "no catalog spec for %s" % op


def test_wave7_hole_draft_and_draft_annotations():
    """Wave-7: official PartDesign Hole + Draft (face taper) features and
    Draft-workbench text/dimension/clone annotations must be registered with
    catalog schemas."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    par = open(os.path.join(root, "cad_agent", "backends",
                            "freecad_parametric.py"), encoding="utf-8").read()
    assert '"param.hole"' in par and '"param.draft"' in par
    assert "PartDesign::Hole" in par and "PartDesign::Draft" in par
    sur = open(os.path.join(root, "cad_agent", "backends",
                            "freecad_surface.py"), encoding="utf-8").read()
    for op in ('"draft.text"', '"draft.dimension"', '"draft.clone"'):
        assert op in sur, "freecad_surface missing %s" % op
    sys.path.insert(0, root)
    from cad_agent import tool_catalog
    for op in ("param.hole", "param.draft", "draft.text",
               "draft.dimension", "draft.clone"):
        assert tool_catalog.spec_for(op), "no catalog spec for %s" % op
