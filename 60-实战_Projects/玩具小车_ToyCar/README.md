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

---

# v2 · 反者道之动：推翻纯拼凑，重建为真实电动玩具车

v1 缺陷：无动力源、无减速传动、无配合公差——现实中动不起来。
v2 按市售 1:18 级电动玩具车结构重建（`build_toycar_v2.py`）：

| 子系统 | 设计 | 复用工具链 |
|---|---|---|
| 车架底盘 | 150×56×4 圆角板 + 4 轴承座塔（Ø4.3 间隙孔，配合间隙 +0.3） | `/ops make_rounded_box/cut` |
| 动力 | 130 型直流电机 Ø20×25（负载 8000 rpm）+ 抱箍式电机座 | `/ops make_cylinder/cut` |
| 减速 | **真渐开线**齿轮副 z10:z40，m0.5，减速比 4:1，中心距 12.65（含 0.15 侧隙） | `freecad_backend make_gear_spur` |
| 传动 | 前后 Ø4×92 传动轴 + 轴端挡圈 | `/ops fuse` |
| 行走 | 四轮 Ø36×14（轮毂+轮胎，Ø4.3 间隙孔） | `/ops make_hollow_cylinder` |
| 车壳 | 开底罩壳 + 圆角驾驶舱 | `/ops make_enclosure` |

## 工程核算（`toycar_v2_engineering.json`）

- 齿轮系运动学耦合：`q_axle = q_motor / 4`（dao_kinematics FK 验证）
- 性能：电机 8000 rpm → 轮速 2000 rpm → 车速 **3.77 m/s ≈ 13.6 km/h**（玩具车合理区间）
- 转子平衡：ISO G16 校核（对称成组策略通过）
- 轴临界转速：Dunkerley 法校核 Ø4×92 轴 @2000 rpm
- 离心载荷：轮体 m·ω²·r + 销轴剪切校核
- **干涉清零**：11 零件两两 `common` 体积全部 < 0.05 mm³
- 总质量 ≈ 618 g（ABS 1.05 + 钢件 7.85 g/cm³ 分材质核算）

## 运行

```bash
python3 build_toycar_v2.py   # 桥接 18920 在线即可，GUI 面板实时可见 + 传动链动画
```

产物：`ToyCarV2.FCStd` / `.step` / `.stl` / `ToyCarV2_iso.png` /
`ToyCarV2_drivetrain.png`（底视透视传动链）/ `toycar_v2_engineering.json`
