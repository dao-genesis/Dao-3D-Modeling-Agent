#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玩具小车 · 复杂装配体从零构建 (经桥接 /exec 直达 FreeCAD 本体, 前端实时可见)
════════════════════════════════════════════════════════════════════════════
道生一: 底盘  一生二: 前后轴  二生三: 四轮+车身+车顶  三生万物: 装配+仿真+验证

板块覆盖:
  Part 参数化建模 · 装配定位(Placement) · 布尔运算 · 倒角
  运动学仿真(车轮滚动 rev 关节, 经 00-本源/dao_kinematics)
  干涉检查(common 体积) · 质量属性 · STEP/STL 导出 · GUI 截图取证

用法:  python3 build_toycar.py   (桥接 http://127.0.0.1:18920 需在跑)
"""
import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("FC_REMOTE", "http://127.0.0.1:18920")
HERE = os.path.dirname(os.path.abspath(__file__))


def api(path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data else "GET")
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def fc(code, timeout=120):
    r = api("/exec", {"code": code}, timeout)
    if not r.get("ok"):
        raise RuntimeError("exec failed: %s" % r)
    return r


STAGES = []


def stage(name):
    def deco(fn):
        STAGES.append((name, fn))
        return fn
    return deco


# ── 阶段一 · 文档与底盘 ────────────────────────────────────────────────────
@stage("文档+底盘")
def s1():
    fc(r'''
import FreeCAD as App, FreeCADGui as Gui
for d in list(App.listDocuments()):
    App.closeDocument(d)
doc = App.newDocument("ToyCar")
raw = doc.addObject("Part::Box", "ChassisRaw")
raw.Length, raw.Width, raw.Height = 120, 60, 12
raw.Placement.Base = App.Vector(-60, -30, 10)
hole_objs = []
for n, x in (("HoleF", 38), ("HoleR", -38)):
    h = doc.addObject("Part::Cylinder", n)
    h.Radius, h.Height = 3.2, 80
    h.Placement = App.Placement(App.Vector(x, -40, 12),
                                App.Rotation(App.Vector(1, 0, 0), -90))
    hole_objs.append(h)
fusion_holes = doc.addObject("Part::MultiFuse", "AxleHoles")
fusion_holes.Shapes = hole_objs
chassis = doc.addObject("Part::Cut", "Chassis")
chassis.Base, chassis.Tool = raw, fusion_holes
doc.recompute()
chassis.ViewObject.ShapeColor = (0.85, 0.15, 0.15)
Gui.activateWorkbench("PartWorkbench")
Gui.SendMsgToActiveView("ViewFit")
''')


# ── 阶段二 · 前后轴 ────────────────────────────────────────────────────────
@stage("前后轴")
def s2():
    fc(r'''
import FreeCAD as App
doc = App.getDocument("ToyCar")
for name, x in (("AxleFront", 38), ("AxleRear", -38)):
    a = doc.addObject("Part::Cylinder", name)
    a.Radius, a.Height = 3, 76
    a.Placement = App.Placement(App.Vector(x, -38, 12),
                                App.Rotation(App.Vector(1, 0, 0), -90))
    a.ViewObject.ShapeColor = (0.6, 0.6, 0.65)
doc.recompute()
''')


# ── 阶段三 · 四轮(带轮毂倒角) ─────────────────────────────────────────────
@stage("四轮")
def s3():
    fc(r'''
import FreeCAD as App
doc = App.getDocument("ToyCar")
positions = {"WheelFL": (38, 30), "WheelFR": (38, -42),
             "WheelRL": (-38, 30), "WheelRR": (-38, -42)}
for name, (x, y) in positions.items():
    tire = doc.addObject("Part::Cylinder", name + "Tire")
    tire.Radius, tire.Height = 16, 12
    tire.Placement = App.Placement(App.Vector(x, y, 12),
                                   App.Rotation(App.Vector(1, 0, 0), -90))
    bore = doc.addObject("Part::Cylinder", name + "Bore")
    bore.Radius, bore.Height = 3.2, 14
    bore.Placement = App.Placement(App.Vector(x, y - 1, 12),
                                   App.Rotation(App.Vector(1, 0, 0), -90))
    w = doc.addObject("Part::Cut", name)
    w.Base, w.Tool = tire, bore
    doc.recompute()
    w.ViewObject.ShapeColor = (0.12, 0.12, 0.12)
doc.recompute()
''')


# ── 阶段四 · 车身+车顶+烟囱(布尔融合) ────────────────────────────────────
@stage("车身车顶")
def s4():
    fc(r'''
import FreeCAD as App, FreeCADGui as Gui
doc = App.getDocument("ToyCar")
body = doc.addObject("Part::Box", "Body")
body.Length, body.Width, body.Height = 90, 50, 22
body.Placement.Base = App.Vector(-50, -25, 22)
cab = doc.addObject("Part::Box", "Cab")
cab.Length, cab.Width, cab.Height = 44, 42, 24
cab.Placement.Base = App.Vector(-40, -21, 44)
fusion = doc.addObject("Part::MultiFuse", "CarBody")
fusion.Shapes = [body, cab]
doc.recompute()
fusion.ViewObject.ShapeColor = (0.95, 0.65, 0.1)
Gui.SendMsgToActiveView("ViewFit")
''')


# ── 阶段五 · 运动学仿真(dao_kinematics · 车轮 revolute 关节) ─────────────
@stage("运动学仿真")
def s5():
    repo = os.path.dirname(os.path.dirname(HERE))
    fc(r'''
import sys, json, math
sys.path.insert(0, %r)
import dao_kinematics as dk
mech = dk.Mechanism("ToyCar", root_link="chassis")
mech.add_link(dk.Link("chassis"))
for wn in ("FL", "FR", "RL", "RR"):
    mech.add_link(dk.Link("wheel_" + wn))
    x = 38 if wn[0] == "F" else -38
    y = 30 if wn[1] == "L" else -36
    mech.add_joint(dk.Joint("j_" + wn, "revolute", parent="chassis",
                            child="wheel_" + wn,
                            origin=dk.SE3.from_translation(dk.v3(x, y, 12)),
                            axis=dk.v3(0, 1, 0)))
travel = 100.0; R = 16.0
angle = travel / R
mech.set_q([angle] * 4)
poses = dk.forward_kinematics(mech)
out = {"travel_mm": travel, "wheel_angle_rad": round(angle, 4),
       "wheel_angle_deg": round(math.degrees(angle), 2),
       "dof": mech.total_dof(),
       "links": sorted(poses.keys())}
open(%r, "w").write(json.dumps(out, ensure_ascii=False, indent=1))
print("KINEMATICS", out)
''' % (os.path.join(repo, "00-本源_Origin"),
       os.path.join(HERE, "kinematics_result.json")))
    # GUI 侧动画: 车轮实转 + 整车前移 (前端面板实时可见)
    fc(r'''
import FreeCAD as App, FreeCADGui as Gui, math, time
doc = App.getDocument("ToyCar")
wheels = [doc.getObject(n) for n in ("WheelFL", "WheelFR", "WheelRL", "WheelRR")]
bodies = [doc.getObject(n) for n in ("ChassisRaw", "AxleHoles", "AxleFront", "AxleRear", "CarBody")]
base0 = {o.Name: App.Vector(o.Placement.Base) for o in wheels + bodies}
rot0 = {o.Name: App.Rotation(o.Placement.Rotation) for o in wheels + bodies}
R = 16.0
steps, travel = 24, 100.0
for i in range(1, steps + 1):
    dx = travel * i / steps
    ang = math.degrees(dx / R)
    for o in bodies:
        o.Placement.Base = base0[o.Name] + App.Vector(dx, 0, 0)
    for o in wheels:
        spin = App.Rotation(App.Vector(0, 1, 0), ang)
        o.Placement = App.Placement(base0[o.Name] + App.Vector(dx, 0, 0),
                                    spin.multiply(rot0[o.Name]))
    doc.recompute()
    Gui.updateGui()
    time.sleep(0.04)
for o in wheels + bodies:
    o.Placement = App.Placement(base0[o.Name], rot0[o.Name])
doc.recompute()
Gui.SendMsgToActiveView("ViewFit")
''', timeout=180)


# ── 阶段六 · 干涉检查 + 质量属性 ─────────────────────────────────────────
@stage("干涉+质量")
def s6():
    fc(r'''
import FreeCAD as App, json, itertools
doc = App.getDocument("ToyCar")
FINAL = ("Chassis", "AxleFront", "AxleRear",
         "WheelFL", "WheelFR", "WheelRL", "WheelRR", "CarBody")
solids = [doc.getObject(n) for n in FINAL]
report = {"interference": [], "mass_props": {}}
for a, b in itertools.combinations(solids, 2):
    try:
        common = a.Shape.common(b.Shape)
        if common.Volume > 1e-6:
            report["interference"].append(
                {"pair": [a.Name, b.Name], "volume_mm3": round(common.Volume, 3)})
    except Exception as e:
        report["interference"].append({"pair": [a.Name, b.Name], "error": str(e)})
for o in solids:
    s = o.Shape
    vol = sum(sd.Volume for sd in s.Solids)
    cog = App.Vector(0, 0, 0)
    for sd in s.Solids:
        cog += sd.CenterOfMass * sd.Volume
    cog = cog * (1.0 / vol) if vol > 1e-9 else cog
    report["mass_props"][o.Name] = {
        "volume_mm3": round(vol, 1),
        "area_mm2": round(s.Area, 1),
        "cog": [round(c, 2) for c in (cog.x, cog.y, cog.z)]}
open(%r, "w").write(json.dumps(report, ensure_ascii=False, indent=1))
print("REPORT", json.dumps(report)[:400])
''' % os.path.join(HERE, "verify_report.json"))


# ── 阶段七 · 导出 + 截图取证 ─────────────────────────────────────────────
@stage("导出+截图")
def s7():
    fc(r'''
import FreeCAD as App, FreeCADGui as Gui, Part
doc = App.getDocument("ToyCar")
doc.saveAs(%r)
FINAL = ("Chassis", "AxleFront", "AxleRear",
         "WheelFL", "WheelFR", "WheelRL", "WheelRR", "CarBody")
solids = [doc.getObject(n) for n in FINAL]
Part.export(solids, %r)
import Mesh
Mesh.export(solids, %r)
Gui.activeDocument().activeView().viewAxometric()
Gui.SendMsgToActiveView("ViewFit")
Gui.activeDocument().activeView().saveImage(%r, 1280, 800, "White")
print("EXPORTED")
''' % (os.path.join(HERE, "ToyCar.FCStd"),
       os.path.join(HERE, "ToyCar.step"),
       os.path.join(HERE, "ToyCar.stl"),
       os.path.join(HERE, "ToyCar_iso.png")))


def main():
    print("桥接:", BASE)
    st = api("/status")
    print("FreeCAD:", ".".join(st["freecad_version"][:2]))
    for name, fn in STAGES:
        t = time.time()
        fn()
        print("✓ %s (%.1fs)" % (name, time.time() - t))
    print("玩具小车装配 · 全阶段完成")


if __name__ == "__main__":
    main()
