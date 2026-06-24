#!/usr/bin/env python3
"""Test all possible STEP import methods in FreeCAD headless."""
import json, sys, os, subprocess, tempfile, shutil
from pathlib import Path

step_path = os.path.join(os.environ["TEMP"], "e2e_test.step").replace("\\", "/")
brep_out = os.path.join(os.environ["TEMP"], "_step_method_test.brep").replace("\\", "/")
print(f"Testing STEP import methods for: {step_path}")

# Script that tries multiple methods
script = f'''import sys, json, traceback
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

methods_tried = []

# Method 1: Part.read()
try:
    import Part
    shape = Part.read("{step_path}")
    if shape and not shape.isNull() and shape.Volume > 0:
        shape.exportBrep("{brep_out}")
        methods_tried.append({{"method": "Part.read", "ok": True, "vol": round(shape.Volume, 4)}})
    else:
        methods_tried.append({{"method": "Part.read", "ok": False, "null": shape.isNull() if shape else True}})
except Exception as e:
    methods_tried.append({{"method": "Part.read", "ok": False, "error": str(e)[:200]}})

# Method 2: Part.Shape.importBrep after doc insert
try:
    import FreeCAD as App
    import Part
    doc = App.newDocument("_imp2")
    Part.insert("{step_path}", doc.Name)
    doc.recompute()
    objs = [o for o in doc.Objects if hasattr(o, "Shape")]
    shapes_info = []
    for o in objs:
        si = {{"name": o.Name, "null": o.Shape.isNull(), "type": o.Shape.ShapeType}}
        if not o.Shape.isNull():
            si["vol"] = round(o.Shape.Volume, 4)
        shapes_info.append(si)
    methods_tried.append({{"method": "Part.insert+doc", "ok": len(shapes_info) > 0, 
                           "objects": len(doc.Objects), "shapes": shapes_info[:5]}})
    App.closeDocument("_imp2")
except Exception as e:
    methods_tried.append({{"method": "Part.insert+doc", "ok": False, "error": str(e)[:200]}})

# Method 3: Import module
try:
    import FreeCAD as App
    import Import
    doc = App.newDocument("_imp3")
    Import.insert("{step_path}", doc.Name)
    doc.recompute()
    shapes_info = []
    for o in doc.Objects:
        if hasattr(o, "Shape") and not o.Shape.isNull():
            shapes_info.append({{"name": o.Name, "vol": round(o.Shape.Volume, 4)}})
    methods_tried.append({{"method": "Import.insert", "ok": len(shapes_info) > 0, "shapes": shapes_info[:5]}})
    App.closeDocument("_imp3")
except Exception as e:
    methods_tried.append({{"method": "Import.insert", "ok": False, "error": str(e)[:200]}})

# Method 4: importOCC module
try:
    import FreeCAD as App
    import importOCC
    doc = App.newDocument("_imp4")
    importOCC.insert("{step_path}", doc.Name)
    doc.recompute()
    shapes_info = []
    for o in doc.Objects:
        if hasattr(o, "Shape") and not o.Shape.isNull():
            shapes_info.append({{"name": o.Name, "vol": round(o.Shape.Volume, 4)}})
    methods_tried.append({{"method": "importOCC.insert", "ok": len(shapes_info) > 0, "shapes": shapes_info[:5]}})
    App.closeDocument("_imp4")
except Exception as e:
    methods_tried.append({{"method": "importOCC.insert", "ok": False, "error": str(e)[:200]}})

print("METHODS_RESULT:" + json.dumps(methods_tried, default=str))
'''

td = Path(tempfile.mkdtemp(prefix="dao_step_m_"))
sf = td / "step_methods.py"
sf.write_text(script, encoding="utf-8")

try:
    r = subprocess.run(
        [r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe", str(sf)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30, creationflags=0x08000000
    )
    out = r.stdout.decode("utf-8", errors="replace")
    for line in out.split("\n"):
        if line.startswith("METHODS_RESULT:"):
            results = json.loads(line[15:])
            for m in results:
                status = "OK" if m.get("ok") else "FAIL"
                print(f"  [{status}] {m['method']}: {json.dumps({k:v for k,v in m.items() if k not in ('method',)}, default=str)[:200]}")
            break
    else:
        print("No METHODS_RESULT found")
        print("STDOUT:", out[-1000:])
    err = r.stderr.decode("utf-8", errors="replace").strip()
    if err:
        print(f"STDERR: {err[-300:]}")
except subprocess.TimeoutExpired:
    print("TIMEOUT! One of the methods hung.")
finally:
    shutil.rmtree(str(td), ignore_errors=True)
