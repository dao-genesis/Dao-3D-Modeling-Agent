"""ORS6_Stewart · FreeCAD 5-pose builder.

Run with FreeCAD 1.0 bundled Python:
    "D:\\path\\to\\FreeCADCmd.exe" ORS6_Stewart/tools/freecad_build.py

Builds .FCStd + .step for home + forward + side_right + pitch_up + roll_left.

CRITICAL design:
    * Pure ASCII source (no CN comments) — Win+CN-path argv can mojibake.
    * Never reference sys.argv / sys.executable (surrogate-encoded on CN paths).
    * All output to a log file + return code via os._exit.

The script writes its own log to ORS6_Stewart/output/_freecad_build.log.
"""
import os
import sys
import time
import traceback

# ── Bootstrap: locate ORS6_Stewart project root from this script's location ──
THIS_FILE = os.path.abspath(__file__)
TOOLS = os.path.dirname(THIS_FILE)              # .../ORS6_Stewart/tools
PROJECT = os.path.dirname(TOOLS)                # .../ORS6_Stewart
PROJECTS_ROOT = os.path.dirname(PROJECT)        # .../60-shizhan_Projects
if PROJECTS_ROOT not in sys.path:
    sys.path.insert(0, PROJECTS_ROOT)

# Output dir: prefer env var (so we can write to original CN-path output/
# while running this script from an ASCII mirror at C:\Temp\ORS6_FC\).
# Default: <package>/output (works when running directly from CN repo too,
# but FreeCADCmd cannot open CN-path .py argv — hence the mirror).
OUT_DIR = os.environ.get("ORS6_FC_OUTPUT_DIR") or os.path.join(PROJECT, "output")
LOG = os.path.join(OUT_DIR, "_freecad_build.log")


def w(line=""):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(line) + "\n")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    # Wipe log
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("== ORS6 FreeCAD build (5 poses) ==\n")
        f.write(f"timestamp = {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ── A. Verify FreeCAD ──
    try:
        import FreeCAD as App
        ver = App.Version()
        w(f"[A] FreeCAD = {'.'.join(str(x) for x in ver[0:3])}")
    except Exception as e:
        w(f"[A] FreeCAD ERR: {e!r}")
        return 1

    # ── B. Import ORS6_Stewart ──
    try:
        from ORS6_Stewart import (
            build_freecad, MOTION_POSES, TCODE_HOME, ROD_LEN_MM,
        )
        w(f"[B] ORS6_Stewart imported OK · ROD_LEN_MM = {ROD_LEN_MM}")
    except Exception as e:
        w(f"[B] ORS6_Stewart import ERR: {e!r}")
        w(traceback.format_exc())
        return 2

    # ── C. Resolve 5 canonical poses ──
    poses = {"home": TCODE_HOME}
    for label_target in ["forward", "side_right", "pitch_up", "roll_left"]:
        for entry in MOTION_POSES:
            if entry[0] == label_target:
                poses[label_target] = tuple(entry[1:])
                break
    w(f"[C] poses = {list(poses.keys())}")

    # ── D. Build each pose ──
    results = []
    t_total = time.time()
    for label, pose in poses.items():
        w("")
        w(f"--- pose: {label} = {pose} ---")
        t1 = time.time()
        try:
            r = build_freecad(pose=pose, label=label, output_dir=OUT_DIR)
            dt = time.time() - t1
            fcstd = r.get("fcstd_path")
            step = r.get("step_path")
            sz_fcstd = os.path.getsize(fcstd) if fcstd and os.path.exists(fcstd) else 0
            sz_step = os.path.getsize(step) if step and os.path.exists(step) else 0
            w(f"  OK in {dt:.2f}s  parts={r.get('parts_count')} rods={len(r.get('rods',[]))}")
            w(f"     FCStd: {sz_fcstd} B  -> {os.path.basename(fcstd) if fcstd else '?'}")
            w(f"     STEP : {sz_step} B  -> {os.path.basename(step) if step else '?'}")
            for rod in r.get("rods", []):
                w(f"     {rod['servo']:11s} type={rod['type']:5s} L={rod['rod_3d_mm']:7.3f}mm "
                  f"stress={rod['stress_pct']:.4f}%  src={rod['src']}")
            results.append({
                "label": label, "ok": True, "duration_s": round(dt, 2),
                "fcstd": fcstd, "fcstd_size": sz_fcstd,
                "step": step, "step_size": sz_step,
                "parts_count": r.get("parts_count"),
            })
        except Exception as e:
            dt = time.time() - t1
            w(f"  FAIL in {dt:.2f}s: {e!r}")
            w(traceback.format_exc())
            results.append({"label": label, "ok": False, "error": str(e)})

    dt_total = time.time() - t_total
    ok = sum(1 for r in results if r.get("ok"))
    w("")
    w("=" * 60)
    w(f"DONE: {ok}/{len(results)} OK · total {dt_total:.2f}s")

    # Write JSON summary
    try:
        import json
        summary = {
            "engine": "freecad",
            "freecad_version": ".".join(str(x) for x in App.Version()[0:3]),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ok_count": ok,
            "total": len(results),
            "duration_s": round(dt_total, 2),
            "results": results,
        }
        sp = os.path.join(OUT_DIR, "_freecad_5pose_summary.json")
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        w(f"summary -> {os.path.basename(sp)}")
    except Exception as e:
        w(f"summary ERR: {e!r}")

    return 0 if ok == len(results) else 3


# Top-level execution: FreeCADCmd does NOT use __name__ == "__main__"
# (it execs the script in its own context, so the guard would skip everything).
# Run main directly + force-exit to flush.
_rc = main()
try:
    sys.stdout.flush()
except Exception:
    pass
os._exit(_rc)
