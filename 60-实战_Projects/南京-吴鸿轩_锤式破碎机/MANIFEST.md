# MANIFEST · 资产清单

> 圣人总而用之, 其数一也. — 此处汇总项目所有核心资产, 一册可观, 表里相依.

**版本**: v6.3 · 大制不割 · 全链路打通
**日期**: 2026-04-25 (`dao_full_loop.py` + `sw_simulate.py` 入位后)
**总量**: 根 28 文件 + 5 目录 · 归档 ~694 文件 · 交付 42 文件

---

## 一、真相源 (Single Source of Truth)

| 路径 | 用途 | 下游依赖 |
|------|------|---------|
| `config.py` | 全参数中心 (机器/零件/装配位姿/BOM/颜色/动平衡) | 所有 `build_*.py` + `dao_*.py` |
| `DESIGN_PARAMS.json` | 论文全参数结构化提取 | 参考 · 无脚本依赖 |
| `dxf/` (7 × A3) | 工程图源文件 | `dxf_extract.py` |

---

## 二、建模脚本 (11 核心)

| 脚本 | 产出 | 根治迭代 |
|------|------|---------|
| `build_all_parts.py` | 6 件旋转部件 STEP/STL (含 V6 销孔对齐修正) | V6 归元 |
| `build_complete.py` | 5 件结构件 STEP/STL (casing 扩至 820) | V5 完善 |
| `build_pulleys_v2.py` | 带 V 槽 B 型 driven+drive_pulley STEP | V13 |
| `build_vbelt_step.py` | V 带 STEP (YZ 平面, 两轮对中) | V12 对中修正 |
| `build_vbelt_pure.py` | V 带 纯 Python STL (1 复合件含 4 带) | 本源 (V6 回归) |
| `build_motor_y180l4.py` | 电机 Y180L-4 22kW STEP | GB 755-2008 合规 |
| `build_complete_assembly.py` | 整机 STL/OBJ/GLB | 纯 Python, 无 CadQuery 依赖 |
| `merge_vbelt.py` | V 带合入 assembly_complete_v4 | 28→32 件 |
| `dxf_extract.py` | DXF 参数化提取 | → `dxf_params.json` |
| `dxf_synthesize.py` | DXF 反向合成 | 验证用 |
| `viewer.html` | Three.js 浏览器 3D 预览 | 加载 `output_cq/*.glb` |

## 二·补 全链路入口 (v6.3)

| 脚本 | 用途 | 输出 |
|------|------|------|
| `dao_full_loop.py` | **全链路统一入口** · 五阶段串行 | `_DAO_FULL_LOOP_REPORT.{md,json}` |
| `sw_simulate.py` | **SolidWorks 实测仿真** · 七相 (干涉/质量/配合/运动) | `sw_api/sw_simulate_report.{md,json}` + `渲染图/sw_*.png` |
| `sw_probe.py` | SW 直连基础探针 (打开+清单+截图+导出) | `sw_api/sw_probe_log.json` |
| `→全链路打通.cmd` | 一键 cmd 启动 dao_full_loop | — |
| `→SolidWorks仿真.cmd` | 一键 cmd 启动 sw_simulate | — |
| `→SolidWorks直连.cmd` | 一键 cmd 启动 sw_probe | — |

---

## 三、验证/运动学 (2 引擎)

| 脚本 | 职责 | 评分 |
|------|------|------|
| `dao_verify_fast.py` | 七相合一审查 (DXF/几何/装配/交叉/文档/FreeCAD/动力学) | 99/100 |
| `dao_kinematic.py` | 运动学 + 动平衡四场景 + 临界转速 + 离心载荷 | 100/100 |

---

## 四、报告 (权威状态)

| 报告 | 内容 |
|------|------|
| `ROOT_CAUSE_FIX_REPORT_V6_归元_反者道之动.md` | **V6 最新**: 三治根治 · 皮带回归/电机贴合/锤头退穿 |
| `COMPLETION_REPORT_V5_大制不割_万法归宗.md` | V5 完善: 37 件全锚定, 传动链加入 |
| `FIGURE_ANALYSIS.md` | 7 张工程图分析 |
| `IMAGE_CATALOG.json` | 图片目录索引 |
| `progress.json` | 滚动进度快照 |
| `南京-吴鸿轩_v4_动平衡维护补充.docx` | 论文 v4 (新增 §5.4.4 动平衡维护) |

---

## 五、最终交付 (`交付包_最终/`)

| 文件 | 尺寸 | 用途 |
|------|------|------|
| `锤式破碎机_总装配.SLDASM` | 554 KB | **主装配 34 件** (V6 归元后) |
| `assembly_structured.step` | 1.2 MB | 跨平台单一 STEP |
| `sldprt/` (13 SLDPRT + 2 SLDASM) | 2.1 MB 合计 | 子零件源文件 |
| `工程图/` (4 × SLDDRW+PDF) | ~400 KB | 总装/筛板/转轴/锤头 |
| `南京-吴鸿轩_v4_动平衡维护补充.docx` | 2.6 MB | 论文终版 |
| `README_交付说明.md` | 3 KB | 交付说明 |

---

## 六、产物 (`output_cq/`, `sw_api/`)

| 目录 | 文件数 | 说明 |
|------|-------|------|
| `output_cq/` | 54 (17.5 MB) | 14 × STEP + 14 × STL + GLB/OBJ + 参数 JSON + BOM |
| `sw_api/` | 9 (9.8 MB) | SolidWorks COM TypeLib 反向索引 `INDEX.json` (2.9 MB) |

---

## 七、归档 (`_archive/`, 146.5 MB, 694 文件)

| 子目录 | 内容 |
|--------|------|
| (早期根目录归档) | v2/v3 docx, early fc_*/build_vbelt*, gallery html, 闭环报告 |
| `legacy_scripts_2026_04/` | **362 迭代脚本**: `_dao_*`, `_V{10-27}_*`, `_庖丁_v{22-26}`, `道_*`, `sw_*`, `dao_sw_*`, `道法自然_*` |
| `legacy_build_outputs_2026_04/` | 8 运行输出目录: `_build_out/`, `_rebuild_out/`, `_sw_{direct,forge,omega}_out/`, `_sw_全能操控_output/`, `_诊断_爆炸图{,_修复后}/` |
| `legacy_deliverables_2026_04/` | 旧版交付: `交付包_CAD_万法/`, `交付包_SolidWorks_万法/`, 旧 SLDASM (V7_bak, V8_final), 24 个时间戳 SLDPRT 备份 |

**归档原则**: 任一归档文件无根治/建模价值, 纯属迭代过程产物; 如需复查 SolidWorks COM 探索历程, 可按 `_dao_V{10..16}*` 等命名线索进入 `legacy_scripts_2026_04/`.

---

## 八、数值体量

| 维度 | 清理前 | 清理后 | 变化 |
|------|--------|--------|------|
| 根目录文件 | 383 | 24 | −359 (−93.7%) |
| 根目录目录 | 17 | 5 | −12 |
| 总文件数 | 836 | ~827 | −9 (锁文件/V_bak 纯删) |
| 根目录可读性 | 低 (海量 `_xxx`) | 高 (一目可览) | 质变 |

**"损之又损, 以至于无为. 无为而无不为."** — 删却 359 件表层噪音, 真骨完整留存, 可构可验可交付.
