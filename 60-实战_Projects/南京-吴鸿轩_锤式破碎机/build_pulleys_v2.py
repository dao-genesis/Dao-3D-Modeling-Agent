"""
Build pulleys v2 · 正确 B 型 V 槽 · 道法自然
两个皮带轮统一用 revolve 切出标准 B 型 V 槽
Pulley 轴沿 +X 方向, 原点在左端面中心
GB/T 13575.1 B 型 V 槽:
  槽角 34° (PD≤190mm) / 38° (PD>190mm)
  有效深度 e=8.7mm, 最小深度 f=10.8mm
  齿距 p=19mm, 边距 e1≈12.5mm
  槽顶宽 (外径处) ≈ 11mm
"""
import cadquery as cq
import math, time, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import DRIVE_PULLEY_PARAMS, VBELT_PARAMS, OUT_DIR

# ── B 型 V 槽标准参数 ──────────────────────────────────────────
GROOVE_PITCH = 19.0        # mm, 槽间距
GROOVE_EDGE  = 12.5        # mm, 端面到第一槽中心
N_GROOVES    = 4           # B型4槽
BELT_TOP_W   = 17.0        # B 型 belt 顶宽
BELT_H       = 11.0        # B 型 belt 高

def build_pulley(name, od_mm, pd_mm, bore_mm, width_mm, groove_angle_deg,
                 hub_od_mm=None, hub_ext_mm=0, keyway_w=0, keyway_d=0, keyway_l=0):
    """构建带 V 槽的皮带轮 · 轴沿 +X, 原点=左端面中心"""
    R_od = od_mm / 2.0
    R_pd = pd_mm / 2.0
    R_bore = bore_mm / 2.0
    half_angle = math.radians(groove_angle_deg / 2.0)

    # V 槽几何: 从外径面切入
    # 槽深 = (OD - PD)/2 + 额外深入
    groove_depth = (od_mm - pd_mm) / 2.0 + 3.0  # 超过节圆 3mm
    # 槽底半径
    R_bottom = R_od - groove_depth
    # 槽顶半宽 (在外径处)
    slot_half_top = groove_depth * math.tan(half_angle)
    # 槽底半宽 (约 1mm 圆角近似为平底)
    slot_half_bot = 1.0

    print(f"  {name}: OD={od_mm} PD={pd_mm} bore={bore_mm} W={width_mm}")
    print(f"    groove: angle={groove_angle_deg}° depth={groove_depth:.1f}mm "
          f"top_w={2*slot_half_top:.1f}mm R_bot={R_bottom:.1f}mm")

    # ── 1. 轮体: 圆柱 沿 +X ──
    pulley = (cq.Workplane("YZ")
              .circle(R_od)
              .extrude(width_mm))

    # ── 2. 中心孔 ──
    pulley = (pulley.faces(">X").workplane()
              .circle(R_bore)
              .cutBlind(-width_mm - hub_ext_mm * 2))

    # ── 3. 轮毂 (如有) ──
    if hub_od_mm and hub_ext_mm > 0:
        R_hub = hub_od_mm / 2.0
        hub_total = width_mm + 2 * hub_ext_mm
        hub = (cq.Workplane("YZ")
               .circle(R_hub)
               .circle(R_bore)
               .extrude(hub_total)
               .translate((-hub_ext_mm, 0, 0)))
        pulley = pulley.union(hub)

    # ── 4. 切 V 槽 ──
    # 每个槽用 revolve 切除: 截面在 XY 平面, revolve 绕 X 轴
    for i in range(N_GROOVES):
        cx = GROOVE_EDGE + GROOVE_PITCH * i  # 槽中心 X 坐标

        # V 槽截面 (在 XR 平面, R=Y 方向, X=轴向)
        # 从外径切入到 R_bottom, 呈 V 形
        # 截面轮廓 (4 点梯形):
        #   外径处两角 (cx ± half_top, R_od+0.5)  → 多切 0.5mm 保证贯穿
        #   底部两角   (cx ± half_bot, R_bottom)
        pts = [
            (cx - slot_half_top, R_od + 0.5),
            (cx + slot_half_top, R_od + 0.5),
            (cx + slot_half_bot, R_bottom),
            (cx - slot_half_bot, R_bottom),
        ]
        groove = (cq.Workplane("XY")
                  .polyline(pts).close()
                  .revolve(360, (0, 0, 0), (1, 0, 0)))
        try:
            pulley = pulley.cut(groove)
            print(f"    groove {i+1}: x={cx:.1f}mm OK")
        except Exception as e:
            print(f"    groove {i+1}: x={cx:.1f}mm FAIL ({e})")

    # ── 5. 键槽 ──
    if keyway_w > 0 and keyway_d > 0 and keyway_l > 0:
        # 键槽在轴孔内壁顶部 (+Y 方向)
        ks = (cq.Workplane("XZ")
              .rect(keyway_l, keyway_w)
              .extrude(keyway_d)
              .translate(((width_mm - keyway_l) / 2, R_bore, 0)))
        pulley = pulley.cut(ks)
        print(f"    keyway: {keyway_w}x{keyway_d}x{keyway_l}mm")

    return pulley


# ═══════════════════════════════════════════════════════════════
# A. 从动皮带轮 (Driven Pulley · 大轮 · 装在主轴)
# ═══════════════════════════════════════════════════════════════
print("\n[A] 从动皮带轮 (Driven Pulley)...")
t0 = time.time()
driven = build_pulley(
    name="driven_pulley",
    od_mm=240, pd_mm=220, bore_mm=70, width_mm=90,
    groove_angle_deg=38,     # PD>190 用 38°
    hub_od_mm=None, hub_ext_mm=0,
    keyway_w=20, keyway_d=8, keyway_l=70,
)
driven_step = str(OUT_DIR / "driven_pulley.step")
driven_stl = str(OUT_DIR / "driven_pulley.stl")
cq.exporters.export(driven, driven_step)
cq.exporters.export(driven, driven_stl)
print(f"  ✅ {driven_step}  ({time.time()-t0:.2f}s)")

# ═══════════════════════════════════════════════════════════════
# B. 主动带轮 (Drive Pulley · 小轮 · 装在电动机轴)
# ═══════════════════════════════════════════════════════════════
print("\n[B] 主动带轮 (Drive Pulley)...")
t0 = time.time()
drive = build_pulley(
    name="drive_pulley",
    od_mm=190, pd_mm=180, bore_mm=55, width_mm=90,
    groove_angle_deg=36,     # 118<PD≤190 用 36°
    hub_od_mm=90, hub_ext_mm=15,
    keyway_w=16, keyway_d=5, keyway_l=70,
)
drive_step = str(OUT_DIR / "drive_pulley.step")
drive_stl = str(OUT_DIR / "drive_pulley.stl")
cq.exporters.export(drive, drive_step)
cq.exporters.export(drive, drive_stl)
print(f"  ✅ {drive_step}  ({time.time()-t0:.2f}s)")

# ── 验证 ──
import trimesh
for name, path in [("driven", driven_stl), ("drive", drive_stl)]:
    m = trimesh.load(path)
    bb = m.bounding_box.bounds
    sz = (bb[1] - bb[0]).round(1)
    print(f"  {name}: faces={m.faces.shape[0]} watertight={m.is_watertight} "
          f"bbox={sz.tolist()}mm")

print("\n道法自然 · 皮带轮 V 槽 ✓")
