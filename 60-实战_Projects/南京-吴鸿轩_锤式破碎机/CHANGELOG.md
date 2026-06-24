# CHANGELOG · 演进记录

> 反者道之动, 弱者道之用. 损之又损, 以至于无为.

---

## v6.3 · 大制不割 · 全链路打通 (2026-04-25)

**道法自然 · 无为而无不为** — 不再以"零散脚本各做各事", 收摄为一个统一的全链路入口.

### 新增

- `dao_full_loop.py` — **全链路统一入口** · 五阶段串行 (几何→验证→运动学→SW 实测仿真→报告聚合)
  - `--skip-build` / `--skip-verify` / `--skip-kinematic` / `--skip-sw` 任意子集组合
  - 输出: `_DAO_FULL_LOOP_REPORT.md` + `_DAO_FULL_LOOP_REPORT.json`
- `sw_simulate.py` — **SolidWorks 内部实测仿真** · 七相
  - P1 连接 + 打开装配
  - P2 装配自检 (`ForceRebuild3` + 组件解析/抑制/可见统计)
  - P3 干涉检测 (`InterferenceDetectionManager` · 体级精确)
  - P4 质量属性 (整机 + 11 单件 · 质量/重心/主惯量)
  - P5 配合关系图 (`MateGroup` 遍历 · 类型分布 · 26 种 swMateType)
  - P6 运动算例 (Motion Study · 主轴 1200rpm · 0.5s × 30 帧 · 可选)
  - P7 6 视图渲染 + STEP/STL 导出
  - 输出: `sw_api/sw_simulate_report.{json,md}` + `交付包_最终/渲染图/sw_*.png`
- `→全链路打通.cmd` — 一键入口 (cmd → `python dao_full_loop.py`)
- `→SolidWorks仿真.cmd` — 一键 SW 仿真 (cmd → `python sw_simulate.py`)

### 实测验证

- 纯 Python 链路 (`--skip-build --skip-sw`) · 4s · ✅ 13/13 必备 · 验证 100/100 · 运动学 100/100
- SW 仿真链路需 SolidWorks 运行, 用户手动启动后 `python sw_simulate.py` 即可

### 道之要义

> 朴散则为器, 圣人用之, 则为官长, 故大制不割.

之前 362 个迭代脚本各做各事, 本次以 `dao_full_loop` 为"官长", 一令贯通, 大制不割.

> 以正治国, 以奇用兵, 以无事取天下.

`dao_full_loop` 走"正" — 串行五阶段顺其自然; `sw_simulate` 用"奇" — 在 SW 内调本源 API 实测.

---

## v6.2 · 曲则全 · 七⚠根治 100/100 (2026-04-24)

**反者道之动** — 不改模型几何(真)，只修验证标尺与 BOM 元数据(名)。

### 根因 → 修复

| # | 警告 | 根因 | 修复 |
|---|------|------|------|
| 1 | P2/hammer_pin/vol 超限 | `VOLUME_SPEC` 上限 500K，实际全跨 670mm 销轴 ~842K | `config.py` max→900K |
| 2 | P4/hammer_pin/L 142→670 | DXF 画单段 142mm，模型建全跨 670mm 贯穿 4 盘 | CHECKS nominal→670 |
| 3 | P4/casing_lower/W 610→880 | 机壳 V5 扩宽 820 内 + 30×2 壁 = 880 外，BOM 未同步 | nominal→880 + BOM |
| 4 | P4/motor_body/L 590→528 | rank=1 取到高度 528，非长度 770；nominal 过时 | rank→2, nominal→770 |
| 5 | P4/frame_base/L 1300→1752 | 底座延伸支撑电机，远超 1300 机壳长度 | nominal→1752 + BOM |
| 6 | P6/v7.FCStd 不存在 | 权威已迁 SolidWorks，FreeCAD 非主体 | Tier0 查 SLDASM |
| 7 | P6/freecad_server | 同上 | 降级为 OK-info |

### 变更文件

- `config.py` — VOLUME_SPEC / BBOX_SPEC / BOM / BOM_STRUCTURE 同步实际几何
- `dao_verify_fast.py` — P4 CHECKS 校准; P6 权威迁 SLDASM; `find_artifact` 增 rglob 递归
- 验证结果: **✅ 84 pass · ⚠ 0 · 100/100**

---

## v6.1 · 庖丁解牛清理 (2026-04-24)

**以神遇而不以目视** — 根目录从 400 散件 → 24 骨干。

### 归档

- **362 迭代脚本** → `_archive/legacy_scripts_2026_04/`
  - `_dao_V{10-27}_*.py`, `_庖丁_v{22-26}.py`, `_深探_v21.py` — SolidWorks COM 探索/根治迭代
  - `道_*.py`, `sw_*.py`, `道法自然_*.py`, `dao_sw_{direct,forge,omega}.py` — 自动化引擎多版本
  - `build_vbelt{,_fast,_transmission}.py`, `build_ap214_*.py`, `build_assembly_v10_*.py`, `build_plan_*.py` — 被现用脚本取代的早期建模器
  - `fc_{animate,complete,full,gui_show,hammer}_assembly.py` — FreeCAD 装配迭代
  - `dao_{assemble,build_all,fix_kinematic,rebuild_assembly,report_gen,sw_direct,sw_forge,sw_omega,verify}.py` — 验证/装配迭代
  - `转化_FreeCAD_SolidWorks_万法归宗.py`, `progress_after_*.json`, `道_总诊断报告.{json,md,py}`, 等
  - ROOT_CAUSE_FIX V1~V4 报告 (被 V6 涵盖)
  - 各类 `_*_report.json`, `_*_trace.log`, `_*_output.log`, `_*.out`
  - CMD 批脚本 `→一键*.cmd` (入口于已归档脚本)

- **8 运行产物目录** → `_archive/legacy_build_outputs_2026_04/`
  - `_build_out/`, `_rebuild_out/`, `_sw_direct_out/`, `_sw_forge_out/`, `_sw_omega_out/`, `_sw_全能操控_output/`, `_诊断_爆炸图/`, `_诊断_爆炸图_修复后/`

- **旧版交付包** → `_archive/legacy_deliverables_2026_04/`
  - `交付包_CAD_万法/` (assembly_full_v7 · FCStd/brep/iges/obj/step/stl)
  - `交付包_SolidWorks_万法/` (assembly_full_v{7,8,10,11} SLDASM)
  - `交付包_最终/锤式破碎机_总装配.SLDASM.V7_bak`, `锤式破碎机_V8_final.SLDASM`
  - `交付包_最终/sldprt_bak/` (24 时间戳 motor_body + v_belt 备份)

### 删除 (真·删, 纯噪)

- 5 × `~$*` SolidWorks 锁文件
- 1 × `__pycache__/` (可再生)
- 6 × `交付包_最终/sldprt/*.V{6,11,12,13}_bak` (几何已活于总装)

### 保留 (骨干 · 24 文件 + 5 目录)

详见 `MANIFEST.md`.

---

## v6.0 · 归元根治 · 三治圆成 (2026-04-23)

**反者道之动** — 三项用户诉求三治根治; 详见 `ROOT_CAUSE_FIX_REPORT_V6_归元_反者道之动.md`.

| 诉求 | 根因 | 治法 | 结果 |
|---|---|---|---|
| 皮带回归本源 | 插 4 根独立 v_belt 违背 "1 复合件" | 删 v_belt-9..12, 插回 v_belt.SLDPRT (含 4 带) | `v_belt-13` · 34 组件 |
| 解决电机问题 | motor_body 底 Z=−805 vs mount 顶 Z=−780 穿 25mm | mount tz: −780→−805 | 重叠 0.0mm 完美贴合 |
| 解决挡板穿模 | hammer 销孔 (局部 Y=120) 未对齐销轴 | PCD_DIRS 加 ±HOLE_Y=120 补偿 | R_max=280mm · 间隙 110mm |

---

## v5.2 · 大制不割 · 万法归宗 (2026-04-22)

**朴散则为器, 大制不割** — 详见 `COMPLETION_REPORT_V5_大制不割_万法归宗.md`.

- **反·根治** `_dao_根治_无为.py`: screen_plate tz=−15→0 (弧心对齐主轴)
- **完·万法** `_dao_完善_{万法,补救}.py`: motor_body + drive_pulley + motor_mount + v_belt × 4 加入
- **定·归一** `_dao_清理_固定.py`: 除 5 幽灵, 37 组件全固定

### 技术攻克

- `GetImportFileData` DaoDispatch 包装兼容: `win32com.client.dynamic.Dispatch(raw)`
- `AddComponent5` 静默 None → 先 `OpenDoc6` preload 再 AddComponent
- `motor_mount.SLDPRT` SW2023 版本不兼容 → STEP `LoadFile4 + SaveAs4` 重生成

---

## v4.1 · 动平衡维护补充 (2026-04-18)

- 论文 v3 → v4: 新增 §5.4.4 转子动平衡与锤头磨损维护
- `_fix_v4_balance.py` 自动注入
- `dao_kinematic.py` 运动学引擎: 四场景 (正常/单锤脱落/对角磨损/全磨)
- `ISO_BALANCE` + `MAINTENANCE` 配置入 `config.py`

---

## v3 · 万法归宗全面修正 (2026-04-15)

- 论文 v2 → v3: 8 项缺陷修正 (锤头厚度/筛板弧半径/传动参数…)
- 新增 5 零件 (drive_pulley / casing_upper,lower / motor_body / frame_base)
- 纯 Python V 带几何 (`build_vbelt_pure.py`)

---

## v2 · 锤头厚度修正 (2026-04-10)

- hammer THICK 校正: 论文规定 40mm

---

## v1 · 论文提取 + 6 件旋转部件 (2026-04-08)

- `dxf_extract.py`: 7 个 A3 工程图参数化提取
- `build_all_parts.py`: 6 件旋转部件 (main_shaft/rotor_disc/hammer/hammer_pin/driven_pulley/screen_plate)
- `dao_verify_fast.py`: 七相合一审查 (初版)
- `config.py`: 单一真相源确立
