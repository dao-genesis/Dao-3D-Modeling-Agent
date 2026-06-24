# SolidWorks 实测仿真报告 · 道法自然

> 生成: 2026-04-25T13:27:46.049048  ·  SW Rev: 31.0.1
> 装配: `D:\道\道生一\一生二\3D建模Agent\60-实战_Projects\南京-吴鸿轩_锤式破碎机\交付包_最终\锤式破碎机_总装配.SLDASM`

## 总览

| Phase | 项 | 结果 |
|---|---|---|
| 2 | 重建 | ✅ |
| 2 | 组件 | 34 件 (解析 33 · 抑制 1 · 固定 34) |
| 3 | 干涉 | 63 处 ⚠️ |
| 4 | 整机质量 | **1238.051 kg** |
| 4 | 整机重心 | (95.7, -3.1, -436.0) mm |
| 4 | 整机体积 | 321526.0 cm³ |
| 4 | 组件级 | 12 件 (去重) |
| 5 | 配合 | 0 处 |
| 6 | 运动算例 | 无插件/跳过  (1200 rpm × 0.5s) |
| 7 | 截图 | 7 视图 |
| 7 | STEP | ✅ D:\道\道生一\一生二\3D建模Agent\60-实战_Projects\南京-吴鸿轩_锤式破碎机\交付包_最终\锤式破碎机_总装配.STEP |
| 7 | STL | ✅ D:\道\道生一\一生二\3D建模Agent\60-实战_Projects\南京-吴鸿轩_锤式破碎机\交付包_最终 |

## 抑制组件 (装配树 ⚠ 图标)

- `drive_pulley-1`

## 配合诊断

- 装配体内 **34** 件组件全部为 *固定* (Fixed) 状态, 故 MateGroup 为空 (0 处配合).
- 当前装配采用 **位置固定式** 而非 **配合约束式**.
- 改进建议: 取消固定 → 添加同心/重合等配合 → 让 SW 自动解算自由度. 这样 Motion Study 才能驱动旋转.

## 干涉清单 (63 处, 按体积降序)

| # | 体积 (mm³) | 组件 |
|---:|---:|---|
| 1 | 90419.0 | main_shaft-1 ↔ casing_upper-1 |
| 2 | 90419.0 | main_shaft-1 ↔ casing_lower-1 |
| 3 | 90419.0 | main_shaft-1 ↔ casing_upper-1 |
| 4 | 90419.0 | main_shaft-1 ↔ casing_lower-1 |
| 5 | 84840.2 | screen_plate-1 ↔ casing_lower-1 |
| 6 | 62828.2 | driven_pulley-1 ↔ v_belt-6 |
| 7 | 62828.2 | driven_pulley-1 ↔ v_belt-6 |
| 8 | 62828.2 | driven_pulley-1 ↔ v_belt-6 |
| 9 | 62828.2 | driven_pulley-1 ↔ v_belt-6 |
| 10 | 49080.7 | hammer_pin-4 ↔ hammer-8 |
| 11 | 49080.7 | hammer_pin-4 ↔ hammer-12 |
| 12 | 49080.7 | hammer_pin-3 ↔ hammer-10 |
| 13 | 49080.7 | hammer_pin-2 ↔ hammer-7 |
| 14 | 49080.7 | hammer_pin-3 ↔ hammer-6 |
| 15 | 49080.7 | hammer_pin-2 ↔ hammer-11 |
| 16 | 49080.4 | hammer_pin-1 ↔ hammer-9 |
| 17 | 49080.4 | hammer_pin-1 ↔ hammer-5 |
| 18 | 39000.0 | frame_base-1 ↔ motor_mount-1 |
| 19 | 38940.6 | hammer_pin-1 ↔ hammer-1 |
| 20 | 38940.5 | hammer_pin-4 ↔ hammer-4 |
| 21 | 38940.5 | hammer_pin-3 ↔ hammer-2 |
| 22 | 38940.5 | hammer_pin-2 ↔ hammer-3 |
| 23 | 38312.7 | hammer_pin-4 ↔ hammer-16 |
| 24 | 38312.7 | hammer_pin-3 ↔ hammer-14 |
| 25 | 38312.7 | hammer_pin-2 ↔ hammer-15 |
| 26 | 38312.5 | hammer_pin-1 ↔ hammer-13 |
| 27 | 33379.4 | main_shaft-1 ↔ rotor_disc-2 |
| 28 | 33379.4 | main_shaft-1 ↔ rotor_disc-1 |
| 29 | 33379.4 | main_shaft-1 ↔ rotor_disc-4 |
| 30 | 33379.4 | main_shaft-1 ↔ rotor_disc-3 |
| 31 | 21756.4 | screen_plate-1 ↔ hammer-4 |
| 32 | 21756.4 | screen_plate-1 ↔ hammer-8 |
| 33 | 21756.4 | screen_plate-1 ↔ hammer-12 |
| 34 | 21756.4 | screen_plate-1 ↔ hammer-16 |
| 35 | 17247.4 | screen_plate-1 ↔ casing_lower-1 |
| 36 | 15188.8 | screen_plate-1 ↔ hammer-7 |
| 37 | 15188.8 | screen_plate-1 ↔ hammer-11 |
| 38 | 15188.8 | screen_plate-1 ↔ hammer-15 |
| 39 | 15188.8 | screen_plate-1 ↔ hammer-3 |
| 40 | 14025.1 | rotor_disc-4 ↔ hammer-15 |
| 41 | 14025.1 | rotor_disc-3 ↔ hammer-11 |
| 42 | 14025.1 | rotor_disc-1 ↔ hammer-3 |
| 43 | 14025.1 | rotor_disc-2 ↔ hammer-7 |
| 44 | 14025.1 | rotor_disc-3 ↔ hammer-10 |
| 45 | 14025.1 | rotor_disc-4 ↔ hammer-14 |
| 46 | 14025.1 | rotor_disc-1 ↔ hammer-2 |
| 47 | 14025.1 | rotor_disc-2 ↔ hammer-6 |
| 48 | 14025.1 | rotor_disc-4 ↔ hammer-13 |
| 49 | 14025.1 | rotor_disc-3 ↔ hammer-9 |
| 50 | 14025.1 | rotor_disc-1 ↔ hammer-1 |
| 51 | 14025.1 | rotor_disc-2 ↔ hammer-5 |
| 52 | 14025.1 | rotor_disc-4 ↔ hammer-16 |
| 53 | 14025.1 | rotor_disc-3 ↔ hammer-12 |
| 54 | 14025.1 | rotor_disc-1 ↔ hammer-4 |
| 55 | 14025.1 | rotor_disc-2 ↔ hammer-8 |
| 56 | 3522.0 | frame_base-1 ↔ v_belt-6 |
| 57 | 3522.0 | frame_base-1 ↔ v_belt-6 |
| 58 | 3205.2 | screen_plate-1 ↔ casing_lower-1 |
| 59 | 2969.0 | screen_plate-1 ↔ casing_lower-1 |
| 60 | 2806.5 | screen_plate-1 ↔ casing_lower-1 |
| 61 | 2718.5 | screen_plate-1 ↔ casing_lower-1 |
| 62 | 2704.5 | screen_plate-1 ↔ casing_lower-1 |
| 63 | 2265.5 | screen_plate-1 ↔ casing_lower-1 |

## 整机质量属性

- **质量**: 1238.051 kg
- **体积**: 0.321526 m³  (321526.0 cm³)
- **表面积**: 22.6128 m²
- **重心 (m)**: [0.0957, -0.0031, -0.436]
- **重心 (mm)**: (95.7, -3.1, -436.0)
- **主惯量 (kg·m²)**: [199.81954, 510.50196, 620.36816]

## 组件质量属性 (12 件唯一零件, 按单件质量降序)

| # | 零件 (ModelDoc) | 实例 | 单件 (kg) | 总质量 (kg) | 体积 (cm³) | 表面 (m²) |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `motor_body-2` | ×1 | 503.935 | 503.935 | 69991.0 | 1.5183 |
| 2 | `frame_base-1` | ×1 | 243.220 | 243.220 | 31182.0 | 3.1216 |
| 3 | `casing_upper-1` | ×1 | 79.807 | 79.807 | 79807.0 | 5.2351 |
| 4 | `casing_lower-1` | ×1 | 69.432 | 69.432 | 69432.0 | 4.8777 |
| 5 | `screen_plate-1` | ×1 | 61.907 | 61.907 | 7886.0 | 1.3692 |
| 6 | `main_shaft-1` | ×1 | 53.943 | 53.943 | 6872.0 | 0.328 |
| 7 | `rotor_disc-1` | ×4 | 36.561 | 146.244 | 4657.0 | 0.4307 |
| 8 | `motor_mount-1` | ×1 | 23.731 | 23.731 | 23731.0 | 2.8142 |
| 9 | `driven_pulley-1` | ×1 | 3.524 | 3.524 | 3524.0 | 0.2263 |
| 10 | `hammer-3` | ×16 | 2.997 | 47.952 | 382.0 | 0.0434 |
| 11 | `v_belt-6` | ×1 | 1.107 | 1.107 | 1107.0 | 0.3655 |
| 12 | `hammer_pin-2` | ×4 | 0.814 | 3.256 | 814.0 | 0.0849 |
| | **整机合计** | | | **1238.058** | | |
| | **整机直读 (Phase 4)** | | | **1238.051** | | ✅ 一致 |

## 截图

- iso: `D:\道\道生一\一生二\3D建模Agent\60-实战_Projects\南京-吴鸿轩_锤式破碎机\交付包_最终\渲染图\sw_iso.png`
- front: `D:\道\道生一\一生二\3D建模Agent\60-实战_Projects\南京-吴鸿轩_锤式破碎机\交付包_最终\渲染图\sw_front.png`
- back: `D:\道\道生一\一生二\3D建模Agent\60-实战_Projects\南京-吴鸿轩_锤式破碎机\交付包_最终\渲染图\sw_back.png`
- right: `D:\道\道生一\一生二\3D建模Agent\60-实战_Projects\南京-吴鸿轩_锤式破碎机\交付包_最终\渲染图\sw_right.png`
- left: `D:\道\道生一\一生二\3D建模Agent\60-实战_Projects\南京-吴鸿轩_锤式破碎机\交付包_最终\渲染图\sw_left.png`
- top: `D:\道\道生一\一生二\3D建模Agent\60-实战_Projects\南京-吴鸿轩_锤式破碎机\交付包_最终\渲染图\sw_top.png`
- bottom: `D:\道\道生一\一生二\3D建模Agent\60-实战_Projects\南京-吴鸿轩_锤式破碎机\交付包_最终\渲染图\sw_bottom.png`

---
*道法自然 · 万法归宗 · SolidWorks 实测仿真完成*