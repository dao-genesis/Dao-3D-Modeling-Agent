"""
锤式破碎机参数化建模项目 — 统一路径配置 v4 (完整版 · 万法归宗)
所有脚本共享此配置，修改路径只需改这一个文件
道法自然 · 万法归宗 · 彻底提取论文所有核心资源
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

DXF_DIR   = BASE_DIR / "dxf"
OUT_DIR   = BASE_DIR / "output_cq"
SLDPRT_DIR = BASE_DIR / "sldprt"

OUT_DIR.mkdir(exist_ok=True)

DXF_FILES = {
    "assembly":     DXF_DIR / "assembly_A3.dxf",
    "shaft":        DXF_DIR / "shaft_A3.dxf",
    "rotor_disc":   DXF_DIR / "rotor_disc_A3.dxf",
    "hammer":       DXF_DIR / "hammer_A3.dxf",
    "hammer_pin":   DXF_DIR / "hammer_pin_A3.dxf",
    "driven_pulley":DXF_DIR / "driven_pulley_A3.dxf",
    "screen_plate": DXF_DIR / "screen_plate_A3.dxf",
}

# 旋转部件6个 + 整机结构5个 = 共11个CadQuery零件 (+ 1个纯Python V带)
PARTS = ["main_shaft", "rotor_disc", "hammer", "hammer_pin", "driven_pulley", "screen_plate"]
PARTS_NEW = ["drive_pulley", "casing_lower", "casing_upper", "motor_body", "frame_base"]
PARTS_ALL = PARTS + PARTS_NEW  # 11个CadQuery零件

# ── 整机总体参数 ─────────────────────────────────────────────
MACHINE_PARAMS = {
    "overall_l_mm":    1300,
    "overall_w_mm":     820,
    "overall_h_mm":     860,
    "top_view_l_mm":   1300,
    "top_view_w_mm":    550,
    "rotor_diam_mm":    700,
    "rotor_length_mm":  800,
    "shaft_total_l_mm": 1145,
    "screen_arc_deg":   120,
    "rotor_speed_rpm":  1200,
    "hammer_tip_speed_ms": 43.98,
    "output_granularity_mm": "10~20",
}

# ── 主轴参数 ─────────────────────────────────────────────────
SHAFT_PARAMS = {
    "material": "45钢",
    "total_L_mm": 1145,
    "segments": [
        {"name": "右端螺纹段", "dia_mm": 60, "len_mm": 30},
        {"name": "右端轴承段", "dia_mm": 80, "len_mm": 70},
        {"name": "右端过渡台肩","dia_mm": 90, "len_mm": 20},
        {"name": "主体工作段", "dia_mm": 90, "len_mm": 925},
        {"name": "左端轴承段", "dia_mm": 80, "len_mm": 70},
        {"name": "左端螺纹段", "dia_mm": 60, "len_mm": 30},
    ],
    "keyway_w_mm": 20, "keyway_L_mm": 70, "keyway_depth_mm": 8,
    "allowable_bending_stress_MPa": 70,
}

# ── 电动机参数 ────────────────────────────────────────────────
MOTOR_PARAMS = {
    "model": "Y180L-4",
    "type": "Y系列三相异步电动机",
    "power_kW": 22,
    "rated_speed_rpm": 1470,
    "poles": 4,
    "sync_speed_rpm": 1500,
    "frame": "180L",
    "shaft_dia_mm": 55,
    "shaft_ext_mm": 110,
    "approx_L_mm": 590,
    "approx_W_mm": 280,
    "approx_H_mm": 350,
}

# ── 主动带轮参数 (小带轮, 装在电动机轴上) ─────────────────────
DRIVE_PULLEY_PARAMS = {
    "location": "电动机轴",
    "pd_mm": 180,
    "od_mm": 190,
    "groove_type": "B",
    "grooves": 4,
    "hub_bore_mm": 55,
    "width_mm": 90,
}

# ── V带传动参数 ───────────────────────────────────────────────
VBELT_PARAMS = {
    "type": "B型普通V带",
    "qty": 4,
    "center_dist_mm": 600,
    "ratio": 1.222,
    "belt_speed_ms": 13.85,
    "drive_pd_mm": 180,
    "driven_pd_mm": 220,
    "actual_rotor_rpm_no_slip": 1203,
    "actual_rotor_rpm_2pct_slip": 1179,
}

# ── 机壳参数 ──────────────────────────────────────────────────
# 反者道之动 · 从锤头摆动半径(400mm)反推内腔半宽需≥410mm
# 原 inner_W_mm=550(半宽275) 导致锤头穿墙125mm → 扩至820(半宽410)
CASING_PARAMS = {
    "material": "Q235钢板",
    "wall_mm": 30,
    "inner_L_mm": 900,
    "inner_W_mm": 820,      # 修正: 550→820 · 容纳锤头摆动(半径400+余量10)
    "inner_H_upper_mm": 430,
    "inner_H_lower_mm": 430,
    "feed_inlet_L_mm": 300,
    "feed_inlet_W_mm": 200,
    "discharge_L_mm": 500,
    "discharge_W_mm": 200,
}

# ── 原始6零件BOM (旋转部件, 用于零件验证) ────────────────────────
BOM = [
    {"id": 1, "name": "主轴",      "en": "Main Shaft",     "mat": "45钢",       "qty": 1,  "dim": "Ø60-80-90 L=1145mm"},
    {"id": 2, "name": "转子盘",    "en": "Rotor Disc",     "mat": "Q345钢",     "qty": 4,  "dim": "Ø500×25, 4销孔PCD440"},
    {"id": 3, "name": "锤头",      "en": "Hammer",         "mat": "ZGMn13",     "qty": 16, "dim": "梯形180×80×40, Ø40孔"},
    {"id": 4, "name": "销轴",      "en": "Hammer Pin",     "mat": "45钢",       "qty": 4,  "dim": "Ø40×670 全跨4盘 M30×2两端"},
    {"id": 5, "name": "从动皮带轮","en": "Driven Pulley",  "mat": "HT200铸铁",  "qty": 1,  "dim": "B型4槽 Ø240 PD224 孔Ø70"},
    {"id": 6, "name": "筛板",      "en": "Screen Plate",   "mat": "不锈钢",     "qty": 1,  "dim": "弧120° Ri=390 t=12 B=800"},
]

# ── 整机结构件BOM (v3+v4新增5零件 + V带) ──────────────────────
BOM_STRUCTURE = [
    {"id":  7, "name": "主动带轮", "en": "Drive Pulley",   "mat": "HT200铸铁",  "qty": 1, "dim": "B型4槽 PD180 孔Ø55"},
    {"id":  8, "name": "下机壳",   "en": "Casing Lower",  "mat": "Q235焊接",   "qty": 1, "dim": "960×880×460mm 壁厚30mm (内宽820)"},
    {"id":  9, "name": "上机壳",   "en": "Casing Upper",  "mat": "Q235焊接",   "qty": 1, "dim": "960×880×610mm + 进料斗 (内宽820)"},
    {"id": 10, "name": "电动机",   "en": "Motor Y180L-4", "mat": "Y系列",      "qty": 1, "dim": "22kW 590×280×350mm"},
    {"id": 11, "name": "机架底座", "en": "Frame Base",    "mat": "Q235焊接",   "qty": 1, "dim": "1752×820×520mm + 4立柱 (延伸支撑电机)"},
    {"id": 12, "name": "V带",      "en": "V-Belt B-type", "mat": "B型橡胶",    "qty": 4, "dim": "B型×4根 C=600mm 传动比1.23"},
]

# ── 全12零件完整BOM (旋转部件6 + 整机结构6, 含V带) ─────────────
BOM_ALL = BOM + BOM_STRUCTURE

# ── 完整16项BOM (来自总装配图 图6-2) ──────────────────────────
BOM_COMPLETE = [
    {"id":  1, "name": "进料口",    "en": "Feed Inlet",          "mat": "Q235焊接件",  "qty": 1,     "dim": ""},
    {"id":  2, "name": "机壳",      "en": "Casing",              "mat": "Q235焊接件",  "qty": 1,     "dim": "上下分体式"},
    {"id":  3, "name": "转子",      "en": "Rotor Assembly",      "mat": "组件",        "qty": 1,     "dim": "Ø700×800"},
    {"id":  4, "name": "锤头",      "en": "Hammer",              "mat": "ZGMn13",      "qty": "n",   "dim": "梯形180×80×40"},
    {"id":  5, "name": "筛板",      "en": "Screen Plate",        "mat": "不锈钢",      "qty": 1,     "dim": "弧120° Ri=390 可更换"},
    {"id":  6, "name": "出料口",    "en": "Discharge Outlet",    "mat": "Q235焊接件",  "qty": 1,     "dim": ""},
    {"id":  7, "name": "从动带轮",  "en": "Driven Pulley",       "mat": "HT200铸铁",   "qty": 1,     "dim": "B型4槽 OD240 PD224"},
    {"id":  8, "name": "V带",       "en": "V-Belt",              "mat": "B型橡胶",     "qty": "2-3", "dim": "B型"},
    {"id":  9, "name": "主动带轮",  "en": "Drive Pulley",        "mat": "HT200铸铁",   "qty": 1,     "dim": "B型4槽 PD180"},
    {"id": 10, "name": "电动机",    "en": "Motor",               "mat": "Y系列",       "qty": 1,     "dim": "Y180L-4 22kW"},
    {"id": 11, "name": "安装板",    "en": "Motor Mounting Plate","mat": "Q235焊接件",  "qty": 1,     "dim": ""},
    {"id": 12, "name": "机架",      "en": "Frame",               "mat": "Q235焊接件",  "qty": 1,     "dim": ""},
    {"id": 13, "name": "减振垫",    "en": "Vibration Damper",    "mat": "橡胶",        "qty": 4,     "dim": ""},
    {"id": 14, "name": "锚轴",      "en": "Pin Shaft",           "mat": "45钢",        "qty": "n",   "dim": ""},
    {"id": 15, "name": "调整垫片",  "en": "Adjustment Shim",     "mat": "钢",          "qty": "n",   "dim": ""},
    {"id": 16, "name": "螺母",      "en": "Nut",                 "mat": "钢",          "qty": "n",   "dim": ""},
]

# ── 动平衡与维护策略 (ISO 1940-1 · GB/T 9239 · JB/T 9752) ──────
# 锤式破碎机动平衡等级与运维阈值 (万法归宗 v4 新增)
ISO_BALANCE = {
    "grade":             "G16",
    "grade_velocity_ms": 16.0,     # mm/s (ISO 1940-1 G16 适用锤式破碎机)
    "standard_ref":      "ISO 1940-1 / GB/T 9239.1 / JB/T 9752",
    "grade_alt_precise": "G6.3",   # 精密工业参考 (电机/泵/风机)
    "grade_alt_loose":   "G40",    # 宽松 (单缸发动机/曲轴)
}

# 运维策略 (对称成组换锤 · 独磨阈值 · 监测周期)
MAINTENANCE = {
    "wear_pct_reference":         30.0,   # 参考磨损百分比 (论文场景假设)
    "wear_solo_critical_pct":     0.70,   # 单锤独磨临界阈值% (超此需停机)
    "pair_wear_tolerance_pct":    2.3,    # 对称成组误差容限% (两对角锤磨损差)
    "replacement_policy":         "对称成组换锤 (按2或4的倍数)",
    "inspection_interval_h":      500,    # 推荐巡检间隔 (运行小时)
    "replacement_interval_h":     2000,   # 推荐全锤更换间隔 (典型工况)
    "residual_imbalance_field":   "field_balance_after_replace",  # 现场动平衡校验标识
    "balancing_planes":           4,      # 动平衡校正面数 (与转子盘数一致)
    "monitoring_vibration_rms":   4.5,    # mm/s RMS报警阈值 (ISO 10816-3 Class I)
    "notes": [
        "独磨超0.7%必须立即停机",
        "对称成组换锤可消除质量差引起的径向不平衡",
        "更换后必须进行现场动平衡校验 (添加配重片)",
        "振动RMS>4.5mm/s需排查轴承或不平衡问题",
    ],
}

# ── 零件规格验证 ──────────────────────────────────────────────
VOLUME_SPEC_MM3 = {
    "main_shaft":    {"min": 5_000_000,  "max": 9_000_000},
    "rotor_disc":    {"min": 3_000_000,  "max": 7_000_000},
    "hammer":        {"min":   100_000,  "max":   800_000},
    "hammer_pin":    {"min":    50_000,  "max":   900_000},  # 全跨670mm: π×20²×670≈842K
    "driven_pulley": {"min": 1_500_000,  "max": 5_500_000},
    "screen_plate":  {"min": 4_000_000,  "max": 12_000_000},
    "drive_pulley":  {"min":   500_000,  "max": 3_000_000},
    "casing_lower":  {"min": 5_000_000,  "max": 80_000_000},
    "casing_upper":  {"min": 5_000_000,  "max": 80_000_000},
    "motor_body":    {"min": 10_000_000, "max": 100_000_000},
    "frame_base":    {"min": 2_000_000,  "max": 50_000_000},
}

BBOX_SPEC_MM = {
    "main_shaft":    {"L_min": 1000, "L_max": 1200},
    "rotor_disc":    {"D_min":  480, "D_max":  520},
    "hammer":        {"H_min":  160, "H_max":  200},
    "hammer_pin":    {"L_min":  130, "L_max":  700},  # 全跨4盘670mm (DXF单段142mm)
    "driven_pulley": {"D_min":  220, "D_max":  250},
    "screen_plate":  {"B_min":  780, "B_max":  820},
    "drive_pulley":  {"D_min":  170, "D_max":  210},
    "casing_lower":  {"L_min":  800, "L_max": 1100},
    "casing_upper":  {"L_min":  800, "L_max": 1100},
    "motor_body":    {"L_min":  400, "L_max":  720},
    "frame_base":    {"L_min": 1000, "L_max": 1800},  # 延伸支撑电机: 1752.5mm
}

# ── 装配坐标系 ──────────────────────────────────────────────────────────
# 原点: 主轴左端中心线.  X=轴向(左→右), Y=水平横向, Z=竖直(向上为正)
# 坐标导出原则 (反者道之动 · 从bbox底层几何推演):
#   · main_shaft bbox: x[0,1145] y/z[±45] → 轴沿X, 中心线(y=0,z=0) ✓
#   · casing_lower bbox: x[±480] y[±305] z[±230] 中心=(0,0,0) 局部坐标
#       顶面(分型面)=局部z=+230, 须对齐世界z=0(轴中心线) → tz=-230
#       X中心=转子中点(207+810)/2=508 → tx=508, ty=0(与轴同中心线)
#   · casing_upper bbox: z[-230,+380] 中心=z+75, 底面=局部z=-230
#       底面须接合lower顶面(世界z=0) → tz=+230
#   · rotor_disc bbox: 局部XY平面(厚度沿Z), 须90°绕Y转使盘面⊥X轴 → rv=[0,1,0] ra=90 ✓
#   · driven_pulley bbox: x[0,90] y/z[±120] → 轴已沿X, 无需旋转
#       安装在轴左端(casing左壁外), tx=-90(盘跨 x=-90→0)
#   · drive_pulley  bbox: x[-15,105] y/z[±95] → 轴已沿X
#       安装在电机轴左端: tx=motor_tx-295(motor体左端)+宽度偏移
#   · screen_plate  bbox: x[-201,402] y[0,402] z[±400] 弧形筛板
#       修正: 绕[-1,1,-1]旋转120° → 800mm宽度沿X(主轴), 弧面朝下(-Z)
#       tx=508(转子中心), ty=100.5(局部X中心偏移), tz=0(轴中心线)
#   · hammer_pin bbox: x[0,142] y/z[±20] → 销轴沿X; PCD半径=220mm
#       4根销轴: Y±220, Z±220(转子中面x≈508附近, 跨4盘)
#       tx=508-71=437(使销轴中点在转子X中心)
#   · frame_base bbox: x[±650] y[±410] z[-10,510] 中心z=250
#       底座顶面(局部z=510)须托住casing底面(世界z=-230-230=-460?)
#       实际: 底座顶面world_z = tz_frame+510, 令其=casing底面z(-460): tz_frame=-970
#       → 整机太深; 将底座顶面支到casing底面z=-460: tz=-970
#   · motor_body bbox: x[-280,405] y[±295] z[±200] 中心x=62.5
#       电机横向偏离轴线, V带垂直中心距600mm → 电机轴z=-600
#       修正: tx=-495 使电机轴端对齐驱动轮(x=-90), 电机体完全在机壳外

ASSEMBLY_POSITIONS = {
    # ── 主轴: 左端原点, 沿+X延伸1145mm ─────────────
    # bbox: x[0,1145] y/z[±45] · 原点=左端中心
    "main_shaft":       {"tx":    0,   "ty":  0,  "tz":    0,  "rv": None,    "ra":  0},
    # ── 从动带轮: bbox x[0,90] 原点=左面
    # 反者道之动 V12 根治: tx=-90 使从动轮 X 中心(+45)对齐主动轮 X 中心(-45)
    # 两轮 X 中心: driven=-90+45=-45 === drive=-90+45=-45  → V 带铅直对称
    # 悬空补偿: driven_pulley 在主轴左端外延 (需主轴螺纹锁紧装配), 或后续延伸主轴
    "driven_pulley":    {"tx":  -90,   "ty":  0,  "tz":    0,  "rv": None,    "ra":  0},

    # ── 4个转子盘: bbox z[0,25] 原点=下底面中心; 绕Y+90°使盘面⊥X
    # Ry90后局部z→世界x; 盘心x=disc_center-12.5; 盘心分别在207/408/610/810
    "rotor_disc_1":     {"tx":  194.5, "ty":  0,  "tz":    0,  "rv": [0,1,0], "ra": 90},
    "rotor_disc_2":     {"tx":  395.5, "ty":  0,  "tz":    0,  "rv": [0,1,0], "ra": 90},
    "rotor_disc_3":     {"tx":  597.5, "ty":  0,  "tz":    0,  "rv": [0,1,0], "ra": 90},
    "rotor_disc_4":     {"tx":  797.5, "ty":  0,  "tz":    0,  "rv": [0,1,0], "ra": 90},

    # ── 4根销轴: bbox x[0,670] y/z[±20] 原点=左端 (修正后长670mm)
    # 修正: 销轴贯穿4盘, 以x=508为中心 → tx=508-670/2=173, 跨世界X[173,843]
    "hammer_pin_T":     {"tx":  173,   "ty": 220, "tz":    0,  "rv": None,    "ra":  0},
    "hammer_pin_B":     {"tx":  173,   "ty":-220, "tz":    0,  "rv": None,    "ra":  0},
    "hammer_pin_F":     {"tx":  173,   "ty":   0, "tz":  220,  "rv": None,    "ra":  0},
    "hammer_pin_K":     {"tx":  173,   "ty":   0, "tz": -220,  "rv": None,    "ra":  0},

    # ── 筛板: bbox x[-201,402] y[0,402] z[±400]; 弧形包住转子底部
    # 修正: 绕[-1,1,-1]旋转120° (列矩阵: col0=[0,-1,0] col1=[0,0,-1] col2=[1,0,0])
    # 效果: 800mm宽度沿X轴(主轴方向), 弧面朝下(-Z)包住转子底部
    # 世界bbox: X[108,908] Y[-302,302] Z[-402,0]
    "screen_plate":     {"tx":  508,   "ty":  100.5,  "tz":    0,  "rv": [-1,1,-1], "ra": 120},

    # ── 主动带轮: bbox x[0,120] 原点=左面
    # 带轮中心x=-45 → tx=-90; z与电机同高-600
    "drive_pulley":     {"tx":  -90,   "ty":  0,  "tz": -600,  "rv": None,    "ra":  0},

    # ── 电动机: bbox x[-280,405] 原点≈联轴器面(x=0)
    # 修正: 电机轴端对齐驱动轮x=-90 → tx=-495(电机体X[-775,-90]完全在机壳外)
    # 世界bbox: X[-775,-90] Y[-295,295] Z[-800,-405]
    "motor_body":       {"tx": -495,   "ty":  0,  "tz": -600,  "rv": None,    "ra":  0},

    # ── 下机壳: bbox z[±230] 原点=中心; 顶面(局部z=+230)=分型面=世界z=0
    # X中心=轴中点=1145/2=572.5; 机壳跨x[92.5,1052.5]夹持轴
    "casing_lower":     {"tx":  572.5, "ty":  0,  "tz": -230,  "rv": None,    "ra":  0},

    # ── 上机壳: bbox z[-230,+380] 原点距底面230mm; 底面=分型面=世界z=0
    # 原点置世界z=+230→底面世界z=0 ✓
    "casing_upper":     {"tx":  572.5, "ty":  0,  "tz":  230,  "rv": None,    "ra":  0},

    # ── 机架底座: bbox z[-10,510] 顶面=局部z=510
    # 令顶面世界z=casing_lower底世界z=-460 → tz=-460-510=-970
    "frame_base":       {"tx":  572.5, "ty":  0,  "tz": -970,  "rv": None,    "ra":  0},
}

# ── 颜色配置 (FreeCAD RGB归一化) ─────────────────────────────
COLOR_MAP = {
    "主轴":     ((0.45, 0.50, 0.75), 0),
    "从动皮带轮": ((0.20, 0.20, 0.20), 0),
    "主动皮带轮": ((0.20, 0.20, 0.20), 0),
    "主动带轮": ((0.20, 0.20, 0.20), 0),
    "转子盘":   ((0.35, 0.35, 0.55), 10),
    "销轴":     ((0.65, 0.65, 0.70), 0),
    "锤头":     ((0.95, 0.75, 0.05), 0),
    "筛板":     ((0.55, 0.80, 0.80), 55),
    "机壳":     ((0.70, 0.75, 0.75), 60),
    "电动机":   ((0.30, 0.30, 0.35), 0),
    "机架":     ((0.50, 0.50, 0.50), 0),
    "V带":      ((0.08, 0.08, 0.08), 0),
}


def check_dxf():
    missing = [k for k, v in DXF_FILES.items() if not v.exists()]
    if missing:
        print("⚠️  缺少DXF文件:", missing)
        return False
    return True
