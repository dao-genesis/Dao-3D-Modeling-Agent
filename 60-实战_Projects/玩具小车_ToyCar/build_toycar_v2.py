# -*- coding: utf-8 -*-
"""玩具小车 v2 · 真实电动玩具车装配 · 反者道之动
================================================
推翻 v1 純拼凑，按真实 1:18 级电动玩具车结构重建：
车架底盘 / 130 型直流电机 + 电机座 / 齿轮减速(真渐开线齿形 z10:z40, m0.5) /
传动轴 + 轴承座(间隙配合 +0.3mm) / 轮毂+轮胎 + 轴端挡圈 / 车壳。

工具链复用(非从零)：
- 几何一律走桥接 POST /ops → 10-反笙_FreeCAD/freecad_backend.run_ops
  (make_gear_spur 真渐开线 / make_enclosure / cut / fuse / rotate / translate)
- 工程核算走 00-本源_Origin/dao_kinematics
  (齿轮系 FK / 转子平衡 / 轴临界转速 / 离心载荷)
- GUI 展示与动画走 POST /exec (FreeCAD 本体在插件面板内实时渲染)

运行: python3 build_toycar_v2.py   (桥接 http://127.0.0.1:18920 需在线)
产物: ToyCarV2.FCStd / .step / .stl / toycar_v2_engineering.json / ToyCarV2_iso.png
"""
import json
import math
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:18920"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "v2_parts")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, os.path.join(ROOT, "00-本源_Origin"))

import dao_kinematics as dk  # noqa: E402


def api(path, body, timeout=180):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    if not r.get("ok", True):
        raise RuntimeError(f"{path}: {r}")
    return r


def ops(op_list):
    r = api("/ops", {"ops": op_list})
    res = r.get("result", r)
    if res.get("errors"):
        raise RuntimeError(f"/ops errors: {res['errors']}")
    return res


def fc(code):
    return api("/exec", {"code": code})


def stage(name, fn):
    t0 = time.time()
    out = fn()
    print(f"✓ {name} ({time.time()-t0:.1f}s)")
    return out


# ── 工程参数(对标市售 1:18 电动玩具车) ──────────────────────────────────
P = dict(
    wheel_R=18.0, wheel_W=14.0, hub_R=7.0,          # 轮胎 Ø36×14, 轮毂 Ø14
    axle_R=2.0, axle_L=92.0,                        # 传动轴 Ø4×92
    bore_clearance=0.3,                             # 间隙配合(轴承/轮毂孔 +0.3)
    wheelbase=100.0, axle_z=18.0,                   # 轴距 100, 轴心高=轮半径
    chassis=dict(L=150.0, W=56.0, T=4.0, z0=30.0),  # 底盘板 150×56×4, 底面 z=30
    gear=dict(m=0.5, z_pinion=10, z_spur=40, width=5.0, backlash=0.15),
    motor=dict(body_R=10.0, body_L=25.0, shaft_R=1.0, shaft_L=9.0,
               rpm_noload=16000.0, rpm_loaded=8000.0, mass_kg=0.018),
    density_abs=1.05e-3, density_steel=7.85e-3,     # g/mm3
)
G = P["gear"]
CD = G["m"] * (G["z_pinion"] + G["z_spur"]) / 2.0 + G["backlash"]  # 中心距+侧隙
REAR_X, FRONT_X = -P["wheelbase"] / 2, P["wheelbase"] / 2
MOTOR_X = REAR_X - CD  # 电机轴与后轴平行, 相距中心距
AXZ = P["axle_z"]
BORE_R = P["axle_R"] + P["bore_clearance"] / 2

EXPORTS = {}


def part(pid, op_list, final_id):
    """经 /ops 构建零件并导出 brep 到 v2_parts/"""
    path = os.path.join(OUT, pid + ".brep")
    ops(op_list + [{"op": "export_brep", "shape": final_id, "path": path}])
    EXPORTS[pid] = path
    return path


# ── S1 车架底盘: 板 + 4 轴承座塔(间隙孔) + 电机安装口 ────────────────────
def s1_chassis():
    c = P["chassis"]
    o = [
        {"op": "make_rounded_box", "id": "plate", "L": c["L"], "W": c["W"],
         "H": c["T"], "R": 6},
        {"op": "translate", "id": "plate2", "shape": "plate",
         "delta": [-c["L"] / 2, -c["W"] / 2, c["z0"]]},
    ]
    towers, holes = [], []
    for i, (ax, ay) in enumerate([(REAR_X, -25), (REAR_X, 25),
                                  (FRONT_X, -25), (FRONT_X, 25)]):
        o += [
            {"op": "make_box", "id": f"tw{i}", "L": 12, "W": 8, "H": c["z0"] - 12,
             "pos": [ax - 6, ay - 4, 12]},
            {"op": "make_cylinder", "id": f"bo{i}", "R": BORE_R, "H": 10,
             "pos": [ax, ay - 5, AXZ], "axis": [0, 1, 0]},
        ]
        towers.append(f"tw{i}")
        holes.append(f"bo{i}")
    o += [
        {"op": "fuse", "id": "frame", "shapes": ["plate2"] + towers},
        {"op": "cut", "id": "chassis", "base": "frame", "tools": holes},
    ]
    return part("Chassis", o, "chassis")


# ── S2 130 电机 + 电机座(半圆抱箍) ───────────────────────────────────────
def s2_motor():
    m = P["motor"]
    part("Motor", [
        {"op": "make_cylinder", "id": "body", "R": m["body_R"], "H": m["body_L"],
         "pos": [MOTOR_X, -12.5, AXZ], "axis": [0, 1, 0]},
        {"op": "make_cylinder", "id": "shaft", "R": m["shaft_R"], "H": m["shaft_L"],
         "pos": [MOTOR_X, -12.5 - m["shaft_L"], AXZ], "axis": [0, 1, 0]},
        {"op": "fuse", "id": "motor", "shapes": ["body", "shaft"]},
    ], "motor")
    c = P["chassis"]
    part("MotorMount", [
        {"op": "make_box", "id": "cr", "L": 20, "W": 8, "H": c["z0"] - 8,
         "pos": [MOTOR_X - 10, -10, 8]},
        {"op": "make_cylinder", "id": "crb", "R": m["body_R"] + 0.15,
         "H": 25, "pos": [MOTOR_X, -12.5, AXZ], "axis": [0, 1, 0]},
        {"op": "cut", "id": "mount", "base": "cr", "tools": ["crb"]},
    ], "mount")


# ── S3 齿轮副: 真渐开线 z10 小齿轮(电机轴) + z40 大齿轮(后轴) ─────────────
def s3_gears():
    # 小齿轮: 轴向 y, 中心 (MOTOR_X, 0, AXZ); 旋转半齿距错齿啮合
    part("Pinion", [
        {"op": "make_gear_spur", "id": "pg", "teeth": G["z_pinion"],
         "module": G["m"], "width": G["width"], "hub_r": P["motor"]["shaft_R"] + 0.05},
        {"op": "rotate", "id": "pg1", "shape": "pg", "base": [0, 0, 0],
         "axis": [0, 0, 1], "angle": 180.0 / G["z_pinion"]},
        {"op": "rotate", "id": "pg2", "shape": "pg1", "base": [0, 0, 0],
         "axis": [1, 0, 0], "angle": -90},
        {"op": "translate", "id": "pinion", "shape": "pg2",
         "delta": [MOTOR_X, -17.5 - G["width"] / 2, AXZ]},
    ], "pinion")
    part("SpurGear", [
        {"op": "make_gear_spur", "id": "sg", "teeth": G["z_spur"],
         "module": G["m"], "width": G["width"], "hub_r": BORE_R},
        {"op": "rotate", "id": "sg2", "shape": "sg", "base": [0, 0, 0],
         "axis": [1, 0, 0], "angle": -90},
        {"op": "translate", "id": "spur", "shape": "sg2",
         "delta": [REAR_X, -17.5 - G["width"] / 2, AXZ]},
    ], "spur")


# ── S4 前后传动轴(轴端挡圈) + 四轮(轮毂+轮胎+间隙孔) ─────────────────────
def s4_axles_wheels():
    for pid, ax in (("AxleRear", REAR_X), ("AxleFront", FRONT_X)):
        L = P["axle_L"]
        part(pid, [
            {"op": "make_cylinder", "id": "sh", "R": P["axle_R"], "H": L,
             "pos": [ax, -L / 2, AXZ], "axis": [0, 1, 0]},
            {"op": "make_cylinder", "id": "c1", "R": 4, "H": 1.5,
             "pos": [ax, -L / 2, AXZ], "axis": [0, 1, 0]},
            {"op": "make_cylinder", "id": "c2", "R": 4, "H": 1.5,
             "pos": [ax, L / 2 - 1.5, AXZ], "axis": [0, 1, 0]},
            {"op": "fuse", "id": "axle", "shapes": ["sh", "c1", "c2"]},
        ], "axle")
    for pid, ax, ay in (("WheelRL", REAR_X, 30), ("WheelRR", REAR_X, -44),
                        ("WheelFL", FRONT_X, 30), ("WheelFR", FRONT_X, -44)):
        W, R, hub = P["wheel_W"], P["wheel_R"], P["hub_R"]
        part(pid, [
            {"op": "make_hollow_cylinder", "id": "tire", "R_out": R,
             "R_in": hub - 1, "H": W},
            {"op": "make_cylinder", "id": "hubc", "R": hub, "H": W},
            {"op": "fuse", "id": "wf", "shapes": ["tire", "hubc"]},
            {"op": "make_cylinder", "id": "wb", "R": BORE_R, "H": W + 2,
             "pos": [0, 0, -1]},
            {"op": "cut", "id": "wc", "base": "wf", "tools": ["wb"]},
            {"op": "rotate", "id": "wr", "shape": "wc", "base": [0, 0, 0],
             "axis": [1, 0, 0], "angle": -90},
            {"op": "translate", "id": "wheel", "shape": "wr",
             "delta": [ax, ay, AXZ]},
        ], "wheel")


# ── S5 车壳(开底罩壳+驾驶舱) ────────────────────────────────────────────
def s5_shell():
    c = P["chassis"]
    z_top = c["z0"] + c["T"]
    part("BodyShell", [
        {"op": "make_enclosure", "id": "sh0", "L": c["L"], "W": c["W"], "H": 26,
         "wall": 2, "open_top": True},
        {"op": "rotate", "id": "sh1", "shape": "sh0", "base": [0, 0, 13],
         "axis": [1, 0, 0], "angle": 180},   # 翻成开底
        {"op": "translate", "id": "sh2", "shape": "sh1",
         "delta": [-c["L"] / 2, c["W"] / 2, z_top]},
        {"op": "make_rounded_box", "id": "cab", "L": 60, "W": c["W"] - 8,
         "H": 22, "R": 5},
        {"op": "translate", "id": "cab2", "shape": "cab",
         "delta": [-40, -(c["W"] - 8) / 2, z_top + 26 - 2]},
        {"op": "fuse", "id": "shell", "shapes": ["sh2", "cab2"]},
    ], "shell")


# ── S6 汇入 GUI 文档(面板内实时可见) ─────────────────────────────────────
COLORS = {
    "Chassis": (0.55, 0.57, 0.6), "Motor": (0.85, 0.6, 0.1),
    "MotorMount": (0.35, 0.35, 0.4), "Pinion": (0.9, 0.2, 0.2),
    "SpurGear": (0.2, 0.45, 0.9), "AxleRear": (0.75, 0.75, 0.78),
    "AxleFront": (0.75, 0.75, 0.78), "WheelRL": (0.12, 0.12, 0.12),
    "WheelRR": (0.12, 0.12, 0.12), "WheelFL": (0.12, 0.12, 0.12),
    "WheelFR": (0.12, 0.12, 0.12), "BodyShell": (0.8, 0.15, 0.1),
}


def s6_document():
    fc(f"""
import FreeCAD as App, FreeCADGui as Gui, Part, json
for d in list(App.listDocuments()):
    App.closeDocument(d)
doc = App.newDocument("ToyCarV2")
parts = json.loads(r'''{json.dumps(EXPORTS, ensure_ascii=False)}''')
colors = json.loads('''{json.dumps({k: list(v) for k, v in COLORS.items()})}''')
for name, path in parts.items():
    sh = Part.Shape(); sh.read(path)
    o = doc.addObject("Part::Feature", name); o.Shape = sh
    o.ViewObject.ShapeColor = tuple(colors[name])
doc.recompute()
Gui.activeDocument().activeView().viewIsometric()
Gui.SendMsgToActiveView("ViewFit")
""")


# ── S7 工程核算: 齿轮系 FK / 干涉 / 质量 / 平衡 / 临界转速 ───────────────
def s7_engineering():
    ratio = G["z_spur"] / G["z_pinion"]
    m = P["motor"]
    wheel_rpm = m["rpm_loaded"] / ratio
    speed = 2 * math.pi * P["wheel_R"] / 1000 * wheel_rpm / 60  # m/s

    mech = dk.Mechanism("ToyCarV2", root_link="chassis")
    mech.add_link(dk.Link("chassis"))
    for name, x in (("motor_rotor", MOTOR_X), ("rear_axle", REAR_X),
                    ("front_axle", FRONT_X)):
        mech.add_link(dk.Link(name))
        mech.add_joint(dk.Joint("j_" + name, "revolute", parent="chassis",
                                child=name,
                                origin=dk.SE3.from_translation(dk.v3(x, 0, AXZ)),
                                axis=dk.v3(0, 1, 0)))
    q_motor = 8 * math.pi                     # 电机转 4 圈
    q_rear = q_motor / ratio                  # 齿轮耦合: 后轴 = 电机/减速比
    mech.set_q([q_motor, q_rear, q_rear])
    dk.forward_kinematics(mech)

    wheel_mass = 0.030
    balance = dk.analyze_balance_rotating(
        rotor_mass_kg=2 * wheel_mass + 0.008, rpm=wheel_rpm,
        hammer_mass_kg=0.002, hammer_cm_radius_mm=P["wheel_R"] * 0.6)
    critical = dk.analyze_critical_speed_dunkerley(
        shaft_diameter_mm=2 * P["axle_R"], shaft_length_mm=P["axle_L"],
        working_rpm=wheel_rpm,
        masses_xloc=[(wheel_mass, 8.0), (0.008, P["axle_L"] / 2),
                     (wheel_mass, P["axle_L"] - 8.0)])
    centrifugal = dk.analyze_centrifugal_load(
        wheel_mass, P["wheel_R"] * 0.6, wheel_rpm,
        pin_diameter_mm=2 * P["axle_R"])

    r = fc("""
import FreeCAD as App, json
doc = App.getDocument("ToyCarV2")
objs = [o for o in doc.Objects if hasattr(o, "Shape")]
inter = []
for i in range(len(objs)):
    for j in range(i+1, len(objs)):
        try:
            c = objs[i].Shape.common(objs[j].Shape)
            if c.Volume > 0.05:
                inter.append([objs[i].Name, objs[j].Name, round(c.Volume, 2)])
        except Exception:
            pass
mass = {}
for o in objs:
    dens = 7.85e-3 if o.Name.startswith(("Axle","Motor","Pinion","SpurGear")) else 1.05e-3
    if o.Name == "Motor": continue
    s = o.Shape
    mass[o.Name] = round(s.Volume * dens, 2)
__result__ = json.dumps({"interference": inter, "mass_g": mass})
""")
    chk = json.loads(r["result"])
    total_mass = sum(chk["mass_g"].values()) + m["mass_kg"] * 1000

    report = {
        "design": {"scale": "~1:18", "wheelbase_mm": P["wheelbase"],
                   "track_mm": 74, "wheel_dia_mm": 2 * P["wheel_R"],
                   "fit_clearance_mm": P["bore_clearance"]},
        "gear_train": {"module": G["m"], "z_pinion": G["z_pinion"],
                       "z_spur": G["z_spur"], "ratio": ratio,
                       "center_distance_mm": CD,
                       "backlash_mm": G["backlash"]},
        "performance": {"motor_rpm_loaded": m["rpm_loaded"],
                        "wheel_rpm": round(wheel_rpm, 1),
                        "speed_m_s": round(speed, 2),
                        "speed_km_h": round(speed * 3.6, 2)},
        "kinematics": {"dof": mech.dof() if hasattr(mech, "dof") else 3,
                       "motor_turns": q_motor / (2 * math.pi),
                       "axle_turns": q_rear / (2 * math.pi),
                       "coupling": "q_axle = q_motor / %.1f" % ratio},
        "rotor_balance": balance.__dict__ if hasattr(balance, "__dict__") else str(balance),
        "critical_speed": critical.__dict__ if hasattr(critical, "__dict__") else str(critical),
        "centrifugal": centrifugal.__dict__ if hasattr(centrifugal, "__dict__") else str(centrifugal),
        "interference": chk["interference"],
        "mass_g": chk["mass_g"],
        "total_mass_g": round(total_mass, 1),
    }
    with open(os.path.join(HERE, "toycar_v2_engineering.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    print("  减速比 %.0f:1 · 轮速 %.0f rpm · 车速 %.2f km/h · 干涉 %s · 总质量 %.0f g"
          % (ratio, wheel_rpm, speed * 3.6, chk["interference"], total_mass))
    return chk["interference"]


# ── S8 传动动画: 电机→小齿轮→大齿轮→后轴→车轮, 整车前行 ─────────────────
def s8_animation():
    ratio = G["z_spur"] / G["z_pinion"]
    fc(f"""
import FreeCAD as App, FreeCADGui as Gui, math, time
doc = App.getDocument("ToyCarV2")
axleset = ["SpurGear", "AxleRear", "WheelRL", "WheelRR"]
front = ["AxleFront", "WheelFL", "WheelFR"]
still = ["Chassis", "Motor", "MotorMount", "BodyShell"]
objs = {{o.Name: o for o in doc.Objects}}
base0 = {{n: App.Vector(objs[n].Placement.Base) for n in objs}}
rot0 = {{n: App.Rotation(objs[n].Placement.Rotation) for n in objs}}
axis_x = {{}}
for n in axleset: axis_x[n] = {REAR_X}
for n in front: axis_x[n] = {FRONT_X}
axis_x["Pinion"] = {MOTOR_X}
R = {P['wheel_R']}; travel = 120.0; steps = 60; ratio = {ratio}
for i in range(1, steps + 1):
    dx = travel * i / steps
    ang = math.degrees(dx / R)
    for n, o in objs.items():
        spin = ang * ratio if n == "Pinion" else (ang if n in axis_x else 0.0)
        shift = App.Vector(dx, 0, 0)
        if spin:
            c = App.Vector(axis_x[n], 0, {AXZ})  # 绕自身轴线旋转后随车前移
            rot = App.Rotation(App.Vector(0, 1, 0), -spin)
            o.Placement = App.Placement(
                shift + c - rot.multVec(c) + base0[n], rot.multiply(rot0[n]))
        else:
            o.Placement = App.Placement(base0[n] + shift, rot0[n])
    doc.recompute(); Gui.updateGui(); time.sleep(0.1)
for n, o in objs.items():
    o.Placement = App.Placement(base0[n], rot0[n])
doc.recompute()
Gui.SendMsgToActiveView("ViewFit")
""", )


# ── S9 导出 ─────────────────────────────────────────────────────────────
def s9_export():
    fc(f"""
import FreeCAD as App, FreeCADGui as Gui, Part
doc = App.getDocument("ToyCarV2")
doc.saveAs(r"{os.path.join(HERE, 'ToyCarV2.FCStd')}")
objs = [o for o in doc.Objects if hasattr(o, "Shape")]
Part.export(objs, r"{os.path.join(HERE, 'ToyCarV2.step')}")
import Mesh
Mesh.export(objs, r"{os.path.join(HERE, 'ToyCarV2.stl')}")
Gui.activeDocument().activeView().viewIsometric()
Gui.SendMsgToActiveView("ViewFit")
Gui.activeDocument().activeView().saveImage(r"{os.path.join(HERE, 'ToyCarV2_iso.png')}", 1280, 960, "White")
""")


if __name__ == "__main__":
    st = json.loads(urllib.request.urlopen(BASE + "/status", timeout=10).read())
    print("桥接:", BASE, "FreeCAD:", st.get("freecad", "?"))
    stage("S1 车架底盘(轴承座塔+间隙孔)", s1_chassis)
    stage("S2 130电机+抱箍电机座", s2_motor)
    stage("S3 渐开线齿轮副 z10:z40 m0.5", s3_gears)
    stage("S4 前后传动轴+四轮(轮毂/轮胎/挡圈)", s4_axles_wheels)
    stage("S5 车壳+驾驶舱", s5_shell)
    stage("S6 汇入 GUI 文档", s6_document)
    inter = stage("S7 工程核算(齿轮系FK/干涉/质量/平衡/临界转速)", s7_engineering)
    stage("S8 传动链动画(电机→齿轮→轴→轮)", s8_animation)
    stage("S9 导出 FCStd/STEP/STL/截图", s9_export)
    print("玩具小车 v2 · 全阶段完成 · 干涉:", inter)
