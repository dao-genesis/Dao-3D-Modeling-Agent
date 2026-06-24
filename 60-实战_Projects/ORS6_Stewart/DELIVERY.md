# ORS6 VAM 摇匀器 · 交付清单 (DELIVERY)

> 反者道之动, 弱也者道之用也. 数字真相已立, 物理落地可依.

- **版本**: `ORS6_Stewart` v2.2.3
- **时间**: 2026-05-10 16:25
- **pytest**: 341/341 PASS (IK=76, geometry=265)
- **装配双引擎**: CadQuery (5/5 OK) · FreeCAD 1.0.2 (5/5 OK + GUI 截图 5/5)
- **final_regression**: **7/7 PASS** (pytest · health · viewer · summaries · FCStd · PNG · clean)
- **RPC audit**: 5/5 PASS (`dao_fc audit` · 25 obj/pose 全过 RPC :9875)

## 〇 · 反者道之动 · v2.2.3 三反思 (2026-05-10)

> 名可名, 非常名. 损之又损, 以至于无为.
>
> 三轮迭代:
> - **v2.2.1**: 修 Tray 跟随 Receiver 的 RECV_PARTS · 测试栈死锁 · 双 Mod 冲突
> - **v2.2.2 反思**: Tray 是 ESP32 内部不可见盒, 不该跟 receiver — 退 RECV+加 hidden;
>   Receiver 不与 Twist_Body 互排 — 移 variant_group, 两件同显
> - **v2.2.3 三思**: L/R_Pitcher placement — STL 自坐 X≈±15 中线前方, 未平移 frame top.
>   trimesh 勘 STL servo horn 位 (±7.5, +9.5, +51.75), 同 main Arm `_arm_trsf` 模式
>   piv→shaft 平移 + IK 旋转, 修后双 Pitcher 物理在 frame top X=±99.6 servo shaft 处.

| # | 弊 (病) | 因 (根) | 刀 (修) | 验 (证) |
|---|---------|---------|---------|---------|
| 1 | **Tray 飘 receiver 顶** (旧 v2.2.0) | Tray 不在 RECV_PARTS, STL 自坐放 Z=24..79 而 Receiver 升至 HOME_H | v2.2.1: Tray 加入 RECV_PARTS, 跟随 Receiver pose | 5 pose 截图 Tray 跟随; 双留 (`_archive/screenshots_pre_tray_fix_20260509/`) |
| 2 | **Tray 仍飘错位** (v2.2.1 后) | Tray 是 Base 内部 ESP32 电源盒, **不该可见** (SR6_ARCHITECTURE p117 "内部不可见") | v2.2.2: Tray/Tray_ScrewJack/Tray_XT60 退 RECV_PARTS, 加入 DEFAULT_HIDDEN | RPC obj list 验 25 obj/pose 无 Tray; 截图 Tray 不显 |
| 3 | **Receiver 不显** | `VARIANT_GROUPS["receiver"]` 错把 Receiver 与 Twist_Body 当互斥 (default Twist_Body), 自动隐 Receiver | v2.2.2: 移除 receiver variant_group, Receiver 不再 auto-hide; 与 Twist_Body 同显 (透 30%) | RPC obj list 含 Receiver 蓝紫 (0x2a3a6a · 透 30%); 截图圆环可见 |
| 4 | **L/R_Pitcher 重叠中线前方** | `assembly.py` 仅做 IK rotation 不平移 → STL 自坐 X≈±15 留在中线 (非 frame top X=±99.6) | v2.2.3: 添 PITCHER_PIVOT_STL=(7.5, 9.5, 51.75), 同 main Arm `_arm_trsf(piv, shaft, delta)` 模式: STL servo horn → frame top servo shaft 平移 + IK 旋转 | RPC obj list 验 L_Pitcher world X=[-138.8, -78.6] · R_Pitcher X=[+78.6, +138.8] · 各在 frame top ±99.6 处 |
| 5 | **双 Mod 冲突** | `FreeCAD-MCP` (旧 socket) 与 `FreeCADMCP` (新 XMLRPC :9875) 命名空间相撞 | 旧 Mod 移至 `%APPDATA%\FreeCAD\Mod\_archive_FreeCAD-MCP_legacy_20260509\` | RPC :9875 通后 5 doc 无碰撞 |
| 6 | **pytest collection 错** | `viewer/server.py:61` module 级 `int(sys.argv[1])`; pytest 收集 argv[1]=`.py` 路径 → ValueError | 加 `argv[1].isdigit()` 守门 | `pytest .` 收 341 件全过 |
| 7 | **regression 二关挂死 + 七关误报** | (a) `subprocess.run(health)` tty 死锁; (b) `.pytest_cache` 自然之物被当 unexpected dirs | (a) `s_health` in-process; (b) `_TOOL_CACHES` 容忍 4 类缓存 | `final_regression` **7/7 PASS** |

**视觉三证** — home pose 截图 (`output/screenshots/ORS6_home.png`):

- **修前 v2.2.0** `_archive/screenshots_pre_tray_fix_20260509/` (86~94KB)
  · Tray 飘高 + Receiver 不显 + L/R_Pitcher 重叠中线前方 (中央大 silver 板)
- **v2.2.2 修后** (78~82KB) · Tray 不见, Receiver 蓝透显示, 但 L/R_Pitcher 仍中线前方
- **v2.2.3 三反思** (84~92KB · 当前) · Tray 不见, Receiver 透紫圆环, **L/R_Pitcher 移到 frame top 各侧**, 6 silver rod 严

**改动文件** (3 file 净改 ~30 line):

- `parts.py`:
  - `VARIANT_GROUPS` 移除 `receiver` entry (4 line)
  - `DEFAULT_HIDDEN` 加 Tray 三件 (1 line)
  - `RECV_PARTS` 移除 Tray 三件 (1 line)
- `assembly.py`:
  - 加 `PITCHER_PIVOT_STL = (7.5, 9.5, 51.75)` (1 line + 4 注释)
  - L/R_Pitcher CadQuery placement: 用 `_arm_trsf(piv, shaft, delta)` (~10 line)
  - L/R_Pitcher FreeCAD placement: piv→shaft `App.Placement` (~7 line)
- `viewer/server.py`: `argv[1].isdigit()` 守门 (1 line)
- `tools/final_regression.py`: in-process health · 缓存容忍 (~10 line)

## 〇β · 反者道之动 · v2.2.1 历程 (2026-05-09)

> 损之又损. 第一刀: Tray 加 RECV_PARTS (后被 v2.2.2 反思).

四关已修, 数字与物理皆归一:

| # | 弊 (病) | 因 (根) | 刀 (修) | 验 (证) |
|---|---------|---------|---------|---------|
| 1 | **托盘悬空** | `Tray` 不在 `RECV_PARTS`, 不随 receiver pose 平移 | `parts.py` `RECV_PARTS` 加入 `Tray`/`Tray_ScrewJack`/`Tray_XT60` | 5 pose 截图 Tray 跟 Receiver 同步, 双留 (`_archive/screenshots_pre_tray_fix_20260509/`) |
| 2 | **双 Mod 冲突** | `FreeCAD-MCP` (旧 socket) 与 `FreeCADMCP` (新 XMLRPC :9875) 命名空间相撞 | 旧 Mod 移至 `%APPDATA%\FreeCAD\Mod\_archive_FreeCAD-MCP_legacy_20260509\` | RPC :9875 通后 `dao_fc.list_documents()` 5 doc 无碰撞 |
| 3 | **pytest collection 错** | `viewer/server.py:61` module 级 `int(sys.argv[1])`; pytest 收集时 argv[1]=`.py` 路径 → ValueError | 加 `argv[1].isdigit()` 守门, 仅数字才覆盖默认端口 | `pytest .` 收集 341 件全过 (2.70s) |
| 4 | **regression 二关挂死 + 七关误报** | (a) `subprocess.run(health)` 在共享 tty 环境通信死锁; (b) `.pytest_cache` 自然之物被当作 unexpected dirs | (a) `s_health` 改 in-process `import cli.cmd_health` + `redirect_stdout`; (b) `s_repo_clean` 加 `_TOOL_CACHES` 容忍 `__pycache__/.pytest_cache/.mypy_cache/.ruff_cache` | `final_regression` **7/7 PASS** (pytest · health 18.5s · viewer · summaries · FCStd · PNG · clean) |

**视觉双证** — 修前/修后 home pose 截图共留:

- 修前 (旧): `_archive/screenshots_pre_tray_fix_20260509/ORS6_*.png` (86~94KB · Tray 飘于 Receiver 顶半身高)
- 修后 (新): `output/screenshots/ORS6_*.png` (58~65KB · Tray 紧贴 Receiver 后上方, 随 pose 同变换)

**改动文件** (3 file 净改 ~12 line):

- `viewer/server.py`: PORT 解析守门 (1 line)
- `tools/final_regression.py`: 二关 in-process · 七关缓存容忍 (~10 line)
- `output/_freecad_gui_summary.json`: timestamp + colored=25 + png_size 同步真值

(Tray bug 本身的 `parts.py` `RECV_PARTS` 修补已先期完成, 此次主修测试栈)

## 一 · 代码真相 (数字)

| 模块 | 作用 | 行数 |
|------|------|------|
| `parts.py` | — | 363 |
| `kinematics.py` | — | 490 |
| `geometry.py` | — | 493 |
| `assembly.py` | — | 649 |
| `verify.py` | — | 70 |
| `analysis.py` | — | 456 |
| `poses.py` | — | 39 |
| `cli.py` | — | 301 |

**双真相架构**:
- `kinematics.py` ← firmware 1:1 移植 (ESP32 .ino), 控制层真相
- `geometry.py` ← 物理 3D 真相 (rod=175mm 严格), 6 锚点反向求解

## 二 · 5 关键 pose 装配 (CadQuery + FreeCAD)

### CadQuery + OCP (Python 本地)

| Pose | T-Code | STEP (B) | STL (B) | rod Δ max (mm) |
|------|--------|----------|---------|----------------|
| ✓ home | `5000,5000,5000,5000,5000,5000` | 27,423 | 10,682,584 | 0.000000 |
| ✓ forward | `5000,9999,5000,5000,5000,5000` | 53,357 | 10,699,184 | 0.000000 |
| ✓ side_right | `5000,5000,9999,5000,5000,5000` | 62,058 | 10,655,984 | 0.000000 |
| ✓ pitch_up | `5000,5000,5000,5000,5000,9999` | 76,171 | 10,699,884 | 0.000000 |
| ✓ roll_left | `5000,5000,5000,5000,0,5000` | 27,562 | 10,670,384 | 0.000000 |

**总计**: 5/5 OK · 均 rod=175mm 严

### FreeCAD 1.0.2 (实机 GUI live)

_生成_: 2026-05-09 19:13:47 · _耗时_: 2.36s

| Pose | FCStd (KB) | STEP (KB) | parts | duration |
|------|------------|-----------|-------|----------|
| ✓ home | 1,570 | 27 | 25 | 0.76s |
| ✓ forward | 1,589 | 52 | 25 | 0.37s |
| ✓ side_right | 1,596 | 61 | 25 | 0.36s |
| ✓ pitch_up | 1,602 | 74 | 25 | 0.4s |
| ✓ roll_left | 1,571 | 27 | 25 | 0.44s |

**总计**: 5/5 OK · .FCStd 可双击 GUI 打开

**FreeCAD CN-path 足跡**: FreeCADCmd 不能读中文 .py argv, 但能读中文 STL 与写中文 output. 一键脚本 `tools/freecad_run.ps1` mirror 包到 `C:\Temp\ORS6_FC\ASCII path 后调 FreeCADCmd.

### FreeCAD GUI 截图 (实机可视化真相)

_生成_: 2026-05-09 22:38:17 · _耗时_: 6.03s

GUI mode 后处理接手 headless 装配产出的 FCStd, 后为每个零件设颜色 · 中央 Receiver 设透明度 30% · isometric 视角 fitAll · 渲染 1200x900 PNG · doc.save() 持久化颜色.

| Pose | colored | PNG | duration |
|------|---------|-----|----------|
| ✓ home | 25/25 | 59 KB | 1.97s |
| ✓ forward | 25/25 | 58 KB | 0.92s |
| ✓ side_right | 25/25 | 58 KB | 1.01s |
| ✓ pitch_up | 25/25 | 64 KB | 1.08s |
| ✓ roll_left | 25/25 | 65 KB | 1.05s |

**总计**: 5/5 OK · 截图位于 `output/screenshots/ORS6_<pose>.png`

一键重生成：

```powershell
pwsh -File ORS6_Stewart\tools\freecad_gui_run.ps1
```


## 三 · 几何自验 V1-V12

| ID | 检查 | 结果 | 细节 |
|----|------|------|------|
| V_LowerLeft_rod175 | - | ✓ | `rod=175.0mm, target=175, Δ=+0.0000mm` |
| V_UpperLeft_rod175 | - | ✓ | `rod=175.0mm, target=175, Δ=+0.0000mm` |
| V_LeftPitch_rod175 | - | ✓ | `rod=175.0mm, target=175, Δ=+0.0000mm` |
| V_RightPitch_rod175 | - | ✓ | `rod=175.0mm, target=175, Δ=+0.0000mm` |
| V_UpperRight_rod175 | - | ✓ | `rod=175.0mm, target=175, Δ=+0.0000mm` |
| V_LowerRight_rod175 | - | ✓ | `rod=175.0mm, target=175, Δ=+0.0000mm` |
| V7_main_anchor_local_Y_sym | - | ✓ | `LL_local_y=+0.000 LR_local_y=+0.000` |
| V8_main_anchor_local_X_antisym | - | ✓ | `LL_local_x=-68.000 LR_local_x=+68.000` |
| V9_pitch_anchor_local_Y_antisym | - | ✓ | `LP_local_y=+53.353 RP_local_y=-53.353` |
| V10_pitch_anchor_local_X_zero | - | ✓ | `LP_local_x=+0.000 RP_local_x=+0.000` |
| V11_fw_vs_3d_angle_divergence | - | ✓ | `max_diff=0.0070° (informational)` |
| V12_all_rods_reachable | - | ✓ | `max_residual=0.0000mm` |

## 四 · 装配自验 (V1-V8)

- ✓ **V1_coord_consistency**: PASS
- ✓ **V2_frame_symmetry**: PASS
- ✓ **V3_arm_pivot**: PASS
- ✓ **V4_receiver_center**: PASS
- ✓ **V5_rect_spacing**: PASS
- ✓ **V6_part_count**: PASS
- ✓ **V7_home_height**: PASS
- ✓ **V8_ik_constants**: PASS

## 五 · 物理交付物

- **31 STL 打印件**: `STLs` (符号链接到 `ORS6-VAM饮料摇匀器/SR6资料.../STLs`)
- **自制 ESP32_Mount.stl**: `ORS6-VAM饮料摇匀器/custom_parts/`
- **5 pose STEP** (CadQuery): `output/ORS6_{label}.step` · 工业标准
- **5 pose STL** (CadQuery): `output/ORS6_{label}.stl` · 装配实例
- **5 pose FCStd** (FreeCAD): `output/ORS6_{label}.FCStd` · 可双击 FreeCAD GUI 打开 · 含颜色
- **5 pose STEP** (FreeCAD): `output/ORS6_{label}.step` (到1.7MB FCStd 伴生, 含装配树)
- **5 pose PNG** (FreeCAD GUI 截图): `output/screenshots/ORS6_{pose}.png` 1200×900 isometric
- **BOM**: [`BOM.md`](./BOM.md) — 31 件 + 6 舵机 + 螺栓 + 电子器件

## 六 · 使用入口

```bash
# 核心命令 (8 子命令)
python -m ORS6_Stewart health       # 健康检查
python -m ORS6_Stewart verify       # 数值自验 (V1-V8 + V1-V12)
python -m ORS6_Stewart build home   # 装配 HOME pose
python -m ORS6_Stewart pose 5000 5000 5000 5000 5000 5000
python -m ORS6_Stewart motion       # 15 pose 动画
python -m ORS6_Stewart analyze      # 质量/工作空间/间距
python -m ORS6_Stewart serve 8871   # Three.js 3D 查看器

# 查看器 API (18 端点)
# GET /api/instances             — 3D 装配 (默认 rod=175mm)
# GET /api/instances?geom=firmware — 旧 firmware 2D 兼容
# GET /api/rods_3d?L0=&L1=&...   — 物理真相杆几何
# GET /api/geometry_verify       — V1-V12 自验
# GET /api/anchors               — 6 锚点 (local + world)
```

### FreeCAD 一键启动 (产生实机装配 FCStd + STEP + GUI 截图)

```powershell
# 1) headless 5 pose 装配 (FCStd + STEP)
pwsh -File ORS6_Stewart\tools\freecad_run.ps1

# 2) GUI 后处理: 设颜色 + 1200x900 isometric 截图
pwsh -File ORS6_Stewart\tools\freecad_gui_run.ps1

# 产出:
#   output/ORS6_<pose>.FCStd      (含颜色, 双击 GUI 打开)
#   output/ORS6_<pose>.step       (工业标准 STEP)
#   output/screenshots/ORS6_<pose>.png  (1200×900 isometric)
#   output/_freecad_*.log + _freecad_*_summary.json
```

## 七 · 残缺 & 已知局限

- **STL 缺失**: 0 件 (全齐)
- **pitch 舵机 2D 近似**: firmware 用平面近似 pitch L-bent arm, 极限 pose 有 ~0.5° 漂移 (数值但非物理). 数字真相已透明记录.
- **workspace thrust_up/down**: 个别 pose 超 SR6 球面 IK 极限, 属设计不可达, 已标 `reachable=False`.
- **CN-path FreeCAD argv**: FreeCADCmd 本身不能读中文 .py argv (Win mbcs surrogate). 已与 `tools/freecad_run.ps1` mirror 脚本解决 — STL/output 仍可中文路径.

## 八 · 下一步 (物理落地清单)

- [ ] 按 BOM.md 订购舵机 (6× DS3225)
- [ ] 按 BOM.md 订购 M5×175mm 杆件 (6×, 双端球头)
- [ ] 打印 22 默认打印件 (隐藏 9 件变体)
- [ ] 组装 Base + L/R_Frame (矩形框架, 间距 199.2mm)
- [ ] 安装 6 舵机到槽位 (Z=46mm pivot)
- [ ] 装 4 主臂 + 2 pitch 臂 (镜像方向正确)
- [ ] 连 6 杆到 Receiver (4 main 共享 Y=0 bolt + 2 pitch 独立 bolt)
- [ ] 闸 ESP32 固件 (TempestMAx fork)
- [ ] TCode 连 VAM (funscript → 舵机 PWM)

## 九 · 价值链

```
STL × 31  →  Stewart IK (firmware + 3D)
     ↓             ↓
  3D print  →  CadQuery 5 STEP+STL ⊕ FreeCAD 5 FCStd+STEP
     ↓                     ↓
  物理装配           Three.js viewer (rod=175 严)
     ↓                     ↓
  实机  ←—— BOM/DELIVERY ESP32 固件 ——→ VAM 仿真
     ↑                     ↑
  FreeCAD GUI 截图 × 5  (可视化真相 · 1200x900 PNG)
```

---

_道生一 一生二 二生三 三生万物._
_万物负阴而抱阳, 中气以为和._

_工具_: `python -m ORS6_Stewart.tools.gen_deliverables` 或 `python ORS6_Stewart/tools/gen_deliverables.py`
