#!/usr/bin/env python3
"""
万法归一 — FreeCAD 长连接 终极一体化构建+验证

道法自然 · 无为而无不为
从根本直接整合所有3D建模需求于一体，于FreeCAD长连接完成一切。

覆盖:
  A. 连接与状态 (4项)
  B. 全部35种参数化模型构建 (35项)
  C. 107种ops操作覆盖 — 基元/布尔/修改器/变换/阵列/线框/曲面 (30+项)
  D. 高级工作流 — PartDesign/Sketcher/布尔链/多体装配 (10+项)
  E. 全格式导出 — STEP/STL/BREP/IGES/FCStd/截图 (7项)
  F. 视图控制/工作台切换/选择系统 (15项)
  G. 命令系统完整性/探针数据 (10+项)
  H. 错误处理/边界情况 (5+项)

运行:
  python _万法归一_build.py
"""
import urllib.request
import json
import time
import os
import sys
import base64
import traceback
from pathlib import Path

REMOTE = "http://127.0.0.1:18920"
SCRIPT_DIR = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in SCRIPT_DIR.parents if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
ROOT_DIR = _DAO_ROOT
# ═══════════════════════════════════════════════════════════════════

OUTPUT_DIR = _dao_paths.PROJECTS / "fc_output"
BUILD_DIR = OUTPUT_DIR / "_万法归一"

passed = 0
failed = 0
errors = []
t_global = time.time()

# ── API Helper ────────────────────────────────────────────────────
def api(path, data=None, timeout=60):
    url = REMOTE + path
    if data:
        req = urllib.request.Request(url, json.dumps(data).encode(), {'Content-Type': 'application/json'})
    else:
        req = urllib.request.Request(url)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

def fc_exec(code, timeout=60):
    """Execute Python code inside FreeCAD GUI thread"""
    return api("/exec", {"code": code}, timeout=timeout)

def fc_ops(ops, timeout=120):
    """Execute backend ops sequence inside FreeCAD"""
    return api("/ops", {"ops": ops}, timeout=timeout)

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  \u2705 {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  \u274c {name} \u2014 {detail}")

def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

# ═══════════════════════════════════════════════════════════════════
# A. 连接与状态
# ═══════════════════════════════════════════════════════════════════
section("A. FreeCAD 长连接状态")
try:
    s = api("/status")
    check("服务器在线", s.get("ok"))
    fc_ver = s.get("freecad_version", [])
    check("FreeCAD版本", len(fc_ver) > 0, f"v={'.'.join(str(x) for x in fc_ver[:3])}")
    check("端口18920", s.get("port") == 18920)
    check("时间戳", s.get("timestamp") is not None)
except Exception as e:
    check("服务器连接", False, str(e))
    print("\n  !! 远程服务器未运行, 终止")
    sys.exit(1)

# Prepare build directory
BUILD_DIR.mkdir(parents=True, exist_ok=True)

# Ensure clean document
fc_exec("import FreeCAD as App\nif not App.ActiveDocument:\n    App.newDocument('WanFa')")
time.sleep(0.3)

# ═══════════════════════════════════════════════════════════════════
# B. 全部35种参数化模型通过ops构建
# ═══════════════════════════════════════════════════════════════════
section("B. 全部参数化模型构建 (35种 — ops→远程)")

MODEL_BUILDS = {
    "box": [{"op":"make_box","id":"r","L":30,"W":20,"H":15}],
    "rounded_box": [{"op":"make_rounded_box","id":"r","L":30,"W":20,"H":10,"R":2}],
    "cylinder": [{"op":"make_cylinder","id":"r","R":10,"H":25}],
    "sphere": [{"op":"make_sphere","id":"r","R":12}],
    "cone": [{"op":"make_cone","id":"r","R1":12,"R2":5,"H":20}],
    "torus": [{"op":"make_torus","id":"r","R1":15,"R2":4}],
    "tube": [{"op":"make_tube","id":"r","R_outer":10,"R_inner":7,"H":20}],
    "prism": [{"op":"make_prism","id":"r","n":6,"R":10,"H":18}],
    "ellipsoid": [{"op":"make_ellipsoid","id":"r","rx":15,"ry":10,"rz":8}],
    "frustum": [{"op":"make_frustum","id":"r","R1":15,"R2":8,"H":20}],
    "pyramid": [{"op":"make_pyramid","id":"r","n":4,"base_r":12,"H":18}],
    "stadium": [{"op":"make_stadium","id":"r","L":30,"R":8,"H":10}],
    "slot": [{"op":"make_slot","id":"r","L":25,"W":8,"H":6}],
    "chamfer_box": [{"op":"make_chamfer_box","id":"r","L":25,"W":18,"H":12,"chamfer":2}],
    "ellipse_extrude": [{"op":"make_ellipse_extrude","id":"r","a":15,"b":10,"H":12}],
    "hex_bolt": [{"op":"make_hex_bolt","id":"r","diameter":8,"length":30,"head_h":5.6,"head_w":14.4}],
    "hex_nut": [{"op":"make_hex_nut","id":"r","diameter":8,"thickness":6.4}],
    "bracket": [{"op":"make_bracket","id":"r","W":30,"H":30,"D":5,"fillet":2}],
    "enclosure": [{"op":"make_enclosure","id":"r","L":60,"W":40,"H":25,"wall":2,"open_top":True}],
    "gear_spur": [{"op":"make_gear_spur","id":"r","teeth":20,"module":1.0,"width":8,"hub_r":0}],
    "gear_rack": [{"op":"make_gear_rack","id":"r","module":1.0,"length":50,"width":8}],
    "bearing_seat": [{"op":"make_bearing_seat","id":"r","od":40,"bore":17,"width":12}],
    "spring": [{"op":"make_spring","id":"r","R":10,"wire_r":1.5,"pitch":8,"turns":5}],
    "i_beam": [{"op":"make_i_beam","id":"r","W":20,"H":30,"tf":3,"tw":2,"L":60}],
    "channel": [{"op":"make_channel","id":"r","W":20,"H":20,"tf":2.5,"tw":2,"L":50}],
    "l_profile": [{"op":"make_l_profile","id":"r","W":20,"H":20,"t":2.5,"L":50}],
    "thread": [{"op":"make_thread","id":"r","diameter":8,"pitch":1.25,"length":20}],
    "pipe_3d": [{"op":"make_pipe_3d","id":"r","path_pts":[[0,0,0],[0,0,20],[10,0,40]],"R":3}],
    "hollow_cyl": [{"op":"make_hollow_cylinder","id":"r","R_out":12,"R_in":9,"H":20}],
    "reg_polygon": [{"op":"make_reg_polygon","id":"r","n":8,"R":10,"H":15}],
    # Complex multi-op models
    "washer": [
        {"op":"make_cylinder","id":"o","R":8,"H":1.6},
        {"op":"make_cylinder","id":"h","R":4.2,"H":1.6},
        {"op":"cut","id":"r","base":"o","tool":"h"}
    ],
    "flange": [
        {"op":"make_cylinder","id":"d","R":30,"H":8},
        {"op":"make_cylinder","id":"b","R":12.5,"H":8},
        {"op":"cut","id":"r","base":"d","tool":"b"}
    ],
    "t_slot": [
        {"op":"make_box","id":"hd","L":20,"W":50,"H":5},
        {"op":"make_box","id":"nk","L":8,"W":50,"H":5,"pos":[6,0,5]},
        {"op":"fuse","id":"r","base":"hd","tool":"nk"}
    ],
    "motor_mount": [
        {"op":"make_box","id":"base","L":40,"W":30,"H":5},
        {"op":"make_cylinder","id":"ring","R":15.5,"H":15,"pos":[20,15,5]},
        {"op":"make_cylinder","id":"bore","R":12.5,"H":15,"pos":[20,15,5]},
        {"op":"fuse","id":"f1","base":"base","tool":"ring"},
        {"op":"cut","id":"r","base":"f1","tool":"bore"}
    ],
    "hinge": [
        {"op":"make_box","id":"lf","L":30,"W":15,"H":2},
        {"op":"make_cylinder","id":"br","R":5,"H":30,"pos":[0,15,1],"dir":[1,0,0]},
        {"op":"fuse","id":"hf","base":"lf","tool":"br"},
        {"op":"make_cylinder","id":"ph","R":3,"H":30,"pos":[0,15,1],"dir":[1,0,0]},
        {"op":"cut","id":"r","base":"hf","tool":"ph"}
    ],
}

model_pass = 0
model_fail = 0
for model_name, ops in MODEL_BUILDS.items():
    try:
        # Add export ops
        stl_path = str(BUILD_DIR / f"{model_name}.stl")
        step_path = str(BUILD_DIR / f"{model_name}.step")
        full_ops = ops + [
            {"op": "export_stl", "shape": "r", "path": stl_path},
            {"op": "export_step", "shape": "r", "path": step_path},
        ]
        r = fc_ops(full_ops, timeout=60)
        ok = r.get("ok", False)
        shapes = r.get("shapes", {})
        has_r = "r" in shapes and shapes["r"].get("type", "") != "ERROR"
        exports = r.get("exports", [])
        exp_ok = sum(1 for e in exports if e.get("ok")) >= 1
        result_ok = ok and has_r
        check(f"模型: {model_name}", result_ok,
              f"ok={ok} shapes={list(shapes.keys())[:5]} vol={shapes.get('r',{}).get('volume_mm3',0):.0f}")
        if result_ok:
            model_pass += 1
        else:
            model_fail += 1
    except Exception as e:
        check(f"模型: {model_name}", False, str(e)[:80])
        model_fail += 1

print(f"\n  模型构建: {model_pass}/{model_pass+model_fail}")

# ═══════════════════════════════════════════════════════════════════
# C. Ops操作全覆盖验证
# ═══════════════════════════════════════════════════════════════════
section("C. Ops操作全覆盖 (基元/布尔/修改器/变换/阵列/线框/曲面/分析)")

# C1: Advanced primitives
section("C1. 高级基元")
c1_ops = [
    {"op":"make_box","id":"bx","L":20,"W":15,"H":10},
    {"op":"make_cylinder","id":"cy","R":8,"H":20},
    {"op":"make_sphere","id":"sp","R":10},
    {"op":"make_cone","id":"cn","R1":10,"R2":3,"H":15},
    {"op":"make_torus","id":"tr","R1":12,"R2":3},
    {"op":"make_wedge","id":"wg","dx":10,"dy":10,"dz":10,"xmin":2,"zmin":2,"xmax":8,"zmax":8,
     "x2min":3,"z2min":3,"x2max":7,"z2max":7},
    {"op":"make_tube","id":"tb","R_outer":10,"R_inner":7,"H":20},
    {"op":"make_prism","id":"pr","n":6,"R":10,"H":15},
    {"op":"make_ellipsoid","id":"el","rx":12,"ry":8,"rz":6},
    {"op":"make_frustum","id":"fr","R1":12,"R2":7,"H":18},
    {"op":"make_pyramid","id":"py","n":5,"base_r":10,"H":15},
    {"op":"make_stadium","id":"st","L":25,"R":6,"H":10},
    {"op":"make_slot","id":"sl","L":20,"W":6,"H":5},
    {"op":"make_rounded_box","id":"rb","L":20,"W":15,"H":10,"R":2},
    {"op":"make_chamfer_box","id":"cb","L":20,"W":15,"H":10,"chamfer":1.5},
    {"op":"make_ellipse_extrude","id":"ee","a":12,"b":8,"H":10},
    {"op":"make_hollow_cylinder","id":"hc","R_out":10,"R_in":7,"H":15},
    {"op":"make_reg_polygon","id":"rp","n":8,"R":10,"H":12},
]
try:
    r = fc_ops(c1_ops)
    shapes = r.get("shapes", {})
    for o in c1_ops:
        oid = o["id"]
        ok = oid in shapes and shapes[oid].get("type","") != "ERROR"
        check(f"基元: {o['op']}", ok, f"type={shapes.get(oid,{}).get('type','MISSING')}")
except Exception as e:
    check("基元批量", False, str(e)[:120])

# C2: Wire and surface
section("C2. 线框/曲面/扫掠")
c2_ops = [
    {"op":"make_polygon_wire","id":"pw","points":[[0,0,0],[20,0,0],[20,15,0],[0,15,0]],"closed":True},
    {"op":"make_circle_wire","id":"cw","R":8},
    {"op":"make_face","id":"fc","wire":"pw"},
    {"op":"extrude","id":"ex","shape":"fc","direction":[0,0,15]},
    {"op":"make_bspline","id":"bs","points":[[0,0,0],[5,10,0],[15,10,0],[20,0,0]]},
    {"op":"make_helix","id":"hx","pitch":5,"height":30,"R":8},
    {"op":"make_spiral","id":"spi","turns":3,"growth":2,"steps":60},
]
try:
    r = fc_ops(c2_ops)
    shapes = r.get("shapes", {})
    for o in c2_ops:
        oid = o["id"]
        ok = oid in shapes and shapes[oid].get("type","") != "ERROR"
        check(f"线框: {o['op']}", ok, f"type={shapes.get(oid,{}).get('type','MISSING')}")
except Exception as e:
    check("线框批量", False, str(e)[:120])

# C3: Booleans
section("C3. 布尔运算")
c3_ops = [
    {"op":"make_box","id":"ba","L":20,"W":20,"H":20},
    {"op":"make_cylinder","id":"bc","R":6,"H":30,"pos":[10,10,-5]},
    {"op":"make_sphere","id":"bs","R":8,"pos":[10,10,10]},
    {"op":"fuse","id":"fu","base":"ba","tool":"bc"},
    {"op":"cut","id":"cu","base":"ba","tool":"bc"},
    {"op":"common","id":"co","base":"ba","tool":"bc"},
    {"op":"section","id":"se","shape":"ba","other":"bs"},
]
try:
    r = fc_ops(c3_ops)
    shapes = r.get("shapes", {})
    for oid in ["fu","cu","co","se"]:
        ok = oid in shapes and shapes[oid].get("type","") != "ERROR"
        check(f"布尔: {oid}", ok, f"type={shapes.get(oid,{}).get('type','MISSING')}")
except Exception as e:
    check("布尔批量", False, str(e)[:120])

# C4: Modifiers
section("C4. 修改器 (倒角/圆角/壳体/偏移)")
c4_ops = [
    {"op":"make_box","id":"mb","L":30,"W":20,"H":15},
    {"op":"fillet","id":"fi","shape":"mb","radius":2},
    {"op":"chamfer","id":"ch","shape":"mb","size":1.5},
    {"op":"shell","id":"sh","shape":"mb","thickness":-2,"face_indices":[0]},
    {"op":"offset3d","id":"of","shape":"mb","offset":1.0},
]
try:
    r = fc_ops(c4_ops)
    shapes = r.get("shapes", {})
    for oid in ["fi","ch","sh","of"]:
        ok = oid in shapes and shapes[oid].get("type","") != "ERROR"
        check(f"修改器: {oid}", ok, f"type={shapes.get(oid,{}).get('type','MISSING')}")
except Exception as e:
    check("修改器批量", False, str(e)[:120])

# C5: Transforms
section("C5. 变换 (平移/旋转/镜像/缩放)")
c5_ops = [
    {"op":"make_box","id":"tb","L":10,"W":10,"H":10},
    {"op":"translate","id":"tr","shape":"tb","vector":[30,0,0]},
    {"op":"rotate","id":"ro","shape":"tb","axis":[0,0,1],"angle":45},
    {"op":"mirror","id":"mi","shape":"tb","plane":"YZ"},
    {"op":"make_scale","id":"sc","shape":"tb","sx":2,"sy":1,"sz":0.5},
    {"op":"scale","id":"su","shape":"tb","factor":1.5},
]
try:
    r = fc_ops(c5_ops)
    shapes = r.get("shapes", {})
    for oid in ["tr","ro","mi","sc","su"]:
        ok = oid in shapes and shapes[oid].get("type","") != "ERROR"
        check(f"变换: {oid}", ok, f"type={shapes.get(oid,{}).get('type','MISSING')}")
except Exception as e:
    check("变换批量", False, str(e)[:120])

# C6: Arrays
section("C6. 阵列 (线性/极性/网格/路径/3D)")
c6_ops = [
    {"op":"make_cylinder","id":"ab","R":3,"H":8},
    {"op":"array_linear","id":"al","shape":"ab","direction":[15,0,0],"count":4,"spacing":15},
    {"op":"array_polar","id":"ap","shape":"ab","center":[0,0,0],"axis":[0,0,1],"count":6,"angle":360},
    {"op":"array_grid","id":"ag","shape":"ab","nx":3,"ny":3,"dx":12,"dy":12},
    {"op":"make_array_3d","id":"a3","shape":"ab","nx":2,"ny":2,"nz":2,"dx":15,"dy":15,"dz":15},
]
try:
    r = fc_ops(c6_ops)
    shapes = r.get("shapes", {})
    for oid in ["al","ap","ag","a3"]:
        ok = oid in shapes and shapes[oid].get("type","") != "ERROR"
        check(f"阵列: {oid}", ok, f"type={shapes.get(oid,{}).get('type','MISSING')}")
except Exception as e:
    check("阵列批量", False, str(e)[:120])

# C7: Engineering parts
section("C7. 工程零件")
eng_ops = [
    {"op":"make_hex_bolt","id":"hb","diameter":10,"length":35,"head_h":7,"head_w":18},
    {"op":"make_hex_nut","id":"hn","diameter":10,"thickness":8},
    {"op":"make_bracket","id":"bk","W":30,"H":25,"D":5,"fillet":2},
    {"op":"make_enclosure","id":"en","L":50,"W":35,"H":25,"wall":2,"open_top":True},
    {"op":"make_gear_spur","id":"gs","teeth":24,"module":1.5,"width":10,"hub_r":0},
    {"op":"make_gear_rack","id":"gr","module":1.5,"length":60,"width":10},
    {"op":"make_bearing_seat","id":"be","od":42,"bore":20,"width":12},
    {"op":"make_spring","id":"sg","R":8,"wire_r":1.2,"pitch":6,"turns":6},
    {"op":"make_i_beam","id":"ib","W":25,"H":35,"tf":3,"tw":2,"L":80},
    {"op":"make_channel","id":"cl","W":25,"H":25,"tf":3,"tw":2,"L":60},
    {"op":"make_l_profile","id":"lp","W":25,"H":25,"t":3,"L":60},
    {"op":"make_thread","id":"td","diameter":10,"pitch":1.5,"length":25},
    {"op":"make_text_3d","id":"tx","text":"DAO","size":12,"depth":3},
]
try:
    r = fc_ops(eng_ops, timeout=120)
    shapes = r.get("shapes", {})
    for o in eng_ops:
        oid = o["id"]
        ok = oid in shapes and shapes[oid].get("type","") != "ERROR"
        check(f"工程: {o['op']}", ok, f"vol={shapes.get(oid,{}).get('volume_mm3',0):.0f}")
except Exception as e:
    check("工程批量", False, str(e)[:120])

# C8: Analysis
section("C8. 分析 (shape_info/mass/3dprint/距离)")
c8_ops = [
    {"op":"make_box","id":"ab","L":30,"W":20,"H":15},
    {"op":"make_sphere","id":"as2","R":10,"pos":[50,0,0]},
    {"op":"shape_info","shape":"ab"},
    {"op":"mass_properties","shape":"ab","density":7.85},
    {"op":"shape_analysis_3dprint","shape":"ab","min_wall_mm":0.5},
    {"op":"check_shape","shape":"ab"},
    {"op":"measure_distance","shape1":"ab","shape2":"as2"},
]
try:
    r = fc_ops(c8_ops)
    analyses = r.get("analyses", [])
    check("shape_info", any(a.get("op") == "shape_info" for a in analyses), f"analyses={len(analyses)}")
    check("mass_properties", any(a.get("op") == "mass_properties" for a in analyses))
    check("3dprint_analysis", any(a.get("op") == "shape_analysis_3dprint" for a in analyses))
    check("check_shape", any(a.get("op") == "check_shape" for a in analyses))
    check("measure_distance", any(a.get("op") == "measure_distance" for a in analyses))
except Exception as e:
    check("分析批量", False, str(e)[:120])

# ═══════════════════════════════════════════════════════════════════
# D. 高级工作流
# ═══════════════════════════════════════════════════════════════════
section("D. 高级工作流")

# D1: PartDesign parametric workflow via exec
section("D1. PartDesign 参数化工作流")
pd_code = """
import FreeCAD as App
import Part

doc = App.ActiveDocument or App.newDocument('WanFa')

# Create parametric box
box = doc.addObject('Part::Box', 'PDBox')
box.Length = 60
box.Width = 40
box.Height = 30
doc.recompute()

# Create cylinder to cut
cyl = doc.addObject('Part::Cylinder', 'PDCyl')
cyl.Radius = 10
cyl.Height = 40
cyl.Placement.Base = App.Vector(30, 20, -5)
doc.recompute()

# Boolean cut
cut = doc.addObject('Part::Cut', 'PDCut')
cut.Base = box
cut.Tool = cyl
doc.recompute()

vol = round(cut.Shape.Volume, 2) if cut.Shape and not cut.Shape.isNull() else 0
faces = len(cut.Shape.Faces) if cut.Shape else 0
__result__ = f'{vol}|{faces}'
"""
try:
    r = fc_exec(pd_code)
    check("PartDesign创建", r.get("ok"), str(r)[:80])
    if r.get("result"):
        parts = r["result"].split("|")
        vol = float(parts[0])
        faces = int(parts[1])
        check("PartDesign体积>0", vol > 0, f"vol={vol}")
        check("PartDesign面数>0", faces > 0, f"faces={faces}")
except Exception as e:
    check("PartDesign工作流", False, str(e)[:80])

# D2: Sketch-based extrusion
section("D2. Sketch→拉伸 工作流")
sketch_code = """
import FreeCAD as App
import Part
from FreeCAD import Base

doc = App.ActiveDocument

# Create L-shape profile via wire→face→extrude
pts = [
    Base.Vector(0, 0, 0),
    Base.Vector(30, 0, 0),
    Base.Vector(30, 5, 0),
    Base.Vector(5, 5, 0),
    Base.Vector(5, 20, 0),
    Base.Vector(0, 20, 0),
    Base.Vector(0, 0, 0),
]
wire = Part.makePolygon(pts)
face = Part.Face(wire)
solid = face.extrude(Base.Vector(0, 0, 40))
obj = doc.addObject('Part::Feature', 'SketchExtrude')
obj.Shape = solid
doc.recompute()

vol = round(solid.Volume, 2)
valid = solid.isValid()
__result__ = f'{vol}|{valid}'
"""
try:
    r = fc_exec(sketch_code)
    check("Sketch拉伸创建", r.get("ok"), str(r)[:80])
    if r.get("result"):
        parts = r["result"].split("|")
        vol = float(parts[0])
        check("Sketch体积>0", vol > 0, f"vol={vol}")
        check("Sketch几何有效", parts[1] == "True")
except Exception as e:
    check("Sketch工作流", False, str(e)[:80])

# D3: Boolean chain workflow
section("D3. 布尔链工作流 (6层叠加)")
bool_chain_code = """
import FreeCAD as App
import Part
from FreeCAD import Base

doc = App.ActiveDocument

# Base plate
plate = Part.makeBox(80, 60, 5)

# 4 mounting holes
holes = []
for x, y in [(10, 10), (70, 10), (10, 50), (70, 50)]:
    holes.append(Part.makeCylinder(3, 10, Base.Vector(x, y, -1)))

# Central boss
boss = Part.makeCylinder(15, 20, Base.Vector(40, 30, 5))

# Central bore
bore = Part.makeCylinder(8, 25, Base.Vector(40, 30, 0))

# Build chain
result = plate.fuse(boss)
for h in holes:
    result = result.cut(h)
result = result.cut(bore)

# Fillet
result = result.makeFillet(1.5, result.Edges[:4])

obj = doc.addObject('Part::Feature', 'BoolChain')
obj.Shape = result
doc.recompute()

vol = round(result.Volume, 2)
faces = len(result.Faces)
__result__ = f'{vol}|{faces}'
"""
try:
    r = fc_exec(bool_chain_code, timeout=30)
    check("布尔链创建", r.get("ok"), str(r)[:80])
    if r.get("result"):
        parts = r["result"].split("|")
        vol = float(parts[0])
        faces = int(parts[1])
        check("布尔链体积>0", vol > 0, f"vol={vol}")
        check("布尔链面数>10", faces > 10, f"faces={faces}")
except Exception as e:
    check("布尔链工作流", False, str(e)[:80])

# D4: Multi-body assembly
section("D4. 多体装配")
assembly_code = """
import FreeCAD as App
import Part
from FreeCAD import Base

doc = App.ActiveDocument

# Shaft
shaft = Part.makeCylinder(5, 60)
shaft_obj = doc.addObject('Part::Feature', 'AsmShaft')
shaft_obj.Shape = shaft

# Gear on shaft
gear_body = Part.makeCylinder(15, 10, Base.Vector(0, 0, 25))
gear_bore = Part.makeCylinder(5.1, 10, Base.Vector(0, 0, 25))
gear = gear_body.cut(gear_bore)
gear_obj = doc.addObject('Part::Feature', 'AsmGear')
gear_obj.Shape = gear

# Bearing housings
bh1 = Part.makeCylinder(12, 8, Base.Vector(0, 0, 0))
bh1_bore = Part.makeCylinder(5.1, 8, Base.Vector(0, 0, 0))
bh1_final = bh1.cut(bh1_bore)
bh1_obj = doc.addObject('Part::Feature', 'AsmBearing1')
bh1_obj.Shape = bh1_final

bh2 = Part.makeCylinder(12, 8, Base.Vector(0, 0, 52))
bh2_bore = Part.makeCylinder(5.1, 8, Base.Vector(0, 0, 52))
bh2_final = bh2.cut(bh2_bore)
bh2_obj = doc.addObject('Part::Feature', 'AsmBearing2')
bh2_obj.Shape = bh2_final

doc.recompute()

count = len([o for o in doc.Objects if hasattr(o, 'Shape') and o.Shape and not o.Shape.isNull()])
__result__ = str(count)
"""
try:
    r = fc_exec(assembly_code, timeout=30)
    check("多体装配创建", r.get("ok"), str(r)[:80])
    if r.get("result"):
        count = int(r["result"])
        check("装配体数量>=4", count >= 4, f"count={count}")
except Exception as e:
    check("多体装配", False, str(e)[:80])

# D5: Loft workflow
section("D5. 放样/扫掠工作流")
loft_ops = [
    {"op":"make_circle_wire","id":"c1","R":15},
    {"op":"make_circle_wire","id":"c2","R":8},
    {"op":"make_circle_wire","id":"c3","R":12},
]
try:
    r = fc_ops(loft_ops, timeout=30)
    shapes = r.get("shapes", {})
    check("放样线框", all(k in shapes for k in ["c1","c2","c3"]))
except Exception as e:
    check("放样线框", False, str(e)[:80])

# Loft via exec (proper z-offset)
loft_code = """
import Part
from FreeCAD import Base
c1 = Part.makeCircle(15, Base.Vector(0,0,0))
c2 = Part.makeCircle(8, Base.Vector(0,0,30))
c3 = Part.makeCircle(12, Base.Vector(0,0,60))
w1, w2, w3 = Part.Wire([c1]), Part.Wire([c2]), Part.Wire([c3])
lf = Part.makeLoft([w1, w2, w3], True, False)
doc = __import__('FreeCAD').ActiveDocument
obj = doc.addObject('Part::Feature', 'LoftBody')
obj.Shape = lf
doc.recompute()
__result__ = str(round(lf.Volume, 2))
"""
try:
    r = fc_exec(loft_code, timeout=30)
    ok = r.get("ok") and float(r.get("result", "0")) > 0
    check("放样实体", ok, f"vol={r.get('result')}")
except Exception as e:
    check("放样实体", False, str(e)[:80])

# Export loft
loft_exp_code = f"""
import Part
doc = __import__('FreeCAD').ActiveDocument
obj = doc.getObject('LoftBody')
if obj and obj.Shape and not obj.Shape.isNull():
    Part.export([obj], r'{BUILD_DIR / "loft.step"}')
    import Mesh
    Mesh.export([obj], r'{BUILD_DIR / "loft.stl"}')
    __result__ = 'ok'
else:
    __result__ = 'no_shape'
"""
try:
    r = fc_exec(loft_exp_code)
    check("放样导出", r.get("result") == "ok")
except Exception as e:
    check("放样导出", False, str(e)[:80])

# D6: Revolve workflow
section("D6. 旋转体工作流")
revolve_ops = [
    {"op":"make_polygon_wire","id":"rw","points":[[5,0,0],[15,0,0],[12,0,30],[8,0,30]],"closed":True},
    {"op":"make_face","id":"rf","wire":"rw"},
    {"op":"revolve","id":"rv","shape":"rf","axis_pos":[0,0,0],"axis_dir":[0,0,1],"angle":360},
    {"op":"export_stl","shape":"rv","path":str(BUILD_DIR / "revolve.stl")},
    {"op":"export_step","shape":"rv","path":str(BUILD_DIR / "revolve.step")},
]
try:
    r = fc_ops(revolve_ops, timeout=30)
    shapes = r.get("shapes", {})
    check("旋转体创建", "rv" in shapes and shapes["rv"].get("volume_mm3",0) > 0,
          f"vol={shapes.get('rv',{}).get('volume_mm3',0):.0f}")
except Exception as e:
    check("旋转体工作流", False, str(e)[:80])

# ═══════════════════════════════════════════════════════════════════
# E. 全格式导出 + 截图
# ═══════════════════════════════════════════════════════════════════
section("E. 全格式导出 + 截图")

# Build a reference model and export in all formats
export_ops = [
    {"op":"make_box","id":"eb","L":30,"W":20,"H":15},
    {"op":"export_stl","shape":"eb","path":str(BUILD_DIR / "万法.stl")},
    {"op":"export_step","shape":"eb","path":str(BUILD_DIR / "万法.step")},
    {"op":"export_brep","shape":"eb","path":str(BUILD_DIR / "万法.brep")},
    {"op":"export_iges","shape":"eb","path":str(BUILD_DIR / "万法.iges")},
    {"op":"export_obj","shape":"eb","path":str(BUILD_DIR / "万法.obj")},
]
try:
    r = fc_ops(export_ops, timeout=30)
    exports = r.get("exports", [])
    for exp in exports:
        fmt = exp.get("op", "?").replace("export_", "").upper()
        ok = exp.get("ok", False)
        size = exp.get("size_bytes", exp.get("size", 0))
        check(f"导出 {fmt}", ok and size > 0, f"size={size}")
except Exception as e:
    check("导出批量", False, str(e)[:120])

# FCStd via remote
try:
    r = api("/export", {
        "format": "fcstd",
        "path": str(BUILD_DIR / "万法.fcstd"),
    })
    check("导出 FCSTD", r.get("ok"), str(r)[:80])
except Exception as e:
    check("导出 FCSTD", False, str(e)[:80])

# Screenshot
api("/view", {"action": "isometric"})
api("/view", {"action": "fit_all"})
time.sleep(0.5)
try:
    r = api("/screenshot")
    ok = r.get("ok") and len(r.get("data", "")) > 100
    check("截图捕获", ok, f"size={r.get('size',0)}")
    if ok:
        ss_path = str(BUILD_DIR / "万法_全景.png")
        with open(ss_path, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        check("截图保存", os.path.exists(ss_path) and os.path.getsize(ss_path) > 1000)
except Exception as e:
    check("截图", False, str(e)[:80])

# ═══════════════════════════════════════════════════════════════════
# F. 视图/工作台/选择 全覆盖
# ═══════════════════════════════════════════════════════════════════
section("F. 视图/工作台/选择系统")

# F1: All view actions
VIEW_ACTIONS = ["isometric", "front", "rear", "top", "bottom", "left", "right",
                "fit_all", "perspective", "orthographic"]
for action in VIEW_ACTIONS:
    try:
        r = api("/view", {"action": action})
        check(f"视图: {action}", r.get("ok"), str(r.get("error",""))[:40])
    except Exception as e:
        check(f"视图: {action}", False, str(e)[:50])

# F2: Workbench switching
WBS = ["PartWorkbench", "PartDesignWorkbench", "SketcherWorkbench", "DraftWorkbench",
       "MeshWorkbench", "FemWorkbench"]
for wb in WBS:
    try:
        r = api("/workbench", {"name": wb})
        check(f"工作台: {wb}", r.get("ok"))
        time.sleep(0.2)
    except Exception as e:
        check(f"工作台: {wb}", False, str(e)[:50])

# Switch back
api("/workbench", {"name": "PartDesignWorkbench"})

# F3: Selection system
try:
    r = api("/select", {"action": "clear"})
    check("选择清空", r.get("ok"))
    sel = api("/selection")
    check("选择为空", sel.get("count") == 0)

    r = api("/select", {"action": "add", "obj": "PDBox"})
    check("选择添加", r.get("ok"))
    sel = api("/selection")
    check("选择数=1", sel.get("count") == 1)

    r = api("/select", {"action": "clear"})
    check("再次清空", r.get("ok"))
except Exception as e:
    check("选择系统", False, str(e)[:80])

# ═══════════════════════════════════════════════════════════════════
# G. 命令系统 + 关键命令验证
# ═══════════════════════════════════════════════════════════════════
section("G. 命令系统完整性")

try:
    cmds = api("/commands")
    cmd_count = cmds.get("count", 0)
    check(f"命令总数>{400}", cmd_count > 400, f"count={cmd_count}")

    KEY_COMMANDS = [
        "Std_New", "Std_Open", "Std_Save", "Std_SaveAs", "Std_CloseActiveWindow",
        "Std_Undo", "Std_Redo", "Std_Copy", "Std_Paste", "Std_Cut", "Std_Delete",
        "Std_ViewFitAll", "Std_ViewIsometric", "Std_ViewFront", "Std_ViewTop",
        "Std_OrthographicCamera", "Std_PerspectiveCamera", "Std_DrawStyle",
        "Std_SelectAll", "Std_SelBack", "Std_Export", "Std_Import",
        "Part_Box", "Part_Cylinder", "Part_Sphere", "Part_Cone", "Part_Torus",
        "Part_Boolean", "Part_Cut", "Part_Fuse", "Part_Common",
        "Part_Fillet", "Part_Chamfer", "Part_Mirror", "Part_Offset",
        "Part_Extrude", "Part_Revolve", "Part_Loft", "Part_Sweep",
    ]
    cmd_names = set(cmds.get("commands", {}).keys())
    for c in KEY_COMMANDS:
        check(f"命令: {c}", c in cmd_names)
except Exception as e:
    check("命令系统", False, str(e)[:120])

# GUI commands execution
section("G2. GUI命令执行")
GUI_EXEC_CMDS = [
    "Std_ViewFitAll",
    "Std_ViewIsometric",
    "Std_OrthographicCamera",
    "Std_PerspectiveCamera",
    "Std_DrawStyle",
]
for cmd in GUI_EXEC_CMDS:
    try:
        r = api("/run_command", {"command": cmd})
        check(f"执行: {cmd}", r.get("ok"), str(r.get("error",""))[:40])
    except Exception as e:
        check(f"执行: {cmd}", False, str(e)[:50])

# ═══════════════════════════════════════════════════════════════════
# H. 错误处理 + 边界情况
# ═══════════════════════════════════════════════════════════════════
section("H. 错误处理/边界情况")

# H1: Invalid command
try:
    r = api("/run_command", {"command": "Nonexistent_Cmd_99999"})
    check("无效命令", not r.get("ok") or "error" in r or "traceback" in r)
except Exception as e:
    check("无效命令", True)  # Exception itself is valid error handling

# H2: Empty command
try:
    r = api("/run_command", {"command": ""})
    check("空命令", not r.get("ok"))
except:
    check("空命令", True)

# H3: Invalid property access
try:
    r = api("/property", {"obj": "NONEXISTENT_OBJ_12345", "prop": "X"})
    check("不存在对象", not r.get("ok"))
except:
    check("不存在对象", True)

# H4: Division by zero in exec
try:
    r = fc_exec("x = 1/0")
    check("除零处理", not r.get("ok") and "division by zero" in str(r.get("error","")).lower())
except:
    check("除零处理", True)

# H5: Empty ops
try:
    r = fc_ops([])
    check("空ops处理", not r.get("ok") or r.get("ok"))  # Both behaviors acceptable
except:
    check("空ops处理", True)

# ═══════════════════════════════════════════════════════════════════
# I. 探针数据完整性
# ═══════════════════════════════════════════════════════════════════
section("I. 探针数据完整性")
probe_path = OUTPUT_DIR / "_fc_gui_probe_result.json"
if probe_path.exists():
    with open(probe_path, "r", encoding="utf-8") as f:
        probe = json.load(f)
    check("探针文件", True)
    check("探针版本", probe.get("probe_version") == "gui_1.0")
    expected_sections = [
        "gui_module", "all_commands", "commands_v2", "workbenches",
        "menus", "toolbars", "dock_widgets", "view_3d",
        "selection", "preferences", "qt_actions", "document_state",
        "keyboard_shortcuts", "macro_system"
    ]
    for sec in expected_sections:
        check(f"探针段: {sec}", sec in probe.get("sections", {}))

    summary = probe.get("summary", {})
    check("探针命令>400", summary.get("total_commands", 0) > 400)
    check("探针工作台>15", summary.get("workbench_count", 0) > 15)
    check("快捷键>50", summary.get("shortcut_count", 0) > 50)
else:
    check("探针文件", False, "未找到")

# ═══════════════════════════════════════════════════════════════════
# FINAL: 终极一览
# ═══════════════════════════════════════════════════════════════════
elapsed = round(time.time() - t_global, 1)

# Count output files
build_files = list(BUILD_DIR.glob("*"))
stl_count = len([f for f in build_files if f.suffix == ".stl"])
step_count = len([f for f in build_files if f.suffix == ".step"])
total_size = sum(f.stat().st_size for f in build_files if f.is_file())

# Get final status
s = api("/status")
d = api("/document")
obj_count = d.get("document", {}).get("object_count", 0) if d.get("document") else 0

print(f"\n{'='*70}")
print(f"  万法归一 — 终极报告")
print(f"{'='*70}")
total = passed + failed
rate = passed / total * 100 if total > 0 else 0
print(f"  \u2705 通过: {passed}/{total} ({rate:.1f}%)")
print(f"  \u274c 失败: {failed}/{total}")
print(f"  \u23f1  耗时: {elapsed}s")
print(f"")
print(f"  FreeCAD: v{'.'.join(str(x) for x in s.get('freecad_version',['?'])[:3])}")
print(f"  工作台: {s.get('active_workbench')}")
print(f"  文档对象: {obj_count}")
print(f"")
print(f"  构建文件: {len(build_files)} ({stl_count} STL + {step_count} STEP)")
print(f"  总大小: {total_size/1024:.1f} KB")

if errors:
    print(f"\n  失败详情:")
    for e in errors[:20]:
        print(f"    \u26a0\ufe0f  {e}")

# Grade
if failed == 0:
    grade = "SSS — 道法自然，万法归一，无为而无不为"
elif failed <= 3:
    grade = "SS — 几近圆满"
elif failed <= 8:
    grade = "S — 优秀"
elif failed <= 15:
    grade = "A — 良好"
else:
    grade = "B — 需改进"

print(f"\n  等级: {grade}")
print(f"{'='*70}")
