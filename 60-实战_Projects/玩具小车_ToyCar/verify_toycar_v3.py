# -*- coding: utf-8 -*-
"""ToyCarV3 自审: 逐件网格化 + trimesh 水密性/体积验证(非水密件体素重建治疗)"""
import json
import os
import urllib.request

import trimesh

BASE = "http://127.0.0.1:18920"
HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.join(HERE, "v3_parts")
STLD = os.path.join(PARTS, "stl")
os.makedirs(STLD, exist_ok=True)


def fc(code, timeout=600):
    req = urllib.request.Request(
        BASE + "/exec", data=json.dumps({"code": code}).encode(),
        headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    if not r.get("ok", True):
        raise RuntimeError(str(r)[:500])
    return r


def mesh_via_bridge(names):
    fc(f"""
import Part, Mesh, MeshPart, os, json
names = {json.dumps(names)}
for n in names:
    sh = Part.Shape(); sh.read(os.path.join(r"{PARTS}", n + ".brep"))
    m = MeshPart.meshFromShape(Shape=sh, LinearDeflection=0.1, AngularDeflection=0.35)
    m.write(os.path.join(r"{STLD}", n + ".stl"))
""")


def main():
    names = sorted(f[:-5] for f in os.listdir(PARTS) if f.endswith(".brep"))
    missing = [n for n in names
               if not os.path.exists(os.path.join(STLD, n + ".stl"))]
    if missing:
        mesh_via_bridge(missing)
    report = {}
    ok = True
    for n in names:
        m = trimesh.load(os.path.join(STLD, n + ".stl"))
        wt = bool(m.is_watertight)
        method = "none"
        if not wt:
            # 齿轮等复杂件: 体素重建水密治疗(同 v2.1)
            pitch = 0.12
            v = m.voxelized(pitch=pitch).fill()
            r = v.marching_cubes
            r.apply_scale(pitch)
            r.apply_translation(v.bounds[0])
            r = trimesh.smoothing.filter_taubin(r, iterations=8)
            r = r.simplify_quadric_decimation(face_count=20000)
            if r.is_watertight:
                r.export(os.path.join(STLD, n + ".stl"))
                m = r
            method = "voxel_remesh(pitch=%g)" % pitch
        wt_fixed = bool(m.is_watertight)
        report[n] = {
            "watertight_raw": wt, "watertight": wt_fixed, "heal": method,
            "volume_mm3": round(float(abs(m.volume)), 2),
            "faces": int(len(m.faces)),
            "bbox": [round(float(v), 2) for v in m.extents],
        }
        ok = ok and wt_fixed
        print(f"{'✓' if wt else ('~' if wt_fixed else '✗')} {n:12s} "
              f"watertight={wt_fixed} heal={method} "
              f"vol={report[n]['volume_mm3']:.0f}mm³ faces={report[n]['faces']}")
    with open(os.path.join(HERE, "toycar_v3_verify.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("自审结论:", "全部水密(含体素治疗)" if ok else "存在非水密件")
    return ok


if __name__ == "__main__":
    main()
