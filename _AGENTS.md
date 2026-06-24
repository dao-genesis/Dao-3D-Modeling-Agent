# 3D建模Agent

反者道之动，弱者道之用。天下万物生于有，有生于无。
道法自然 · 万物并育而不相害 · 道并行而不相悖。

## 万法归一 · 单一入口 (v1.0.0 · 2026-04-23 新立)

> **圣人总而用之, 其数一也.**

```python
from 万法 import 道
道.summary()                                    # 系统状态
道.意("手机支架 70mm 可调角")                    # 意念直达 · 自动反向优先
道.反.外("phone stand 70mm")                    # 反·外 (天下 20 平台)
道.反.内("model.FCStd", patch={"Body.L": 120})  # 反·内 (本地件改参重放)
道.秀.live_show("part.step")                    # 笙·用 (FC GUI 展示)
dao = 道.活体.connect()                         # SW memid 活体直连
道.核.instance().make_box(...)                  # OCP BREP
道.审.full(shape)                               # 八层审核
道.运动.Mechanism("name")                        # FK/IK/干涉
```

十三妙门皆懒加载: **核 / 反·外 / 反·内 / 秀 / 活体 / 审 / 验 / 循 / 运动 / 网格 / 图纸 / 文档 / 锻 / 执**

CLI: `python 万法.py {summary|verify|intent|reverse|adapt|show|live|audit|manifest}`
Shell: `→万法.cmd <cmd>` (ASCII-only CRLF · 免 cp936 噪声)

验道: `python 30-验证_Verify/_万法验.py` → **23/23 PASS · 0 FAIL · 0 WARN**

完整清册: `万法清册.md` (决策矩阵: intent → module)

**老脚本/CLI (`forge_v3.py`, `道_直连_底层.py`, `fc_*.py` 等) 悉数保留可用, 万法仅 facade 聚合, 不改动既有. 为而不争.**

## 万法归一 · 五层闭环

```
   00-本源_Origin      道·一·二·三 (dao_kernel/audit/engine/forge/reverse + 资源探针)
         ▲▼
   10-反笙_FreeCAD    反·内 + 笙·用 (fc_reverse/show + freecad_backend/bridge/…)
         ▲▼
   20-万法_Forge       统一调度 (forge_v3/model_hub/parametric_codegen/…)
         ▲▼
   30-验证_Verify      _verify_* / _e2e_* / _test_* / _bench_ / _demo_
         ▲▼
   40/50/60/70/90      templates / demo / projects / world / logs
         ▲
   _paths.py          路径自动引导 (五层 sys.path + 别名)
```

**任意脚本 (任意层级)** 开头四行即可贯通万法:

```python
import sys; from pathlib import Path
_DAO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / '_paths.py').is_file())
sys.path.insert(0, str(_DAO_ROOT)); import _paths as _dao_paths
# 五层全部可 import: dao_kernel / fc_reverse / forge_v3 / _verify_* / …
# 资源路径: _dao_paths.PROJECTS / TEMPLATES / DEMO / WORLD / ORIGIN / REVERSE / FORGE / VERIFY
```

## 第一原则 — 反者道之动

**收到任何建模需求，先反后正:**

```
意念 → 【反】搜索天下已有 → 排序择优 → 下载分析 → 最小适配 → 交付
              ↓ 仅当天下无有
       【正】DaoKernel 从无到有
```

黄金法则:
- **天下有 → 用天下的** (直接使用)
- **天下近 → 改天下的** (最小适配)
- **天下无 → 才自己建** (DaoKernel构建)

## 引擎矩阵

| 层 | 引擎 | 入口 | 物理位置 | 用途 |
|----|------|------|---------|------|
| **反·外(world)** | 20平台+GitHub+Tavily | `dao_reverse.DaoReverse` | 00-本源_Origin | 搜索天下·排序·分析·适配 |
| **反·内(file)** | FCStd XML+BRep | `fc_reverse.FCReverse` | 10-反笙_FreeCAD | 从本地件逆向→ops→改参→重放 |
| **反·SW(CFB)** | MS-CFB+COM+eDrawings | `dao_solidworks` **v3.3.0** | 00-本源_Origin | SLDPRT/SLDASM/SLDDRW · L0→L9 全境: OLE2深反 + COM活体 + eDrawings兜底 + 深流carve + PE/Reg + 打通 + 几何反演 + Parasolid + **L9一键激活** |
| **激·SW(L9)** | 编排 L0.5→L5→COM活检→复诊 | `sw_activate` / `sw_activate_and_verify` | 00-本源_Origin | 从零到 COM 活体·管理员自知·severity 前后对比·next_steps 自指导 (v3.3.0) |
| **桥·夸克(Q)** | CDP 借客户端登录态 | `dao_quark_bridge.DaoQuarkBridge` | 00-本源_Origin | 夸克网盘 ×3D建模Agent 桥·分享链接解析·SW 资源自动定位+批量拉下·道法自然不落盘 cookie (v3.3.0) |
| **装·SW2026(L10)** | RAR→安装→激活→验证 全链路 | `sw2026_install` | 00-本源_Origin | 6 阶段 pipeline · 幂等 sentinel · dry-run 默 · 7-Zip 自备 · StartSWInstall /now 静默 · 失败兜 GUI · 激活 L9 · COM 活体 verify |
| **笙·用(show)** | FreeCAD GUI HTTP | `fc_show.FCShow` | 10-反笙_FreeCAD | 反向锚定·任何产物直抵 GUI 展示 |
| **笙·SW(show)** | SW COM GUI | `sw_show.SWShow` | 10-反笙_FreeCAD | SLDPRT 直抵 SolidWorks 窗口·多视角截图·批导出 |
| **笙·环境(env)** | Win32 + 对话框分类 | `SWHealthCheck` / `SWDialogHandler` / `EDrawingsLauncher` | 00-本源_Origin | license/COM/eDrawings 探测 · FlexLM 对话框断更 · eDrawings 窗口截图兜底 |
| **道(kernel)** | OCP/OCCT直连 | `dao_kernel.DaoKernel` | 00-本源_Origin | 一切BREP操作的本源 |
| **一(sugar)** | build123d | `dao_kernel.DaoBridge` | 00-本源_Origin | 高层语法糖 |
| **二(analysis)** | trimesh+numpy | `dao_kernel.DaoMesh` | 00-本源_Origin | 网格分析/质量检查 |
| **验(audit)** | BRepCheck+ShapeAnalysis | `dao_audit` | 00-本源_Origin | 八层审核(拓扑/几何/工程/装配/格式/参数/意图/感知) |
| **三(probe)** | HTTP+Playwright | `资源探针.py` | 00-本源_Origin | 20平台API逆向连接 |
| **锻(forge)** | FreeCAD 动态持久化 | `dao_forge.DaoForge` | 00-本源_Origin | 模型注册/ops/画廊 |
| **执(engine)** | 多引擎透明切换 | `dao_engine.DaoEngine` | 00-本源_Origin | 增量执行+反馈闭环 |
| **运动(kinematics)** | 零依赖纯 Python | `dao_kinematics` | 00-本源_Origin | 通用 FK/IK/动力学/干涉/平衡/临界转速 · 8 种关节 + Mechanism |
| **网格(mesh)** | 零依赖纯 Python | `dao_mesh` | 00-本源_Origin | STL(binary/ASCII) · OBJ · GLB 读写 · 体积/包围盒/流形 |
| **图纸(dxf)** | 零依赖纯 Python | `dao_dxf` | 00-本源_Origin | AC1009+ DXF 解析 · 实体 (LINE/TEXT/CIRCLE/ARC) · 尺寸抽取 |
| **文档(docx)** | 零依赖纯 Python | `dao_docx` | 00-本源_Origin | docx (ZIP) · 段落/图片/表格/关系 · 图题/章节自动抽取 |
| **验(verifier)** | 零依赖纯 Python | `dao_verifier` | 00-本源_Origin | N 相验证框架 · Phase/Check/评分 · Markdown+JSON dump |
| **环(loop)** | 零依赖纯 Python | `dao_loop` | 00-本源_Origin | 通用闭环控制器 · probe→build→verify→heal→reverify |
| **抱一(belt)** | 零依赖纯 Python (+ SW) | `道_抱一_带传动.BeltForge` | 00-本源_Origin | 传动几何自涌现 · 动态识别带轮+涌现皮带装配 · 六境: 发现→配对→成谋→锻造→安装→自愈 · 幂等不争 · 适配任意装配/带轮/平面 |
| 兼容 | CadQuery/OpenSCAD/FreeCAD | `forge_v3.py` | 20-万法_Forge | 统一CLI, 向后兼容 |

首选: **DaoReverse(外反)** → **FCReverse(内反)** → DaoKernel(道) → build123d(一) → 兼容引擎

## 反者道之动 · FCReverse (从 FreeCAD 件逆向突破)

从任何 FCStd/STEP/BREP 文件 → 可重放/可改参的 ops 序列.
建立在 `freecad_bridge` + `dao_forge` + `freecad_backend` 之上, 以最小代价打通闭环:

```
  天下件(.FCStd/.step/.brep) → FCReverse.reverse → ops[] → patch(id.param) → replay → 新件
```

**能力矩阵** (验证: 53 FCStd 件, 62.3% 可反演, 477 ops 成功):

| FC 类型 | → Op | 备注 |
|---------|------|------|
| Part::Box/Cylinder/Sphere/Cone/Torus | make_* | 原始几何完全参数化 |
| Part::Cut/Fuse/Common/Section | cut/fuse/common/section | 布尔(Base/Tool 依赖自动解析) |
| Part::Fillet/Chamfer/Offset/Thickness | fillet/chamfer/offset3d/shell | 修饰 |
| Part::Extrusion/Revolution/Loft/Sweep | extrude/revolve/loft/pipe | 衍生 |
| PartDesign::Pad/Pocket/Fillet | partdesign_pad/pocket/fillet | 特征 |
| Part::Feature (BRep引用) | import_brep (自动提取) | 通用容器 |
| Sketcher::SketchObject / Part::Part2DObjectPython | (未支持, 增强空间) |

## 入口

- `forge_v3.py reverse "意念"` — **外反** (20平台搜索)
- `forge_v3.py fc_reverse <file>` — **内反**: 件→ops.json
- `forge_v3.py fc_probe <file>` — 诊断: op_count + warnings + replayable
- `forge_v3.py fc_index [--refresh]` — 扫描天下件 (FreeCAD安装+projects+网络资源库)
- `forge_v3.py fc_search <query> [--kind fcstd|step|brep]` — 搜索本地索引
- `forge_v3.py fc_replay <ops.json> [--patch k=v,...]` — 执行/重放
- `forge_v3.py fc_adapt <file> [k=v ...]` — 一键: 反演+改参+重放
- `forge_v3.py search-world "query"` — 20平台全网搜索
- `forge_v3.py analyze-model <file>` — 本地模型分析
- `dao_reverse.py fulfill "意念"` — Python API 完整外反
- `fc_reverse.py {reverse|index|search|replay|adapt|probe}` — 本源单文件入口
- `dao_kernel.py verify` — 内核自验证 (43项)
- `forge_v3.py audit <step>` — 全八层审核
- `forge_v3.py check` — 环境检查
- `model_hub.py` :8872 — Dashboard+API

## 内反 · 典型用法

```bash
# 场景1: 直接用已有件
forge_v3.py fc_search "gear module" --kind fcstd
forge_v3.py fc_adapt <found.FCStd>   # 原样重放

# 场景2: 最小适配 (改尺寸)
forge_v3.py fc_adapt <phone_stand.FCStd> Body.L=120 Body.W=80
# 自动: 反演 → 打补丁 → 重放 → 导出 stl/step

# 场景3: 纯反演供 Cascade 分析
forge_v3.py fc_reverse <any.FCStd> > ops.json
# Cascade 读 ops.json, 理解意图, 生成修改建议

# 场景4: 批量诊断
for f in *.FCStd; do forge_v3.py fc_probe "$f"; done
```

**柔弱胜刚强**: 天下件 > 自建. 一条 `fc_adapt` 等价于 DaoKernel 数十行构建代码.

## 笙·用 · FCShow (反向锚定 FreeCAD GUI 为天生展示台)

> 得鱼而忘笙，复得返用笙 — 以 ops 为舟渡河 (笙)，既到，忘舟；再欲渡新河，复取其舟。

任何 **FCStd/STEP/BREP/STL/OBJ/IGES/ops** 皆可直达 GUI，内反(FCReverse)与外反(DaoReverse)的成果皆归于此台.

```text
本机 Python  ──HTTP──▶  FreeCAD GUI (:18920)
fc_show.FCShow          _fc_remote_server.py (既有 15 个API端点)
```

### FCShow 核心API (`fc_show.FCShow`)

| 方法 | 作用 |
|------|------|
| `ensure_gui()` | 若未启动, 自动启动 FreeCAD 1.0 + 远程服务器 (轮询就绪) |
| `status()` / `document()` / `documents()` | 查询当前状态 |
| `load(path)` | 加载任意格式文件 → 当前文档 (自动识别 FCStd/STEP/STL/…) |
| `load_many(paths)` | 批量加载 → 每文件一个 Part::Feature/Mesh (装配展示) |
| `load_ops(ops)` | 直接送 ops 到 GUI 线程 (via freecad_backend.run_ops) |
| `open_fcstd(path)` | 打开 FCStd (而非导入, 保留参数化特征树) |
| `view(action)` | isometric/front/top/right/home/perspective/orthographic |
| `fit()` / `isometric()` | 视图收敛 |
| `screenshot(path)` | PNG 1920×1080 |
| `live_show(src, shots=[..])` | 一键: 清空→加载→多角度截图 |
| `clear(close_all=False)` | 清空当前文档 / 关闭所有 |
| `save_as(path)` | 保存 FCStd |
| `exec_py(code)` | 在 GUI 线程执行任意 Python (调试逃生口) |

### CLI 入口 (`forge_v3.py`)

- `forge_v3.py fc_launch` — 启动 GUI + 远程服务器
- `forge_v3.py fc_show <file> [--shots iso,front,top,right]` — 一键秀
- `forge_v3.py fc_load <file>` / `fc_load_many <f1> <f2> …`
- `forge_v3.py fc_shot <name.png>` — 截屏当前视图
- `forge_v3.py fc_view <action>` / `fc_clear` / `fc_close_all`
- **`forge_v3.py fc_adapt <file> [k=v ...] --show`** — 反演+改参+重放 **+GUI展示** 一气呵成

### 典型用法 (三场闭环)

```bash
# 场景1: 打开既有大装配 (南京吴鸿轩 28件锤式破碎机)
forge_v3.py fc_show solidwork建模/南京-吴鸿轩/output_cq/assembly_full_v6.FCStd

# 场景2: 散装展示 (11 STEP 零件全部加载到一文档, 每件一 Feature)
forge_v3.py fc_load_many output_cq/*.step

# 场景3: 反演+改参 → 直接在 GUI 中看到新形状
forge_v3.py fc_adapt 万法.fcstd PDBox.L=120 PDCyl.R=25 --show
# 自动: 反演 → patch → replay → STEP导入GUI → 4角度截图
```

### 本源验证 (`_verify_show.py`)

**20/20 通过 · 等级 S** (空文档截图 / FCStd 加载 / 多视角 / STEP/STL 加载 / load_many / adapt+show / save+reopen).

`Part.export([sh])` **根本修复**: `Shape.exportStep(str)` 直接写盘, 支持 Compound/Solid/Shell, 避免 DocumentObject 封装.

## Agent协议 (Cascade)

```python
# 第一步: 反 — 搜索天下
from dao_reverse import DaoReverse
plan = DaoReverse.fulfill("用户需求")

# 第二步: 判 — 看plan.cascade_protocol.action
# "use_directly" / "adapt_existing" / "reference_and_build" / "build_from_scratch"

# 第三步: 行 — 执行最小操作
# 补充搜索: Tavily MCP / GitHub MCP / Context7 MCP
```

## 约束

- 收敛条件: full_audit.grade≥A + 意图忠实(L6) + 制造就绪(L2) + 感知评估(L7)
- 自主循环≤8轮
- 项目结构: `projects/<name>/` (reference/parts/output/params.json/report.md)
