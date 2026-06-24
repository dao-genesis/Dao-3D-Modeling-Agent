# ORS6_Stewart — Stewart 六轴平台一等项目

> **道生一**: 31 STL = 唯一几何真相
> **一生二**: firmware IK + trimesh 数值分析
> **二生三**: CadQuery(OCP) + FreeCAD 两大装配路径
> **三生万物**: 15 姿态动画 + 质量/工作空间/间距/碰撞 + Web 查看器

反者道之动 — 此项目原散居于 `ORS6-VAM饮料摇匀器/` (控制系统)，
今归位于万法本源 `3D建模Agent/60-实战_Projects/ORS6_Stewart/`。
ORS6 业务层 (TCode/VaM/Funscript) 通过 `sr6_modeling.py` shim 反向 import 此处。

## 架构

```
ORS6_Stewart/
├── __init__.py              公开 API (from ORS6_Stewart import *)
├── parts.py                 31 STL 注册表 + SR6 IK 常数 + STL 定位
├── kinematics.py            Stewart IK 唯一实现 (firmware 1:1)
├── verify.py                V1-V8 数值验证
├── analysis.py              mass/quality/workspace/clearance/assembly_stats
├── assembly.py              CadQuery+OCP 和 FreeCAD 两路径装配
├── poses.py                 15 标准 T-Code 姿态
├── viewer/
│   ├── server.py            HTTP 服务 :8871 (Three.js 前端)
│   └── index.html           查看器前端 (原 sr6_studio.html)
├── cli.py                   统一 CLI (health/verify/build/serve/...)
├── __main__.py              enable `python -m ORS6_Stewart`
└── _selftest.py             自检 (11 IK + 8 verify + 31 STL)
```

## CLI

```bash
cd 3D建模Agent/60-实战_Projects

# 基础
python -m ORS6_Stewart info              # STL_ROOT / PARTS 数 / HOME_H
python -m ORS6_Stewart health            # 完整健康诊断
python -m ORS6_Stewart verify            # V1-V8 数值验证
python -m ORS6_Stewart ik-verify         # IK standalone 11 检查
python -m ORS6_Stewart overview          # 31 零件按 Z 排序概览

# 几何
python -m ORS6_Stewart servo             # 舵机槽位 (Z=46mm)
python -m ORS6_Stewart section 46        # 任意 Z 截面
python -m ORS6_Stewart info-part Base    # 单件 trimesh 信息
python -m ORS6_Stewart rebuild-bounds    # 重建 _stl_bounds.json

# 运动学
python -m ORS6_Stewart rods              # home 杆几何
python -m ORS6_Stewart rods 9999 5000 5000 5000 5000 5000
python -m ORS6_Stewart ik-forward 0.5 0.5 0.5 0.5 0.5 0.5

# 分析
python -m ORS6_Stewart mass              # 全件质量 (PLA)
python -m ORS6_Stewart mass Base pla
python -m ORS6_Stewart quality           # 全件质检
python -m ORS6_Stewart workspace 10      # IK 工作空间
python -m ORS6_Stewart clearance         # 装配间距
python -m ORS6_Stewart assembly          # 装配整体
python -m ORS6_Stewart collision Base L_Frame

# 建模
python -m ORS6_Stewart build             # CadQuery 构建 home
python -m ORS6_Stewart build 9999 5000 5000 5000 5000 5000 thrust_up
python -m ORS6_Stewart build-fc          # FreeCAD 路径 (需 FreeCAD 环境)
python -m ORS6_Stewart motion cadquery   # 15 姿态序列

# 查看器
python -m ORS6_Stewart serve             # http://localhost:8871
python -m ORS6_Stewart serve 8888
```

## Python API

```python
import ORS6_Stewart as S

# Registry
S.PARTS                 # {name: (subfolder, filename, color, group)}
S.SR6                   # IK 常数 dict
S.HOME_H                # 208.48mm
S.stl_path("Base")      # 绝对路径
S.load_stl("Base")      # trimesh.Mesh

# IK (单一实现)
ik = S.StewartIK()
ik.compute_servo_outputs(5000, 5000, 5000, 5000, 5000, 5000)
ik.compute_receiver_pose(9999, 5000, 5000, 5000, 5000, 5000)
ik.compute_full_geometry(...)  # {arm_tips, recv_mounts, arm_angles}
S.compute_rods(pose=S.TCODE_HOME)
S.assembly_instances(pose=S.TCODE_HOME)
S.ik_home_arm_angle("LowerLeft")  # radians
S.arm_tip_world("LowerLeft", pose=(9999,5000,5000,5000,5000,5000))

# 验证
S.verify_assembly()              # {V1_coord_consistency: PASS, ...}
S.verify_ik_standalone()         # [(name, ok, detail), ...]

# 分析
S.mass_properties("Base", "pla")
S.quality_check_all()
S.workspace_analysis(resolution=10)
S.clearance_analysis()
S.assembly_stats()

# 构建
S.build_cadquery(pose=S.TCODE_HOME, label="home")     # → STEP+STL
S.build_freecad(pose=(9999,5000,5000,5000,5000,5000), label="thrust_up")
S.motion_sequence(engine="cadquery")   # 15 姿态
```

## STL_ROOT 解析 (道法自然)

按优先级查找:
1. 环境变量 `ORS6_STL_ROOT`
2. `../../../ORS6-VAM饮料摇匀器/SR6资料/.../STLs` (默认)
3. `./STLs/` (本地 symlink)

## 数值常数 (firmware-verified)

| 参数 | 值 | 来源 |
|------|------|------|
| baseH | 162.48mm | firmware `16248/100` |
| mainArm | 50mm | `2a=100 → a=50` |
| mainRod | 175mm | PDF p.26 + `√30625` |
| pitchArm | 75mm | `2a=150 → a=75` |
| pitchOff | 55mm | `5500/100` |
| pitchAng | 15° | `0.2618 rad` |
| msPerRad | 637 | 标准舵机 |
| servoPivotH | 46mm | STL Arm Z_min |
| HOME_H | 208.48mm | servoPivotH + baseH |

## 固件魔术常数

- `28125 = 175² − 50²` (mainRod² − mainArm², 余弦定理化简)
- `36250 = 75² + 175²` (pitchArm² + pitchRod²)
- `5625 = 75²` (pitchArm²)

## 装配层次

A. 静态结构件 (Base/Frames/Pitchers/Lid/PowerBus/Shield/Tray) — STL 原位导入  
B. 舵机臂 — 4× Arm STL 实例 (镜像+IK旋转) + 2× Pitcher STL (IK旋转)  
C. 接收器 + T-wist4 — elevate to HOME_H + roll/pitch + twist 齿轮组  
D. 6 连杆 — 参数化圆柱+球头，IK arm_tip → recv_mount

## Home 位置杆几何 (验证值)

```
LowerLeft    arm=-10.55°  2D=175.00 mm  3D=178.87 mm  stress=0.02%
UpperLeft    arm=-10.55°  2D=175.00 mm  3D=178.87 mm  stress=0.02%
LeftPitch    arm=+16.35°  2D=175.00 mm  3D=175.00 mm  stress=0.00%
RightPitch   arm=+16.35°  2D=175.00 mm  3D=175.00 mm  stress=0.00%
UpperRight   arm=-10.55°  2D=175.00 mm  3D=178.87 mm  stress=0.02%
LowerRight   arm=-10.55°  2D=175.00 mm  3D=178.87 mm  stress=0.02%
```

## 兼容性说明 (ORS6 业务层)

ORS6 项目侧保留 `sr6_modeling.py` 薄 shim:
```python
# ORS6-VAM饮料摇匀器/sr6_modeling.py
from ORS6_Stewart import *   # 转发所有建模 API
```

如果老代码 `from sr6_tools import PARTS, SR6`，会以 DeprecationWarning 转发。
新代码应 `from sr6_modeling import PARTS, SR6`。

## 回归历史

| 版本 | 事件 |
|------|------|
| v1.x | 建模代码散居于 ORS6 (sr6_tools/sr6_analyzer/sr6_geometry/sr6_assembly + ors6_freecad_build/ors6_cq_build/freecad_assembly + sr6_config.js + forge_bridge), IK 三重实现彼此漂移, freecad_output/ 膨胀至 1966 MB |
| **v2.0** | **本次归一**: 3500 行建模代码归位到此项目，IK 归为唯一实现 (11/11 PASS), 8/8 verify PASS, freecad_output/ 清空, ORS6 控制层解耦 |
