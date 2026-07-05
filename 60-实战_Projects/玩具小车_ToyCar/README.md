# 玩具小车 · 复杂装配体从零构建（VS Code 插件体系内实战）

> 道法自然 · 无为而无不为：一切经桥接 `/exec` 直达 FreeCAD 本体，
> AI 后端逐阶段构建，用户前端（VS Code「整窗归一」面板）实时可见。

## 全流程七阶段

| 阶段 | 内容 | 板块 |
|---|---|---|
| 1 | 底盘（带前后轴孔 Part::Cut） | 参数化建模 + 布尔 |
| 2 | 前后轴 | 装配定位 Placement |
| 3 | 四轮（胎体−轴孔 Part::Cut） | 布尔 + 配合孔轴 |
| 4 | 车身+驾驶室（Part::MultiFuse） | 布尔融合 |
| 5 | 运动学仿真：dao_kinematics revolute 关节 FK + GUI 实转动画（前移 100mm，轮转 358.1°） | 00-本源 运动学 + GUI 动画 |
| 6 | 干涉检查（两两 common 体积）+ 质量属性（体积/面积/质心） | 验证 |
| 7 | FCStd / STEP / STL 导出 + 等轴测截图取证 | 交付 |

## 实践暴露缺陷 → 修复闭环

1. `dao_kinematics.Link(mass=…)` 不存在 → 按真实 API（`Mechanism(root_link=…)` +
   `SE3.from_translation` + `forward_kinematics`）修正。
2. `Part::MultiFuse` 结果为 Compound，无 `CenterOfMass` → 按 Solids 加权求质心。
3. 轴穿底盘/轮体干涉（1510.6/226.2 mm³）→ 底盘开轴孔、轮体开贯通孔 →
   **干涉清零**（`verify_report.json: interference: []`）。

## 运行

```bash
# 桥接需在跑（插件自启或手动: freecad 10-反笙_FreeCAD/_fc_remote_server.py）
python3 build_toycar.py
```

产物：`ToyCar.FCStd` / `ToyCar.step` / `ToyCar.stl` / `ToyCar_iso.png` /
`kinematics_result.json` / `verify_report.json`
