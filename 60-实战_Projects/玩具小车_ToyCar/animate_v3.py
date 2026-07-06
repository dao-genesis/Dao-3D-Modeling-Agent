# -*- coding: utf-8 -*-
"""ToyCarV3 GUI 动画: 爆炸装拆 + 传动仿真运动测试(经桥接 :18920)"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:18920"

EXPLODE = {
    "BodyShell": (0, 0, 70), "Hood": (25, 0, 55), "BatteryPack": (0, 0, 32),
    "PCB": (0, 0, 42), "Motor": (-28, 0, 0), "MotorMount": (-28, 0, 18),
    "Pinion": (-28, -14, 0), "SpurGear": (0, -14, 0),
    "WheelRL": (0, 30, 0), "WheelRR": (0, -30, 0),
    "WheelFL": (0, 30, 0), "WheelFR": (0, -30, 0),
    "AxleRear": (0, 0, -18), "AxleFront": (0, 0, -18),
}


def fc(code, timeout=600):
    req = urllib.request.Request(
        BASE + "/exec", data=json.dumps({"code": code}).encode(),
        headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    if not r.get("ok", True):
        raise RuntimeError(str(r)[:500])
    return r


def explode_anim():
    fc(f"""
import FreeCAD as App, FreeCADGui as Gui, time
doc = App.getDocument("ToyCarV3")
off = {json.dumps(EXPLODE)}
base = {{o.Name: App.Vector(o.Placement.Base) for o in doc.Objects}}
Gui.activeDocument().activeView().viewIsometric()
Gui.SendMsgToActiveView("ViewFit")
steps = 40
for phase in (1, 0):   # 爆炸 → 复装
    rng = range(1, steps + 1) if phase else range(steps - 1, -1, -1)
    for i in rng:
        t = i / steps
        for o in doc.Objects:
            d = off.get(o.Name, (0, 0, 0))
            o.Placement.Base = base[o.Name] + App.Vector(d[0]*t, d[1]*t, d[2]*t)
        doc.recompute(); Gui.updateGui(); time.sleep(0.12)
    time.sleep(1.0)
for o in doc.Objects:
    o.Placement.Base = base[o.Name]
doc.recompute(); Gui.updateGui()
Gui.SendMsgToActiveView("ViewFit")
""")


def drive_anim():
    fc("""
import FreeCAD as App, FreeCADGui as Gui, math, time
doc = App.getDocument("ToyCarV3")
REAR_X, FRONT_X, MOTOR_X, AXZ, R, ratio = -65.0, 65.0, -77.65, 18.0, 18.0, 4.0
axleset = ["SpurGear", "AxleRear", "WheelRL", "WheelRR"]
front = ["AxleFront", "WheelFL", "WheelFR"]
objs = {o.Name: o for o in doc.Objects}
base0 = {n: App.Vector(objs[n].Placement.Base) for n in objs}
rot0 = {n: App.Rotation(objs[n].Placement.Rotation) for n in objs}
axis_x = {}
for n in axleset: axis_x[n] = REAR_X
for n in front: axis_x[n] = FRONT_X
axis_x["Pinion"] = MOTOR_X
travel = 140.0; steps = 70
for i in range(1, steps + 1):
    dx = travel * i / steps
    ang = math.degrees(dx / R)
    for n, o in objs.items():
        spin = ang * ratio if n == "Pinion" else (ang if n in axis_x else 0.0)
        shift = App.Vector(dx, 0, 0)
        if spin:
            c = App.Vector(axis_x[n], 0, AXZ)
            rot = App.Rotation(App.Vector(0, 1, 0), -spin)
            o.Placement = App.Placement(
                shift + c - rot.multVec(c) + base0[n], rot.multiply(rot0[n]))
        else:
            o.Placement = App.Placement(base0[n] + shift, rot0[n])
    doc.recompute(); Gui.updateGui(); time.sleep(0.1)
time.sleep(0.8)
for n, o in objs.items():
    o.Placement = App.Placement(base0[n], rot0[n])
doc.recompute(); Gui.updateGui()
Gui.SendMsgToActiveView("ViewFit")
""")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("explode", "all"):
        explode_anim()
        print("爆炸装拆动画 完成")
    if which in ("drive", "all"):
        drive_anim()
        print("传动仿真运动 完成")
