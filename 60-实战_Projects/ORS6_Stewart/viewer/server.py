#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORS6_Stewart · viewer/server — 3D装配查看器 HTTP 服务 (原 sr6_studio.py)

Three.js 前端 + Python API, 默认端口 :8871.
Usage:
    python -m ORS6_Stewart.viewer.server           # default :8871
    python -m ORS6_Stewart.viewer.server 8888      # custom port

API:
    GET /api/parts               — 31 零件清单 + bounds + STL url
    GET /api/ik                  — IK 常数 (SR6 dict)
    GET /api/health              — 服务状态
    GET /api/servo               — 舵机槽位 (Z=46mm 截面)
    GET /api/verify              — V1-V8 数值验证
    GET /api/section?z=<Z>       — 任意 Z 截面
    GET /api/overview            — 零件概览 (按 Z 高度排序)
    GET /api/instances           — 装配实例 (arm/link/pitcher_arm 位姿)
    GET /api/assembly_validate   — 装配验证 (checks + rods)
    GET /api/diagnostics         — 轻量诊断 (fast, <100ms)
    GET /api/mass?part=<P>       — 质量属性 (单件/全部)
    GET /api/quality[?part=P]    — 质量检查
    GET /api/workspace?resolution=<N>
    GET /api/clearance
    GET /api/assembly
    GET /api/ik_pose?L0=&...     — 正运动学
    GET /api/collision?p1=&p2=
    GET /stl/<PartName>          — STL 二进制
    GET /                        — index.html
"""
from __future__ import annotations

import http.server
import json
import mimetypes
import os
import socketserver
import sys
import urllib.parse
from pathlib import Path

# ── Bootstrap — allow running as both `python -m` and direct script ──────────
HERE = Path(__file__).resolve().parent       # viewer/
PROJECT = HERE.parent                         # ORS6_Stewart/
PROJECTS_DIR = PROJECT.parent                 # 60-实战_Projects/
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))

import ORS6_Stewart as S  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8871
HTML_PATH = HERE / "index.html"


def _color_hex(color_int: int) -> str:
    return f"{color_int:06x}"


def get_parts_manifest():
    """Build parts manifest with bounds data (consumed by frontend)."""
    bounds = {}
    if os.path.exists(S.BOUNDS_FILE):
        bounds = json.load(open(S.BOUNDS_FILE, encoding="utf-8"))

    manifest = []
    for name, (sub, fn, color_int, group) in S.PARTS.items():
        path = S.stl_path(name)
        vgroup = None
        for vg_name, vg_info in S.VARIANT_GROUPS.items():
            if name in vg_info["parts"]:
                vgroup = vg_name
                break
        entry = {
            "name": name, "file": fn,
            "color": _color_hex(color_int),
            "group": group,
            "url": f"/stl/{urllib.parse.quote(name)}",
            "exists": os.path.exists(path),
            "hidden": name in S.DEFAULT_HIDDEN,
            "recv": name in S.RECV_PARTS,
            "variant_group": vgroup,
        }
        if name in bounds and "center" in bounds[name]:
            b = bounds[name]
            entry["center"] = b["center"]
            entry["size"] = b["size"]
            entry["min"] = b.get("min")
            entry["max"] = b.get("max")
        manifest.append(entry)
    return manifest


class StudioHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/parts":
                self._json(get_parts_manifest())
            elif path == "/api/ik":
                self._json(S.SR6)
            elif path == "/api/health":
                self._json({"status": "ok", "parts": len(S.PARTS),
                            "port": PORT, "version": S.__version__})
            elif path == "/api/servo":
                self._json(S.extract_servo_slots())
            elif path == "/api/verify":
                self._json(S.verify_assembly())
            elif path == "/api/section":
                z = float(query.get("z", ["46"])[0])
                results = {}
                for n in ["L_Frame", "R_Frame"]:
                    sec = S.section_at_z(n, z)
                    if sec:
                        results[n] = sec
                self._json(results)
            elif path == "/api/overview":
                self._json({"overview": S.overview()})
            elif path == "/api/instances":
                self._json(S.assembly_instances())
            elif path == "/api/assembly_validate":
                checks = S.verify_assembly()
                rods = S.compute_rods()
                self._json({"checks": checks, "rods": rods})
            elif path == "/api/diagnostics":
                self._json(self._diagnostics())
            elif path == "/api/mass":
                part = query.get("part", [None])[0]
                mat = query.get("material", ["pla"])[0]
                if part:
                    self._json(S.mass_properties(part, mat))
                else:
                    grps = query.get("group", [None])[0]
                    groups = [grps] if grps else None
                    self._json(S.mass_properties_all(mat, groups))
            elif path == "/api/quality":
                part = query.get("part", [None])[0]
                self._json(S.quality_check(part) if part else S.quality_check_all())
            elif path == "/api/workspace":
                res = int(query.get("resolution", ["10"])[0])
                self._json(S.workspace_analysis(res))
            elif path == "/api/clearance":
                self._json(S.clearance_analysis())
            elif path == "/api/assembly":
                self._json(S.assembly_stats())
            elif path == "/api/ik_pose":
                vals = {k: float(query.get(k, ["0.5"])[0])
                        for k in ("L0", "L1", "L2", "R0", "R1", "R2")}
                self._json(S.ik_forward(**vals))
            elif path == "/api/collision":
                p1 = query.get("p1", ["Base"])[0]
                p2 = query.get("p2", ["L_Frame"])[0]
                self._json(S.collision_check(p1, p2))
            elif path.startswith("/api/part/"):
                pname = urllib.parse.unquote(path[10:])
                try:
                    self._json(S.part_info(pname))
                except Exception as e:
                    self._json({"error": str(e)})
            elif path.startswith("/stl/"):
                part_name = urllib.parse.unquote(path[5:])
                self._serve_stl(part_name)
            elif path == "/" or path == "/index.html":
                self._serve_file(str(HTML_PATH))
            else:
                self._serve_file(str(HERE / path.lstrip("/")))
        except Exception as e:
            self._json({"error": str(e)}, status=500)

    def _json(self, data, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_stl(self, part_name: str):
        if part_name not in S.PARTS:
            self.send_error(404, f"Part not found: {part_name}")
            return
        filepath = S.stl_path(part_name)
        self._serve_file(filepath, "application/octet-stream")

    def _serve_file(self, filepath: str, content_type=None):
        if not os.path.exists(filepath):
            self.send_error(404)
            return
        if content_type is None:
            content_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _diagnostics(self):
        """Lightweight diagnostics (no trimesh loading)."""
        try:
            missing = [n for n in S.PARTS if not os.path.exists(S.stl_path(n))]
            checks = [
                {"name": "stl_files", "pass": len(missing) == 0,
                 "missing": missing, "total": len(S.PARTS)},
                {"name": "bounds_file", "pass": os.path.exists(S.BOUNDS_FILE)},
                {"name": "ik_constants", "pass": bool(S.SR6),
                 "baseH": S.SR6["baseH"], "mainRod": S.SR6["mainRod"]},
            ]
            passes = sum(1 for c in checks if c["pass"])
            grade = "S" if passes == len(checks) else "A" if passes >= len(checks) - 1 else "B"
            return {
                "parts": len(S.PARTS), "checks": checks,
                "score": f"{passes}/{len(checks)}", "grade": grade,
                "note": "Lightweight. For full diagnostics run "
                        "`python -m ORS6_Stewart.cli health`.",
            }
        except Exception as e:
            return {"error": str(e)}

    def log_message(self, fmt, *args):
        if "/stl/" not in str(args[0]):
            super().log_message(fmt, *args)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main():
    server = ThreadedHTTPServer(("0.0.0.0", PORT), StudioHandler)
    print(f"ORS6_Stewart Viewer @ http://localhost:{PORT}")
    print(f"  Parts: {len(S.PARTS)} | STL root: {S.STL_ROOT}")
    print(f"  API: /api/{{parts,ik,health,mass,quality,workspace,clearance,"
          f"assembly,ik_pose,collision,instances,verify,assembly_validate,section,servo}}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
