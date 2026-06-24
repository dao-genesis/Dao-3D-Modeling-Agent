#!/usr/bin/env python3
"""Benchmark: DaoKernel vs build123d vs CadQuery — same geometry."""
import sys, time, os
from pathlib import Path

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), Path(__file__).resolve().parent.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

results = {}

# === TEST 1: DaoKernel (Raw OCP, 0 layers) ===
t0 = time.time()
from dao_kernel import DaoKernel as K
box = K.box(80, 60, 10, origin=(-40, -30, 0))
cyl = K.cylinder(20, 40, origin=(0, 0, 10))
body = K.fuse(box, cyl)
hole = K.cylinder(8, 60)
body = K.cut(body, hole)
body = K.fillet(body, 1.5)
vol_ocp = K.volume(body)
K.to_stl(body, "output/_bench_ocp.stl")
K.to_step(body, "output/_bench_ocp.step")
dt_ocp = (time.time() - t0) * 1000
results["DaoKernel(OCP)"] = {"ms": round(dt_ocp, 1), "vol": round(vol_ocp, 1), "layers": 0}

# === TEST 2: build123d (2 layers) ===
t0 = time.time()
from build123d import *
with BuildPart() as p:
    Box(80, 60, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((0, 0, 10)):
        Cylinder(20, 40, align=(Align.CENTER, Align.CENTER, Align.MIN))
    Cylinder(8, 60, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    fillet(p.edges(), radius=1.5)
vol_b3d = p.part.volume
os.makedirs("output", exist_ok=True)
export_stl(p.part, "output/_bench_b3d.stl")
export_step(p.part, "output/_bench_b3d.step")
dt_b3d = (time.time() - t0) * 1000
results["build123d"] = {"ms": round(dt_b3d, 1), "vol": round(vol_b3d, 1), "layers": 2}

# === TEST 3: CadQuery (3 layers) ===
t0 = time.time()
import cadquery as cq
r = (cq.Workplane("XY")
     .box(80, 60, 10)
     .faces(">Z").workplane()
     .circle(20).extrude(40)
     .faces(">Z").workplane()
     .circle(8).cutThruAll()
     .edges().fillet(1.5))
vol_cq = r.val().Volume()
cq.exporters.export(r, "output/_bench_cq.stl")
cq.exporters.export(r, "output/_bench_cq.step")
dt_cq = (time.time() - t0) * 1000
results["CadQuery"] = {"ms": round(dt_cq, 1), "vol": round(vol_cq, 1), "layers": 3}

# === Print ===
print("=" * 65)
print("  Benchmark: same model (box+cyl+hole+fillet+STL+STEP)")
print("=" * 65)
fmt = "{:<20} {:>10} {:>15} {:>8}"
print(fmt.format("Engine", "Time(ms)", "Volume(mm3)", "Layers"))
print("-" * 65)
for name, d in results.items():
    print(fmt.format(name, f"{d['ms']:.1f}", f"{d['vol']:.1f}", str(d["layers"])))
print("-" * 65)

vols = [d["vol"] for d in results.values()]
max_drift = max(vols) - min(vols)
drift_pct = max_drift / vols[0] * 100
print(f"Volume consistency: drift = {max_drift:.1f}mm3 ({drift_pct:.4f}%)")

fastest = min(results.items(), key=lambda x: x[1]["ms"])
slowest = max(results.items(), key=lambda x: x[1]["ms"])
print(f"Winner: {fastest[0]} @ {fastest[1]['ms']:.0f}ms")
print(f"Speedup vs {slowest[0]}: {slowest[1]['ms']/fastest[1]['ms']:.1f}x")
print("=" * 65)
