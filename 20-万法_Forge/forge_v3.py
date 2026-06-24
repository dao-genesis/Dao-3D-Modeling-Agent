#!/usr/bin/env python3
"""
ModelForge v3 — Universal 3D Analysis & Modeling Engine
Generalized from ORS6 sr6_analyzer + forge_v2 capabilities.

Agent's 3D World Understanding: millisecond-precise computations
that surpass human visual inspection.

Capabilities:
  ANALYSIS (from ORS6 sr6_analyzer, generalized):
    mass <stl> [material]       Mass properties (volume/mass/CoM/inertia)
    quality <stl>               Mesh quality check (watertight/normals/degenerates)
    collision <stl1> <stl2>     Collision detection between two meshes
    clearance <dir>             Clearance analysis for all STL pairs in directory
    assembly <dir>              Assembly statistics (bounding box/groups/envelope)
    section <stl> <z>           Cross-section at Z height

  MODELING (from forge_v2):
    cq <code> [out]             CadQuery inline execution
    b3d <code> [out]            build123d inline execution
    scad <file> [out] [fn]      OpenSCAD render
    freecad <script>            FreeCAD headless script execution

  UTILITIES:
    measure <stl>               Full geometric measurement report
    compare <stl1> <stl2>       3D shape similarity analysis
    bom <dir>                   Bill of Materials from STL directory
    convert <in> <out>          Format conversion (STL/STEP/OBJ)
    check                       Environment & tool chain check
    serve [port]                Start ModelHub HTTP server (default :8872)

Usage:
    python forge_v3.py check
    python forge_v3.py mass model.stl pla
    python forge_v3.py quality model.stl
    python forge_v3.py collision part_a.stl part_b.stl
    python forge_v3.py cq "result = cq.Workplane().box(20,20,10)" out.stl
    python forge_v3.py serve 8872
"""
import os, sys, json, subprocess, time, shutil, math
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

VERSION = "3.0.0"

# ─────────────────────────────────────────────────────
# Tool Detection
# ─────────────────────────────────────────────────────
OPENSCAD_SEARCH = [
    r"D:\openscad\openscad.com", r"D:\openscad\openscad.exe",
    r"C:\Program Files\OpenSCAD\openscad.exe",
]
FREECAD_SEARCH = [
    r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe",
    r"D:\安装的软件\FreeCAD 0.21\bin\FreeCADCmd.exe",
    r"C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe",
    r"C:\Program Files\FreeCAD\bin\FreeCADCmd.exe",
    r"D:\FreeCAD\bin\FreeCADCmd.exe",
]
_NO_WINDOW = 0x08000000

def _hidden_run(cmd, **kw):
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    kw.setdefault('startupinfo', si)
    kw.setdefault('creationflags', _NO_WINDOW)
    return subprocess.run(cmd, **kw)

def _find_tool(paths):
    for p in paths:
        if Path(p).exists(): return p
    return None

def _pkg_ver(name):
    try:
        m = __import__(name)
        return getattr(m, "__version__", "installed")
    except ImportError:
        return None

MATERIALS = {
    "pla": 1240, "petg": 1270, "abs": 1050,
    "tpu": 1200, "nylon": 1140, "resin": 1100,
    "metal_steel": 7800, "metal_aluminum": 2700,
}

def detect_tools():
    tools = {}
    scad = _find_tool(OPENSCAD_SEARCH) or shutil.which("openscad") or shutil.which("openscad.com")
    tools["openscad"] = {"path": scad, "ok": bool(scad)}
    fc = _find_tool(FREECAD_SEARCH) or shutil.which("FreeCADCmd")
    tools["freecad"] = {"path": fc, "ok": bool(fc)}
    for pkg in ["trimesh", "cadquery", "build123d", "numpy", "scipy"]:
        v = _pkg_ver(pkg)
        tools[pkg] = {"ok": v is not None, "version": v or "not installed"}
    # ORS6
    ors6_dir = ROOT_DIR.parent / "ORS6-VAM饮料摇匀器"
    tools["ors6"] = {"ok": (ors6_dir / "sr6_tools.py").exists(), "path": str(ors6_dir)}
    # Quest3
    q3 = ROOT_DIR.parent / "quest3开发"
    tools["quest3"] = {"ok": (q3 / "quest3_hub.py").exists() or (q3 / "quest3_supreme.py").exists()}
    return tools

TOOLS = None  # lazy init

def get_tools():
    global TOOLS
    if TOOLS is None:
        TOOLS = detect_tools()
    return TOOLS


# ═══════════════════════════════════════════════════════
# UNIVERSAL 3D ANALYSIS ENGINE
# Generalized from ORS6 sr6_analyzer — works on ANY STL
# ═══════════════════════════════════════════════════════

def _load_mesh(stl_path):
    import trimesh
    p = Path(stl_path)
    if not p.exists():
        raise FileNotFoundError(f"STL not found: {p}")
    return trimesh.load(str(p))


def cmd_mass(stl_path, material="pla"):
    """Universal mass properties analysis for any STL file."""
    import numpy as np
    t0 = time.time()
    try:
        mesh = _load_mesh(stl_path)
        density = MATERIALS.get(material, 1240)
        density_g_mm3 = density * 1e-6
        is_wt = bool(mesh.is_watertight)
        result = {
            "file": str(stl_path),
            "material": material,
            "density_kg_m3": density,
            "watertight": is_wt,
            "vertices": len(mesh.vertices),
            "faces": len(mesh.faces),
            "surface_area_mm2": round(float(mesh.area), 2),
            "bounding_box_mm": {
                "min": [round(float(v), 3) for v in mesh.bounds[0]],
                "max": [round(float(v), 3) for v in mesh.bounds[1]],
                "size": [round(float(v), 3) for v in mesh.bounding_box.extents],
            },
        }
        if is_wt:
            vol = float(mesh.volume)
            mass_g = vol * density_g_mm3
            com = mesh.center_mass.tolist()
            inertia = mesh.moment_inertia
            eigvals = np.linalg.eigvalsh(inertia)
            result.update({
                "volume_mm3": round(vol, 2),
                "volume_cm3": round(vol / 1000, 3),
                "mass_g": round(mass_g, 2),
                "center_of_mass_mm": [round(v, 3) for v in com],
                "principal_moments": [round(float(v), 4) for v in sorted(eigvals)],
                "fill_ratio": round(vol / float(np.prod(mesh.bounding_box.extents)), 4),
            })
        else:
            bb_vol = float(np.prod(mesh.bounding_box.extents))
            result.update({
                "volume_mm3": None, "mass_g": None,
                "note": "Not watertight — volume/mass approximate",
                "bb_volume_cm3": round(bb_vol / 1000, 3),
            })
        result["time_ms"] = round((time.time() - t0) * 1000, 1)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


def cmd_quality(stl_path):
    """Universal mesh quality check for any STL file."""
    import numpy as np
    t0 = time.time()
    try:
        mesh = _load_mesh(stl_path)
        is_wt = bool(mesh.is_watertight)
        is_wc = bool(mesh.is_winding_consistent)
        areas = mesh.area_faces
        degen = int(np.sum(areas < 1e-10))
        unique_f, counts = np.unique(np.sort(mesh.faces, axis=1), axis=0, return_counts=True)
        dupes = int(np.sum(counts > 1))
        referenced = set(mesh.faces.flatten())
        isolated = len(mesh.vertices) - len(referenced)
        issues = []
        if not is_wt: issues.append("not_watertight")
        if not is_wc: issues.append("winding_inconsistent")
        if degen > 0: issues.append(f"{degen}_degenerate_faces")
        if dupes > 0: issues.append(f"{dupes}_duplicate_faces")
        if isolated > 0: issues.append(f"{isolated}_isolated_vertices")
        grade = "S" if not issues else "A" if len(issues) <= 1 else "B" if len(issues) <= 2 else "C"
        normals = mesh.face_normals
        z = normals[:, 2]
        overhang_mask = z < -0.7071
        overhang_pct = round(float(np.sum(areas[overhang_mask]) / mesh.area * 100), 1) if mesh.area > 0 else 0
        result = {
            "file": str(stl_path), "grade": grade, "issues": issues,
            "watertight": is_wt, "winding_consistent": is_wc,
            "faces": len(mesh.faces), "vertices": len(mesh.vertices),
            "degenerate_faces": degen, "duplicate_faces": dupes,
            "isolated_vertices": isolated,
            "surface_area_mm2": round(float(mesh.area), 2),
            "overhang_pct": overhang_pct,
            "printability": {
                "has_flat_bottom": bool(float(np.sum(areas[np.abs(z + 1) < 0.1])) > 10),
                "overhang_pct": overhang_pct,
                "estimated_material_g": round(float(abs(mesh.volume)) * 1.24e-3, 1) if is_wt else None,
            },
            "time_ms": round((time.time() - t0) * 1000, 1),
        }
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


def cmd_collision(stl1, stl2):
    """Collision detection between two STL files."""
    import trimesh
    t0 = time.time()
    try:
        m1 = _load_mesh(stl1)
        m2 = _load_mesh(stl2)
        mgr = trimesh.collision.CollisionManager()
        mgr.add_object("p1", m1)
        mgr.add_object("p2", m2)
        is_col, names = mgr.in_collision_internal(return_names=True)
        gaps = []
        for ax in range(3):
            gap = max(m2.bounds[0][ax] - m1.bounds[1][ax],
                      m1.bounds[0][ax] - m2.bounds[1][ax])
            gaps.append(float(gap))
        result = {
            "file1": str(stl1), "file2": str(stl2),
            "collision": bool(is_col),
            "bb_gap_mm": round(max(gaps), 3),
            "axis_gaps_mm": {"x": round(gaps[0], 3), "y": round(gaps[1], 3), "z": round(gaps[2], 3)},
            "time_ms": round((time.time() - t0) * 1000, 1),
        }
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


def cmd_clearance(directory):
    """Clearance analysis for all STL pairs in a directory."""
    import itertools
    t0 = time.time()
    d = Path(directory)
    stls = sorted(d.glob("**/*.stl"))
    if len(stls) < 2:
        print(json.dumps({"ok": False, "error": f"Need >=2 STLs, found {len(stls)}"}))
        return 1
    results = []
    for s1, s2 in itertools.combinations(stls[:20], 2):  # cap at 20
        try:
            m1, m2 = _load_mesh(s1), _load_mesh(s2)
            dx = max(0, m2.bounds[0][0]-m1.bounds[1][0], m1.bounds[0][0]-m2.bounds[1][0])
            dy = max(0, m2.bounds[0][1]-m1.bounds[1][1], m1.bounds[0][1]-m2.bounds[1][1])
            dz = max(0, m2.bounds[0][2]-m1.bounds[1][2], m1.bounds[0][2]-m2.bounds[1][2])
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            results.append({
                "parts": [s1.stem, s2.stem],
                "bb_separation_mm": round(dist, 2),
                "bb_overlap": dist < 0.001,
            })
        except Exception as e:
            results.append({"parts": [s1.stem, s2.stem], "error": str(e)})
    out = {
        "directory": str(d), "pairs": len(results),
        "overlapping": sum(1 for r in results if r.get("bb_overlap")),
        "clearances": results,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_assembly(directory):
    """Assembly statistics for all STLs in a directory."""
    import numpy as np
    t0 = time.time()
    d = Path(directory)
    stls = sorted(d.glob("**/*.stl"))
    if not stls:
        print(json.dumps({"ok": False, "error": "No STLs found"}))
        return 1
    parts = []
    all_min, all_max = [], []
    total_faces = 0
    for s in stls:
        try:
            m = _load_mesh(s)
            total_faces += len(m.faces)
            ext = m.bounding_box.extents
            parts.append({
                "name": s.stem, "file": str(s.relative_to(d)),
                "faces": len(m.faces), "vertices": len(m.vertices),
                "center_mm": [round(float(c), 1) for c in m.centroid],
                "size_mm": [round(float(e), 1) for e in ext],
                "watertight": bool(m.is_watertight),
                "volume_cm3": round(float(m.volume) / 1000, 2) if m.is_watertight else None,
            })
            all_min.append(m.bounds[0])
            all_max.append(m.bounds[1])
        except Exception as e:
            parts.append({"name": s.stem, "error": str(e)})
    if all_min:
        amin = np.min(all_min, axis=0)
        amax = np.max(all_max, axis=0)
        asize = amax - amin
    else:
        amin = amax = asize = np.zeros(3)
    result = {
        "directory": str(d),
        "total_parts": len(parts), "total_faces": total_faces,
        "assembly_bbox_mm": {
            "min": [round(float(v), 1) for v in amin],
            "max": [round(float(v), 1) for v in amax],
            "size": [round(float(v), 1) for v in asize],
        },
        "footprint_mm2": round(float(asize[0] * asize[1]), 1),
        "height_mm": round(float(asize[2]), 1),
        "parts": parts,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_section(stl_path, z_mm):
    """Cross-section analysis at given Z height."""
    t0 = time.time()
    try:
        mesh = _load_mesh(stl_path)
        sec = mesh.section(plane_origin=[0, 0, float(z_mm)], plane_normal=[0, 0, 1])
        if sec is None:
            print(json.dumps({"ok": False, "z_mm": z_mm, "note": "No intersection at this Z"}))
            return 1
        b = sec.bounds
        result = {
            "file": str(stl_path), "z_mm": float(z_mm),
            "x_range": [round(float(b[0][0]), 3), round(float(b[1][0]), 3)],
            "y_range": [round(float(b[0][1]), 3), round(float(b[1][1]), 3)],
            "width_x": round(float(b[1][0] - b[0][0]), 3),
            "depth_y": round(float(b[1][1] - b[0][1]), 3),
            "vertices": len(sec.vertices),
            "time_ms": round((time.time() - t0) * 1000, 1),
        }
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


# ═══════════════════════════════════════════════════════
# MODELING COMMANDS
# ═══════════════════════════════════════════════════════

def cmd_cq(code, output=None):
    """Execute CadQuery code inline → STL/STEP."""
    if output is None:
        output = str(_dao_paths.PROJECTS / "temp/output/cq_result.stl")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ext = output.suffix.lower()
    export_line = f"result.val().exportStep(r'{output}')" if ext in (".step", ".stp") else f"result.val().exportStl(r'{output}')"
    script = f"import cadquery as cq\nimport os\nos.makedirs(r'{output.parent}', exist_ok=True)\n{code}\n{export_line}\nprint('Exported:', r'{output}')\n"
    tmp = ROOT_DIR / "_tmp_cq.py"
    tmp.write_text(script, encoding="utf-8")
    t0 = time.time()
    try:
        r = _hidden_run([sys.executable, str(tmp)], capture_output=True, text=True, timeout=60, cwd=str(SCRIPT_DIR))
        ok = output.exists() and output.stat().st_size > 0
        result = {"ok": ok, "output": str(output), "seconds": round(time.time()-t0, 2),
                  "stdout": r.stdout.strip()[:300], "stderr": r.stderr.strip()[:500] if not ok else ""}
        if ok:
            result["size_bytes"] = output.stat().st_size
            try:
                m = _load_mesh(output)
                result["faces"] = len(m.faces)
                result["is_watertight"] = bool(m.is_watertight)
                result["bounds_mm"] = [round(float(b), 2) for b in m.bounding_box.extents]
            except Exception:
                pass
        print(json.dumps(result, indent=2))
        return 0 if ok else 1
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "error": "Timeout after 60s"}))
        return 1
    finally:
        if tmp.exists(): tmp.unlink()


def cmd_b3d(code, output=None):
    """Execute build123d code inline → STL/STEP."""
    if output is None:
        output = str(_dao_paths.PROJECTS / "temp/output/b3d_result.stl")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    export_fn = "export_step" if output.suffix.lower() in (".step", ".stp") else "export_stl"
    script = f"""from build123d import *
import os, build123d as _b
os.makedirs(r'{output.parent}', exist_ok=True)
{code}
_exported = False
for _name in reversed(list(locals().keys())):
    _obj = locals()[_name]
    if hasattr(_obj, 'part') or isinstance(_obj, (_b.Part, _b.Solid, _b.Compound)):
        {export_fn}(_obj.part if hasattr(_obj, 'part') else _obj, r'{output}')
        _exported = True
        print("Exported:", r'{output}')
        break
if not _exported: print("WARNING: No exportable part found.")
"""
    tmp = ROOT_DIR / "_tmp_b3d.py"
    tmp.write_text(script, encoding="utf-8")
    t0 = time.time()
    try:
        r = _hidden_run([sys.executable, str(tmp)], capture_output=True, text=True, timeout=120, cwd=str(SCRIPT_DIR))
        ok = output.exists() and output.stat().st_size > 0
        result = {"ok": ok, "output": str(output), "seconds": round(time.time()-t0, 2),
                  "stdout": r.stdout.strip()[:300], "stderr": r.stderr.strip()[:500] if not ok else ""}
        if ok:
            result["size_bytes"] = output.stat().st_size
        print(json.dumps(result, indent=2))
        return 0 if ok else 1
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "error": "Timeout after 120s"}))
        return 1
    finally:
        if tmp.exists(): tmp.unlink()


def _scad_lib_paths():
    """Discover OpenSCAD library paths (BOSL2, MCAD, etc.)."""
    libs_dir = _dao_paths.WORLD / "网络资源库" / "OpenSCAD_Libraries"
    paths = []
    for d in ("BOSL2", "MCAD", "NopSCADlib", "Round-Anything", "LibSCAD"):
        p = libs_dir / d
        if p.is_dir():
            paths.append(str(p.parent))  # OpenSCAD needs parent so include <BOSL2/std.scad> works
            break  # Only need parent once
    return paths


def cmd_scad(scad_path, stl_out=None, fn=64):
    """OpenSCAD render → STL. Auto-loads BOSL2/MCAD libraries."""
    tools = get_tools()
    scad_exe = tools["openscad"].get("path")
    if not scad_exe:
        print(json.dumps({"ok": False, "error": "OpenSCAD not found"}))
        return 1
    scad_path = Path(scad_path)
    if not scad_path.exists():
        print(json.dumps({"ok": False, "error": f"SCAD not found: {scad_path}"}))
        return 1
    if stl_out is None:
        stl_out = scad_path.with_suffix(".stl")
    stl_out = Path(stl_out)
    stl_out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        cmd = [scad_exe, "-o", str(stl_out.resolve()), "-D", f"$fn={fn}", str(scad_path.resolve())]
        env = os.environ.copy()
        lib_paths = _scad_lib_paths()
        if lib_paths:
            existing = env.get("OPENSCADPATH", "")
            env["OPENSCADPATH"] = os.pathsep.join(lib_paths + ([existing] if existing else []))
        r = _hidden_run(cmd, capture_output=True, timeout=180, env=env)
        ok = stl_out.exists() and stl_out.stat().st_size > 0
        stderr = (r.stderr or b"").decode("utf-8", errors="replace").strip()[:300]
        result = {"ok": ok, "stl": str(stl_out), "seconds": round(time.time()-t0, 2),
                  "size": stl_out.stat().st_size if ok else 0}
        if not ok and stderr:
            result["stderr"] = stderr
        print(json.dumps(result, indent=2))
        return 0 if ok else 1
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "error": "Timeout after 180s"}))
        return 1


def cmd_fc_build(model_type, params_json=None, out_dir=None, formats="stl,step"):
    """Build parametric 3D model via FreeCAD model builder."""
    try:
        from fc_model_builder import FCModelBuilder
    except ImportError as e:
        print(json.dumps({"ok": False, "error": f"fc_model_builder not found: {e}"}))
        return 1
    params = {}
    if params_json:
        try:
            params = json.loads(params_json)
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": f"Invalid JSON params: {e}"}))
            return 1
    fmt_list = [f.strip() for f in formats.split(",")]
    builder = FCModelBuilder()
    if not builder.available():
        print(json.dumps({"ok": False, "error": "FreeCAD not found. Install from freecad.org"}))
        return 1
    t0 = time.time()
    result = builder.build(model_type, params, out_dir=out_dir, formats=fmt_list)
    result["total_s"] = round(time.time() - t0, 2)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result.get("ok") else 1


def cmd_fc_ops(ops_json):
    """Execute raw FreeCAD ops JSON string or file path."""
    try:
        from fc_model_builder import FCModelBuilder
    except ImportError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    p = Path(ops_json)
    if p.exists():
        ops = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(ops, dict):
            ops = ops.get("ops", [])
    else:
        try:
            ops = json.loads(ops_json)
            if isinstance(ops, dict):
                ops = ops.get("ops", [])
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": f"Invalid JSON: {e}"}))
            return 1
    builder = FCModelBuilder()
    result = builder.run_ops(ops, "cli_ops")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result.get("ok") else 1


def cmd_freecad(script_path):
    """Execute FreeCAD headless script."""
    tools = get_tools()
    fc = tools["freecad"].get("path")
    if not fc:
        print(json.dumps({"ok": False, "error": "FreeCAD not installed. Download from freecad.org"}))
        return 1
    script_path = Path(script_path)
    if not script_path.exists():
        print(json.dumps({"ok": False, "error": f"Script not found: {script_path}"}))
        return 1
    t0 = time.time()
    # FreeCAD's internal Python uses GBK on Chinese Windows — copy to temp if non-ASCII path
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
        r = _hidden_run([fc, run_path], capture_output=True, timeout=300)
        stdout = (r.stdout or b"").decode("utf-8", errors="replace").strip()[:500]
        stderr = (r.stderr or b"").decode("utf-8", errors="replace").strip()[:500]
        result = {"ok": r.returncode == 0, "seconds": round(time.time()-t0, 2),
                  "stdout": stdout, "stderr": stderr}
        print(json.dumps(result, indent=2))
        return 0 if r.returncode == 0 else 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), "seconds": round(time.time()-t0, 2)}))
        return 1
    finally:
        if tmp_script and tmp_script.exists():
            tmp_script.unlink(missing_ok=True)


def cmd_convert(input_path, output_path):
    """Convert between 3D formats (STL/STEP/OBJ) via CadQuery/trimesh."""
    inp, out = Path(input_path), Path(output_path)
    if not inp.exists():
        print(json.dumps({"ok": False, "error": f"Input not found: {inp}"}))
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        in_ext, out_ext = inp.suffix.lower(), out.suffix.lower()
        if in_ext == ".stl" and out_ext in (".step", ".stp"):
            from OCP.StlAPI import StlAPI_Reader
            from OCP.TopoDS import TopoDS_Shape
            import cadquery as cq
            reader = StlAPI_Reader()
            shape = TopoDS_Shape()
            reader.Read(shape, str(inp))
            cq.Assembly().add(cq.Shape(shape), name=inp.stem).save(str(out))
        elif in_ext in (".step", ".stp") and out_ext == ".stl":
            import cadquery as cq
            shape = cq.importers.importStep(str(inp))
            cq.exporters.export(shape, str(out))
        else:
            import trimesh
            trimesh.load(str(inp)).export(str(out))
        ok = out.exists() and out.stat().st_size > 0
        print(json.dumps({"ok": ok, "input": str(inp), "output": str(out),
                          "seconds": round(time.time()-t0, 2), "size": out.stat().st_size if ok else 0}, indent=2))
        return 0 if ok else 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


# ═══════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════

def cmd_measure(stl_path):
    """Full geometric measurement report."""
    import numpy as np
    t0 = time.time()
    try:
        mesh = _load_mesh(stl_path)
        ext = mesh.bounding_box.extents
        bbox_vol = float(np.prod(ext))
        normals = mesh.face_normals
        z_n = normals[:, 2]
        overhang_mask = z_n < -0.7071
        report = {
            "file": str(stl_path), "file_size_kb": round(Path(stl_path).stat().st_size/1024, 1),
            "mesh": {"vertices": len(mesh.vertices), "faces": len(mesh.faces)},
            "geometry": {"is_watertight": bool(mesh.is_watertight),
                         "euler_number": int(getattr(mesh, 'euler_number', 0))},
            "dimensions": {"x_mm": round(float(ext[0]), 3), "y_mm": round(float(ext[1]), 3), "z_mm": round(float(ext[2]), 3)},
            "position": {"centroid_mm": [round(float(c), 3) for c in mesh.centroid],
                         "bounds_min": [round(float(b), 3) for b in mesh.bounds[0]],
                         "bounds_max": [round(float(b), 3) for b in mesh.bounds[1]]},
            "volume": {"mesh_mm3": round(float(mesh.volume), 2), "bbox_mm3": round(bbox_vol, 2),
                       "fill_ratio": round(float(mesh.volume)/bbox_vol if bbox_vol > 0 else 0, 4),
                       "surface_area_mm2": round(float(mesh.area), 2)},
            "printability": {"overhang_pct": round(float(np.sum(mesh.area_faces[overhang_mask])/mesh.area*100), 1) if mesh.area > 0 else 0,
                             "estimated_material_g": round(float(mesh.volume)*1.24e-3, 1)},
            "time_ms": round((time.time()-t0)*1000, 1),
        }
        print(json.dumps(report, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


def cmd_compare(stl1, stl2):
    """Compare two STL files with Hausdorff distance + volume + size metrics."""
    import numpy as np
    try:
        m1, m2 = _load_mesh(stl1), _load_mesh(stl2)
        e1, e2 = m1.bounding_box.extents, m2.bounding_box.extents
        n1, n2 = float(np.linalg.norm(e1)), float(np.linalg.norm(e2))
        size_sim = 1.0 - abs(n1-n2)/max(n1, n2, 1)
        v1, v2 = abs(float(m1.volume)), abs(float(m2.volume))
        vol_sim = min(v1, v2)/max(v1, v2, 1)
        f1, f2 = len(m1.faces), len(m2.faces)
        face_sim = min(f1, f2)/max(f1, f2, 1)
        # Hausdorff distance (sampled) — gold-standard 3D shape comparison
        hausdorff = None
        hausdorff_norm = None
        try:
            n_pts = min(5000, len(m1.vertices), len(m2.vertices))
            pts1 = m1.sample(n_pts) if len(m1.faces) > 0 else m1.vertices[:n_pts]
            pts2 = m2.sample(n_pts) if len(m2.faces) > 0 else m2.vertices[:n_pts]
            from scipy.spatial.distance import directed_hausdorff
            h12 = directed_hausdorff(pts1, pts2)[0]
            h21 = directed_hausdorff(pts2, pts1)[0]
            hausdorff = round(max(h12, h21), 4)
            diag = max(n1, n2, 1)
            hausdorff_norm = round(hausdorff / diag, 4)
        except Exception:
            pass
        hausdorff_sim = max(0, 1.0 - (hausdorff_norm or 0.5)) if hausdorff_norm is not None else 0.5
        overall = size_sim*0.2 + vol_sim*0.3 + hausdorff_sim*0.4 + face_sim*0.1
        result = {"file1": str(stl1), "file2": str(stl2),
                  "hausdorff_mm": hausdorff,
                  "hausdorff_normalized": hausdorff_norm,
                  "similarity": {"overall": round(overall, 3), "size": round(size_sim, 3),
                                 "volume": round(vol_sim, 3), "hausdorff": round(hausdorff_sim, 3),
                                 "face_count": round(face_sim, 3)},
                  "verdict": "MATCH" if overall > 0.85 else "SIMILAR" if overall > 0.5 else "DIFFERENT"}
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


def cmd_bom(project_dir):
    """Generate Bill of Materials from all STLs in a project."""
    proj = Path(project_dir)
    stls = sorted(proj.glob("**/*.stl"))
    if not stls:
        print(json.dumps({"ok": False, "error": "No STL files found"}))
        return 1
    bom, total_vol = [], 0
    for stl in stls:
        try:
            m = _load_mesh(stl)
            vol = abs(float(m.volume))
            total_vol += vol
            bom.append({"part": stl.stem, "file": str(stl.relative_to(proj)),
                        "faces": len(m.faces), "volume_mm3": round(vol, 2),
                        "material_g": round(vol*1.24e-3, 1), "watertight": bool(m.is_watertight)})
        except Exception as e:
            bom.append({"part": stl.stem, "error": str(e)})
    total_mat = round(total_vol*1.24e-3, 1)
    print(json.dumps({"project": str(proj), "parts": len(bom), "total_material_g": total_mat, "bom": bom}, indent=2))
    return 0


def cmd_batch(directory, material="pla"):
    """Batch mass + quality analysis for all STLs in a directory."""
    import numpy as np
    t0 = time.time()
    d = Path(directory)
    stls = sorted(d.glob("**/*.stl"))
    if not stls:
        print(json.dumps({"ok": False, "error": "No STL files found"}))
        return 1
    density = MATERIALS.get(material, 1240)
    results = []
    grades = {"S": 0, "A": 0, "B": 0, "C": 0}
    total_mass = 0
    for stl in stls:
        try:
            mesh = _load_mesh(stl)
            is_wt = bool(mesh.is_watertight)
            issues = []
            if not is_wt: issues.append("not_watertight")
            if not mesh.is_winding_consistent: issues.append("winding")
            degen = int(np.sum(mesh.area_faces < 1e-10))
            if degen > 0: issues.append(f"{degen}_degen")
            grade = "S" if not issues else "A" if len(issues) <= 1 else "B" if len(issues) <= 2 else "C"
            grades[grade] = grades.get(grade, 0) + 1
            mass_g = round(float(mesh.volume) * density * 1e-6, 2) if is_wt else None
            if mass_g: total_mass += mass_g
            results.append({
                "part": stl.stem, "file": str(stl.relative_to(d)),
                "faces": len(mesh.faces), "watertight": is_wt,
                "grade": grade, "mass_g": mass_g,
                "size_mm": [round(float(e), 1) for e in mesh.bounding_box.extents],
            })
        except Exception as e:
            results.append({"part": stl.stem, "error": str(e)})
    out = {
        "directory": str(d), "material": material,
        "total_parts": len(results),
        "total_mass_g": round(total_mass, 1),
        "grades": grades,
        "grade_summary": f"{grades.get('S',0)}S {grades.get('A',0)}A {grades.get('B',0)}B {grades.get('C',0)}C",
        "parts": results,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }
    print(json.dumps(out, indent=2))
    return 0


# ═══════════════════════════════════════════════════════
# PRINTABILITY ANALYSIS (migrated + enhanced from forge.py)
# ═══════════════════════════════════════════════════════

_FDM_MIN_WALL = 1.2        # mm minimum wall thickness
_FDM_MAX_OVERHANG = 45     # degrees from horizontal
_FDM_MIN_BED_AREA = 10     # mm² minimum bed contact area
_THICKNESS_SAMPLES = 400   # ray-cast samples (balanced speed/accuracy)


def _pw_wall_thickness(mesh, n_samples=_THICKNESS_SAMPLES):
    """Estimate wall thickness via inward ray casting."""
    import numpy as np
    try:
        n = min(n_samples, len(mesh.faces))
        idx = np.random.choice(len(mesh.faces), size=n, replace=False)
        origins = mesh.triangles_center[idx]
        ray_dirs = -mesh.face_normals[idx]
        origins_off = origins + ray_dirs * 0.01
        locs, ray_idx, _ = mesh.ray.intersects_location(ray_origins=origins_off, ray_directions=ray_dirs)
        if len(locs) == 0:
            return {"min": 0, "max": 0, "mean": 0, "pct_below_min": 100, "samples": n}
        th = []
        for i in range(n):
            hits = locs[ray_idx == i]
            if len(hits) > 0:
                th.append(float(np.min(np.linalg.norm(hits - origins_off[i], axis=1))))
        if not th:
            return {"min": 0, "max": 0, "mean": 0, "pct_below_min": 100, "samples": n}
        arr = np.array(th)
        return {
            "min": round(float(np.min(arr)), 2), "max": round(float(np.max(arr)), 2),
            "mean": round(float(np.mean(arr)), 2), "median": round(float(np.median(arr)), 2),
            "pct_below_min": round(float(np.sum(arr < _FDM_MIN_WALL) / len(arr) * 100), 1),
            "samples": len(th),
        }
    except Exception as e:
        return {"error": str(e), "min": 0, "max": 0, "mean": 0, "pct_below_min": 0, "samples": 0}


def _pw_overhangs(mesh, max_deg=_FDM_MAX_OVERHANG):
    """Analyze overhang faces (angle from horizontal build direction Z-up)."""
    import numpy as np
    try:
        z = mesh.face_normals[:, 2]
        mask = z < -math.cos(math.radians(max_deg))
        areas = mesh.area_faces
        total = float(np.sum(areas))
        oh_area = float(np.sum(areas[mask]))
        return {
            "overhang_faces": int(np.sum(mask)),
            "total_faces": len(mesh.faces),
            "overhang_area_mm2": round(oh_area, 2),
            "pct_area": round(oh_area / total * 100 if total > 0 else 0, 1),
            "threshold_deg": max_deg,
        }
    except Exception as e:
        return {"error": str(e), "overhang_faces": 0, "pct_area": 0}


def _pw_bed_contact(mesh):
    """Analyze print bed contact (bottom flat surface)."""
    import numpy as np
    try:
        z_min = float(mesh.bounds[0][2])
        ctrs = mesh.triangles_center
        normals = mesh.face_normals
        areas = mesh.area_faces
        mask = (ctrs[:, 2] < (z_min + 0.1)) & (normals[:, 2] < -0.9)
        contact_area = float(np.sum(areas[mask]))
        return {
            "area_mm2": round(contact_area, 2),
            "is_flat": contact_area > _FDM_MIN_BED_AREA,
            "z_min_mm": round(z_min, 2),
            "contact_faces": int(np.sum(mask)),
        }
    except Exception as e:
        return {"error": str(e), "area_mm2": 0, "is_flat": False}


def cmd_printability(stl_path, tech="fdm"):
    """Full FDM/SLA printability analysis: wall thickness + overhangs + bed contact."""
    t0 = time.time()
    try:
        mesh = _load_mesh(stl_path)
        issues, warnings = [], []

        wall = _pw_wall_thickness(mesh)
        if "error" not in wall:
            if wall["min"] < _FDM_MIN_WALL and tech == "fdm":
                issues.append(f"Thin wall: {wall['min']:.2f}mm < {_FDM_MIN_WALL}mm")
            if wall["pct_below_min"] > 10:
                warnings.append(f"{wall['pct_below_min']:.0f}% walls below minimum")

        oh = _pw_overhangs(mesh)
        if "error" not in oh and tech == "fdm":
            if oh["pct_area"] > 50:
                issues.append(f"Excessive overhangs: {oh['pct_area']:.0f}%")
            elif oh["pct_area"] > 20:
                warnings.append(f"Significant overhangs: {oh['pct_area']:.0f}% — may need supports")

        bed = _pw_bed_contact(mesh)
        if "error" not in bed and not bed["is_flat"] and tech == "fdm":
            warnings.append(f"Small bed contact: {bed['area_mm2']:.1f}mm² — adhesion risk")

        grade = "S" if not issues and not warnings else "A" if not issues else "B" if len(issues) <= 1 else "C"
        result = {
            "file": str(stl_path), "tech": tech, "grade": grade,
            "printable": grade in ("S", "A"),
            "issues": issues, "warnings": warnings,
            "wall_thickness_mm": wall,
            "overhangs": oh,
            "bed_contact": bed,
            "time_ms": round((time.time() - t0) * 1000, 1),
        }
        print(json.dumps(result, indent=2))
        return 0 if grade in ("S", "A", "B") else 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


def api_printability(stl_path, tech="fdm"):
    """Return printability dict (for HTTP API use)."""
    t0 = time.time()
    mesh = _load_mesh(stl_path)
    issues, warnings = [], []
    wall = _pw_wall_thickness(mesh)
    oh = _pw_overhangs(mesh)
    bed = _pw_bed_contact(mesh)
    if "error" not in wall and wall["min"] < _FDM_MIN_WALL and tech == "fdm":
        issues.append(f"thin_wall:{wall['min']:.2f}mm")
    if "error" not in oh and oh["pct_area"] > 50 and tech == "fdm":
        issues.append(f"overhangs:{oh['pct_area']:.0f}%")
    elif "error" not in oh and oh["pct_area"] > 20 and tech == "fdm":
        warnings.append(f"overhangs:{oh['pct_area']:.0f}%")
    if "error" not in bed and not bed["is_flat"] and tech == "fdm":
        warnings.append(f"bed_contact:{bed['area_mm2']:.1f}mm²")
    grade = "S" if not issues and not warnings else "A" if not issues else "B" if len(issues) <= 1 else "C"
    return {
        "file": str(stl_path), "tech": tech, "grade": grade, "printable": grade in ("S", "A"),
        "issues": issues, "warnings": warnings,
        "wall_thickness_mm": wall, "overhangs": oh, "bed_contact": bed,
        "time_ms": round((time.time() - t0) * 1000, 1),
    }


# ═══════════════════════════════════════════════════════
# PROJECT MANAGEMENT
# ═══════════════════════════════════════════════════════

def cmd_init(project_name):
    """Initialize a new modeling project with standard directory structure."""
    proj = _dao_paths.PROJECTS / project_name
    if proj.exists():
        print(json.dumps({"ok": False, "error": f"Project already exists: {proj}"}))
        return 1
    dirs = ["reference", "parts", "output", "iterations"]
    for d in dirs:
        (proj / d).mkdir(parents=True, exist_ok=True)
    # Create params.json template
    params = {
        "project": project_name,
        "engine": "auto",
        "target_tech": "fdm",
        "parameters": {},
        "notes": ""
    }
    (proj / "params.json").write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
    # Create iteration_log.json
    log = {"project": project_name, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "iterations": []}
    (proj / "iteration_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    result = {"ok": True, "project": project_name, "path": str(proj),
              "dirs": dirs, "files": ["params.json", "iteration_log.json"]}
    print(json.dumps(result, indent=2))
    return 0


def cmd_preview(scad_or_stl, output_dir=None):
    """Generate 4-angle preview PNGs (front/right/top/iso) from SCAD or STL."""
    src = Path(scad_or_stl)
    if not src.exists():
        print(json.dumps({"ok": False, "error": f"Not found: {src}"}))
        return 1
    out_dir = Path(output_dir) if output_dir else src.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # If SCAD, render to STL first
    stl_path = src
    if src.suffix.lower() == ".scad":
        stl_path = out_dir / src.with_suffix(".stl").name
        tools = get_tools()
        scad_exe = tools["openscad"].get("path")
        if not scad_exe:
            print(json.dumps({"ok": False, "error": "OpenSCAD not found for preview"}))
            return 1
        env = os.environ.copy()
        lib_paths = _scad_lib_paths()
        if lib_paths:
            existing = env.get("OPENSCADPATH", "")
            env["OPENSCADPATH"] = os.pathsep.join(lib_paths + ([existing] if existing else []))
        _hidden_run([scad_exe, "-o", str(stl_path.resolve()), "-D", "$fn=64",
                     str(src.resolve())], capture_output=True, timeout=180, env=env)
        if not stl_path.exists():
            print(json.dumps({"ok": False, "error": "OpenSCAD render failed for preview"}))
            return 1

    # Generate 4-angle PNG previews via OpenSCAD --camera or trimesh
    views = {
        "front":  (0, 0, 0, 0, 0, 0),
        "right":  (0, 0, 0, 0, 0, 90),
        "top":    (0, 0, 0, 90, 0, 0),
        "iso":    (0, 0, 0, 25, 0, 35),
    }
    generated = []
    tools = get_tools()
    scad_exe = tools["openscad"].get("path")

    if src.suffix.lower() == ".scad" and scad_exe:
        env = os.environ.copy()
        lib_paths = _scad_lib_paths()
        if lib_paths:
            existing = env.get("OPENSCADPATH", "")
            env["OPENSCADPATH"] = os.pathsep.join(lib_paths + ([existing] if existing else []))
        for vname, (tx, ty, tz, rx, ry, rz) in views.items():
            png = out_dir / f"preview_{vname}.png"
            cmd = [scad_exe, "-o", str(png.resolve()),
                   "--camera", f"{tx},{ty},{tz},{rx},{ry},{rz},0",
                   "--imgsize", "800,600", "-D", "$fn=64",
                   str(src.resolve())]
            try:
                _hidden_run(cmd, capture_output=True, timeout=60, env=env)
                if png.exists() and png.stat().st_size > 100:
                    generated.append(str(png))
            except Exception:
                pass
    else:
        # Fallback: use trimesh scene rendering
        try:
            import trimesh
            import numpy as np
            mesh = trimesh.load(str(stl_path))
            scene = trimesh.Scene(mesh)
            for vname in views:
                png = out_dir / f"preview_{vname}.png"
                try:
                    data = scene.save_image(resolution=(800, 600))
                    if data:
                        png.write_bytes(data)
                        generated.append(str(png))
                except Exception:
                    pass
        except Exception:
            pass

    result = {"ok": len(generated) > 0, "source": str(src),
              "previews": generated, "count": len(generated),
              "seconds": round(time.time() - t0, 2)}
    print(json.dumps(result, indent=2))
    return 0 if generated else 1


def cmd_log(project_dir, iteration_json):
    """Append an iteration record to project's iteration_log.json."""
    proj = Path(project_dir)
    log_file = proj / "iteration_log.json"
    if not log_file.exists():
        print(json.dumps({"ok": False, "error": f"No iteration_log.json in {proj}"}))
        return 1
    try:
        log = json.loads(log_file.read_text(encoding="utf-8"))
        entry = json.loads(iteration_json) if isinstance(iteration_json, str) else iteration_json
        entry["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        entry["iteration"] = len(log.get("iterations", [])) + 1
        log.setdefault("iterations", []).append(entry)
        log_file.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"ok": True, "iteration": entry["iteration"], "total": len(log["iterations"])}))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


def cmd_report(project_dir):
    """Generate Markdown report from project's iteration_log.json."""
    proj = Path(project_dir)
    log_file = proj / "iteration_log.json"
    if not log_file.exists():
        print(json.dumps({"ok": False, "error": f"No iteration_log.json in {proj}"}))
        return 1
    try:
        log = json.loads(log_file.read_text(encoding="utf-8"))
        iters = log.get("iterations", [])
        name = log.get("project", proj.name)
        lines = [f"# ModelForge Report — {name}\n"]
        lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append(f"## Summary\n")
        lines.append(f"- **Iterations**: {len(iters)}")
        if iters:
            last = iters[-1]
            converged = last.get("converged", False)
            lines.append(f"- **Converged**: {'Yes' if converged else 'No'}")
            metrics = last.get("metrics", {})
            for k, v in metrics.items():
                lines.append(f"- **{k}**: {v}")
        lines.append(f"\n## Iteration History\n")
        for it in iters:
            n = it.get("iteration", "?")
            ts = it.get("timestamp", "")
            lines.append(f"### Iteration {n} ({ts})\n")
            if it.get("deviations"):
                lines.append("**Deviations:**")
                for d in it["deviations"]:
                    lines.append(f"- {d}")
            if it.get("fixes"):
                lines.append("\n**Fixes:**")
                for f in it["fixes"]:
                    lines.append(f"- {f}")
            if it.get("metrics"):
                lines.append("\n**Metrics:**")
                for k, v in it["metrics"].items():
                    lines.append(f"- {k}: {v}")
            verdict = it.get("verdict", "")
            if verdict:
                lines.append(f"\n**Verdict**: {verdict}")
            lines.append("")
        # STL inventory
        stls = sorted(proj.glob("**/*.stl"))
        if stls:
            lines.append(f"## Output Files\n")
            for s in stls:
                try:
                    size_kb = round(s.stat().st_size / 1024, 1)
                    lines.append(f"- `{s.relative_to(proj)}` ({size_kb} KB)")
                except Exception:
                    lines.append(f"- `{s.name}`")
        report_md = "\n".join(lines) + "\n"
        report_path = proj / "report.md"
        report_path.write_text(report_md, encoding="utf-8")
        print(json.dumps({"ok": True, "path": str(report_path), "iterations": len(iters),
                          "size": len(report_md)}))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


def cmd_dxf(stl_path, output=None, axis="z"):
    """Project 3D STL to 2D DXF for laser cutting / CNC."""
    import numpy as np
    t0 = time.time()
    src = Path(stl_path)
    if not src.exists():
        print(json.dumps({"ok": False, "error": f"Not found: {src}"}))
        return 1
    out = Path(output) if output else src.with_suffix(".dxf")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        mesh = _load_mesh(stl_path)
        # Project to 2D along specified axis
        axis_map = {"z": (0, 1), "y": (0, 2), "x": (1, 2)}
        ax = axis_map.get(axis.lower(), (0, 1))
        # Get cross-section at midpoint or flatten via convex hull
        try:
            import trimesh
            # Try section at midpoint
            mid = (mesh.bounds[0] + mesh.bounds[1]) / 2
            plane_origin = mid.copy()
            plane_normal = [0, 0, 0]
            axis_idx = {"z": 2, "y": 1, "x": 0}.get(axis.lower(), 2)
            plane_normal[axis_idx] = 1
            section = mesh.section(plane_origin=plane_origin, plane_normal=plane_normal)
            if section is not None:
                path_2d = section.to_2D()[0] if hasattr(section, 'to_2D') else section.to_planar()[0]
                path_2d.export(str(out))
                ok = out.exists() and out.stat().st_size > 0
                result = {"ok": ok, "output": str(out), "axis": axis, "method": "section",
                          "seconds": round(time.time() - t0, 2), "size": out.stat().st_size if ok else 0}
                print(json.dumps(result, indent=2))
                return 0 if ok else 1
        except Exception:
            pass
        # Fallback: 2D convex hull projection
        verts_2d = mesh.vertices[:, list(ax)]
        from scipy.spatial import ConvexHull
        hull = ConvexHull(verts_2d)
        hull_pts = verts_2d[hull.vertices]
        # Write simple DXF
        dxf_lines = ["0\nSECTION\n2\nENTITIES"]
        for i in range(len(hull_pts)):
            p1 = hull_pts[i]
            p2 = hull_pts[(i + 1) % len(hull_pts)]
            dxf_lines.append(f"0\nLINE\n8\n0\n10\n{p1[0]:.4f}\n20\n{p1[1]:.4f}\n30\n0\n11\n{p2[0]:.4f}\n21\n{p2[1]:.4f}\n31\n0")
        dxf_lines.append("0\nENDSEC\n0\nEOF")
        out.write_text("\n".join(dxf_lines), encoding="utf-8")
        ok = out.exists() and out.stat().st_size > 0
        result = {"ok": ok, "output": str(out), "axis": axis, "method": "convex_hull",
                  "hull_vertices": len(hull_pts), "seconds": round(time.time() - t0, 2),
                  "size": out.stat().st_size if ok else 0}
        print(json.dumps(result, indent=2))
        return 0 if ok else 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


# ═══════════════════════════════════════════════════════
# WORKSPACE INTEGRATION
# ═══════════════════════════════════════════════════════

def _probe_workspace_hubs():
    """Discover running Hub services in the workspace."""
    import urllib.request
    hubs = {}
    probes = [
        ("model_hub", 8872, "/api/health"), ("ors6_studio", 8871, "/api/health"),
        ("ors6_tcode", 41927, "/api/health"), ("dao_one", 8880, "/api/health"),
        ("quest3", 8860, "/api/health"), ("agent_arsenal", 8840, "/api/health"),
        ("bambu_lab", 8870, "/api/health"), ("pc_cognitive", 8820, "/api/health"),
    ]
    for name, port, path in probes:
        try:
            r = urllib.request.urlopen(f"http://localhost:{port}{path}", timeout=1)
            hubs[name] = {"port": port, "status": "online", "data": json.loads(r.read())}
        except Exception:
            hubs[name] = {"port": port, "status": "offline"}
    return hubs


# ═══════════════════════════════════════════════════════
# API FUNCTIONS (for model_hub.py to import)
# ═══════════════════════════════════════════════════════

def api_mass(stl_path, material="pla"):
    """Return mass properties dict (for HTTP API use)."""
    import numpy as np
    t0 = time.time()
    mesh = _load_mesh(stl_path)
    density = MATERIALS.get(material, 1240)
    is_wt = bool(mesh.is_watertight)
    result = {"file": str(stl_path), "material": material, "watertight": is_wt,
              "vertices": len(mesh.vertices), "faces": len(mesh.faces),
              "bounding_box_mm": {"size": mesh.bounding_box.extents.tolist()}}
    if is_wt:
        vol = float(mesh.volume)
        result.update({"volume_mm3": round(vol, 2), "mass_g": round(vol*density*1e-6, 2),
                       "center_of_mass_mm": mesh.center_mass.tolist()})
    result["time_ms"] = round((time.time()-t0)*1000, 1)
    return result

def api_quality(stl_path):
    """Return quality check dict (for HTTP API use)."""
    import numpy as np
    t0 = time.time()
    mesh = _load_mesh(stl_path)
    issues = []
    if not mesh.is_watertight: issues.append("not_watertight")
    if not mesh.is_winding_consistent: issues.append("winding_inconsistent")
    degen = int(np.sum(mesh.area_faces < 1e-10))
    if degen > 0: issues.append(f"{degen}_degenerate")
    grade = "S" if not issues else "A" if len(issues) <= 1 else "B"
    return {"file": str(stl_path), "grade": grade, "issues": issues,
            "faces": len(mesh.faces), "time_ms": round((time.time()-t0)*1000, 1)}

def api_examples():
    """Return list of CadQuery examples from local resource library."""
    ex_dir = _dao_paths.WORLD / "网络资源库" / "cadquery" / "examples"
    examples = []
    if ex_dir.is_dir():
        for f in sorted(ex_dir.glob("*.py")):
            try:
                code = f.read_text(encoding="utf-8", errors="replace")[:2000]
                examples.append({"name": f.stem, "file": f.name, "lines": code.count("\n")+1,
                                 "preview": code[:500], "full_code": code})
            except Exception:
                examples.append({"name": f.stem, "file": f.name, "error": "read failed"})
    return {"examples": examples, "count": len(examples), "source": "cadquery/examples"}


def api_resources():
    """Return unified view of all local 3D resources."""
    res_dir = _dao_paths.WORLD / "网络资源库"
    resources = {}
    if res_dir.is_dir():
        # BOSL2
        bosl2 = res_dir / "OpenSCAD_Libraries" / "BOSL2"
        if bosl2.is_dir():
            scads = list(bosl2.glob("*.scad"))
            resources["bosl2"] = {"type": "openscad_lib", "count": len(scads),
                                  "path": str(bosl2), "files": [f.name for f in scads[:20]]}
        # MCAD
        mcad = res_dir / "OpenSCAD_Libraries" / "MCAD"
        if mcad.is_dir():
            scads = list(mcad.glob("*.scad"))
            resources["mcad"] = {"type": "openscad_lib", "count": len(scads),
                                 "path": str(mcad), "files": [f.name for f in scads[:20]]}
        # CadQuery examples
        cq_ex = res_dir / "cadquery" / "examples"
        if cq_ex.is_dir():
            pys = list(cq_ex.glob("*.py"))
            resources["cadquery_examples"] = {"type": "python_examples", "count": len(pys),
                                              "path": str(cq_ex), "files": [f.name for f in pys]}
        # SolidPython
        sp = res_dir / "SolidPython"
        if sp.is_dir():
            resources["solidpython"] = {"type": "python_lib", "path": str(sp)}
    # ORS6 parts
    ors6_dir = ROOT_DIR.parent / "ORS6-VAM饮料摇匀器"
    if (ors6_dir / "sr6_tools.py").exists():
        try:
            if str(ors6_dir) not in sys.path: sys.path.insert(0, str(ors6_dir))
            from sr6_tools import PARTS
            resources["ors6_parts"] = {"type": "stl_parts", "count": len(PARTS)}
        except Exception:
            pass
    # Local projects
    proj_dir = _dao_paths.PROJECTS
    if proj_dir.is_dir():
        projs = [d.name for d in proj_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
        resources["local_projects"] = {"type": "projects", "count": len(projs), "names": projs}
    return {"resources": resources, "total_sources": len(resources)}


def api_collision(stl1, stl2):
    """Return collision check dict (for HTTP API use)."""
    import trimesh
    t0 = time.time()
    m1, m2 = _load_mesh(stl1), _load_mesh(stl2)
    mgr = trimesh.collision.CollisionManager()
    mgr.add_object("p1", m1); mgr.add_object("p2", m2)
    is_col, _ = mgr.in_collision_internal(return_names=True)
    gaps = [max(m2.bounds[0][ax]-m1.bounds[1][ax], m1.bounds[0][ax]-m2.bounds[1][ax]) for ax in range(3)]
    return {"collision": bool(is_col), "bb_gap_mm": round(max(gaps), 3),
            "time_ms": round((time.time()-t0)*1000, 1)}


def cmd_check():
    """Enhanced environment & integration check."""
    tools = get_tools()
    print(f"ModelForge v{VERSION} — Environment Check\n")
    for name, info in tools.items():
        icon = "✅" if info.get("ok") else "❌"
        ver = info.get("version", "")
        path_str = info.get("path", "")
        extra = f" v{ver}" if ver and ver != "not installed" else ""
        extra += f"  ({path_str})" if path_str and info.get("ok") else ""
        print(f"  {icon}  {name}{extra}")
    print("\nWorkspace Hubs:")
    hubs = _probe_workspace_hubs()
    online = sum(1 for h in hubs.values() if h["status"] == "online")
    for name, h in hubs.items():
        icon = "✅" if h["status"] == "online" else "⚪"
        print(f"  {icon}  {name} :{h['port']}")
    print(f"\n  {online}/{len(hubs)} hubs online")
    ors6_dir = ROOT_DIR.parent / "ORS6-VAM饮料摇匀器"
    if (ors6_dir / "sr6_tools.py").exists():
        try:
            if str(ors6_dir) not in sys.path: sys.path.insert(0, str(ors6_dir))
            from sr6_tools import PARTS
            print(f"\n  ✅  ORS6: {len(PARTS)} parts registered")
        except Exception as e:
            print(f"\n  ⚠️   ORS6: {e}")
    res_dir = _dao_paths.WORLD / "网络资源库"
    if res_dir.exists():
        libs = [d.name for d in res_dir.iterdir() if d.is_dir()]
        print(f"\nResource Libraries:")
        bosl2 = res_dir / "OpenSCAD_Libraries" / "BOSL2"
        mcad = res_dir / "OpenSCAD_Libraries" / "MCAD"
        cq_ex = res_dir / "cadquery" / "examples"
        if bosl2.is_dir():
            print(f"  ✅  BOSL2: {len(list(bosl2.glob('*.scad')))} modules")
        if mcad.is_dir():
            print(f"  ✅  MCAD: {len(list(mcad.glob('*.scad')))} modules")
        if cq_ex.is_dir():
            print(f"  ✅  CadQuery Examples: {len(list(cq_ex.glob('*.py')))} examples")
        for d in res_dir.iterdir():
            if d.is_dir() and d.name not in ("OpenSCAD_Libraries", "cadquery"):
                print(f"  ✅  {d.name}")
    print(f"\nForge v{VERSION} check complete.")
    return 0


def cmd_serve(port=8872):
    """Start ModelHub HTTP server."""
    hub = SCRIPT_DIR / "model_hub.py"   # 同层 20-万法_Forge
    if not hub.exists():
        print(f"ERROR: model_hub.py not found")
        return 1
    os.execv(sys.executable, [sys.executable, str(hub), str(port)])


def _run_preflight(arg):
    """Run geometric preflight check via geometric_preflight.py."""
    pf = SCRIPT_DIR / "geometric_preflight.py"   # 同层 20-万法_Forge
    if not pf.exists():
        print(json.dumps({"error": "geometric_preflight.py not found"}))
        return 1
    r = _hidden_run([sys.executable, str(pf), arg], capture_output=True, text=True, timeout=10, cwd=str(SCRIPT_DIR))
    print(r.stdout.strip() if r.stdout else r.stderr.strip())
    return r.returncode


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════
USAGE = f"""ModelForge v{VERSION} — Universal 3D Analysis & Modeling Engine

REVERSE:     reverse <intent> [--download N]  — 反者道之动: search world → rank → adapt
             search-world <query> [--limit N]   — Search all 20 platforms for existing models
             analyze-model <stl|step> [intent]  — Analyze model, compare to intent
FC-REVERSE:  fc_reverse <file>                  — FCStd/STEP/BREP → ops.json (逆向反演)
             fc_probe <file>                    — 完整诊断(几何+ops可达性)
             fc_index [--refresh]               — 扫描天下件 (FreeCAD+projects+网络资源库)
             fc_search <query> [--limit N] [--kind fcstd|step|brep|stl|scad]
             fc_replay <ops.json> [--label L] [--patch k=v,...]
             fc_adapt <file> [k=v ...] [--show] — 反演+改参+重放 (+GUI展示)
FC-SHOW:     fc_launch                          — 启动 FreeCAD GUI + 远程服务器 (18920)
             fc_show <file> [--shots iso,front,top,right]  — 加载+多角度截图 (一键秀)
             fc_load <file>                     — 加载单个到 GUI
             fc_load_many <f1> <f2> ...         — 批量加载 (装配展示)
             fc_shot <name.png>                 — 截屏当前视图 (1920×1080)
             fc_view <isometric|front|top|right|perspective|...>
             fc_clear / fc_close_all            — 清空文档 / 关闭所有
SW-ORIGIN:   sw_info                            — SolidWorks 安装 + COM 诊断
             sw_probe <file.sldprt> [--json]    — 深反 (OLE2, 无需 SW)
             sw_preview <file> [out.png]        — 抽取内嵌预览图
SW-LIVE:     sw_status                          — 运行状态 + 文档列表
             sw_launch                          — 启动 SW GUI + COM 连接
             sw_load <file>                     — 加载到 SW GUI
             sw_show <file> [--shots iso,front,top,right]  — 一键秀 (加载+多角度)
             sw_view <iso|front|top|right|back|bottom|left|trimetric>
             sw_shot <out.png>                  — 截图
             sw_convert <src> <dst> [--fmt step|iges|stl|x_t|dxf]
             sw_export_all <src> <out_dir> [--fmts step,iges,stl,x_t]
             sw_batch <src_dir> <dst_dir> [--fmt step]
             sw_close [--all]
SW-WAY:      sw_health [--json]                 — 环境健康: license/COM/eDrawings/推荐路径
             sw_dialogs [--json]                — 列出 SW/eDrawings 对话框 (分类)
             sw_dismiss [--aggressive|--kinds k1,k2]  — 断更对话框 (默认 safe)
             sw_ed <file> [--out png] [--wait s] [--close] [--no-shot]
                                                — eDrawings 启动 + 窗口截图
             sw_live <file> [--prefer sw_com,edrawings,ole2] [--out-dir D]
                                                — 道法自然 · 多路自动选优活体展示
SW-DEEP:     sw_license [--json]                — L0.5 许可 FlexLM/服务/端口/TSF 诊断
             sw_deep <file> [--json]            — L1.5 深流 carve 特征/配置 (无 SW)
             sw_pe <dll_or_exe> [--exports N]   — L3 PE 头 · 导出名单
             sw_dll [--installdir D] [--max N]  — L3 SW 安装根 DLL 索引
             sw_reg [--values]                  — L4 注册表全景 (roots + 统计)
             sw_docmgr                          — L2.5 SwDocumentMgr COM 只读探测
SW-BREAK:    sw_remediate [--apply] [--no-service] [--enable-disabled]
                                                — L5 一键打通 (regasm + sc start · dry 默)
             sw_docmgr_reg [--apply]            — L5.1 单 regasm SwDocumentMgr
             sw_license_start [--apply] [--enable-disabled]
                                                — L5.2 启 SW Licensing Service
             sw_geom <file> [--max-bytes N]     — L6 几何反演 · Parasolid/BRep/孤儿
SW-ACTIVATE: sw_activate [--apply] [--dispatch] [--no-probe] [--report out.json]
                                                — L9 一键激活: L0.5→L5→COM活检→复诊 (v3.3.0)
             sw_activate_verify [--apply] [--launch] [--test-file F] [--report out.json]
                                                — L9+ 激活 + 真启 SW + 可选 test_file 一张截图
SW-QUARK:    sw_quark_status                    — 夸克网盘桥: CDP/登录/tgt 三态
             sw_quark_find <query> [--limit N]  — 夸克全局搜索文件
             sw_quark_ls [pdir_fid|/path]       — 列夸克目录 (默根)
             sw_quark_locate                    — 定位 SW 资源 (安装包/许可/文档)
             sw_quark_pull <name|path> [dst]    — 按名或路径拉到本机 (70-天下_World/sw/)
             sw_from_quark [--what installer|license|docx|all] [--dst D]
                                                — 一键: 找 SW 资源 + 批量拉下 (道法自然)
             sw_quark_share <share_url> [--passcode P]
                                                — 解析夸克分享链接 → 文件清单
SW-OMEGA:    sw_live_status                     — L11 活体状态 (版本/文档/连接)
             sw_new_part [--template T] [--save-as P]
                                                — 活体新建零件 (可选保存)
             sw_new_assembly [--template T] [--save-as P]
             sw_new_drawing [--template T]
             sw_cmd <id|name> [--title T]       — 触发 SW 内部命令 (swCommands_e)
             sw_list_cmds [--json]              — 列出常用 SW 命令枚举
             sw_macro <path.swp> [--module M] [--proc P]
                                                — 运行 .swp VBA 宏
             sw_prop_set <name> <value> [--config C] [--type TXT|NUM|YN]
             sw_prop_get <name> [--config C]
             sw_prop_all [--config C]           — 当前文档全部自定义属性
             sw_eqn <equation>                  — 追加方程 (如 '\"L\"=100' )
             sw_material <name> [--db DB] [--config C]
             sw_live_snap <out.png> [--view iso|front|top|right|trimetric]
             sw_build_demo [--out D] [--fmt step,stl]
                                                — 活体 demo: 建垫片 + 多视角截图 + 多格式导出
ANALYSIS:    mass quality collision clearance assembly section batch printability
MODELING:    cq b3d scad freecad convert dxf
FREECAD:     fc_build <type> [params_json] [out_dir] [formats]  — Parametric model
             fc_ops <ops_json_or_file>                          — Raw FreeCAD ops
             Types: box cylinder sphere torus tube cone hex_bolt hex_nut washer
                    bracket enclosure gear_spur flange motor_mount standoff spring...
UTILITIES:   measure compare bom check serve
AUDIT:       audit <step_file> [--json]      — Full 8-layer 3D audit (topology→perception)
             audit-dir <dir> [--json]        — Batch audit all STEP files
REASONING:   preflight <json|demo>           — Geometric feasibility pre-check
PROJECT:     init <name>                    — Create project scaffold
             preview <scad|stl> [out_dir]   — 4-angle preview PNGs
             log <proj_dir> '<json>'        — Append iteration record
             report <proj_dir>              — Generate Markdown report
"""

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(USAGE); return 0
    cmd = args[0].lower()
    if cmd == "check":          return cmd_check()
    elif cmd == "mass":         return cmd_mass(args[1], args[2] if len(args)>2 else "pla") if len(args)>1 else print("Usage: mass <stl> [mat]") or 1
    elif cmd == "quality":      return cmd_quality(args[1]) if len(args)>1 else print("Usage: quality <stl>") or 1
    elif cmd == "collision":    return cmd_collision(args[1], args[2]) if len(args)>2 else print("Usage: collision <s1> <s2>") or 1
    elif cmd == "clearance":    return cmd_clearance(args[1]) if len(args)>1 else print("Usage: clearance <dir>") or 1
    elif cmd == "assembly":     return cmd_assembly(args[1]) if len(args)>1 else print("Usage: assembly <dir>") or 1
    elif cmd == "section":      return cmd_section(args[1], float(args[2])) if len(args)>2 else print("Usage: section <stl> <z>") or 1
    elif cmd == "printability": return cmd_printability(args[1], args[2] if len(args)>2 else "fdm") if len(args)>1 else print("Usage: printability <stl> [fdm|sla]") or 1
    elif cmd == "cq":           return cmd_cq(args[1], args[2] if len(args)>2 else None) if len(args)>1 else print("Usage: cq <code> [out]") or 1
    elif cmd == "b3d":          return cmd_b3d(args[1], args[2] if len(args)>2 else None) if len(args)>1 else print("Usage: b3d <code> [out]") or 1
    elif cmd == "scad":         return cmd_scad(args[1], args[2] if len(args)>2 else None, int(args[3]) if len(args)>3 else 64) if len(args)>1 else print("Usage: scad <f> [out] [fn]") or 1
    elif cmd == "freecad":      return cmd_freecad(args[1]) if len(args)>1 else print("Usage: freecad <script>") or 1
    elif cmd == "fc_build":     return cmd_fc_build(args[1], args[2] if len(args)>2 else None, args[3] if len(args)>3 else None, args[4] if len(args)>4 else "stl,step") if len(args)>1 else print("Usage: fc_build <type> [params_json] [out_dir] [formats]") or 1
    elif cmd == "fc_ops":       return cmd_fc_ops(args[1]) if len(args)>1 else print("Usage: fc_ops <ops_json_or_file>") or 1
    elif cmd == "convert":      return cmd_convert(args[1], args[2]) if len(args)>2 else print("Usage: convert <in> <out>") or 1
    elif cmd == "measure":      return cmd_measure(args[1]) if len(args)>1 else print("Usage: measure <stl>") or 1
    elif cmd == "compare":      return cmd_compare(args[1], args[2]) if len(args)>2 else print("Usage: compare <s1> <s2>") or 1
    elif cmd == "bom":          return cmd_bom(args[1]) if len(args)>1 else print("Usage: bom <dir>") or 1
    elif cmd == "batch":        return cmd_batch(args[1], args[2] if len(args)>2 else "pla") if len(args)>1 else print("Usage: batch <dir> [mat]") or 1
    elif cmd == "serve":        return cmd_serve(int(args[1]) if len(args)>1 else 8872)
    elif cmd == "init":         return cmd_init(args[1]) if len(args)>1 else print("Usage: init <project_name>") or 1
    elif cmd == "preview":      return cmd_preview(args[1], args[2] if len(args)>2 else None) if len(args)>1 else print("Usage: preview <scad|stl> [out_dir]") or 1
    elif cmd == "log":          return cmd_log(args[1], args[2]) if len(args)>2 else print("Usage: log <proj_dir> '<json>'") or 1
    elif cmd == "report":       return cmd_report(args[1]) if len(args)>1 else print("Usage: report <proj_dir>") or 1
    elif cmd == "dxf":          return cmd_dxf(args[1], args[2] if len(args)>2 else None, args[3] if len(args)>3 else "z") if len(args)>1 else print("Usage: dxf <stl> [out.dxf] [axis]") or 1
    elif cmd == "audit":        return _cmd_audit(args[1:]) if len(args)>1 else print("Usage: audit <step_file> [--json]") or 1
    elif cmd in ("audit-dir", "audit_dir"): return _cmd_audit_dir(args[1:]) if len(args)>1 else print("Usage: audit-dir <dir> [--json]") or 1
    elif cmd == "preflight":    return _run_preflight(args[1] if len(args)>1 else "demo")
    elif cmd == "reverse":       return _cmd_reverse(args[1:]) if len(args)>1 else print("Usage: reverse <intent> [--download N]") or 1
    elif cmd in ("search-world", "search_world"): return _cmd_search_world(args[1:]) if len(args)>1 else print("Usage: search-world <query> [--limit N]") or 1
    elif cmd in ("analyze-model", "analyze_model"): return _cmd_analyze_model(args[1], args[2] if len(args)>2 else "") if len(args)>1 else print("Usage: analyze-model <stl|step> [intent]") or 1
    elif cmd in ("fc_reverse", "fc-reverse"): return _cmd_fc_reverse(args[1:]) if len(args)>1 else print("Usage: fc_reverse <file>") or 1
    elif cmd in ("fc_probe", "fc-probe"):     return _cmd_fc_probe(args[1:])   if len(args)>1 else print("Usage: fc_probe <file>") or 1
    elif cmd in ("fc_index", "fc-index"):     return _cmd_fc_index(args[1:])
    elif cmd in ("fc_search", "fc-search"):   return _cmd_fc_search(args[1:])  if len(args)>1 else print("Usage: fc_search <query> [--limit N] [--kind K]") or 1
    elif cmd in ("fc_replay", "fc-replay"):   return _cmd_fc_replay(args[1:])  if len(args)>1 else print("Usage: fc_replay <ops.json> [--label L] [--patch k=v,...]") or 1
    elif cmd in ("fc_adapt", "fc-adapt"):     return _cmd_fc_adapt(args[1:])   if len(args)>1 else print("Usage: fc_adapt <file> [k=v ...] [--show]") or 1
    elif cmd in ("fc_launch", "fc-launch"):   return _cmd_fc_launch()
    elif cmd in ("fc_show", "fc-show"):       return _cmd_fc_show(args[1:])    if len(args)>1 else print("Usage: fc_show <file> [--shots iso,front,top,right]") or 1
    elif cmd in ("fc_load", "fc-load"):       return _cmd_fc_load(args[1:])    if len(args)>1 else print("Usage: fc_load <file>") or 1
    elif cmd in ("fc_load_many", "fc-load-many"): return _cmd_fc_load_many(args[1:]) if len(args)>1 else print("Usage: fc_load_many <f1> <f2> ...") or 1
    elif cmd in ("fc_shot", "fc-shot"):       return _cmd_fc_shot(args[1:])    if len(args)>1 else print("Usage: fc_shot <name.png>") or 1
    elif cmd in ("fc_view", "fc-view"):       return _cmd_fc_view(args[1:])    if len(args)>1 else print("Usage: fc_view <isometric|front|top|right|...>") or 1
    elif cmd in ("fc_clear", "fc-clear"):     return _cmd_fc_clear(close_all=False)
    elif cmd in ("fc_close_all", "fc-close-all"): return _cmd_fc_clear(close_all=True)
    # ── 万法 · SolidWorks (反者道之动) ──────────────────────────────
    elif cmd in ("sw_info", "sw-info"):       return _cmd_sw_info()
    elif cmd in ("sw_probe", "sw-probe"):     return _cmd_sw_probe(args[1:])   if len(args)>1 else print("Usage: sw_probe <file.sldprt> [--json]") or 1
    elif cmd in ("sw_preview", "sw-preview"): return _cmd_sw_preview(args[1:]) if len(args)>1 else print("Usage: sw_preview <file> [out.png]") or 1
    elif cmd in ("sw_status", "sw-status"):   return _cmd_sw_status()
    elif cmd in ("sw_launch", "sw-launch"):   return _cmd_sw_launch()
    elif cmd in ("sw_load", "sw-load"):       return _cmd_sw_load(args[1:])    if len(args)>1 else print("Usage: sw_load <file>") or 1
    elif cmd in ("sw_view", "sw-view"):       return _cmd_sw_view(args[1:])    if len(args)>1 else print("Usage: sw_view <iso|front|top|right|back|bottom|left|trimetric>") or 1
    elif cmd in ("sw_shot", "sw-shot"):       return _cmd_sw_shot(args[1:])    if len(args)>1 else print("Usage: sw_shot <out.png>") or 1
    elif cmd in ("sw_show", "sw-show"):       return _cmd_sw_show(args[1:])    if len(args)>1 else print("Usage: sw_show <file> [--shots iso,front,top,right]") or 1
    elif cmd in ("sw_convert", "sw-convert"): return _cmd_sw_convert(args[1:]) if len(args)>2 else print("Usage: sw_convert <src> <dst> [--fmt step]") or 1
    elif cmd in ("sw_export_all", "sw-export-all"): return _cmd_sw_export_all(args[1:]) if len(args)>2 else print("Usage: sw_export_all <src> <out_dir> [--fmts step,iges,stl,x_t]") or 1
    elif cmd in ("sw_batch", "sw-batch"):     return _cmd_sw_batch(args[1:])   if len(args)>2 else print("Usage: sw_batch <src_dir> <dst_dir> [--fmt step]") or 1
    elif cmd in ("sw_close", "sw-close"):     return _cmd_sw_close(args[1:])
    # —— 环境健康 · 对话框 · 道法自然多路选优 (新) ——
    elif cmd in ("sw_health", "sw-health"):   return _cmd_sw_health(args[1:])
    elif cmd in ("sw_dialogs", "sw-dialogs"): return _cmd_sw_dialogs(args[1:])
    elif cmd in ("sw_dismiss", "sw-dismiss"): return _cmd_sw_dismiss(args[1:])
    elif cmd in ("sw_ed", "sw-ed"):           return _cmd_sw_ed(args[1:])
    elif cmd in ("sw_live", "sw-live"):       return _cmd_sw_live(args[1:])    if len(args)>1 else print("Usage: sw_live <file> [--prefer sw_com,edrawings,ole2]") or 1
    # —— 深反新层 (L0.5/L1.5/L2.5/L3/L4) ——
    elif cmd in ("sw_license", "sw-license"): return _cmd_sw_license(args[1:])
    elif cmd in ("sw_deep", "sw-deep"):        return _cmd_sw_deep(args[1:])    if len(args)>1 else print("Usage: sw_deep <file.sldprt> [--json]") or 1
    elif cmd in ("sw_pe", "sw-pe"):            return _cmd_sw_pe(args[1:])       if len(args)>1 else print("Usage: sw_pe <dll_or_exe> [--exports N]") or 1
    elif cmd in ("sw_dll", "sw-dll"):          return _cmd_sw_dll(args[1:])
    elif cmd in ("sw_reg", "sw-reg"):          return _cmd_sw_reg(args[1:])
    elif cmd in ("sw_docmgr", "sw-docmgr"):    return _cmd_sw_docmgr(args[1:])
    # —— L5 / L6 · 打通 / 几何反演 ——
    elif cmd in ("sw_remediate", "sw-remediate"): return _cmd_sw_remediate(args[1:])
    elif cmd in ("sw_docmgr_reg", "sw-docmgr-reg", "sw_docmgr-register"):
                                              return _cmd_sw_docmgr_reg(args[1:])
    elif cmd in ("sw_license_start", "sw-license-start"):
                                              return _cmd_sw_license_start(args[1:])
    elif cmd in ("sw_geom", "sw-geom"):        return _cmd_sw_geom(args[1:])     if len(args)>1 else print("Usage: sw_geom <file.sldprt> [--max-bytes N] [--json]") or 1
    # —— L9 · 一键激活 (v3.3.0) + SW × 夸克网盘桥 ——
    elif cmd in ("sw_activate", "sw-activate"):          return _cmd_sw_activate(args[1:])
    elif cmd in ("sw_activate_verify", "sw-activate-verify",
                 "sw_activate-verify"):                   return _cmd_sw_activate_verify(args[1:])
    elif cmd in ("sw_quark_status", "sw-quark-status"):   return _cmd_sw_quark_status()
    elif cmd in ("sw_quark_find", "sw-quark-find"):       return _cmd_sw_quark_find(args[1:])     if len(args)>1 else print("Usage: sw_quark_find <query> [--limit N]") or 1
    elif cmd in ("sw_quark_ls", "sw-quark-ls"):           return _cmd_sw_quark_ls(args[1:])
    elif cmd in ("sw_quark_locate", "sw-quark-locate"):   return _cmd_sw_quark_locate()
    elif cmd in ("sw_quark_pull", "sw-quark-pull"):       return _cmd_sw_quark_pull(args[1:])     if len(args)>1 else print("Usage: sw_quark_pull <name|path> [dst_dir]") or 1
    elif cmd in ("sw_from_quark", "sw-from-quark"):       return _cmd_sw_from_quark(args[1:])
    elif cmd in ("sw_quark_share", "sw-quark-share"):     return _cmd_sw_quark_share(args[1:])   if len(args)>1 else print("Usage: sw_quark_share <share_url> [--passcode P]") or 1
    # —— SW-OMEGA · L11 活体万象 (v4.0) ——
    elif cmd in ("sw_live_status", "sw_new_part", "sw_new_assembly",
                 "sw_new_drawing", "sw_cmd", "sw_list_cmds", "sw_macro",
                 "sw_prop_set", "sw_prop_get", "sw_prop_all", "sw_eqn",
                 "sw_material", "sw_live_snap", "sw_build_demo",
                 "sw-live-status", "sw-new-part", "sw-new-assembly",
                 "sw-new-drawing", "sw-cmd", "sw-list-cmds", "sw-macro",
                 "sw-prop-set", "sw-prop-get", "sw-prop-all", "sw-eqn",
                 "sw-material", "sw-live-snap", "sw-build-demo"):
        from forge_sw_omega import dispatch as _omega_dispatch
        _rc = _omega_dispatch(cmd, args[1:])
        return 1 if _rc is None else int(_rc)
    else:
        print(f"Unknown command: {cmd}\n{USAGE}"); return 1


def _cmd_audit(args):
    """Full 8-layer audit for a STEP file."""
    from dao_audit import full_audit, _print_audit
    from dao_kernel import DaoKernel as AK
    step_file = args[0]
    json_out = "--json" in args
    t = Path(step_file)
    if not t.exists():
        print(f"File not found: {step_file}"); return 1
    shape = AK.from_step(str(t))
    result = full_audit(shape, name=t.stem)
    if json_out:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        print("  道 · Full 8-Layer Audit")
        print("=" * 70)
        _print_audit(result, verbose=True)
        if result.get('layers'):
            print()
            for layer in result['layers']:
                ln = layer.get('name', '?')
                lg = layer.get('grade', '?')
                ls = layer.get('score', 0)
                print(f"    Layer {layer['layer']}: {ln:<12} {lg} ({ls:.0f})")
        print(f"\n  Total: {result.get('total_time_ms', 0):.0f}ms")
        print("=" * 70)
    return 0


def _cmd_audit_dir(args):
    """Batch audit all STEP files in a directory."""
    from dao_audit import batch_audit
    d = args[0]
    json_out = "--json" in args
    result = batch_audit(d)
    if json_out:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        print(f"  Batch Audit: {d}")
        print(f"  Parts: {result.get('parts', 0)}  Avg: {result.get('avg_score', 0):.0f}  Grade: {result.get('overall_grade', '?')}")
        print("=" * 70)
        for r in result.get('results', []):
            name = r.get('name', '?')
            grade = r.get('grade', '?')
            score = r.get('score', 0)
            print(f"  {name:<20} {grade} ({score:.0f})")
        print("=" * 70)
    return 0


def _cmd_reverse(args):
    """反者道之动 — 完整反向流水线"""
    from dao_reverse import DaoReverse
    dl = 0
    if "--download" in args:
        idx = args.index("--download")
        dl = int(args[idx+1]) if idx+1 < len(args) else 3
        args = args[:idx] + args[idx+2:]
    query = " ".join(args)
    result = DaoReverse.fulfill(query, download_top=dl)
    print(json.dumps(result.get("cascade_protocol", {}), ensure_ascii=False, indent=2))
    return 0


def _cmd_search_world(args):
    """搜索天下已有模型"""
    from dao_reverse import DaoReverse
    limit = 20
    if "--limit" in args:
        idx = args.index("--limit")
        limit = int(args[idx+1]) if idx+1 < len(args) else 20
        args = args[:idx] + args[idx+2:]
    query = " ".join(args)
    results = DaoReverse.search(query, limit)
    for i, r in enumerate(results[:limit]):
        print(f"  #{i+1:2d} [{r.get('platform',''):12s}] {r.get('name','?')[:45]}")
        print(f"       ↓{r.get('downloads',0):6d} ♥{r.get('likes',0):5d}  {r.get('url','')[:55]}")
    return 0


def _cmd_analyze_model(path, intent=""):
    """分析本地模型"""
    from dao_reverse import DaoReverse
    result = DaoReverse.analyze_local(path, intent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


# ═══════════════════════════════════════════════════════
# FC-REVERSE 反者 — 从 FreeCAD 件逆向突破
# ═══════════════════════════════════════════════════════

def _parse_kv_pairs(args):
    """把 'a=1 b=2 c=3' 的参数列表转成 dict (带 float 尝试)."""
    out = {}
    for a in args:
        if "=" not in a:
            continue
        k, v = a.split("=", 1)
        try:
            out[k.strip()] = float(v.strip())
        except ValueError:
            out[k.strip()] = v.strip()
    return out


def _cmd_fc_reverse(args):
    """逆向 FCStd/STEP/BREP → ops.json (打印到stdout)."""
    from fc_reverse import FCReverse
    result = FCReverse.reverse(args[0])
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


def _cmd_fc_probe(args):
    """完整诊断: 几何 + ops 可达性 + 警告."""
    from fc_reverse import FCReverse
    r = FCReverse.probe(args[0])
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cmd_fc_index(args):
    """扫描天下件 → 索引."""
    from fc_reverse import FCReverse, INDEX_FILE
    refresh = "--refresh" in args
    idx = FCReverse.index(refresh=refresh)
    summary = {
        "version": idx.get("version"),
        "generated_at": idx.get("generated_at"),
        "elapsed_s": idx.get("elapsed_s"),
        "total": idx.get("total"),
        "by_root": idx.get("by_root"),
        "by_kind": idx.get("by_kind"),
        "file": str(INDEX_FILE),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_fc_search(args):
    """从索引搜索资源."""
    from fc_reverse import FCReverse
    limit = 20
    kind = None
    q_parts = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2; continue
        if a == "--kind" and i + 1 < len(args):
            kind = args[i + 1]; i += 2; continue
        q_parts.append(a); i += 1
    query = " ".join(q_parts)
    hits = FCReverse.search(query, limit=limit, kind=kind)
    out = {
        "query": query, "count": len(hits),
        "hits": [
            {"kind": h["kind"], "root": h["root"], "stem": h["stem"],
             "size_kb": round(h["size_bytes"] / 1024, 1), "path": h["path"]}
            for h in hits
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_fc_replay(args):
    """重放 ops.json (可带 --patch)."""
    from fc_reverse import FCReverse
    ops_path = Path(args[0])
    if not ops_path.exists():
        print(json.dumps({"ok": False, "error": f"not found: {ops_path}"}))
        return 1
    data = json.loads(ops_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "ops" in data:
        ops = data["ops"]; label = data.get("label", ops_path.stem)
    else:
        ops = data; label = ops_path.stem
    patch = {}
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--label" and i + 1 < len(args):
            label = args[i + 1]; i += 2; continue
        if a == "--patch" and i + 1 < len(args):
            patch.update(_parse_kv_pairs(args[i + 1].split(",")))
            i += 2; continue
        i += 1
    if patch:
        ops = FCReverse.patch(ops, patch)
    result = FCReverse.replay(ops, label=label)
    print(json.dumps({
        "ok": result.get("ok"), "label": label,
        "op_count": len(ops), "patch": patch,
        "errors": result.get("errors", []),
        "exports": result.get("exports", []),
        "elapsed_s": result.get("elapsed_s"),
    }, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_fc_adapt(args):
    """一键适配: 反演+改参+重放 (+GUI展示)."""
    from fc_reverse import FCReverse
    show_flag = "--show" in args
    args = [a for a in args if a != "--show"]
    src = args[0]
    patch = _parse_kv_pairs(args[1:])
    result = FCReverse.adapt(src, patch=patch)
    out = {
        "ok": result.get("ok"), "stage": result.get("stage"),
        "source": src, "patch": patch,
        "reverse_meta": result.get("reverse", {}),
        "replay": {k: v for k, v in result.get("replay", {}).items()
                   if k not in ("shapes",)},
    }
    # --show: 改参后的 STEP/STL 送到 FreeCAD GUI
    if show_flag and result.get("ok"):
        try:
            from fc_show import FCShow
            exports = result.get("replay", {}).get("exports", [])
            step = next((e["path"] for e in exports if e.get("op") == "export_step"), None)
            target = step or (exports[0]["path"] if exports else None)
            if target:
                show_r = FCShow.live_show(target,
                                          shots=["isometric", "front", "top", "right"])
                out["gui_show"] = {
                    "ok": show_r.get("ok"),
                    "shot_dir": show_r.get("shot_dir"),
                    "shots": [{"view": s["view"], "path": s.get("path")}
                              for s in show_r.get("shots", [])],
                }
        except Exception as e:
            out["gui_show"] = {"ok": False, "error": str(e)}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


# ═══════════════════════════════════════════════════════
# FC-SHOW 笙用 — FreeCAD GUI 天生展示台
# ═══════════════════════════════════════════════════════

def _cmd_fc_launch():
    """启动 FreeCAD GUI + 远程服务器 (端口 18920)."""
    from fc_show import FCShow
    r = FCShow.ensure_gui()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cmd_fc_show(args):
    """一键秀: 加载+多角度截图 (默认 iso/front/top/right)."""
    from fc_show import FCShow
    file_path = args[0]
    shots = ["isometric", "front", "top", "right"]
    i = 1
    while i < len(args):
        if args[i] == "--shots" and i + 1 < len(args):
            shots = [s.strip() for s in args[i + 1].split(",") if s.strip()]
            i += 2; continue
        i += 1
    r = FCShow.live_show(file_path, shots=shots)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cmd_fc_load(args):
    """加载单个到 GUI."""
    from fc_show import FCShow
    r = FCShow.load(args[0])
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cmd_fc_load_many(args):
    """批量加载 (装配展示)."""
    from fc_show import FCShow
    r = FCShow.load_many(args)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0 if r.get("ok") else 1


def _cmd_fc_shot(args):
    """截屏当前视图 → PNG."""
    from fc_show import FCShow
    r = FCShow.screenshot(args[0])
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cmd_fc_view(args):
    """视图 (isometric/front/top/right/home/perspective/orthographic...)."""
    from fc_show import FCShow
    r = FCShow.view(args[0])
    FCShow.fit()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def _cmd_fc_clear(close_all=False):
    """清空当前文档 (或关闭所有)."""
    from fc_show import FCShow
    r = FCShow.clear(close_all=close_all)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


# ═════════════════════════════════════════════════════════════════════
# 万法 · SolidWorks 命令族 · 反者道之动
# ═════════════════════════════════════════════════════════════════════
def _cmd_sw_info():
    """显示 SolidWorks 安装信息 + COM 状态."""
    import dao_solidworks as _sw
    info = _sw.sw_info(probe_com=True)
    print(json.dumps(info.to_dict(), ensure_ascii=False, indent=2))
    return 0 if info.installed else 1


def _cmd_sw_probe(args):
    """深反 SLDPRT (无需 SW). JSON 输出含所有流/元数据."""
    import dao_solidworks as _sw
    file = args[0]
    json_out = "--json" in args
    meta = _sw.probe_file(file)
    if json_out:
        print(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"file:     {meta.get('path')}")
        print(f"ok:       {meta.get('ok')}")
        print(f"doc_type: {meta.get('doc_type')}")
        print(f"size:     {meta.get('size_MB')} MB")
        print(f"streams:  {len(meta.get('streams', []))}")
        print(f"storages: {len(meta.get('storages', []))}")
        sm = meta.get("summary", {})
        if sm:
            print("summary:")
            for k in ("title","author","last_author","created","last_saved","app_name"):
                if k in sm: print(f"  {k:15s} {sm[k]}")
        if meta.get("preview"):   print(f"preview:  {meta['preview']}")
        if meta.get("step_proxy"):print(f"step_proxy: {meta['step_proxy']}")
        if meta.get("hints"):     print(f"hints:    {meta['hints']}")
    return 0 if meta.get("ok") else 1


def _cmd_sw_preview(args):
    """抽取 SLDPRT 内嵌预览 → PNG."""
    import dao_solidworks as _sw
    src = args[0]
    out = args[1] if len(args) > 1 else str(Path(src).with_suffix(".preview.png"))
    data = _sw.extract_preview(src, out)
    if data:
        print(f"saved: {out} ({len(data):,} B)")
        return 0
    print("no preview found")
    return 1


def _cmd_sw_status():
    from sw_show import SWShow
    sw = SWShow()
    st = sw.status()
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


def _cmd_sw_launch():
    from sw_show import SWShow
    sw = SWShow()
    try:
        sw.ensure_gui(visible=True, launch_timeout_s=120.0)
        print(json.dumps(sw.status(), ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(f"launch failed: {e}")
        return 1


def _cmd_sw_load(args):
    from sw_show import SWShow
    sw = SWShow()
    try:
        doc = sw.load(args[0])
        print(json.dumps({
            "ok": True, "path": doc.path_name(),
            "type": __import__("dao_solidworks").SW_DOC_TYPE.name(doc.doc_type),
            "configs": doc.configurations(),
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "err": str(e)}, ensure_ascii=False))
        return 1


def _cmd_sw_view(args):
    from sw_show import SWShow
    sw = SWShow()
    try:
        r = sw.view(args[0])
        sw.fit()
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("ok") else 1
    except Exception as e:
        print(json.dumps({"ok": False, "err": str(e)}, ensure_ascii=False))
        return 1


def _cmd_sw_shot(args):
    from sw_show import SWShow
    sw = SWShow()
    try:
        p = sw.screenshot(args[0])
        print(json.dumps({"ok": True, "path": str(p),
                          "size_B": p.stat().st_size},
                         ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "err": str(e)}, ensure_ascii=False))
        return 1


def _cmd_sw_show(args):
    """一键秀: 加载 + 多角度截图."""
    from sw_show import SWShow
    file = args[0]
    shots = ["isometric", "front", "top", "right"]
    out_dir = None
    if "--shots" in args:
        i = args.index("--shots")
        if i + 1 < len(args):
            shots = [s.strip() for s in args[i+1].split(",") if s.strip()]
    if "--out-dir" in args:
        i = args.index("--out-dir")
        if i + 1 < len(args):
            out_dir = args[i+1]
    sw = SWShow()
    try:
        r = sw.live_show(file, shots=shots, out_dir=out_dir)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "err": str(e)}, ensure_ascii=False))
        return 1


def _cmd_sw_convert(args):
    """SW COM 导出 src → dst."""
    from sw_show import SWShow
    import dao_solidworks as _sw
    src, dst = args[0], args[1]
    fmt = None
    if "--fmt" in args:
        i = args.index("--fmt")
        if i + 1 < len(args): fmt = args[i+1]
    sw = SWShow()
    try:
        sw.ensure_gui(visible=False)
        doc = sw.load(src, readonly=True)
        p = sw.save_as(doc, dst, fmt=fmt)
        print(json.dumps({"ok": True, "src": src, "dst": str(p),
                          "size_B": p.stat().st_size},
                         ensure_ascii=False, indent=2))
        sw.close()
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "err": str(e)}, ensure_ascii=False))
        return 1


def _cmd_sw_export_all(args):
    """一次性导出多种格式."""
    from sw_show import SWShow
    src, out_dir = args[0], args[1]
    fmts = ["step", "iges", "stl", "x_t"]
    if "--fmts" in args:
        i = args.index("--fmts")
        if i + 1 < len(args):
            fmts = [s.strip() for s in args[i+1].split(",") if s.strip()]
    sw = SWShow()
    try:
        sw.ensure_gui(visible=False)
        doc = sw.load(src, readonly=True)
        r = sw.export_all(doc, out_dir, fmts=fmts)
        sw.close()
        print(json.dumps({"src": src, "out_dir": out_dir, "results": r},
                         ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "err": str(e)}, ensure_ascii=False))
        return 1


def _cmd_sw_batch(args):
    """批量 SLDPRT → 目标格式."""
    import dao_solidworks as _sw
    src_dir, dst_dir = args[0], args[1]
    fmt = "step"
    if "--fmt" in args:
        i = args.index("--fmt")
        if i + 1 < len(args): fmt = args[i+1]
    bridge = _sw.SolidWorksBridge()
    try:
        bridge.connect(launch_if_needed=True)
        outs = bridge.batch_convert(src_dir, dst_dir, fmt=fmt)
        print(json.dumps({"ok": True, "n": len(outs),
                          "dst_dir": dst_dir,
                          "files": [str(p) for p in outs[:20]]},
                         ensure_ascii=False, indent=2))
        bridge.disconnect()
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "err": str(e)}, ensure_ascii=False))
        return 1


def _cmd_sw_close(args):
    from sw_show import SWShow
    sw = SWShow()
    close_all = "--all" in args
    try:
        sw.close(close_all=close_all)
        print(json.dumps({"ok": True}, ensure_ascii=False))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "err": str(e)}, ensure_ascii=False))
        return 1


# ═════════════════════════════════════════════════════════════════════
# 万法 · SolidWorks 环境健康 · 道法自然多路选优 (新)
# ═════════════════════════════════════════════════════════════════════

def _cmd_sw_health(args):
    """SW 环境健康 · license/COM/eDrawings/推荐路径."""
    import dao_solidworks as _sw
    json_out = "--json" in args
    no_scan = "--no-scan" in args
    h = _sw.SWHealthCheck.check(scan_dialogs=not no_scan)
    if json_out:
        print(json.dumps(h, ensure_ascii=False, indent=2, default=str))
        return 0
    print("═" * 60)
    print(f"  SolidWorks 环境健康检查 · 道法自然")
    print("═" * 60)
    ins = h["install"]
    print(f"  installed:     {ins['installed']}  ({ins['version']})")
    print(f"  progid:        {ins['progid']}")
    print(f"  exe:           {ins['exe']}")
    print(f"  pywin32:       {ins['pywin32_ok']}")
    print(f"  sw_processes:  {h['running']}")
    print(f"  com_ready:     {h['com_ready']}")
    print(f"    reason:      {h.get('com_msg','')}")
    print(f"  license_ok:    {h['license_ok']}")
    print(f"  dialogs ({len(h['dialogs'])}):")
    for d in h["dialogs"]:
        print(f"    [{d['kind']:14s}] pid={d['pid']} {d['title']!r}")
    ed = h["edrawings"]
    print(f"  edrawings_exe: {ed['exe']}")
    print(f"  edrawings_com: {ed['com']}  {ed.get('msg','')}")
    print(f"  ─────────────────────────────────────────────")
    print(f"  推荐路径:      {h['recommendation']}")
    print("═" * 60)
    return 0


def _cmd_sw_dialogs(args):
    """列出所有 SW/eDrawings 可见对话框 (分类)."""
    import dao_solidworks as _sw
    ds = _sw.SWDialogHandler.scan()
    json_out = "--json" in args
    if json_out:
        clean = [{k: v for k, v in d.items() if k != "buttons"}
                  for d in ds]
        print(json.dumps(clean, ensure_ascii=False, indent=2,
                          default=str))
        return 0
    print(f"visible dialogs: {len(ds)}")
    for d in ds:
        print(f"\n  [{d['kind']}] hwnd=0x{d['hwnd']:08x} pid={d['pid']}")
        print(f"    title:   {d['title']!r}")
        if d["children"]:
            print(f"    children:")
            for cls_name, text in d["children"][:10]:
                print(f"      [{cls_name}] {text!r}")
        if d["buttons"]:
            print(f"    buttons: {[t for _, t in d['buttons']]}")
    return 0


def _cmd_sw_dismiss(args):
    """断更 SW/eDrawings 对话框. 默认 SAFE: welcome+tip."""
    import dao_solidworks as _sw
    kinds = ("welcome", "tip")
    if "--aggressive" in args:
        kinds = ("welcome", "tip", "license_error", "unknown")
    if "--kinds" in args:
        i = args.index("--kinds")
        if i + 1 < len(args):
            kinds = tuple(s.strip() for s in args[i+1].split(",")
                          if s.strip())
    r = _sw.SWDialogHandler.dismiss(kinds=kinds)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_sw_ed(args):
    """eDrawings.exe 启动 + 窗口截图."""
    import dao_solidworks as _sw
    file_arg = args[0] if args and not args[0].startswith("-") else None
    out = None
    wait = 15.0
    close_after = "--close" in args
    no_shot = "--no-shot" in args
    if "--out" in args:
        i = args.index("--out")
        if i + 1 < len(args): out = args[i+1]
    if "--wait" in args:
        i = args.index("--wait")
        if i + 1 < len(args):
            try: wait = float(args[i+1])
            except ValueError: pass
    ed = _sw.EDrawingsLauncher()
    if not ed.is_available():
        print(json.dumps({"ok": False, "err": "eDrawings.exe not found"}))
        return 1
    pid = ed.launch(file_arg)
    result = {"ok": True, "pid": pid, "exe": ed.exe, "file": file_arg}
    if not no_shot:
        from pathlib import Path as _P
        default = (_P(file_arg).parent / f"{_P(file_arg).stem}_edrawings.png"
                   if file_arg else _P.cwd() / "edrawings.png")
        tgt = _P(out) if out else default
        p = ed.snap(tgt, wait_s=wait)
        if p:
            result["screenshot"] = str(p)
            result["screenshot_size"] = p.stat().st_size
        else:
            result["screenshot"] = None
            result["err"] = "main window not found"
    if close_after:
        ed.close()
        result["closed"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_sw_live(args):
    """道法自然 · 多路自动选优活体展示."""
    import dao_solidworks as _sw
    file = args[0]
    prefer = ("sw_com", "edrawings", "ole2")
    out_dir = None
    no_shot = "--no-shot" in args
    no_dismiss = "--no-dismiss" in args
    if "--prefer" in args:
        i = args.index("--prefer")
        if i + 1 < len(args):
            prefer = tuple(s.strip() for s in args[i+1].split(",")
                            if s.strip())
    if "--out-dir" in args:
        i = args.index("--out-dir")
        if i + 1 < len(args): out_dir = args[i+1]
    r = _sw.live_show(file, out_dir=out_dir, prefer=prefer,
                      screenshot=not no_shot,
                      dismiss_dialogs=not no_dismiss)
    print("═" * 60)
    print(f"  live_show · {Path(file).name}")
    print("═" * 60)
    print(f"  path_used:      {r['path_used']}")
    print(f"  recommendation: {r['health']['recommendation']}")
    print(f"  license_ok:     {r['health']['license_ok']}")
    print(f"  com_ready:      {r['health']['com_ready']}")
    print(f"  artifacts ({len(r['artifacts'])}):")
    for art in r["artifacts"]:
        sz = Path(art["path"]).stat().st_size if Path(art["path"]).exists() else 0
        print(f"    [{art['kind']:20s}] {art['path']}  ({sz:,} B)")
    if r["errors"]:
        print(f"  errors:")
        for e in r["errors"]:
            print(f"    - {e}")
    print("═" * 60)
    return 0


# ═════════════════════════════════════════════════════════════════════
# 万法 · SolidWorks 深反新层 (L0.5/L1.5/L2.5/L3/L4)
# ═════════════════════════════════════════════════════════════════════

def _cmd_sw_license(args):
    """L0.5 · SW 许可系统诊断 (FlexLM/服务/端口/TSF/事件)."""
    import dao_solidworks as _sw
    json_out = "--json" in args
    s = _sw.sw_license_diagnose()
    d = s.to_dict() if hasattr(s, "to_dict") else dict(s)
    if json_out:
        print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
        return 0
    print("═" * 60)
    print(f"  L0.5 · SolidWorks 许可诊断 · severity={d.get('severity')}")
    print("═" * 60)
    print(f"  findings ({len(d.get('findings', []))}):")
    for f in d.get("findings", []):
        print(f"    · {f}")
    print(f"  ports:")
    for p, ok in (d.get("ports") or {}).items():
        print(f"    {p:6d}  {'OPEN' if ok else 'closed'}")
    print("═" * 60)
    return 0


def _cmd_sw_deep(args):
    """L1.5 · 深流 carve + OLE2 深反 (无需 SW)."""
    import dao_solidworks as _sw
    file = args[0]
    json_out = "--json" in args
    dp = _sw.deep_probe_file(file)
    if json_out:
        print(json.dumps(dp, ensure_ascii=False, indent=2, default=str))
        return 0 if dp.get("ok") else 1
    print(f"file:      {dp.get('path')}")
    print(f"ok:        {dp.get('ok')}")
    print(f"doc_type:  {dp.get('doc_type')}")
    print(f"size:      {dp.get('size_MB')} MB")
    feats = dp.get("feature_names_carved", [])
    cfgs = dp.get("config_names_carved", [])
    print(f"n_features: {len(feats)}")
    print(f"n_configs:  {len(cfgs)}")
    print(f"stream_highlights:")
    for nm, info in (dp.get("stream_highlights", {}) or {}).items():
        print(f"  {nm:24s} size={info['size_B']:>10,}B  names={info['n_names_found']}")
    print(f"first feature names (top 10):")
    for s in feats[:10]:
        print(f"  · {s}")
    return 0 if dp.get("ok") else 1


def _cmd_sw_pe(args):
    """L3 · PE 头 · 导出名单."""
    import dao_solidworks as _sw
    target = args[0]
    limit = 20
    if "--exports" in args:
        i = args.index("--exports")
        if i + 1 < len(args):
            try: limit = int(args[i+1])
            except ValueError: pass
    try:
        with _sw.PEReader(target) as pe:
            s = pe.summary()
            exps = pe.exports(limit=limit)
    except Exception as e:
        print(json.dumps({"ok": False, "err": f"{type(e).__name__}: {e}"}))
        return 1
    print(json.dumps({
        "path": str(target),
        "summary": s,
        "exports": exps,
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_sw_dll(args):
    """L3 · SW 安装根 DLL 索引 (native/managed 归类)."""
    import dao_solidworks as _sw
    installdir = None
    max_files = 500
    include_exports = "--exports" in args
    if "--installdir" in args:
        i = args.index("--installdir")
        if i + 1 < len(args): installdir = args[i+1]
    if "--max" in args:
        i = args.index("--max")
        if i + 1 < len(args):
            try: max_files = int(args[i+1])
            except ValueError: pass
    idx = _sw.sw_dll_index(installdir=installdir, max_files=max_files,
                            include_exports=include_exports)
    if "err" in idx:
        print(json.dumps(idx, ensure_ascii=False))
        return 1
    summary = {
        "root": idx.get("root"),
        "total": idx.get("total"),
        "managed_count": idx.get("managed_count"),
        "native_count": idx.get("native_count"),
        "dir_count": len(idx.get("by_dir", {})),
        "top_dirs": sorted(
            ((d, len(v)) for d, v in idx.get("by_dir", {}).items()),
            key=lambda x: -x[1])[:10],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_sw_reg(args):
    """L4 · 注册表全景 (roots + 统计)."""
    import dao_solidworks as _sw
    include_values = "--values" in args
    json_out = "--json" in args
    reg = _sw.sw_registry_dump(include_values=include_values, max_keys=500)
    if json_out:
        print(json.dumps(reg, ensure_ascii=False, indent=2, default=str))
        return 0
    summary = reg.get("_summary", {})
    print(f"total_keys:   {summary.get('total_keys')}")
    print(f"total_values: {summary.get('total_values')}")
    print(f"roots ({len(summary.get('roots', []))}):")
    for r in summary.get("roots", []):
        print(f"  · {r}")
    return 0


def _cmd_sw_docmgr(args):
    """L2.5 · SwDocumentMgr COM (只读, 无 license) 探测."""
    import dao_solidworks as _sw
    s = _sw.swdm_probe()
    d = s.to_dict() if hasattr(s, "to_dict") else dict(s)
    print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
    return 0 if d.get("ok") else 1


# ═════════════════════════════════════════════════════════════════════
# 万法 · L5 打通 (remediate) + L6 几何反演 (geom)
# ═════════════════════════════════════════════════════════════════════

def _cmd_sw_remediate(args):
    """L5 · 一键打通 (regasm SwDocumentMgr + sc start Licensing).

    默 dry_run=True; 用 --apply 实执 (需 admin shell).
    """
    import dao_solidworks as _sw
    apply_it = "--apply" in args
    no_service = "--no-service" in args
    enable_disabled = "--enable-disabled" in args
    json_out = "--json" in args
    out = _sw.sw_remediate_all(
        dry_run=not apply_it,
        with_licensing_service=not no_service,
        change_disabled_to_manual=enable_disabled,
    )
    if json_out:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print("═" * 62)
    print(f"  L5 · 反者道之动 · 打通  dry_run={not apply_it}  admin={out['admin']}")
    print("═" * 62)
    for k in ("docmgr", "licensing"):
        r = out.get(k)
        if not r:
            print(f"\n[{k}] — 跳过")
            continue
        print(f"\n[{k}]  action={r.get('action')}  ok={r.get('ok')}  "
               f"err={r.get('err')}")
        for step in r.get("steps", []):
            print(f"  · {step}")
        for note in r.get("notes", []):
            print(f"  ⓘ {note}")
    pd = out.get("post_diagnose", {})
    if isinstance(pd, dict) and "severity" in pd:
        print(f"\n[复诊] severity={pd.get('severity')}  "
               f"recommend={pd.get('recommend')}")
    return 0


def _cmd_sw_docmgr_reg(args):
    """L5.1 · 单 regasm SwDocumentMgr."""
    import dao_solidworks as _sw
    apply_it = "--apply" in args
    json_out = "--json" in args
    r = _sw.remediate_docmgr_com(dry_run=not apply_it)
    if json_out:
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2, default=str))
        return 0 if r.ok else 1
    print(f"action:  {r.action}")
    print(f"dry_run: {r.dry_run}")
    print(f"admin:   {r.admin}")
    print(f"ok:      {r.ok}")
    if r.err: print(f"err:     {r.err}")
    for s in r.steps: print(f"  · {s}")
    for n in r.notes: print(f"  ⓘ {n}")
    return 0 if r.ok else 1


def _cmd_sw_license_start(args):
    """L5.2 · 启 SW Licensing Service."""
    import dao_solidworks as _sw
    apply_it = "--apply" in args
    enable_disabled = "--enable-disabled" in args
    json_out = "--json" in args
    r = _sw.remediate_sw_licensing_service(
        dry_run=not apply_it,
        change_disabled_to_manual=enable_disabled,
    )
    if json_out:
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2, default=str))
        return 0 if r.ok else 1
    print(f"action:  {r.action}")
    print(f"dry_run: {r.dry_run}")
    print(f"admin:   {r.admin}")
    print(f"ok:      {r.ok}")
    print(f"before:  {r.before}")
    if r.after: print(f"after:   {r.after}")
    for s in r.steps: print(f"  · {s}")
    for n in r.notes: print(f"  ⓘ {n}")
    return 0 if r.ok else 1


# ═════════════════════════════════════════════════════════════════════
# L9 · 一键激活 + SW × 夸克网盘桥 (v3.3.0)
# 道法自然 · 万法归一 · 从 SW 安装包在夸克网盘 → SW COM 活体
# ═════════════════════════════════════════════════════════════════════

def _arg_get(args, flag, default=None, cast=str):
    """取 --flag VAL; 找不到回 default."""
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            try: return cast(args[i + 1])
            except Exception: return default
    return default


def _cmd_sw_activate(args):
    """L9 · 一键激活 (L0.5→L5→COM活检→复诊)."""
    import dao_solidworks as _sw
    apply_it = "--apply" in args
    no_probe = "--no-probe" in args
    dispatch = "--dispatch" in args
    no_enable = "--no-enable-disabled" in args
    no_service = "--no-service" in args
    json_out = "--json" in args
    report = _arg_get(args, "--report")
    probe_timeout = _arg_get(args, "--probe-timeout", 20.0, float)
    wait_s = _arg_get(args, "--wait", 5.0, float)

    r = _sw.sw_activate(
        dry_run=not apply_it,
        wait_license_s=wait_s,
        enable_disabled=not no_enable,
        with_licensing_service=not no_service,
        probe_com=not no_probe,
        probe_com_timeout_s=probe_timeout,
        probe_com_include_dispatch=dispatch,
    )
    if report:
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        Path(report).write_text(
            json.dumps(r.to_dict(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"[saved] {report}")
    if json_out:
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        print("═" * 66)
        print(f"  L9 · 一键激活  dry_run={r.dry_run}  admin={r.admin}")
        print("═" * 66)
        print(f"  ok:          {r.ok}  ({r.elapsed_s:.1f}s)")
        print(f"  severity:    {r.severity_before or '?'}  →  "
              f"{r.severity_after or '?'}")
        print(f"  com_ready:   {r.com_ready}")
        if r.com_revision:
            print(f"  revision:    {r.com_revision}")
        if r.com_msg:
            print(f"  com_msg:     {r.com_msg}")
        print(f"  stages ({len(r.stages)}):")
        for s in r.stages:
            mark = "✓" if s.get("ok") else "·"
            print(f"    {mark} {s.get('stage', '?'):15s} "
                  f"ok={s.get('ok')}")
        for ns in r.next_steps:
            print(f"  → {ns}")
        print("═" * 66)
    return 0 if r.ok else 1


def _cmd_sw_activate_verify(args):
    """L9+ · 激活 + 真启 SW + 可选 test_file 一张截图."""
    import dao_solidworks as _sw
    apply_it = "--apply" in args
    launch = "--launch" in args
    test_file = _arg_get(args, "--test-file")
    report = _arg_get(args, "--report")
    probe_timeout = _arg_get(args, "--probe-timeout", 20.0, float)
    json_out = "--json" in args

    out = _sw.sw_activate_and_verify(
        dry_run=not apply_it,
        launch_sw=launch,
        test_file=test_file,
        save_report=report,
        probe_com_timeout_s=probe_timeout,
    )
    if json_out:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:
        act = out.get("activate", {})
        print("═" * 66)
        print(f"  L9+ · 激活验证  dry_run={act.get('dry_run')}  "
              f"admin={act.get('admin')}")
        print("═" * 66)
        print(f"  activate.ok:   {act.get('ok')}  "
              f"severity: {act.get('severity_before')} → "
              f"{act.get('severity_after')}")
        lr = out.get("launch")
        if lr is not None:
            print(f"  launch.ok:     {lr.get('ok')}  "
                  f"rev={lr.get('revision', 'n/a')}  "
                  f"({lr.get('elapsed_s', 0):.1f}s)")
        tfr = out.get("test_file")
        if tfr and test_file:
            print(f"  test_file.ok:  {tfr.get('ok')}  "
                  f"({tfr.get('elapsed_s', 0):.1f}s)")
            for name, shot in (tfr.get("shots") or {}).items():
                if shot.get("ok"):
                    print(f"    [{name}] {shot['path']}")
        print("═" * 66)
    return 0 if out.get("activate", {}).get("ok") else 1


# ─── SW × 夸克网盘桥 · L1/L2/L3 辅助 ───────────────────────────────

def _get_quark_bridge():
    """延迟 import · 给用户清楚的错因."""
    try:
        import dao_quark_bridge as _qb  # type: ignore
    except ImportError as e:
        print(f"[ERR] cannot import dao_quark_bridge: {e}")
        print("      确保 00-本源_Origin 在 sys.path · 见 _paths.py")
        return None, None
    return _qb, _qb.DaoQuarkBridge()


def _cmd_sw_quark_status():
    _qb, br = _get_quark_bridge()
    if br is None: return 2
    st = br.status()
    print(json.dumps(st.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0 if st.cdp_up and st.quark_target_alive else 3


def _cmd_sw_quark_find(args):
    _qb, br = _get_quark_bridge()
    if br is None: return 2
    q = args[0]
    limit = _arg_get(args, "--limit", 50, int)
    if not br.connect(verbose=True):
        print("[ERR] CDP connect failed · 见 sw_quark_status")
        return 3
    items = br.find(q, limit=limit)
    print(json.dumps([f.to_dict() for f in items],
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_sw_quark_ls(args):
    _qb, br = _get_quark_bridge()
    if br is None: return 2
    if not br.connect(verbose=True):
        return 3
    if not args:
        items = br.ls("0")
    elif args[0].startswith("/"):
        items = br.ls_path(args[0])
    else:
        items = br.ls(args[0])
    print(json.dumps([f.to_dict() for f in items],
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_sw_quark_locate():
    _qb, br = _get_quark_bridge()
    if br is None: return 2
    if not br.connect(verbose=True):
        return 3
    loc = br.sw_installer_locate()
    print(json.dumps(loc, ensure_ascii=False, indent=2, default=str))
    return 0 if loc.get("n_hits", 0) > 0 else 4


def _cmd_sw_quark_pull(args):
    _qb, br = _get_quark_bridge()
    if br is None: return 2
    if not br.connect(verbose=True):
        return 3
    name_or_path = args[0]
    dst = args[1] if len(args) > 1 else None
    if dst is None:
        # 默认: 70-天下_World/sw/
        try:
            import _paths as _dao_paths  # type: ignore
            dst = _dao_paths.WORLD / "sw"
        except Exception:
            dst = Path("./sw")
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    try:
        def _progress_bar(got, total):
            bar_w = 24
            if total:
                filled = int(bar_w * got / total)
                bar = "█" * filled + "░" * (bar_w - filled)
                pct = got / total * 100
                sys.stdout.write(f"\r  [{bar}] {pct:5.1f}% "
                                 f"{got / 1e6:.1f}MB/{total / 1e6:.1f}MB")
            else:
                sys.stdout.write(f"\r  {got / 1e6:.1f}MB")
            sys.stdout.flush()

        r = br.pull(name_or_path, dst, progress=_progress_bar)
        print()
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2,
                         default=str))
        return 0 if r.ok else 4
    except Exception as e:
        print(f"[ERR] pull: {type(e).__name__}: {e}")
        return 5


def _cmd_sw_from_quark(args):
    """一键: 找 SW 资源 + 批量拉下 (道法自然核心)."""
    _qb, br = _get_quark_bridge()
    if br is None: return 2
    if not br.connect(verbose=True):
        return 3
    what = _arg_get(args, "--what", "installer", str)
    dst = _arg_get(args, "--dst", None)
    if dst is None:
        try:
            import _paths as _dao_paths  # type: ignore
            dst = _dao_paths.WORLD / "sw"
        except Exception:
            dst = Path("./sw")
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)

    def _progress_bar(got, total):
        bar_w = 24
        if total:
            filled = int(bar_w * got / total)
            bar = "█" * filled + "░" * (bar_w - filled)
            pct = got / total * 100
            sys.stdout.write(f"\r  [{bar}] {pct:5.1f}% "
                             f"{got / 1e6:.1f}MB/{total / 1e6:.1f}MB")
        else:
            sys.stdout.write(f"\r  {got / 1e6:.1f}MB")
        sys.stdout.flush()

    try:
        r = br.sw_installer_pull(dst, what=what, progress=_progress_bar)
        print()
        # 略掉 results 详情 · 只打印头部
        summary = {k: v for k, v in r.items() if k != "results"}
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        print(f"\n  n_ok={r.get('n_ok')}/{r.get('n_picked')}  "
              f"dst={r.get('dst_dir')}")
        return 0 if r.get("ok") else 4
    except Exception as e:
        print(f"[ERR] sw_from_quark: {type(e).__name__}: {e}")
        return 5


def _cmd_sw_quark_share(args):
    """解析夸克分享链接 (转发至 dao_quark_bridge)."""
    _qb, br = _get_quark_bridge()
    if br is None: return 2
    if not br.connect(verbose=True):
        return 3
    url = args[0]
    passcode = _arg_get(args, "--passcode", "", str)
    info = br.share_resolve(url, passcode)
    print(json.dumps(info.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0 if not info.err else 5


def _cmd_sw_geom(args):
    """L6 · 几何反演 (Parasolid XT + BRep + Orphan)."""
    import dao_solidworks as _sw
    file = args[0]
    max_bytes = 4 * 1024 * 1024
    if "--max-bytes" in args:
        i = args.index("--max-bytes")
        if i + 1 < len(args):
            try: max_bytes = int(args[i+1])
            except ValueError: pass
    json_out = "--json" in args
    g = _sw.carve_geometry_refs(file, max_stream_bytes=max_bytes)
    if json_out:
        print(json.dumps(g.to_dict(), ensure_ascii=False, indent=2, default=str))
        return 0 if g.ok else 1
    print("═" * 62)
    print(f"  L6 · 几何反演  file={Path(file).name}")
    print("═" * 62)
    print(f"ok:                 {g.ok}  err={g.err}")
    print(f"geometry_streams:   {len(g.geometry_streams)}")
    for s in g.geometry_streams:
        star = "★" if s.get("n_hits", 0) else " "
        print(f"  {star} {s['name']:28s}  size={s.get('size_B', 0):>10,} B  "
               f"sampled={s.get('sampled_B', 0):>9,} B  hits={s.get('n_hits', 0)}")
    print(f"Parasolid XT hits:  {len(g.xt_hits)}")
    for h in g.xt_hits[:10]:
        print(f"  · {h['stream']:28s}  kind={h['kind']:10s}  "
               f"offset=0x{h['offset']:08x}")
    print(f"Orphan BRep refs:   {len(g.orphan_breps)}")
    for b in g.orphan_breps[:8]:
        print(f"  · {b}")
    if len(g.orphan_breps) > 8:
        print(f"  · ... (+{len(g.orphan_breps) - 8} 条)")
    for n in g.notes:
        print(f"  ⓘ {n}")
    return 0 if g.ok else 1


if __name__ == "__main__":
    sys.exit(main())
