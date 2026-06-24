#!/usr/bin/env python3
"""
ModelHub — 3D建模Agent中枢 v3.0
统一整合: OpenSCAD + CadQuery + build123d + trimesh + ORS6 + Quest3 VR

端口: :8872
Dashboard: http://localhost:8872/
API:
  GET  /api/health          健康状态
  GET  /api/catalog         项目目录
  GET  /api/tools           工具链状态
  GET  /api/projects        项目列表
  GET  /api/project/{name}  单项目详情
  POST /api/render          OpenSCAD渲染
  POST /api/generate        CadQuery/build123d代码生成
  POST /api/analyze         trimesh分析
  POST /api/manufacture     制造性分析
  GET  /api/stl/{path}      STL文件服务
  GET  /api/ors6/parts      ORS6零件列表
  GET  /api/ors6/health     ORS6健康
  GET  /api/viewer?stl=URL  VR查看器
  GET  /sense               全景感知摘要

Usage:
  python model_hub.py [port]
  python model_hub.py serve [port]
"""
import os, sys, json, subprocess, time, threading, http.server, socketserver, urllib.parse, mimetypes
import queue as _queue
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
ROOT_DIR = _DAO_ROOT
# ═══════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────
# Event Bus — 阳(Agent)→阴(User) real-time bridge (SSE)
# ─────────────────────────────────────────────────────
_event_subscribers = []  # list of queue.Queue
_event_lock = threading.Lock()
_event_history = []  # last 50 events for late joiners

def _emit_event(event_type, data):
    """Broadcast event to all SSE subscribers."""
    event = {"type": event_type, "data": data, "ts": datetime.now().isoformat()}
    with _event_lock:
        _event_history.append(event)
        if len(_event_history) > 50:
            _event_history.pop(0)
        dead = []
        for i, q in enumerate(_event_subscribers):
            try:
                q.put_nowait(event)
            except Exception:
                dead.append(i)
        for i in reversed(dead):
            _event_subscribers.pop(i)

PORT = int(sys.argv[-1]) if len(sys.argv) > 1 and sys.argv[-1].isdigit() else 8872

ORS6_DIR = ROOT_DIR.parent / "ORS6-VAM饮料摇匀器"   # 外部姐妹项目
PROJECTS_DIR = _dao_paths.PROJECTS                    # 60-实战_Projects
DEMO_DIR = _dao_paths.DEMO                            # 50-演示_Demo

# ─────────────────────────────────────────────────────
# Tool Detection
# ─────────────────────────────────────────────────────
OPENSCAD_SEARCH = [
    r"D:\openscad\openscad.com", r"D:\openscad\openscad.exe",
    r"C:\Program Files\OpenSCAD\openscad.exe",
    r"C:\Program Files (x86)\OpenSCAD\openscad.exe",
]
FREECAD_SEARCH = [
    r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe",
    r"D:\安装的软件\FreeCAD 0.21\bin\FreeCADCmd.exe",
    r"C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe",
    r"C:\Program Files\FreeCAD\bin\FreeCADCmd.exe",
    r"D:\FreeCAD\bin\FreeCADCmd.exe",
]

def _find(paths):
    for p in paths:
        if Path(p).exists(): return p
    return None

def detect_tools():
    tools = {}
    # OpenSCAD
    scad = _find(OPENSCAD_SEARCH)
    if not scad:
        import shutil; scad = shutil.which("openscad") or shutil.which("openscad.com")
    tools["openscad"] = {"path": scad, "ok": bool(scad)}
    # FreeCAD
    fc = _find(FREECAD_SEARCH)
    tools["freecad"] = {"path": fc, "ok": bool(fc)}
    # Python packages
    for pkg in ["trimesh", "cadquery", "build123d", "numpy", "PIL"]:
        try:
            mod = __import__("PIL" if pkg == "PIL" else pkg)
            ver = getattr(mod, "__version__", "?")
            tools[pkg] = {"ok": True, "version": ver}
        except ImportError:
            tools[pkg] = {"ok": False}
    return tools

TOOLS = detect_tools()

# ─────────────────────────────────────────────────────
# ORS6 Integration
# ─────────────────────────────────────────────────────
_ors6_parts = None
_ors6_ik = None

def _load_ors6():
    global _ors6_parts, _ors6_ik
    if _ors6_parts is not None:
        return True
    try:
        if str(ORS6_DIR) not in sys.path:
            sys.path.insert(0, str(ORS6_DIR))
        from sr6_tools import PARTS, SR6
        _ors6_parts = PARTS
        _ors6_ik = SR6
        return True
    except Exception:
        return False

# ─────────────────────────────────────────────────────
# Project Catalog
# ─────────────────────────────────────────────────────
def scan_projects():
    projects = []
    for d in sorted(PROJECTS_DIR.glob("*")):
        if not d.is_dir() or d.name.startswith("."): continue
        stls = list(d.glob("output/*.stl")) + list(d.glob("**/*.stl"))
        scads = list(d.glob("**/*.scad"))
        log = d / "iteration_log.json"
        iters = 0
        if log.exists():
            try:
                iters = len(json.loads(log.read_text(encoding="utf-8")).get("iterations", []))
            except Exception: pass
        projects.append({
            "name": d.name, "path": str(d),
            "stl_count": len(stls), "scad_count": len(scads),
            "iterations": iters,
            "has_report": (d / "report.md").exists(),
            "stls": [str(s.relative_to(ROOT_DIR)) for s in stls[:5]],
        })
    # Also scan demo
    demos = []
    for f in sorted(DEMO_DIR.glob("*.scad")):
        stl = f.with_suffix(".stl")
        demos.append({"name": f.stem, "scad": str(f.relative_to(ROOT_DIR)),
                      "stl": str(stl.relative_to(ROOT_DIR)) if stl.exists() else None})
    return {"projects": projects, "demos": demos, "total": len(projects)}

# ─────────────────────────────────────────────────────
# OpenSCAD Runner
# ─────────────────────────────────────────────────────
def _scad_lib_paths():
    """Discover OpenSCAD library paths (BOSL2, MCAD, etc.)."""
    libs_dir = _dao_paths.WORLD / "网络资源库" / "OpenSCAD_Libraries"
    paths = []
    for d in ("BOSL2", "MCAD", "NopSCADlib", "Round-Anything", "LibSCAD"):
        p = libs_dir / d
        if p.is_dir():
            paths.append(str(p.parent))
            break
    return paths

def run_openscad(scad_path, stl_out=None, fn=64, timeout=180, visible=False):
    scad = TOOLS["openscad"].get("path")
    if not scad:
        return {"ok": False, "error": "OpenSCAD not found"}
    scad_path = Path(scad_path)
    if not scad_path.exists():
        return {"ok": False, "error": f"SCAD not found: {scad_path}"}
    if stl_out is None:
        stl_out = scad_path.with_suffix(".stl")
    stl_out = Path(stl_out)
    stl_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [scad, "-o", str(stl_out.resolve()), "-D", f"$fn={fn}", str(scad_path.resolve())]
    env = os.environ.copy()
    lib_paths = _scad_lib_paths()
    if lib_paths:
        existing = env.get("OPENSCADPATH", "")
        env["OPENSCADPATH"] = os.pathsep.join(lib_paths + ([existing] if existing else []))
    _emit_event("render_start", {"engine": "openscad", "scad": str(scad_path), "fn": fn, "visible": visible})
    t0 = time.time()
    try:
        si = subprocess.STARTUPINFO()
        cflags = 0
        if not visible:
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            cflags = _NO_WINDOW
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           startupinfo=si, creationflags=cflags, env=env)
        ok = stl_out.exists() and stl_out.stat().st_size > 0
        stderr = (r.stderr or b"").decode("utf-8", errors="replace")
        try:
            stl_rel = str(stl_out.resolve().relative_to(ROOT_DIR)).replace("\\", "/")
        except ValueError:
            stl_rel = None
        result = {"ok": ok, "stl": str(stl_out), "stl_url": stl_rel, "seconds": round(time.time()-t0, 2),
                "size": stl_out.stat().st_size if ok else 0,
                "errors": [l for l in stderr.splitlines() if "ERROR" in l.upper()]}
        _emit_event("render_complete", result)
        return result
    except subprocess.TimeoutExpired:
        result = {"ok": False, "error": f"Timeout after {timeout}s"}
        _emit_event("render_complete", result)
        return result

def run_freecad(script_path, timeout=300, visible=False):
    """Execute FreeCAD headless script via FreeCADCmd."""
    fc = TOOLS.get("freecad", {}).get("path")
    if not fc:
        return {"ok": False, "error": "FreeCAD not installed"}
    script_path = Path(script_path)
    if not script_path.exists():
        return {"ok": False, "error": f"Script not found: {script_path}"}
    _emit_event("freecad_start", {"script": str(script_path), "visible": visible})
    t0 = time.time()
    import tempfile
    tmp_script = None
    run_path = str(script_path.resolve())
    try:
        run_path.encode("ascii")
    except UnicodeEncodeError:
        tmp_script = Path(tempfile.gettempdir()) / f"_fc_{script_path.name}"
        tmp_script.write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")
        run_path = str(tmp_script)
    try:
        si = subprocess.STARTUPINFO()
        cflags = 0
        if not visible:
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            cflags = _NO_WINDOW
        r = subprocess.run([fc, run_path], capture_output=True,
                           timeout=timeout, startupinfo=si, creationflags=cflags)
        stdout = (r.stdout or b"").decode("utf-8", errors="replace").strip()[:500]
        stderr = (r.stderr or b"").decode("utf-8", errors="replace").strip()[:500]
        result = {"ok": r.returncode == 0, "seconds": round(time.time()-t0, 2),
                "stdout": stdout, "stderr": stderr}
        _emit_event("freecad_complete", result)
        return result
    except subprocess.TimeoutExpired:
        result = {"ok": False, "error": f"Timeout after {timeout}s"}
        _emit_event("freecad_complete", result)
        return result
    except Exception as e:
        result = {"ok": False, "error": str(e)}
        _emit_event("freecad_complete", result)
        return result
    finally:
        if tmp_script and tmp_script.exists():
            tmp_script.unlink(missing_ok=True)

# ─────────────────────────────────────────────────────
# trimesh Analysis
# ─────────────────────────────────────────────────────
def analyze_stl(stl_path):
    try:
        import trimesh, numpy as np
        mesh = trimesh.load(str(stl_path))
        bounds = mesh.bounding_box.extents
        return {
            "ok": True,
            "vertices": len(mesh.vertices),
            "faces": len(mesh.faces),
            "volume_mm3": round(float(mesh.volume), 2),
            "surface_area_mm2": round(float(mesh.area), 2),
            "is_watertight": bool(mesh.is_watertight),
            "bounds_mm": [round(float(b), 2) for b in bounds],
            "centroid_mm": [round(float(c), 2) for c in mesh.centroid],
            "fill_ratio": round(float(mesh.volume) / float(np.prod(bounds)) if np.prod(bounds) > 0 else 0, 3),
        }
    except ImportError:
        return {"ok": False, "error": "trimesh not installed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ─────────────────────────────────────────────────────
# CadQuery / build123d Generator
# ─────────────────────────────────────────────────────
def run_python_cad(code, output_path, timeout=60, visible=False):
    """Execute CadQuery or build123d code that exports to output_path."""
    _emit_event("generate_start", {"output": str(output_path), "visible": visible})
    tmp = Path(output_path).parent / "_tmp_gen.py"
    tmp.write_text(code, encoding="utf-8")
    t0 = time.time()
    try:
        si = subprocess.STARTUPINFO()
        cflags = 0
        if not visible:
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            cflags = _NO_WINDOW
        r = subprocess.run([sys.executable, str(tmp)], capture_output=True, text=True,
                           timeout=timeout, cwd=str(ROOT_DIR),
                           startupinfo=si, creationflags=cflags)
        ok = Path(output_path).exists()
        try:
            out_rel = str(Path(output_path).resolve().relative_to(ROOT_DIR)).replace("\\", "/")
        except ValueError:
            out_rel = None
        result = {"ok": ok, "output": str(output_path), "output_url": out_rel, "seconds": round(time.time()-t0, 2),
                "stdout": r.stdout[:500], "stderr": r.stderr[:500] if not ok else ""}
        _emit_event("generate_complete", result)
        return result
    except subprocess.TimeoutExpired:
        result = {"ok": False, "error": f"Timeout after {timeout}s"}
        _emit_event("generate_complete", result)
        return result
    finally:
        if tmp.exists(): tmp.unlink()

# ─────────────────────────────────────────────────────
# Quest3 ADB Integration
# ─────────────────────────────────────────────────────
QUEST3_SN  = os.environ.get("QUEST_SN",  "2G0YC5ZG8L08Z7")
QUEST3_IP  = os.environ.get("QUEST_IP",  "192.168.31.136")
ADB_PATH   = os.environ.get("ADB_PATH",  r"D:\platform-tools\adb.exe")
_NO_WINDOW = 0x08000000

def _adb(args, timeout=10):
    """Run ADB command, return (ok, stdout, stderr)."""
    adb = ADB_PATH if Path(ADB_PATH).exists() else "adb"
    cmd = [adb, "-s", QUEST3_SN] + args
    try:
        import subprocess as _sp
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        r = _sp.run(cmd, capture_output=True, text=True, timeout=timeout,
                    startupinfo=si, creationflags=_NO_WINDOW)
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return False, "", "ADB not found at " + ADB_PATH
    except Exception as e:
        return False, "", str(e)

def quest3_status():
    """Get Quest3 connection status."""
    ok, out, err = _adb(["get-state"])
    if ok and "device" in out:
        ok2, bat, _ = _adb(["shell", "dumpsys battery | grep level"])
        battery = bat.strip() if ok2 else "?"
        return {"connected": True, "state": out, "battery": battery, "sn": QUEST3_SN, "ip": QUEST3_IP}
    return {"connected": False, "error": err or "device not found", "sn": QUEST3_SN}

def quest3_open_url(url):
    """Open URL in Quest3 OculusBrowser via ADB."""
    ok, out, err = _adb([
        "shell", "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", url,
        "-n", "com.oculus.browser/.OculusBrowserViewIntentHandler"
    ])
    return {"ok": ok, "url": url, "stdout": out, "stderr": err}

def quest3_open_3d_viewer(stl_url=None):
    """Open the VR 3D viewer on Quest3. Must be HTTPS or accessible IP."""
    pc_ip = "192.168.31.141"  # Desktop IP
    viewer_url = f"http://{pc_ip}:{PORT}/viewer"
    if stl_url:
        viewer_url += "?stl=" + urllib.parse.quote(stl_url, safe=":/")
    return quest3_open_url(viewer_url)

# ─────────────────────────────────────────────────────
# Sense — 全景摘要
# ─────────────────────────────────────────────────────
def sense():
    cat = scan_projects()
    tool_status = {k: ("✅" if v.get("ok") else "❌") for k, v in TOOLS.items()}
    ors6_ok = _load_ors6()
    return {
        "timestamp": datetime.now().isoformat(),
        "port": PORT,
        "tools": tool_status,
        "projects": cat["total"],
        "demos": len(cat["demos"]),
        "ors6_connected": ors6_ok,
        "ors6_parts": len(_ors6_parts) if _ors6_parts else 0,
        "grade": "S" if all(v.get("ok") for k, v in TOOLS.items() if k in ["openscad","trimesh","cadquery","build123d"]) else "A",
    }

# ─────────────────────────────────────────────────────
# Dashboard HTML
# ─────────────────────────────────────────────────────
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ModelHub — 3D建模Agent中枢</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;display:flex;flex-direction:column;min-height:100vh}
header{background:linear-gradient(135deg,#1f2937,#111827);padding:16px 24px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:16px}
h1{font-size:20px;font-weight:700;color:#58a6ff}
.badge{background:#21262d;border:1px solid #30363d;border-radius:6px;padding:2px 10px;font-size:12px;color:#8b949e}
nav{display:flex;gap:4px;padding:12px 24px;background:#161b22;border-bottom:1px solid #21262d;overflow-x:auto}
.tab{padding:6px 16px;border-radius:6px;cursor:pointer;font-size:13px;white-space:nowrap;color:#8b949e;transition:all .2s}
.tab.active,.tab:hover{background:#21262d;color:#e6edf3}
.tab.active{color:#58a6ff;border:1px solid #30363d}
main{flex:1;padding:24px;max-width:1400px;width:100%;margin:0 auto}
.panel{display:none}.panel.active{display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-bottom:24px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px}
.card h3{font-size:13px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px}
.stat{font-size:28px;font-weight:700;color:#58a6ff}
.tool-row{display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid #21262d}
.tool-row:last-child{border:none}
.ok{color:#3fb950}.fail{color:#f85149}
.project-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;cursor:pointer;transition:all .2s}
.project-card:hover{border-color:#58a6ff;background:#1c2333}
.btn{background:#238636;color:#fff;border:none;border-radius:6px;padding:8px 16px;cursor:pointer;font-size:13px;margin:4px}
.btn:hover{background:#2ea043}.btn.secondary{background:#21262d;border:1px solid #30363d}
.btn.secondary:hover{background:#30363d}.btn.danger{background:#da3633}.btn.danger:hover{background:#f85149}
textarea{width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;border-radius:6px;padding:12px;font-family:monospace;font-size:13px;resize:vertical;min-height:160px}
input[type=text]{width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;border-radius:6px;padding:8px 12px;font-size:13px;margin-bottom:8px}
.result-box{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;font-family:monospace;font-size:12px;white-space:pre-wrap;max-height:400px;overflow-y:auto;margin-top:8px}
.section-title{font-size:16px;font-weight:600;margin:24px 0 12px;color:#e6edf3;border-bottom:1px solid #30363d;padding-bottom:8px}
.tag{display:inline-block;background:#21262d;border-radius:4px;padding:2px 8px;font-size:11px;margin:2px;color:#8b949e}
.vr-btn{background:linear-gradient(135deg,#7c3aed,#4f46e5);color:#fff;border:none;border-radius:6px;padding:10px 20px;cursor:pointer;font-size:14px;font-weight:600}
.vr-btn:hover{background:linear-gradient(135deg,#8b5cf6,#6366f1)}
#toast{position:fixed;bottom:24px;right:24px;background:#238636;color:#fff;padding:12px 20px;border-radius:8px;display:none;z-index:999}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.live-dot{width:8px;height:8px;border-radius:50%;background:#3fb950;display:inline-block;animation:pulse 2s infinite;margin-right:6px}
.event-item{padding:4px 0;border-bottom:1px solid #21262d;font-size:12px;font-family:monospace}
.cb-visible{accent-color:#58a6ff;margin-right:6px}
</style>
</head>
<body>
<header>
  <div>
    <h1>🧊 ModelHub</h1>
    <div style="font-size:12px;color:#8b949e;margin-top:4px">3D建模Agent中枢 · 7引擎 · 5大能力 · Hausdorff验证 · 万物可造</div>
  </div>
  <span class="badge" id="grade-badge">Grade ?</span>
  <span class="badge" style="margin-left:auto">:8872</span>
</header>
<nav>
  <div class="tab active" onclick="show('overview')">☰ 全景</div>
  <div class="tab" onclick="show('projects')">📁 项目</div>
  <div class="tab" onclick="show('render')">🔨 渲染</div>
  <div class="tab" onclick="show('generate')">⚗️ 生成</div>
  <div class="tab" onclick="show('analyze')">🔬 分析</div>
  <div class="tab" onclick="show('vr')">🥽 VR查看</div>
  <div class="tab" onclick="show('resources')">📦 资源</div>
  <div class="tab" onclick="show('examples')">💡 示例</div>
  <div class="tab" onclick="show('ors6')">🤖 ORS6</div>
  <div class="tab" onclick="show('templates')">📐 模板</div>
  <div class="tab" onclick="show('tools')">🛠️ 工具链</div>
  <div class="tab" onclick="show('fcremote')">🔧 FC Remote</div>
  <div class="tab" onclick="show('forge')">⚒️ 锻造</div>
  <div class="tab" onclick="show('live')" id="tab-live" style="color:#3fb950"><span class="live-dot"></span>实时</div>
</nav>
<main>

<!-- Overview -->
<div class="panel active" id="panel-overview">
  <div class="grid" id="stat-cards"></div>
  <div class="section-title">工具链状态</div>
  <div class="card" id="tools-overview"></div>
  <div class="section-title">快捷操作</div>
  <button class="btn" onclick="show('render')">🔨 渲染SCAD</button>
  <button class="btn" onclick="show('generate')">⚗️ 生成模型</button>
  <button class="btn" onclick="show('vr')">🥽 VR查看</button>
  <button class="btn secondary" onclick="window.open('http://localhost:8871','_blank')">📺 ORS6 Studio</button>
</div>

<!-- Projects -->
<div class="panel" id="panel-projects">
  <div class="section-title">项目目录</div>
  <div id="projects-grid" class="grid"></div>
  <div class="section-title">Demo 模型</div>
  <div id="demos-grid" class="grid"></div>
</div>

<!-- Render -->
<div class="panel" id="panel-render">
  <div class="section-title">OpenSCAD 渲染</div>
  <div class="card">
    <div style="margin-bottom:8px;font-size:13px;color:#8b949e">SCAD 文件路径（绝对路径或相对路径）</div>
    <input type="text" id="render-scad" placeholder="demo/coffee_mug.scad">
    <input type="text" id="render-stl" placeholder="输出STL路径（可选，默认同名.stl）">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <span style="font-size:13px;color:#8b949e">$fn=</span>
      <input type="text" id="render-fn" value="64" style="width:80px">
    </div>
    <label style="display:flex;align-items:center;font-size:12px;color:#8b949e;margin-bottom:8px;cursor:pointer"><input type="checkbox" id="render-visible" class="cb-visible">可见模式（显示OpenSCAD窗口）</label>
    <button class="btn" onclick="doRender()">🔨 渲染</button>
    <div class="result-box" id="render-result">等待渲染...</div>
  </div>
</div>

<!-- Generate -->
<div class="panel" id="panel-generate">
  <div class="section-title">CadQuery / build123d 代码生成</div>
  <div class="card">
    <div style="margin-bottom:8px;font-size:13px;color:#8b949e">Python CAD代码（CadQuery 或 build123d）</div>
    <textarea id="gen-code" placeholder="import cadquery as cq
# 创建一个简单的盒子
result = cq.Workplane('XY').box(20, 20, 10)
result.val().exportStl('output/box.stl')"></textarea>
    <input type="text" id="gen-output" placeholder="输出文件路径（.stl 或 .step）" style="margin-top:8px">
    <label style="display:flex;align-items:center;font-size:12px;color:#8b949e;margin-bottom:8px;cursor:pointer"><input type="checkbox" id="gen-visible" class="cb-visible">可见模式（显示Python窗口）</label>
    <button class="btn" onclick="doGenerate()">⚗️ 执行</button>
    <div class="result-box" id="gen-result">等待执行...</div>
  </div>
  <div class="section-title">快速模板</div>
  <button class="btn secondary" onclick="loadTemplate('box')">📦 CadQuery Box</button>
  <button class="btn secondary" onclick="loadTemplate('cylinder')">🔵 CadQuery Cylinder</button>
  <button class="btn secondary" onclick="loadTemplate('build123d_box')">🧱 build123d Box</button>
  <button class="btn secondary" onclick="loadTemplate('esp32_mount')">💡 ESP32支架</button>
  <button class="btn secondary" onclick="loadTemplate('bracket')">🔩 CQ安装支架</button>
  <button class="btn secondary" onclick="loadTemplate('enclosure')">📦 CQ电子外壳</button>
</div>

<!-- Analyze -->
<div class="panel" id="panel-analyze">
  <div class="section-title">trimesh 3D分析</div>
  <div class="card">
    <div style="margin-bottom:8px;font-size:13px;color:#8b949e">STL文件路径</div>
    <input type="text" id="analyze-stl" placeholder="demo/coffee_mug.stl">
    <button class="btn" onclick="doAnalyze()">🔬 分析</button>
    <div class="result-box" id="analyze-result">等待分析...</div>
  </div>
</div>

<!-- VR -->
<div class="panel" id="panel-vr">
  <div class="section-title">🥽 VR 3D 查看器 (Quest3 兼容)</div>
  <div class="card">
    <div style="margin-bottom:8px;font-size:13px;color:#8b949e">STL文件URL（留空则使用demo模型）</div>
    <input type="text" id="vr-stl" placeholder="http://localhost:8872/api/stl/demo/coffee_mug.stl">
    <button class="vr-btn" onclick="openViewer()">🥽 打开3D查看器</button>
    <button class="btn secondary" onclick="openViewer(true)">🌐 VR模式（Quest3）</button>
    <div style="margin-top:16px;font-size:13px;color:#8b949e">
      <strong>Quest3 使用方式：</strong><br>
      1. 在Quest3浏览器打开: <code>https://aiotvr.xyz/model?stl=...</code><br>
      2. 或局域网直连: <code>http://192.168.31.141:8872/viewer</code>
    </div>
  </div>
  <div class="section-title">快速预览</div>
  <div id="demo-vr-grid" class="grid"></div>
</div>

<!-- Resources -->
<div class="panel" id="panel-resources">
  <div class="section-title">📦 资源库总览</div>
  <div class="grid" id="resources-grid"></div>
  <div class="section-title">批量分析</div>
  <div class="card">
    <div style="margin-bottom:8px;font-size:13px;color:#8b949e">STL目录路径（批量质量+质量分析）</div>
    <input type="text" id="batch-dir" placeholder="E:/道/道生一/一生二/ORS6-VAM饮料摇匀器/...STLs/SR6测试版零件">
    <button class="btn" onclick="doBatch()">🔬 批量分析</button>
    <div class="result-box" id="batch-result">等待分析...</div>
  </div>
</div>

<!-- Examples -->
<div class="panel" id="panel-examples">
  <div class="section-title">💡 CadQuery 示例库</div>
  <div id="examples-grid" class="grid"></div>
  <div class="section-title">示例代码预览</div>
  <div class="result-box" id="example-preview" style="min-height:200px">选择一个示例查看代码...</div>
</div>

<!-- ORS6 -->
<div class="panel" id="panel-ors6">
  <div class="section-title">ORS6 集成</div>
  <div class="card" id="ors6-status"></div>
  <div class="section-title">零件列表</div>
  <div id="ors6-parts-grid" class="grid"></div>
  <div style="margin-top:16px">
    <button class="btn" onclick="window.open('http://localhost:8871','_blank')">📺 ORS6 Studio :8871</button>
    <button class="btn secondary" onclick="loadOrs6Parts()">🔄 刷新零件</button>
  </div>
</div>

<!-- Templates -->
<div class="panel" id="panel-templates">
  <div class="section-title">📐 黄金模板库 — 每种引擎的最佳实践</div>
  <div class="grid" id="templates-grid"></div>
  <div class="section-title">模板代码预览</div>
  <div class="result-box" id="template-preview" style="min-height:200px">选择模板查看代码...</div>
  <button class="btn" id="use-template-btn" style="display:none;margin-top:8px" onclick="useCurrentTemplate()">⚗️ 使用此模板</button>
</div>

<!-- Tools -->
<div class="panel" id="panel-tools">
  <div class="section-title">工具链详情</div>
  <div class="card" id="tools-detail"></div>
  <div class="section-title">感知摘要</div>
  <div class="result-box" id="sense-result"></div>
  <button class="btn" onclick="loadSense()" style="margin-top:8px">🔄 刷新感知</button>
</div>

<!-- FC Remote -->
<div class="panel" id="panel-fcremote">
  <div class="section-title">🔧 FreeCAD Remote 控制台 (:18920 长连接)</div>
  <div class="card" id="fcremote-status">探测中...</div>
  <div class="section-title">快速命令</div>
  <div>
    <button class="btn secondary" onclick="fcView('isometric')">等轴测</button>
    <button class="btn secondary" onclick="fcView('fit_all')">全显</button>
    <button class="btn secondary" onclick="fcView('top')">顶视</button>
    <button class="btn secondary" onclick="fcView('front')">前视</button>
    <button class="btn" onclick="fcScreenshot()">📸 截图</button>
    <button class="btn secondary" onclick="loadFCRemote()">🔄 刷新</button>
  </div>
  <div class="section-title">Python Exec</div>
  <div class="card">
    <textarea id="fc-exec-code" placeholder="import FreeCAD as App&#10;__result__ = str(len(App.ActiveDocument.Objects)) if App.ActiveDocument else 'none'"></textarea>
    <button class="btn" onclick="fcExec()">▶ 执行</button>
    <div class="result-box" id="fc-exec-result">等待执行...</div>
  </div>
</div>

<!-- Forge -->
<div class="panel" id="panel-forge">
  <div class="section-title">⚒️ 道·锻造 — 参数化模型库 (35+)</div>
  <div class="card" id="forge-summary">加载中...</div>
  <div class="section-title">模型画廊</div>
  <div id="forge-gallery" class="grid"></div>
  <div class="section-title">参数化构建</div>
  <div class="card">
    <div style="margin-bottom:8px;font-size:13px;color:#8b949e">模型名称 (如 box/enclosure/gear_spur/hex_bolt)</div>
    <input type="text" id="forge-model" placeholder="enclosure" value="enclosure">
    <div style="margin-bottom:8px;font-size:13px;color:#8b949e">参数 JSON</div>
    <textarea id="forge-params" style="min-height:80px">{"L":60,"W":40,"H":30,"wall":2}</textarea>
    <label style="display:flex;align-items:center;font-size:12px;color:#8b949e;margin:8px 0;cursor:pointer"><input type="checkbox" id="forge-gui" class="cb-visible">GUI模式 (启动FreeCAD可视化)</label>
    <button class="btn" onclick="doForgeBuild()">⚒️ 锻造</button>
    <div class="result-box" id="forge-result">等待锻造...</div>
  </div>
</div>

<!-- Live -->
<div class="panel" id="panel-live">
  <div class="section-title" style="display:flex;align-items:center"><span class="live-dot"></span>实时监控 — Agent⇌User 阴阳同步</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;height:calc(100vh - 220px)">
    <div class="card" style="overflow:hidden;display:flex;flex-direction:column">
      <h3 style="display:flex;justify-content:space-between;align-items:center">3D 实时预览<button class="btn secondary" onclick="reloadLiveViewer()" style="font-size:11px;padding:3px 8px">🔄</button></h3>
      <iframe id="live-viewer" src="/viewer" style="flex:1;border:none;border-radius:6px;margin-top:8px;background:#0d1117"></iframe>
    </div>
    <div class="card" style="display:flex;flex-direction:column">
      <h3 style="display:flex;justify-content:space-between;align-items:center">事件流<span id="event-count" style="color:#58a6ff;font-size:12px">0 events</span></h3>
      <div style="display:flex;gap:4px;margin:8px 0">
        <button class="btn secondary" onclick="clearEvents()" style="font-size:11px;padding:3px 8px">清空</button>
        <span id="sse-status" style="font-size:11px;color:#8b949e;align-self:center">连接中...</span>
      </div>
      <div id="event-log" style="flex:1;overflow-y:auto;font-family:monospace;font-size:12px;padding:8px;background:#0d1117;border-radius:6px;line-height:1.6"></div>
    </div>
  </div>
</div>

</main>
<div id="toast"></div>

<script>
const BASE = '';

function show(tab) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('panel-' + tab).classList.add('active');
  event.target.classList.add('active');
  if (tab === 'overview') loadOverview();
  if (tab === 'projects') loadProjects();
  if (tab === 'resources') loadResources();
  if (tab === 'examples') loadExamples();
  if (tab === 'ors6') loadOrs6();
  if (tab === 'tools') loadTools();
  if (tab === 'templates') loadTemplates();
  if (tab === 'vr') loadDemoVR();
  if (tab === 'fcremote') loadFCRemote();
  if (tab === 'forge') loadForge();
}

async function loadFCRemote() {
  try {
    const h = await api('/api/health');
    const fc = h.freecad_remote || {connected:false};
    const el = document.getElementById('fcremote-status');
    if (fc.connected) {
      const s = await api('/api/fc/status');
      const c = await api('/api/fc/commands');
      const w = await api('/api/fc/workbenches');
      el.innerHTML = `
        <div class="tool-row"><span>连接</span><span class="ok">✅ :18920</span></div>
        <div class="tool-row"><span>FreeCAD</span><span>${(fc.version||[]).slice(0,3).join('.')}</span></div>
        <div class="tool-row"><span>工作台</span><span>${s.active_workbench || '?'}</span></div>
        <div class="tool-row"><span>命令数</span><span>${c.count || 0}</span></div>
        <div class="tool-row"><span>工作台数</span><span>${Object.keys(w.workbenches||{}).length}</span></div>
      `;
    } else {
      el.innerHTML = `<div class="fail">❌ FC Remote 未连接: ${fc.error||''}</div>
        <div style="margin-top:8px;font-size:12px;color:#8b949e">启动方式: 在 FreeCAD GUI 中运行 _fc_remote_server.py</div>`;
    }
  } catch(e) { document.getElementById('fcremote-status').innerHTML = '<div class="fail">探测失败: '+e+'</div>'; }
}

async function fcView(action) {
  const r = await api('/api/fc/view', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action})});
  toast(r.ok ? '视图: '+action : '失败', r.ok);
}

async function fcExec() {
  const code = document.getElementById('fc-exec-code').value;
  const r = await api('/api/fc/exec', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({code})});
  document.getElementById('fc-exec-result').textContent = JSON.stringify(r, null, 2);
}

async function fcScreenshot() {
  const r = await api('/api/fc/screenshot', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
  if (r.ok && r.data) {
    const w = window.open('', '_blank');
    w.document.write('<img src="data:image/png;base64,'+r.data+'" style="max-width:100%">');
  } else { toast('截图失败', false); }
}

async function loadForge() {
  try {
    const m = await api('/api/forge/models');
    document.getElementById('forge-summary').innerHTML = `
      <div class="tool-row"><span>模型数</span><span class="ok">${m.count||0}</span></div>
      <div class="tool-row"><span>Ops数</span><span class="ok">${m.ops_count||0}</span></div>
      <div class="tool-row"><span>已建画廊</span><span>${(m.gallery||[]).length}</span></div>
    `;
    const g = document.getElementById('forge-gallery');
    g.innerHTML = (m.gallery||[]).map(x => `
      <div class="project-card" onclick="document.getElementById('forge-model').value='${x.name}'">
        <div style="font-weight:600">${x.name}</div>
        <div class="tag">STL ${Math.round(x.size/1024)}KB</div>
      </div>
    `).join('');
  } catch(e) { document.getElementById('forge-summary').innerHTML = '<div class="fail">'+e+'</div>'; }
}

async function doForgeBuild() {
  const model = document.getElementById('forge-model').value;
  const params = JSON.parse(document.getElementById('forge-params').value || '{}');
  const gui = document.getElementById('forge-gui').checked;
  document.getElementById('forge-result').textContent = '锻造中...';
  const r = await api('/api/forge/build', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({model, params, gui})});
  document.getElementById('forge-result').textContent = JSON.stringify(r, null, 2);
}

function toast(msg, ok=true) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.background = ok ? '#238636' : '#da3633';
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 3000);
}

async function api(path, opts) {
  const r = await fetch(BASE + path, opts);
  return r.json();
}

async function loadOverview() {
  const data = await api('/api/health');
  const cards = document.getElementById('stat-cards');
  const res = data.resources || {};
  cards.innerHTML = `
    <div class="card"><h3>项目</h3><div class="stat">${data.projects || 0}</div><div style="font-size:12px;color:#8b949e">建模项目</div></div>
    <div class="card"><h3>ORS6零件</h3><div class="stat">${data.ors6_parts || 0}</div><div style="font-size:12px;color:#8b949e">已连接${data.ors6_connected ? '✅' : '❌'}</div></div>
    <div class="card"><h3>资源库</h3><div class="stat">${res.total || 0}</div><div style="font-size:12px;color:#8b949e">BOSL2:${res.bosl2||0} MCAD:${res.mcad||0} CQ:${res.cq_examples||0}</div></div>
    <div class="card"><h3>评级</h3><div class="stat">${data.grade || '?'}</div><div style="font-size:12px;color:#8b949e">系统健康度</div></div>
  `;
  document.getElementById('grade-badge').textContent = 'Grade ' + (data.grade || '?');
  // Tools overview
  const tov = document.getElementById('tools-overview');
  tov.innerHTML = Object.entries(data.tools || {}).map(([k,v]) =>
    `<div class="tool-row"><span>${k}</span><span class="${v.includes('✅')?'ok':'fail'}">${v}</span></div>`
  ).join('');
}

async function loadProjects() {
  const data = await api('/api/catalog');
  const pg = document.getElementById('projects-grid');
  const dg = document.getElementById('demos-grid');
  if (!data.projects.length) { pg.innerHTML = '<div style="color:#8b949e">暂无项目。使用 forge_v3.py init 创建。</div>'; }
  pg.innerHTML = data.projects.map(p => `
    <div class="project-card">
      <div style="font-weight:600;margin-bottom:4px">${p.name}</div>
      <div class="tag">${p.stl_count} STL</div>
      <div class="tag">${p.scad_count} SCAD</div>
      <div class="tag">${p.iterations} 迭代</div>
      ${p.stls.map(s => `<div style="font-size:11px;color:#8b949e;margin-top:4px">📄 ${s}</div>`).join('')}
    </div>
  `).join('');
  dg.innerHTML = data.demos.map(d => `
    <div class="project-card" onclick="quickView('${d.stl || ''}')">
      <div style="font-weight:600;margin-bottom:4px">${d.name}</div>
      <div class="tag">Demo</div>
      ${d.stl ? '<div class="tag ok">STL ✅</div>' : '<div class="tag fail">需渲染</div>'}
      <button class="btn secondary" onclick="event.stopPropagation();fillAnalyze('${d.stl || ''}')" style="margin-top:8px;font-size:11px">🔬 分析</button>
    </div>
  `).join('');
}

function quickView(stl) {
  if (!stl) return;
  document.getElementById('vr-stl').value = 'http://localhost:8872/api/stl/' + stl;
  show('vr');
}

function fillAnalyze(stl) {
  document.getElementById('analyze-stl').value = stl;
  show('analyze');
}

async function doRender() {
  const scad = document.getElementById('render-scad').value.trim();
  const stl = document.getElementById('render-stl').value.trim();
  const fn = document.getElementById('render-fn').value.trim() || '64';
  const visible = document.getElementById('render-visible').checked;
  if (!scad) { toast('请输入SCAD路径', false); return; }
  document.getElementById('render-result').textContent = '渲染中...';
  const r = await api('/api/render', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({scad, stl: stl||null, fn: parseInt(fn), visible})
  });
  document.getElementById('render-result').textContent = JSON.stringify(r, null, 2);
  if (r.ok) toast('渲染成功 ✅ ' + r.seconds + 's');
  else toast('渲染失败: ' + (r.error||''), false);
}

async function doGenerate() {
  const code = document.getElementById('gen-code').value.trim();
  const output = document.getElementById('gen-output').value.trim();
  const visible = document.getElementById('gen-visible').checked;
  if (!code) { toast('请输入代码', false); return; }
  document.getElementById('gen-result').textContent = '执行中...';
  const r = await api('/api/generate', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({code, output: output||null, visible})
  });
  document.getElementById('gen-result').textContent = JSON.stringify(r, null, 2);
  if (r.ok) toast('生成成功 ✅');
  else toast('执行失败', false);
}

async function doAnalyze() {
  const stl = document.getElementById('analyze-stl').value.trim();
  if (!stl) { toast('请输入STL路径', false); return; }
  document.getElementById('analyze-result').textContent = '分析中...';
  const r = await api('/api/analyze', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({stl})
  });
  document.getElementById('analyze-result').textContent = JSON.stringify(r, null, 2);
  if (r.ok) toast('分析完成 ✅');
}

function openViewer(vr=false) {
  const stl = document.getElementById('vr-stl').value.trim();
  let url = '/viewer';
  if (stl) url += '?stl=' + encodeURIComponent(stl);
  if (vr) url += (stl ? '&' : '?') + 'vr=1';
  window.open(url, '_blank');
}

async function loadDemoVR() {
  const data = await api('/api/catalog');
  const g = document.getElementById('demo-vr-grid');
  g.innerHTML = data.demos.filter(d => d.stl).map(d => `
    <div class="project-card" onclick="openViewerFor('${d.stl}')">
      <div style="font-weight:600;margin-bottom:4px">${d.name}</div>
      <div class="tag">demo</div>
      <button class="vr-btn" onclick="event.stopPropagation();openViewerFor('${d.stl}')" style="margin-top:8px;font-size:12px">🥽 VR查看</button>
    </div>
  `).join('');
}

function openViewerFor(stl) {
  window.open('/viewer?stl=' + encodeURIComponent('http://localhost:8872/api/stl/' + stl), '_blank');
}

async function loadOrs6() {
  const data = await api('/api/ors6/health');
  document.getElementById('ors6-status').innerHTML = `
    <div class="tool-row"><span>ORS6连接</span><span class="${data.connected?'ok':'fail'}">${data.connected?'✅已连接':'❌未连接'}</span></div>
    <div class="tool-row"><span>零件数量</span><span class="ok">${data.parts_count || 0}</span></div>
    <div class="tool-row"><span>IK参数</span><span class="ok">${data.ik ? JSON.stringify(data.ik) : 'N/A'}</span></div>
  `;
  if (data.connected) loadOrs6Parts();
}

async function loadOrs6Parts() {
  const data = await api('/api/ors6/parts');
  const g = document.getElementById('ors6-parts-grid');
  if (!data.parts) { g.innerHTML = '<div style="color:#8b949e">ORS6未连接</div>'; return; }
  g.innerHTML = data.parts.slice(0, 12).map(p => `
    <div class="project-card">
      <div style="font-weight:600;margin-bottom:4px">${p.name}</div>
      <div class="tag">${p.group}</div>
      <div style="width:16px;height:16px;border-radius:3px;background:#${p.color};display:inline-block;margin:2px"></div>
      <span class="tag ${p.exists?'ok':'fail'}">${p.exists?'STL✅':'缺失❌'}</span>
    </div>
  `).join('');
}

async function loadTools() {
  const data = await api('/api/tools');
  document.getElementById('tools-detail').innerHTML = Object.entries(data).map(([k,v]) => `
    <div class="tool-row">
      <span style="font-weight:600">${k}</span>
      <span class="${v.ok?'ok':'fail'}">${v.ok ? '✅' + (v.version ? ' v'+v.version : '') + (v.path ? '<br><span style="font-size:11px;color:#8b949e">'+v.path+'</span>' : '') : '❌ 未安装'}</span>
    </div>
  `).join('');
  loadSense();
}

async function loadSense() {
  const data = await api('/sense');
  document.getElementById('sense-result').textContent = JSON.stringify(data, null, 2);
}

const TEMPLATES = {
  box: `import cadquery as cq
import os
os.makedirs('projects/temp/output', exist_ok=True)
result = cq.Workplane('XY').box(30, 20, 10)
result.val().exportStl('projects/temp/output/box.stl')
print("Generated: box.stl")`,
  cylinder: `import cadquery as cq
import os
os.makedirs('projects/temp/output', exist_ok=True)
result = cq.Workplane('XY').cylinder(20, 10)
result.val().exportStl('projects/temp/output/cylinder.stl')
print("Generated: cylinder.stl")`,
  build123d_box: `from build123d import *
import os
os.makedirs('projects/temp/output', exist_ok=True)
with BuildPart() as part:
    Box(30, 20, 10)
export_stl(part.part, 'projects/temp/output/b123d_box.stl')
print("Generated: b123d_box.stl")`,
  bracket: `import cadquery as cq
import os
os.makedirs('projects/temp/output', exist_ok=True)
# Parametric bracket with mounting holes
W, H, T = 60, 40, 5
result = (cq.Workplane('XY').box(W, H, T)
    .faces('>Z').workplane()
    .pushPoints([(-20, 0), (20, 0)]).hole(5.5)
    .faces('>Z').workplane().slot2D(10, 20, angle=90).cutThruAll()
    .edges('|Z').fillet(3)
    .edges('>Z').chamfer(0.5))
cq.exporters.export(result, 'projects/temp/output/bracket.stl')
print("Generated: bracket.stl")`,
  enclosure: `import cadquery as cq
import os
os.makedirs('projects/temp/output', exist_ok=True)
# Electronics enclosure with standoffs
L, W, H, WALL = 80, 50, 30, 2
result = (cq.Workplane('XY')
    .box(L+2*WALL, W+2*WALL, H+WALL)
    .edges('|Z').fillet(3)
    .faces('>Z').shell(-WALL))
cq.exporters.export(result, 'projects/temp/output/enclosure.stl')
print("Generated: enclosure.stl")`,
  esp32_mount: `import cadquery as cq
import os
os.makedirs('projects/temp/output', exist_ok=True)
# ESP32 DevKit V1 mount bracket
W, H, T = 58, 28, 3  # board footprint + wall
result = (cq.Workplane('XY')
    .box(W+6, H+6, T)
    .faces('>Z').workplane()
    .rect(W, H).cutBlind(-T)
    .faces('>Z').workplane()
    .pushPoints([(W/2+1, 0, 0), (-W/2-1, 0, 0)])
    .hole(4, T))
result.val().exportStl('projects/temp/output/esp32_mount.stl')
print("Generated: ESP32 mount STL")`,
};

function loadTemplate(name) {
  const t = TEMPLATES[name];
  if (t) document.getElementById('gen-code').value = t;
}

async function loadResources() {
  const data = await api('/api/resources');
  const g = document.getElementById('resources-grid');
  if (!data.resources) { g.innerHTML = '<div style="color:#8b949e">无资源数据</div>'; return; }
  g.innerHTML = Object.entries(data.resources).map(([k,v]) => `
    <div class="card">
      <h3>${k}</h3>
      <div class="stat">${v.count || '—'}</div>
      <div style="font-size:12px;color:#8b949e">${v.type || ''}</div>
      ${v.files ? '<div style="margin-top:8px">' + v.files.slice(0,8).map(f => '<span class="tag">'+f+'</span>').join('') + (v.files.length > 8 ? '<span class="tag">+' + (v.files.length-8) + ' more</span>' : '') + '</div>' : ''}
    </div>
  `).join('');
}

async function loadExamples() {
  const data = await api('/api/examples');
  const g = document.getElementById('examples-grid');
  if (!data.examples || !data.examples.length) { g.innerHTML = '<div style="color:#8b949e">无示例</div>'; return; }
  g.innerHTML = data.examples.map(ex => `
    <div class="project-card" onclick="showExample('${ex.name}')">
      <div style="font-weight:600;margin-bottom:4px">${ex.name}</div>
      <div class="tag">${ex.lines} lines</div>
      <div class="tag">CadQuery</div>
      <button class="btn secondary" style="margin-top:8px;font-size:11px" onclick="event.stopPropagation();useExample('${ex.name}')">⚗️ 使用此示例</button>
    </div>
  `).join('');
  window._examples = data.examples;
}

function showExample(name) {
  if (!window._examples) return;
  const ex = window._examples.find(e => e.name === name);
  if (ex) document.getElementById('example-preview').textContent = ex.full_code || ex.preview;
}

function useExample(name) {
  if (!window._examples) return;
  const ex = window._examples.find(e => e.name === name);
  if (ex) {
    document.getElementById('gen-code').value = ex.full_code || ex.preview;
    show('generate');
  }
}

async function doBatch() {
  const dir = document.getElementById('batch-dir').value.trim();
  if (!dir) { toast('请输入STL目录路径', false); return; }
  document.getElementById('batch-result').textContent = '分析中...';
  const r = await api('/api/batch?dir=' + encodeURIComponent(dir));
  if (r.error) {
    document.getElementById('batch-result').textContent = 'Error: ' + r.error;
    toast('批量分析失败', false);
  } else {
    let txt = `${r.total_parts} 零件 | ${r.total_mass_g}g | ${r.grade_summary}\n\n`;
    (r.parts||[]).forEach(p => {
      txt += `${p.grade||'?'} ${p.part}: ${p.mass_g||'?'}g  ${p.size_mm ? p.size_mm.map(v=>v+'mm').join('×') : ''} ${p.watertight?'✅':'⚠️'}\n`;
    });
    txt += `\nTime: ${r.time_ms}ms`;
    document.getElementById('batch-result').textContent = txt;
    toast(`批量分析完成: ${r.total_parts}零件 ${r.grade_summary}`);
  }
}

// ─── Templates ───
let _currentTemplate = null;

async function loadTemplates() {
  const data = await api('/api/templates');
  const g = document.getElementById('templates-grid');
  if (!data.templates || !data.templates.length) { g.innerHTML = '<div style="color:#8b949e">无模板</div>'; return; }
  const engineColors = {CadQuery:'#58a6ff', build123d:'#3fb950', OpenSCAD:'#f0883e', FreeCAD:'#bc8cff'};
  g.innerHTML = data.templates.map(t => `
    <div class="project-card" onclick="showTemplate('${t.name}')">
      <div style="font-weight:600;margin-bottom:4px">${t.name}</div>
      <div class="tag" style="background:${engineColors[t.engine]||'#21262d'}30;color:${engineColors[t.engine]||'#8b949e'}">${t.engine}</div>
      <div class="tag">${t.lines} lines</div>
      <div style="font-size:11px;color:#8b949e;margin-top:4px">${t.description}</div>
    </div>
  `).join('');
  window._templates = data.templates;
}

function showTemplate(name) {
  if (!window._templates) return;
  const t = window._templates.find(x => x.name === name);
  if (!t) return;
  _currentTemplate = t;
  document.getElementById('template-preview').textContent = t.code;
  const btn = document.getElementById('use-template-btn');
  if (btn) { btn.style.display = 'inline-block'; btn.textContent = '⚗️ 使用 ' + t.name; }
}

function useCurrentTemplate() {
  if (!_currentTemplate) return;
  document.getElementById('gen-code').value = _currentTemplate.code;
  show('generate');
}

// ─── SSE Live Connection (阳→阴 bridge) ───
let _sse = null;
let _evtCount = 0;

function connectSSE() {
  if (_sse) _sse.close();
  _sse = new EventSource('/api/events');
  const st = document.getElementById('sse-status');
  _sse.onopen = () => { if (st) st.textContent = '已连接 ✅'; };
  _sse.onmessage = (e) => {
    try {
      const evt = JSON.parse(e.data);
      _evtCount++;
      const ec = document.getElementById('event-count');
      if (ec) ec.textContent = _evtCount + ' events';
      const log = document.getElementById('event-log');
      if (log) {
        const time = new Date(evt.ts).toLocaleTimeString();
        const isOk = evt.type.includes('complete') && evt.data && evt.data.ok;
        const isStart = evt.type.includes('start');
        const color = isOk ? '#3fb950' : isStart ? '#58a6ff' : (evt.data && evt.data.ok === false) ? '#f85149' : '#e6edf3';
        const icon = isOk ? '✅' : isStart ? '⏳' : '❌';
        log.innerHTML = `<div style="color:${color};margin-bottom:4px">${icon} [${time}] <b>${evt.type}</b>: ${JSON.stringify(evt.data||{}).substring(0,150)}</div>` + log.innerHTML;
      }
      // Viewer iframe handles STL auto-load via its own SSE connection (no iframe reload needed)
    } catch(err) {}
  };
  _sse.onerror = () => {
    if (st) st.textContent = '断开 ⚠️ 重连中...';
    setTimeout(connectSSE, 5000);
  };
}

function clearEvents() {
  const log = document.getElementById('event-log');
  if (log) log.innerHTML = '';
  _evtCount = 0;
  const ec = document.getElementById('event-count');
  if (ec) ec.textContent = '0 events';
}

function reloadLiveViewer() {
  const vf = document.getElementById('live-viewer');
  if (vf) vf.src = '/viewer';
}

window.addEventListener('load', () => { loadOverview(); connectSSE(); });
</script>
</body>
</html>"""

# ─────────────────────────────────────────────────────
# FreeCAD Remote Proxy (:18920 — GUI 长连接)
# 道法自然：Hub 对外统一门面，幕后代理到 FC Remote
# ─────────────────────────────────────────────────────
FC_REMOTE = "http://127.0.0.1:18920"

def fc_remote_probe(timeout=1.0):
    """轻量探测 FC Remote 是否在线。"""
    try:
        import urllib.request as _ur
        req = _ur.Request(FC_REMOTE + "/status")
        with _ur.urlopen(req, timeout=timeout) as r:
            s = json.loads(r.read())
        return {"connected": True, "port": 18920,
                "version": s.get("freecad_version"),
                "workbench": s.get("active_workbench")}
    except Exception as e:
        return {"connected": False, "port": 18920, "error": str(e)[:80]}

def fc_remote_forward(method, path, body=None, timeout=180):
    """将请求透传到 FC Remote 并返回 JSON。"""
    import urllib.request as _ur
    url = FC_REMOTE + path
    try:
        if method == "POST":
            data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
            req = _ur.Request(url, data, {"Content-Type": "application/json"})
        else:
            req = _ur.Request(url)
        with _ur.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": f"fc_remote proxy {method} {path}: {e}"}

def forge_models_summary():
    """反向解构 dao_forge 的模型注册/ops/画廊。"""
    try:
        from dao_forge import MODEL_REGISTRY, OPS_REGISTRY
        registry = sorted(MODEL_REGISTRY.keys())
        gallery_dir = _dao_paths.PROJECTS / "fc_output" / "_\u4e07\u6cd5\u5f52\u4e00"
        gallery = []
        if gallery_dir.exists():
            for m in registry:
                stl = gallery_dir / f"{m}.stl"
                if stl.exists() and stl.stat().st_size > 100:
                    gallery.append({
                        "name": m,
                        "stl": f"projects/fc_output/_\u4e07\u6cd5\u5f52\u4e00/{m}.stl",
                        "size": stl.stat().st_size,
                    })
        return {"registry": registry, "ops_count": len(OPS_REGISTRY),
                "gallery": gallery, "count": len(registry)}
    except Exception as e:
        return {"registry": [], "ops_count": 0, "gallery": [], "error": str(e)}

def forge_build(model, params=None, gui=False, formats=None, timeout=180):
    """委托 DaoForge 参数化构建。"""
    try:
        from dao_forge import DaoForge
        forge = DaoForge()
        t0 = time.time()
        r = forge.build(model, params=params or {}, gui=gui,
                        formats=formats or ["stl", "step"])
        r["elapsed_s"] = round(time.time() - t0, 2)
        r["mode"] = "gui" if gui else "headless"
        return r
    except Exception as e:
        import traceback as _tb
        return {"ok": False, "error": str(e), "trace": _tb.format_exc()[:400],
                "model": model}

# ─────────────────────────────────────────────────────
# HTTP Handler
# ─────────────────────────────────────────────────────
class HubHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        p = parsed.path
        q = urllib.parse.parse_qs(parsed.query)

        if p in ('/', '/index.html'):
            self._html(DASHBOARD_HTML)
        elif p == '/viewer':
            # Serve the VR viewer HTML
            viewer_path = SCRIPT_DIR / "model_viewer.html"   # 同层 20-万法_Forge
            if viewer_path.exists():
                self._file(viewer_path)
            else:
                self._json({"error": "model_viewer.html not found — run model_hub.py to generate"}, 404)
        elif p == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        elif p == '/api/health':
            cat = scan_projects()
            tool_status = {k: ("✅ ok" if v.get("ok") else "❌") for k, v in TOOLS.items()}
            ors6_ok = _load_ors6()
            # Resource counts
            res_dir = _dao_paths.WORLD / "网络资源库"
            bosl2_n = len(list((res_dir / "OpenSCAD_Libraries" / "BOSL2").glob("*.scad"))) if (res_dir / "OpenSCAD_Libraries" / "BOSL2").is_dir() else 0
            mcad_n = len(list((res_dir / "OpenSCAD_Libraries" / "MCAD").glob("*.scad"))) if (res_dir / "OpenSCAD_Libraries" / "MCAD").is_dir() else 0
            cq_ex_n = len(list((res_dir / "cadquery" / "examples").glob("*.py"))) if (res_dir / "cadquery" / "examples").is_dir() else 0
            self._json({
                "status": "ok", "port": PORT,
                "tools": tool_status,
                "projects": cat["total"], "demos": len(cat["demos"]),
                "ors6_connected": ors6_ok,
                "ors6_parts": len(_ors6_parts) if _ors6_parts else 0,
                "resources": {"bosl2": bosl2_n, "mcad": mcad_n, "cq_examples": cq_ex_n,
                              "total": bosl2_n + mcad_n + cq_ex_n},
                "freecad_remote": fc_remote_probe(),
                "grade": "S" if TOOLS.get("openscad",{}).get("ok") and TOOLS.get("trimesh",{}).get("ok") else "A",
            })
        elif p == '/api/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            q = _queue.Queue()
            with _event_lock:
                _event_subscribers.append(q)
                for evt in _event_history[-10:]:
                    q.put_nowait(evt)
            try:
                while True:
                    try:
                        event = q.get(timeout=30)
                        msg = f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
                        self.wfile.write(msg.encode('utf-8'))
                        self.wfile.flush()
                    except _queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with _event_lock:
                    if q in _event_subscribers:
                        _event_subscribers.remove(q)
            return
        elif p == '/api/events/history':
            with _event_lock:
                self._json({"events": list(_event_history), "count": len(_event_history)})
        elif p == '/api/catalog':
            self._json(scan_projects())
        elif p == '/api/tools':
            self._json(TOOLS)
        elif p == '/api/projects':
            self._json(scan_projects())
        elif p == '/api/ors6/health':
            ok = _load_ors6()
            self._json({"connected": ok, "parts_count": len(_ors6_parts) if _ors6_parts else 0,
                        "ik": _ors6_ik})
        elif p == '/api/ors6/parts':
            if not _load_ors6():
                self._json({"error": "ORS6 not connected"})
                return
            manifest = []
            for name, tup in _ors6_parts.items():
                sub, fn, color_int, group = tup[0], tup[1], tup[2], tup[3]
                import sys as _sys
                ors6_mod = _sys.modules.get('sr6_tools')
                stl_root = getattr(ors6_mod, 'STL_ROOT', '') if ors6_mod else ''
                path = os.path.join(stl_root, sub, fn)
                manifest.append({
                    "name": name, "group": group,
                    "color": f"{color_int:06x}",
                    "exists": os.path.exists(path),
                    "url": f"http://localhost:8871/stl/{urllib.parse.quote(name)}",
                })
            self._json({"parts": manifest, "count": len(manifest)})
        elif p.startswith('/api/stl/'):
            rel = urllib.parse.unquote(p[9:])  # URL-decode + strip prefix
            # Support both absolute (D:\...) and relative (demo/foo.stl) paths
            if os.path.isabs(rel):
                fpath = Path(rel)
            else:
                fpath = ROOT_DIR / rel
            fpath = fpath.resolve()
            if fpath.exists() and fpath.suffix.lower() in ('.stl', '.step', '.obj', '.3mf'):
                self._file(fpath, 'application/octet-stream')
            else:
                self._json({"error": f"STL not found: {rel}"}, 404)
        elif p == '/sense':
            self._json(sense())
        elif p == '/api/quest3/status':
            self._json(quest3_status())
        elif p == '/api/quest3/open':
            url = q.get('url', [''])[0]
            if not url:
                self._json({"ok": False, "error": "url required"})
                return
            self._json(quest3_open_url(url))
        elif p == '/api/quest3/vr':
            stl = q.get('stl', [''])[0]
            self._json(quest3_open_3d_viewer(stl or None))
        # ── forge_v3 Analysis API ──
        elif p == '/api/mass':
            stl = q.get('stl', [''])[0]
            mat = q.get('material', ['pla'])[0]
            if not stl:
                self._json({"error": "stl parameter required"})
                return
            try:
                from forge_v3 import api_mass
                self._json(api_mass(stl, mat))
            except Exception as e:
                self._json({"error": str(e)})
        elif p == '/api/quality':
            stl = q.get('stl', [''])[0]
            if not stl:
                self._json({"error": "stl parameter required"})
                return
            try:
                from forge_v3 import api_quality
                self._json(api_quality(stl))
            except Exception as e:
                self._json({"error": str(e)})
        elif p == '/api/collision':
            s1 = q.get('stl1', [''])[0]
            s2 = q.get('stl2', [''])[0]
            if not s1 or not s2:
                self._json({"error": "stl1 and stl2 parameters required"})
                return
            try:
                from forge_v3 import api_collision
                self._json(api_collision(s1, s2))
            except Exception as e:
                self._json({"error": str(e)})
        elif p == '/api/printability':
            stl = q.get('stl', [''])[0]
            tech = q.get('tech', ['fdm'])[0]
            if not stl:
                self._json({"error": "stl parameter required"})
                return
            try:
                from forge_v3 import api_printability
                self._json(api_printability(stl, tech))
            except Exception as e:
                self._json({"error": str(e)})
        elif p == '/api/hubs':
            try:
                from forge_v3 import _probe_workspace_hubs
                self._json(_probe_workspace_hubs())
            except Exception as e:
                self._json({"error": str(e)})
        elif p == '/api/forge':
            try:
                from forge_v3 import get_tools, VERSION
                self._json({"version": VERSION, "tools": get_tools()})
            except Exception as e:
                self._json({"error": str(e)})
        elif p == '/api/forge/models':
            self._json(forge_models_summary())
        elif p.startswith('/api/fc/'):
            fc_path = "/" + p[len('/api/fc/'):].rstrip("/")
            if fc_path == "/":
                fc_path = "/status"
            self._json(fc_remote_forward("GET", fc_path))
        elif p == '/api/templates':
            tmpl_dir = _dao_paths.TEMPLATES
            templates = []
            if tmpl_dir.is_dir():
                engine_map = {"cq_": "CadQuery", "b3d_": "build123d", "scad_": "OpenSCAD", "fc_": "FreeCAD"}
                for f in sorted(tmpl_dir.iterdir()):
                    if f.suffix in (".py", ".scad", ".json") and not f.name.startswith("_"):
                        try:
                            code = f.read_text(encoding="utf-8", errors="replace")
                            engine = "Unknown"
                            for prefix, eng in engine_map.items():
                                if f.stem.startswith(prefix):
                                    engine = eng
                                    break
                            # Extract description from first docstring or comment
                            desc = f.stem.replace("_", " ").title()
                            for line in code.splitlines()[:10]:
                                if "—" in line or "Golden Template" in line:
                                    desc = line.strip().strip("\"'# /*")
                                    break
                            templates.append({
                                "name": f.stem, "file": f.name, "engine": engine,
                                "lines": code.count("\n") + 1,
                                "description": desc[:100],
                                "code": code
                            })
                        except Exception:
                            pass
            self._json({"templates": templates, "count": len(templates)})
        elif p == '/api/examples':
            try:
                from forge_v3 import api_examples
                self._json(api_examples())
            except Exception as e:
                self._json({"error": str(e)})
        elif p == '/api/resources':
            try:
                from forge_v3 import api_resources
                self._json(api_resources())
            except Exception as e:
                self._json({"error": str(e)})
        elif p == '/api/batch':
            stl_dir = q.get('dir', [''])[0]
            mat = q.get('material', ['pla'])[0]
            if not stl_dir:
                self._json({"error": "dir parameter required"})
                return
            try:
                from forge_v3 import cmd_batch
                import io, contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cmd_batch(stl_dir, mat)
                self._json(json.loads(buf.getvalue()))
            except Exception as e:
                self._json({"error": str(e)})
        else:
            # Try static file
            fpath = ROOT_DIR / p.lstrip('/')
            if fpath.exists() and fpath.is_file():
                self._file(fpath)
            else:
                self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length) or b'{}')
        p = urllib.parse.urlparse(self.path).path

        if p == '/api/render':
            scad = body.get('scad', '')
            stl_out = body.get('stl') or None
            fn = int(body.get('fn', 64))
            if not scad:
                self._json({"ok": False, "error": "scad required"})
                return
            visible = body.get('visible', False)
            scad_path = Path(scad) if Path(scad).is_absolute() else ROOT_DIR / scad
            stl_path = (Path(stl_out) if stl_out else None)
            self._json(run_openscad(scad_path, stl_path, fn, visible=visible))

        elif p == '/api/generate':
            code = body.get('code', '')
            output = body.get('output') or str(_dao_paths.PROJECTS / 'temp/output/generated.stl')
            if not code:
                self._json({"ok": False, "error": "code required"})
                return
            visible = body.get('visible', False)
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            self._json(run_python_cad(code, output, visible=visible))

        elif p == '/api/analyze':
            stl = body.get('stl', '')
            if not stl:
                self._json({"ok": False, "error": "stl required"})
                return
            fpath = Path(stl) if Path(stl).is_absolute() else ROOT_DIR / stl
            self._json(analyze_stl(fpath))

        elif p == '/api/freecad':
            script = body.get('script', '')
            if not script:
                self._json({"ok": False, "error": "script path required"})
                return
            visible = body.get('visible', False)
            fpath = Path(script) if Path(script).is_absolute() else ROOT_DIR / script
            self._json(run_freecad(fpath, visible=visible))

        elif p == '/api/forge/build':
            model = body.get('model', '')
            if not model:
                self._json({"ok": False, "error": "model required"})
                return
            self._json(forge_build(
                model,
                params=body.get('params', {}),
                gui=bool(body.get('gui', False)),
                formats=body.get('formats', ['stl', 'step']),
            ))

        elif p.startswith('/api/fc/'):
            fc_path = "/" + p[len('/api/fc/'):].rstrip("/")
            if fc_path == "/":
                fc_path = "/status"
            self._json(fc_remote_forward("POST", fc_path, body))

        elif p == '/api/manufacture':
            stl = body.get('stl', '')
            tech = body.get('tech', 'fdm')
            if not stl:
                self._json({"ok": False, "error": "stl required"})
                return
            # Delegate to forge_v3.py printability
            forge = SCRIPT_DIR / 'forge_v3.py'   # 同层 20-万法_Forge
            fpath = Path(stl) if Path(stl).is_absolute() else ROOT_DIR / stl
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            r = subprocess.run([sys.executable, str(forge), 'printability', str(fpath), tech],
                               capture_output=True, text=True, timeout=60, cwd=str(ROOT_DIR),
                               startupinfo=si, creationflags=_NO_WINDOW)
            try:
                self._json(json.loads(r.stdout))
            except Exception:
                self._json({"ok": False, "error": r.stderr[:300]})
        else:
            self._json({"error": "unknown endpoint"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html_str):
        body = html_str.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ct=None):
        path = Path(path)
        if ct is None:
            ct = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
        with open(path, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', len(data))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass  # silent

# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────
if __name__ == '__main__':
    # Pre-load ORS6 integration
    threading.Thread(target=_load_ors6, daemon=True).start()
    class ThreadedHub(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
    server = ThreadedHub(('0.0.0.0', PORT), HubHandler)
    print(f"ModelHub @ http://localhost:{PORT}")
    print(f"  Dashboard: http://localhost:{PORT}/")
    print(f"  VR Viewer: http://localhost:{PORT}/viewer")
    print(f"  API: /api/health | /api/catalog | /api/render | /api/analyze")
    print(f"  ORS6: {ORS6_DIR.name} → /api/ors6/*")
    t_names = [k for k,v in TOOLS.items() if v.get("ok")]
    print(f"  Tools: {', '.join(t_names)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
