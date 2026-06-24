# 锤式破碎机 — 参数化建模工程

> **核心叙事**: 论文全文提取 → DXF 工程图 → CadQuery 参数化建模 → 12 种零件建模 + V带传动 + 整机装配 → SolidWorks 活体直连 → 六阶段归元根治 → **全链路打通 + SW 实测仿真**
>
> **当前阶段**: **v6.3 · 大制不割 · 全链路打通** (2026-04-25)
> **最新里程碑**: 五阶段统一入口 (`dao_full_loop.py`) · SW 内部实测仿真七相 (`sw_simulate.py`) · 4s 纯 Python 链路 100/100
> **最终交付**: `交付包_最终/锤式破碎机_总装配.SLDASM` (554KB · V6 根治后) + 工程图 PDF/SLDDRW

---

## 项目身份证

| 维度 | 内容 |
|------|------|
| **机器** | 单转子锤式破碎机 (Single-Rotor Hammer Crusher) |
| **论文** | 南京工业职业技术大学 · 吴鸿轩 毕业论文 (2025) |
| **整机外形** | 1300 × 820 × 860 mm |
| **转子** | Ø700 mm · 1200 r/min · 4 盘 × 4 向 = 16 锤头 |
| **零件** | 12 种模型 · BOM 34 件实例 (含 4 V 带复合为 1 件) |
| **电机** | Y180L-4 · 22 kW · 1470 r/min |
| **传动** | B 型 V 带 × 4 根 · 中心距 600 mm · 传动比 1.23 |
| **建模引擎** | CadQuery 2.6 + trimesh + SolidWorks 2023 (COM 直连) |

---

## 目录结构 (清洁态)

```
南京-吴鸿轩_锤式破碎机/
├── README.md                                         ← 本文件
├── MANIFEST.md                                       ← 文件清单 · 用途索引
├── CHANGELOG.md                                      ← 演进记录
├── config.py                                         ← 统一参数中心 (单一真相源)
│
├── ROOT_CAUSE_FIX_REPORT_V6_归元_反者道之动.md       ← 最新根治报告
├── COMPLETION_REPORT_V5_大制不割_万法归宗.md         ← V5 完善报告
├── DESIGN_PARAMS.json                                ← 论文全参数结构化
├── IMAGE_CATALOG.json / FIGURE_ANALYSIS.md           ← 图纸索引
├── progress.json                                     ← 进度快照
├── 南京-吴鸿轩_v4_动平衡维护补充.docx                ← 论文 v4
│
├── build_all_parts.py                                ← 6 件旋转部件 CadQuery
├── build_complete.py                                 ← 5 件结构件 CadQuery
├── build_complete_assembly.py                        ← 整机 STL/OBJ/GLB 合成
├── build_pulleys_v2.py                               ← 带 V 槽 B 型皮带轮 (V13)
├── build_vbelt_step.py                               ← V 带 STEP (V12 修正版)
├── build_vbelt_pure.py                               ← V 带纯 Python STL (原本源)
├── build_motor_y180l4.py                             ← 电机 Y180L-4
├── merge_vbelt.py                                    ← V 带合入装配
├── dxf_extract.py / dxf_synthesize.py                ← DXF 参数提取/合成
├── dao_verify_fast.py                                ← 七相合一验证
├── dao_kinematic.py                                  ← 运动学/动平衡
├── viewer.html                                       ← Three.js 3D Web 预览
│
├── dxf/                        ← 源: 7 个 A3 工程图
├── output_cq/                  ← 产物: STEP / STL / GLB (CadQuery 输出)
├── sw_api/                     ← SolidWorks COM API 类型库缓存
├── 交付包_最终/                ← 最终交付 (V6 归元态)
│   ├── 锤式破碎机_总装配.SLDASM              ← 主装配 (34 件)
│   ├── assembly_structured.step              ← 单一 STEP (跨平台)
│   ├── 南京-吴鸿轩_v4_动平衡维护补充.docx
│   ├── README_交付说明.md
│   ├── sldprt/                               ← 13 件 SLDPRT + 2 SLDASM
│   ├── 工程图/                               ← 4 份 SLDDRW + PDF
│   └── 论文截图/
│
└── _archive/                   ← 归档
    ├── (早期 docx/fc 脚本/build_vbelt/gallery)
    ├── legacy_scripts_2026_04/       ← 362 迭代脚本 (_dao_*/sw_*/道_*/庖丁_v*)
    ├── legacy_build_outputs_2026_04/ ← 8 运行输出目录 (_build_out/_sw_*_out/…)
    └── legacy_deliverables_2026_04/  ← 旧版交付包 (CAD_万法/SolidWorks_万法)
```

---

## 快速开始

### 一键 · 全链路打通 (推荐)

```bash
# 五阶段串行: 几何 → 验证 → 运动学 → SW 实测仿真 → 报告
python dao_full_loop.py                          # 完整全链路
python dao_full_loop.py --skip-build --skip-sw   # 仅纯 Python (4s · 100/100)
python dao_full_loop.py --skip-build             # 复用几何, 跑 SW 仿真
```

或双击 `→全链路打通.cmd` (Windows).

### 分步执行

```bash
# ── 1. 几何重建 (CadQuery → STEP/STL) ───────────────────────
python build_all_parts.py              # 6 件旋转部件
python build_complete.py               # 5 件结构件
python build_pulleys_v2.py             # 带 V 槽皮带轮 (V13)
python build_vbelt_step.py             # V 带 STEP (V12 对中修正)
python build_motor_y180l4.py           # 电机

# ── 2. 整机装配 (纯 Python) ─────────────────────────────────
python build_complete_assembly.py      # → STL/OBJ/GLB
python merge_vbelt.py                  # 合并 V 带进装配

# ── 3. 验证 ────────────────────────────────────────────────
python dao_verify_fast.py              # 七相合一 · 约 3 秒 · 100/100
python dao_kinematic.py                # 运动学 + 动平衡四场景

# ── 4. SolidWorks 实测仿真 (需 SW 运行) ────────────────────
python sw_simulate.py                  # 七相: 干涉/质量/配合/运动算例/渲染
python sw_simulate.py --skip-motion    # 无 Motion 插件时

# ── 5. 浏览器预览 ──────────────────────────────────────────
python -m http.server 8080             # 浏览 http://localhost:8080/viewer.html
```

SolidWorks 活体装配 (V6 根治) 由 `00-本源_Origin/_dao_归元_根治.py` 直接操作 SW COM 完成; 结果落地于 `交付包_最终/锤式破碎机_总装配.SLDASM`. 仿真验证由 `sw_simulate.py` 完成, 报告写入 `sw_api/sw_simulate_report.{json,md}`.

---

## V6 归元根治摘要

三治应对三诉求 (详见 `ROOT_CAUSE_FIX_REPORT_V6_归元_反者道之动.md`):

| 诉求 | 根因 | 治法 | 结果 |
|---|---|---|---|
| **皮带回归本源** | 4 根独立 v_belt 违背"1 复合件"本源 | 删 v_belt-9..12,插回 v_belt.SLDPRT (单件含 4 带) | `v_belt-13` · 34 组件 ✓ |
| **电机贴合** | mount 顶 Z=−780 vs motor 底 Z=−805 穿 25mm | mount tz −780 → −805 | 重叠 **0.0mm** 完美贴合 ✓ |
| **锤头穿筛板** | hammer 销孔 (局部 Y=120) 未对齐销轴 → world R_max=400 > Ri=390 | PCD_DIRS 补 ±HOLE_Y=120 项 | **R_max=280mm** 间隙 110mm ✓ |

---

## 零件与 BOM

**旋转部件 (6 种)**

| 件号 | 名称 | 材料 | 数量 | 关键尺寸 |
|------|------|------|------|----------|
| 1 | 主轴 | 45 钢 | 1 | Ø60-80-90 L=1145 |
| 2 | 转子盘 | Q345 | 4 | Ø500×25 · PCD440 |
| 3 | 锤头 | ZGMn13 | 16 | 梯形 180×80×40 · Ø40 孔 |
| 4 | 销轴 | 45 钢 | 4 | Ø40 L=670 |
| 5 | 从动带轮 | HT200 | 1 | B 型 4 槽 OD240 PD220 孔Ø70 |
| 6 | 筛板 | 不锈钢 | 1 | 弧 120° Ri=390 t=12 B=800 |

**整机结构 (6 种)**

| 件号 | 名称 | 材料 | 数量 | 关键尺寸 |
|------|------|------|------|----------|
| 7 | 主动带轮 | HT200 | 1 | B 型 4 槽 OD190 PD180 孔Ø55 |
| 8 | 下机壳 | Q235 | 1 | 960×820×460 壁 30 |
| 9 | 上机壳 | Q235 | 1 | 960×820×610 + 进料斗 |
| 10 | 电机 | Y180L-4 | 1 | 22 kW · 590×280×350 |
| 11 | 机架底座 | Q235 | 1 | 1300×820×520 + 4 立柱 |
| 12 | V 带 | B 型橡胶 | 4 (复合为 1 件) | C=600 mm · 传动比 1.23 |

---

## 万法归宗 · 七相审查

`dao_verify_fast.py` 七相合一:

| Phase | 检查项 |
|-------|--------|
| 1 | DXF 源完整性 (7 DXF + 关键参数) |
| 2 | 几何质量 (11 零件 STL 面片/体积/bbox) |
| 3 | 装配完整性 (BOM + 产出文件清单) |
| 4 | DXF↔Model 交叉验证 (17 项尺寸) |
| 5 | 论文文档 (v2~v4 docx + 审查报告) |
| 6 | FreeCAD 实机 (FCStd + 截图, 可选) |
| 7 | 运动学 + 动平衡四场景 + 临界转速 + 传动链 |

**最新评分: 78✅ 1⚠️ · 99/100 · 零件覆盖 11/11 · 运动学 100/100**

---

## 装配坐标系

原点 = 主轴左端中心线. X=轴向(左→右), Y=水平横向, Z=竖直(上 +). 详细几何推演见 `config.py:221-299`.

---

## 历史脚本

本次清理 (2026-04-24) 将 362 个迭代脚本归档至 `_archive/legacy_scripts_2026_04/`; 若需考察某脚本演进历史, 可进入该目录按名查阅. 三大类别:

- `_dao_*`, `_V*_*`, `_庖丁_v*` — SolidWorks COM 迭代调试
- `道_*`, `sw_*`, `道法自然_*` — 早期版本的自动化引擎
- `build_vbelt.py`, `build_ap214_*`, `build_assembly_*` — 被现用脚本取代的早期建模器

---

*道法自然 · 万法归宗 · 锚定本源 · 归元毕 · 三治圆成 · 反者道之动 · 大制不割 · 全链路打通 — 南京吴鸿轩锤式破碎机建模引擎 v6.3*
