#!/usr/bin/env python3
"""通过freecadcmd运行 _test_freecad_ops.py (launcher pattern，绕过中文路径问题)"""
import subprocess, shutil, sys, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in SCRIPT_DIR.parents if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

CMD = r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe"

import tempfile
td = Path(tempfile.mkdtemp(prefix="dao_ops_test_"))
try:
    shutil.copy2(str(_dao_paths.REVERSE / "freecad_backend.py"), str(td / "freecad_backend.py"))
    shutil.copy2(str(SCRIPT_DIR / "_test_freecad_ops.py"), str(td / "_test_ops.py"))

    # Create launcher that explicitly calls main() (FreeCAD may not set __name__=="__main__")
    launcher = td / "launcher_ops.py"
    launcher.write_text(
        f"import sys\nsys.path.insert(0,r'{td}')\n"
        "import _test_ops as _t\n_t.main()\n",
        encoding="utf-8"
    )

    t0 = time.time()
    r = subprocess.run(
        [CMD, str(launcher)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=180, creationflags=0x08000000
    )
    elapsed = round(time.time() - t0, 2)

    stdout = r.stdout.decode("utf-8", errors="replace")
    stderr = r.stderr.decode("utf-8", errors="replace")
    print(stdout)
    if r.returncode != 0 and stderr:
        print("STDERR:", stderr[:500])
    print(f"[exit={r.returncode} elapsed={elapsed}s]")
finally:
    shutil.rmtree(str(td), ignore_errors=True)
