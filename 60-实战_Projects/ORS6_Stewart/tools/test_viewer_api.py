#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ORS6_Stewart viewer · API regression: starts server, hits all key endpoints, stops."""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PROJECT = TOOLS.parent
PROJECTS = PROJECT.parent
sys.path.insert(0, str(PROJECTS))

# Patch viewer port to ephemeral 8889
import ORS6_Stewart.viewer.server as srv
srv.PORT = 8889

PORT = 8889
BASE = f"http://127.0.0.1:{PORT}"


def get(path: str, timeout: int = 8):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    server = srv.ThreadedHTTPServer(("127.0.0.1", PORT), srv.StudioHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)

    try:
        results = []
        # /api/health
        h = get("/api/health")
        results.append(("health", h.get("status") == "ok",
                        f"status={h.get('status')} parts={h.get('parts')} v={h.get('version')}"))

        # /api/instances (default geom=3d, NEW behavior)
        ins = get("/api/instances")
        results.append(("instances:default-3d",
                        ins.get("rod_model") == "physical_3d",
                        f"rod_model={ins.get('rod_model')} rod_nom={ins.get('rod_nominal_mm')}mm "
                        f"arms={len(ins.get('arms',[]))} links={len(ins.get('links',[]))} "
                        f"pitchers={len(ins.get('pitcher_arms',[]))}"))

        # Verify all 6 links have rod_3d_mm == 175 (STRICT)
        link_devs = [abs(L["rod_3d_mm"] - 175.0) for L in ins.get("links", [])]
        max_dev = max(link_devs) if link_devs else float("inf")
        results.append(("instances:rod-175-strict", max_dev < 0.001,
                        f"max Δ = {max_dev:.6f} mm (across {len(link_devs)} links)"))

        # /api/instances?geom=firmware (legacy)
        ins_fw = get("/api/instances?geom=firmware")
        results.append(("instances:legacy-firmware",
                        "rod_model" not in ins_fw,
                        f"keys={sorted(ins_fw.keys())[:5]}"))

        # /api/rods_3d
        rods = get("/api/rods_3d")
        rod_devs = [abs(r["rod_3d_mm"] - 175.0) for r in rods]
        max_rd = max(rod_devs) if rod_devs else float("inf")
        results.append(("rods_3d:175-strict", max_rd < 0.001,
                        f"6 rods · max Δ = {max_rd:.6f} mm"))

        # /api/geometry_verify (V1-V12)
        gv = get("/api/geometry_verify")
        ok = sum(1 for c in gv if c.get("ok"))
        total = len(gv)
        results.append(("geometry_verify:V1-V12", ok == total,
                        f"{ok}/{total} OK"))

        # /api/anchors
        a = get("/api/anchors")
        results.append(("anchors", a.get("rod_nominal_mm") == 175.0,
                        f"rod_nominal={a.get('rod_nominal_mm')} anchors={len(a.get('anchors',[]))}"))

        # /api/assembly_validate
        av = get("/api/assembly_validate")
        rods_3d_ok = len(av.get("rods_3d", [])) == 6
        gc_ok = sum(1 for c in av.get("geometry_checks", []) if c.get("ok"))
        results.append(("assembly_validate", rods_3d_ok and gc_ok > 0,
                        f"rods_3d={len(av.get('rods_3d',[]))} geom_ok={gc_ok}"))

        # /api/parts (manifest)
        parts = get("/api/parts")
        results.append(("parts:31-manifest", len(parts) == 31,
                        f"{len(parts)} parts (expected 31)"))

        # Print
        print("=" * 78)
        print(f"  Viewer API regression @ {BASE}")
        print("=" * 78)
        passed = 0
        for name, ok, detail in results:
            mark = "OK " if ok else "X  "
            print(f"  [{mark}] {name:32s} {detail}")
            if ok:
                passed += 1
        print("-" * 78)
        print(f"  {passed}/{len(results)} pass")
        return 0 if passed == len(results) else 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
