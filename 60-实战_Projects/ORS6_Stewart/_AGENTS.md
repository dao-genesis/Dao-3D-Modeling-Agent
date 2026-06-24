# ORS6_Stewart — Agent 操作手册

## 项目身份

Stewart 六轴平台一等项目. ORS6-VAM 饮料摇匀器 的所有 3D 建模/分析/运动学职责归位于此.

反者道之动 · 原散居于 `ORS6-VAM饮料摇匀器/` (业务层) 的 ~3500 行建模代码归一到此处.
ORS6 业务层通过 `../ORS6-VAM饮料摇匀器/sr6_modeling.py` 薄 shim 反向 import.

## 道 — 锚定本源

| 真相 | 内容 |
|---|---|
| **STL = 唯一几何真相** | 31 个 CAD 零件, Z-up 共享坐标系, `parts.PARTS` 唯一真相源 |
| **IK = 唯一实现** | `kinematics.StewartIK` 从 firmware 1:1 复刻, 11/11 验证 PASS |
| **框架 = 矩形** | L/R 框架间距 199.2mm (非圆形 BASE_R) |
| **HOME_H** | 208.48mm = servoPivotH(46) + baseH(162.48) |

## 铁律

1. **数值先于视觉** — 任何 3D 决策先用 trimesh 计算 bbox/volume, 再渲染
2. **STL 是唯一几何真相** — 禁止用 primitive 替代已有 STL 零件
3. **IK 只有一处** — 全部 `StewartIK` via `kinematics.py`, 禁止再实现
4. **业务与建模分离** — hub.html = 控制面板, 不是 CAD 系统
5. **验证 = 数值断言 + 视觉确认** — E2E 必须含 trimesh 数值检查

## 入口

| 命令 | 作用 |
|---|---|
| `python -m ORS6_Stewart info` | STL_ROOT / PARTS / HOME_H 概览 |
| `python -m ORS6_Stewart health` | 完整健康 (STL + verify + IK + tools) |
| `python -m ORS6_Stewart verify` | V1-V8 数值验证 (预期 8/8 PASS) |
| `python -m ORS6_Stewart ik-verify` | IK 11 项检查 (预期 11/11 PASS) |
| `python -m ORS6_Stewart rods` | Home 位置杆几何 |
| `python -m ORS6_Stewart build` | CadQuery 构建 home, 导出 STEP+STL |
| `python -m ORS6_Stewart motion cadquery` | 15 姿态序列 |
| `python -m ORS6_Stewart serve 8871` | 启动 Web 查看器 |

## 模块边界

```
parts.py       ← 唯一数据源 (PARTS / SR6 / RECV_PARTS / ...)
kinematics.py  ← 唯一 IK (StewartIK / compute_rods / assembly_instances)
verify.py      ← V1-V8 数值断言 (依赖 parts)
analysis.py    ← mass/quality/workspace/... (依赖 parts + kinematics)
assembly.py    ← CadQuery+OCP 和 FreeCAD 双路径构建 (依赖以上三)
poses.py       ← 15 姿态常量
viewer/        ← HTTP + Three.js 查看器 (依赖以上全)
cli.py         ← 统一命令行
__init__.py    ← 公开 API
```

## 反模式

| 信号 | 正确做法 |
|---|---|
| 在 ORS6 业务层重新实现 IK | 删除, 改用 `from sr6_modeling import StewartIK` |
| 往 `parts.py` 加运动学 | 加到 `kinematics.py` |
| 重复 hub.html 的控制面板 | 分离到业务层 `ors6_hub.py` |
| 把建模相关脚本放在 ORS6 目录 | 移到此项目 |
| 在 freecad_output/ 堆大文件 | 只输出 BREP rods (~200KB), 不输出全装配 STEP |

## 数值常量速查

- 28125 = 175² − 50² (mainRod² − mainArm²)
- 36250 = 75² + 175² (pitchArm² + pitchRod²)
- 5625 = 75² (pitchArm²)
- HOME_H = 208.48mm
- Frame spacing = 199.2mm (rectangular)
- Arm home angle = −10.55° (below horizontal, NOT 0!)
- Main rod 3D at home = 178.87mm (含 37mm bay offset)

## Home 位置完整状态 (已验证)

```
LowerLeft    arm=-10.55°  2D=175.00mm  3D=178.87mm  stress=0.02%
UpperLeft    arm=-10.55°  2D=175.00mm  3D=178.87mm  stress=0.02%
LeftPitch    arm=+16.35°  2D=175.00mm  3D=175.00mm  stress=0.00%
RightPitch   arm=+16.35°  2D=175.00mm  3D=175.00mm  stress=0.00%
UpperRight   arm=-10.55°  2D=175.00mm  3D=178.87mm  stress=0.02%
LowerRight   arm=-10.55°  2D=175.00mm  3D=178.87mm  stress=0.02%
```

## 验证结果

| 维度 | 结果 |
|---|---|
| **IK standalone** | 11/11 PASS (V1~V10 + symmetry) |
| **verify_assembly** | 8/8 PASS (V1_coord ~ V8_ik_constants) |
| **ORS6 pytest** | 76/76 PASS (test_pdf_data 43 + test_virtual_device + test_douyin_sim) |
| **STL 文件完整性** | 31/31 存在且可加载 |
| **Viewer HTTP** | 所有 API 端点正常 (/api/parts/health/ik/instances/verify/...) |

## 与 3D建模Agent 其它资产的关系

- `00-本源_Origin/dao_kinematics.py` — 通用 FK/IK (此项目的 Stewart IK 未使用它, 因为 firmware 是针对 SR6 的 1:1 实现. 未来如需动力学/干涉/临界转速分析, 可接入)
- `00-本源_Origin/dao_audit.py` — 八层审核 (可选: 对 assembly.step 做结构审核)
- `10-反笙_FreeCAD/fc_show.py` — GUI 展示台 (assembly.py build_freecad 后可 `fc_show assembly.FCStd`)
- `20-万法_Forge/forge_v3.py printability` — 制造性分析 (analysis 暂未集成, 如需: 加 `printability_check` 调用)
