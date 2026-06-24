#!/usr/bin/env python3
"""Test STEP import via subprocess script method."""
import json, sys, os, subprocess, tempfile, shutil
from pathlib import Path

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), Path(__file__).resolve().parent.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

step_path = os.path.join(os.environ["TEMP"], "e2e_test.step").replace("\\", "/")
brep_out = os.path.join(os.environ["TEMP"], "_step_test_import.brep").replace("\\", "/")
print(f"STEP input: {step_path} (exists={Path(step_path).exists()}, size={Path(step_path).stat().st_size})")

# Generate the import script
script = f'''import sys, json
import FreeCAD as App
import Part
result = {{"ok": False}}
try:
    doc = App.newDocument("_imp")
    Part.insert("{step_path}", doc.Name)
    doc.recompute()
    shapes = [o.Shape.copy() for o in doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()]
    if shapes:
        compound = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
        compound.exportBrep("{brep_out}")
        result = {{"ok": True, "shapes": len(shapes), "vol": round(compound.Volume, 4)}}
    else:
        result["error"] = "No shapes found"
    App.closeDocument("_imp")
except Exception as e:
    result["error"] = str(e)
print("IMPORT_RESULT:" + json.dumps(result))
'''

td = Path(tempfile.mkdtemp(prefix="dao_step_"))
sf = td / "step_import.py"
sf.write_text(script, encoding="utf-8")
print(f"Script: {sf}")

try:
    r = subprocess.run(
        [r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe", str(sf)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30, creationflags=0x08000000
    )
    print(f"RC: {r.returncode}")
    out = r.stdout.decode("utf-8", errors="replace")
    print(f"STDOUT:\n{out[-1500:]}")
    err = r.stderr.decode("utf-8", errors="replace")
    if err.strip():
        print(f"STDERR:\n{err[-500:]}")

    # Check output
    for line in out.split("\n"):
        if line.startswith("IMPORT_RESULT:"):
            result = json.loads(line[14:])
            print(f"\nParsed result: {json.dumps(result, indent=2)}")
            break
    else:
        print("\nNo IMPORT_RESULT line found in output")

    # Check brep file
    bp = Path(brep_out)
    if bp.exists():
        print(f"BREP output: {bp} ({bp.stat().st_size} bytes)")
    else:
        print(f"BREP output: NOT CREATED")
except subprocess.TimeoutExpired:
    print("TIMEOUT! (STEP import hung as expected)")
finally:
    shutil.rmtree(str(td), ignore_errors=True)
