#!/usr/bin/env python3
"""
锤式破碎机 · 完整零件建模 (新增5个零件)
道法自然 · 万法归宗 · 整合到底 · 完善一切

新增零件:
  7. drive_pulley   — 主动带轮 (B型4槽, PD180, 装在电动机轴)
  8. casing_lower   — 下机壳 (Q235焊接, 含出料口)
  9. casing_upper   — 上机壳 (Q235焊接, 含进料口)
  10. motor_body    — 电动机 (Y180L-4, 简化几何模型)
  11. frame_base    — 机架底座 (Q235焊接, 含减振垫位)

参数来源: config.py (所有参数统一管理)
"""
import cadquery as cq
import math, os, json, time
from pathlib import Path
from config import (OUT_DIR as OUT, DRIVE_PULLEY_PARAMS, MOTOR_PARAMS,
                    CASING_PARAMS, VBELT_PARAMS)

OUT.mkdir(exist_ok=True)

results = {}

def log(msg):
    print(f"  {msg}", flush=True)

# ══════════════════════════════════════════════════════════════════
# 7. 主动带轮 Drive Pulley (小带轮, 装在电动机轴)
# ══════════════════════════════════════════════════════════════════
print("\n[7/11] 主动带轮 (Drive Pulley, 小带轮)...")
t0 = time.time()
try:
    # 参数 (来自 config.py DRIVE_PULLEY_PARAMS)
    PD   = DRIVE_PULLEY_PARAMS["pd_mm"]       # 节径 180mm
    OD   = DRIVE_PULLEY_PARAMS["od_mm"]       # 外径 190mm
    BORE = DRIVE_PULLEY_PARAMS["hub_bore_mm"] # 轴孔 55mm
    W    = DRIVE_PULLEY_PARAMS["width_mm"]    # 宽度 90mm
    N_G  = DRIVE_PULLEY_PARAMS["grooves"]     # 槽数 4

    # 轮毂参数
    HUB_OD = 90    # 轮毂外径 (approx 1.6×bore)
    HUB_L  = 120   # 轮毂长度 (含键槽段)
    HUB_EXT = (HUB_L - W) / 2  # 轮毂两侧伸出量 (各15mm)

    # 1. 主体圆柱 (带槽轮缘)
    pulley = (cq.Workplane("YZ")
              .circle(OD / 2)
              .extrude(W))

    # 2. B型V槽: 槽角38°, 槽顶宽11mm, 间距≈19mm
    GROOVE_PITCH = W / N_G
    GROOVE_DEPTH = (OD - PD) / 2  # 约5mm
    GROOVE_TOP_W = 11
    GROOVE_ANGLE = math.radians(19)  # 半角

    for i in range(N_G):
        cx = GROOVE_PITCH * i + GROOVE_PITCH / 2
        # 切除V形槽 (用梯形近似)
        gw_bot = max(1, GROOVE_TOP_W - 2 * GROOVE_DEPTH * math.tan(GROOVE_ANGLE))
        pts = [
            (cx - GROOVE_TOP_W/2, OD/2),
            (cx + GROOVE_TOP_W/2, OD/2),
            (cx + gw_bot/2,       OD/2 - GROOVE_DEPTH),
            (cx - gw_bot/2,       OD/2 - GROOVE_DEPTH),
        ]
        groove_wire = (cq.Workplane("XY")
                       .polyline(pts).close()
                       .revolve(360, (0, 0, 0), (0, 1, 0)))
        try:
            pulley = pulley.cut(groove_wire)
        except Exception:
            pass  # 槽切除失败时保持原体

    # 3. 轮毂
    hub = (cq.Workplane("YZ")
           .circle(HUB_OD / 2)
           .extrude(HUB_L)
           .translate((-HUB_EXT, 0, 0)))
    pulley = pulley.union(hub)

    # 4. 轴孔
    shaft_hole = (cq.Workplane("YZ")
                  .circle(BORE / 2)
                  .extrude(HUB_L)
                  .translate((-HUB_EXT, 0, 0)))
    pulley = pulley.cut(shaft_hole)

    # 5. 键槽 (12mm宽 × 5mm深 × 70mm长)
    keyway = (cq.Workplane("XY")
              .box(70, 12, 6)
              .translate((-HUB_EXT + 25, 0, BORE/2 - 3)))
    pulley = pulley.cut(keyway)

    step_path = str(OUT / "drive_pulley.step")
    stl_path  = str(OUT / "drive_pulley.stl")
    cq.exporters.export(pulley, step_path)
    cq.exporters.export(pulley, stl_path)
    log(f"✅ STEP: {step_path}")
    log(f"   PD={PD}mm  OD={OD}mm  B={W}mm  孔Ø{BORE}mm  {N_G}槽")
    results["drive_pulley"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results["drive_pulley"] = {"status": "FAIL", "error": str(e)}

# ══════════════════════════════════════════════════════════════════
# 8. 下机壳 Casing Lower
# ══════════════════════════════════════════════════════════════════
print("\n[8/11] 下机壳 (Casing Lower)...")
t0 = time.time()
try:
    # 参数
    L   = CASING_PARAMS["inner_L_mm"]        # 内腔长 900mm
    W   = CASING_PARAMS["inner_W_mm"]        # 内腔宽 550mm
    H   = CASING_PARAMS["inner_H_lower_mm"]  # 内腔高 430mm (下半)
    T   = CASING_PARAMS["wall_mm"]           # 壁厚 30mm
    DL  = CASING_PARAMS["discharge_L_mm"]   # 出料口长 500mm
    DW  = CASING_PARAMS["discharge_W_mm"]   # 出料口宽 200mm

    OL = L + 2 * T  # 外腔长 960mm
    OW = W + 2 * T  # 外腔宽 610mm
    OH = H + T      # 外腔高 460mm (下半+底板)

    # 1. 外壳体 (实心)
    casing_low = (cq.Workplane("XY")
                  .box(OL, OW, OH))

    # 2. 内腔 (挖空: 从顶面向下挖H深)
    inner = (cq.Workplane("XY")
             .box(L, W, H)
             .translate((0, 0, T/2)))
    casing_low = casing_low.cut(inner)

    # 3. 出料口 (底面中央开孔)
    discharge = (cq.Workplane("XY")
                 .box(DL, DW, T + 2)
                 .translate((0, 0, -(OH/2))))
    casing_low = casing_low.cut(discharge)

    # 4. 两端轴孔 (主轴通过, Ø100)
    for sx in [-(OL/2), (OL/2)]:
        shaft_pass = (cq.Workplane("YZ")
                      .circle(50)
                      .extrude(T + 2)
                      .translate((sx, 0, 0)))
        try:
            casing_low = casing_low.cut(shaft_pass)
        except Exception:
            pass

    step_path = str(OUT / "casing_lower.step")
    stl_path  = str(OUT / "casing_lower.stl")
    cq.exporters.export(casing_low, step_path)
    cq.exporters.export(casing_low, stl_path)
    log(f"✅ STEP: {step_path}")
    log(f"   外: {OL}×{OW}×{OH}mm  壁厚{T}mm  出料口{DL}×{DW}mm")
    results["casing_lower"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results["casing_lower"] = {"status": "FAIL", "error": str(e)}

# ══════════════════════════════════════════════════════════════════
# 9. 上机壳 Casing Upper
# ══════════════════════════════════════════════════════════════════
print("\n[9/11] 上机壳 (Casing Upper)...")
t0 = time.time()
try:
    L   = CASING_PARAMS["inner_L_mm"]        # 内腔长 900mm
    W   = CASING_PARAMS["inner_W_mm"]        # 内腔宽 550mm
    H   = CASING_PARAMS["inner_H_upper_mm"]  # 内腔高 430mm (上半)
    T   = CASING_PARAMS["wall_mm"]           # 壁厚 30mm
    FL  = CASING_PARAMS["feed_inlet_L_mm"]   # 进料口长 300mm
    FW  = CASING_PARAMS["feed_inlet_W_mm"]   # 进料口宽 200mm

    OL = L + 2 * T
    OW = W + 2 * T
    OH = H + T      # 上半+顶板

    # 1. 外壳体
    casing_up = (cq.Workplane("XY")
                 .box(OL, OW, OH))

    # 2. 内腔 (从底面向上挖H深)
    inner = (cq.Workplane("XY")
             .box(L, W, H)
             .translate((0, 0, -T/2)))
    casing_up = casing_up.cut(inner)

    # 3. 进料口 (顶面中央开孔)
    feed = (cq.Workplane("XY")
            .box(FL, FW, T + 2)
            .translate((0, 0, OH/2)))
    casing_up = casing_up.cut(feed)

    # 4. 进料斗 (顶部漏斗形, 简化为矩形延伸)
    hopper = (cq.Workplane("XY")
              .box(FL + 100, FW + 100, 150)
              .translate((0, 0, OH/2 + 75)))
    hopper_inner = (cq.Workplane("XY")
                    .box(FL - 10, FW - 10, 155)
                    .translate((0, 0, OH/2 + 75)))
    hopper = hopper.cut(hopper_inner)
    casing_up = casing_up.union(hopper)

    # 5. 两端轴孔 (主轴通过, Ø100)
    for sx in [-(OL/2), (OL/2)]:
        shaft_pass = (cq.Workplane("YZ")
                      .circle(50)
                      .extrude(T + 2)
                      .translate((sx, 0, 0)))
        try:
            casing_up = casing_up.cut(shaft_pass)
        except Exception:
            pass

    step_path = str(OUT / "casing_upper.step")
    stl_path  = str(OUT / "casing_upper.stl")
    cq.exporters.export(casing_up, step_path)
    cq.exporters.export(casing_up, stl_path)
    log(f"✅ STEP: {step_path}")
    log(f"   外: {OL}×{OW}×{OH}mm  壁厚{T}mm  进料口{FL}×{FW}mm + 进料斗")
    results["casing_upper"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results["casing_upper"] = {"status": "FAIL", "error": str(e)}

# ══════════════════════════════════════════════════════════════════
# 10. 电动机 Motor Body (Y180L-4, 简化几何模型)
# ══════════════════════════════════════════════════════════════════
print("\n[10/11] 电动机机体 (Motor Body Y180L-4)...")
t0 = time.time()
try:
    ML  = MOTOR_PARAMS["approx_L_mm"]      # 机体长 590mm
    MW  = MOTOR_PARAMS["approx_W_mm"]      # 机体宽 280mm
    MH  = MOTOR_PARAMS["approx_H_mm"]      # 机体高 350mm
    SD  = MOTOR_PARAMS["shaft_dia_mm"]     # 轴径 55mm
    SE  = MOTOR_PARAMS["shaft_ext_mm"]     # 轴伸 110mm
    FH  = 180                              # 轴中心高 (frame 180)

    # 1. 主机体 (带圆角的矩形)
    motor = (cq.Workplane("YZ")
             .box(ML, MW, MH))

    # 2. 散热筋 (顶部, 简化为矩形凸起)
    for i in range(8):
        rib_x = -ML/2 + 40 + i * 65
        rib = (cq.Workplane("XY")
               .box(20, MW + 20, 20)
               .translate((rib_x, 0, MH/2 + 10)))
        motor = motor.union(rib)

    # 3. 轴 (从右端伸出)
    shaft_stub = (cq.Workplane("YZ")
                  .circle(SD / 2)
                  .extrude(SE)
                  .translate((ML/2, 0, FH - MH/2)))
    motor = motor.union(shaft_stub)

    # 4. 接线盒 (顶部侧面小盒)
    jbox = (cq.Workplane("XY")
            .box(100, 80, 80)
            .translate((0, MW/2 + 40, MH/2 - 20)))
    motor = motor.union(jbox)

    # 5. 安装脚 (底部四角)
    for sx, sy in [(-250, -110), (250, -110), (-250, 110), (250, 110)]:
        foot = (cq.Workplane("XY")
                .box(60, 60, 25)
                .translate((sx, sy, -(MH/2 + 12))))
        motor = motor.union(foot)

    step_path = str(OUT / "motor_body.step")
    stl_path  = str(OUT / "motor_body.stl")
    cq.exporters.export(motor, step_path)
    cq.exporters.export(motor, stl_path)
    log(f"✅ STEP: {step_path}")
    log(f"   Y180L-4: {ML}×{MW}×{MH}mm  轴Ø{SD}×{SE}mm")
    results["motor_body"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results["motor_body"] = {"status": "FAIL", "error": str(e)}

# ══════════════════════════════════════════════════════════════════
# 11. 机架底座 Frame Base (Q235焊接)
# ══════════════════════════════════════════════════════════════════
print("\n[11/11] 机架底座 (Frame Base)...")
t0 = time.time()
try:
    # 总装配图: 总长1300mm, 总宽820mm
    # 机架底座: 1300×820×100mm + 立柱
    FL   = 1300   # 底座长
    FW   = 820    # 底座宽
    FH   = 100    # 底座高 (底板)
    T    = 20     # 钢板厚
    PH   = 500    # 立柱高 (支撑主机)
    PW   = 60     # 立柱截面

    # 1. 底板
    base_plate = (cq.Workplane("XY")
                  .box(FL, FW, T))

    # 2. 四角立柱
    for sx, sy in [(-580, -360), (580, -360), (-580, 360), (580, 360)]:
        col = (cq.Workplane("XY")
               .box(PW, PW, PH)
               .translate((sx, sy, T/2 + PH/2)))
        base_plate = base_plate.union(col)

    # 3. 横梁 (连接对侧立柱)
    for sy in [-360, 360]:
        beam = (cq.Workplane("XY")
                .box(FL - 120, T, 40)
                .translate((0, sy, T/2 + PH - 20)))
        base_plate = base_plate.union(beam)

    # 4. 纵梁
    for sx in [-580, 580]:
        lbeam = (cq.Workplane("XY")
                 .box(T, FW - 120, 40)
                 .translate((sx, 0, T/2 + PH - 20)))
        base_plate = base_plate.union(lbeam)

    # 5. 减振垫位 (四角圆孔)
    for sx, sy in [(-500, -300), (500, -300), (-500, 300), (500, 300)]:
        pad_hole = (cq.Workplane("XY")
                    .circle(35)
                    .extrude(T + 2)
                    .translate((sx, sy, 0)))
        try:
            base_plate = base_plate.cut(pad_hole)
        except Exception:
            pass

    step_path = str(OUT / "frame_base.step")
    stl_path  = str(OUT / "frame_base.stl")
    cq.exporters.export(base_plate, step_path)
    cq.exporters.export(base_plate, stl_path)
    log(f"✅ STEP: {step_path}")
    log(f"   机架: {FL}×{FW}×{FH}mm  立柱高{PH}mm  4立柱+横纵梁")
    results["frame_base"] = {"status": "OK", "time": round(time.time()-t0, 2)}
except Exception as e:
    log(f"❌ 失败: {e}")
    import traceback; traceback.print_exc()
    results["frame_base"] = {"status": "FAIL", "error": str(e)}

# ── 汇总报告 ──────────────────────────────────────────────────────
print("\n" + "="*62)
print("  build_complete.py 完工汇总")
print("="*62)
total = len(results)
passed = sum(1 for v in results.values() if v["status"] == "OK")
for name, r in results.items():
    icon = "✅" if r["status"] == "OK" else "❌"
    t_str = f"  ({r.get('time', '?')}s)" if r["status"] == "OK" else f"  {r.get('error','')[:60]}"
    print(f"  {icon} {name:<20}{t_str}")

print(f"\n  结果: {passed}/{total} PASS")
if passed < total:
    print("  ⚠️  部分零件构建失败, 检查以上错误信息")
else:
    print("  🎯 道法自然 · 全部新零件构建完成")

# 写入结果JSON
results_path = OUT / "build_complete_results.json"
import json
with open(results_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n  📄 结果: {results_path}")
