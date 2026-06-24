# -*- coding: utf-8 -*-
"""反者道之动 · 全装配错位审计

原则: 数字真相直接给, 不再轻信任何文档/报告.
对每个 STL 报告:
  - STL 自带 bbox (设计坐标)
  - viewer 中 Three.js mesh 实际 position (loadAllParts 后)
  - assembly.py CadQuery 实际 placement (build_cadquery 后)
  - 期望位置: 静态 = STL 自坐, 受 IK 影响 = HOME_H 或 frame top 等

输出: 三列对比, 找出每件零件的"应在/实在/差距".
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import trimesh
from ORS6_Stewart.parts import (
    PARTS, RECV_PARTS, DEFAULT_HIDDEN, SR6, SERVO_SLOTS, HOME_H,
    TWIST_RECV_PARTS, TWIST_RECV_Z_OFFSET, stl_path,
)


def stl_bounds(name: str):
    m = trimesh.load(stl_path(name))
    b = m.bounds
    return {
        "min": [round(float(b[0][i]), 1) for i in range(3)],
        "max": [round(float(b[1][i]), 1) for i in range(3)],
        "center": [round(float((b[0][i] + b[1][i]) / 2), 1) for i in range(3)],
        "size": [round(float(b[1][i] - b[0][i]), 1) for i in range(3)],
    }


print("=" * 100)
print("ORS6_Stewart · 全 STL 装配错位审计 · 反者道之动")
print("=" * 100)

# Categorize parts into expected placement modes
INSTANCED = {"Arm", "L_Pitcher", "R_Pitcher"}

print(f"\n类别一: 静态 (STL 自坐, 不应平移): expect viewer/CadQuery 都用原坐标")
print("-" * 100)
static_parts = [n for n in PARTS
                if n not in RECV_PARTS and n not in DEFAULT_HIDDEN
                and n not in INSTANCED]
for n in sorted(static_parts):
    b = stl_bounds(n)
    print(f"  {n:25s}  STL center={b['center']}  size={b['size']}  Z=[{b['min'][2]},{b['max'][2]}]")

print(f"\n类别二: 升 receiver (随 receiver pose 平移到 HOME_H=208.48):")
print("-" * 100)
recv_visible = [n for n in RECV_PARTS if n not in DEFAULT_HIDDEN]
for n in sorted(recv_visible):
    b = stl_bounds(n)
    z_off = TWIST_RECV_Z_OFFSET if n in TWIST_RECV_PARTS else 0.0
    expect_z_local = b["center"][2] + z_off
    expect_z_world = expect_z_local + HOME_H
    print(f"  {n:25s}  STL center={b['center']}  z_off={z_off:+.1f}  "
          f"→ world Z center≈{expect_z_world:.1f}")

print(f"\n类别三: Arm 实例 (4×, 平移到 frame top servo shaft Z=46):")
print("-" * 100)
b = stl_bounds("Arm")
print(f"  Arm STL center={b['center']}  bbox X=[{b['min'][0]},{b['max'][0]}]  Y=[{b['min'][1]},{b['max'][1]}]  Z=[{b['min'][2]},{b['max'][2]}]")
for sname, stype, sx, sy, _sign in SERVO_SLOTS:
    if stype == "main":
        mirror = "✓" if sx < 0 else " "
        print(f"    {sname:12s}  shaft=({sx:+.1f},{sy:+.1f},{SR6['servoPivotH']:.1f})  mirror_x={mirror}")

print(f"\n类别四: Pitcher (2×, 平移到 frame top servo shaft Z=46):")
print("-" * 100)
for nm in ["L_Pitcher", "R_Pitcher"]:
    b = stl_bounds(nm)
    print(f"  {nm:25s}  STL center={b['center']}  bbox X=[{b['min'][0]},{b['max'][0]}]  Y=[{b['min'][1]},{b['max'][1]}]  Z=[{b['min'][2]},{b['max'][2]}]")
for sname, stype, sx, sy, _sign in SERVO_SLOTS:
    if stype == "pitch":
        print(f"    {sname:12s}  shaft=({sx:+.1f},{sy:+.1f},{SR6['servoPivotH']:.1f})")

print(f"\n类别五: 隐藏 (DEFAULT_HIDDEN, 不应可见):")
print("-" * 100)
for n in sorted(DEFAULT_HIDDEN):
    b = stl_bounds(n)
    print(f"  {n:25s}  STL center={b['center']}  size={b['size']}")

# Now query the viewer API to see what it returns and compare
print("\n" + "=" * 100)
print("Viewer API /api/parts 返回 (关注 hidden / recv 标志):")
print("-" * 100)
import urllib.request, json as _json
try:
    with urllib.request.urlopen("http://localhost:8871/api/parts", timeout=3) as r:
        parts_api = _json.loads(r.read())
    for p in parts_api:
        # Highlight critical: parts that are NOT in RECV_PARTS but have visible Z>200 STL center
        b = stl_bounds(p["name"])
        flag = ""
        if not p["hidden"] and not p["recv"] and p["name"] not in INSTANCED:
            if b["center"][2] > 100:
                flag = "⚠ STL Z=" + str(b['center'][2]) + " 高位但无 recv 标志!"
            elif p["name"] in ("ESP32_Mount",) or "Tray" in p["name"]:
                flag = "⚠ 该件应 hidden 或 recv"
        recv = "RECV" if p["recv"] else "    "
        hide = "HIDE" if p["hidden"] else "    "
        print(f"  {p['name']:25s} {recv} {hide} STL_Z={b['center'][2]:+6.1f}  {flag}")
except Exception as e:
    print(f"  API 不可达: {e}")

# Now try to get assembly info — what z does each part end up at after build_cadquery?
print("\n" + "=" * 100)
print("假想装配 home pose · 查 viewer/CadQuery 计算结果:")
print("-" * 100)
try:
    with urllib.request.urlopen("http://localhost:8871/api/instances", timeout=3) as r:
        inst = _json.loads(r.read())
    print(f"  arms={len(inst.get('arms', []))}  links={len(inst.get('links', []))}  "
          f"pitcher_arms={len(inst.get('pitcher_arms', []))}")
    print(f"  HOME_H = {inst.get('home_h')}")
except Exception as e:
    print(f"  API 不可达: {e}")
