#!/usr/bin/env python3
"""直接运行FreeCAD backend self_test via launcher pattern"""
import json, subprocess, sys, time, tempfile, shutil
from pathlib import Path

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), Path(__file__).resolve().parent.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

backend_src = _dao_paths.REVERSE / "freecad_backend.py"   # 10-反笙_FreeCAD
CMD = r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe"

td = Path(tempfile.mkdtemp(prefix="dao_selftest_"))
try:
    shutil.copy2(str(backend_src), str(td / "freecad_backend.py"))
    cf = td / "cmd.json"
    rf = td / "result.json"
    cf.write_text(json.dumps({"ops": [{"op": "self_test"}]}, ensure_ascii=True), encoding="utf-8")

    lf = td / "launcher.py"
    lf.write_text(
        "import sys,json\nfrom pathlib import Path\n"
        f"sys.path.insert(0,r'{td}')\n"
        "from freecad_backend import run_ops\n"
        f"ops=json.loads(Path(r'{cf}').read_text(encoding='utf-8')).get('ops',[])\n"
        "r=run_ops(ops)\n"
        f"Path(r'{rf}').write_text(json.dumps(r,indent=2,ensure_ascii=False,default=str),encoding='utf-8')\n",
        encoding="utf-8"
    )

    t0 = time.time()
    r = subprocess.run(
        [CMD, str(lf)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=120, creationflags=0x08000000
    )
    elapsed = round(time.time() - t0, 2)

    if rf.exists():
        data = json.loads(rf.read_text(encoding="utf-8"))
    else:
        data = {"error": "no result file", "stderr": r.stderr.decode("utf-8", errors="replace")[:500]}

    tests = data.get("tests", [])
    passed = data.get("pass", 0)
    failed = data.get("fail", 0)
    warns = data.get("warn", 0)
    print(f"Time: {elapsed}s | pass={passed} fail={failed} warn={warns}")
    print(f"SVG: {data.get('techdraw_svg_exists')} ({data.get('techdraw_svg_bytes',0)} bytes)")
    for t in tests:
        s = "OK" if t.get("ok") else "FAIL"
        w = t.get("warn", [])
        line = f"  [{s}] {t.get('name','?')}"
        for wi in w:
            line += f"\n       WARN: {str(wi)[:80]}"
        print(line)
    if "error" in data:
        print("ERROR:", data["error"])
finally:
    shutil.rmtree(str(td), ignore_errors=True)
