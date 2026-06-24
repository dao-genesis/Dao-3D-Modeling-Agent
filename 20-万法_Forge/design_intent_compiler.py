#!/usr/bin/env python3
"""
道 · 意图编译器 — Design Intent Compiler v1.0
================================================
反者道之动 — 从人类三维认知的逆向出发，构建Agent的空间理解内核。

人类在画第一条线之前，已经完成了：
  1. 功能分解 — 这个物体要做什么？
  2. 结构映射 — 什么几何结构能实现这个功能？
  3. 约束推导 — 各部分之间有什么关系？
  4. 参数锁定 — 关键尺寸是什么？
  5. 失败预测 — 什么操作可能出错？

本模块让Agent具备同样的能力。

架构位置:
  用户意念 → [DesignIntentCompiler] → DesignTree → [ParametricCodegen] → Code → [DaoEngine] → Output

Usage:
    from design_intent_compiler import DesignIntentCompiler, DesignTree

    compiler = DesignIntentCompiler()

    # 1. 从结构化描述编译
    tree = compiler.compile({
        "name": "phone_stand",
        "function": "支撑手机在桌面上，可调角度",
        "parts": [
            {"name": "base", "function": "support", "dims": {"L": 80, "W": 60, "H": 5}},
            {"name": "cradle", "function": "contain", "dims": {"W": 75, "slot_d": 12, "H": 40}},
            {"name": "hinge", "function": "hinge", "dims": {"pin_r": 2, "clearance": 0.3}},
        ],
        "process": "fdm",
    })

    # 2. 预检
    report = compiler.preflight(tree)

    # 3. 生成构建计划
    plan = compiler.plan(tree)
"""

import json
import math
import copy
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple, Union
from enum import Enum, auto
from pathlib import Path

__version__ = "1.0.0"
__all__ = [
    "DesignIntentCompiler", "DesignTree", "PartNode", "FeatureNode",
    "ConstraintSet", "BuildPlan", "PreflightReport",
    "Function", "FeatureType", "JoinMethod", "Process",
]

# ═══════════════════════════════════════════════════════════════════════════
# 一、人类三维认知的形式化 — 枚举与数据结构
# ═══════════════════════════════════════════════════════════════════════════

class Function(Enum):
    """物体的原始功能 — 人看到物体即知用途 (Gibson affordance)"""
    CONTAIN    = "contain"     # 容纳: 壳体, 杯子, 盒子
    SUPPORT    = "support"     # 支撑: 底板, 立柱, 肋
    FASTEN     = "fasten"      # 连接: 螺丝孔, 卡扣, 焊接面
    GUIDE      = "guide"       # 导向: 槽, 导轨
    SEAL       = "seal"        # 密封: O型圈槽, 唇边
    VENTILATE  = "ventilate"   # 散热: 栅格, 百叶窗
    HINGE      = "hinge"       # 铰接: 活页, 旋转轴
    FLEX       = "flex"        # 弹性: 薄臂, 蛇形弹簧
    STACK      = "stack"       # 堆叠: 凸台+凹槽
    DISPLAY    = "display"     # 展示: 倾斜面+槽
    TRANSMIT   = "transmit"    # 传动: 齿轮, 带轮, 链轮
    SHIELD     = "shield"      # 防护: 罩壳, 挡板
    MOUNT      = "mount"       # 安装: 法兰, 支架
    FLOW       = "flow"        # 流体: 管道, 通道
    STRUCTURAL = "structural"  # 结构: 梁, 板, 桁架
    CUSTOM     = "custom"      # 自定义


class FeatureType(Enum):
    """几何特征的原子类型 — 一切复杂形状由这些特征组合而成"""
    # 基础体
    BODY_BOX       = "body_box"
    BODY_CYLINDER  = "body_cylinder"
    BODY_SPHERE    = "body_sphere"
    BODY_CONE      = "body_cone"
    BODY_TORUS     = "body_torus"
    BODY_PRISM     = "body_prism"
    # 特征操作
    PAD            = "pad"             # Sketch → 拉伸
    POCKET         = "pocket"          # Sketch → 挖槽
    HOLE           = "hole"            # 参数化孔 (通孔/盲孔/沉头/锥孔)
    FILLET         = "fillet"          # 圆角
    CHAMFER        = "chamfer"         # 倒角
    SHELL          = "shell"           # 抽壳
    PATTERN_LINEAR = "pattern_linear"  # 线性阵列
    PATTERN_POLAR  = "pattern_polar"   # 极坐标阵列
    MIRROR         = "mirror"          # 镜像
    # 高级
    LOFT           = "loft"            # 放样
    SWEEP          = "sweep"           # 扫掠
    REVOLVE        = "revolve"         # 旋转体
    RIB            = "rib"             # 加强筋
    DRAFT          = "draft"           # 拔模斜度
    THREAD         = "thread"          # 螺纹
    BOSS           = "boss"            # 凸台
    GROOVE         = "groove"          # 槽
    # 导入
    IMPORT_STL     = "import_stl"
    IMPORT_STEP    = "import_step"
    # 自定义
    CUSTOM_SKETCH  = "custom_sketch"   # 自由草图+拉伸


class JoinMethod(Enum):
    """零件间连接方式"""
    FUSE       = "fuse"       # 布尔融合 (一体化)
    SCREW      = "screw"      # 螺丝连接
    SNAP       = "snap"       # 卡扣
    PRESS_FIT  = "press_fit"  # 过盈配合
    GLUE       = "glue"       # 胶粘
    WELD       = "weld"       # 焊接
    HINGE_PIN  = "hinge_pin"  # 铰链销
    SLIDE      = "slide"      # 滑动配合
    NONE       = "none"       # 独立件


class Process(Enum):
    """制造工艺"""
    FDM        = "fdm"
    SLA        = "sla"
    CNC        = "cnc"
    INJECTION  = "injection"
    LASER_CUT  = "laser_cut"
    SHEET_METAL = "sheet_metal"
    GENERIC    = "generic"


# ── 制造约束数据库 ─────────────────────────────────────────────────────
PROCESS_LIMITS = {
    Process.FDM: {
        "min_wall": 1.2, "rec_wall": 1.5, "min_hole": 1.5,
        "max_overhang_deg": 45, "max_bridge_mm": 10,
        "xy_tol": 0.2, "z_tol": 0.1,
        "clearance": 0.3, "press_fit": 0.1,
    },
    Process.SLA: {
        "min_wall": 0.5, "rec_wall": 0.8, "min_hole": 0.5,
        "max_overhang_deg": 30, "max_bridge_mm": 5,
        "xy_tol": 0.05, "z_tol": 0.025,
        "clearance": 0.15, "press_fit": 0.05,
    },
    Process.CNC: {
        "min_wall": 1.0, "rec_wall": 1.5, "min_hole": 1.0,
        "max_overhang_deg": 90, "max_bridge_mm": 999,
        "xy_tol": 0.02, "z_tol": 0.02,
        "clearance": 0.1, "press_fit": 0.02,
    },
    Process.GENERIC: {
        "min_wall": 1.0, "rec_wall": 2.0, "min_hole": 1.0,
        "max_overhang_deg": 90, "max_bridge_mm": 999,
        "xy_tol": 0.1, "z_tol": 0.1,
        "clearance": 0.2, "press_fit": 0.05,
    },
}

# ── 功能 → 结构模式映射 (Gibson affordance → geometry) ──────────────
FUNCTION_TO_STRUCTURE = {
    Function.CONTAIN: {
        "pattern": "shell(outer - inner)",
        "required_params": ["outer_dims", "wall_thickness"],
        "features": [FeatureType.BODY_BOX, FeatureType.SHELL],
        "constraints": ["wall >= min_wall", "inner = outer - 2*wall"],
    },
    Function.SUPPORT: {
        "pattern": "base_plate + optional(ribs | columns)",
        "required_params": ["base_dims", "load_height"],
        "features": [FeatureType.PAD, FeatureType.RIB],
        "constraints": ["base_area >= load_footprint * 1.5"],
    },
    Function.FASTEN: {
        "pattern": "boss + hole(clearance | selftap | insert)",
        "required_params": ["screw_size", "depth"],
        "features": [FeatureType.BOSS, FeatureType.HOLE],
        "constraints": ["boss_wall >= screw_d", "hole_d = clearance[screw_size]"],
    },
    Function.GUIDE: {
        "pattern": "slot(width = rail_w + clearance)",
        "required_params": ["rail_width", "length"],
        "features": [FeatureType.GROOVE],
        "constraints": ["slot_w = rail_w + 2*clearance"],
    },
    Function.SEAL: {
        "pattern": "groove(w=cord_d*1.4, d=cord_d*0.7)",
        "required_params": ["cord_diameter"],
        "features": [FeatureType.GROOVE],
        "constraints": ["groove_w = cord_d * 1.4", "groove_d = cord_d * 0.7"],
    },
    Function.HINGE: {
        "pattern": "barrel + pin_hole + clearance",
        "required_params": ["pin_r", "arm_length"],
        "features": [FeatureType.BODY_CYLINDER, FeatureType.HOLE],
        "constraints": ["clearance >= process.clearance"],
    },
    Function.TRANSMIT: {
        "pattern": "gear(involute) | pulley | sprocket",
        "required_params": ["teeth", "module"],
        "features": [FeatureType.REVOLVE, FeatureType.PATTERN_POLAR],
        "constraints": ["pitch_r = module * teeth / 2"],
    },
    Function.MOUNT: {
        "pattern": "flange + bolt_holes",
        "required_params": ["bolt_pattern", "interface_size"],
        "features": [FeatureType.PAD, FeatureType.HOLE, FeatureType.PATTERN_POLAR],
        "constraints": ["bolt_edge_dist >= 2 * bolt_d"],
    },
    Function.FLOW: {
        "pattern": "pipe(path, inner_r, wall)",
        "required_params": ["path", "inner_d", "wall"],
        "features": [FeatureType.SWEEP],
        "constraints": ["wall >= min_wall", "bend_r >= 2 * outer_d"],
    },
    Function.SHIELD: {
        "pattern": "shell(outer) + ventilation(optional)",
        "required_params": ["coverage_dims"],
        "features": [FeatureType.SHELL, FeatureType.PATTERN_LINEAR],
        "constraints": ["wall >= min_wall"],
    },
    Function.STRUCTURAL: {
        "pattern": "profile(I|C|L|T) extruded along length",
        "required_params": ["profile_type", "length"],
        "features": [FeatureType.PAD],
        "constraints": ["section_modulus >= required"],
    },
}

# ── 标准公制螺丝参数 ───────────────────────────────────────────────
METRIC_SCREWS = {
    "M2":   {"d": 2.0, "clearance": 2.4, "selftap_fdm": 1.7, "head_d": 4.0,  "head_h": 2.0,  "nut_h": 1.6},
    "M2.5": {"d": 2.5, "clearance": 2.9, "selftap_fdm": 2.2, "head_d": 5.0,  "head_h": 2.5,  "nut_h": 2.0},
    "M3":   {"d": 3.0, "clearance": 3.4, "selftap_fdm": 2.7, "head_d": 6.0,  "head_h": 3.0,  "nut_h": 2.4},
    "M4":   {"d": 4.0, "clearance": 4.5, "selftap_fdm": 3.5, "head_d": 8.0,  "head_h": 4.0,  "nut_h": 3.2},
    "M5":   {"d": 5.0, "clearance": 5.5, "selftap_fdm": 4.5, "head_d": 10.0, "head_h": 5.0,  "nut_h": 4.0},
    "M6":   {"d": 6.0, "clearance": 6.6, "selftap_fdm": 5.3, "head_d": 12.0, "head_h": 6.0,  "nut_h": 5.0},
    "M8":   {"d": 8.0, "clearance": 9.0, "selftap_fdm": 7.0, "head_d": 16.0, "head_h": 8.0,  "nut_h": 6.5},
    "M10":  {"d":10.0, "clearance":11.0, "selftap_fdm": 9.0, "head_d": 20.0, "head_h":10.0,  "nut_h": 8.0},
}


# ═══════════════════════════════════════════════════════════════════════════
# 二、设计树 — Agent 的内部三维表征 (Shepard mental rotation substrate)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Constraint:
    """设计约束 — 零件/特征间的关系"""
    type: str          # "dimension", "coincident", "parallel", "distance", "angle", "symmetric"
    targets: list      # 涉及的零件/特征名称
    value: Any = None  # 约束值
    expr: str = ""     # 参数化表达式, e.g. "wall*2"
    note: str = ""


@dataclass
class FeatureNode:
    """特征节点 — 单个建模特征"""
    name: str
    type: FeatureType
    params: Dict[str, Any] = field(default_factory=dict)
    sketch: Optional[Dict] = None       # Sketch定义 (2D profiles)
    constraints: List[Constraint] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)  # 依赖的特征名
    order: int = 0
    note: str = ""

    def to_dict(self):
        d = asdict(self)
        d["type"] = self.type.value
        return d


@dataclass
class PartNode:
    """零件节点 — 一个独立零件"""
    name: str
    function: Function = Function.CUSTOM
    dims: Dict[str, float] = field(default_factory=dict)
    features: List[FeatureNode] = field(default_factory=list)
    material: str = "pla"
    color: Tuple[float, float, float] = (0.7, 0.7, 0.7)
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    note: str = ""

    def to_dict(self):
        d = asdict(self)
        d["function"] = self.function.value
        d["features"] = [f.to_dict() for f in self.features]
        return d


@dataclass
class JoinNode:
    """连接节点 — 两个零件的连接关系"""
    part_a: str
    part_b: str
    method: JoinMethod = JoinMethod.NONE
    params: Dict[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass
class DesignTree:
    """
    设计树 — 完整的设计意图表达。
    这是Agent的内部三维表征，等价于人类工程师脑中的设计构想。
    """
    name: str
    description: str = ""
    process: Process = Process.FDM
    parts: List[PartNode] = field(default_factory=list)
    joins: List[JoinNode] = field(default_factory=list)
    global_params: Dict[str, Any] = field(default_factory=dict)
    constraints: List[Constraint] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "process": self.process.value,
            "parts": [p.to_dict() for p in self.parts],
            "joins": [{**asdict(j), "method": j.method.value} for j in self.joins],
            "global_params": self.global_params,
            "constraints": [asdict(c) for c in self.constraints],
            "metadata": self.metadata,
        }

    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, d):
        """从字典重建DesignTree"""
        tree = cls(
            name=d.get("name", "unnamed"),
            description=d.get("description", ""),
            process=Process(d.get("process", "generic")),
            global_params=d.get("global_params", {}),
            metadata=d.get("metadata", {}),
        )
        for pd in d.get("parts", []):
            features = []
            for fd in pd.get("features", []):
                fn = FeatureNode(
                    name=fd["name"],
                    type=FeatureType(fd["type"]),
                    params=fd.get("params", {}),
                    sketch=fd.get("sketch"),
                    depends_on=fd.get("depends_on", []),
                    order=fd.get("order", 0),
                    note=fd.get("note", ""),
                )
                features.append(fn)
            part = PartNode(
                name=pd["name"],
                function=Function(pd.get("function", "custom")),
                dims=pd.get("dims", {}),
                features=features,
                material=pd.get("material", "pla"),
                color=tuple(pd.get("color", (0.7, 0.7, 0.7))),
                origin=tuple(pd.get("origin", (0, 0, 0))),
                note=pd.get("note", ""),
            )
            tree.parts.append(part)
        for jd in d.get("joins", []):
            tree.joins.append(JoinNode(
                part_a=jd["part_a"], part_b=jd["part_b"],
                method=JoinMethod(jd.get("method", "none")),
                params=jd.get("params", {}),
            ))
        for cd in d.get("constraints", []):
            tree.constraints.append(Constraint(
                type=cd["type"], targets=cd["targets"],
                value=cd.get("value"), expr=cd.get("expr", ""),
                note=cd.get("note", ""),
            ))
        return tree

    def part(self, name) -> Optional[PartNode]:
        for p in self.parts:
            if p.name == name:
                return p
        return None


# ═══════════════════════════════════════════════════════════════════════════
# 三、预检引擎 — 在写代码前预测失败 (Marr 2.5D sketch验证)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Issue:
    severity: str   # "error", "warning", "info"
    part: str       # 零件名
    feature: str    # 特征名 (可空)
    message: str
    suggestion: str = ""


@dataclass
class PreflightReport:
    feasible: bool
    issues: List[Issue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "feasible": self.feasible,
            "issues": [asdict(i) for i in self.issues],
            "stats": self.stats,
        }

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i.severity == "warning"]


def _check_wall_thickness(part: PartNode, process: Process) -> List[Issue]:
    """检查壁厚约束"""
    issues = []
    limits = PROCESS_LIMITS.get(process, PROCESS_LIMITS[Process.GENERIC])
    min_w = limits["min_wall"]
    rec_w = limits["rec_wall"]

    for feat in part.features:
        if feat.type == FeatureType.SHELL:
            t = feat.params.get("thickness", 0)
            if t > 0 and t < min_w:
                issues.append(Issue("error", part.name, feat.name,
                    f"壁厚 {t}mm < 最小 {min_w}mm ({process.value})",
                    f"增大壁厚至 ≥{rec_w}mm"))
            elif t > 0 and t < rec_w:
                issues.append(Issue("warning", part.name, feat.name,
                    f"壁厚 {t}mm < 推荐 {rec_w}mm ({process.value})",
                    f"建议壁厚 ≥{rec_w}mm"))

    wall = part.dims.get("wall", part.dims.get("wall_thickness", 0))
    if wall > 0 and wall < min_w:
        issues.append(Issue("error", part.name, "",
            f"壁厚参数 {wall}mm < 最小 {min_w}mm",
            f"增大至 ≥{rec_w}mm"))
    return issues


def _check_fillet_feasibility(part: PartNode) -> List[Issue]:
    """检查圆角/倒角是否超过相邻边"""
    issues = []
    dims = part.dims
    # 获取最小尺寸
    dim_values = [v for k, v in dims.items()
                  if isinstance(v, (int, float)) and k in ("L", "W", "H", "D", "R")]
    if not dim_values:
        return issues
    min_dim = min(dim_values) if dim_values else 999

    for feat in part.features:
        if feat.type == FeatureType.FILLET:
            r = feat.params.get("radius", 0)
            if r > 0 and r >= min_dim / 2:
                issues.append(Issue("error", part.name, feat.name,
                    f"圆角 R{r} ≥ 最短边/2 ({min_dim/2}mm)",
                    f"最大可用圆角 R{min_dim/2 - 0.1:.1f}"))
        elif feat.type == FeatureType.CHAMFER:
            s = feat.params.get("size", 0)
            if s > 0 and s >= min_dim / 2:
                issues.append(Issue("error", part.name, feat.name,
                    f"倒角 {s}mm ≥ 最短边/2 ({min_dim/2}mm)",
                    f"最大可用倒角 {min_dim/2 - 0.1:.1f}mm"))
    return issues


def _check_hole_feasibility(part: PartNode, process: Process) -> List[Issue]:
    """检查孔径约束"""
    issues = []
    limits = PROCESS_LIMITS.get(process, PROCESS_LIMITS[Process.GENERIC])
    min_hole = limits["min_hole"]

    for feat in part.features:
        if feat.type == FeatureType.HOLE:
            d = feat.params.get("diameter", feat.params.get("d", 0))
            if d > 0 and d < min_hole:
                issues.append(Issue("warning", part.name, feat.name,
                    f"孔径 {d}mm < 最小 {min_hole}mm ({process.value})",
                    f"增大至 ≥{min_hole}mm 或后钻"))
    return issues


def _check_boolean_sanity(part: PartNode) -> List[Issue]:
    """检查布尔操作的基本合理性"""
    issues = []
    feature_names = {f.name for f in part.features}
    for feat in part.features:
        for dep in feat.depends_on:
            if dep not in feature_names:
                issues.append(Issue("error", part.name, feat.name,
                    f"依赖特征 '{dep}' 不存在",
                    "检查特征依赖链"))
    return issues


def _check_dims_chain(tree: DesignTree) -> List[Issue]:
    """检查尺寸链闭合"""
    issues = []
    for part in tree.parts:
        d = part.dims
        if "L" in d and "wall" in d:
            inner_l = d["L"] - 2 * d["wall"]
            if inner_l <= 0:
                issues.append(Issue("error", part.name, "",
                    f"内腔长度 = L({d['L']}) - 2*wall({d['wall']}) = {inner_l} ≤ 0",
                    "增大L或减小wall"))
        if "W" in d and "wall" in d:
            inner_w = d["W"] - 2 * d["wall"]
            if inner_w <= 0:
                issues.append(Issue("error", part.name, "",
                    f"内腔宽度 = W({d['W']}) - 2*wall({d['wall']}) = {inner_w} ≤ 0",
                    "增大W或减小wall"))
    return issues


def _estimate_complexity(tree: DesignTree) -> Dict:
    """估算构建复杂度"""
    total_features = sum(len(p.features) for p in tree.parts)
    has_boolean = any(
        f.type in (FeatureType.POCKET, FeatureType.HOLE)
        for p in tree.parts for f in p.features
    )
    has_pattern = any(
        f.type in (FeatureType.PATTERN_LINEAR, FeatureType.PATTERN_POLAR)
        for p in tree.parts for f in p.features
    )
    has_sweep = any(
        f.type in (FeatureType.SWEEP, FeatureType.LOFT, FeatureType.REVOLVE)
        for p in tree.parts for f in p.features
    )

    if has_sweep or total_features > 20:
        level = "high"
    elif has_boolean or has_pattern or total_features > 8:
        level = "medium"
    else:
        level = "low"

    return {
        "parts": len(tree.parts),
        "features": total_features,
        "joins": len(tree.joins),
        "level": level,
        "has_boolean": has_boolean,
        "has_pattern": has_pattern,
        "has_sweep": has_sweep,
    }


def _recommend_engine(tree: DesignTree) -> str:
    """根据设计树特征推荐最佳建模引擎"""
    complexity = _estimate_complexity(tree)
    has_sweep = complexity["has_sweep"]

    # 有旋转体/扫掠 → FreeCAD PartDesign 或 CadQuery
    if has_sweep:
        return "cadquery"

    # 多零件装配 → CadQuery assembly
    if len(tree.parts) > 3:
        return "cadquery"

    # 简单原型 → OpenSCAD (最快)
    if complexity["level"] == "low" and len(tree.parts) <= 2:
        return "cadquery"  # CadQuery 仍更通用

    # 默认: CadQuery (最佳平衡)
    return "cadquery"


# ═══════════════════════════════════════════════════════════════════════════
# 四、构建计划 — 从DesignTree到执行步骤
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class BuildStep:
    """构建计划中的一步"""
    order: int
    part_name: str
    action: str            # "create_body", "add_feature", "join", "export"
    feature: Optional[str] = None
    engine: str = "cadquery"
    code_hint: str = ""    # 代码生成提示
    checkpoint: bool = False  # 是否在此步后验证


@dataclass
class BuildPlan:
    """完整的构建计划"""
    design_name: str
    engine: str
    steps: List[BuildStep] = field(default_factory=list)
    estimated_ops: int = 0
    output_formats: List[str] = field(default_factory=lambda: ["stl", "step"])

    def to_dict(self):
        return {
            "design_name": self.design_name,
            "engine": self.engine,
            "steps": [asdict(s) for s in self.steps],
            "estimated_ops": self.estimated_ops,
            "output_formats": self.output_formats,
        }


def _plan_part(part: PartNode, engine: str) -> List[BuildStep]:
    """为单个零件生成构建步骤"""
    steps = []
    order = 0

    # Step 0: Create base body
    base_features = [f for f in part.features if f.type.value.startswith("body_")]
    if base_features:
        for bf in base_features:
            steps.append(BuildStep(
                order=order, part_name=part.name,
                action="create_body", feature=bf.name,
                engine=engine,
                code_hint=_feature_code_hint(bf, part, engine),
            ))
            order += 1
    elif part.features:
        # 第一个特征作为基体
        first = part.features[0]
        steps.append(BuildStep(
            order=order, part_name=part.name,
            action="create_body", feature=first.name,
            engine=engine,
            code_hint=_feature_code_hint(first, part, engine),
        ))
        order += 1

    # Subsequent features
    for feat in part.features:
        if feat in base_features:
            continue
        if not base_features and feat == part.features[0]:
            continue
        steps.append(BuildStep(
            order=order, part_name=part.name,
            action="add_feature", feature=feat.name,
            engine=engine,
            code_hint=_feature_code_hint(feat, part, engine),
        ))
        order += 1

    # Checkpoint after each part
    if steps:
        steps[-1].checkpoint = True

    return steps


def _feature_code_hint(feat: FeatureNode, part: PartNode, engine: str) -> str:
    """为特征生成代码提示 — 给LLM的指导"""
    p = feat.params
    d = part.dims

    if engine == "cadquery":
        return _cq_hint(feat, part)
    elif engine == "freecad":
        return _fc_hint(feat, part)
    else:
        return _cq_hint(feat, part)


def _cq_hint(feat: FeatureNode, part: PartNode) -> str:
    """CadQuery 代码提示"""
    p = feat.params
    d = part.dims
    t = feat.type

    if t == FeatureType.BODY_BOX:
        L, W, H = d.get("L", p.get("L", 20)), d.get("W", p.get("W", 15)), d.get("H", p.get("H", 10))
        return f'cq.Workplane("XY").box({L}, {W}, {H})'

    elif t == FeatureType.BODY_CYLINDER:
        R, H = p.get("R", d.get("R", 10)), p.get("H", d.get("H", 20))
        return f'cq.Workplane("XY").circle({R}).extrude({H})'

    elif t == FeatureType.PAD:
        H = p.get("height", p.get("H", 10))
        sketch_hint = p.get("sketch_desc", "rectangular profile")
        return f'# Sketch: {sketch_hint}\n.extrude({H})'

    elif t == FeatureType.POCKET:
        depth = p.get("depth", 5)
        return f'.faces(">Z").workplane().rect(...).cutBlind(-{depth})'

    elif t == FeatureType.HOLE:
        d_hole = p.get("diameter", p.get("d", 3.4))
        depth = p.get("depth", "thru")
        if depth == "thru":
            return f'.faces(">Z").workplane().hole({d_hole})'
        else:
            return f'.faces(">Z").workplane().hole({d_hole}, depth={depth})'

    elif t == FeatureType.FILLET:
        r = p.get("radius", 2)
        edges = p.get("edges", "all")
        if edges == "all":
            return f'.edges().fillet({r})'
        elif edges == "vertical":
            return f'.edges("|Z").fillet({r})'
        else:
            return f'.edges("...").fillet({r})  # edges: {edges}'

    elif t == FeatureType.CHAMFER:
        s = p.get("size", 1)
        return f'.edges().chamfer({s})'

    elif t == FeatureType.SHELL:
        t_val = p.get("thickness", 2)
        faces = p.get("faces_to_remove", ">Z")
        return f'.faces("{faces}").shell(-{t_val})'

    elif t == FeatureType.PATTERN_LINEAR:
        count = p.get("count", 3)
        spacing = p.get("spacing", 10)
        direction = p.get("direction", "X")
        return f'# Linear pattern: {count}x, spacing {spacing}mm along {direction}'

    elif t == FeatureType.PATTERN_POLAR:
        count = p.get("count", 6)
        return f'# Polar pattern: {count}x around Z axis'

    elif t == FeatureType.MIRROR:
        plane = p.get("plane", "YZ")
        return f'.mirror("{plane}")'

    elif t == FeatureType.REVOLVE:
        angle = p.get("angle", 360)
        return f'.revolve({angle})'

    elif t == FeatureType.SWEEP:
        return '# Sweep profile along path wire'

    elif t == FeatureType.LOFT:
        return '# Loft between multiple profiles'

    elif t == FeatureType.BOSS:
        d_boss = p.get("diameter", 8)
        h = p.get("height", 5)
        return f'.faces(">Z").workplane().circle({d_boss/2}).extrude({h})'

    elif t == FeatureType.GROOVE:
        w = p.get("width", 3)
        d_val = p.get("depth", 2)
        return f'# Groove: width={w}, depth={d_val}'

    elif t == FeatureType.RIB:
        t_val = p.get("thickness", 2)
        h = p.get("height", 10)
        return f'# Rib: thickness={t_val}, height={h}'

    return f'# {feat.type.value}: {json.dumps(p, ensure_ascii=False)}'


def _fc_hint(feat: FeatureNode, part: PartNode) -> str:
    """FreeCAD PartDesign 代码提示"""
    p = feat.params
    d = part.dims
    t = feat.type

    if t == FeatureType.BODY_BOX:
        L, W, H = d.get("L", 20), d.get("W", 15), d.get("H", 10)
        return f'Part.makeBox({L}, {W}, {H})'

    elif t == FeatureType.PAD:
        return 'Body.addObject("PartDesign::Pad", "Pad"); Pad.Length = ...'

    elif t == FeatureType.POCKET:
        return 'Body.addObject("PartDesign::Pocket", "Pocket"); Pocket.Length = ...'

    return f'# FreeCAD: {feat.type.value}'


# ═══════════════════════════════════════════════════════════════════════════
# 五、主编译器 — 统一入口
# ═══════════════════════════════════════════════════════════════════════════

class DesignIntentCompiler:
    """
    设计意图编译器 — Agent的空间理解内核。

    道法自然: 从人类认知的原始结构出发，不从工具出发。
    反者道之动: 从逆向（功能→结构→几何）编译设计意图。
    """

    def __init__(self, default_process: Process = Process.FDM):
        self.default_process = default_process

    def compile(self, spec: Dict) -> DesignTree:
        """
        编译设计规格为DesignTree。

        Args:
            spec: 设计规格字典, 结构:
                {
                    "name": str,
                    "description": str,
                    "process": "fdm"|"sla"|"cnc"|...,
                    "parts": [
                        {
                            "name": str,
                            "function": "contain"|"support"|...,
                            "dims": {"L": 50, "W": 40, ...},
                            "features": [
                                {"name": str, "type": "hole"|"fillet"|..., "params": {...}},
                            ],
                            "material": "pla",
                        },
                    ],
                    "joins": [{"part_a": str, "part_b": str, "method": "screw"|...}],
                    "constraints": [...],
                }
        Returns:
            DesignTree
        """
        process = Process(spec.get("process", self.default_process.value))

        tree = DesignTree(
            name=spec.get("name", "unnamed"),
            description=spec.get("description", ""),
            process=process,
            global_params=spec.get("global_params", {}),
            metadata=spec.get("metadata", {}),
        )

        # 编译零件
        for pd in spec.get("parts", []):
            part = self._compile_part(pd, process)
            tree.parts.append(part)

        # 编译连接
        for jd in spec.get("joins", []):
            tree.joins.append(JoinNode(
                part_a=jd["part_a"],
                part_b=jd["part_b"],
                method=JoinMethod(jd.get("method", "none")),
                params=jd.get("params", {}),
            ))

        # 编译约束
        for cd in spec.get("constraints", []):
            tree.constraints.append(Constraint(
                type=cd["type"],
                targets=cd["targets"],
                value=cd.get("value"),
                expr=cd.get("expr", ""),
            ))

        # 自动推导: 如果零件有功能但没有特征，从功能映射生成默认特征
        for part in tree.parts:
            if not part.features and part.function != Function.CUSTOM:
                self._auto_features(part, process)

        return tree

    def _compile_part(self, pd: Dict, process: Process) -> PartNode:
        """编译单个零件"""
        func = Function(pd.get("function", "custom"))
        features = []
        for i, fd in enumerate(pd.get("features", [])):
            features.append(FeatureNode(
                name=fd.get("name", f"feat_{i}"),
                type=FeatureType(fd["type"]),
                params=fd.get("params", {}),
                sketch=fd.get("sketch"),
                depends_on=fd.get("depends_on", []),
                order=fd.get("order", i),
                note=fd.get("note", ""),
            ))

        return PartNode(
            name=pd["name"],
            function=func,
            dims=pd.get("dims", {}),
            features=features,
            material=pd.get("material", "pla"),
            color=tuple(pd.get("color", (0.7, 0.7, 0.7))),
            origin=tuple(pd.get("origin", (0, 0, 0))),
            note=pd.get("note", ""),
        )

    def _auto_features(self, part: PartNode, process: Process):
        """从功能自动生成默认特征 — 可供性推理 (Gibson affordance)"""
        func = part.function
        d = part.dims
        mapping = FUNCTION_TO_STRUCTURE.get(func)
        if not mapping:
            return

        if func == Function.CONTAIN:
            # 容纳 → 盒体 + 抽壳
            wall = d.get("wall", d.get("wall_thickness", 2.0))
            part.features.append(FeatureNode(
                name="body", type=FeatureType.BODY_BOX,
                params={"L": d.get("L", 50), "W": d.get("W", 40), "H": d.get("H", 30)},
                order=0,
            ))
            part.features.append(FeatureNode(
                name="shell", type=FeatureType.SHELL,
                params={"thickness": wall, "faces_to_remove": ">Z"},
                depends_on=["body"], order=1,
            ))
            if d.get("fillet_r", 0) > 0:
                part.features.append(FeatureNode(
                    name="fillet", type=FeatureType.FILLET,
                    params={"radius": d["fillet_r"]},
                    depends_on=["body"], order=0.5,  # before shell
                ))

        elif func == Function.SUPPORT:
            # 支撑 → 底板
            part.features.append(FeatureNode(
                name="base_plate", type=FeatureType.BODY_BOX,
                params={"L": d.get("L", 80), "W": d.get("W", 60), "H": d.get("H", 5)},
                order=0,
            ))

        elif func == Function.FASTEN:
            # 连接 → 凸台 + 孔
            screw = d.get("screw_size", "M3")
            screw_info = METRIC_SCREWS.get(screw, METRIC_SCREWS["M3"])
            hole_d = screw_info["clearance"]
            boss_d = hole_d + 2 * screw_info["d"]
            part.features.append(FeatureNode(
                name="boss", type=FeatureType.BOSS,
                params={"diameter": boss_d, "height": d.get("height", 8)},
                order=0,
            ))
            part.features.append(FeatureNode(
                name="screw_hole", type=FeatureType.HOLE,
                params={"diameter": hole_d, "depth": "thru"},
                depends_on=["boss"], order=1,
            ))

        elif func == Function.MOUNT:
            # 安装 → 法兰 + 孔阵列
            part.features.append(FeatureNode(
                name="flange", type=FeatureType.BODY_CYLINDER,
                params={"R": d.get("od", 60) / 2, "H": d.get("thickness", 8)},
                order=0,
            ))
            part.features.append(FeatureNode(
                name="bore", type=FeatureType.HOLE,
                params={"diameter": d.get("id", 25), "depth": "thru"},
                depends_on=["flange"], order=1,
            ))
            n_bolts = d.get("n_bolts", 6)
            part.features.append(FeatureNode(
                name="bolt_holes", type=FeatureType.PATTERN_POLAR,
                params={"feature": "bolt_hole", "count": n_bolts,
                        "hole_d": d.get("bolt_d", 6.6), "pcd": d.get("pcd", 45)},
                depends_on=["flange"], order=2,
            ))

    def preflight(self, tree: DesignTree) -> PreflightReport:
        """
        几何可行性预检 — 在写任何代码之前验证设计。
        人类工程师的"直觉"的计算实现。
        """
        issues = []
        process = tree.process

        for part in tree.parts:
            issues.extend(_check_wall_thickness(part, process))
            issues.extend(_check_fillet_feasibility(part))
            issues.extend(_check_hole_feasibility(part, process))
            issues.extend(_check_boolean_sanity(part))

        issues.extend(_check_dims_chain(tree))

        feasible = not any(i.severity == "error" for i in issues)
        stats = _estimate_complexity(tree)
        stats["engine_recommendation"] = _recommend_engine(tree)

        return PreflightReport(feasible=feasible, issues=issues, stats=stats)

    def plan(self, tree: DesignTree) -> BuildPlan:
        """
        生成构建计划 — 从DesignTree到有序的构建步骤。
        """
        engine = _recommend_engine(tree)
        steps = []
        order_offset = 0

        for part in tree.parts:
            part_steps = _plan_part(part, engine)
            for s in part_steps:
                s.order += order_offset
            steps.extend(part_steps)
            order_offset = steps[-1].order + 1 if steps else 0

        # 连接步骤
        for join in tree.joins:
            if join.method == JoinMethod.FUSE:
                steps.append(BuildStep(
                    order=order_offset,
                    part_name=f"{join.part_a}+{join.part_b}",
                    action="join",
                    engine=engine,
                    code_hint=f'result = {join.part_a}.union({join.part_b})',
                    checkpoint=True,
                ))
                order_offset += 1

        # 导出步骤
        steps.append(BuildStep(
            order=order_offset,
            part_name="*",
            action="export",
            engine=engine,
            code_hint="export STL + STEP",
            checkpoint=True,
        ))

        return BuildPlan(
            design_name=tree.name,
            engine=engine,
            steps=steps,
            estimated_ops=len(steps),
        )

    def compile_and_plan(self, spec: Dict) -> Tuple[DesignTree, PreflightReport, BuildPlan]:
        """一步完成: 编译 + 预检 + 规划"""
        tree = self.compile(spec)
        report = self.preflight(tree)
        plan = self.plan(tree) if report.feasible else BuildPlan(design_name=tree.name, engine="none")
        return tree, report, plan


# ═══════════════════════════════════════════════════════════════════════════
# 六、CLI 入口
# ═══════════════════════════════════════════════════════════════════════════

def _demo():
    """演示: 编译一个手机支架"""
    spec = {
        "name": "phone_stand",
        "description": "桌面手机支架，可调角度，带充电线槽",
        "process": "fdm",
        "parts": [
            {
                "name": "base",
                "function": "support",
                "dims": {"L": 80, "W": 60, "H": 5},
                "features": [
                    {"name": "body", "type": "body_box", "params": {"L": 80, "W": 60, "H": 5}},
                    {"name": "rubber_feet", "type": "pattern_linear",
                     "params": {"count": 4, "feature": "foot_hole",
                                "hole_d": 8, "positions": [[10,10],[70,10],[10,50],[70,50]]}},
                    {"name": "cable_slot", "type": "groove",
                     "params": {"width": 8, "depth": 5, "length": 20}},
                    {"name": "fillet", "type": "fillet", "params": {"radius": 3, "edges": "vertical"}},
                ],
                "material": "pla",
                "color": [0.2, 0.2, 0.8],
            },
            {
                "name": "cradle",
                "function": "contain",
                "dims": {"L": 75, "W": 12, "H": 40, "wall": 2},
                "features": [
                    {"name": "body", "type": "body_box", "params": {"L": 75, "W": 12, "H": 40}},
                    {"name": "phone_slot", "type": "pocket",
                     "params": {"width": 71, "depth": 10, "height": 35}},
                    {"name": "fillet", "type": "fillet", "params": {"radius": 2}},
                ],
                "color": [0.2, 0.2, 0.8],
            },
        ],
        "joins": [
            {"part_a": "base", "part_b": "cradle", "method": "fuse",
             "params": {"position": [2.5, 24, 5]}},
        ],
    }

    compiler = DesignIntentCompiler()
    tree, report, plan = compiler.compile_and_plan(spec)

    print("=" * 60)
    print(f"设计树: {tree.name}")
    print(f"描述: {tree.description}")
    print(f"工艺: {tree.process.value}")
    print(f"零件: {len(tree.parts)}, 连接: {len(tree.joins)}")
    print()

    print("── 预检报告 ──")
    print(f"可行: {report.feasible}")
    for issue in report.issues:
        print(f"  [{issue.severity}] {issue.part}.{issue.feature}: {issue.message}")
        if issue.suggestion:
            print(f"         → {issue.suggestion}")
    print(f"复杂度: {report.stats}")
    print()

    print("── 构建计划 ──")
    print(f"引擎: {plan.engine}")
    for step in plan.steps:
        chk = " ✓" if step.checkpoint else ""
        print(f"  [{step.order}] {step.part_name}.{step.action}"
              f"{'(' + step.feature + ')' if step.feature else ''}{chk}")
        if step.code_hint:
            for line in step.code_hint.split('\n'):
                print(f"       {line}")
    print()
    print("── DesignTree JSON ──")
    print(tree.to_json())


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        _demo()
    elif len(sys.argv) > 1:
        # Load spec from JSON file
        spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        compiler = DesignIntentCompiler()
        tree, report, plan = compiler.compile_and_plan(spec)
        print(json.dumps({
            "tree": tree.to_dict(),
            "preflight": report.to_dict(),
            "plan": plan.to_dict(),
        }, indent=2, ensure_ascii=False, default=str))
    else:
        print("Usage: python design_intent_compiler.py demo")
        print("       python design_intent_compiler.py <spec.json>")
        _demo()
