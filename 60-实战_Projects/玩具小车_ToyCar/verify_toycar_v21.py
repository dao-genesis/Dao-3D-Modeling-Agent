# -*- coding: utf-8 -*-
"""玩具小车 v2.1 · 落地闭环校核 · 反者道之动
==============================================
v2 建模/干涉清零之后的自审迭代——把模型推向"现实可造可跑"：

1. 逐零件 STL 导出(v2_parts/stl/) —— 直接可 3D 打印
2. 可打印性校核 —— 实体水密性 / 最小特征尺寸(FDM 0.4 喷嘴) / 打印耗材估算
3. 电机电气 + 整车动力学仿真 —— 130 直流电机模型(Kt/Ke/R) → 牵引力平衡 ODE
   → 极速 / 0-1m 加速 / 爬坡度 / 2×AA 续航

运行: python3 verify_toycar_v21.py  (桥接 http://127.0.0.1:18920 在线, ToyCarV2 文档已开)
产物: v2_parts/stl/*.stl / toycar_v21_report.json
"""
import json
import math
import os
import urllib.request

BASE = "http://127.0.0.1:18920"
HERE = os.path.dirname(os.path.abspath(__file__))
STL_DIR = os.path.join(HERE, "v2_parts", "stl")
os.makedirs(STL_DIR, exist_ok=True)


def fc(code, timeout=300):
    req = urllib.request.Request(
        BASE + "/exec", data=json.dumps({"code": code}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    if not r.get("ok", True):
        raise RuntimeError(r)
    return r


# ── 1+2. 逐零件 STL 导出 + 可打印性校核(在 FreeCAD 本体内完成) ────────────
def export_and_check():
    r = fc(f"""
import FreeCAD as App, Mesh, MeshPart, json, os
doc = App.getDocument("ToyCarV2")
out = r"{STL_DIR}"
NOZZLE = 0.4          # FDM 0.4 喷嘴
MIN_WALL = 2 * NOZZLE  # 最小壁厚 0.8mm
res = {{}}
for o in doc.Objects:
    if not hasattr(o, "Shape"):
        continue
    s = o.Shape
    m = MeshPart.meshFromShape(Shape=s, LinearDeflection=0.05, AngularDeflection=0.3)
    p = os.path.join(out, o.Name + ".stl")
    m.write(p)
    bb = s.BoundBox
    # 最小特征: 遍历边长与圆柱半径, 找可能小于喷嘴分辨率的特征
    min_edge = min((e.Length for e in s.Edges if e.Length > 1e-6), default=0)
    min_cyl_r = min((f.Surface.Radius for f in s.Faces
                     if hasattr(f.Surface, "Radius")), default=None)
    res[o.Name] = {{
        "watertight_solid": bool(s.isValid() and s.Solids and s.isClosed()),
        "volume_mm3": round(s.Volume, 1),
        "bbox_mm": [round(bb.XLength, 1), round(bb.YLength, 1), round(bb.ZLength, 1)],
        "min_edge_mm": round(min_edge, 3),
        "min_cyl_radius_mm": round(min_cyl_r, 3) if min_cyl_r else None,
        "printable_walls": bool(min_edge >= MIN_WALL or min_edge == 0),
        "stl": p,
    }}
__result__ = json.dumps(res)
""")
    return json.loads(r["result"])


# ── 2b. 齿轮网格治疗: 渐开线齿轮 BREP 有自交/未焊缝, 体素重建保证水密 ──────
def heal_gear_meshes():
    import trimesh
    healed = {}
    for n, pitch in [("Pinion", 0.08), ("SpurGear", 0.15)]:
        raw = os.path.join(STL_DIR, n + ".stl")
        m = trimesh.load(raw)
        if m.is_watertight:
            healed[n] = {"watertight": True, "method": "none"}
            continue
        v = m.voxelized(pitch=pitch).fill()
        r = v.marching_cubes
        r.apply_scale(pitch)
        r.apply_translation(v.bounds[0])
        r = trimesh.smoothing.filter_taubin(r, iterations=8)
        r = r.simplify_quadric_decimation(face_count=20000)
        if r.is_watertight:
            r.export(raw)
        healed[n] = {"watertight": bool(r.is_watertight),
                     "method": "voxel_remesh(pitch=%g)" % pitch,
                     "volume_mm3": round(float(r.volume), 1),
                     "faces": len(r.faces)}
    return healed


def final_stl_watertight():
    import trimesh
    res = {}
    for f in sorted(os.listdir(STL_DIR)):
        if f.endswith(".stl") and not f.endswith("_raw.stl"):
            m = trimesh.load(os.path.join(STL_DIR, f))
            res[f[:-4]] = bool(m.is_watertight)
    return res


# ── 3. 电机电气 + 整车动力学(纵向 ODE) ───────────────────────────────────
def drivetrain_dynamics(total_mass_g):
    # FA-130 典型电气参数 @3V (万宝至数据表量级)
    V = 3.0                    # 2×AA
    rpm_nl, i_nl = 16000.0, 0.20        # 空载
    stall_T_gcm, i_stall = 36.0, 2.10   # 堵转 36 g·cm
    stall_T = stall_T_gcm * 9.80665e-5  # N·m
    R = V / i_stall
    Ke = (V - i_nl * R) / (rpm_nl * 2 * math.pi / 60)   # V·s/rad
    Kt = stall_T / i_stall                              # N·m/A
    ratio, eta = 4.0, 0.85
    wheel_R = 0.018
    m_kg = total_mass_g / 1000.0
    Crr = 0.015                                          # 橡胶/硬地滚阻
    dt, t, x, v = 1e-3, 0.0, 0.0, 0.0
    t_1m = None
    for _ in range(int(20 / dt)):
        w_motor = v / wheel_R * ratio
        i = (V - Ke * w_motor) / R
        F = max(Kt * i * ratio * eta / wheel_R, 0.0) - Crr * m_kg * 9.81
        v = max(v + F / m_kg * dt, 0.0)
        x += v * dt
        t += dt
        if t_1m is None and x >= 1.0:
            t_1m = t
        if F < 1e-4 and t > 1.0:
            break
    v_top = v
    # 爬坡度: Kt*i*ratio*eta/R_w = m g (sinθ + Crr cosθ), 低速 i≈i_stall*0.8
    F_max = Kt * (0.8 * i_stall) * ratio * eta / wheel_R
    grade = math.degrees(math.asin(min((F_max / (m_kg * 9.81)) - Crr, 1.0)))
    # 续航: 巡航电流≈(i_nl+0.5*(i_stall-i_nl)*Crr痕迹)取 0.45A, 2000mAh
    i_cruise = 0.45
    runtime_min = 2.0 / i_cruise * 60
    return dict(V=V, R_ohm=round(R, 3), Ke=round(Ke, 6), Kt=round(Kt, 6),
                ratio=ratio, eta=eta, mass_kg=round(m_kg, 3),
                top_speed_m_s=round(v_top, 2), top_speed_km_h=round(v_top * 3.6, 2),
                accel_0_1m_s=round(t_1m, 2) if t_1m else None,
                max_grade_deg=round(grade, 1),
                est_runtime_min=round(runtime_min, 0))


if __name__ == "__main__":
    parts = export_and_check()
    healed = heal_gear_meshes()
    wt = final_stl_watertight()
    bad = [n for n, ok in wt.items() if not ok]
    eng = json.load(open(os.path.join(HERE, "toycar_v2_engineering.json")))
    dyn = drivetrain_dynamics(eng["total_mass_g"])
    report = {"printability": parts, "gear_mesh_heal": healed,
              "stl_watertight": wt, "non_watertight": bad, "dynamics": dyn}
    with open(os.path.join(HERE, "toycar_v21_report.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("STL 导出:", len(parts), "件 · 非水密:", bad or "无")
    print("动力学: 极速 %.2f km/h · 0-1m %.2fs · 爬坡 %.1f° · 续航 ~%d min"
          % (dyn["top_speed_km_h"], dyn["accel_0_1m_s"] or -1,
             dyn["max_grade_deg"], dyn["est_runtime_min"]))
