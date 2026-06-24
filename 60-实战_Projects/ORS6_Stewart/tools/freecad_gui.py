"""ORS6_Stewart · FreeCAD GUI postprocess (color persistence + screenshots).

Run with FreeCAD 1.0 GUI mode:
    "D:\\path\\to\\freecad.exe" ORS6_Stewart/tools/freecad_gui.py

For each pose FCStd in output/:
  - open document
  - resolve color per object name (Arm_<servo> -> Arm color, Rod_<servo> -> silver, etc.)
  - set ViewObject.ShapeColor + Visibility=True (persisted into FCStd)
  - viewIsometric + fitAll
  - saveImage 1200x900 PNG to output/screenshots/
  - doc.save() (persist colors)
  - close

Then quit GUI cleanly via QTimer.

CRITICAL design (same as freecad_build.py):
  * Pure ASCII source.
  * Never reference sys.argv / sys.executable.
  * Bootstrap from THIS_FILE location (will be in mirrored ASCII path).
"""
import os
import sys
import time
import traceback

THIS_FILE = os.path.abspath(__file__)
TOOLS = os.path.dirname(THIS_FILE)
PROJECT = os.path.dirname(TOOLS)
PROJECTS_ROOT = os.path.dirname(PROJECT)
if PROJECTS_ROOT not in sys.path:
    sys.path.insert(0, PROJECTS_ROOT)

OUT_DIR = os.environ.get("ORS6_FC_OUTPUT_DIR") or os.path.join(PROJECT, "output")
SCREENS = os.path.join(OUT_DIR, "screenshots")
LOG = os.path.join(OUT_DIR, "_freecad_gui.log")

os.makedirs(SCREENS, exist_ok=True)


def w(msg=""):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


# Wipe log
with open(LOG, "w", encoding="utf-8") as f:
    f.write("== FreeCAD GUI postprocess ==\n")
    f.write(f"timestamp = {time.strftime('%Y-%m-%d %H:%M:%S')}\n")


# ── A. Imports (FreeCAD GUI must be available) ──
try:
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide2 import QtCore, QtWidgets
    w(f"[A] FreeCAD={'.'.join(str(x) for x in App.Version()[0:3])}")
    w(f"[A] GUI app: {QtWidgets.QApplication.instance() is not None}")
except Exception as e:
    w(f"[A] FAIL: {e!r}")
    w(traceback.format_exc())
    raise


# ── B. Import ORS6_Stewart parts registry for color lookup ──
try:
    from ORS6_Stewart.parts import PARTS
    w(f"[B] PARTS loaded: {len(PARTS)} entries")
except Exception as e:
    w(f"[B] FAIL: {e!r}")
    w(traceback.format_exc())
    raise


def color_rgb(hex_int):
    return (((hex_int >> 16) & 0xFF) / 255.0,
            ((hex_int >> 8) & 0xFF) / 255.0,
            (hex_int & 0xFF) / 255.0)


def resolve_color(obj_name):
    """Resolve color for a doc object name.

    Direct match: PARTS[name].
    Instance match: 'Arm_LowerLeft' -> PARTS['Arm'], 'L_Pitcher' -> PARTS['L_Pitcher'].
    Rod: 'Rod_<servo>' -> silver 0xc0c0c0.
    """
    if obj_name in PARTS:
        return PARTS[obj_name][2]
    if obj_name.startswith("Arm_"):
        return PARTS["Arm"][2]
    if obj_name.startswith("Rod_"):
        return 0xc0c0c0
    # Try prefix match (e.g. "Receiver" with possible suffix)
    for k in PARTS:
        if obj_name == k or obj_name.startswith(k + "_") or obj_name.startswith(k + "."):
            return PARTS[k][2]
    return None


POSES = ["home", "forward", "side_right", "pitch_up", "roll_left"]
results = []
t_total = time.time()

for pose in POSES:
    fc_path = os.path.join(OUT_DIR, "ORS6_" + pose + ".FCStd")
    if not os.path.exists(fc_path):
        w("\n--- " + pose + ": MISSING " + fc_path + " ---")
        results.append({"pose": pose, "ok": False, "error": "fcstd_missing"})
        continue

    w("\n--- " + pose + " ---")
    t1 = time.time()
    try:
        doc = App.openDocument(fc_path)
        QtCore.QCoreApplication.processEvents()

        colored = 0
        skipped = 0
        for obj in doc.Objects:
            color_hex = resolve_color(obj.Name)
            if color_hex is None:
                skipped += 1
                continue
            vp = obj.ViewObject
            if vp is None:
                skipped += 1
                continue
            try:
                rgb = color_rgb(color_hex)
                if hasattr(vp, "ShapeColor"):
                    # Mesh: ShapeColor 4-tuple (r,g,b,transparency); Part: 3-tuple
                    if obj.TypeId.startswith("Mesh"):
                        vp.ShapeColor = rgb + (0.0,)
                    else:
                        vp.ShapeColor = rgb
                vp.Visibility = True
                if obj.Name == "Receiver" and hasattr(vp, "Transparency"):
                    vp.Transparency = 30
                colored += 1
            except Exception as ec:
                w("  color fail " + obj.Name + ": " + repr(ec))

        # Camera + render
        Gui.activeDocument().ActiveView.viewIsometric()
        Gui.activeDocument().ActiveView.fitAll()
        QtCore.QCoreApplication.processEvents()

        png_path = os.path.join(SCREENS, "ORS6_" + pose + ".png")
        Gui.activeDocument().ActiveView.saveImage(png_path, 1200, 900, "Current")
        png_size = os.path.getsize(png_path) if os.path.exists(png_path) else 0

        # Save FCStd to persist colors
        doc.save()
        new_fcstd_size = os.path.getsize(fc_path)

        dt = time.time() - t1
        w("  OK colored={} skipped={} png={}B dt={:.2f}s".format(
            colored, skipped, png_size, dt))
        results.append({
            "pose": pose, "ok": True,
            "colored": colored, "skipped": skipped,
            "png_path": png_path, "png_size": png_size,
            "fcstd_size_after": new_fcstd_size,
            "duration_s": round(dt, 2),
        })

        App.closeDocument(doc.Name)
        QtCore.QCoreApplication.processEvents()
    except Exception as e:
        w("  FAIL: " + repr(e))
        w(traceback.format_exc())
        results.append({"pose": pose, "ok": False, "error": str(e)})
        try:
            App.closeDocument(doc.Name)
        except Exception:
            pass


dt_total = time.time() - t_total
ok = sum(1 for r in results if r.get("ok"))
w("\n" + "=" * 60)
w("DONE: {}/{} OK · total {:.2f}s".format(ok, len(results), dt_total))

# Save summary JSON
try:
    import json
    summary = {
        "engine": "freecad_gui",
        "freecad_version": ".".join(str(x) for x in App.Version()[0:3]),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ok_count": ok,
        "total": len(results),
        "duration_s": round(dt_total, 2),
        "screenshots_dir": SCREENS,
        "results": results,
    }
    sp = os.path.join(OUT_DIR, "_freecad_gui_summary.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    w("summary -> " + os.path.basename(sp))
except Exception as e:
    w("summary ERR: " + repr(e))


# Quit FreeCAD GUI cleanly (give Qt event loop a beat to flush)
def _quit():
    try:
        for d in list(App.listDocuments()):
            try:
                App.closeDocument(d)
            except Exception:
                pass
    except Exception:
        pass
    QtWidgets.QApplication.instance().quit()


QtCore.QTimer.singleShot(800, _quit)
