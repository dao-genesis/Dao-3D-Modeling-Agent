# 🜂 dao 本源五器 · 锤式破碎机自验证

> 只使用 00-本源_Origin 的模块, 脱离项目脚本独立审查

> 时间: 2026-04-18 01:51:00
> 评分: **100/100** (✅20 ⚠️0 ❌0)

---

## P1 — DXF 工程图 (dao_dxf)

*7 passes · 0 warnings · 0 failures*

| 状态 | 标签 | 说明 |
|------|------|------|
| ✅ PASS | `dxf/assembly_A3` | assembly_A3.dxf: 187 lines · 106 texts · W=394mm · 0 diameters |
| ✅ PASS | `dxf/driven_pulley_A3` | driven_pulley_A3.dxf: 32 lines · 38 texts · W=390mm · 3 diameters |
| ✅ PASS | `dxf/hammer_A3` | hammer_A3.dxf: 61 lines · 40 texts · W=390mm · 1 diameters |
| ✅ PASS | `dxf/hammer_pin_A3` | hammer_pin_A3.dxf: 52 lines · 35 texts · W=390mm · 1 diameters |
| ✅ PASS | `dxf/rotor_disc_A3` | rotor_disc_A3.dxf: 50 lines · 38 texts · W=391mm · 4 diameters |
| ✅ PASS | `dxf/screen_plate_A3` | screen_plate_A3.dxf: 49 lines · 40 texts · W=390mm · 2 diameters |
| ✅ PASS | `dxf/shaft_A3` | shaft_A3.dxf: 116 lines · 46 texts · W=640mm · 4 diameters |

## P2 — STL/GLB 网格 (dao_mesh)

*7 passes · 0 warnings · 0 failures*

| 状态 | 标签 | 说明 |
|------|------|------|
| ✅ PASS | `stl/main_shaft` | 2564 faces · bbox=(1145.0, 90.0, 90.0) · vol=6.87×10⁶mm³ |
| ✅ PASS | `stl/rotor_disc` | 3040 faces · bbox=(500.0, 499.8, 25.0) · vol=4.66×10⁶mm³ |
| ✅ PASS | `stl/hammer` | 520 faces · bbox=(80.0, 180.0, 40.0) · vol=0.38×10⁶mm³ |
| ✅ PASS | `stl/hammer_pin` | 2264 faces · bbox=(142.0, 40.0, 40.0) · vol=0.15×10⁶mm³ |
| ✅ PASS | `stl/driven_pulley` | 1004 faces · bbox=(90.0, 240.0, 239.9) · vol=3.71×10⁶mm³ |
| ✅ PASS | `stl/screen_plate` | 4530 faces · bbox=(603.0, 402.0, 800.0) · vol=7.88×10⁶mm³ |
| ✅ PASS | `glb/assembly_v4` | 50342 faces · bbox=(1873, 1115, 1200)mm · vol=256.8×10⁶mm³ |

## P3 — 论文 docx (dao_docx)

*6 passes · 0 warnings · 0 failures*

| 状态 | 标签 | 说明 |
|------|------|------|
| ✅ PASS | `docx/paragraphs` | 672 段落 |
| ✅ PASS | `docx/images` | 9 图片 (共 2518KB) |
| ✅ PASS | `docx/tables` | 4 表格 |
| ✅ PASS | `docx/figures` | 8 图题 |
| ✅ PASS | `docx/sections` | 222 章节 |
| ✅ PASS | `docx/fig2.2` | 图2.2 (整机结构) 存在 |

---

*道法自然 · 万法归宗 · 锚定本源 · 闭环自验证*
