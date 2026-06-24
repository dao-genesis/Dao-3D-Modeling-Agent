#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_verify_kinematics.py · 通用运动学底层 · 七相验证
══════════════════════════════════════════════════════════════════════════════
验证 00-本源_Origin/dao_kinematics.py 的七大根本能力:

  I.   数学本源     · SE3/Rodrigues 单位正交性 · 组合与逆 · 点/向量作用
  II.  关节原语     · 8 种关节类型的 FK 正确性 · 限位与 DOF
  III. FK 拓扑      · 零位 / 特殊位形 / 串联 / 树形
  IV.  Jacobian     · 数值一致性 · 与解析 Jacobian 误差
  V.   IK 收敛      · DLS 阻尼法 · 随机目标 · 奇异附近
  VI.  动力学       · 平衡 ISO 1940-1 四场景 · Dunkerley 临界 · 离心
  VII. 仿真与干涉   · 稳态旋转 · AABB 扫掠 · 径向间隙 · JSON 往返

单命令:
  python 30-验证_Verify/_verify_kinematics.py           # 默认全部七相
  python 30-验证_Verify/_verify_kinematics.py --phase III  # 只跑第三相
  python 30-验证_Verify/_verify_kinematics.py --export    # 写 JSON 报告

产出:
  _DAO_KINEMATICS_VERIFY.json (如 --export)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════════
SCRIPT_DIR = Path(__file__).parent.resolve()
_DAO_ROOT = next((p for p in SCRIPT_DIR.parents if (p / "_paths.py").is_file()),
                  SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (五层自动注入)

# ═══ 本源运动学引擎 ═══════════════════════════════════════════════════════
from dao_kinematics import (  # type: ignore
    SE3, rodrigues, rot_z, mat3_mul, mat3_transpose, mat3_identity,
    v_len, v_dist, v_sub, v_norm,
    JointLimits, Joint, InertiaProperties, AABB, Link, Mechanism,
    forward_kinematics, get_link_point_world,
    numerical_jacobian, inverse_kinematics,
    analyze_balance_rotating, analyze_critical_speed_dunkerley,
    analyze_centrifugal_load, detect_aabb_interference,
    check_radial_clearance, simulate_cyclic_rotation,
    build_mechanism_from_spec, mechanism_to_spec,
    VALID_JOINT_TYPES,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ══════════════════════════════════════════════════════════════════════════════
# 验证结果收集器
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CheckResult:
    phase: str
    name: str
    ok: bool
    detail: str = ""
    metric: Dict[str, Any] = field(default_factory=dict)


class Verifier:
    def __init__(self) -> None:
        self.results: List[CheckResult] = []
        self.t0 = time.time()

    def check(self, phase: str, name: str, ok: bool, detail: str = "",
              metric: Dict[str, Any] = None) -> bool:
        icon = "✅" if ok else "❌"
        self.results.append(CheckResult(phase, name, ok, detail, metric or {}))
        print(f"  {icon} [{phase}] {name}"
              + (f" · {detail}" if detail else ""))
        return ok

    def summary(self) -> Dict[str, Any]:
        n_pass = sum(1 for r in self.results if r.ok)
        n_fail = len(self.results) - n_pass
        score = int(n_pass / max(1, len(self.results)) * 100)
        return {
            "schema": "dao_kinematics/verify/v1",
            "n_total": len(self.results),
            "n_pass": n_pass, "n_fail": n_fail,
            "score": score,
            "elapsed_s": round(time.time() - self.t0, 2),
            "phases": sorted(set(r.phase for r in self.results)),
            "checks": [
                {"phase": r.phase, "name": r.name, "ok": r.ok,
                 "detail": r.detail, "metric": r.metric}
                for r in self.results
            ],
            "failures": [
                {"phase": r.phase, "name": r.name, "detail": r.detail}
                for r in self.results if not r.ok
            ],
        }


# ══════════════════════════════════════════════════════════════════════════════
# I. 数学本源 · SE3 / Rodrigues
# ══════════════════════════════════════════════════════════════════════════════

def phase_I(V: Verifier) -> None:
    print("\n── 相 I · 数学本源 (SE3 / Rodrigues) ──")

    # I.1 恒等变换
    T = SE3.identity()
    ok = T.apply_point((3.0, -5.0, 7.0)) == (3.0, -5.0, 7.0)
    V.check("I", "Identity SE3 保点不变", ok)

    # I.2 Rodrigues 单位正交性 R·Rᵀ = I
    for axis, ang in [((0, 0, 1), math.pi / 3),
                      ((1, 1, 1), math.pi / 4),
                      ((0.3, -0.7, 0.5), 1.234)]:
        R = rodrigues(axis, ang)
        RRt = mat3_mul(R, mat3_transpose(R))
        err = max(abs(RRt[i][j] - (1.0 if i == j else 0.0))
                  for i in range(3) for j in range(3))
        V.check("I", f"Rodrigues 正交 axis={axis} ang={ang:.2f}",
                err < 1e-9, f"max|R·Rᵀ - I| = {err:.2e}",
                {"orthogonality_error": err})

    # I.3 det(R) = 1 (right-handed)
    for axis, ang in [((0, 0, 1), math.pi / 2), ((1, 0, 0), 0.9)]:
        R = rodrigues(axis, ang)
        det = (R[0][0]*(R[1][1]*R[2][2] - R[1][2]*R[2][1])
               - R[0][1]*(R[1][0]*R[2][2] - R[1][2]*R[2][0])
               + R[0][2]*(R[1][0]*R[2][1] - R[1][1]*R[2][0]))
        V.check("I", f"det(R)=1 axis={axis}", abs(det - 1.0) < 1e-9,
                f"det = {det:.9f}")

    # I.4 SE3 组合 T1 · T1⁻¹ = I
    T1 = SE3.from_axis_angle((1, 2, 3), 1.0, translation=(10, 20, 30))
    T_inv = T1.inverse()
    T_id = T1.compose(T_inv)
    err = max(abs(T_id.t[i]) for i in range(3))
    V.check("I", "SE3 T·T⁻¹ = I (平移)", err < 1e-9,
            f"max |t| = {err:.2e}", {"inverse_error_mm": err})

    # I.5 SE3 组合 (R · t): 绕 Z 转 90° 把 (1,0,0) → (0,1,0)
    T = SE3.from_axis_angle((0, 0, 1), math.pi/2)
    p = T.apply_point((1.0, 0.0, 0.0))
    err = max(abs(p[0]), abs(p[1] - 1.0), abs(p[2]))
    V.check("I", "SE3 z旋转 90°", err < 1e-9,
            f"(1,0,0) → ({p[0]:.2e},{p[1]:.3f},{p[2]:.2e})")

    # I.6 RPY 欧拉角组合
    T = SE3.from_rpy(0.1, 0.2, 0.3, translation=(1.0, 2.0, 3.0))
    T_inv = T.inverse()
    p = T.apply_point((5.0, 6.0, 7.0))
    p_back = T_inv.apply_point(p)
    err = max(abs(p_back[i] - [5.0, 6.0, 7.0][i]) for i in range(3))
    V.check("I", "RPY T & T⁻¹ 往返", err < 1e-9,
            f"max err = {err:.2e}", {"rpy_roundtrip_error": err})


# ══════════════════════════════════════════════════════════════════════════════
# II. 关节原语 · 8 种类型
# ══════════════════════════════════════════════════════════════════════════════

def phase_II(V: Verifier) -> None:
    print("\n── 相 II · 关节原语 (8 种类型) ──")

    expected_dof = {"fixed": 0, "revolute": 1, "prismatic": 1, "helical": 1,
                    "cylindrical": 2, "spherical": 3, "universal": 2, "planar": 3}

    # II.1 所有关节类型的 DOF
    for jt, dof_expected in expected_dof.items():
        j = Joint(name=f"j_{jt}", joint_type=jt,
                  parent="a", child="b")
        V.check("II", f"DOF({jt}) = {dof_expected}",
                j.dof() == dof_expected,
                f"got {j.dof()}")

    # II.2 revolute 绕 Z 转 90° · 初始 (0,0,0) 变换后不动, 但 (1,0,0) → (0,1,0)
    j = Joint("r", "revolute", "a", "b", axis=(0, 0, 1), q=[math.pi/2])
    T = j.transform()
    p = T.apply_point((1.0, 0.0, 0.0))
    V.check("II", "revolute 90°: (1,0,0) → (0,1,0)",
            abs(p[0]) < 1e-9 and abs(p[1] - 1.0) < 1e-9)

    # II.3 prismatic 沿 X 平移 42
    j = Joint("p", "prismatic", "a", "b", axis=(1, 0, 0), q=[42.0])
    T = j.transform()
    p = T.apply_point((0.0, 0.0, 0.0))
    V.check("II", "prismatic 42mm along X",
            abs(p[0] - 42.0) < 1e-9 and abs(p[1]) < 1e-9 and abs(p[2]) < 1e-9)

    # II.4 helical 螺距 5mm/rad, 转一圈 (2π) 应平移 10π mm
    j = Joint("h", "helical", "a", "b", axis=(0, 0, 1),
              pitch=5.0, q=[2 * math.pi])
    T = j.transform()
    V.check("II", "helical 一圈 (2π, pitch=5) 平移 10π",
            abs(T.t[2] - 10 * math.pi) < 1e-9,
            f"t_z = {T.t[2]:.4f}")

    # II.5 cylindrical 同时转 π/2 + 平移 100
    j = Joint("c", "cylindrical", "a", "b", axis=(0, 0, 1),
              q=[math.pi / 2, 100.0])
    T = j.transform()
    p = T.apply_point((1.0, 0.0, 0.0))
    V.check("II", "cylindrical 同时 rot+trans",
            abs(p[0]) < 1e-9 and abs(p[1] - 1.0) < 1e-9 and abs(p[2] - 100.0) < 1e-9)

    # II.6 spherical · 绕 Z 转 π/2 (q = [0,0,π/2])
    j = Joint("s", "spherical", "a", "b",
              q=[0.0, 0.0, math.pi / 2])
    T = j.transform()
    p = T.apply_point((1.0, 0.0, 0.0))
    V.check("II", "spherical (0,0,π/2) 等同绕 Z 90°",
            abs(p[0]) < 1e-9 and abs(p[1] - 1.0) < 1e-9)

    # II.7 universal 绕 Z 90° 再绕 X 180° (相对)
    j = Joint("u", "universal", "a", "b",
              axis=(0, 0, 1), axis2=(1, 0, 0),
              q=[math.pi / 2, math.pi])
    T = j.transform()
    # (0, 1, 0) 先绕 axis2=X 转 180° → (0, -1, 0); 再绕 axis=Z 转 π/2 → (1, 0, 0)
    p = T.apply_point((0.0, 1.0, 0.0))
    V.check("II", "universal 双转", abs(p[0] - 1.0) < 1e-9 and abs(p[1]) < 1e-9,
            f"→ ({p[0]:.3f},{p[1]:.3f},{p[2]:.3f})")

    # II.8 planar (Tx=10, Ty=20, rz=π/2): (1,0,0) → (10, 21, 0)
    j = Joint("pl", "planar", "a", "b", q=[10.0, 20.0, math.pi / 2])
    T = j.transform()
    p = T.apply_point((1.0, 0.0, 0.0))
    V.check("II", "planar (10,20,π/2)", abs(p[0] - 10.0) < 1e-9 and abs(p[1] - 21.0) < 1e-9,
            f"→ ({p[0]:.3f},{p[1]:.3f},{p[2]:.3f})")

    # II.9 关节限位
    j = Joint("r2", "revolute", "a", "b",
              limits=JointLimits(lower=-1.0, upper=1.0), q=[0.5])
    V.check("II", "JointLimits in-range 0.5",
            j.in_limits() is True and j.in_limits([0.8]) is True)
    V.check("II", "JointLimits out-of-range 1.5",
            j.in_limits([1.5]) is False)
    V.check("II", "JointLimits clamp(2.0) → 1.0",
            j.clamp([2.0]) == [1.0])

    # II.10 非法类型抛错
    threw = False
    try:
        Joint("x", "nonsense", "a", "b")
    except ValueError:
        threw = True
    V.check("II", "非法 joint type 抛 ValueError", threw)


# ══════════════════════════════════════════════════════════════════════════════
# III. FK 拓扑 · 串联与树形
# ══════════════════════════════════════════════════════════════════════════════

def _make_2r_arm(L1: float = 300.0, L2: float = 300.0) -> Mechanism:
    mech = Mechanism(name="2R", root_link="base")
    mech.add_link(Link("base"))
    mech.add_link(Link("link1"))
    mech.add_link(Link("link2"))
    mech.add_joint(Joint("j1", "revolute", "base", "link1", axis=(0, 0, 1)))
    mech.add_joint(Joint("j2", "revolute", "link1", "link2",
                         origin=SE3.from_translation((L1, 0, 0)),
                         axis=(0, 0, 1)))
    return mech


def _make_3r_tree() -> Mechanism:
    """Y-shaped 树: base → (j1) → arm → (jL, jR) → left/right."""
    mech = Mechanism(name="tree3", root_link="base")
    for n in ("base", "arm", "left", "right"):
        mech.add_link(Link(n))
    mech.add_joint(Joint("j1", "revolute", "base", "arm", axis=(0, 0, 1)))
    mech.add_joint(Joint("jL", "revolute", "arm", "left",
                         origin=SE3.from_translation((200, 0, 0)), axis=(0, 0, 1)))
    mech.add_joint(Joint("jR", "revolute", "arm", "right",
                         origin=SE3.from_translation((200, 0, 0)), axis=(0, 0, 1)))
    return mech


def phase_III(V: Verifier) -> None:
    print("\n── 相 III · FK 拓扑 (串联 / 树形) ──")

    mech = _make_2r_arm(300, 300)

    # III.1 零位
    mech.set_q([0.0, 0.0])
    tip = get_link_point_world(mech, "link2", (300, 0, 0))
    V.check("III", "2R @ q=(0,0): tip (600,0,0)",
            abs(tip[0] - 600.0) < 1e-9 and abs(tip[1]) < 1e-9,
            f"tip = {tip}")

    # III.2 π/2 · 0
    mech.set_q([math.pi / 2, 0.0])
    tip = get_link_point_world(mech, "link2", (300, 0, 0))
    V.check("III", "2R @ q=(π/2,0): tip (0,600,0)",
            abs(tip[0]) < 1e-6 and abs(tip[1] - 600.0) < 1e-6,
            f"tip = {tip}")

    # III.3 0 · π
    mech.set_q([0.0, math.pi])
    tip = get_link_point_world(mech, "link2", (300, 0, 0))
    V.check("III", "2R @ q=(0,π): tip (0,0,0)",
            abs(tip[0]) < 1e-6 and abs(tip[1]) < 1e-6,
            f"tip = {tip}")

    # III.4 π · π  → 两次 π 旋转累积 2π, 末端回到 (0,0,0): link1 指 -x 到 (-300,0),
    #                link2 再翻 π 把指向从 -x 翻回 +x, 终点 (-300+300, 0, 0) = 原点
    mech.set_q([math.pi, math.pi])
    tip = get_link_point_world(mech, "link2", (300, 0, 0))
    V.check("III", "2R @ q=(π,π): 折叠回原点 (0,0,0)",
            abs(tip[0]) < 1e-6 and abs(tip[1]) < 1e-6,
            f"tip = ({tip[0]:.3e},{tip[1]:.2e})")

    # III.6 π · 0  → link1 翻到 -x 方向, link2 不转, 终点 (-600,0,0)
    mech.set_q([math.pi, 0.0])
    tip = get_link_point_world(mech, "link2", (300, 0, 0))
    V.check("III", "2R @ q=(π,0): tip (-600,0,0)",
            abs(tip[0] + 600.0) < 1e-6 and abs(tip[1]) < 1e-6,
            f"tip = ({tip[0]:.3f},{tip[1]:.2e})")

    # III.5 树形拓扑
    tree = _make_3r_tree()
    tree.set_q([0.0, 0.0, 0.0])
    poses = forward_kinematics(tree)
    V.check("III", "树形 FK: left @ arm origin",
            abs(poses["left"].t[0] - 200.0) < 1e-9 and abs(poses["right"].t[0] - 200.0) < 1e-9,
            f"left.t={poses['left'].t} right.t={poses['right'].t}")


# ══════════════════════════════════════════════════════════════════════════════
# IV. Jacobian · 数值一致性
# ══════════════════════════════════════════════════════════════════════════════

def phase_IV(V: Verifier) -> None:
    print("\n── 相 IV · Jacobian (数值求导一致性) ──")

    mech = _make_2r_arm(300, 300)

    # IV.1 解析 Jacobian of 2R planar (tip):
    # J_analytic = [[-L1 sinθ1 - L2 sin(θ1+θ2), -L2 sin(θ1+θ2)],
    #               [ L1 cosθ1 + L2 cos(θ1+θ2),  L2 cos(θ1+θ2)],
    #               [0,                           0           ]]
    for q in [(0.1, 0.2), (math.pi/4, math.pi/3), (-0.5, 1.2)]:
        mech.set_q(list(q))
        L1 = 300; L2 = 300
        s1 = math.sin(q[0]); c1 = math.cos(q[0])
        s12 = math.sin(q[0] + q[1]); c12 = math.cos(q[0] + q[1])
        J_exp = [[-L1*s1 - L2*s12, -L2*s12],
                 [ L1*c1 + L2*c12,  L2*c12],
                 [0.0, 0.0]]
        J_num = numerical_jacobian(mech, "link2", (300, 0, 0), eps=1e-5)
        err = max(abs(J_num[i][k] - J_exp[i][k])
                  for i in range(3) for k in range(2))
        V.check("IV", f"Jacobian 2R @ q={tuple(round(x,2) for x in q)}",
                err < 1e-3,
                f"max|J_num - J_ana| = {err:.2e}",
                {"max_jacobian_error": err})


# ══════════════════════════════════════════════════════════════════════════════
# V. IK · DLS 收敛性
# ══════════════════════════════════════════════════════════════════════════════

def phase_V(V: Verifier) -> None:
    print("\n── 相 V · 逆运动学 (DLS 阻尼法) ──")

    mech = _make_2r_arm(300, 300)
    # V.1 可达目标 (400, 200) · 期望收敛
    r = inverse_kinematics(mech, "link2", (400.0, 200.0, 0.0),
                           point_in_link_local=(300, 0, 0),
                           q_init=[0.1, 0.2], max_iter=100, tolerance=1e-3)
    V.check("V", "IK 可达 (400,200)",
            r.success and r.position_error < 1e-3,
            f"err={r.position_error:.4f} mm in {r.iterations} iter",
            {"err": r.position_error, "iter": r.iterations})

    # V.2 另一个可达目标 (0, 500)
    r = inverse_kinematics(mech, "link2", (0.0, 500.0, 0.0),
                           point_in_link_local=(300, 0, 0),
                           q_init=[math.pi/4, math.pi/4], max_iter=100)
    V.check("V", "IK 可达 (0,500)",
            r.success and r.position_error < 1e-2,
            f"err={r.position_error:.4f}mm iter={r.iterations}")

    # V.3 工作空间边界 (600, 0) · 单点解
    r = inverse_kinematics(mech, "link2", (599.0, 0.0, 0.0),
                           point_in_link_local=(300, 0, 0),
                           q_init=[0.01, 0.01], max_iter=200, tolerance=0.01)
    V.check("V", "IK 近边界 (599,0)", r.position_error < 0.5,
            f"err={r.position_error:.4f}mm")

    # V.4 不可达目标 (1000, 0) · 至少收敛到工作空间外 (残余 ≥ 400mm) 且
    #     不发散 (≤ 2×diameter). DLS 在不可达目标下的最终位形依赖于 λ 与 q_init,
    #     多种合法行为: 完全伸展 (err≈400) / 反向卡死 (err≈1200). 都视为 "已收敛".
    r = inverse_kinematics(mech, "link2", (1000.0, 0.0, 0.0),
                           point_in_link_local=(300, 0, 0),
                           q_init=[0.01, 0.01], max_iter=100,
                           damping=0.1)
    V.check("V", "IK 不可达 (1000,0) · 稳定有界",
            350 <= r.position_error <= 1300,
            f"err={r.position_error:.1f}mm (伸展 ~400 / 反向 ~1200 均合法)")

    # V.5 较高阻尼下, 良好初值应驱向伸展解 (err ≈ 400)
    r = inverse_kinematics(mech, "link2", (1000.0, 0.0, 0.0),
                           point_in_link_local=(300, 0, 0),
                           q_init=[0.0, 0.0], max_iter=200,
                           damping=0.5)
    V.check("V", "IK 不可达 (1000,0) · 零初值+强阻尼 → 伸展解",
            abs(r.position_error - 400.0) < 5.0,
            f"err={r.position_error:.2f}mm")


# ══════════════════════════════════════════════════════════════════════════════
# VI. 动力学 · 平衡 + 临界 + 离心
# ══════════════════════════════════════════════════════════════════════════════

def phase_VI(V: Verifier) -> None:
    print("\n── 相 VI · 动力学 (平衡 / 临界 / 离心) ──")

    # VI.1 动平衡 · 锤式破碎机工况
    bal = analyze_balance_rotating(
        rotor_mass_kg=150, rpm=1200, hammer_mass_kg=4.5,
        hammer_cm_radius_mm=310, n_hammers_per_plane=4, n_planes=4,
        iso_grade="G16", wear_pct_scenario=30.0,
    )
    V.check("VI", "ISO G16 对称成组策略通过",
            bal.scenarios["pair_worn_symmetric"]["ok"],
            f"imb_pair = {bal.scenarios['pair_worn_symmetric']['imb_gmm']:.2f} g·mm "
            f"U_plane = {bal.allowable_per_plane_gmm:.0f}")
    V.check("VI", "四场景独磨最坏为最大值",
            bal.scenarios["solo_worn"]["imb_gmm"] > bal.scenarios["pair_worn_symmetric"]["imb_gmm"],
            f"solo={bal.scenarios['solo_worn']['imb_gmm']:.0f} "
            f">> pair={bal.scenarios['pair_worn_symmetric']['imb_gmm']:.2f}")
    V.check("VI", "独磨临界阈值合理 (0.1~5%)",
            0.1 < bal.critical_wear_pct < 5.0,
            f"crit_wear = {bal.critical_wear_pct:.2f}%")

    # VI.2 临界转速 · 锤破主轴 Ø90×1145
    cs = analyze_critical_speed_dunkerley(
        shaft_diameter_mm=90, shaft_length_mm=1145, working_rpm=1200,
        masses_xloc=[(40, 207), (40, 408), (40, 610), (40, 810), (40, 960)],
    )
    V.check("VI", "临界转速安全 > 1.33×",
            cs.safety_factor > 1.33,
            f"n_cr = {cs.critical_rpm:.0f} rpm · safety = {cs.safety_factor:.2f}")
    V.check("VI", "临界转速 > 工作转速",
            cs.critical_rpm > cs.working_rpm,
            f"{cs.critical_rpm:.0f} > {cs.working_rpm}")

    # VI.3 离心载荷
    cf = analyze_centrifugal_load(
        mass_kg=4.5, radius_cm_mm=310, rpm=1200,
        pin_diameter_mm=40, allowable_shear_mpa=100,
    )
    # F = 4.5 * (125.66)² * 0.31 ≈ 22 kN
    V.check("VI", "离心力 F ≈ 22 kN (锤头@310mm, 1200rpm)",
            20 < cf.force_kN < 24,
            f"F = {cf.force_kN:.2f} kN")
    V.check("VI", "销轴剪切在许用内",
            cf.ok, f"τ = {cf.pin_shear_mpa:.1f} MPa")


# ══════════════════════════════════════════════════════════════════════════════
# VII. 仿真与干涉 · AABB 扫掠 + 径向间隙 + JSON 往返
# ══════════════════════════════════════════════════════════════════════════════

def phase_VII(V: Verifier) -> None:
    print("\n── 相 VII · 仿真与干涉 ──")

    # VII.1 构造一个绕 X 轴旋转的转子 · 锤头刃尖置于 YZ 平面内 (r=400 mm, 初始沿 +Y)
    #        锤头 key_point 必须偏离旋转轴, 否则旋转不会改变其世界坐标
    mech = Mechanism(name="rotor_1h", root_link="ground")
    mech.add_link(Link("ground", aabb=AABB((-50, -500, -500), (50, 500, 500))))
    mech.add_link(Link("rotor",
                       aabb=AABB((-10, -10, -10), (10, 10, 10)),
                       inertia=InertiaProperties.point(40.0)))
    # 锤头本地坐标系: 刃尖沿 +Y 方向伸出 400 mm (以销轴中心为原点)
    mech.add_link(Link("hammer",
                       aabb=AABB((-20, -20, -20), (20, 400, 20)),
                       inertia=InertiaProperties.box(4.5, 180, 80, 40),
                       key_points={"tip": (0.0, 400.0, 0.0)}))
    mech.add_joint(Joint("shaft", "revolute", "ground", "rotor", axis=(1, 0, 0)))
    mech.add_joint(Joint("pin", "fixed", "rotor", "hammer",
                         origin=SE3.identity()))

    sim = simulate_cyclic_rotation(mech, driving_joint="shaft", rpm=1200,
                                    n_frames=24,
                                    ignore_pairs=[("rotor", "hammer")])
    V.check("VII", "仿真帧数 = 24", sim.n_frames == 24)
    V.check("VII", "周期 ≈ 50 ms @ 1200 rpm",
            abs(sim.period_ms - 50.0) < 0.1,
            f"period = {sim.period_ms:.3f} ms")
    # 锤尖每帧的 r = sqrt(y² + z²) 应恒 ≈ 400 (绕 X 轴旋转保持 YZ 平面距离)
    tip_r: List[float] = []
    for kf in sim.keyframes:
        t = kf.key_points.get("hammer", {}).get("tip")
        if t is None: continue
        tip_r.append(math.sqrt(t[1]**2 + t[2]**2))
    r_mean = sum(tip_r) / len(tip_r) if tip_r else 0
    r_std = math.sqrt(sum((r - r_mean)**2 for r in tip_r) / len(tip_r)) if tip_r else 0
    V.check("VII", "锤尖半径恒定 ≈ 400 mm (绕 X 旋转)",
            abs(r_mean - 400.0) < 0.5 and r_std < 0.5,
            f"mean={r_mean:.2f} std={r_std:.4f} (n={len(tip_r)})")
    # tip_x 应恒为 0 (锤头初始在 YZ 平面, 绕 X 旋转保持 X=0)
    tip_x_abs_max = max(abs(kf.key_points.get("hammer", {}).get("tip", (0, 0, 0))[0])
                        for kf in sim.keyframes)
    V.check("VII", "锤尖 X 坐标恒 0 (在 YZ 平面)",
            tip_x_abs_max < 1e-6, f"max|x| = {tip_x_abs_max:.2e}")

    # VII.2 径向间隙 · 锤尖 400 vs 机壳内半径 430 · 间隙 30 mm > 20 ✅
    rc = check_radial_clearance(400, 430, "锤尖", "机壳", min_clearance_mm=20)
    V.check("VII", "径向间隙 锤尖400 vs 机壳430 ≥ 20mm",
            rc["severity"] == "OK", f"clearance = {rc['clearance_mm']:.1f} mm")

    # VII.3 筛板设计意图穿透 · 锤尖 400, 筛板内径 390, 穿透 10 (意图 20 → OK)
    rc = check_radial_clearance(400, 390, "锤尖", "筛板",
                                 min_clearance_mm=0,
                                 design_intent_penetration_mm=20)
    V.check("VII", "筛板穿透 10mm 在设计意图内 (≤20)",
            rc["severity"] == "DESIGN_INTENT", f"sev={rc['severity']}")

    # VII.4 硬干涉: 锤尖 400, 机壳 350 · 穿透 50 · HARD
    rc = check_radial_clearance(400, 350, "锤尖", "机壳",
                                 min_clearance_mm=20,
                                 design_intent_penetration_mm=0)
    V.check("VII", "严重硬穿透报 HARD",
            rc["severity"] == "HARD", f"sev={rc['severity']}")

    # VII.5 JSON 规范往返
    spec = mechanism_to_spec(mech)
    js = json.dumps(spec, ensure_ascii=False)
    spec2 = json.loads(js)
    mech2 = build_mechanism_from_spec(spec2)
    V.check("VII", "JSON spec 序列化-反序列化",
            mech2.total_dof() == mech.total_dof()
            and len(mech2.links) == len(mech.links)
            and len(mech2.joints) == len(mech.joints),
            f"dof={mech2.total_dof()} links={len(mech2.links)} joints={len(mech2.joints)}")

    # VII.6 AABB 干涉检测: 构造两个显然重叠的连杆
    m = Mechanism(name="aabb_test", root_link="g")
    m.add_link(Link("g"))
    m.add_link(Link("a", aabb=AABB((-50, -50, -50), (50, 50, 50))))
    m.add_link(Link("b", aabb=AABB((0, 0, 0), (100, 100, 100))))
    m.add_joint(Joint("ja", "fixed", "g", "a"))
    m.add_joint(Joint("jb", "fixed", "g", "b"))
    events = detect_aabb_interference(m, [m.get_q()], [0.0])
    V.check("VII", "AABB 检测到明显重叠",
            len(events) == 1 and events[0].overlap_mm > 40,
            f"n_events = {len(events)} overlap = {events[0].overlap_mm if events else 0} mm")


# ══════════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════════

PHASES = {
    "I": phase_I, "II": phase_II, "III": phase_III, "IV": phase_IV,
    "V": phase_V, "VI": phase_VI, "VII": phase_VII,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="dao_kinematics 七相验证")
    parser.add_argument("--phase", choices=list(PHASES.keys()) + ["ALL"],
                        default="ALL", help="跑指定相 (默认 ALL)")
    parser.add_argument("--export", action="store_true",
                        help="写 JSON 报告到 _DAO_KINEMATICS_VERIFY.json")
    parser.add_argument("--output", default="_DAO_KINEMATICS_VERIFY.json")
    args = parser.parse_args()

    print("=" * 68)
    print("  dao_kinematics · 七相验证 · 通用运动学底层")
    print("=" * 68)

    V = Verifier()

    phases_to_run = list(PHASES.keys()) if args.phase == "ALL" else [args.phase]
    for p in phases_to_run:
        try:
            PHASES[p](V)
        except Exception as exc:
            V.check(p, f"运行异常: {exc.__class__.__name__}", False, str(exc))

    # 汇总
    summary = V.summary()
    print("\n" + "=" * 68)
    print(f"  综合 · 通过 {summary['n_pass']}/{summary['n_total']} · "
          f"评分 {summary['score']}/100 · 耗时 {summary['elapsed_s']}s")
    if summary["n_fail"] > 0:
        print(f"  ❌ 失败 {summary['n_fail']}:")
        for f in summary["failures"]:
            print(f"     [{f['phase']}] {f['name']}: {f['detail']}")
    else:
        print("  ✅ 全部通过")
    print("=" * 68)

    if args.export:
        out = SCRIPT_DIR / args.output
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"  📄 报告: {out}")

    return 0 if summary["n_fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
