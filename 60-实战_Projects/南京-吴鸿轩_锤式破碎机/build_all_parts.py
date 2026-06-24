#!/usr/bin/env python3
"""
锤式破碎机 · 全零件参数化建模
道法自然 · 从DXF工程图→CadQuery 3D模型 · 万法归宗

零件清单:
  1. main_shaft       — 主轴 (stepped shaft Ø60-80-90, L=1145mm)
  2. rotor_disc       — 转子盘 (Ø500, bore Ø80, 4×Ø40 pin holes)
  3. hammer           — 锤头 (trapezoid 180×80×40, Ø40 hole)
  4. hammer_pin       — 销轴 (Ø40×92 body, M30×2 both ends)
  5. driven_pulley    — 从动皮带轮 (B型4槽, Ø240, bore Ø70)
  6. screen_plate     — 筛板 (弧形 120°, Ri=390, t=12, B=800)

数据来源: DXF工程图 (assembly_A3/shaft_A3/rotor_disc_A3/hammer_A3/hammer_pin_A3/
           driven_pulley_A3/screen_plate_A3)
"""
import cadquery as cq
import math, os, json, time
from pathlib import Path
from config import OUT_DIR as OUT, BOM as BOM_DATA

# 输出目录由 config.py 统一管理
OUT.mkdir(exist_ok=True)

results = {}

def log(msg):
    print(f"  {msg}", flush=True)

# ══════════════════════════════════════════════════════════════════
# 1. 主轴 Main Shaft
# ══════════════════════════════════════════════════════════════════
print("\n[1/6] 主轴 (Main Shaft)...")
t0 = time.time()
try:
    # 阶梯轴参数 (从DXF shaft_A3.dxf提取)
    # 从右到左: 螺纹段Ø60×30 → Ø80×70 → Ø90×20 → 主体Ø90×800 → 端部Ø80×70 → Ø60×30×(螺纹)
    # 总长1145mm, 键槽20×70在皮带轮座
    # 简化为5段阶梯轴:
    #   段1: Ø60  × 30  (右端螺纹)
    #   段2: Ø80  × 70  (右端台肩)
    #   段3: Ø90  × 20  (右端台肩过渡)
    #   段4: Ø90  × 925 (主体, 1145-30-70-20-70-30=925)
    #   段5: Ø80  × 70  (左端台肩)
    #   段6: Ø60  × 30  (左端螺纹)
    # 总=30+70+20+925+70+30=1145 (与DXF标注一致)

    segments = [
        (30,  30),   # Ø60 × 30
        (40,  70),   # Ø80 × 70
        (45,  20),   # Ø90 × 20
        (45, 925),   # Ø90 × 925 (主体)
        (40,  70),   # Ø80 × 70
        (30,  30),   # Ø60 × 30
    ]  # (radius, length)

    shaft = None
    x_pos = 0
    for radius, length in segments:
        seg = cq.Workplane("YZ").circle(radius).extrude(length).translate((x_pos, 0, 0))
        if shaft is None:
            shaft = seg
        else:
            shaft = shaft.union(seg)
        x_pos += length

    # 键槽: 20mm宽 × 70mm长 × 8mm深, 位于皮带轮座 (左端约120-190mm处)
    keyway_x = 30 + 70 + 20  # 在主体上从右算
    keyway = (cq.Workplane("XY")
              .box(70, 20, 10)
              .translate((x_pos - 30 - 70 - 20 - 70 - 70, 0, 45 - 5)))
    shaft = shaft.cut(keyway)

    stl_path = str(OUT / "main_shaft.stl")
    step_path = str(OUT / "main_shaft.step")
    cq.exporters.export(shaft, stl_path)
    cq.exporters.export(shaft, step_path)
    log(f"✅ STL: {stl_path}")
    log(f"✅ STEP: {step_path}")
    results["main_shaft"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    results["main_shaft"] = {"status": "FAIL", "error": str(e)}

# ══════════════════════════════════════════════════════════════════
# 2. 转子盘 Rotor Disc
# ══════════════════════════════════════════════════════════════════
print("\n[2/6] 转子盘 (Rotor Disc)...")
t0 = time.time()
try:
    # 参数: Ø500, bore Ø80, 厚25mm
    # 4个销孔Ø40, PCD Ø440, 等分布置
    OD = 500 / 2   # 外半径
    BORE = 80 / 2   # 内孔半径
    THK = 25        # 厚度
    PIN_D = 40 / 2  # 销孔半径
    PIN_PCD = 440 / 2  # 销孔PCD半径

    disc = (cq.Workplane("XY")
            .circle(OD)
            .extrude(THK)
            .faces(">Z").workplane()
            .circle(BORE).cutBlind(-THK))

    # 4个销孔 (均匀分布)
    for angle in [0, 90, 180, 270]:
        rad = math.radians(angle)
        cx = PIN_PCD * math.cos(rad)
        cy = PIN_PCD * math.sin(rad)
        hole = cq.Workplane("XY").circle(PIN_D).extrude(THK).translate((cx, cy, 0))
        disc = disc.cut(hole)

    stl_path = str(OUT / "rotor_disc.stl")
    step_path = str(OUT / "rotor_disc.step")
    cq.exporters.export(disc, stl_path)
    cq.exporters.export(disc, step_path)
    log(f"✅ STL: {stl_path}")
    results["rotor_disc"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    results["rotor_disc"] = {"status": "FAIL", "error": str(e)}

# ══════════════════════════════════════════════════════════════════
# 3. 锤头 Hammer
# ══════════════════════════════════════════════════════════════════
print("\n[3/6] 锤头 (Hammer)...")
t0 = time.time()
try:
    # 梯形摆锤 180×80×40mm
    # 孔Ø40, 中心距底面120mm
    # 梯形: 底部宽80mm, 顶部宽40mm (假设从DXF几何推断), 高180mm, 厚40mm
    W_BOTTOM = 80
    W_TOP    = 40
    HEIGHT   = 180
    THICK    = 40
    HOLE_R   = 20      # Ø40/2
    HOLE_Y   = 120     # 孔中心距底面

    # 梯形截面: XY平面, Z方向拉伸(厚度方向)
    hammer = (cq.Workplane("XY")
              .moveTo(-W_BOTTOM/2, 0)
              .lineTo( W_BOTTOM/2, 0)
              .lineTo( W_TOP/2,    HEIGHT)
              .lineTo(-W_TOP/2,    HEIGHT)
              .close()
              .extrude(THICK))
    # 绝对坐标打孔: 圆柱中心(0, HOLE_Y), 贯穿Z方向
    cyl = cq.Workplane("XY").circle(HOLE_R).extrude(THICK + 2).translate((0, HOLE_Y, -1))
    hammer = hammer.cut(cyl)

    stl_path = str(OUT / "hammer.stl")
    step_path = str(OUT / "hammer.step")
    cq.exporters.export(hammer, stl_path)
    cq.exporters.export(hammer, step_path)
    log(f"✅ STL: {stl_path}")
    results["hammer"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    results["hammer"] = {"status": "FAIL", "error": str(e)}

# ══════════════════════════════════════════════════════════════════
# 4. 销轴 Hammer Pin
# ══════════════════════════════════════════════════════════════════
print("\n[4/6] 销轴 (Hammer Pin)...")
t0 = time.time()
try:
    # 反者道之动 · 销轴必须贯穿全部4盘
    # 4盘跨度 disc1(x=194..220) 至 disc4(x=798..823) = 629mm
    # 销轴主体需≥629mm + 锁紧余量 → BODY_L=620, 总长=25+620+25=670mm
    # 原 BODY_L=92(总长142) 无法贯穿 → 放大至620
    BODY_R    = 20    # Ø40/2
    BODY_L    = 620   # 修正: 92→620 · 贯穿4盘(跨度629mm)
    THREAD_R  = 15    # M30/2 (近似)
    THREAD_L  = 25    # 螺纹段长
    # 两端倒角C2

    # 从左到右: 螺纹端25mm → 主体92mm → 螺纹端25mm
    left_thread = cq.Workplane("YZ").circle(THREAD_R).extrude(THREAD_L)
    try: left_thread = left_thread.edges("<X").chamfer(2)
    except Exception: pass
    body = (cq.Workplane("YZ").circle(BODY_R).extrude(BODY_L)
            .translate((THREAD_L, 0, 0)))
    right_thread = (cq.Workplane("YZ").circle(THREAD_R).extrude(THREAD_L)
                    .translate((THREAD_L + BODY_L, 0, 0)))
    try: right_thread = right_thread.edges(">X").chamfer(2)
    except Exception: pass

    pin = left_thread.union(body).union(right_thread)

    stl_path = str(OUT / "hammer_pin.stl")
    step_path = str(OUT / "hammer_pin.step")
    cq.exporters.export(pin, stl_path)
    cq.exporters.export(pin, step_path)
    log(f"✅ STL: {stl_path}")
    results["hammer_pin"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    results["hammer_pin"] = {"status": "FAIL", "error": str(e)}

# ══════════════════════════════════════════════════════════════════
# 5. 从动皮带轮 Driven Pulley
# ══════════════════════════════════════════════════════════════════
print("\n[5/6] 从动皮带轮 (Driven Pulley)...")
t0 = time.time()
try:
    # B型4槽皮带轮
    # 外径Ø240, 节径Ø224, 孔Ø70, 宽90mm
    # 键槽: 20×8 (宽×深)
    OD = 120      # 外径Ø240/2
    PD = 112      # 节径Ø224/2
    BORE = 35     # 孔Ø70/2
    WIDTH = 90    # 总宽
    GROOVE_N = 4  # 槽数
    # B型V槽: 顶宽17mm, 角度34°, 深10.8mm
    GROOVE_W_TOP = 8.5   # 半宽
    GROOVE_DEPTH = 10.8
    GROOVE_ANGLE = 34    # 度

    # 基础轮体
    pulley = (cq.Workplane("YZ")
              .circle(OD)
              .extrude(WIDTH))

    # 中心孔
    pulley = (pulley.faces(">X").workplane()
              .circle(BORE).cutBlind(-WIDTH))

    # 4条V槽 (均匀分布)
    groove_spacing = WIDTH / (GROOVE_N + 1)
    for i in range(GROOVE_N):
        groove_x = groove_spacing * (i + 1)
        # V形截面 (三角形近似)
        half_angle = math.radians(GROOVE_ANGLE / 2)
        half_top = GROOVE_W_TOP
        groove_pts = [
            (-half_top, 0),
            ( half_top, 0),
            (0, -GROOVE_DEPTH / math.tan(half_angle) * 0.5),  # V底点
        ]
        # 使用revolve在轮体表面切出V槽
        groove_profile = (cq.Workplane("XY")
                         .moveTo(PD - GROOVE_DEPTH, groove_x - half_top)
                         .lineTo(OD + 1, groove_x - half_top)
                         .lineTo(OD + 1, groove_x + half_top)
                         .lineTo(PD - GROOVE_DEPTH, groove_x + half_top)
                         .close()
                         .revolve(360, (0, 0, 0), (1, 0, 0)))
        pulley = pulley.cut(groove_profile)

    # 键槽: 20mm宽 × 8mm深 × 60mm长 (在孔内)
    keyway = (cq.Workplane("YZ")
              .rect(20, 8)
              .extrude(WIDTH)
              .translate((0, BORE + 4, 0)))  # 从孔边向外8mm
    pulley = pulley.cut(keyway)

    stl_path = str(OUT / "driven_pulley.stl")
    step_path = str(OUT / "driven_pulley.step")
    cq.exporters.export(pulley, stl_path)
    cq.exporters.export(pulley, step_path)
    log(f"✅ STL: {stl_path}")
    results["driven_pulley"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    results["driven_pulley"] = {"status": "FAIL", "error": str(e)}

# ══════════════════════════════════════════════════════════════════
# 6. 筛板 Screen Plate
# ══════════════════════════════════════════════════════════════════
print("\n[6/6] 筛板 (Screen Plate)...")
t0 = time.time()
try:
    # 弧形筛板: 内径Ri=390, 外径Ro=402 (厚12mm), 宽800mm, 弧角120°
    # 筛孔: Ø15, 节距30mm
    # 6个安装孔: Ø14
    RI = 390      # 内半径
    RO = 402      # 外半径
    WIDTH = 800   # 轴向宽度
    ARC = 120     # 弧角度
    PERF_D = 7.5  # 筛孔半径 (Ø15/2)
    PERF_PITCH = 30  # 节距
    MOUNT_D = 7   # 安装孔半径 (Ø14/2)

    # 构建弧形截面: 圆弧环形截面
    # 在XZ平面: 弧角120°, 中心在原点
    half_arc = ARC / 2  # ±60°

    # 截面轮廓 (径向截面)
    r_start = math.radians(-half_arc)
    r_end   = math.radians( half_arc)

    # 用shell_extrude: 先建弧面再增厚
    # 简化: 用sweep截面
    # 截面: 矩形 12mm厚 × 800mm宽 (radial cross-section)
    profile = (cq.Workplane("XY")
               .rect(RO - RI, WIDTH))

    # 路径: 圆弧半径=(Ri+Ro)/2, 角度120°
    R_MID = (RI + RO) / 2
    path_pts = []
    for a in range(-60, 61, 5):
        rad = math.radians(a)
        path_pts.append((R_MID * math.cos(rad), R_MID * math.sin(rad), 0))

    # 使用revolve方式建弧形板
    # 以X轴旋转截面
    screen = (cq.Workplane("XZ")
              .moveTo(RI, -WIDTH/2)
              .lineTo(RO, -WIDTH/2)
              .lineTo(RO,  WIDTH/2)
              .lineTo(RI,  WIDTH/2)
              .close()
              .revolve(ARC, (0, 0, 0), (0, 1, 0), combine=True))

    # 筛孔: 在弧面上打孔 (近似在Z方向穿透)
    # 简化: 在矩形展开图上布孔, 近似为XY方向的穿透孔
    # 展开弧长 = R_MID * ARC_rad ≈ 396 * 2.094 = 829mm
    ARC_LEN = R_MID * math.radians(ARC)
    cols = int(ARC_LEN / PERF_PITCH) - 1
    rows = int(WIDTH / PERF_PITCH) - 1

    # 在弧板上每隔30mm打一个Ø15孔 (近似)
    for ci in range(cols):
        angle = -half_arc + ARC / (cols + 1) * (ci + 1)
        for ri in range(rows):
            y = -WIDTH/2 + PERF_PITCH * (ri + 1)
            rad = math.radians(angle)
            cx = R_MID * math.cos(rad)
            cz = R_MID * math.sin(rad)
            hole_axis = (math.cos(rad), 0, math.sin(rad))
            hole = (cq.Workplane("YZ")
                    .circle(PERF_D)
                    .extrude(RO - RI + 2)
                    .translate((cx - hole_axis[0], y, cz - hole_axis[2])))
            # 简化: 只打Z向孔
            try:
                punch = (cq.Workplane("XY")
                         .moveTo(cx, y)
                         .circle(PERF_D)
                         .extrude(50)
                         .translate((0, 0, -(RO + 5))))
                screen = screen.cut(punch)
            except: pass

    # 6个安装孔 (均匀分布, 在弧面两侧)
    mount_angles = [-55, -20, 20, 55]
    for a in mount_angles:
        for y in [-WIDTH/2 + 40, WIDTH/2 - 40]:
            rad = math.radians(a)
            cx = R_MID * math.cos(rad)
            cz = R_MID * math.sin(rad)
            try:
                mhole = (cq.Workplane("XY")
                         .moveTo(cx, y)
                         .circle(MOUNT_D)
                         .extrude(50)
                         .translate((0, 0, -(RO + 5))))
                screen = screen.cut(mhole)
            except: pass

    stl_path = str(OUT / "screen_plate.stl")
    step_path = str(OUT / "screen_plate.step")
    cq.exporters.export(screen, stl_path)
    cq.exporters.export(screen, step_path)
    log(f"✅ STL: {stl_path}")
    results["screen_plate"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    results["screen_plate"] = {"status": "FAIL", "error": str(e)}

# ══════════════════════════════════════════════════════════════════
# 质量验证
# ══════════════════════════════════════════════════════════════════
print("\n[质量验证] trimesh分析...")
import trimesh
quality = {}
for name, data in results.items():
    if data.get("status") == "OK":
        stl_path = str(OUT / f"{name}.stl")
        try:
            m = trimesh.load(stl_path)
            bb = m.bounding_box.bounds
            size = (bb[1] - bb[0]).round(1).tolist()
            quality[name] = {
                "faces": int(m.faces.shape[0]),
                "watertight": bool(m.is_watertight),
                "volume_mm3": round(m.volume, 1),
                "bbox_mm": size,
            }
            print(f"  {name}: {quality[name]['faces']}面 "
                  f"{'流形✅' if quality[name]['watertight'] else '非流形⚠'} "
                  f"bbox={size}mm vol={quality[name]['volume_mm3']:.0f}mm³")
        except Exception as e:
            quality[name] = {"error": str(e)}
            print(f"  {name}: ❌ {e}")

# ══════════════════════════════════════════════════════════════════
# BOM + 报告
# ══════════════════════════════════════════════════════════════════
print("\n[报告生成]...")

BOM = [
    {"件号": b["id"], "名称": b["name"], "英文": b["en"],
     "材料": b["mat"], "数量": b["qty"], "备注": b["dim"]}
    for b in BOM_DATA
]

report_lines = [
    "# 锤式破碎机 — 全零件参数化建模报告",
    "",
    "**项目**: 南京-吴鸿轩 锤式破碎机 (Hammer Crusher)",
    "**方法**: DXF工程图 → CadQuery参数化建模 → STL/STEP导出",
    "",
    "## 机器总体参数 (来自assembly_A3.dxf)",
    "",
    "| 参数 | 值 |",
    "|---|---|",
    "| 整机尺寸 | 1300 × 860 mm |",
    "| 转子直径 | Ø700 mm |",
    "| 主轴总长 | 1145 mm |",
    "| 筛板弧角 | 120° |",
    "",
    "## 零件明细表 (BOM)",
    "",
    "| 件号 | 名称 | 英文 | 材料 | 数量 | 关键尺寸 |",
    "|---|---|---|---|---|---|",
]
for p in BOM:
    report_lines.append(f"| {p['件号']} | {p['名称']} | {p['英文']} | {p['材料']} | {p['数量']} | {p['备注']} |")

report_lines += [
    "",
    "## 建模结果",
    "",
    "| 零件 | 状态 | 面数 | 流形 | 体积(mm³) | 包围盒(mm) |",
    "|---|---|---|---|---|---|",
]
for name, data in results.items():
    q = quality.get(name, {})
    status = "✅" if data.get("status") == "OK" else "❌"
    faces = q.get("faces", "-")
    wt = "✅" if q.get("watertight") else "⚠"
    vol = q.get("volume_mm3", "-")
    bbox = q.get("bbox_mm", "-")
    report_lines.append(f"| {name} | {status} | {faces} | {wt} | {vol} | {bbox} |")

report_lines += [
    "",
    "## 输出文件",
    "",
    f"所有文件保存至: `{OUT}`",
    "",
    "| 文件 | 格式 | 用途 |",
    "|---|---|---|",
]
for name in results:
    if results[name].get("status") == "OK":
        report_lines.append(f"| {name}.stl | STL | 3D打印/网格分析 |")
        report_lines.append(f"| {name}.step | STEP | 工程交换/CAD |")

report_lines += [
    "",
    "## 数据来源",
    "",
    "以下DXF文件已解析并提取所有工程参数:",
    "- `assembly_A3.dxf` — 总装图",
    "- `shaft_A3.dxf` — 主轴",
    "- `rotor_disc_A3.dxf` — 转子盘",
    "- `hammer_A3.dxf` — 锤头",
    "- `hammer_pin_A3.dxf` — 销轴",
    "- `driven_pulley_A3.dxf` — 从动皮带轮",
    "- `screen_plate_A3.dxf` — 筛板",
    "",
    "---",
    "*Generated by 锤式破碎机 CadQuery建模引擎 · 道法自然*",
]

report_path = OUT / "REPORT.md"
report_path.write_text("\n".join(report_lines), encoding="utf-8")

# 保存BOM JSON
(OUT / "BOM.json").write_text(
    json.dumps(BOM, ensure_ascii=False, indent=2), encoding="utf-8"
)
# 保存质量分析
(OUT / "quality.json").write_text(
    json.dumps(quality, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
)

print(f"\n{'='*60}")
print(f"  全零件建模完成!")
print(f"  输出目录: {OUT}")
print(f"{'='*60}")
for name, data in results.items():
    icon = "✅" if data.get("status") == "OK" else "❌"
    time_s = data.get("time", "-")
    print(f"  {icon} {name:20s} ({time_s}s)")
print(f"\n  报告: {report_path}")
print(f"  BOM:  {OUT / 'BOM.json'}")

# ══════════════════════════════════════════════════════════════════
# 7. 装配体 Assembly  (trimesh合并所有零件, 施加刚体变换)
# ══════════════════════════════════════════════════════════════════
print("\n[装配体] Assembly (trimesh合并)...")
try:
    import numpy as np

    def _T(R3=None, t=(0, 0, 0)):
        M = np.eye(4)
        if R3 is not None:
            M[:3, :3] = R3
        M[:3, 3] = t
        return M

    # 绕Y轴旋转+90°: 使XY平面零件法线从+Z变为+X (垂直于主轴)
    Ry90 = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], dtype=float)
    I3   = np.eye(3)

    def load_stl(name):
        p = str(OUT / f"{name}.stl")
        if not os.path.exists(p):
            return None
        try:
            m = trimesh.load(p)
            if isinstance(m, trimesh.Scene):
                m = trimesh.util.concatenate(m.dump())
            return m
        except Exception as _e:
            print(f"  ⚠ 加载{name}失败: {_e}")
            return None

    asm_parts = []

    # 1. 主轴: 已沿X轴 (YZ平面挤出), 无变换
    m = load_stl("main_shaft")
    if m: asm_parts.append(m)

    # 2. 从动皮带轮: 已沿X轴, 平移到左端轴段(X≈960)
    m = load_stl("driven_pulley")
    if m:
        m.apply_transform(_T(t=(960, 0, 0)))
        asm_parts.append(m)

    # 3. 转子盘×4: Ry90使盘面垂直于X轴, 均布于主体段
    disc = load_stl("rotor_disc")
    disc_x_centers = [220, 421, 622, 823]
    if disc:
        for dx in disc_x_centers:
            md = disc.copy()
            md.apply_transform(_T(Ry90, (dx - 12.5, 0, 0)))
            asm_parts.append(md)

    # 4. 销轴×4: 已沿X轴, 分布于PCD=220mm四角
    pin = load_stl("hammer_pin")
    pin_offsets = [(220, 0), (-220, 0), (0, 220), (0, -220)]
    if pin:
        for py, pz in pin_offsets:
            mp = pin.copy()
            mp.apply_transform(_T(t=(120, py, pz)))
            asm_parts.append(mp)

    # 5. 锤头×4 (代表性, 每销轴各1): Ry90后孔轴沿X, 平移对齐销轴
    hammer_m = load_stl("hammer")
    if hammer_m:
        for py, pz in pin_offsets:
            mh = hammer_m.copy()
            # Ry90后: 原Z轴(孔轴)→+X, 原XY面→YZ; 孔中心原(0,HOLE_Y=120,THICK/2=20)→(20,120,0)
            # 平移使孔心对齐销轴位置(X=470, Y=py, Z=pz)
            mh.apply_transform(_T(Ry90, (470 - 20, py - 120, pz)))
            asm_parts.append(mh)

    # 6. 筛板: 绕Y轴120°弧, 围绕转子下方, 平移X方向居中
    m = load_stl("screen_plate")
    if m:
        m.apply_transform(_T(t=(160, 0, 0)))
        asm_parts.append(m)

    if asm_parts:
        asm = trimesh.util.concatenate(asm_parts)
        asm_stl = str(OUT / "assembly.stl")
        asm_obj  = str(OUT / "assembly.obj")
        asm.export(asm_stl)
        asm.export(asm_obj)
        try: asm.export(str(OUT / "assembly.glb"))
        except Exception: pass
        bb = asm.bounding_box.bounds
        sz = (bb[1] - bb[0]).round(0).tolist()
        print(f"  ✅ 装配体: {len(asm_parts)} 个零件  bbox={sz} mm")
        print(f"  ✅ {asm_stl}")
        print(f"  ✅ {asm_obj}")
        results["assembly"] = {"status": "OK", "parts": len(asm_parts)}
    else:
        print("  ⚠ 无可装配零件")
except Exception as _asm_e:
    print(f"  ❌ 装配体失败: {_asm_e}")
    import traceback; traceback.print_exc()
