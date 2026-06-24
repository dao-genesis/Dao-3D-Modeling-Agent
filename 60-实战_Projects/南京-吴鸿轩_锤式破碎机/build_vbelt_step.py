#!/usr/bin/env python3
"""V带双轮传动 · CadQuery 实体版 → STEP
用 revolve + box 分段联合构建 V 带双轮传动实体 · 输出 STEP + STL
相比 build_vbelt_transmission.py (纯 STL 三角面),
本脚本输出真正的实体 STEP, SW 可直接另存为 SLDPRT.
"""
import cadquery as cq
import math, json, sys, time
from pathlib import Path

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
from config import OUT_DIR, VBELT_PARAMS, ASSEMBLY_POSITIONS, DRIVE_PULLEY_PARAMS

OUT_DIR.mkdir(exist_ok=True)

# ═ 几何参数 ═
R1 = DRIVE_PULLEY_PARAMS["pd_mm"] / 2.0   # 90
R2 = VBELT_PARAMS["driven_pd_mm"] / 2.0    # 110
DRIVE_CX = ASSEMBLY_POSITIONS["drive_pulley"]["tx"] + DRIVE_PULLEY_PARAMS["width_mm"] / 2.0  # -45
DRIVE_CZ = ASSEMBLY_POSITIONS["drive_pulley"]["tz"]   # -600
DRIVEN_CX = ASSEMBLY_POSITIONS["driven_pulley"]["tx"] + 45.0   # +45
DRIVEN_CZ = ASSEMBLY_POSITIONS["driven_pulley"]["tz"]   # 0

dx, dz = DRIVEN_CX - DRIVE_CX, DRIVEN_CZ - DRIVE_CZ
C = math.sqrt(dx*dx + dz*dz)
psi = math.asin((R2 - R1) / C)
wrap1_deg = math.degrees(math.pi - 2*psi)    # 主动轮包角 (小弧)
wrap2_deg = math.degrees(math.pi + 2*psi)    # 从动轮包角 (大弧)

# 法向角 (XZ 平面, 从 +X 顺 +Z 为正)
beta = math.atan2(dz, dx)  # 连心线方向角
# u·n = -(R2-R1)/C, n 有两解
phi_off = math.acos(-(R2 - R1) / C)
ang_up = math.degrees(beta + phi_off)   # T_up 法向角
ang_dn = math.degrees(beta - phi_off)   # T_dn 法向角 (<0)

# 确保 ang_up 指上 (sin>0), ang_dn 指下
if math.sin(math.radians(ang_up)) < math.sin(math.radians(ang_dn)):
    ang_up, ang_dn = ang_dn, ang_up

# 切点
n_up = (math.cos(math.radians(ang_up)), math.sin(math.radians(ang_up)))
n_dn = (math.cos(math.radians(ang_dn)), math.sin(math.radians(ang_dn)))
T1_up = (DRIVE_CX + R1*n_up[0], 0.0, DRIVE_CZ + R1*n_up[1])
T2_up = (DRIVEN_CX + R2*n_up[0], 0.0, DRIVEN_CZ + R2*n_up[1])
T1_dn = (DRIVE_CX + R1*n_dn[0], 0.0, DRIVE_CZ + R1*n_dn[1])
T2_dn = (DRIVEN_CX + R2*n_dn[0], 0.0, DRIVEN_CZ + R2*n_dn[1])

# B 型截面
TOP_W, BOT_W, HEIGHT = 17.0, 11.0, 11.0

# 4 根带 Y 偏置
N_BELTS = int(VBELT_PARAMS["qty"])
GROOVE_P = 19.0
Y_OFFSETS = [GROOVE_P*(i - (N_BELTS-1)/2.0) for i in range(N_BELTS)]

print(f"V带双轮传动 (STEP 实体)")
print(f"  P1=({DRIVE_CX}, {DRIVE_CZ}) R1={R1}  P2=({DRIVEN_CX}, {DRIVEN_CZ}) R2={R2}  C={C:.2f}mm")
print(f"  包角: 小={wrap1_deg:.2f}° 大={wrap2_deg:.2f}°")
print(f"  切点法向角: T_up={ang_up:.2f}° T_dn={ang_dn:.2f}°")
print(f"  切点 T1_up={T1_up}\n        T2_up={T2_up}\n        T1_dn={T1_dn}\n        T2_dn={T2_dn}")


def make_pulley_arc(pulley_R, wrap_deg, rot_deg, center_xz, y_off):
    """绕轮心 (中心在 Y 轴上) 建 V 带包弧 · CCW revolve
    profile 置 +X 方向 (法向角 0°), 内径=R-HEIGHT, 外径=R
    revolve wrap_deg (CCW 从 +X 向 +Z)
    然后 rotate 绕 Y 轴 rot_deg 使起点对齐目标法向
    translate 到世界 center_xz = (cx, cz)
    """
    # 截面位于 XY 平面, Y 作"带轴向偏置", 径向沿 X
    prof = (cq.Workplane("XY")
            .moveTo(pulley_R,         +TOP_W/2 + y_off)
            .lineTo(pulley_R,         -TOP_W/2 + y_off)
            .lineTo(pulley_R - HEIGHT, -BOT_W/2 + y_off)
            .lineTo(pulley_R - HEIGHT, +BOT_W/2 + y_off)
            .close())
    # CadQuery revolve 绕 axis=(0,1,0) 实际为 CW (OCC 方向); 用 (0,-1,0) 获标准 CCW
    arc = prof.revolve(wrap_deg, (0, 0, 0), (0, -1, 0))
    arc = arc.rotate((0, 0, 0), (0, -1, 0), rot_deg)
    arc = arc.translate((center_xz[0], 0, center_xz[1]))
    return arc


def make_tangent_line(p_start, p_end, y_off, ang_deg):
    """切线段: 以 p_start→p_end 为切向 · 截面 V 梯形 (外宽 TOP_W 外侧径向, 内宽 BOT_W)
    局部: +X=切向, +Y=轴向, -Z=内法向方向 (即径向内)
    profile 在 YZ 平面 (截面), extrude 沿 +X 方向 length
    rotate 绕 Y 轴 ang_deg (切线方向角度) → +X → 切向, -Z → 径向内
    translate 到 p_start
    """
    length = math.sqrt((p_end[0]-p_start[0])**2 + (p_end[2]-p_start[2])**2)
    # 截面: Y 为轴向宽度, Z 为径向深度 (负 Z = 向内)
    prof = (cq.Workplane("YZ")
            .moveTo(+TOP_W/2 + y_off, 0)
            .lineTo(-TOP_W/2 + y_off, 0)
            .lineTo(-BOT_W/2 + y_off, -HEIGHT)
            .lineTo(+BOT_W/2 + y_off, -HEIGHT)
            .close())
    line = prof.extrude(length)
    line = line.rotate((0, 0, 0), (0, -1, 0), ang_deg)
    line = line.translate(p_start)
    return line


def make_one_belt(y_off):
    """单根 V 带 · 4 段并集 (两轮弧 + 两切线)"""
    # ── 段 A: 主动轮弧 (CCW 从 ang_up 到 ang_up - wrap1_deg = ang_up + (360-wrap1_deg)%360)
    # 我们希望 revolve 起点法向 = ang_up (T1_up), 终点 = ang_dn (T1_dn), CCW 走 wrap1 (177°小弧)
    # profile 初始在 +X (法向 0°), revolve(wrap1) → [0°, wrap1] 横跨
    # rotate ang_up → [ang_up, ang_up + wrap1] 横跨
    # 验证: ang_up + wrap1 = 173 + 177 = 350 ≡ -10 = ang_dn ✓ (小弧, 经过 P1 底+左, 外侧)
    arc_drive = make_pulley_arc(R1, wrap1_deg, ang_up, (DRIVE_CX, DRIVE_CZ), y_off)

    # ── 段 C: 从动轮弧 (CCW 从 ang_dn 到 ang_up, 走 wrap2=183° 大弧, 经外侧)
    # profile 初始 +X (法向 0°), revolve(wrap2) → [0°, wrap2]
    # rotate ang_dn → [ang_dn, ang_dn + wrap2] = [-10, -10+183] = [-10, 173] ✓
    arc_driven = make_pulley_arc(R2, wrap2_deg, ang_dn, (DRIVEN_CX, DRIVEN_CZ), y_off)

    # ── 段 B: 上切线 T1_up → T2_up
    # 切向角 (XZ 内 atan2(z_diff, x_diff))
    up_tan_ang = math.degrees(math.atan2(T2_up[2]-T1_up[2], T2_up[0]-T1_up[0]))
    # 上切线外法向 = (n_up[0], n_up[1]) 朝 +Z 方向
    # 局部 -Z (径向内) 经绕 Y 旋转 up_tan_ang 后, 方向 = (sin(up_tan_ang), 0, -cos(up_tan_ang))
    # 这需等于内法向 = -n_up = (-n_up[0], 0, -n_up[1])
    # 即 sin(up_tan_ang) = -n_up[0], -cos(up_tan_ang) = -n_up[1], 即 cos(up_tan_ang) = n_up[1]
    # up_tan_ang = atan2(-n_up[0], n_up[1])  - 与 atan2(T2_up - T1_up 方向) 等价
    line_up = make_tangent_line(T1_up, T2_up, y_off, up_tan_ang)

    # ── 段 D: 下切线 T2_dn → T1_dn
    dn_tan_ang = math.degrees(math.atan2(T1_dn[2]-T2_dn[2], T1_dn[0]-T2_dn[0]))
    line_dn = make_tangent_line(T2_dn, T1_dn, y_off, dn_tan_ang)

    belt = arc_drive.union(arc_driven).union(line_up).union(line_dn)
    return belt


t0 = time.time()
all_belts = None
for i, y_off in enumerate(Y_OFFSETS):
    tb = time.time()
    b = make_one_belt(y_off)
    if all_belts is None:
        all_belts = b
    else:
        all_belts = all_belts.union(b)
    print(f"  带{i+1} y={y_off:+.1f}mm  {time.time()-tb:.2f}s")

dt = time.time() - t0
stl_path = str(OUT_DIR / "v_belt.stl")
step_path = str(OUT_DIR / "v_belt.step")

# ─── 关键旋转: XZ 平面 → YZ 平面 ─────────────────────────────────────
# CadQuery 构建 belt 绕 Y 轴 (arcs 在 XZ 平面), 但装配中 pulley 轴沿 X
# 需旋转 90° 绕 Z 轴 (过两轮公共 X 中心) 使 belt arcs 转到 YZ 平面
# 旋转后: belt 正确包裹 pulley 的 YZ 截面圆, width 方向沿 X (pulley 轴向)
all_belts = all_belts.rotate((-45, 0, 0), (-45, 0, 1), 90)
print(f"  Rz(90°) 旋转完成: XZ → YZ 平面")

# ─── 把多个 solids 合并为 Compound 作为单一 Part Shape ──────────
# CQ Workplane 含多个 disjoint solid 时, export STEP 生成 assembly 结构
# 用 cq.Compound.makeCompound 将所有 solids 装进一个 Compound, SW 识别为 Part
_all_solids = all_belts.solids().vals()
_compound = cq.Compound.makeCompound(_all_solids)
print(f"  合并 {len(_all_solids)} solids → 单一 Compound")
cq.exporters.export(_compound, stl_path)
cq.exporters.export(_compound, step_path)

print(f"\n✅ STL: {stl_path}")
print(f"✅ STEP: {step_path}")
print(f"  耗时: {dt:.2f}s")

# 验证
import trimesh
m = trimesh.load(stl_path)
bb = m.bounding_box.bounds
sz = (bb[1] - bb[0]).round(1).tolist()
print(f"  面数={int(m.faces.shape[0])}  流形={m.is_watertight}  bbox={sz}mm")
print(f"  世界范围: X[{bb[0][0]:.1f}, {bb[1][0]:.1f}]  "
      f"Y[{bb[0][1]:.1f}, {bb[1][1]:.1f}]  Z[{bb[0][2]:.1f}, {bb[1][2]:.1f}]")

# JSON
res = {
    "C_mm": C, "psi_deg": math.degrees(psi),
    "wrap1_deg": wrap1_deg, "wrap2_deg": wrap2_deg,
    "ang_up_deg": ang_up, "ang_dn_deg": ang_dn,
    "T1_up": list(T1_up), "T2_up": list(T2_up),
    "T1_dn": list(T1_dn), "T2_dn": list(T2_dn),
    "Y_OFFSETS": Y_OFFSETS,
    "bbox_mm": sz, "faces": int(m.faces.shape[0]),
    "watertight": bool(m.is_watertight),
    "status": "OK_SOLID_STEP",
}
(OUT_DIR / "v_belt_results.json").write_text(
    json.dumps(res, indent=2), encoding="utf-8")
print("\n道法自然 · V带实体双轮传动 ✓")
