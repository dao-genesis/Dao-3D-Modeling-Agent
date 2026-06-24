#!/usr/bin/env python3
"""Y180L-4 三相异步电动机 · 真实建模 · 反者道之动
依 GB/T 18488.1 / JB/T 10391 标准尺寸:
  H=180 (中心高) · L=710 (总长) · 22kW 1470rpm
  D=48 E=110 F=14 (轴伸 Ø48×110, 键宽14)
  A=279 B=279 C=121 K=14.5 (底脚安装孔距)
  机座外径~Ø360 · 接线盒~200×160×150 · 底脚厚 20mm
  12片轴向散热筋 · 前后端盖 · 风扇罩

局部坐标系:
  原点 = 前端盖外表面中心 (drive end cap outer face center)
  +X = 轴伸方向 (机外朝驱动轮)
  +Z = 向上 (朝接线盒)
  +Y = 轴向 (机器侧面)
  轴中心线: y=0, z=0
  底脚底面: z = -180

建模步骤:
  1. 机座圆柱 (带散热筋) · x ∈ [-500, 0]
  2. 前端盖 · x ∈ [-40, 0]
  3. 后端盖 · x ∈ [-540, -500]
  4. 轴伸 Ø48×110 · x ∈ [0, +110]
  5. 键槽 14×9 深40mm
  6. 底脚 4 块 · z = -180
  7. 接线盒 · z = +180 顶部
  8. 风扇罩 (后端)
"""
import cadquery as cq
import math, time, json
from pathlib import Path
import sys

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
from config import OUT_DIR

OUT_DIR.mkdir(exist_ok=True)

# ─── Y180L-4 标准尺寸 ───────────────────────────────────────
H         = 180     # 中心高
L_TOTAL   = 710     # 总长
FRAME_OD  = 360     # 机座外径 (近似 2*H)
FRAME_L   = 500     # 机座主体长度
ENDCAP_D  = 320     # 端盖直径
ENDCAP_L  = 40      # 端盖厚度
FAN_D     = 340     # 风扇罩直径
FAN_L     = 80      # 风扇罩长 (后端)

SHAFT_D   = 48      # 轴伸直径 D
SHAFT_L   = 110     # 轴伸长度 E
KEY_W     = 14      # 键宽 F
KEY_H     = 9       # 键高
KEY_L     = 80      # 键槽长 (<E=110)

FOOT_A    = 279     # 底脚孔距轴向
FOOT_B    = 279     # 底脚孔距横向
FOOT_C    = 121     # 底脚孔距后端
FOOT_K    = 14.5    # 底脚孔径
FOOT_W    = 70      # 底脚板宽
FOOT_T    = 20      # 底脚板厚
FOOT_L_EA = 100     # 每块底脚板轴向长

JB_W      = 200     # 接线盒长 (X方向)
JB_D      = 160     # 接线盒宽 (Y方向)
JB_H      = 150     # 接线盒高 (Z方向)

FIN_N     = 12      # 散热筋数
FIN_W     = 10      # 筋厚 (周向)
FIN_R     = 15      # 筋高 (径向)

results = {}
t0 = time.time()

try:
    # ═══ 1. 机座主体圆柱 ═══════════════════════════════════════
    # 前端盖外表面在 x=0, 机座从 x=-40 到 x=-540
    frame = (cq.Workplane("YZ")
             .circle(FRAME_OD / 2)
             .extrude(-FRAME_L)
             .translate((-ENDCAP_L, 0, 0)))

    # 顶部削平 (接线盒安装面)
    flat_top = (cq.Workplane("XY")
                .box(FRAME_L, JB_D + 20, 20)
                .translate((-ENDCAP_L - FRAME_L / 2, 0, FRAME_OD / 2 - 5)))
    frame = frame.cut(flat_top)

    # ═══ 2. 散热筋 (轴向, FIN_N 均布, 不含顶部削平区) ═══════
    fins = None
    for i in range(FIN_N):
        ang = 360 * i / FIN_N - 90  # 起始角让筋均布
        # 跳过顶部削平区域 (±30°)
        if abs(((ang + 90) % 360) - 180) < 30:
            continue
        rad = math.radians(ang)
        fy = (FRAME_OD / 2 + FIN_R / 2 - 2) * math.cos(rad)
        fz = (FRAME_OD / 2 + FIN_R / 2 - 2) * math.sin(rad)
        fin = (cq.Workplane("YZ")
               .rect(FIN_W, FIN_R)
               .extrude(-FRAME_L)
               .translate((-ENDCAP_L, fy, fz)))
        # 绕轴转到该角度
        fin = fin.rotate((0, 0, 0), (1, 0, 0), ang + 90)
        if fins is None:
            fins = fin
        else:
            fins = fins.union(fin)
    if fins is not None:
        frame = frame.union(fins)

    # ═══ 3. 前端盖 (D-end) ═════════════════════════════════════
    front_cap = (cq.Workplane("YZ")
                 .circle(ENDCAP_D / 2)
                 .extrude(-ENDCAP_L))
    # 中心轴孔 Ø60 (容纳轴伸穿出)
    bore = (cq.Workplane("YZ")
            .circle(30)
            .extrude(-ENDCAP_L - 2)
            .translate((1, 0, 0)))
    front_cap = front_cap.cut(bore)
    # 前端盖突台 (轴承座)
    bearing_boss = (cq.Workplane("YZ")
                    .circle(70)
                    .extrude(20)
                    .translate((0, 0, 0)))
    bearing_boss = bearing_boss.cut(
        cq.Workplane("YZ").circle(30).extrude(22).translate((-1, 0, 0)))
    front_cap = front_cap.union(bearing_boss)

    # ═══ 4. 后端盖 (N-end) + 风扇罩 ════════════════════════════
    rear_cap = (cq.Workplane("YZ")
                .circle(ENDCAP_D / 2)
                .extrude(-ENDCAP_L)
                .translate((-ENDCAP_L - FRAME_L, 0, 0)))
    fan_cover = (cq.Workplane("YZ")
                 .circle(FAN_D / 2)
                 .extrude(-FAN_L)
                 .translate((-ENDCAP_L - FRAME_L - ENDCAP_L, 0, 0)))
    # 风扇罩开槽 (气孔, 4个扇形)
    for a in [0, 90, 180, 270]:
        rad = math.radians(a)
        hole = (cq.Workplane("YZ")
                .moveTo(120 * math.cos(rad - math.radians(20)),
                        120 * math.sin(rad - math.radians(20)))
                .lineTo(160 * math.cos(rad - math.radians(20)),
                        160 * math.sin(rad - math.radians(20)))
                .lineTo(160 * math.cos(rad + math.radians(20)),
                        160 * math.sin(rad + math.radians(20)))
                .lineTo(120 * math.cos(rad + math.radians(20)),
                        120 * math.sin(rad + math.radians(20)))
                .close()
                .extrude(-FAN_L - 4)
                .translate((-ENDCAP_L - FRAME_L - ENDCAP_L + 2, 0, 0)))
        fan_cover = fan_cover.cut(hole)

    # ═══ 5. 轴伸 Ø48 × 110 ═══════════════════════════════════
    shaft = (cq.Workplane("YZ")
             .circle(SHAFT_D / 2)
             .extrude(SHAFT_L))
    # 轴伸末端倒角 C2
    try:
        shaft = shaft.edges(">X").chamfer(2)
    except Exception:
        pass

    # 键槽 14×9 深9mm × 长80mm (从x=SHAFT_L-KEY_L-10 到 SHAFT_L-10)
    keyway = (cq.Workplane("XY")
              .box(KEY_L, KEY_W, KEY_H * 2)
              .translate((SHAFT_L - KEY_L / 2 - 10, 0, SHAFT_D / 2 - KEY_H / 2 + KEY_H)))
    shaft = shaft.cut(keyway)

    # ═══ 6. 4块底脚 ═════════════════════════════════════════
    # 底脚底面 z = -180. 底脚板 厚20, 顶面 z = -160
    # A=279 (轴向孔距), B=279 (横向孔距)
    # 4块底脚各在 (±A/2, ±B/2) 孔位中心
    feet = None
    foot_corners = [
        (-ENDCAP_L - FOOT_C,              -FOOT_B / 2),   # 前左
        (-ENDCAP_L - FOOT_C,              +FOOT_B / 2),   # 前右
        (-ENDCAP_L - FOOT_C - FOOT_A,     -FOOT_B / 2),   # 后左
        (-ENDCAP_L - FOOT_C - FOOT_A,     +FOOT_B / 2),   # 后右
    ]
    # 底脚板: 每块为 FOOT_L_EA × FOOT_W × FOOT_T 长方体, 以孔位为中心
    for (cx, cy) in foot_corners:
        pad = (cq.Workplane("XY")
               .box(FOOT_L_EA, FOOT_W, FOOT_T)
               .translate((cx, cy, -H + FOOT_T / 2)))
        # 安装孔
        hole = (cq.Workplane("XY")
                .circle(FOOT_K / 2)
                .extrude(FOOT_T + 4)
                .translate((cx, cy, -H - 2)))
        pad = pad.cut(hole)
        if feet is None: feet = pad
        else: feet = feet.union(pad)

    # 底脚与机座之间连接肋 (两侧三角板)
    for side in [-1, +1]:
        y_side = side * (FOOT_B / 2)
        # 两块三角肋: 从底脚顶到机座侧
        rib = (cq.Workplane("XY")
               .box(FRAME_L - 20, 20, H - FOOT_T)
               .translate((-ENDCAP_L - FRAME_L / 2,
                           y_side,
                           -(H - FOOT_T) / 2 - FOOT_T / 2)))
        if feet is None: feet = rib
        else: feet = feet.union(rib)

    # ═══ 7. 接线盒 (顶部) ═══════════════════════════════════
    jb = (cq.Workplane("XY")
          .box(JB_W, JB_D, JB_H)
          .translate((-ENDCAP_L - FRAME_L / 2 + 50,
                      0,
                      FRAME_OD / 2 + JB_H / 2 - 5)))
    # 接线盒盖凸台
    jb_lid = (cq.Workplane("XY")
              .box(JB_W - 30, JB_D - 30, 10)
              .translate((-ENDCAP_L - FRAME_L / 2 + 50,
                          0,
                          FRAME_OD / 2 + JB_H)))
    jb = jb.union(jb_lid)
    # 出线孔 (侧面)
    cable_hole = (cq.Workplane("XZ")
                  .circle(20)
                  .extrude(40)
                  .translate((-ENDCAP_L - FRAME_L / 2 + 50,
                              JB_D / 2 + 20,
                              FRAME_OD / 2 + JB_H / 3)))
    jb = jb.cut(cable_hole)

    # ═══ 8. 吊环 (顶部中央) ═══════════════════════════════════
    lift_eye = (cq.Workplane("XY")
                .circle(20)
                .extrude(50)
                .translate((-ENDCAP_L - FRAME_L / 2,
                            0,
                            FRAME_OD / 2 + 25)))
    ring_hole = (cq.Workplane("XY")
                 .circle(10)
                 .extrude(30)
                 .translate((-ENDCAP_L - FRAME_L / 2,
                             0,
                             FRAME_OD / 2 + 30)))
    lift_eye = lift_eye.cut(ring_hole)

    # ═══ 合体 ═══════════════════════════════════════════════
    motor = frame.union(front_cap).union(rear_cap).union(fan_cover).union(shaft).union(feet).union(jb).union(lift_eye)

    stl_path = str(OUT_DIR / "motor_body.stl")
    step_path = str(OUT_DIR / "motor_body.step")
    # 合并成单一 Compound, 防 SW 识别为 Assembly
    _solids = motor.solids().vals()
    _compound = cq.Compound.makeCompound(_solids)
    print(f"  合并 {len(_solids)} solids → 单一 Compound")
    cq.exporters.export(_compound, stl_path)
    cq.exporters.export(_compound, step_path)
    dt = time.time() - t0
    print(f"  ✅ STL: {stl_path}")
    print(f"  ✅ STEP: {step_path}")
    print(f"  耗时: {dt:.2f}s")
    results["motor_body_y180l4"] = {"status": "OK", "time": round(dt, 2)}

    # 几何验证
    import trimesh
    m = trimesh.load(stl_path)
    bb = m.bounding_box.bounds
    size = (bb[1] - bb[0]).round(1).tolist()
    print(f"  面数={int(m.faces.shape[0])}  流形={m.is_watertight}  bbox={size}mm")
    print(f"  世界Z范围 (底脚应=-180, 顶应≈+255+JB_H)")
    print(f"     实测 Z[{bb[0][2]:.1f}, {bb[1][2]:.1f}]")
    print(f"     实测 X[{bb[0][0]:.1f}, {bb[1][0]:.1f}] (轴伸端=+110, 电机尾=−620)")
    results["motor_body_y180l4"].update({
        "faces": int(m.faces.shape[0]),
        "bbox_mm": size,
        "x_range": [float(bb[0][0]), float(bb[1][0])],
        "z_range": [float(bb[0][2]), float(bb[1][2])],
    })

except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback
    traceback.print_exc()
    results["motor_body_y180l4"] = {"status": "FAIL", "error": str(e)}

(OUT_DIR / "motor_y180l4_results.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"\n道法自然 · Y180L-4 真电机 ✓")
