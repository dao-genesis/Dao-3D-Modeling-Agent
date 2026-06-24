#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_kinematics.py · 通用运动学底层 · 万法之资归一
══════════════════════════════════════════════════════════════════════════════
道生一  → 向量/四元数/齐次变换                (Vec3 / Quat / SE3)
一生二  → 连杆 + 关节                         (Link / Joint)
二生三  → 机构 = 连杆×关节 构成的拓扑树        (Mechanism)
三生万物 → 正逆运动学 · 动力学 · 干涉 · 平衡     (FK / IK / Dynamics / Interference / Balance)

反者道之动 — 不从具体零件出发, 从通用关节原语出发, 任何机构皆是其组合.
柔弱胜刚强 — 零外部依赖 (只用 math/json), 可嵌入任意环境.
无为而无不为 — API 只暴露必要, 默认参数覆盖 95% 场景.

关节谱系: fixed / revolute / prismatic / helical / cylindrical /
          spherical / universal / planar
三大分析: ForwardKinematics / InverseKinematics (DLS) / KinematicsSimulator
三大动力: InertiaCalculator / BalanceAnalyzer (ISO 1940-1) / CriticalSpeedAnalyzer (Dunkerley)
两大审查: InterferenceDetector (AABB+扫掠) / WorkspaceAnalyzer

该模块完全内化了锤式破碎机项目中 dao_kinematic.py 的全部能力并泛化至通用机构.
"""
from __future__ import annotations

import cmath
import json
import math
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

__version__ = "1.0.0"
EPS = 1e-12

Vec3T = Tuple[float, float, float]
Mat3T = List[List[float]]
Mat4T = List[List[float]]


# ══════════════════════════════════════════════════════════════════════════════
# 一、数学本源 · 向量 / 矩阵 / 齐次变换 SE3
# ══════════════════════════════════════════════════════════════════════════════

def v3(x=0.0, y=0.0, z=0.0) -> Vec3T:
    return (float(x), float(y), float(z))

def v_add(a: Vec3T, b: Vec3T) -> Vec3T:
    return (a[0]+b[0], a[1]+b[1], a[2]+b[2])

def v_sub(a: Vec3T, b: Vec3T) -> Vec3T:
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def v_scale(a: Vec3T, s: float) -> Vec3T:
    return (a[0]*s, a[1]*s, a[2]*s)

def v_dot(a: Vec3T, b: Vec3T) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def v_cross(a: Vec3T, b: Vec3T) -> Vec3T:
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

def v_len(a: Vec3T) -> float:
    return math.sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])

def v_dist(a: Vec3T, b: Vec3T) -> float:
    return v_len(v_sub(a, b))

def v_norm(a: Vec3T) -> Vec3T:
    m = v_len(a)
    return (a[0]/m, a[1]/m, a[2]/m) if m > EPS else (0.0, 0.0, 0.0)

def mat3_identity() -> Mat3T:
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

def mat3_mul(A: Mat3T, B: Mat3T) -> Mat3T:
    return [[A[i][0]*B[0][j] + A[i][1]*B[1][j] + A[i][2]*B[2][j]
             for j in range(3)] for i in range(3)]

def mat3_vec(M: Mat3T, v: Vec3T) -> Vec3T:
    return (M[0][0]*v[0] + M[0][1]*v[1] + M[0][2]*v[2],
            M[1][0]*v[0] + M[1][1]*v[1] + M[1][2]*v[2],
            M[2][0]*v[0] + M[2][1]*v[1] + M[2][2]*v[2])

def mat3_transpose(M: Mat3T) -> Mat3T:
    return [[M[j][i] for j in range(3)] for i in range(3)]

def rodrigues(axis: Vec3T, angle: float) -> Mat3T:
    """Rodrigues: R = I + sinθ·[k]× + (1-cosθ)·[k]×² (分量展开)."""
    ax, ay, az = v_norm(axis)
    c = math.cos(angle); s = math.sin(angle); t = 1.0 - c
    return [
        [t*ax*ax + c,     t*ax*ay - s*az, t*ax*az + s*ay],
        [t*ax*ay + s*az,  t*ay*ay + c,    t*ay*az - s*ax],
        [t*ax*az - s*ay,  t*ay*az + s*ax, t*az*az + c],
    ]

def rot_x(a): c,s = math.cos(a), math.sin(a); return [[1,0,0],[0,c,-s],[0,s,c]]
def rot_y(a): c,s = math.cos(a), math.sin(a); return [[c,0,s],[0,1,0],[-s,0,c]]
def rot_z(a): c,s = math.cos(a), math.sin(a); return [[c,-s,0],[s,c,0],[0,0,1]]


class SE3:
    """齐次变换 (R, t). 组合用 compose 或 @ 运算符."""
    __slots__ = ("R", "t")

    def __init__(self, R: Optional[Mat3T] = None, t: Optional[Vec3T] = None):
        self.R: Mat3T = [row[:] for row in (R if R else mat3_identity())]
        self.t: Vec3T = tuple(t) if t else (0.0, 0.0, 0.0)  # type: ignore

    @staticmethod
    def identity() -> "SE3": return SE3()

    @staticmethod
    def from_translation(t: Vec3T) -> "SE3":
        return SE3(mat3_identity(), t)

    @staticmethod
    def from_rotation(R: Mat3T) -> "SE3":
        return SE3(R, (0.0, 0.0, 0.0))

    @staticmethod
    def from_axis_angle(axis: Vec3T, angle: float,
                        translation: Vec3T = (0.0, 0.0, 0.0)) -> "SE3":
        return SE3(rodrigues(axis, angle), translation)

    @staticmethod
    def from_rpy(roll: float, pitch: float, yaw: float,
                 translation: Vec3T = (0.0, 0.0, 0.0)) -> "SE3":
        R = mat3_mul(mat3_mul(rot_z(yaw), rot_y(pitch)), rot_x(roll))
        return SE3(R, translation)

    def compose(self, other: "SE3") -> "SE3":
        R_new = mat3_mul(self.R, other.R)
        t_new = v_add(self.t, mat3_vec(self.R, other.t))
        return SE3(R_new, t_new)

    def __matmul__(self, other: "SE3") -> "SE3":
        return self.compose(other)

    def inverse(self) -> "SE3":
        Rt = mat3_transpose(self.R)
        t_inv = v_scale(mat3_vec(Rt, self.t), -1.0)
        return SE3(Rt, t_inv)

    def apply_point(self, p: Vec3T) -> Vec3T:
        return v_add(mat3_vec(self.R, p), self.t)

    def apply_vector(self, v: Vec3T) -> Vec3T:
        return mat3_vec(self.R, v)

    def translation(self) -> Vec3T:
        return self.t

    def rotation(self) -> Mat3T:
        return [row[:] for row in self.R]

    def __repr__(self):
        t = self.t
        return f"SE3(t=[{t[0]:.3f},{t[1]:.3f},{t[2]:.3f}])"


# ══════════════════════════════════════════════════════════════════════════════
# 二、关节原语 · 1~3 DOF · fixed/revolute/prismatic/helical/cylindrical/
#                spherical/universal/planar
# ══════════════════════════════════════════════════════════════════════════════

VALID_JOINT_TYPES = {
    "fixed", "revolute", "prismatic", "helical",
    "cylindrical", "spherical", "universal", "planar",
}
_DOF_MAP = {
    "fixed": 0, "revolute": 1, "prismatic": 1, "helical": 1,
    "cylindrical": 2, "spherical": 3, "universal": 2, "planar": 3,
}


@dataclass
class JointLimits:
    lower: Optional[float] = None
    upper: Optional[float] = None
    velocity: Optional[float] = None
    effort: Optional[float] = None

    def clamp(self, q: float) -> float:
        if self.lower is not None and q < self.lower: return self.lower
        if self.upper is not None and q > self.upper: return self.upper
        return q

    def in_range(self, q: float) -> bool:
        if self.lower is not None and q < self.lower - 1e-9: return False
        if self.upper is not None and q > self.upper + 1e-9: return False
        return True


@dataclass
class Joint:
    """通用关节: parent → child 以 origin 为安装点, 绕/沿 axis 运动."""
    name: str
    joint_type: str
    parent: str
    child: str
    origin: SE3 = field(default_factory=SE3.identity)
    axis: Vec3T = (0.0, 0.0, 1.0)
    axis2: Vec3T = (1.0, 0.0, 0.0)        # universal 副轴
    pitch: float = 0.0                    # helical 螺距 (mm/rad)
    limits: JointLimits = field(default_factory=JointLimits)
    q: List[float] = field(default_factory=list)

    def __post_init__(self):
        if self.joint_type not in VALID_JOINT_TYPES:
            raise ValueError(f"Unknown joint type: {self.joint_type}")
        self.axis = v_norm(self.axis)
        if self.joint_type == "universal":
            self.axis2 = v_norm(self.axis2)
        dof = self.dof()
        if len(self.q) < dof:
            self.q = list(self.q) + [0.0] * (dof - len(self.q))
        elif len(self.q) > dof:
            self.q = list(self.q[:dof])

    def dof(self) -> int:
        return _DOF_MAP[self.joint_type]

    def transform(self, q: Optional[Sequence[float]] = None) -> SE3:
        """T = origin · Δ(q)."""
        qv = list(q) if q is not None else self.q
        jt = self.joint_type
        if jt == "fixed":
            delta = SE3.identity()
        elif jt == "revolute":
            delta = SE3.from_axis_angle(self.axis, qv[0])
        elif jt == "prismatic":
            delta = SE3.from_translation(v_scale(self.axis, qv[0]))
        elif jt == "helical":
            delta = SE3(rodrigues(self.axis, qv[0]),
                        v_scale(self.axis, qv[0] * self.pitch))
        elif jt == "cylindrical":
            delta = SE3(rodrigues(self.axis, qv[0]),
                        v_scale(self.axis, qv[1]))
        elif jt == "spherical":
            ang = math.sqrt(qv[0]*qv[0] + qv[1]*qv[1] + qv[2]*qv[2])
            if ang < EPS:
                delta = SE3.identity()
            else:
                delta = SE3.from_axis_angle((qv[0]/ang, qv[1]/ang, qv[2]/ang), ang)
        elif jt == "universal":
            R1 = rodrigues(self.axis, qv[0])
            R2 = rodrigues(self.axis2, qv[1])
            delta = SE3(mat3_mul(R1, R2), (0.0, 0.0, 0.0))
        elif jt == "planar":
            delta = SE3(rot_z(qv[2]), (qv[0], qv[1], 0.0))
        else:
            delta = SE3.identity()
        return self.origin.compose(delta)

    def in_limits(self, q=None) -> bool:
        qv = list(q) if q is not None else self.q
        if self.dof() == 1 and len(qv) >= 1:
            return self.limits.in_range(qv[0])
        return True

    def clamp(self, q=None) -> List[float]:
        qv = list(q) if q is not None else list(self.q)
        if self.dof() == 1 and len(qv) >= 1:
            qv[0] = self.limits.clamp(qv[0])
        return qv


# ══════════════════════════════════════════════════════════════════════════════
# 三、连杆 · 刚体 (质量+惯量+AABB+关键点+圆柱包络)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class InertiaProperties:
    mass_kg: float = 0.0
    com: Vec3T = (0.0, 0.0, 0.0)
    ixx: float = 0.0; iyy: float = 0.0; izz: float = 0.0
    ixy: float = 0.0; ixz: float = 0.0; iyz: float = 0.0

    @staticmethod
    def cylinder(mass_kg, radius_mm, length_mm, axis="x"):
        r, L = radius_mm, length_mm
        I_axis = 0.5 * mass_kg * r * r
        I_rad  = mass_kg * (3*r*r + L*L) / 12
        if axis == "x": return InertiaProperties(mass_kg=mass_kg, ixx=I_axis, iyy=I_rad, izz=I_rad)
        if axis == "y": return InertiaProperties(mass_kg=mass_kg, iyy=I_axis, ixx=I_rad, izz=I_rad)
        return InertiaProperties(mass_kg=mass_kg, izz=I_axis, ixx=I_rad, iyy=I_rad)

    @staticmethod
    def box(mass_kg, lx, ly, lz):
        return InertiaProperties(
            mass_kg=mass_kg,
            ixx=mass_kg*(ly*ly + lz*lz)/12,
            iyy=mass_kg*(lx*lx + lz*lz)/12,
            izz=mass_kg*(lx*lx + ly*ly)/12,
        )

    @staticmethod
    def point(mass_kg, com=(0.0, 0.0, 0.0)):
        return InertiaProperties(mass_kg=mass_kg, com=com)


@dataclass
class AABB:
    min: Vec3T = (0.0, 0.0, 0.0)
    max: Vec3T = (0.0, 0.0, 0.0)

    def center(self) -> Vec3T:
        return ((self.min[0]+self.max[0])/2, (self.min[1]+self.max[1])/2, (self.min[2]+self.max[2])/2)

    def size(self) -> Vec3T:
        return (self.max[0]-self.min[0], self.max[1]-self.min[1], self.max[2]-self.min[2])

    def corners(self) -> List[Vec3T]:
        xs=(self.min[0], self.max[0]); ys=(self.min[1], self.max[1]); zs=(self.min[2], self.max[2])
        return [(x,y,z) for x in xs for y in ys for z in zs]

    def transformed(self, T: SE3) -> "AABB":
        pts = [T.apply_point(c) for c in self.corners()]
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]; zs=[p[2] for p in pts]
        return AABB((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))

    def overlaps(self, other: "AABB", tol: float = 0.0) -> bool:
        return (self.min[0] <= other.max[0]+tol and self.max[0] >= other.min[0]-tol and
                self.min[1] <= other.max[1]+tol and self.max[1] >= other.min[1]-tol and
                self.min[2] <= other.max[2]+tol and self.max[2] >= other.min[2]-tol)


@dataclass
class Link:
    name: str
    inertia: InertiaProperties = field(default_factory=InertiaProperties)
    aabb: Optional[AABB] = None
    key_points: Dict[str, Vec3T] = field(default_factory=dict)
    envelope_cylinder: Optional[Tuple[str, float, float]] = None  # (axis,r,L)


# ══════════════════════════════════════════════════════════════════════════════
# 四、机构 · 连杆 + 关节 DAG
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Mechanism:
    name: str = "mechanism"
    links: Dict[str, Link] = field(default_factory=dict)
    joints: List[Joint] = field(default_factory=list)
    root_link: str = "ground"
    closure_constraints: List[Tuple[str, Vec3T, str, Vec3T]] = field(default_factory=list)

    def add_link(self, link: Link) -> "Mechanism":
        self.links[link.name] = link
        return self

    def add_joint(self, joint: Joint) -> "Mechanism":
        if joint.parent not in self.links:
            raise ValueError(f"Joint '{joint.name}' parent '{joint.parent}' not in links")
        if joint.child not in self.links:
            raise ValueError(f"Joint '{joint.name}' child '{joint.child}' not in links")
        self.joints.append(joint)
        return self

    def children_of(self, link_name: str):
        return [(j, j.child) for j in self.joints if j.parent == link_name]

    def joint_by_name(self, name: str) -> Joint:
        for j in self.joints:
            if j.name == name: return j
        raise KeyError(f"No joint named '{name}'")

    def movable_joints(self) -> List[Joint]:
        return [j for j in self.joints if j.dof() > 0]

    def total_dof(self) -> int:
        return sum(j.dof() for j in self.movable_joints())

    def get_q(self) -> List[float]:
        out: List[float] = []
        for j in self.movable_joints():
            out.extend(j.q)
        return out

    def set_q(self, q_flat: Sequence[float]) -> None:
        if len(q_flat) != self.total_dof():
            raise ValueError(f"q dim mismatch: expected {self.total_dof()}, got {len(q_flat)}")
        idx = 0
        for j in self.movable_joints():
            d = j.dof()
            j.q = list(q_flat[idx:idx+d])
            idx += d


# ══════════════════════════════════════════════════════════════════════════════
# 五、正运动学 (FK)
# ══════════════════════════════════════════════════════════════════════════════

def forward_kinematics(mech: Mechanism, q_flat: Optional[Sequence[float]] = None) -> Dict[str, SE3]:
    """BFS 遍历连杆树, 求每个连杆的世界姿态."""
    saved_q = None
    if q_flat is not None:
        saved_q = mech.get_q()
        mech.set_q(q_flat)
    try:
        poses: Dict[str, SE3] = {mech.root_link: SE3.identity()}
        frontier = [mech.root_link]
        visited = {mech.root_link}
        while frontier:
            nxt: List[str] = []
            for parent in frontier:
                for j, child in mech.children_of(parent):
                    if child in visited:
                        continue
                    T_world = poses[parent].compose(j.transform())
                    poses[child] = T_world
                    visited.add(child)
                    nxt.append(child)
            frontier = nxt
        return poses
    finally:
        if saved_q is not None:
            mech.set_q(saved_q)


def get_link_point_world(mech: Mechanism, link_name: str, p_local: Vec3T,
                         poses: Optional[Dict[str, SE3]] = None) -> Vec3T:
    if poses is None:
        poses = forward_kinematics(mech)
    return poses[link_name].apply_point(p_local)


# ══════════════════════════════════════════════════════════════════════════════
# 六、雅可比 · 数值中心差分
# ══════════════════════════════════════════════════════════════════════════════

def numerical_jacobian(mech: Mechanism, target_link: str,
                       target_point_local: Vec3T = (0.0, 0.0, 0.0),
                       eps: float = 1e-5) -> List[List[float]]:
    """∂p_world/∂q, 3×N, 中心差分."""
    N = mech.total_dof()
    q0 = mech.get_q()
    J: List[List[float]] = [[0.0]*N for _ in range(3)]
    for k in range(N):
        qp = list(q0); qp[k] += eps
        qm = list(q0); qm[k] -= eps
        pp = forward_kinematics(mech, qp)[target_link].apply_point(target_point_local)
        pm = forward_kinematics(mech, qm)[target_link].apply_point(target_point_local)
        for i in range(3):
            J[i][k] = (pp[i] - pm[i]) / (2*eps)
    return J


# ══════════════════════════════════════════════════════════════════════════════
# 七、逆运动学 (IK) · 阻尼最小二乘法 (DLS)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class IKResult:
    success: bool
    q_final: List[float]
    position_error: float
    iterations: int
    damping: float
    error_history: List[float] = field(default_factory=list)
    message: str = ""


def _invert_3x3(M: Mat3T) -> Optional[Mat3T]:
    a,b,c = M[0]; d,e,f = M[1]; g,h,i = M[2]
    det = a*(e*i - f*h) - b*(d*i - f*g) + c*(d*h - e*g)
    if abs(det) < 1e-18: return None
    inv = 1.0/det
    return [
        [(e*i - f*h)*inv, (c*h - b*i)*inv, (b*f - c*e)*inv],
        [(f*g - d*i)*inv, (a*i - c*g)*inv, (c*d - a*f)*inv],
        [(d*h - e*g)*inv, (b*g - a*h)*inv, (a*e - b*d)*inv],
    ]


def _clamp_flat_q(mech: Mechanism, q_flat: List[float]) -> List[float]:
    out = list(q_flat); idx = 0
    for j in mech.movable_joints():
        d = j.dof()
        clamped = j.clamp(out[idx:idx+d])
        for k in range(d):
            out[idx+k] = clamped[k]
        idx += d
    return out


def inverse_kinematics(mech: Mechanism, target_link: str,
                       target_point_world: Vec3T,
                       point_in_link_local: Vec3T = (0.0, 0.0, 0.0),
                       q_init: Optional[Sequence[float]] = None,
                       max_iter: int = 80,
                       tolerance: float = 1e-3,
                       damping: float = 1e-2) -> IKResult:
    """
    Damped Least Squares (Levenberg-Marquardt):
      Δq = Jᵀ (J Jᵀ + λ²I)⁻¹ · e
    """
    N = mech.total_dof()
    if N == 0:
        return IKResult(False, [], 0.0, 0, damping, message="No DOF")
    q = list(q_init) if q_init is not None else mech.get_q()
    if len(q) != N:
        return IKResult(False, q, math.inf, 0, damping,
                        message=f"q_init dim {len(q)} != dof {N}")
    errors: List[float] = []
    for it in range(max_iter):
        # 关键: 每步先把当前 q 同步到 mech, 才能让 numerical_jacobian 在正确位形处求导
        mech.set_q(q)
        p = forward_kinematics(mech)[target_link].apply_point(point_in_link_local)
        e = v_sub(target_point_world, p)
        err = v_len(e)
        errors.append(err)
        if err < tolerance:
            return IKResult(True, q, err, it, damping, errors, "converged")
        J = numerical_jacobian(mech, target_link, point_in_link_local)
        JJt = [[sum(J[i][k]*J[j][k] for k in range(N)) for j in range(3)] for i in range(3)]
        lam2 = damping*damping
        for i in range(3):
            JJt[i][i] += lam2
        JJt_inv = _invert_3x3(JJt)
        if JJt_inv is None: break
        v = mat3_vec(JJt_inv, e)  # type: ignore
        dq = [sum(J[i][k]*v[i] for i in range(3)) for k in range(N)]
        q = [q[k] + dq[k] for k in range(N)]
        q = _clamp_flat_q(mech, q)
    mech.set_q(q)
    p = forward_kinematics(mech, q)[target_link].apply_point(point_in_link_local)
    err = v_dist(target_point_world, p)
    return IKResult(err < tolerance*10, q, err, max_iter, damping, errors,
                    "max_iter" if err >= tolerance else "converged_late")


# ══════════════════════════════════════════════════════════════════════════════
# 八、质量/质心 + 动平衡 (ISO 1940-1 · 复向量法)
# ══════════════════════════════════════════════════════════════════════════════

def total_mass(mech: Mechanism) -> float:
    return sum(L.inertia.mass_kg for L in mech.links.values())


def center_of_mass_world(mech: Mechanism, poses=None) -> Vec3T:
    if poses is None:
        poses = forward_kinematics(mech)
    M = 0.0; cx = cy = cz = 0.0
    for name, L in mech.links.items():
        if L.inertia.mass_kg <= 0: continue
        T = poses.get(name, SE3.identity())
        c = T.apply_point(L.inertia.com)
        M  += L.inertia.mass_kg
        cx += L.inertia.mass_kg * c[0]
        cy += L.inertia.mass_kg * c[1]
        cz += L.inertia.mass_kg * c[2]
    if M <= 0: return (0.0, 0.0, 0.0)
    return (cx/M, cy/M, cz/M)


ISO_1940_GRADES = {
    "G0.4":0.4, "G1":1.0, "G2.5":2.5, "G6.3":6.3, "G16":16.0,
    "G40":40.0, "G100":100.0, "G250":250.0, "G630":630.0, "G1600":1600.0, "G4000":4000.0,
}


@dataclass
class BalanceReport:
    iso_grade: str
    grade_velocity_ms: float
    rotor_mass_kg: float
    omega_rad_s: float
    allowable_total_gmm: float
    allowable_per_plane_gmm: float
    n_balancing_planes: int
    scenarios: Dict[str, Dict[str, float]]
    critical_wear_pct: float
    pair_tolerance_pct: float
    issues: List[str] = field(default_factory=list)
    ok: bool = True


def analyze_balance_rotating(rotor_mass_kg: float, rpm: float,
                             hammer_mass_kg: float,
                             hammer_cm_radius_mm: float,
                             n_hammers_per_plane: int = 4,
                             n_planes: int = 4,
                             iso_grade: str = "G16",
                             wear_pct_scenario: float = 30.0) -> BalanceReport:
    """通用旋转机械动平衡 · 复向量法 · 四场景."""
    omega = rpm * 2 * math.pi / 60
    grade_v = ISO_1940_GRADES.get(iso_grade, 16.0)
    U_total = grade_v * rotor_mass_kg * 1000 / max(omega, EPS)
    U_plane = U_total / max(n_planes, 1)

    delta_m = hammer_mass_kg * (wear_pct_scenario / 100.0)
    r_cm = hammer_cm_radius_mm
    angles = [2*math.pi*i/n_hammers_per_plane for i in range(n_hammers_per_plane)]

    imb_new = abs(sum(hammer_mass_kg*1000*r_cm*cmath.exp(1j*a) for a in angles))
    imb_uniform = abs(sum(delta_m*1000*r_cm*cmath.exp(1j*a) for a in angles))
    imb_solo = delta_m * 1000 * r_cm
    imb_pair = abs(delta_m*1000*r_cm*(cmath.exp(1j*0.0) + cmath.exp(1j*math.pi)))

    delta_m_crit = U_plane / (r_cm * 1000) if r_cm > 0 else 0.0
    crit_wear_pct = delta_m_crit/hammer_mass_kg*100 if hammer_mass_kg > 0 else 0.0
    eps_max = U_plane / imb_solo if imb_solo > 0 else 0.0
    pair_tol_pct = eps_max * 100

    scenarios = {
        "new_ideal":           {"imb_gmm": round(imb_new, 2),     "ok": imb_new <= U_plane},
        "solo_worn":           {"imb_gmm": round(imb_solo, 1),    "ok": imb_solo <= U_plane},
        "pair_worn_symmetric": {"imb_gmm": round(imb_pair, 2),    "ok": imb_pair <= U_plane},
        "uniform_worn":        {"imb_gmm": round(imb_uniform, 2), "ok": imb_uniform <= U_plane},
    }

    issues: List[str] = []
    if scenarios["pair_worn_symmetric"]["ok"]:
        issues.append(f"✅ 对称成组策略 {imb_pair:.2f} g·mm << ISO {iso_grade} {U_plane:.0f} g·mm/面")
    else:
        issues.append(f"⚠ 对称成组仍超限 {imb_pair:.0f} > {U_plane:.0f} g·mm/面")
    if not scenarios["solo_worn"]["ok"]:
        ratio = imb_solo/U_plane if U_plane > 0 else math.inf
        issues.append(f"△ 独件磨损 {wear_pct_scenario:.0f}% 最坏: {imb_solo:.0f} g·mm = {ratio:.1f}× 许用")
        issues.append(f"  → 独磨阈值 {crit_wear_pct:.2f}%, 对称容限 ±{pair_tol_pct:.1f}%")

    return BalanceReport(
        iso_grade=iso_grade, grade_velocity_ms=grade_v,
        rotor_mass_kg=rotor_mass_kg, omega_rad_s=omega,
        allowable_total_gmm=round(U_total, 1),
        allowable_per_plane_gmm=round(U_plane, 1),
        n_balancing_planes=n_planes, scenarios=scenarios,
        critical_wear_pct=round(crit_wear_pct, 2),
        pair_tolerance_pct=round(pair_tol_pct, 1),
        issues=issues, ok=scenarios["pair_worn_symmetric"]["ok"],
    )


# ══════════════════════════════════════════════════════════════════════════════
# 九、临界转速 (Dunkerley) + 离心载荷
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CriticalSpeedReport:
    shaft_diameter_mm: float
    shaft_length_mm: float
    E_MPa: float
    I_mm4: float
    critical_rpm: float
    working_rpm: float
    safety_factor: float
    speed_ratio: float
    ok: bool
    issues: List[str] = field(default_factory=list)


def analyze_critical_speed_dunkerley(shaft_diameter_mm: float, shaft_length_mm: float,
                                     working_rpm: float,
                                     masses_xloc: List[Tuple[float, float]],
                                     E_MPa: float = 2.1e5,
                                     safety_min: float = 1.33) -> CriticalSpeedReport:
    """
    Dunkerley: 1/ω² = Σ 1/ω_i².  简支梁集中质量挠度法.
    k = 3EIL/(a²b²), ω² = 1000·k/m (单位从 N/mm·kg⁻¹ → rad²/s²).
    """
    I = math.pi * shaft_diameter_mm**4 / 64
    L = shaft_length_mm
    s_inv = 0.0
    for m_i, a in masses_xloc:
        b = L - a
        if a <= 0 or b <= 0 or m_i <= 0: continue
        delta_per_N = a*a*b*b / (3*E_MPa*I*L)
        k_i = 1.0/delta_per_N
        omega_ci_sq = (k_i/m_i)*1000.0
        s_inv += 1.0/omega_ci_sq
    if s_inv <= 0:
        return CriticalSpeedReport(shaft_diameter_mm, shaft_length_mm, E_MPa, I,
            math.inf, working_rpm, math.inf, 0.0, True, ["无有效集中质量"])
    omega_cr = math.sqrt(1.0/s_inv)
    n_cr = omega_cr*60/(2*math.pi)
    safety = n_cr/working_rpm if working_rpm > 0 else math.inf
    ratio = working_rpm/n_cr if n_cr > 0 else math.inf
    issues: List[str] = []
    ok = safety >= safety_min
    if safety < safety_min:
        issues.append(f"❌ 安全系数 {safety:.2f} < {safety_min} (工作 {working_rpm}, 临界 {n_cr:.0f})")
    elif 0.9 <= ratio <= 1.1:
        issues.append(f"⚠ 转速比 {ratio:.3f} 在共振区 [0.9,1.1]")
    else:
        issues.append(f"✅ 安全系数 {safety:.2f} (工作 {working_rpm}rpm, 临界 {n_cr:.0f}rpm)")
    return CriticalSpeedReport(
        shaft_diameter_mm, shaft_length_mm, E_MPa, round(I, 1),
        round(n_cr, 0), working_rpm, round(safety, 3), round(ratio, 4),
        ok, issues)


@dataclass
class CentrifugalReport:
    mass_kg: float
    radius_cm_mm: float
    omega_rad_s: float
    force_N: float
    force_kN: float
    pin_shear_mpa: Optional[float]
    allowable_shear_mpa: Optional[float]
    ok: bool
    issues: List[str] = field(default_factory=list)


def analyze_centrifugal_load(mass_kg: float, radius_cm_mm: float, rpm: float,
                             pin_diameter_mm: Optional[float] = None,
                             allowable_shear_mpa: float = 100.0) -> CentrifugalReport:
    """F_c = m ω² r.  销轴剪切 τ = F/A."""
    omega = rpm * 2 * math.pi / 60
    r_m = radius_cm_mm / 1000
    F = mass_kg * omega * omega * r_m
    tau = None; ok = True; issues: List[str] = []
    if pin_diameter_mm and pin_diameter_mm > 0:
        A = math.pi*(pin_diameter_mm/2)**2 / 1e6
        tau = F / A / 1e6
        if tau > allowable_shear_mpa:
            ok = False
            issues.append(f"❌ τ={tau:.1f} MPa > 许用 {allowable_shear_mpa}")
        elif tau > allowable_shear_mpa*0.6:
            issues.append(f"△ τ={tau:.1f} MPa 达许用 {tau/allowable_shear_mpa*100:.0f}%")
        else:
            issues.append(f"✅ τ={tau:.1f} MPa << 许用 {allowable_shear_mpa}")
    return CentrifugalReport(
        mass_kg=mass_kg, radius_cm_mm=radius_cm_mm, omega_rad_s=round(omega, 3),
        force_N=round(F, 1), force_kN=round(F/1000, 3),
        pin_shear_mpa=round(tau, 2) if tau is not None else None,
        allowable_shear_mpa=allowable_shear_mpa if tau is not None else None,
        ok=ok, issues=issues,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 十、干涉检测 · AABB 扫掠 + 径向间隙
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class InterferenceEvent:
    frame: int
    time_ms: float
    link_a: str
    link_b: str
    overlap_mm: float
    severity: str
    detail: str = ""


def detect_aabb_interference(mech: Mechanism,
                             q_trajectory: List[List[float]],
                             times_ms: Optional[List[float]] = None,
                             ignore_pairs: Optional[List[Tuple[str, str]]] = None,
                             tolerance_mm: float = 0.0) -> List[InterferenceEvent]:
    """逐帧检查所有连杆对 AABB 是否重叠."""
    ignore = set()
    if ignore_pairs:
        for a, b in ignore_pairs:
            ignore.add((a, b)); ignore.add((b, a))
    events: List[InterferenceEvent] = []
    link_names = list(mech.links.keys())
    for fi, q in enumerate(q_trajectory):
        poses = forward_kinematics(mech, q)
        wbs: Dict[str, AABB] = {}
        for name, L in mech.links.items():
            if L.aabb is None: continue
            wbs[name] = L.aabb.transformed(poses[name])
        names = [n for n in link_names if n in wbs]
        for i in range(len(names)):
            for j in range(i+1, len(names)):
                a, b = names[i], names[j]
                if (a, b) in ignore: continue
                if wbs[a].overlaps(wbs[b], tolerance_mm):
                    dx = min(wbs[a].max[0], wbs[b].max[0]) - max(wbs[a].min[0], wbs[b].min[0])
                    dy = min(wbs[a].max[1], wbs[b].max[1]) - max(wbs[a].min[1], wbs[b].min[1])
                    dz = min(wbs[a].max[2], wbs[b].max[2]) - max(wbs[a].min[2], wbs[b].min[2])
                    ov = min(dx, dy, dz)
                    sev = "HARD" if ov > 5.0 else "WARN"
                    events.append(InterferenceEvent(
                        frame=fi, time_ms=times_ms[fi] if times_ms else 0.0,
                        link_a=a, link_b=b, overlap_mm=round(ov, 2),
                        severity=sev,
                        detail=f"dx={dx:.1f} dy={dy:.1f} dz={dz:.1f}",
                    ))
    return events


def check_radial_clearance(tip_radius_mm: float, envelope_radius_mm: float,
                           name_a: str = "moving", name_b: str = "static",
                           min_clearance_mm: float = 20.0,
                           design_intent_penetration_mm: float = 0.0) -> Dict[str, Any]:
    """径向间隙: 锤尖 vs 机壳 / 筛板."""
    clearance = envelope_radius_mm - tip_radius_mm
    severity = "OK"; issues: List[str] = []
    if clearance < -design_intent_penetration_mm:
        severity = "HARD"
        issues.append(f"❌ {name_a} r={tip_radius_mm:.0f} 穿透 {name_b} {-clearance:.1f} mm")
    elif clearance < 0:
        severity = "DESIGN_INTENT" if design_intent_penetration_mm > 0 else "WARN"
        issues.append(f"★ {name_a} 穿透 {name_b} {-clearance:.1f} mm (设计意图限 ±{design_intent_penetration_mm})")
    elif clearance < min_clearance_mm:
        severity = "WARN"
        issues.append(f"⚠ 间隙 {clearance:.1f} < 最小 {min_clearance_mm} mm")
    else:
        issues.append(f"✅ 间隙 {clearance:.1f} mm 充足")
    return {"severity": severity, "clearance_mm": round(clearance, 2),
            "tip_radius_mm": tip_radius_mm, "envelope_radius_mm": envelope_radius_mm,
            "issues": issues}


# ══════════════════════════════════════════════════════════════════════════════
# 十一、时间线仿真 · 稳态旋转
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Keyframe:
    frame: int
    time_ms: float
    q: List[float]
    link_positions: Dict[str, Vec3T]
    key_points: Dict[str, Dict[str, Vec3T]]


@dataclass
class SimulationReport:
    n_frames: int
    period_ms: float
    keyframes: List[Keyframe]
    interference_events: List[InterferenceEvent]
    swept_aabb: AABB
    summary: Dict[str, Any] = field(default_factory=dict)


def simulate_cyclic_rotation(mech: Mechanism, driving_joint: str, rpm: float,
                             n_frames: int = 24,
                             interference_tolerance_mm: float = 0.0,
                             ignore_pairs: Optional[List[Tuple[str, str]]] = None) -> SimulationReport:
    """稳态旋转仿真: driving_joint 扫 360°, 其余关节保持."""
    j = mech.joint_by_name(driving_joint)
    if j.joint_type != "revolute":
        raise ValueError(f"driving_joint '{driving_joint}' is not revolute")
    period_ms = 1000.0 / (rpm/60)
    q_base = mech.get_q()
    # 找 driving_joint 在 flat q 中的索引
    idx = 0; found = -1
    for mj in mech.movable_joints():
        if mj.name == driving_joint:
            found = idx; break
        idx += mj.dof()
    if found < 0:
        raise ValueError("driving_joint not in movable joints")

    keyframes: List[Keyframe] = []
    q_traj: List[List[float]] = []; times: List[float] = []
    swept_min = [math.inf]*3; swept_max = [-math.inf]*3

    for fi in range(n_frames):
        angle = 2 * math.pi * fi / n_frames
        t_ms = period_ms * fi / n_frames
        qf = list(q_base); qf[found] = angle
        q_traj.append(qf); times.append(t_ms)
        poses = forward_kinematics(mech, qf)
        link_pos: Dict[str, Vec3T] = {}
        kp_out: Dict[str, Dict[str, Vec3T]] = {}
        for name, L in mech.links.items():
            T = poses[name]
            link_pos[name] = tuple(round(x, 3) for x in T.apply_point(L.inertia.com))  # type: ignore
            if L.key_points:
                kp_out[name] = {kn: tuple(round(x, 3) for x in T.apply_point(kp))  # type: ignore
                                for kn, kp in L.key_points.items()}
            if L.aabb is not None:
                bb = L.aabb.transformed(T)
                for i in range(3):
                    swept_min[i] = min(swept_min[i], bb.min[i])
                    swept_max[i] = max(swept_max[i], bb.max[i])
        keyframes.append(Keyframe(fi, round(t_ms, 3), qf, link_pos, kp_out))

    mech.set_q(q_base)
    events = detect_aabb_interference(mech, q_traj, times, ignore_pairs, interference_tolerance_mm)
    swept = AABB(tuple(swept_min), tuple(swept_max)) if not math.isinf(swept_min[0]) else AABB()  # type: ignore
    severe = [e for e in events if e.severity == "HARD"]
    summary = {
        "driving_joint": driving_joint, "rpm": rpm,
        "total_dof": mech.total_dof(), "n_links": len(mech.links),
        "n_interference_events": len(events),
        "n_severe_events": len(severe),
        "swept_size_mm": ([round(x, 2) for x in (swept_max[0]-swept_min[0],
                                                  swept_max[1]-swept_min[1],
                                                  swept_max[2]-swept_min[2])]
                          if not math.isinf(swept_min[0]) else [0, 0, 0]),
    }
    return SimulationReport(n_frames, round(period_ms, 3), keyframes, events, swept, summary)


# ══════════════════════════════════════════════════════════════════════════════
# 十二、机构构造 · dict ↔ Mechanism
# ══════════════════════════════════════════════════════════════════════════════

def build_mechanism_from_spec(spec: Dict[str, Any]) -> Mechanism:
    """
    spec 格式 (见 mechanism_to_spec 逆操作):
      {name, root_link, links: [{name, mass_kg, com, aabb_min, aabb_max, key_points, ...}],
       joints: [{name, type, parent, child, origin_xyz, origin_rpy, axis, axis2, pitch, limits, q}]}
    """
    mech = Mechanism(name=spec.get("name", "mechanism"),
                     root_link=spec.get("root_link", "ground"))
    for ld in spec.get("links", []):
        inertia = InertiaProperties(
            mass_kg=ld.get("mass_kg", 0.0),
            com=tuple(ld.get("com", [0, 0, 0])),  # type: ignore
            ixx=ld.get("ixx", 0.0), iyy=ld.get("iyy", 0.0), izz=ld.get("izz", 0.0),
        )
        aabb = None
        if "aabb_min" in ld and "aabb_max" in ld:
            aabb = AABB(tuple(ld["aabb_min"]), tuple(ld["aabb_max"]))  # type: ignore
        mech.add_link(Link(
            name=ld["name"], inertia=inertia, aabb=aabb,
            key_points={k: tuple(v) for k, v in ld.get("key_points", {}).items()},  # type: ignore
            envelope_cylinder=tuple(ld["envelope_cylinder"]) if "envelope_cylinder" in ld else None,  # type: ignore
        ))
    for jd in spec.get("joints", []):
        oxyz = tuple(jd.get("origin_xyz", [0, 0, 0]))
        orpy = tuple(jd.get("origin_rpy", [0, 0, 0]))
        origin = SE3.from_rpy(*orpy, translation=oxyz)  # type: ignore
        lim = jd.get("limits", {}) or {}
        limits = JointLimits(lower=lim.get("lower"), upper=lim.get("upper"),
                             velocity=lim.get("velocity"), effort=lim.get("effort"))
        mech.add_joint(Joint(
            name=jd["name"], joint_type=jd["type"],
            parent=jd["parent"], child=jd["child"],
            origin=origin,
            axis=tuple(jd.get("axis", [0, 0, 1])),  # type: ignore
            axis2=tuple(jd.get("axis2", [1, 0, 0])),  # type: ignore
            pitch=jd.get("pitch", 0.0),
            limits=limits, q=list(jd.get("q", [])),
        ))
    return mech


def mechanism_to_spec(mech: Mechanism) -> Dict[str, Any]:
    spec: Dict[str, Any] = {"name": mech.name, "root_link": mech.root_link,
                             "links": [], "joints": []}
    for L in mech.links.values():
        ld: Dict[str, Any] = {
            "name": L.name, "mass_kg": L.inertia.mass_kg,
            "com": list(L.inertia.com),
            "ixx": L.inertia.ixx, "iyy": L.inertia.iyy, "izz": L.inertia.izz,
        }
        if L.aabb is not None:
            ld["aabb_min"] = list(L.aabb.min); ld["aabb_max"] = list(L.aabb.max)
        if L.key_points:
            ld["key_points"] = {k: list(v) for k, v in L.key_points.items()}
        if L.envelope_cylinder is not None:
            ld["envelope_cylinder"] = list(L.envelope_cylinder)
        spec["links"].append(ld)
    for j in mech.joints:
        spec["joints"].append({
            "name": j.name, "type": j.joint_type,
            "parent": j.parent, "child": j.child,
            "origin_xyz": list(j.origin.t),
            "axis": list(j.axis), "axis2": list(j.axis2), "pitch": j.pitch,
            "limits": {"lower": j.limits.lower, "upper": j.limits.upper,
                       "velocity": j.limits.velocity, "effort": j.limits.effort},
            "q": list(j.q),
        })
    return spec


# ══════════════════════════════════════════════════════════════════════════════
# 十三、工作空间分析
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class WorkspaceReport:
    n_samples: int
    reachable_aabb: AABB
    centroid: Vec3T
    volume_mm3: float
    singularity_ratio: float
    issues: List[str] = field(default_factory=list)


def _default_limits(j: Joint) -> Tuple[float, float]:
    if j.limits.lower is not None and j.limits.upper is not None:
        return (j.limits.lower, j.limits.upper)
    if j.joint_type in ("revolute", "helical", "spherical", "universal", "cylindrical"):
        return (-math.pi, math.pi)
    if j.joint_type == "prismatic":
        return (0.0, 1000.0)
    if j.joint_type == "planar":
        return (-500.0, 500.0)
    return (-1.0, 1.0)


def _is_singular(J: List[List[float]], threshold: float = 1e-4) -> bool:
    N = len(J[0]) if J else 0
    if N == 0: return True
    JJt = [[sum(J[i][k]*J[j][k] for k in range(N)) for j in range(3)] for i in range(3)]
    a,b,c = JJt[0]; d,e,f = JJt[1]; g,h,i = JJt[2]
    det = a*(e*i-f*h) - b*(d*i-f*g) + c*(d*h-e*g)
    return abs(det) < threshold


def analyze_workspace(mech: Mechanism, target_link: str,
                      target_point_local: Vec3T = (0.0, 0.0, 0.0),
                      n_samples: int = 200,
                      seed: int = 0xDA0) -> WorkspaceReport:
    """随机采样关节空间, 统计可达工作空间."""
    import random
    rng = random.Random(seed)
    xs, ys, zs = [], [], []; singular = 0
    for _ in range(n_samples):
        q: List[float] = []
        for j in mech.movable_joints():
            lo, hi = _default_limits(j)
            for _k in range(j.dof()):
                q.append(rng.uniform(lo, hi))
        p = forward_kinematics(mech, q)[target_link].apply_point(target_point_local)
        xs.append(p[0]); ys.append(p[1]); zs.append(p[2])
        J = numerical_jacobian(mech, target_link, target_point_local)
        if _is_singular(J): singular += 1
    bb = AABB((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))
    size = bb.size()
    issues: List[str] = []
    sing_ratio = singular / max(1, n_samples)
    if sing_ratio > 0.10:
        issues.append(f"奇异采样比例 {sing_ratio*100:.1f}% — 机构大范围接近奇异")
    if size[0]*size[1]*size[2] < 1.0:
        issues.append("工作空间体积≈0 — 机构实际无可动")
    return WorkspaceReport(
        n_samples=n_samples, reachable_aabb=bb,
        centroid=(sum(xs)/n_samples, sum(ys)/n_samples, sum(zs)/n_samples),
        volume_mm3=size[0]*size[1]*size[2],
        singularity_ratio=sing_ratio, issues=issues,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 十四、顶层分析 · 聚合全部引擎
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class AnalysisReport:
    mechanism: str
    timestamp: str
    total_dof: int
    total_mass_kg: float
    fk_poses: Dict[str, SE3]
    simulation: Optional[SimulationReport] = None
    balance: Optional[BalanceReport] = None
    critical_speed: Optional[CriticalSpeedReport] = None
    centrifugal: Optional[CentrifugalReport] = None
    workspace: Optional[WorkspaceReport] = None
    issues: List[str] = field(default_factory=list)
    ok: bool = True
    score: int = 100

    def to_dict(self) -> Dict[str, Any]:
        def ser(x):
            if isinstance(x, SE3): return {"t": list(x.t), "R": x.R}
            if isinstance(x, AABB): return {"min": list(x.min), "max": list(x.max)}
            if hasattr(x, "__dataclass_fields__"):
                return {k: ser(v) for k, v in asdict(x).items()}
            if isinstance(x, dict):
                return {k: ser(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [ser(v) for v in x]
            return x
        return {
            "schema": "dao_kinematics/analysis/v1",
            "mechanism": self.mechanism, "timestamp": self.timestamp,
            "total_dof": self.total_dof, "total_mass_kg": self.total_mass_kg,
            "fk_poses": {k: {"t": list(v.t), "R": v.R} for k, v in self.fk_poses.items()},
            "simulation": ser(self.simulation) if self.simulation else None,
            "balance": ser(self.balance) if self.balance else None,
            "critical_speed": ser(self.critical_speed) if self.critical_speed else None,
            "centrifugal": ser(self.centrifugal) if self.centrifugal else None,
            "workspace": ser(self.workspace) if self.workspace else None,
            "issues": self.issues, "ok": self.ok, "score": self.score,
        }


def run_full_analysis(mech: Mechanism,
                      operating: Optional[Dict[str, Any]] = None) -> AnalysisReport:
    """一站式分析. operating 字段详见代码."""
    from datetime import datetime
    op = operating or {}

    poses = forward_kinematics(mech)
    total_m = total_mass(mech)

    sim = None
    if op.get("driving_joint") and op.get("rpm"):
        sim = simulate_cyclic_rotation(
            mech, driving_joint=op["driving_joint"], rpm=op["rpm"],
            n_frames=op.get("n_frames", 24),
            interference_tolerance_mm=op.get("interference_tolerance_mm", 0.0),
            ignore_pairs=op.get("ignore_pairs"),
        )

    bal = None
    if all(k in op for k in ("balance_rotor_mass_kg", "balance_hammer_mass_kg",
                              "balance_hammer_cm_radius_mm", "rpm")):
        bal = analyze_balance_rotating(
            rotor_mass_kg=op["balance_rotor_mass_kg"], rpm=op["rpm"],
            hammer_mass_kg=op["balance_hammer_mass_kg"],
            hammer_cm_radius_mm=op["balance_hammer_cm_radius_mm"],
            n_hammers_per_plane=op.get("balance_n_per_plane", 4),
            n_planes=op.get("balance_n_planes", 4),
            iso_grade=op.get("balance_iso_grade", "G16"),
            wear_pct_scenario=op.get("balance_wear_pct", 30.0),
        )

    cs = None
    if all(k in op for k in ("shaft_diameter_mm", "shaft_length_mm",
                              "shaft_masses_xloc", "rpm")):
        cs = analyze_critical_speed_dunkerley(
            shaft_diameter_mm=op["shaft_diameter_mm"],
            shaft_length_mm=op["shaft_length_mm"],
            working_rpm=op["rpm"], masses_xloc=op["shaft_masses_xloc"],
            E_MPa=op.get("shaft_E_MPa", 2.1e5),
            safety_min=op.get("critical_speed_safety_min", 1.33),
        )

    cf = None
    if all(k in op for k in ("centrifugal_mass_kg", "centrifugal_radius_mm", "rpm")):
        cf = analyze_centrifugal_load(
            mass_kg=op["centrifugal_mass_kg"],
            radius_cm_mm=op["centrifugal_radius_mm"], rpm=op["rpm"],
            pin_diameter_mm=op.get("centrifugal_pin_d_mm"),
            allowable_shear_mpa=op.get("centrifugal_allowable_shear_mpa", 100.0),
        )

    ws = None
    if op.get("workspace_target_link"):
        ws = analyze_workspace(
            mech, target_link=op["workspace_target_link"],
            target_point_local=tuple(op.get("workspace_target_point_local", [0, 0, 0])),  # type: ignore
            n_samples=op.get("workspace_samples", 200),
        )

    defects: List[str] = []; issues: List[str] = []
    if sim and sim.summary.get("n_severe_events", 0) > 0:
        defects.append(f"运动仿真检测到 {sim.summary['n_severe_events']} 次硬干涉")
    if cs and not cs.ok: defects.extend(cs.issues)
    if cf and not cf.ok: defects.extend(cf.issues)
    if bal and not bal.ok: issues.extend(bal.issues)
    if ws: issues.extend(ws.issues)

    score = max(0, 100 - len(defects)*20 - len(issues)*5)
    return AnalysisReport(
        mechanism=mech.name,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        total_dof=mech.total_dof(), total_mass_kg=round(total_m, 3),
        fk_poses=poses, simulation=sim, balance=bal,
        critical_speed=cs, centrifugal=cf, workspace=ws,
        issues=defects + issues, ok=(len(defects) == 0), score=score,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 十五、自检入口
# ══════════════════════════════════════════════════════════════════════════════

def _selftest() -> int:
    """自检: 关节原语 + FK + IK + 平衡 + 临界转速 + 仿真."""
    rc = 0

    # 1) SE3 恒等
    T = SE3.identity()
    assert T.apply_point((1.0, 2.0, 3.0)) == (1.0, 2.0, 3.0), "SE3 identity失败"

    # 2) Rodrigues 绕 Z 转 90° 把 (1,0,0) → (0,1,0)
    T = SE3.from_axis_angle((0, 0, 1), math.pi/2)
    p = T.apply_point((1.0, 0.0, 0.0))
    assert abs(p[0]) < 1e-9 and abs(p[1] - 1.0) < 1e-9, f"Rodrigues 错: {p}"
    print(f"  ✅ SE3 / Rodrigues 正确: (1,0,0) → ({p[0]:.3e},{p[1]:.3f},{p[2]:.3e})")

    # 3) 2R 机械臂 FK
    mech = Mechanism(name="2R_arm", root_link="base")
    mech.add_link(Link("base"))
    mech.add_link(Link("link1", key_points={"tip": (300.0, 0.0, 0.0)}))
    mech.add_link(Link("link2", key_points={"tip": (300.0, 0.0, 0.0)}))
    mech.add_joint(Joint("j1", "revolute", "base", "link1", axis=(0, 0, 1)))
    mech.add_joint(Joint("j2", "revolute", "link1", "link2",
                         origin=SE3.from_translation((300.0, 0.0, 0.0)),
                         axis=(0, 0, 1)))
    # 关节 (0, 0) → tip 应在 (600, 0, 0)
    mech.set_q([0.0, 0.0])
    tip = get_link_point_world(mech, "link2", (300.0, 0.0, 0.0))
    assert abs(tip[0] - 600.0) < 1e-9 and abs(tip[1]) < 1e-9, f"FK 零位错: {tip}"
    print(f"  ✅ 2R FK zero config: tip = ({tip[0]:.1f}, {tip[1]:.1f}, {tip[2]:.1f})")

    # 关节 (π/2, 0) → tip (0, 600)
    mech.set_q([math.pi/2, 0.0])
    tip = get_link_point_world(mech, "link2", (300.0, 0.0, 0.0))
    assert abs(tip[0]) < 1e-6 and abs(tip[1] - 600.0) < 1e-6, f"FK 90° 错: {tip}"
    print(f"  ✅ 2R FK q=(π/2, 0): tip = ({tip[0]:.3e}, {tip[1]:.1f}, {tip[2]:.3e})")

    # 4) IK 解: 目标 (400, 200)
    result = inverse_kinematics(mech, "link2", (400.0, 200.0, 0.0),
                                point_in_link_local=(300.0, 0.0, 0.0),
                                q_init=[0.1, 0.1], max_iter=100, tolerance=1e-3)
    assert result.success, f"IK 失败: err={result.position_error:.3f}"
    print(f"  ✅ 2R IK (400,200): err={result.position_error:.4f}mm in {result.iterations} iter")

    # 5) 平衡分析 · 锤式破碎机工况复现 (转子 150 kg, 锤 4.5 kg, 1200rpm)
    bal = analyze_balance_rotating(
        rotor_mass_kg=150, rpm=1200, hammer_mass_kg=4.5,
        hammer_cm_radius_mm=310, n_hammers_per_plane=4, n_planes=4,
        iso_grade="G16", wear_pct_scenario=30,
    )
    assert bal.scenarios["pair_worn_symmetric"]["ok"], "对称成组应通过"
    print(f"  ✅ Balance 四场景: solo={bal.scenarios['solo_worn']['imb_gmm']:.0f} "
          f"pair={bal.scenarios['pair_worn_symmetric']['imb_gmm']:.2f} "
          f"U_plane={bal.allowable_per_plane_gmm:.0f} g·mm")

    # 6) 临界转速 · 简支梁 Ø90 × 1145 mm + 4 × (40 kg @ 207/408/610/810)
    cs = analyze_critical_speed_dunkerley(
        shaft_diameter_mm=90, shaft_length_mm=1145, working_rpm=1200,
        masses_xloc=[(40, 207), (40, 408), (40, 610), (40, 810), (40, 960)],
    )
    assert cs.critical_rpm > 1200 * 1.33, f"临界转速 {cs.critical_rpm} 太低"
    print(f"  ✅ Critical speed: n_cr={cs.critical_rpm:.0f}rpm (安全 {cs.safety_factor:.2f}×)")

    # 7) 仿真: 2R 机械臂 j1 稳态旋转 60 rpm, 24 帧
    mech.set_q([0.0, math.pi/4])
    sim = simulate_cyclic_rotation(mech, driving_joint="j1", rpm=60, n_frames=24)
    assert sim.n_frames == 24, "帧数错"
    print(f"  ✅ Simulation: {sim.n_frames} frames · swept AABB size = {sim.summary['swept_size_mm']}")

    # 8) JSON 往返
    spec = mechanism_to_spec(mech)
    mech2 = build_mechanism_from_spec(spec)
    assert mech2.total_dof() == mech.total_dof(), "往返 DOF 不一致"
    print(f"  ✅ JSON spec roundtrip OK · dof={mech2.total_dof()}")

    print(f"\n  dao_kinematics v{__version__} 自检通过.")
    return rc


__all__ = [
    "SE3", "Mat3T", "Mat4T", "Vec3T", "EPS",
    "v3", "v_add", "v_sub", "v_scale", "v_dot", "v_cross", "v_len", "v_dist", "v_norm",
    "mat3_identity", "mat3_mul", "mat3_vec", "mat3_transpose",
    "rodrigues", "rot_x", "rot_y", "rot_z",
    "JointLimits", "Joint", "VALID_JOINT_TYPES",
    "InertiaProperties", "AABB", "Link", "Mechanism",
    "forward_kinematics", "get_link_point_world",
    "numerical_jacobian", "IKResult", "inverse_kinematics",
    "total_mass", "center_of_mass_world",
    "ISO_1940_GRADES", "BalanceReport", "analyze_balance_rotating",
    "CriticalSpeedReport", "analyze_critical_speed_dunkerley",
    "CentrifugalReport", "analyze_centrifugal_load",
    "InterferenceEvent", "detect_aabb_interference", "check_radial_clearance",
    "Keyframe", "SimulationReport", "simulate_cyclic_rotation",
    "WorkspaceReport", "analyze_workspace",
    "AnalysisReport", "run_full_analysis",
    "build_mechanism_from_spec", "mechanism_to_spec",
]


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"dao_kinematics v{__version__} · 通用运动学底层 · 自检开始\n")
    try:
        rc = _selftest()
    except AssertionError as e:
        print(f"\n  ❌ 自检失败: {e}")
        rc = 1
    sys.exit(rc)
