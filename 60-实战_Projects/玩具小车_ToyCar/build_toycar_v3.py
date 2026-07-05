# -*- coding: utf-8 -*-
"""玩具小车 v3 · 真实电动汽车架构 1:18 缩小 · 道法自然
====================================================
在 v2 基础上按真实电动汽车逻辑重构（滑板底盘 + 动力总成 + 车壳三分体）：
- S1 滑板底盘: 地板 + 电池仓围壁 + PCB 安装柱 + 轴承塔 + 电机沉窝/齿轮槽
- S2 动力总成: 130 电机(横置) + 抱箍座 + 渐开线齿轮 z10:z40 (4:1)
- S3 传动轴 + 四轮(轮毂/轮胎/挡圈/间隙配合 +0.3)
- S4 电池组 + PCB 控制板(1:1 安装接口: 仓壁贴合 / 立柱支撑)
- S5 车壳: 真车轮廓(腰线/驾驶舱/挡风玻璃/侧窗/轮拱/前脸格栅/尾灯)
- S5b 引擎盖: 独立检修面板(与车壳 common/cut 分割)
- S6 汇入 GUI · S7 干涉核算(目标 0 干涉) · S8 渲染 iso/front/side/爆炸图 · S9 导出

运行: python3 build_toycar_v3.py   (桥接 http://127.0.0.1:18920 需在线)
产物: ToyCarV3.FCStd / .step / .stl / v3_parts/*.brep / ToyCarV3_{iso,front,side,exploded}.png
      toycar_v3_engineering.json
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
OUT = os.path.join(HERE, "v3_parts")
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


# ── 工程参数(1:18 真实电动车架构缩小) ───────────────────────────────────
P = dict(
    wheel_R=18.0, wheel_W=12.0, hub_R=7.0,          # 轮胎 Ø36×12
    axle_R=2.0, axle_L=92.0,                        # 传动轴 Ø4×92
    bore_clearance=0.3,                             # 间隙配合 +0.3
    wheelbase=130.0, axle_z=18.0,                   # 轴距 130(真车比例)
    floor=dict(L=160.0, W=60.0, z0=8.0, z1=12.0),   # 滑板底盘地板
    gear=dict(m=0.5, z_pinion=10, z_spur=40, width=5.0, backlash=0.15),
    motor=dict(body_R=10.0, body_L=25.0, shaft_R=1.0, shaft_L=9.0,
               rpm_noload=16000.0, rpm_loaded=8000.0, mass_kg=0.018),
    battery=dict(x0=-41.0, x1=9.0, y=18.0, z0=12.0, z1=24.0),  # 中置电池组
    pcb=dict(x0=30.0, x1=58.0, y=14.0, z0=17.0, z1=19.0),      # 前舱控制板
    density_abs=1.05e-3, density_steel=7.85e-3,
)
G = P["gear"]
CD = G["m"] * (G["z_pinion"] + G["z_spur"]) / 2.0 + G["backlash"]
REAR_X, FRONT_X = -P["wheelbase"] / 2, P["wheelbase"] / 2
MOTOR_X = REAR_X - CD                    # 后置横置电机, 平行后轴
AXZ = P["axle_z"]
BORE_R = P["axle_R"] + P["bore_clearance"] / 2
FL = P["floor"]
SPUR_TIP_R = G["m"] * (G["z_spur"] + 2) / 2.0

EXPORTS = {}


def part(pid, op_list, final_id):
    path = os.path.join(OUT, pid + ".brep")
    ops(op_list + [{"op": "export_brep", "shape": final_id, "path": path}])
    EXPORTS[pid] = path
    return path


# ── S1 滑板底盘: 地板+电池仓围壁+PCB柱+轴承塔+电机沉窝/齿轮槽 ───────────
def s1_chassis():
    b, p = P["battery"], P["pcb"]
    o = [
        {"op": "make_rounded_box", "id": "fl", "L": FL["L"], "W": FL["W"],
         "H": FL["z1"] - FL["z0"], "R": 6},
        {"op": "translate", "id": "floor", "shape": "fl",
         "delta": [-FL["L"] / 2, -FL["W"] / 2, FL["z0"]]},
    ]
    add, holes = ["floor"], []
    # 轴承塔 y=±26(塔宽8: y 22..30), z12..24, 孔 z18
    for i, (ax, ay) in enumerate([(REAR_X, -26), (REAR_X, 26),
                                  (FRONT_X, -26), (FRONT_X, 26)]):
        o += [
            {"op": "make_box", "id": f"tw{i}", "L": 12, "W": 8, "H": 12,
             "pos": [ax - 6, ay - 4, FL["z1"]]},
            {"op": "make_cylinder", "id": f"bo{i}", "R": BORE_R, "H": 10,
             "pos": [ax, ay - 5, AXZ], "axis": [0, 1, 0]},
        ]
        add.append(f"tw{i}")
        holes.append(f"bo{i}")
    # 电池仓围壁(与电池组贴合不叠)
    o += [
        {"op": "make_box", "id": "bw0", "L": 3, "W": 2 * b["y"], "H": 10,
         "pos": [b["x0"] - 3, -b["y"], FL["z1"]]},
        {"op": "make_box", "id": "bw1", "L": 3, "W": 2 * b["y"], "H": 10,
         "pos": [b["x1"], -b["y"], FL["z1"]]},
        {"op": "make_box", "id": "bw2", "L": b["x1"] - b["x0"] + 6, "W": 3,
         "H": 10, "pos": [b["x0"] - 3, -b["y"] - 3, FL["z1"]]},
        {"op": "make_box", "id": "bw3", "L": b["x1"] - b["x0"] + 6, "W": 3,
         "H": 10, "pos": [b["x0"] - 3, b["y"], FL["z1"]]},
    ]
    add += ["bw0", "bw1", "bw2", "bw3"]
    # PCB 安装柱 ×4 (z12..17, 顶面承托 PCB)
    for i, (px, py) in enumerate([(p["x0"] + 3, -p["y"] + 3), (p["x0"] + 3, p["y"] - 3),
                                  (p["x1"] - 3, -p["y"] + 3), (p["x1"] - 3, p["y"] - 3)]):
        o.append({"op": "make_cylinder", "id": f"st{i}", "R": 2.0,
                  "H": p["z0"] - FL["z1"], "pos": [px, py, FL["z1"]]})
        add.append(f"st{i}")
    # 电机沉窝(电机体 z8..28 贯穿地板) + 大齿轮槽(齿顶圆 z7.5..28.5)
    o += [
        {"op": "make_box", "id": "mp", "L": 2 * P["motor"]["body_R"] + 2.5,
         "W": P["motor"]["body_L"] + 3, "H": FL["z1"] - FL["z0"] + 2,
         "pos": [MOTOR_X - P["motor"]["body_R"] - 1.25, -14, FL["z0"] - 1]},
        {"op": "make_box", "id": "gp", "L": 2 * SPUR_TIP_R + 2,
         "W": G["width"] + 2.5, "H": FL["z1"] - FL["z0"] + 2,
         "pos": [REAR_X - SPUR_TIP_R - 1, -21.25, FL["z0"] - 1]},
        {"op": "fuse", "id": "frame", "shapes": add},
        {"op": "cut", "id": "chassis", "base": "frame",
         "tools": holes + ["mp", "gp"]},
    ]
    return part("Chassis", o, "chassis")


# ── S2 动力总成: 130 电机 + 抱箍座 + 齿轮副 ─────────────────────────────
def s2_powertrain():
    m = P["motor"]
    part("Motor", [
        {"op": "make_cylinder", "id": "body", "R": m["body_R"], "H": m["body_L"],
         "pos": [MOTOR_X, -12.5, AXZ], "axis": [0, 1, 0]},
        {"op": "make_cylinder", "id": "shaft", "R": m["shaft_R"], "H": m["shaft_L"],
         "pos": [MOTOR_X, -12.5 - m["shaft_L"], AXZ], "axis": [0, 1, 0]},
        {"op": "fuse", "id": "motor", "shapes": ["body", "shaft"]},
    ], "motor")
    part("MotorMount", [
        {"op": "make_box", "id": "cr", "L": 24, "W": 8, "H": 18,
         "pos": [MOTOR_X - 12, 4, FL["z1"]]},
        {"op": "make_cylinder", "id": "crb", "R": m["body_R"] + 0.15,
         "H": 10, "pos": [MOTOR_X, 3, AXZ], "axis": [0, 1, 0]},
        {"op": "make_cylinder", "id": "cra", "R": 4.5,
         "H": 10, "pos": [REAR_X, 3, AXZ], "axis": [0, 1, 0]},
        {"op": "cut", "id": "mount", "base": "cr", "tools": ["crb", "cra"]},
    ], "mount")
    part("Pinion", [
        {"op": "make_gear_spur", "id": "pg", "teeth": G["z_pinion"],
         "module": G["m"], "width": G["width"], "hub_r": m["shaft_R"] + 0.05},
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


# ── S3 传动轴 + 四轮 ────────────────────────────────────────────────────
def s3_axles_wheels():
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
    for pid, ax, ay in (("WheelRL", REAR_X, 32), ("WheelRR", REAR_X, -44),
                        ("WheelFL", FRONT_X, 32), ("WheelFR", FRONT_X, -44)):
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


# ── S4 电池组 + PCB(1:1 安装接口) ──────────────────────────────────────
def s4_battery_pcb():
    b, p = P["battery"], P["pcb"]
    part("BatteryPack", [
        {"op": "make_rounded_box", "id": "bp", "L": b["x1"] - b["x0"],
         "W": 2 * b["y"], "H": b["z1"] - b["z0"], "R": 2},
        {"op": "translate", "id": "batt", "shape": "bp",
         "delta": [b["x0"], -b["y"], b["z0"]]},
    ], "batt")
    part("PCB", [
        {"op": "make_box", "id": "pl", "L": p["x1"] - p["x0"], "W": 2 * p["y"],
         "H": p["z1"] - p["z0"], "pos": [p["x0"], -p["y"], p["z0"]]},
        {"op": "make_box", "id": "chip", "L": 8, "W": 8, "H": 2,
         "pos": [(p["x0"] + p["x1"]) / 2 - 4, -4, p["z1"]]},
        {"op": "fuse", "id": "pcb", "shapes": ["pl", "chip"]},
    ], "pcb")


# ── S5 车壳: 真车轮廓 ───────────────────────────────────────────────────
BODY_Z0, BELT_Z, ROOF_Z = 24.0, 46.0, 64.0
BODY_Y = 28.0
HOOD = dict(x0=30.0, x1=81.0, z0=42.0)


def s5_shell():
    o = [
        # 下车体(腰线以下)
        {"op": "make_rounded_box", "id": "lb", "L": 160, "W": 2 * BODY_Y,
         "H": BELT_Z - BODY_Z0, "R": 7},
        {"op": "translate", "id": "low", "shape": "lb",
         "delta": [-80, -BODY_Y, BODY_Z0]},
        # 驾驶舱(温室)
        {"op": "make_rounded_box", "id": "gh", "L": 62, "W": 2 * (BODY_Y - 6),
         "H": ROOF_Z - BELT_Z + 2, "R": 6},
        {"op": "translate", "id": "cab", "shape": "gh",
         "delta": [-37, -(BODY_Y - 6), BELT_Z - 2]},
        {"op": "fuse", "id": "raw", "shapes": ["low", "cab"]},
        # 挡风玻璃斜切(前 42°)
        {"op": "make_box", "id": "ws", "L": 40, "W": 70, "H": 30,
         "pos": [25, -35, BELT_Z - 1]},
        {"op": "rotate", "id": "wsr", "shape": "ws", "base": [25, 0, BELT_Z - 1],
         "axis": [0, 1, 0], "angle": -42},
        # 后窗斜切(缓 35°)
        {"op": "make_box", "id": "rw", "L": 40, "W": 70, "H": 30,
         "pos": [-77, -35, BELT_Z - 1]},
        {"op": "rotate", "id": "rwr", "shape": "rw", "base": [-37, 0, BELT_Z - 1],
         "axis": [0, 1, 0], "angle": 35},
        # 侧窗
        {"op": "make_box", "id": "sw1", "L": 24, "W": 2 * BODY_Y + 4, "H": 12,
         "pos": [-8, -BODY_Y - 2, BELT_Z + 2]},
        {"op": "make_box", "id": "sw2", "L": 20, "W": 2 * BODY_Y + 4, "H": 12,
         "pos": [-34, -BODY_Y - 2, BELT_Z + 2]},
        # 轮拱 ×2 (贯通 y)
        {"op": "make_cylinder", "id": "ar", "R": 22, "H": 2 * BODY_Y + 8,
         "pos": [REAR_X, -BODY_Y - 4, AXZ], "axis": [0, 1, 0]},
        {"op": "make_cylinder", "id": "af", "R": 22, "H": 2 * BODY_Y + 8,
         "pos": [FRONT_X, -BODY_Y - 4, AXZ], "axis": [0, 1, 0]},
        # 内腔挖空(壁厚 2.5, 罩住底盘上装)
        {"op": "make_box", "id": "cav", "L": 155, "W": 2 * BODY_Y - 5,
         "H": BELT_Z - BODY_Z0 - 2.5, "pos": [-77.5, -BODY_Y + 2.5, BODY_Z0 - 1]},
        # 前脸格栅凹槽 + 尾部内收
        {"op": "make_box", "id": "gr", "L": 3, "W": 30, "H": 8,
         "pos": [79, -15, 30]},
        {"op": "cut", "id": "shellraw", "base": "raw",
         "tools": ["wsr", "rwr", "sw1", "sw2", "ar", "af", "cav", "gr"]},
    ]
    # 头灯/尾灯(凸出小圆柱, 融合)
    for i, (lx, ly, r) in enumerate([(79.5, -19, 3), (79.5, 19, 3),
                                     (-80.5, -19, 2.5), (-80.5, 19, 2.5)]):
        o.append({"op": "make_cylinder", "id": f"lp{i}", "R": r, "H": 1.5,
                  "pos": [lx, ly, 38], "axis": [1, 0, 0]})
    o.append({"op": "fuse", "id": "shellfull",
              "shapes": ["shellraw", "lp0", "lp1", "lp2", "lp3"]})
    # 引擎盖分割: 车壳 = shellfull − hoodbox
    o += [
        {"op": "make_box", "id": "hb", "L": HOOD["x1"] - HOOD["x0"],
         "W": 2 * BODY_Y + 6, "H": 20,
         "pos": [HOOD["x0"], -BODY_Y - 3, HOOD["z0"]]},
        {"op": "cut", "id": "shell", "base": "shellfull", "tools": ["hb"]},
    ]
    return part("BodyShell", o, "shell")


# ── S5b 引擎盖: 独立检修面板 ────────────────────────────────────────────
def s5b_hood():
    o = [
        {"op": "make_rounded_box", "id": "lb", "L": 160, "W": 2 * BODY_Y,
         "H": BELT_Z - BODY_Z0, "R": 7},
        {"op": "translate", "id": "low", "shape": "lb",
         "delta": [-80, -BODY_Y, BODY_Z0]},
        {"op": "make_box", "id": "ws", "L": 40, "W": 70, "H": 30,
         "pos": [25, -35, BELT_Z - 1]},
        {"op": "rotate", "id": "wsr", "shape": "ws", "base": [25, 0, BELT_Z - 1],
         "axis": [0, 1, 0], "angle": -42},
        {"op": "make_box", "id": "cav", "L": 155, "W": 2 * BODY_Y - 5,
         "H": BELT_Z - BODY_Z0 - 2.5, "pos": [-77.5, -BODY_Y + 2.5, BODY_Z0 - 1]},
        {"op": "make_cylinder", "id": "af", "R": 22, "H": 2 * BODY_Y + 8,
         "pos": [FRONT_X, -BODY_Y - 4, AXZ], "axis": [0, 1, 0]},
        {"op": "cut", "id": "lowcut", "base": "low", "tools": ["wsr", "cav", "af"]},
        {"op": "make_box", "id": "hb", "L": HOOD["x1"] - HOOD["x0"],
         "W": 2 * BODY_Y + 6, "H": 20,
         "pos": [HOOD["x0"], -BODY_Y - 3, HOOD["z0"]]},
        {"op": "common", "id": "hood", "shapes": ["lowcut", "hb"]},
    ]
    return part("Hood", o, "hood")


# ── S6 汇入 GUI 文档 ───────────────────────────────────────────────────
COLORS = {
    "Chassis": (0.55, 0.57, 0.6), "Motor": (0.85, 0.6, 0.1),
    "MotorMount": (0.35, 0.35, 0.4), "Pinion": (0.9, 0.2, 0.2),
    "SpurGear": (0.2, 0.45, 0.9), "AxleRear": (0.75, 0.75, 0.78),
    "AxleFront": (0.75, 0.75, 0.78), "WheelRL": (0.12, 0.12, 0.12),
    "WheelRR": (0.12, 0.12, 0.12), "WheelFL": (0.12, 0.12, 0.12),
    "WheelFR": (0.12, 0.12, 0.12), "BatteryPack": (0.15, 0.55, 0.25),
    "PCB": (0.1, 0.4, 0.15), "BodyShell": (0.8, 0.15, 0.1),
    "Hood": (0.85, 0.25, 0.15),
}


def s6_document():
    fc(f"""
import FreeCAD as App, FreeCADGui as Gui, Part, json
for d in list(App.listDocuments()):
    App.closeDocument(d)
doc = App.newDocument("ToyCarV3")
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


# ── S7 干涉核算 + 工程报告 ─────────────────────────────────────────────
def s7_engineering():
    ratio = G["z_spur"] / G["z_pinion"]
    m = P["motor"]
    wheel_rpm = m["rpm_loaded"] / ratio
    speed = 2 * math.pi * P["wheel_R"] / 1000 * wheel_rpm / 60

    mech = dk.Mechanism("ToyCarV3", root_link="chassis")
    mech.add_link(dk.Link("chassis"))
    for name, x in (("motor_rotor", MOTOR_X), ("rear_axle", REAR_X),
                    ("front_axle", FRONT_X)):
        mech.add_link(dk.Link(name))
        mech.add_joint(dk.Joint("j_" + name, "revolute", parent="chassis",
                                child=name,
                                origin=dk.SE3.from_translation(dk.v3(x, 0, AXZ)),
                                axis=dk.v3(0, 1, 0)))
    q_motor = 8 * math.pi
    q_rear = q_motor / ratio
    mech.set_q([q_motor, q_rear, q_rear])
    dk.forward_kinematics(mech)

    r = fc("""
import FreeCAD as App, json
doc = App.getDocument("ToyCarV3")
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
    dens = 7.85e-3 if o.Name.startswith(("Axle","Pinion","SpurGear")) else 1.05e-3
    if o.Name == "Motor": continue
    mass[o.Name] = round(o.Shape.Volume * dens, 2)
__result__ = json.dumps({"interference": inter, "mass_g": mass})
""")
    chk = json.loads(r["result"])
    total_mass = sum(chk["mass_g"].values()) + m["mass_kg"] * 1000
    report = {
        "design": {"scale": "1:18 真车架构(滑板底盘/中置电池/前舱PCB/后横置电机)",
                   "wheelbase_mm": P["wheelbase"], "track_mm": 76,
                   "wheel_dia_mm": 2 * P["wheel_R"],
                   "fit_clearance_mm": P["bore_clearance"]},
        "gear_train": {"module": G["m"], "z_pinion": G["z_pinion"],
                       "z_spur": G["z_spur"], "ratio": ratio,
                       "center_distance_mm": CD, "backlash_mm": G["backlash"]},
        "performance": {"motor_rpm_loaded": m["rpm_loaded"],
                        "wheel_rpm": round(wheel_rpm, 1),
                        "speed_m_s": round(speed, 2),
                        "speed_km_h": round(speed * 3.6, 2)},
        "interference": chk["interference"],
        "mass_g": chk["mass_g"],
        "total_mass_g": round(total_mass, 1),
    }
    with open(os.path.join(HERE, "toycar_v3_engineering.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    print("  减速比 %.0f:1 · 轮速 %.0f rpm · 车速 %.2f km/h · 干涉 %s · 总质量 %.0f g"
          % (ratio, wheel_rpm, speed * 3.6, chk["interference"], total_mass))
    return chk["interference"]


# ── S8 渲染 iso/front/side/爆炸图 ──────────────────────────────────────
EXPLODE = {
    "BodyShell": (0, 0, 70), "Hood": (25, 0, 55), "BatteryPack": (0, 0, 32),
    "PCB": (0, 0, 42), "Motor": (-28, 0, 0), "MotorMount": (-28, 0, 18),
    "Pinion": (-28, -14, 0), "SpurGear": (0, -14, 0),
    "WheelRL": (0, 30, 0), "WheelRR": (0, -30, 0),
    "WheelFL": (0, 30, 0), "WheelFR": (0, -30, 0),
    "AxleRear": (0, 0, -18), "AxleFront": (0, 0, -18),
}


def s8_render():
    for view, code in (("iso", "viewIsometric()"), ("front", "viewFront()"),
                       ("side", "viewRight()")):
        fc(f"""
import FreeCAD as App, FreeCADGui as Gui
Gui.activeDocument().activeView().{code}
Gui.SendMsgToActiveView("ViewFit")
Gui.activeDocument().activeView().saveImage(
    r"{os.path.join(HERE, f'ToyCarV3_{view}.png')}", 1280, 960, "White")
""")
    fc(f"""
import FreeCAD as App, FreeCADGui as Gui
doc = App.getDocument("ToyCarV3")
off = {json.dumps(EXPLODE)}
base = {{}}
for o in doc.Objects:
    base[o.Name] = App.Vector(o.Placement.Base)
    d = off.get(o.Name, (0, 0, 0))
    o.Placement.Base = base[o.Name] + App.Vector(*d)
doc.recompute()
Gui.activeDocument().activeView().viewIsometric()
Gui.SendMsgToActiveView("ViewFit")
Gui.activeDocument().activeView().saveImage(
    r"{os.path.join(HERE, 'ToyCarV3_exploded.png')}", 1280, 960, "White")
for o in doc.Objects:
    o.Placement.Base = base[o.Name]
doc.recompute()
Gui.SendMsgToActiveView("ViewFit")
""")


# ── S9 导出 ─────────────────────────────────────────────────────────────
def s9_export():
    fc(f"""
import FreeCAD as App, FreeCADGui as Gui, Part, Mesh
doc = App.getDocument("ToyCarV3")
doc.saveAs(r"{os.path.join(HERE, 'ToyCarV3.FCStd')}")
objs = [o for o in doc.Objects if hasattr(o, "Shape")]
Part.export(objs, r"{os.path.join(HERE, 'ToyCarV3.step')}")
Mesh.export(objs, r"{os.path.join(HERE, 'ToyCarV3.stl')}")
""")


if __name__ == "__main__":
    st = json.loads(urllib.request.urlopen(BASE + "/status", timeout=10).read())
    print("桥接:", BASE, "FreeCAD:", st.get("freecad_version", st.get("freecad", "?")))
    stage("S1 滑板底盘(电池仓/PCB柱/轴承塔/电机沉窝)", s1_chassis)
    stage("S2 动力总成(130电机/抱箍/渐开线齿轮4:1)", s2_powertrain)
    stage("S3 传动轴+四轮", s3_axles_wheels)
    stage("S4 电池组+PCB(1:1安装接口)", s4_battery_pcb)
    stage("S5 车壳(真车轮廓/挡风/侧窗/轮拱/前脸/尾灯)", s5_shell)
    stage("S5b 引擎盖(独立检修面板)", s5b_hood)
    stage("S6 汇入GUI文档", s6_document)
    inter = stage("S7 干涉核算", s7_engineering)
    stage("S8 渲染 iso/front/side/爆炸图", s8_render)
    stage("S9 导出 FCStd/STEP/STL", s9_export)
    print("完成: ToyCarV3 ·", len(EXPORTS), "件 · 干涉:", inter)
