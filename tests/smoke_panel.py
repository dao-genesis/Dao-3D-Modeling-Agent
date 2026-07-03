"""In-GUI AI IDE panel (the DAO dock) driven inside a real ``freecad`` process.

Boots the full GUI under the Qt offscreen platform with the ``freecad/DAO``
addon on the Mod path, mounts the dock panel, and pushes chat turns through
``DAOPanel._run`` exactly as a typing human would: build, boolean, measure.
This is the fusion regression that caught the matplotlib-in-GUI wedge: merely
*registering* the ``view.*`` group used to import pyplot into the GUI process,
after which ``Gui.updateGui()`` (called by the panel's view refresh) never
returned and the first chat turn hung forever.
"""
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DRIVER = r'''
import os
_f = open(os.environ["DAO_PANEL_OUT"], "a")


def P(*a):
    _f.write(" ".join(str(x) for x in a) + "\n")
    _f.flush()


import FreeCAD as App  # noqa: F401,E402
import FreeCADGui as Gui  # noqa: F401,E402
from PySide import QtCore  # noqa: E402

app = QtCore.QCoreApplication.instance()
for _ in range(200):
    app.processEvents(QtCore.QEventLoop.AllEvents, 10)
try:
    import sys
    sys.path.insert(0, os.path.join(os.environ["DAO_REPO"], "freecad", "DAO"))
    import dao_panel
    p = dao_panel.ensure_panel()
    assert p is not None, "panel did not mount"
    panel = p.widget()
    P("PANEL_MOUNTED", type(panel).__name__)
    for cmd in ("box 40x30x10 name plate", "cylinder r=6 h=40 name hole",
                "cut hole from plate", "measure plate"):
        panel._run(cmd)
        P("TURN_OK", cmd)
    txt = panel.log.toPlainText()
    assert "volume" in txt, txt[-400:]
    assert App.ActiveDocument is not None
    names = [o.Name for o in App.ActiveDocument.Objects]
    P("DOC_OBJECTS", ",".join(names))
    assert any("plate" in n for n in names), names
    # AI-IDE tabs: conversation / data / management
    assert panel.tabs.count() == 3, panel.tabs.count()
    panel._refresh_data()
    data = panel.data_view.toPlainText()
    assert "plate" in data, data[:400]
    P("DATA_TAB_OK")
    panel._refresh_mgmt()
    mgmt = panel.mgmt_view.toPlainText()
    assert "Agent API" in mgmt, mgmt[:400]
    P("MGMT_TAB_OK")
    # the world's model libraries are part of the in-GUI tool surface
    assert "resource.search" in panel.engine.handlers, \
        sorted(panel.engine.handlers)[:20]
    P("RESOURCE_OPS_OK")
    P("PANEL_SMOKE_PASS")
except Exception:
    import traceback
    P(traceback.format_exc())
    P("PANEL_SMOKE_FAIL")
os._exit(0)
'''


def _freecad_gui_exe():
    cmd = os.environ.get("FREECADCMD")
    if cmd:
        base = os.path.dirname(cmd)
        for name in ("freecad", "FreeCAD", "freecad.exe", "FreeCAD.exe"):
            cand = os.path.join(base, name)
            if os.path.exists(cand):
                return cand
    for cand in ("/usr/bin/freecad", "/usr/local/bin/freecad"):
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError("freecad (GUI binary) not found; set FREECADCMD")


def main():
    exe = _freecad_gui_exe()
    with tempfile.TemporaryDirectory() as td:
        driver = os.path.join(td, "panel_driver.py")
        out = os.path.join(td, "panel.out")
        with open(driver, "w", encoding="utf-8") as f:
            f.write(_DRIVER)
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env.setdefault("XDG_RUNTIME_DIR", "/tmp/dao-runtime")
        env["DAO_PANEL_OUT"] = out
        env["DAO_REPO"] = REPO
        env["PYTHONUTF8"] = "1"
        try:
            os.makedirs(env["XDG_RUNTIME_DIR"], mode=0o700, exist_ok=True)
        except Exception:
            pass
        subprocess.run([exe, driver], env=env, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(out, encoding="utf-8") as f:
            log = f.read()
    print(log.strip())
    assert "PANEL_MOUNTED" in log, log
    assert log.count("TURN_OK") == 4, log
    for marker in ("DATA_TAB_OK", "MGMT_TAB_OK", "RESOURCE_OPS_OK",
                   "PANEL_SMOKE_PASS"):
        assert marker in log, log
    print("PANEL SMOKE OK")


if __name__ == "__main__":
    sys.exit(main())
