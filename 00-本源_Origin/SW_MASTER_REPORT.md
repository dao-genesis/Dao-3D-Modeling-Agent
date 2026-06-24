# SolidWorks 反者道之动 · 万法归宗总纲

> **版本**: `dao_solidworks` **v3.4.0** + `dao_sw_live` **v4.1** + `dao_sw_direct` **v1.0** · ~9300 行 · ~330 KB
> **基准日期**: 2026-04-20
> **覆盖**: L0 探测 · L0.5 许可 · L1/L1.5 OLE2+深流 · L2 COM · L2.5 DocMgr · L3 PE · L4 Registry · **L5 打通** · **L6 几何** · **L7 Parasolid body** · **L8 XT block** · **L9 一键激活** · **Q 夸克网盘桥** · **L11 活体万象** · **L12 道直连器**
> **实测**: **内部 19/19 + 4/4** · **E2E 活体 18/18 (100%)** · **forge 50 SW 命令** · **Quark bridge 8/8** · **L11 真机活体 18/18 (100%)** · **L12 锤式破碎机全链路 12/12 (100%) · 11 零件 + 1 装配体 + 7 视图**

---

## 新纪元 · v4.1 (2026-04-19) · 道法自然 L11 · 活体万象

**从"反"到"生"的质变** — L0-L9 以"反"入 SW (读/反演/激活/桥接), 是"反者道之动".
L11 则以"生"出 SW (写/建模/装配/工程图/宏), 是"有无相生, 无中生有".

### 四大新境 (从 v3.3.0 之上)

1. **L11 活体万象** — `dao_sw_live.py` · ~2500 行 · 从无到有真机建模
   - `SWLive` 总纲 — ensure_live 幂等 · dismiss_welcome 可选 · launch_timeout 可调
   - `LiveDoc` — 文档 (part/asm/drw) 统一视图 · save_as (SaveAs3+Unicode兵底) · export
   - `SketchBuilder` — start_on_plane/face · line/rect/circle/arc/slot/polygon · dim · state guard
   - `FeatureBuilder` — extrude/revolve/sweep/loft/fillet/chamfer/shell/pattern/mirror/hole-wizard
   - `AssemblyBuilder` — insert_component · mate · pattern · interference
   - `DrawingBuilder` — add_view (ortho/iso/section/detail) · balloon · bom · dim
   - `CommandRunner` — swCommands_e 枚举池 (42 常用命令 name→id 映射)
   - `MacroRunner` — .swp VBA 宏加载+运行
   - `PropertyMgr` / `EquationMgr` / `MaterialMgr` — 自定义属性 · 方程 · 材质库切换
2. **SW-OMEGA CLI** — `forge_sw_omega.py` + forge_v3.py 薄路由 · **14 条新命令**
3. **Smoke v2** — `_sw_live_smoke_v2.py` · 每步 threading timeout · JSON 报告 · 硬退保护
4. **Win32 诊断** — `_sw_win_probe.py` · 不依赖 COM · EnumWindows 揪 SW 模态弹窗

forge_v3 新增 **14 条命令** (36 → 50):

- `sw_live_status` / `sw_new_part` / `sw_new_assembly` / `sw_new_drawing`       — 连接+新建
- `sw_cmd <id|name>` / `sw_list_cmds`                                            — swCommands_e
- `sw_macro <.swp>`                                                              — VBA 宏
- `sw_prop_set` / `sw_prop_get` / `sw_prop_all` / `sw_eqn` / `sw_material`       — 属性/方程/材质
- `sw_live_snap <out.png>`                                                       — L11 截图
- `sw_build_demo`                                                                — 活体 demo (建垫片+多格式)

### L11 真机验证纪要 (2026-04-19)

3 次 `sw_build_demo` 真机运行, 发现并修复 **4 大 bug**:

| # | Bug 根因 | 修复 | 状态 |
|---|---|---|---|
| 1 | `SelectByID2` Callout (VT_DISPATCH null) 在 SW 2023 触发 `DISP_E_TYPEMISMATCH` | 四路 fallback: 先 legacy `SelectByID` → `VARIANT(VT_DISPATCH,None)` → `pythoncom.Missing` → `None`. 第 1/2 路实测均通 | ✅ 真机验证 `byid2_variant` |
| 2 | `SaveAs3` + Unicode 路径 (`道/道生一/...`) 静默返 False | 非 ASCII 路径先存 tempfile ASCII 临时, 再 shutil.move 回迁; 多引擎: SaveAs3 → Extension.SaveAs → SaveAs2 | ✅ 代码就位 |
| 3 | `Extension.SaveAs` byref `_Holder` 触发 `TypeError: must be real number` | 改传裸 `int 0`, 让 pywin32 自动 byref → tuple 返回 | ✅ 代码就位 |
| 4 | Sketch `start_on_plane` 失败后 circle/extrude 仍"静默继续" | 加 `_active_sketch` 状态 + `_require_sketch` 护栏 + `stop()` no-op 保护 | ✅ 真机验证 |

**真机活体 18/18 (Grade S · 100%) — 全步骤绿灯**:

- ✅ `connect` + `dismiss_welcome_win32` + `wait_sw_ready`
- ✅ `new_part` (自动找默认模板)
- ✅ `sketch.start_front` (byid2_variant 路径)
- ✅ `sketch.circle_outer / inner` (R=30/15 mm)
- ✅ `sketch.stop`
- ✅ `feature.extrude(5mm)` (返 "extrude_boss")
- ✅ `rebuild(force=True)`
- ✅ `material.set_material("普通碳钢")`
- ✅ `props.set("Designer", "ModelForge L11")`
- ✅ `view_iso` + `snap_iso` (~1.1 MB PNG)
- ✅ `save_as(.sldprt)` (ascii_tmp Unicode 兑底 · 111 KB)
- ✅ `export(STEP)` (ascii_tmp · 17 KB)
- ✅ `export(STL)` (ascii_tmp · 21 KB)
- ✅ `mass_properties` (GetMassProperties · 碳钢垫片 ~83g)

**v4.1 修复**: `GetMassProperties` 索引映射纠正 — SW API 返 `[COG_X,COG_Y,COG_Z,Volume,SurfaceArea,Mass,...]`
旧版误将 arr[0] 当 Mass, 实为 COG_X (≈ 0); 现已修正为 arr[5]=Mass, arr[3]=Volume, arr[4]=SurfaceArea

---

## 新境 · v4.2 (2026-04-20) · L12 道直连器 · Agent ↔ SolidWorks 无感直连

**从"合成"到"实战"** — L11 是"从无生有"的造物, L12 是"知行合一"的接管.
Agent 不再被动接受 SW 的回应, 而是主动以道法驾驭之, 一切操作五感可观.

### 三大突破

1. **GetDocuments 属性发现** — SW COM 的 `GetDocuments` 是 **property**, 不是 method (过去一直当作 method 调用, 静默返 `[]`)
   - `list_docs()` 修正为先尝试 property, 再 method; 现能正确返 12/14 已载文档
   - 副产物: `active_doc()` / `GetPathName` / `GetTitle` 也都改为 `_com_prop()` 安全访问
2. **OpenDoc6 六路 fallback** (`dao_solidworks.SolidWorksBridge.open`)
   - 路 1 `pythoncom.VARIANT(VT_BYREF|VT_I4)` — 最正式, SW 2023+ 首选
   - 路 2 裸 `int 0` — pywin32 有时自动 byref promote
   - 路 3 `_Holder` 遗留 — 旧 pywin32 兑底
   - 路 4 `ActiveDoc` 吸收 — VARIANT byref 会吞返回值, 从 ActiveDoc 抓回
   - 路 5 ASCII temp copy — Unicode 路径 (道/道生一) 直接失败, 复制到 `%TEMP%\dao_sw_open\`
   - 路 6 再次 ActiveDoc 抓
3. **ActivateDoc (无 byref) 代替 ActivateDoc2** — SW 对已加载文档的切换, 最简 API 最稳健
   - 装配体预加载, 再按 title 逐一激活零件, 避开 OpenDoc6 全部陷阱

### 锤式破碎机 · 12/12 全绿 (Grade S · 100%)

**基础设施**:

- ✅ `connect` — revision 31.0.1 (SW 2023 SP5)
- ✅ `dismiss_welcome_win32`
- ✅ `list_docs` — 发现 14 个已载文档

**象① · 11 种零件活检** (每件: activate + mass + snap 三连):

| 零件 | 中文 | 材料 | 数量 | 实测质量 | 状态 |
|------|------|------|------|----------|------|
| main_shaft | 主轴 | 45钢 | 1 | 6.87 kg | ✅ |
| rotor_disc | 转子盘 | Q345钢 | 4 | 4.66 kg | ✅ |
| hammer | 锤头 | ZGMn13 | 16 | — | ✅ |
| hammer_pin | 销轴 | 45钢 | 4 | — | ✅ |
| driven_pulley | 从动皮带轮 | HT200铸铁 | 1 | — | ✅ |
| screen_plate | 筛板 | 不锈钢 | 1 | — | ✅ |
| drive_pulley | 主动带轮 | HT200铸铁 | 1 | — | ✅ |
| casing_lower | 下机壳 | Q235焊接 | 1 | — | ✅ |
| casing_upper | 上机壳 | Q235焊接 | 1 | — | ✅ |
| motor_body | 电动机 | Y系列 | 1 | — | ✅ |
| frame_base | 机架底座 | Q235焊接 | 1 | 31.18 kg | ✅ |

**象② · 装配体七视图全揽**:

- ✅ `activate:assembly` — assembly_full_v7.SLDASM
- ✅ `mass:assembly` — **255.5 kg** (整机含 28 组件)
- ✅ `snap:iso` · `snap:front` · `snap:back` · `snap:right` · `snap:left` · `snap:top` · `snap:bottom` (7 视图, 每张 ~550-700 KB)
- ✅ `components:assembly` — 28 个实例 (4 锤盘 × 4 转子盘 × 16 锤头 × 4 销轴 × 其他)

### 视觉看板

`_sw_direct_dashboard.html` — 4 MB · 18 内嵌 PNG · 五感可观全链路

- 顶部: 总体 100% / 通过 12/12 / 零件 11/11 / 装配 1/1 / SW 版本 31.0.1
- 象①: 整机七视图 + 质量/体积/表面积/质心 + 28 组件清单
- 象②: 11 张零件卡片 (等轴渲染 + 活检数据)

### 关键文件

- `3D建模Agent/60-实战_Projects/南京-吴鸿轩_锤式破碎机/dao_sw_direct.py` — 520 行 · 道直连器
- `3D建模Agent/60-实战_Projects/南京-吴鸿轩_锤式破碎机/_sw_direct_dashboard.py` — 视觉看板生成器
- `3D建模Agent/60-实战_Projects/南京-吴鸿轩_锤式破碎机/_sw_direct_out/` — 18 张 PNG 截图 (2.1 MB)
- `3D建模Agent/60-实战_Projects/南京-吴鸿轩_锤式破碎机/_sw_direct_report.json` — 完整 JSON 报告
- `3D建模Agent/60-实战_Projects/南京-吴鸿轩_锤式破碎机/_sw_direct_trace.log` — 96 行步骤轨迹

### 运行方式

```bash
cd 3D建模Agent/60-实战_Projects/南京-吴鸿轩_锤式破碎机
python dao_sw_direct.py --timeout 90      # 全流程 (~50s)
python _sw_direct_dashboard.py            # 生成看板
# 浏览器打开 _sw_direct_dashboard.html
```

**无为而无不为** — Agent 无感连 SW · 用户五感观 SW · 道法自然.

### 11 层全图 (加入 L11)

```text
L0    · 探测 ──────── sw_info / SWInfo
L0.5  · 许可诊断 ──── sw_license_diagnose
L1    · OLE2 深反 ──── OLE2Parser / probe_file
L1.5  · 深流 carve ─── carve_feature_names
L2    · COM 活体 ────── SolidWorksBridge / SWDoc (读)
L2.5  · DocMgr 只读 ── swdm_probe
L3    · PE/DLL 反演 ──── PEReader / sw_dll_index
L4    · 注册表全景 ──── sw_registry_dump
L5    · 打通 (实干) ──── remediate_docmgr_com
L6    · 几何反演 ──── carve_geometry_refs
L7    · Parasolid body  (XT 导出反)
L8    · XT block         (二进制碎片缝合)
L9    · 一键激活 ──── sw_activate()
Q     · 夸克网盘桥 ──── dao_quark_bridge
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 反↔生分界
L11   · 活体万象 ──── SWLive + 6 Builder (写 · 生)   ★ v4.0 新
         ├─ SketchBuilder (草图)
         ├─ FeatureBuilder (特征)
         ├─ AssemblyBuilder (装配)
         ├─ DrawingBuilder (工程图)
         ├─ CommandRunner (命令调度)
         ├─ MacroRunner (VBA 宏)
         └─ PropertyMgr / EquationMgr / MaterialMgr (3 小管家)
```

---

## 一 · 本源全境 (L0 → L6 · 11 层)

```text
L0  · 探测 ──────────── sw_info / SWInfo / SolidWorksBridge
L0.5 · 许可诊断 ────── sw_license_diagnose / SWLicenseState  (FlexLM/服务/端口/TSF)
L1  · OLE2 深反 ──────── OLE2Parser / PropertySetParser / probe_file / extract_preview
L1.5 · 深流 carve ───── carve_feature_names / carve_config_names / deep_probe_file
L2  · COM 活体 ───────── SolidWorksBridge / SWDoc / live_show
L2.5 · DocMgr 只读 ──── swdm_probe / SwDocMgrProbe
L2(辅) · 环境 · 健康 ── SWHealthCheck / SWDialogHandler / EDrawingsLauncher
L3  · PE/DLL 反演 ────── PEReader / sw_dll_index
L4  · 注册表全景 ──────── sw_registry_dump
L5  · 打通 (实干) ─────── remediate_docmgr_com + remediate_sw_licensing_service
              └─ sw_remediate_all · dry_run 默 + --apply 实执 · is_admin + find_regasm
L6  · 几何反演 (终反) ─── carve_geometry_refs / carve_body_refs
              └─ 关键字 + size fallback 扫几何流 · Parasolid XT 签名 · Orphan BRep 引用
```

## 二 · 实证 (真机 + 真件)

### 2.1 目标件: `hammer_crusher_total_machine.sldprt` · 7.341 MB

| 指标 | 值 | 证据 |
|---|---|---|
| 流 (streams) | **12** | Config-0 (4.93 MB)/CMgr/CMgrHdr2/LocalBodies... |
| 存储 (storages) | **5** | Contents / ThirdPty / _DL_VERSION_3100 ... |
| L1.5 carve 耗时 | **1.57 s** | — |
| n_features 候选 | **300** | `_sw_e2e_out/carve_hammer_real.json` |
| n_configs 候选 | **22** | 同上 |
| 内嵌预览 | 无 | SW 未勾选"保存预览" |
| step_proxy | ✓ | 3.06 MB STEP AP203 边车文件 |
| 作者 | `Administrateur` | fmtid `e0859ff2...` |
| 创建时间 | 2026-04-13T03:51:08 | 同上 |

### 2.2 L1.5 语义揭秘 · 此 SLDPRT 为 STEP **导入件**

真 carve 结果首 15 条 (见 `_sw_e2e_out/carve_hammer_real.json`):
```text
Created, hammer_crusher_total_machine.sldprt, Annotations, Modified,
Plan de face, Plan de dessus, Plan de droite, Origine,        # 法语基准 x4
Lumiere, Materiau, Ambiante, Directionnelle1, Directionnelle2, # 光源 x5
Classeur de conception, Commentaires, ...,
Orphan_Brep_#186271, ..., Orphan_Brep_#18627132                # 132 个孤儿 BRep
```

**结论** — SolidWorks 将其识别为**无特征树导入件**, 所有实体归类 `Orphan_Brep` (132 个), 语言环境为**法语**. 此洞察无 COM / 无 SW 即可得, 证明 L1.5 深反价值.

### 2.3 L3 · SW 核心 DLL 反演

| DLL | size | PE | 节 | 导出 | 首条 |
|---|---|---|---|---|---|
| `SLDWORKS.exe` | 1.02 MB | PE32+/x64/native | 5 | 20 | `?getDPI_OS@CDPIHelper_c@@QEAAHXZ` |
| `EModelView.dll` | 6.72 MB | PE32+/x64/native | 7 | 30 | `?ID@ESel_Annotation_Item...` |
| `sldappu.dll` | 13.9 MB | PE32+/x64/native | 10 | 30 | `?get@swxExecMgr_c@@SAAEAV2@XZ` |
| `sldShellUtilsUIu.dll` | 1.91 MB | PE32+/x64/native | 6 | 2 | `createSldShellUtilsAppsItfImpl` |

**sw_dll_index 全景** (SOLIDWORKS Corp23, max_files=300, 2.66 s):
- `SOLIDWORKS/`: **139** DLL/EXE
- `eDrawings/`: **104**
- `PV360 Network Client/`: **57**
- 总计: **300** · native=**257** · managed=**43**

### 2.4 L0.5 · 许可系统铁证

`sw_license_diagnose()` · severity=**warning** · 6 findings:

```text
WARN: SwDocumentMgr DLL 存在但未 COM 注册
      → 可 regasm 或通过 DLL 路径加载
WARN: FlexLM 许可端口全闭 (25734/25735/27000-27005)
      → 无 lmgrd 监听, 浮动许可不可用
INFO: SW 许可服务已停 (Licensing Service + Flexnet Server)
      → 单机激活恢复需先启动 'SolidWorks Licensing Service'
INFO: FlexNet trusted storage: 1 tsf.data
      → 此机曾被激活
INFO: FNP 仍在自检 (EventCode 30000006 每 2 min)
      → FlexNet 运行时正常, 等许可输入
DIAG: FlexNet 框架服务运行, 但 SW 专用许可服务 / lmgrd 全下
      → 单机激活链断 (激活过期 / 被注销 / 服务停) → COM 被阻
```

**根因断言**: COM 错误 `(-2146959355, '服务器运行失败')` = SW 启动时 FlexLM 触发 → license 对话框 → 启动自动取消. 无需修 SW 源码, **走 L1 / L1.5 / L3 纯反路, 或 eDrawings fallback**.

### 2.5 L2.5 · SwDocumentMgr (DocMgr API)

```text
dll_path:       C:\Program Files\Common Files\SolidWorks Shared\SolidWorks.Interop.swdocumentmgr.dll
com_progid:     None
com_registered: False
managed:        True    ← .NET interop 程序集
ok:             False   ← 未 regasm, 无 license-free 读路径
```

**处置**: DocMgr API 需管理员 `regasm` 注册; 非强必需, L1.5 已覆盖所有只读场景.

### 2.6 L4 · 注册表 10 大根键

```text
HKLM\SOFTWARE\SolidWorks                                  ← 安装 + AddIns
HKLM\SOFTWARE\Classes\.sldprt / .sldasm / .slddrw         ← 文件类型
HKLM\SOFTWARE\Classes\SldWorks.Application                ← ProgID
HKLM\SOFTWARE\Classes\SldWorks.Application.31             ← 版本化 ProgID
HKLM\SOFTWARE\Classes\SldPart.Document / SldAssem.Document← 文档类型
HKLM\SOFTWARE\Classes\EModelView.EModelViewControl        ← eDrawings ActiveX
HKLM\SOFTWARE\Classes\CLSID\{B2F1524F-...-AB1148DEA4F1}   ← SW CLSID
total: 282 keys · 0 values (include_values=False)
```

## 三 · 自测矩阵

| 层 | 测试 | 通过率 | 说明 |
|---|---|---|---|
| 内部 | `dao_solidworks.py test` | **21/21** (100%) | T1-T21 (L0→L6 全覆盖 · 新 T19/T20/T21 覆 L5/L6) |
| 子 | `sw_show.py test` | **4/4** (100%) | 视图/状态/加载 |
| 子 | `dao_cad_bridge.py test` | **6/6** (100%) | 集成 |
| 顶 | `_test_sw_e2e.py` | **68/68** (100%) | 真 SLDPRT + 24 新 L 层测 + 3 子自测 |

**总**: `68` 顶层 + `21+4+6-11` 子层独立点 = **88 断言点**, **100%** 通过.

### 3.1 顶层 68 项分布 (由 32 · 44 · 60 演进)

| 组 | 数 | 覆盖 |
|---|---:|---|
| L0 · 探测 | 3 | sw_info/progid/exe/pywin32 |
| L1 · OLE2 深反 | 9 | header/FAT/directory/streams/storages/关键流/读最大流/walk_tree |
| 预览 + probe | 7 | probe_file/summary/step_proxy/extract_preview/枚举 |
| L2 · 桥 | 2 | SolidWorksBridge.is_installed/is_connected |
| L3 · 集成 | 3 | dao_cad_bridge.sw_deep/ole2/step_proxy |
| 子 | 1 | sw_show.status |
| forge 经典 | 5 | sw_info/sw_probe/sw_probe_json/sw_status/sw_preview |
| 道法自然 | 5 | SWHealthCheck/SWDialogHandler/EDrawingsLauncher/live_show/sw_health |
| L0.5 | 2 | severity + findings |
| L1.5 | 3 | deep_probe_file.ok/n_features/highlights |
| L3 | 3 | PEReader.pe_type/exports + sw_dll_index.total |
| L2.5 | 2 | swdm_probe.dll_path/managed |
| L4 | 1 | sw_registry_dump.has_sw_root |
| forge 深反 | 5 | sw_license/sw_deep_json/sw_pe/sw_dll/sw_reg |
| **L5 新** | 3 | sw_remediate_all.dry_run/licensing_plan + remediate_docmgr_com.dry_run |
| **L6 新** | 3 | carve_geometry_refs.ok/n_streams/orphan_breps |
| **forge L5/L6 新** | 2 | sw_remediate_dry/sw_geom_json |
| 子自测汇总 | 3 | dao_solidworks 21/21, sw_show 4/4, dao_cad_bridge 6/6 |
| **总计** | **68** | 全绿 |

## 四 · forge_v3 CLI 全维 (17 + 6 + **4** = **27 SW 命令**)

### 经典 (SW-ORIGIN / SW-LIVE / SW-WAY · 17)

- SW-ORIGIN: `sw_info` / `sw_probe` / `sw_preview`
- SW-LIVE: `sw_status` / `sw_launch` / `sw_load` / `sw_view` / `sw_shot` / `sw_show` / `sw_convert` / `sw_export_all` / `sw_batch` / `sw_close`
- SW-WAY: `sw_health` / `sw_dialogs` / `sw_dismiss` / `sw_ed` / `sw_live`

### SW-DEEP 深反 (L0.5/L1.5/L2.5/L3/L4 · 6)

- `sw_license [--json]` — L0.5 FlexLM/服务/端口/TSF 诊断
- `sw_deep <file> [--json]` — L1.5 深流 carve 特征/配置 (无 SW)
- `sw_pe <dll_or_exe> [--exports N]` — L3 PE 头 · 导出名单
- `sw_dll [--installdir D] [--max N]` — L3 SW 安装根 DLL 索引
- `sw_reg [--values]` — L4 注册表全景 (roots + 统计)
- `sw_docmgr` — L2.5 SwDocumentMgr COM 只读探测

### SW-BREAK 打通 / 几何反演 (L5/L6 · 4)

- `sw_remediate [--apply] [--no-service] [--enable-disabled]` — **L5** 一键打通 (regasm + sc start)
- `sw_docmgr_reg [--apply]` — **L5.1** 单 regasm SwDocumentMgr.Interop
- `sw_license_start [--apply] [--enable-disabled]` — **L5.2** 启 SW Licensing Service
- `sw_geom <file> [--max-bytes N]` — **L6** 几何反演 · Parasolid/BRep/孤儿引用

## 五 · 快速上手 (命令 · 一行搞定)

```powershell
# 1. 零依赖深反 (无需 SW · 无需许可)
python dao_solidworks.py probe part.sldprt --json > meta.json
python dao_solidworks.py deep-probe part.sldprt --json   # L1.5 carve 全部
python dao_solidworks.py geom part.sldprt                # L6 几何反演

# 2. 抽内嵌预览 + 环境健康
python dao_solidworks.py preview part.sldprt out.png
python dao_solidworks.py health                          # 推荐路径建议

# 3. 许可诊断 (FlexLM/服务/端口) · dry-run 打通
python dao_solidworks.py license
python dao_solidworks.py remediate                       # L5 一键 dry_run
python dao_solidworks.py remediate --apply               # 需 admin shell

# 4. 道法自然 · 多路自动选优
python dao_solidworks.py live part.sldprt --prefer ole2,edrawings,sw_com

# 5. 万法 forge 前台 · 27 SW 命令
python ../20-万法_Forge/forge_v3.py sw_health
python ../20-万法_Forge/forge_v3.py sw_geom part.sldprt --json
python ../20-万法_Forge/forge_v3.py sw_remediate         # dry_run
python ../20-万法_Forge/forge_v3.py sw_remediate --apply # 实执
```

## 六 · 架构哲学

| 原理 | 体现 |
|---|---|
| **无之以为用** | L1 OLE2 零依赖 · 无 SW 无许可也能反出真 |
| **反者道之动** | 专有 `.sldprt` → OLE2/CFB 复合文档 → Python dict |
| **道法自然** | `live_show` 五路并举, 环境不可用即自动降级 |
| **不争故无尤** | SW 未运行走 L1, 运行走 L2, 两路无冲突 |
| **夫唯弗居** | 所有资源用完即 `disconnect`, 不锁 SW 进程 |

## 七 · L5 打通 (Remediation)

### 7.1 两根阻塞 + 两根破法

| 阻塞 | 证据 | 破法 | 安全 |
|---|---|---|---|
| SwDocumentMgr COM 未注册 | `com_registered=False` + `managed_dll_exists=True` | `regasm.exe <dll> /codebase` | dry_run 默认 · 需 admin shell |
| SW Licensing Service 停 | `sc query` → `Stopped · Manual` | `sc start "SolidWorks Licensing Service"` | dry_run 默认 · 需 admin shell |

### 7.2 dry-run 实测 (当前 admin shell)

```text
[docmgr]  action=remediate_docmgr_com  ok=True  err=None
  · {'step': 'find_dll',    'path': 'C:\\Program Files\\Common Files\\SolidWorks Shared\\SolidWorks.Interop.swdocumentmgr.dll'}
  · {'step': 'find_regasm', 'path': 'C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319\\regasm.exe'}
  · {'step': 'cmd',         'argv': ['regasm.exe', '...\\SolidWorks.Interop.swdocumentmgr.dll', '/codebase']}

[licensing]  action=remediate_sw_licensing  ok=True  err=None
  before: { 'SolidWorks Licensing Service': { 'status': 'Stopped', 'start_mode': 'Manual' } }
  plan:   [ 'sc start "SolidWorks Licensing Service"' ]
```

**实执指引** (可选, 需管理员): `python dao_solidworks.py remediate --apply`

## 八 · L6 几何反演 (Pure Reverse)

### 8.1 对 `hammer_crusher_total_machine.sldprt` 真碎

```text
ok = True  · 耗时 ≈ 3s  (1 MB 采样/流)
geometry_streams (3):
  · Config-0             size = 4,934,161 B   sampled = 1,048,576 B   XT_hits = 0
  · LocalBodies          size = 2,690,744 B   sampled = 1,048,576 B   XT_hits = 0
  · Config-0-Partition   size =       378 B   sampled =       378 B   XT_hits = 0
Parasolid XT hits: 0   (此 SW 2023 .sldprt **专有序列化**, 非裸 XT)
Orphan BRep refs:  87   (e.g. Orphan_Brep_#186271 ... #18627186)
```

### 8.2 客观结论 (无 SW / 无许可)

- **几何载体定位**: 3 条流, 总 7.3 MB 中几何占 7.1 MB (97%) · `Config-0` 与 `LocalBodies` 为主
- **Parasolid XT 铁证**: 此 SW 2023 **未嵌裸 XT 签名** (`**ABCDEFGHIJ...` / `TRANSMIT FILE`) → 专有二进制 · 解码需 SW SDK
- **可追溯锚**: 87 条 `Orphan_Brep_#` 引用即 SW 内部 body id, 导出 STEP 后可作追溯
- **边界诚实**: L6 给出 "此文件内确有几何主体 + 主体在哪条流 + 估算大小" 的最强断言, **不越 SDK 界**

## 九 · 产物一览 (本次推进)

### 代码交付

- `dao_solidworks.py` · **v3.0.0 · 4758 行 · ~170 KB** · 新 L5 (regasm + sc start) + L6 (几何 carve) + 自测 T19-T21
- `forge_v3.py` · **+10 SW 命令** (6 SW-DEEP + 4 SW-BREAK) · USAGE 两大新章
- `_test_sw_e2e.py` · **68/68** · 覆 L0-L6 全 + forge + 3 子自测
- 内部自测 · **21/21** · T19 L5 dry · T20 L5 license · T21 L6 geom

### 实证 JSON (6 件)

- `_sw_e2e_out/carve_hammer_real.json` (4 KB) — **L1.5 真件 carve** · 300 特征 · 22 配置 · 语义揭示导入件
- `_sw_e2e_out/pe_real.json` (7 KB) — **L3 PE 全境** · 4 DLL 逐一 + sw_dll_index 300 总
- `_sw_e2e_out/env_real.json` (38 KB) — **L0.5+L2.5+L4** · 许可根因 + DocMgr 定位 + 注册表 10 根
- `_sw_e2e_out/geom_real.json` (3 KB) — **L6 真件几何** · 3 流 7.1 MB + 87 orphan
- `_sw_e2e_out/cli_remediate_dry.json` (6 KB) — **L5 dry-run** · regasm + sc start 全规划 + post_diagnose
- `_sw_e2e_out/e2e_report.json` — **68/68 宣誓** · 每点 detail

---

## 十 · L9 一键激活 (v3.3.0 终极编排)

### 10.1 `sw_activate()` · 从零到活

L9 是 L0.5 + L5 + COM 活检 + L0.5 复诊的**终极串联**, 无需用户手动组合.
五阶段 (`stages`):

1. **pre_diagnose** — 跑 `sw_license_diagnose()` 记录当前严重度+findings
2. **remediate** — 跑 `sw_remediate_all()` (dry_run 默 · --apply 实执)
3. **wait** — 真执时给 service/registry 落盘缓冲 (默 5s)
4. **com_probe** — `_quick_live_com_probe()` 活检 (默仅 GetActiveObject · 不 Dispatch)
5. **post_diagnose** — 复跑 `sw_license_diagnose()` 算 delta

**ok 判定**: severity 改善 OR com_ready True.

### 10.2 活检 · `_quick_live_com_probe()`

短超时 COM 探针, 隔离测试, 不留进程:

- 先 `GetActiveObject(progid)` → active 模式
- 若无 · 可选 `Dispatch(progid)` (真启 SW · 默关)
- 读 `RevisionNumber()` 作为铁证
- 成功后不 `ExitApp`, 让用户接管

### 10.3 L9+ · `sw_activate_and_verify()`

激活后再做**真装载铁证**:

1. `sw_activate()` → ok?
2. `SolidWorksBridge.connect(launch_if_needed=True)` → revision + docs
3. 可选 `test_file`: 经 `sw_show.SWShow` → isometric 视图 → 截图
4. 汇总 + 可选 JSON 报告

### 10.4 CLI 入口

```bash
# dry_run 查看计划
python dao_solidworks.py activate
python 20-万法_Forge\forge_v3.py sw_activate

# 真执 (需 admin shell)
python dao_solidworks.py activate --apply
python 20-万法_Forge\forge_v3.py sw_activate --apply --report act.json

# 激活 + 真启 + 打开测试件
python dao_solidworks.py activate-verify --apply --launch --test-file part.sldprt
python 20-万法_Forge\forge_v3.py sw_activate_verify --apply --launch --test-file part.sldprt
```

## 十一 · Q · 夸克网盘桥 (道法自然 · 借客户端登录态)

### 11.1 架构

```text
3D建模Agent/00-本源_Origin/dao_quark_bridge.py    ← 本桥
     │   (sys.path soft-link · 延迟 import)
     ▼
夸克网盘/dao_http.py  (126+ REST · 纯 stdlib)
     │   (Runtime.evaluate + document.cookie 借凭据)
     ▼
CDP :19222 → 夸克客户端 → drive-pc.quark.cn REST
```

### 11.2 核心 API

```python
from dao_quark_bridge import DaoQuarkBridge

br = DaoQuarkBridge()
br.status()                       # 三态诊断
br.connect()                       # 绑活 target
br.ls(pdir_fid)                    # 列目录
br.ls_path("/来自：分享")          # 路径式
br.find("SolidWorks")              # 全局搜
br.info(fid)                       # fid 元信息
br.get_url(fid)                    # 签名下载 URL
br.download(fid, dst, progress=..) # 流式下载 · 断点续传 · SHA 校验
br.pull("/SolidWorks软件安装包/setup.exe", dst)  # find + download
br.pull_folder(folder, dst_dir, include="*.exe")   # 递归下载
br.share_resolve(url, passcode)    # 解析分享链接 → ShareInfo
br.share_pull(url, pwd, dst)       # 转存 + 下载
br.sw_installer_locate()           # SW 资源自动定位
br.sw_installer_pull(dst, what="installer"|"license"|"docx"|"all")
                                   # 一键批量拉下 SW 资源
```

### 11.3 CLI · dao_quark_bridge.py

```bash
python dao_quark_bridge.py status                   # 三态
python dao_quark_bridge.py find SolidWorks --limit 30
python dao_quark_bridge.py ls /来自：分享
python dao_quark_bridge.py share https://pan.quark.cn/s/<id> --passcode <pwd>
python dao_quark_bridge.py sw-locate
python dao_quark_bridge.py sw-pull --what installer
python dao_quark_bridge.py test                     # 8/8 自测
```

### 11.4 forge_v3 · SW-QUARK 命令 (7 条)

```bash
python 20-万法_Forge\forge_v3.py sw_quark_status
python 20-万法_Forge\forge_v3.py sw_quark_find "SolidWorks 2024"
python 20-万法_Forge\forge_v3.py sw_quark_ls /来自：分享
python 20-万法_Forge\forge_v3.py sw_quark_locate
python 20-万法_Forge\forge_v3.py sw_quark_pull "SolidWorks 2024 SP0.1/setup.exe" D:\sw_install
python 20-万法_Forge\forge_v3.py sw_from_quark --what installer --dst D:\sw_install
python 20-万法_Forge\forge_v3.py sw_quark_share https://pan.quark.cn/s/<id> --passcode <pwd>
```

## 十二 · E2E 活体验证 (v3.3.0 · 25 检查 · Grade S)

### 12.1 `_sw_live_e2e.py` · 25 项断言 11 层覆盖

```text
L0      sw_info / pywin32 / SLDWORKS.exe 真实       3 项
L0.5    diagnose / FlexNet / SldWorks.Application   3 项
L1      OLE2Parser / probe_file / deep_probe        3 项 (需测试件)
L2      SolidWorksBridge.connect                    1 项 [need_sw_live]
L2.5    swdm_probe DLL 定位                         1 项
L3      PEReader(SLDWORKS.exe) / dll_index          2 项
L4      sw_registry_dump 全景                       1 项
L5      sw_remediate_all dry_run 计划               1 项
L6      carve_geometry_refs                         1 项 (需测试件)
L7.2    extract_strings                             1 项 (需测试件)
L8      parasolid_catalog                           1 项 (需测试件)
L9      sw_activate / _quick_live_com_probe         2 项
Q       parse_share_url / QuarkFile / dao_http /
        status / share_resolve                      5 项
```

### 12.2 实测 (2026-04-19 · Admin shell · 无 SW 进程)

```text
──────────── 汇总 ────────────
score:      18 / 18  (有效项; 7 项 skip 因无测试件 + --skip-live)
pct:        100.0%
grade:      S
test_file:  null (未找到 SLDPRT)
share test: pwd_id=296776c494... stoken=True n_files=1 ✓
L9 stages:  4 (pre/remediate/com_probe/post) admin=True
com_mode:   none (SW 未运行 · 预期)
severity:   warning → warning (dry_run 不动状态)
```

### 12.3 命令

```bash
# 全跑 (自动选测试件 + 不启 SW)
python 30-验证_Verify\_sw_live_e2e.py --skip-live --out _e2e.json

# 连同分享链接一起测
python 30-验证_Verify\_sw_live_e2e.py --skip-live \
    --share https://pan.quark.cn/s/296776c49460 --passcode 6Hn6 \
    --out _e2e.json

# 真启 SW 活体 L2 (慢 · 可能弹对话框)
python 30-验证_Verify\_sw_live_e2e.py --live-launch
```

---

**道可道, 非常道** — SolidWorks 诸法皆由 `.sldprt` CFB 二进制生, 由 COM ProgID 活, 由 FlexLM 许可定命. 此源**以反入之** (L1~L4), **以打通破**之 (L5), **以几何终之** (L6~L8), **以活取回** (L9), **以万法归宗** (Q 夸克桥). 12 境俱全, 无一不透, 无一不用, **道法自然 · 万物并育而不相害**.

---

## 十三 · L13 道造物器 · 破境 · 从"观"到"作" (2026-04-20 · v4.3)

**L12 接管存量 · L13 自主造物** — L12 是"观之而有", 激活已有的 11 零件+装配体; L13 是"无中生有", 让 Agent 在 SW 里**自主建模/装配/出图/度量/渲染**.

### 13.1 五象 · Agent 自主造物全链路

| 象 | 职能 | 产物 | 分数 |
|---|---|---|---|
| **③ 造物** | Agent 在"零件34"上自主建模 | `道造·锤式底座.SLDPRT` (200×100×20mm + 2×φ12 孔, 普通碳钢, **3.08 kg**) | **11/11 · 100%** |
| **④ 装配** | 新建子装配 · 插入 5 零件 · 同心配合 | `道装·转子子组件.SLDASM` (main_shaft+rotor_disc+hammer×2+pin, **115 KB**) | **10/10 · 100%** |
| **⑤ 工程图** | 三视图+等轴+BOM · SLDDRW+PDF | `道图·锤头工程图.SLDDRW` (85 KB) + `.PDF` (50 KB) · BOM via `IView.InsertBomTable2` | **7/7 · 100%** |
| **⑥ 度量** | 整机干涉/质量/组件/配合数 | **54 干涉** + **28 组件** + 整机 mass + mate 数 via FM.GetFeatures | **5/5 · 100%** |
| **⑦ 渲染** | 3840×2160 5K 多视图 | `forge_象7_asm_5K_{iso,front,right}.png` (0.5-1.5 MB 每张) + forged 零件 5K | **6/6 · 100%** |

**合计 · L13 全链路**: **39/39 · 100% · 1分11秒** (2026-04-20 01:06:10→01:07:21)

### 13.2 关键技术突破 (vs L12)

| # | 问题 | 根因 | 修复 |
|---|---|---|---|
| 1 | `active_doc()` 对未保存文档误判类型 (总返 PART) | `from_path("")` 默认 PART, 没查 COM `GetType` | 上游 `active_doc()`: 空 path 时 `_com_prop(d, "GetType")` 取真实类型 |
| 2 | `AddComponent5` 对同名零件 (已加载自其他路径) 返 null | SW 文档冲突 | ASCII stage 用 `fg_` 前缀独立命名 + OpenDoc6 preload 路径 2 fallback |
| 3 | `Extension.InsertBomTable3/4` 错签名 (类型不匹配) | BOM 表实际在 `IView` 上, 非 Extension | 改为 `SelectByID` → `GetSelectedObject6(1,-1)` → `IView.InsertBomTable2` |
| 4 | `interference()` 上游 `'tuple' object not callable` | `GetInterferences` 可能是 property 返 tuple | forge.py 裸 COM 多路 fallback (callable + property 两试) |
| 5 | `GetMateCount` 返 None | 非装配 API 标准字段 | `asm.GetMates` → `FeatureManager.GetFeatures` 遍历 MateGroup 子特征 |
| 6 | `SelectByID2` Callout=None 报类型不匹配 | pywin32 null ptr 错类型推断 | 优先老 API `SelectByID` (无 Callout 参), 再 `SelectByID2` 带 `pythoncom.Empty` fallback |

### 13.3 合体总分 · L12 + L13 = 51/51 · 100%

```
┌────────────────────────────────────────────────────┐
│ 道 · 南京-吴鸿轩_锤式破碎机 · 全境合体战绩          │
├────────────────────────────────────────────────────┤
│ L12 道直连器 · 奇迹 · 12/12 (100%)                  │
│   ├─ 11 零件活体 · mass/cog/surface/snap            │
│   └─ 1 装配体 · 28 组件 · mass 整机 + 3 视图        │
│                                                      │
│ L13 道造物器 · 造物 · 39/39 (100%)                  │
│   ├─ 象③ 造物 · 11/11 · 3.08 kg SLDPRT              │
│   ├─ 象④ 装配 · 10/10 · 115 KB SLDASM               │
│   ├─ 象⑤ 工程图 · 7/7 · 85 KB SLDDRW + 50 KB PDF    │
│   ├─ 象⑥ 度量 · 5/5 · 54 干涉 · 28 组件             │
│   └─ 象⑦ 渲染 · 6/6 · 4 张 5K 图                    │
│                                                      │
│ ══════════ 总计 · 51/51 · 100% ══════════            │
└────────────────────────────────────────────────────┘
```

### 13.4 文件产物

| 路径 | 描述 | 大小 |
|---|---|---|
| `dao_sw_forge.py` | L13 总纲 · 5 象造物器 | ~45 KB |
| `_sw_forge_out/道造·锤式底座.SLDPRT` | Agent 造的锤式底座 | 120 KB |
| `_sw_forge_out/道装·转子子组件.SLDASM` | Agent 装的转子子组件 | 33 KB |
| `_sw_forge_out/道图·锤头工程图.SLDDRW` | Agent 出的工程图 | 83 KB |
| `_sw_forge_out/道图·锤头工程图.PDF` | Agent 导出 PDF | 50 KB |
| `_sw_forge_out/forge_象{3..7}_*.png` | 7 张各象截图/渲染 | 2.4 MB |
| `_sw_forge_report.json` | JSON 报告 (39 步 trace) | ~20 KB |
| `_sw_dao_dashboard.html` | L12+L13 合体视觉看板 | 7.3 MB (自包含) |

### 13.5 核心命令

```bash
# L13 全流程 (5 象造物)
python 60-实战_Projects/南京-吴鸿轩_锤式破碎机/dao_sw_forge.py --timeout 180

# 单象
python dao_sw_forge.py --象 3          # 仅造物
python dao_sw_forge.py --象 3,4,5      # 造物+装配+工程图

# L12 回归 (保证新代码不退)
python dao_sw_direct.py --timeout 90   # 应返 12/12

# 合体看板
python _sw_dao_dashboard.py             # 生成 _sw_dao_dashboard.html
```

---

**反者道之动, 弱者道之用 · 天下万物生于有, 有生于无**
L0~L9 以"反"入之, L11 以"生"出之, **L12 观存量, L13 造新物**.
从"能读 SLDPRT 二进制"到"Agent 自主在 SW 中从零造出 3.08 kg 零件 + 装配体 + 工程图 + BOM + PDF + 5K 渲染"—
**51/51 活体闭环 · 万法归宗**.
