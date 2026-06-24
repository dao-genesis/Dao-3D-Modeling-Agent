#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo_kinematics.py · 通用运动学底层 · 四大机构原型演示
══════════════════════════════════════════════════════════════════════════════
道法自然 · 一以贯之 · 同一套底层 (dao_kinematics) 可表达任意机构.

本演示展示四种截然不同的机构原型如何全部由同一个通用底层 (Mechanism +
Joint + Link) 构造, 并通过 FK / IK / 仿真 / 动力学 分析得出全套工程指标.

  A. 2R 平面机械臂    · 串行链   (SerialChain)  · 机器人学基准
  B. 4R 曲柄摇杆机构  · 闭链     (ClosedLoop)   · 回转→摆动转换
  C. 凸轮-从动杆机构  · 高副     (HigherPair)   · 非线性运动转换
  D. 旋转转子-锤头    · 装配树   (AssemblyTree) · 工业破碎机缩影

使用:
  python 50-演示_Demo/demo_kinematics.py              # 运行全部四个演示
  python 50-演示_Demo/demo_kinematics.py --demo A     # 只跑某一个
  python 50-演示_Demo/demo_kinematics.py --export     # 导出 JSON 机构规范
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════════
SCRIPT_DIR = Path(__file__).parent.resolve()
_DAO_ROOT = next((p for p in SCRIPT_DIR.parents if (p / "_paths.py").is_file()),
                  SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  五层路径自动注入

from dao_kinematics import (  # type: ignore
    SE3, Joint, JointLimits, InertiaProperties, AABB, Link, Mechanism,
    forward_kinematics, get_link_point_world, inverse_kinematics,
    analyze_balance_rotating, analyze_critical_speed_dunkerley,
    analyze_workspace, simulate_cyclic_rotation,
    run_full_analysis, mechanism_to_spec,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _section(title: str) -> None:
    print("\n" + "═" * 68)
    print(f"  {title}")
    print("═" * 68)


def _sub(title: str) -> None:
    print(f"\n── {title} ──")


# ══════════════════════════════════════════════════════════════════════════════
# 演示 A · 2R 平面机械臂 · 串行链 · FK + IK + 工作空间
# ══════════════════════════════════════════════════════════════════════════════

def demo_A_serial_arm(export: bool = False) -> Dict[str, Any]:
    _section("演示 A · 2R 平面机械臂 (串行链 · 机器人学基准)")
    print(
        "  机构: base ──(j1, revolute Z)──▶ link1 ──(j2, revolute Z)──▶ link2\n"
        "        两段 300 mm, 在 XY 平面运动"
    )

    L1, L2 = 300.0, 300.0
    mech = Mechanism(name="2R_planar_arm", root_link="base")
    mech.add_link(Link("base", aabb=AABB((-30, -30, -30), (30, 30, 30))))
    mech.add_link(Link("link1",
                       inertia=InertiaProperties.box(1.0, L1, 40, 40),
                       aabb=AABB((0, -20, -20), (L1, 20, 20))))
    mech.add_link(Link("link2",
                       inertia=InertiaProperties.box(0.8, L2, 40, 40),
                       aabb=AABB((0, -20, -20), (L2, 20, 20)),
                       key_points={"tip": (L2, 0.0, 0.0)}))
    mech.add_joint(Joint("j1", "revolute", "base", "link1",
                         axis=(0, 0, 1),
                         limits=JointLimits(lower=-math.pi, upper=math.pi)))
    mech.add_joint(Joint("j2", "revolute", "link1", "link2",
                         origin=SE3.from_translation((L1, 0, 0)),
                         axis=(0, 0, 1),
                         limits=JointLimits(lower=-math.pi*0.9, upper=math.pi*0.9)))

    # A.1 正运动学在 4 个代表位形
    _sub("A.1 正运动学 (FK) · 4 个代表位形")
    configs = [
        (0.0, 0.0,            "全伸展"),
        (math.pi/2, 0.0,      "竖直上举"),
        (math.pi/4, math.pi/4,"对角折"),
        (0.0, math.pi/2,      "肘部 90°"),
    ]
    for q1, q2, desc in configs:
        mech.set_q([q1, q2])
        tip = get_link_point_world(mech, "link2", (L2, 0.0, 0.0))
        print(f"    q=({math.degrees(q1):6.1f}°, {math.degrees(q2):6.1f}°) "
              f"→ tip=({tip[0]:7.1f}, {tip[1]:7.1f}, {tip[2]:6.2f})  ({desc})")

    # A.2 IK · 解 8 个随机目标
    #   DLS 的收敛类型依赖于初值与阻尼:
    #     低阻尼 + 靠近 zero-pose 初值 → 在奇异位形反向卡死
    #     使用 damping=0.1 与 q_init=(0.3, 0.8) 可将近似全部目标带入伸展解支
    _sub("A.2 逆运动学 (IK) · 阻尼最小二乘 · 8 个目标")
    targets = [(400, 200, 0), (0, 500, 0), (-300, 200, 0), (500, -100, 0),
               (200, 550, 0), (-400, 0, 0), (100, -400, 0), (350, 350, 0)]
    ok_count = 0
    for tgt in targets:
        # 针对 2R 平面臂的 IK: 适当初值与阻尼是收敛的关键
        best: Any = None
        for q_init in [(0.3, 0.8), (-0.3, -0.8), (1.0, 1.0), (-1.0, 1.0)]:
            r = inverse_kinematics(mech, "link2", tgt,
                                    point_in_link_local=(L2, 0.0, 0.0),
                                    q_init=list(q_init), max_iter=120,
                                    tolerance=1e-3, damping=0.1)
            if best is None or r.position_error < best.position_error:
                best = r
            if r.success:
                break
        r = best
        mark = "✅" if r.success else ("△" if r.position_error < 10 else "❌")
        if r.success: ok_count += 1
        print(f"    {mark} tgt={tgt} → err={r.position_error:7.3f} mm  "
              f"iter={r.iterations}  q=({math.degrees(r.q_final[0]):6.1f}°, "
              f"{math.degrees(r.q_final[1]):6.1f}°)")
    print(f"    → 收敛 {ok_count}/{len(targets)}")

    # A.3 工作空间分析
    _sub("A.3 工作空间分析 · 500 个采样点")
    ws = analyze_workspace(mech, "link2", (L2, 0.0, 0.0), n_samples=500)
    bb = ws.reachable_aabb
    print(f"    可达 AABB: X[{bb.min[0]:6.1f}, {bb.max[0]:6.1f}] "
          f"Y[{bb.min[1]:6.1f}, {bb.max[1]:6.1f}] "
          f"Z[{bb.min[2]:6.1f}, {bb.max[2]:6.1f}]")
    print(f"    质心: ({ws.centroid[0]:.1f}, {ws.centroid[1]:.1f}, {ws.centroid[2]:.1f})")
    print(f"    奇异采样比例: {ws.singularity_ratio*100:.1f}%")

    return {"demo": "A", "mechanism": mech, "ik_ok": ok_count,
            "workspace": {"bbox_min": list(bb.min), "bbox_max": list(bb.max),
                          "singularity_ratio": ws.singularity_ratio}}


# ══════════════════════════════════════════════════════════════════════════════
# 演示 B · 4R 曲柄摇杆机构 · 闭链 · 通过 IK 实现约束求解
# ══════════════════════════════════════════════════════════════════════════════

def demo_B_four_bar(export: bool = False) -> Dict[str, Any]:
    _section("演示 B · 4R 曲柄摇杆机构 (闭链 · 回转→摆动)")
    print(
        "  经典 Grashof 四杆:\n"
        "    A────B  (曲柄 a=100)  B────C  (连杆 b=250)  C────D  (摇杆 c=200)\n"
        "    │             ↓              │\n"
        "    └────  固定底座 d=240  ─────┘\n"
        "  输入: 曲柄角 θ_a (驱动);  输出: 摇杆角 θ_c (运动学解)"
    )

    a, b, c, d = 100.0, 250.0, 200.0, 240.0  # 四杆长度
    # 构造 Grashof: s + l ≤ p + q  (a=100 最短, b=250 最长, c=200, d=240)
    # 100 + 250 = 350 ≤ 200 + 240 = 440  ✅ 满足曲柄摇杆条件

    mech = Mechanism(name="4R_four_bar", root_link="ground")
    mech.add_link(Link("ground",
                       aabb=AABB((0, -20, -10), (d, 20, 10))))
    mech.add_link(Link("crank",
                       inertia=InertiaProperties.box(0.2, a, 20, 10),
                       aabb=AABB((0, -10, -5), (a, 10, 5)),
                       key_points={"B": (a, 0.0, 0.0)}))
    mech.add_link(Link("coupler",
                       inertia=InertiaProperties.box(0.5, b, 20, 10),
                       aabb=AABB((0, -10, -5), (b, 10, 5)),
                       key_points={"C": (b, 0.0, 0.0)}))
    mech.add_link(Link("rocker",
                       inertia=InertiaProperties.box(0.4, c, 20, 10),
                       aabb=AABB((0, -10, -5), (c, 10, 5)),
                       key_points={"C_local": (c, 0.0, 0.0)}))

    # 树形: ground → crank (j_A, revolute) → coupler (j_B, revolute)
    #         ground → rocker (j_D, revolute)
    # 闭合约束: coupler 末端 C ≡ rocker 末端 C_local (在世界空间)
    mech.add_joint(Joint("j_A", "revolute", "ground", "crank",
                         origin=SE3.from_translation((0, 0, 0)),
                         axis=(0, 0, 1)))
    mech.add_joint(Joint("j_B", "revolute", "crank", "coupler",
                         origin=SE3.from_translation((a, 0, 0)),
                         axis=(0, 0, 1)))
    mech.add_joint(Joint("j_D", "revolute", "ground", "rocker",
                         origin=SE3.from_translation((d, 0, 0)),
                         axis=(0, 0, 1)))

    # 注册闭合约束: coupler@(b,0,0) 与 rocker@(c,0,0) 必须重合
    mech.closure_constraints.append(("coupler", (b, 0, 0), "rocker", (c, 0, 0)))

    _sub("B.1 曲柄每转 30°, 三角形解法闭链 (解 rocker 角度)")
    print(f"  {'曲柄角':>7} | {'B 世界':>20} | {'摇杆角':>8} | {'闭链残差':>10}")
    print(f"  {'-'*7}-+-{'-'*20}-+-{'-'*8}-+-{'-'*10}")
    results = []
    # 三角形解法: 已知 A=(0,0), D=(d,0), B=(a·cosθ_a, a·sinθ_a),
    # 求 C 使 |BC|=b 且 |DC|=c. 两圆相交 → 两个分支, 选其中一个.
    for deg in range(0, 360, 30):
        theta_a = math.radians(deg)
        Bx = a * math.cos(theta_a); By = a * math.sin(theta_a)
        BD_len = math.hypot(Bx - d, By)
        if BD_len < abs(b - c) or BD_len > b + c:
            print(f"  {deg:>6}° | {'BD=%.1f 越界'%BD_len:>20} | {'─':>8} | {'─':>10}")
            continue
        # 余弦定理于顶点 B 处 (角分隔 ∠DBC)
        cos_DBC = (b*b + BD_len*BD_len - c*c) / (2*b*BD_len)
        cos_DBC = max(-1.0, min(1.0, cos_DBC))
        ang_DBC = math.acos(cos_DBC)
        # B → D 世界方向角
        phi_BD = math.atan2(0.0 - By, d - Bx)
        # B → C 的世界方向 (+分支 为“上”装配, Grashof 连续旋转)
        coupler_world = phi_BD + ang_DBC
        # 相对角 j_B = coupler_world - θ_a (crank 的末端刚好指向 B)
        theta_B = coupler_world - theta_a
        # C 世界
        Cx = Bx + b * math.cos(coupler_world)
        Cy = By + b * math.sin(coupler_world)
        # rocker 角 (从 D 指向 C)
        theta_D = math.atan2(Cy, Cx - d)

        mech.set_q([theta_a, theta_B, theta_D])
        poses = forward_kinematics(mech)
        C_coupler = poses["coupler"].apply_point((b, 0, 0))
        C_rocker  = poses["rocker"].apply_point((c, 0, 0))
        residual = math.hypot(C_coupler[0] - C_rocker[0],
                              C_coupler[1] - C_rocker[1])
        results.append({
            "theta_a_deg": deg,
            "theta_c_deg": math.degrees(theta_D) % 360,
            "residual_mm": residual,
            "B_world": (Bx, By),
        })
        print(f"  {deg:>6}° | ({Bx:7.1f},{By:7.1f}) | "
              f"{math.degrees(theta_D) % 360:>7.1f}° | {residual:>9.6f}")

    # B.2 摇杆角度范围
    _sub("B.2 摇杆角度范围 (θ_c 的扫描包络)")
    rocker_angles = [r["theta_c_deg"] for r in results]
    if rocker_angles:
        print(f"    θ_c ∈ [{min(rocker_angles):.1f}°, {max(rocker_angles):.1f}°]  "
              f"摆幅 = {max(rocker_angles) - min(rocker_angles):.1f}°")
        print(f"    闭链残差: max = {max(r['residual_mm'] for r in results):.4f} mm  "
              f"(闭合约束满足度)")

    return {"demo": "B", "mechanism": mech, "trajectory": results}


# ══════════════════════════════════════════════════════════════════════════════
# 演示 C · 凸轮-从动杆 · 高副 · 非圆运动学 · 位移函数直接建模
# ══════════════════════════════════════════════════════════════════════════════

def demo_C_cam_follower(export: bool = False) -> Dict[str, Any]:
    _section("演示 C · 凸轮-从动杆 (高副 · 非线性位移规律)")
    print(
        "  用 prismatic 关节表达从动杆位移, 用位移函数 s(θ) 驱动.\n"
        "  s(θ) = r₀ + h × (0.5 - 0.5·cos(2θ))   (cycloidal-like, 单程升降)\n"
        "  基圆 r₀ = 30 mm, 升程 h = 20 mm, 凸轮绕 X 轴转动"
    )

    r0 = 30.0  # 基圆
    h  = 20.0  # 升程
    mech = Mechanism(name="cam_follower", root_link="ground")
    mech.add_link(Link("ground", aabb=AABB((-50, -50, -50), (50, 50, 50))))
    mech.add_link(Link("cam",
                       inertia=InertiaProperties.cylinder(0.5, r0 + h, 20, axis="x"),
                       aabb=AABB((-10, -(r0+h), -(r0+h)), (10, r0+h, r0+h))))
    mech.add_link(Link("follower",
                       inertia=InertiaProperties.box(0.1, 60, 15, 15),
                       aabb=AABB((-30, -7.5, -7.5), (30, 7.5, 7.5)),
                       key_points={"contact": (0, 0, 0)}))

    mech.add_joint(Joint("cam_shaft", "revolute", "ground", "cam", axis=(1, 0, 0)))
    mech.add_joint(Joint("follower_slide", "prismatic", "ground", "follower",
                         origin=SE3.from_translation((0, 0, r0)),
                         axis=(0, 0, 1),
                         limits=JointLimits(lower=0.0, upper=h + 5.0)))

    def s_of_theta(theta: float) -> float:
        """位移函数 · 单程余弦升降."""
        return h * 0.5 * (1 - math.cos(2 * theta))

    _sub("C.1 一整圈 24 帧 · 位移-速度-加速度")
    print(f"  {'θ°':>5} | {'s(θ) mm':>8} | {'v(θ) mm/rad':>11} | {'a(θ) mm/rad²':>12}")
    print(f"  {'-'*5}-+-{'-'*8}-+-{'-'*11}-+-{'-'*12}")
    ds_max = 0.0; s_samples = []
    for i in range(0, 24, 2):  # 12 rows
        theta = 2 * math.pi * i / 24
        s = s_of_theta(theta)
        v = h * math.sin(2 * theta)              # ds/dθ
        a = 2 * h * math.cos(2 * theta)           # d²s/dθ²
        ds_max = max(ds_max, abs(v))
        s_samples.append(s)
        # 将 s 设入 follower_slide 的 q
        mech.joint_by_name("cam_shaft").q = [theta]
        mech.joint_by_name("follower_slide").q = [s]
        poses = forward_kinematics(mech)
        # follower 的 contact 世界位置
        contact_world = poses["follower"].apply_point((0, 0, 0))
        print(f"  {math.degrees(theta):>4.0f} | {s:>7.2f}  | "
              f"{v:>10.2f}  | {a:>11.2f}")

    _sub("C.2 行程统计")
    print(f"    行程 s(θ) ∈ [{min(s_samples):.2f}, {max(s_samples):.2f}] mm  "
          f"(h = {h} mm)")
    print(f"    最大速度 ds/dθ = {ds_max:.2f} mm/rad")
    print(f"    凸轮 1000 rpm 时: 最大线速度 = {ds_max * 1000 * 2 * math.pi / 60 / 1000:.2f} m/s")

    return {"demo": "C", "mechanism": mech,
            "stroke_mm": max(s_samples) - min(s_samples), "max_dsdθ": ds_max}


# ══════════════════════════════════════════════════════════════════════════════
# 演示 D · 锤式破碎机 · 装配树 · 全套工业分析
# ══════════════════════════════════════════════════════════════════════════════

def demo_D_hammer_crusher(export: bool = False) -> Dict[str, Any]:
    _section("演示 D · 锤式破碎机 (装配树 · 工业破碎机完整分析)")
    print(
        "  拓扑: ground ──(shaft, revolute X)──▶ rotor\n"
        "        rotor  ──(pin_i_j, fixed)──▶ hammer_i_j   (4盘 × 4锤 = 16锤)\n"
        "  工况: 1200 rpm · 锤头 4.5 kg · 销轴 PCD 440 mm · 刃尖 R 350 mm"
    )

    # 参数
    RPM        = 1200
    ROTOR_R    = 350.0
    SHAFT_L    = 1145.0
    SHAFT_D    = 90.0
    DISC_X     = [207.0, 408.0, 610.0, 810.0]
    PIN_R      = 220.0
    N_PINS     = 4
    PIN_D      = 40.0
    HAMMER_L   = 180.0
    HAMMER_W   = 80.0
    HAMMER_T   = 40.0
    HAMMER_M   = 4.49

    # 构造通用 Mechanism
    # 注: ground 不设 AABB (避免作为包围框与内部旋转构件触发假阳性干涉)
    mech = Mechanism(name="锤式破碎机_demo", root_link="ground")
    mech.add_link(Link("ground",
                       inertia=InertiaProperties.point(0.0),
                       aabb=None))
    rotor_mass = (math.pi * (SHAFT_D/2)**2 * SHAFT_L / 1e9 * 7850
                  + 4 * (math.pi * (500/2)**2 * 25 / 1e9 * 7850)
                  + 16 * 1.4)  # pins
    mech.add_link(Link("rotor",
                       inertia=InertiaProperties.cylinder(rotor_mass, ROTOR_R, SHAFT_L, axis="x"),
                       aabb=AABB((0, -ROTOR_R, -ROTOR_R), (SHAFT_L, ROTOR_R, ROTOR_R))))
    mech.add_joint(Joint("shaft", "revolute", "ground", "rotor", axis=(1, 0, 0)))

    # 4 盘 × 4 锤
    arm_len = ROTOR_R - PIN_R  # 130 mm
    for di, dx in enumerate(DISC_X):
        for pi in range(N_PINS):
            alpha = 2 * math.pi * pi / N_PINS
            name = f"hammer_{di}_{pi}"
            mech.add_link(Link(
                name,
                inertia=InertiaProperties.box(HAMMER_M, HAMMER_W, HAMMER_L, HAMMER_T),
                aabb=AABB((-HAMMER_W/2, 0, -HAMMER_T/2),
                           (HAMMER_W/2, arm_len + HAMMER_L/2, HAMMER_T/2)),
                key_points={"tip": (0.0, arm_len + HAMMER_L/2, 0.0)},
            ))
            mech.add_joint(Joint(
                f"pin_{di}_{pi}", "fixed", "rotor", name,
                origin=SE3.from_axis_angle((1.0, 0.0, 0.0), alpha,
                                            translation=(dx, 0.0, 0.0)),
            ))

    _sub("D.1 机构规模")
    print(f"    连杆 {len(mech.links)} · 关节 {len(mech.joints)} · DOF {mech.total_dof()}")

    # D.2 一站式完整分析
    _sub("D.2 run_full_analysis · 仿真/平衡/临界/离心/工作空间")
    r_cm = PIN_R + HAMMER_L/2
    masses_xloc = [
        ((math.pi * (500/2)**2 * 25 / 1e9 * 7850) + N_PINS * HAMMER_M, x)
        for x in DISC_X
    ] + [(math.pi * (500/2)**2 * 25 / 1e9 * 7850, 960.0)]

    # 忽略对: rotor 与所有 hammer (锤头固定在转子上, 原就互相接触),
    #           同盘锤头相互在 AABB 下可能重叠 (旋转至中间角度时 AABB 扩张)
    ignore_pairs = []
    for di in range(len(DISC_X)):
        for pi in range(N_PINS):
            ignore_pairs.append(("rotor", f"hammer_{di}_{pi}"))
            # 同盘锤头互忽 (4 锤在同一 x 处, AABB 会重叠)
            for pj in range(pi+1, N_PINS):
                ignore_pairs.append((f"hammer_{di}_{pi}", f"hammer_{di}_{pj}"))

    operating = {
        "driving_joint": "shaft",
        "rpm": RPM,
        "n_frames": 24,
        "ignore_pairs": ignore_pairs,
        "balance_rotor_mass_kg": rotor_mass + 16 * HAMMER_M,
        "balance_hammer_mass_kg": HAMMER_M,
        "balance_hammer_cm_radius_mm": r_cm,
        "balance_n_per_plane": N_PINS,
        "balance_n_planes": len(DISC_X),
        "balance_iso_grade": "G16",
        "shaft_diameter_mm": SHAFT_D,
        "shaft_length_mm": SHAFT_L,
        "shaft_masses_xloc": masses_xloc,
        "centrifugal_mass_kg": HAMMER_M,
        "centrifugal_radius_mm": r_cm,
        "centrifugal_pin_d_mm": PIN_D,
    }
    report = run_full_analysis(mech, operating)

    print(f"    总 DOF: {report.total_dof} · 总质量: {report.total_mass_kg} kg")
    print(f"    综合评分: {report.score}/100 · ok: {report.ok}")

    # D.3 核心指标
    _sub("D.3 核心工程指标")
    if report.simulation:
        s = report.simulation.summary
        print(f"    仿真: {s['n_interference_events']} 次干涉事件 "
              f"({s['n_severe_events']} 严重) · 扫掠 AABB = {s['swept_size_mm']} mm")
    if report.balance:
        b = report.balance
        print(f"    动平衡: ISO {b.iso_grade} 许用 {b.allowable_per_plane_gmm:.0f} g·mm/面")
        print(f"      场景: 独磨={b.scenarios['solo_worn']['imb_gmm']:.0f} / "
              f"对称={b.scenarios['pair_worn_symmetric']['imb_gmm']:.1f} / "
              f"均匀={b.scenarios['uniform_worn']['imb_gmm']:.1f} g·mm")
        print(f"      独磨临界阈值: {b.critical_wear_pct}% · 成组容限: ±{b.pair_tolerance_pct}%")
    if report.critical_speed:
        cs = report.critical_speed
        print(f"    临界转速: {cs.critical_rpm:.0f} rpm · 安全系数 {cs.safety_factor}×")
    if report.centrifugal:
        cf = report.centrifugal
        print(f"    单锤离心力: {cf.force_kN} kN · 销轴剪切: {cf.pin_shear_mpa} MPa")

    # D.4 导出 JSON 规范
    if export:
        spec = mechanism_to_spec(mech)
        out = SCRIPT_DIR / "demo_hammer_crusher.mechanism.json"
        out.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n    📄 机构规范已导出: {out}")

    return {"demo": "D", "mechanism": mech,
            "score": report.score, "ok": report.ok,
            "total_mass_kg": report.total_mass_kg,
            "critical_rpm": report.critical_speed.critical_rpm if report.critical_speed else None,
            "centrifugal_kN": report.centrifugal.force_kN if report.centrifugal else None}


# ══════════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════════

DEMOS = {"A": demo_A_serial_arm, "B": demo_B_four_bar,
         "C": demo_C_cam_follower, "D": demo_D_hammer_crusher}


def main() -> int:
    parser = argparse.ArgumentParser(description="通用运动学底层 · 四大机构原型演示")
    parser.add_argument("--demo", choices=list(DEMOS.keys()) + ["ALL"], default="ALL",
                        help="选择演示 (默认 ALL)")
    parser.add_argument("--export", action="store_true",
                        help="导出 JSON 机构规范")
    args = parser.parse_args()

    print("╔" + "═" * 66 + "╗")
    print("║  dao_kinematics · 通用运动学底层 · 四大机构原型演示           ║")
    print("║  道法自然 · 一以贯之 · 同一底层, 万类机构                    ║")
    print("╚" + "═" * 66 + "╝")

    results = {}
    to_run = list(DEMOS.keys()) if args.demo == "ALL" else [args.demo]
    for key in to_run:
        try:
            results[key] = DEMOS[key](export=args.export)
        except Exception as exc:
            print(f"\n  ❌ 演示 {key} 失败: {exc.__class__.__name__}: {exc}")
            import traceback; traceback.print_exc()
            results[key] = {"demo": key, "error": str(exc)}

    # 总结
    _section("综合汇总")
    for key, r in results.items():
        if "error" in r:
            print(f"  ❌ 演示 {key}: {r['error']}")
        else:
            names = {"A": "2R机械臂", "B": "4R曲柄摇杆", "C": "凸轮从动杆", "D": "锤式破碎机"}
            mech_name = names.get(key, key)
            print(f"  ✅ 演示 {key} ({mech_name}): OK")
    print("\n  道可道, 非常道. 同一底层 (Mechanism + Joint + Link), 可表达:")
    print("    · 串行链 (机械臂 / 关节臂)")
    print("    · 闭链   (4杆 / 6杆 / 曲柄滑块)")
    print("    · 高副   (凸轮 / 齿轮 / 螺旋)")
    print("    · 装配树 (破碎机 / 离心机 / 涡轮)")
    print("  三生万物, 万法归一.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
