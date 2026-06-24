# ModelForge — 三维意念的通用翻译器

> 消弭意念与实物之间的一切摩擦。
> 反者道之动 — 不从工具出发，从人的原始需求出发。
> 柔弱胜刚强 — 不从创造出发，从天下已有出发。
> **道法自然 · 万物并育而不相害 · 道并行而不相悖**

## 🜁 万法归一 · agent 单一入口 (v1.0.0 · 2026-04-23 新立)

> **圣人总而用之, 其数一也.**

```python
from 万法 import 道
道.summary()                                    # 系统状态
道.意("手机支架 70mm 可调角")                    # 意念直达 · 自动反向优先
道.反.外("phone stand 70mm")                    # 天下搜索 20 平台
道.反.内("model.FCStd", patch={"Body.L": 120})  # 本地件改参重放
道.秀.live_show("part.step")                    # FreeCAD GUI 展示
dao = 道.活体.connect()                         # SolidWorks memid 活体直连
```

十三妙门 (懒加载): **核 / 反·外 / 反·内 / 秀 / 活体 / 审 / 验 / 循 / 运动 / 网格 / 图纸 / 文档 / 锻 / 执**

- CLI: `python 万法.py {summary|verify|intent|reverse|adapt|show|live|audit|manifest}`
- Shell: `→万法.cmd <cmd>` (ASCII-only CRLF)
- 验道: `python 30-验证_Verify/_万法验.py` → **23/23 PASS** (2026-04-23)
- 清册: `万法清册.md` (决策矩阵: intent → module)

**老脚本 (`forge_v3.py`, `fc_*.py`, `道_直连_底层.py` 等) 悉数保留可用, 万法仅 facade 聚合, 不动既有. 为而不争.**

## 万法归一 · 五层闭环架构

```
                 ┌─────────── 意念输入 ───────────┐
                 │ (文字/图片/草图/旧件/规格书)   │
                 └────────────────┬───────────────┘
                                  ▼
  ╔════════════════════════════════════════════════════════════╗
  ║  00-本源_Origin       道 · 一 · 二 · 三                       ║
  ║  ├─ dao_kernel      OCP/OCCT 直连内核 (最底)                 ║
  ║  ├─ dao_audit       八层审核 (拓扑→感知)                     ║
  ║  ├─ dao_engine      增量执行引擎                              ║
  ║  ├─ dao_forge       FreeCAD 动态持久化锻造                   ║
  ║  ├─ dao_reverse     反·外: 20平台搜索                         ║
  ║  ├─ dao_kinematics  ★ 通用运动学底层 (FK/IK/动力学/干涉)     ║
  ║  ├─ dao_solidworks  ★★ SW 本源桥 v3.3.0 (L0→L9 全境)         ║
  ║  ├─ dao_sw_live     ★★★ L11 活体万象 (Sketch/Feature/Asm/Drw)║
  ║  ├─ dao_quark_bridge ★★ 夸克网盘桥 (CDP + 126 REST + SW 拉包)║
  ║  └─ 资源探针        天下连通器 (HTTP+Playwright)             ║
  ╚════════════════════════════════════════════════════════════╝
                                  ▲▼
  ╔════════════════════════════════════════════════════════════╗
  ║  10-反笙_FreeCAD      反·内 + 笙·用                         ║
  ║  ├─ fc_reverse    反·内: FCStd/STEP/BREP → ops              ║
  ║  ├─ fc_show       笙·用: FreeCAD GUI 展示台                 ║
  ║  ├─ fc_model_builder  参数化构建器                           ║
  ║  ├─ freecad_backend   内核 (60+ ops)                         ║
  ║  ├─ freecad_bridge/connection  嵌入+子进程接口层             ║
  ║  ├─ freecad_gui_launcher/macro GUI 宏/启动                   ║
  ║  └─ _fc_remote_server   GUI HTTP :18920                      ║
  ╚════════════════════════════════════════════════════════════╝
                                  ▲▼
  ╔════════════════════════════════════════════════════════════╗
  ║  20-万法_Forge        统一调度                                ║
  ║  ├─ forge_v3      统一 CLI (40+ 命令)                        ║
  ║  ├─ model_hub     HTTP Dashboard+API :8872                   ║
  ║  ├─ design_intent_compiler  意图编译器                       ║
  ║  ├─ parametric_codegen      参数化代码生成                   ║
  ║  ├─ geometric_preflight     空间预检                         ║
  ║  ├─ _playwright_scrapers    浏览器抓取层                     ║
  ║  └─ model_viewer.html       三维 VR 查看器                   ║
  ╚════════════════════════════════════════════════════════════╝
                                  ▲▼
  ╔════════════════════════════════════════════════════════════╗
  ║  30-验证_Verify       本源验证 + 实战测试                      ║
  ║  ├─ _verify_reverse/show    反·内/笙·用 本源 20 项验证       ║
  ║  ├─ _本源_verify, _万法归一_build  全域闭环验证               ║
  ║  ├─ _audit_e2e_test         八层审核 E2E                      ║
  ║  ├─ _e2e_verify/ultimate    连接管理器 E2E                   ║
  ║  ├─ _fc_probe, _fc_gui_deep_probe  FreeCAD 能力探针          ║
  ║  ├─ _bench_dao              性能基准                          ║
  ║  ├─ _demo_hammer_crusher    南京 28 件装配实战                ║
  ║  └─ _test_*                 单点测试                          ║
  ╚════════════════════════════════════════════════════════════╝
                                  ▲▼
  ┌──────── 资源层 (40/50/60/70) ───────────────────────────┐
  │  40-模板_Templates    4 引擎黄金模板 (CQ/b3d/SCAD/FC)     │
  │  50-演示_Demo          现成案例 (coffee_mug/chibi)        │
  │  60-实战_Projects      ORS6_Stewart + chibi_mech +        │
  │                        南京-吴鸿轩_锤式破碎机 (+各自_archive) │
  │  70-天下_World         网络资源库 + 运行时 cache (gitignore) │
  │  90-日志_Logs          .log 归档                          │
  │  _archive              sw_probes / sw_e2e_out /           │
  │                        fc_diagnostics (跨层历史归档)       │
  │  _paths.py             五层路径自动引导 (万法归一)         │
  └──────────────────────────────────────────────────────────┘
```

## 核心理念

**反者道之动，弱者道之用。最小化操作，最大化成果。无为而无不为。**

收到任何建模需求 → **先搜索天下已有** → 排序择优 → 下载分析 → 最小适配 → 交付。
仅当天下无有，方从无到有构建。

不限输入形态（一句话/图片/草图/旧模型/规格书）。
不限输出目的地（3D打印/CNC/注塑/激光切割/VR/工程图纸）。
不锁定建模引擎 — 需求决定工具，不是工具决定需求。

**Cascade = 大脑** · **dao_reverse.py = 天眼** · **dao_kernel.py = 双手** · **20平台 = 天下**

## 内部闭环

任意脚本 (无论层级) 开头:

```python
import sys; from pathlib import Path
_DAO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / '_paths.py').is_file())
sys.path.insert(0, str(_DAO_ROOT)); import _paths as _dao_paths   # 五层自动注入
```

此后:
- `from dao_kernel import DaoKernel`    # ← 00-本源
- `from fc_reverse import FCReverse`    # ← 10-反笙
- `from forge_v3 import ...`            # ← 20-万法
- `_dao_paths.PROJECTS` → 60-实战_Projects
- `_dao_paths.WORLD` → 70-天下_World
- `_dao_paths.TEMPLATES / DEMO / ORIGIN / REVERSE / FORGE / VERIFY`

## 六大原始能力

| # | 能力 | 含义 | 典型场景 |
|---|------|------|---------|
| ⓪ | **REVERSE-外** | 从天下到己 | "帮我建一个手机支架" → 先搜天下已有 → 适配 |
| ⓪b | **REVERSE-内** | 从己件到ops | FCStd/STEP/BREP → ops → 改参 → 重放 (`fc_adapt`) |
| ⓪c | **SHOW-笙用** | 反向锚定GUI | 任何产物(FCStd/STEP/STL/ops) → FreeCAD GUI 直显 (`fc_show`) |
| ① | **CREATE** | 从无到有 | 天下无有时 → DaoKernel参数化构建 |
| ② | **TRANSFORM** | 从有到优 | "把这个STL加4个M3螺丝孔" / "转成STEP" |
| ③ | **VERIFY** | 从疑到信 | "这个零件打印得出来吗" / "两个件会不会干涉" |
| ④ | **MANUFACTURE** | 从虚到实 | "生成FDM打印就绪文件" / "导出激光切割DXF" |
| ⑤ | **EXCHANGE** | 从己到人 | "导出STEP给工厂" / "生成BOM" / "推到Quest3" |

## 架构

```
用户发送意念（文字/图片/草图/旧模型/规格书）
       ↓
  ┌─ 0.反搜 ─── ★搜索天下20平台+GitHub+Web ──────┐
  │  1.感知 ─── 解构: 几何/功能/物理/制造/约束     │
  │  2.择优 ─── 排序已有模型 → 下载 → 分析差距     │
  │  ├ 天下有 → 直接使用/格式转换                  │
  │  ├ 天下近 → 最小适配(缩放/开孔/修复)           │
  │  └ 天下无 → 进入构建流程↓                      │
  │  3.建模 ─── DaoKernel/build123d参数化建模      │
  │  4.组装 ─── 装配+公差+干涉检查                 │
  │  5.验证 ─── 几何+尺寸+3D对比+物理分析          │  自主循环
  │  6.诊断 ─── 定位偏差根因(哪个部件/参数)         │  (≤8轮)
  │  7.修正 ─── 最小变更+回到3                      │
  └─ 8.交付 ─── 全格式输出+制造分析+报告 ──────────┘
```

## 引擎选择矩阵

Agent根据需求自动选择最佳路径，**反向优先**:

| 需求特征 | 最佳路径 | 命令 |
|---------|---------|------|
| **任何建模需求(首选)** | **反向搜索天下** | `forge_v3.py reverse <intent>` |
| 搜索已有模型 | 20平台并行搜索 | `forge_v3.py search-world <query>` |
| 分析已有模型 | trimesh/DaoKernel | `forge_v3.py analyze-model <file>` |
| 精密参数化(圆角/倒角) | DaoKernel/build123d | `forge_v3.py cq <code>` |
| 复杂工程(Sketch→Pad) | FreeCAD PartDesign | `forge_v3.py fc_build <type>` |
| 快速CSG原型 | OpenSCAD | `forge_v3.py scad <file>` |
| 现代Python造型 | build123d | `forge_v3.py b3d <code>` |
| 网格分析/修复 | trimesh | `forge_v3.py quality/mass` |
| 格式转换 | FreeCAD Import | `forge_v3.py convert` |

降级链：**反向搜索** → DaoKernel → build123d → CadQuery → OpenSCAD/FreeCAD。

## 使用方式

在Windsurf中对Cascade说任何三维需求：

```
# REVERSE (首选 — Agent自动执行)
> 帮我建一个手机支架，宽70mm，可调角度
  → Agent先搜索天下 → 找到已有 → 适配/直接使用

# CREATE (天下无有时)
> [发送图片] 帮我把这个建模出来

# TRANSFORM
> 把 output.stl 加4个M3沉头孔，间距40mm
> 把这个STEP文件的圆角从R2改成R3

# VERIFY
> 检查这个STL能不能FDM打印
> 这两个零件装配后会不会干涉

# MANUFACTURE
> 给这个模型做制造性分析（FDM）
> 导出激光切割用的DXF

# EXCHANGE
> 把所有零件导出STEP给工厂
> 生成零件清单和材料汇总
```

Agent自主完成全部工作。最终输出：

- `parts/*` — 参数化源码（.scad/.py/.FCStd，按引擎）
- `output/model.stl` — 可制造的STL
- `output/model.step` — 工程交换格式
- `output/preview_*.png` — 4视角预览图
- `params.json` — 统一参数表（跨引擎可读）
- `report.md` — 迭代对比报告

## 项目结构 (60-实战_Projects 下)

```
60-实战_Projects/<name>/
├── reference/          # 参考素材(图片/草图/旧模型/规格书)
├── parts/              # 子部件源码(.scad/.py/.FCStd)
├── output/             # 导出文件(STL/STEP/OBJ/DXF/PNG)
├── iterations/         # 迭代对比记录
├── assembly.*          # 主装配文件(格式随引擎)
├── params.json         # 统一参数表
├── iteration_log.json  # 迭代追踪
└── report.md           # 最终报告
```

已入库项目:
- `60-实战_Projects/南京-吴鸿轩_锤式破碎机/` — 28 件装配 (原 solidwork建模/南京-吴鸿轩)
- `60-实战_Projects/fc_output/` — FreeCAD 全局产物目录 (_万法归一/_fc_shots/…)
- `60-实战_Projects/chibi_mech/` — Chibi Robot 演示

## forge_v3.py 统一CLI (现位于 `20-万法_Forge/forge_v3.py`)

```bash
# 执行: python 20-万法_Forge\forge_v3.py <cmd>
# 或在 PowerShell: python "20-万法_Forge/forge_v3.py" <cmd>

# ★ 反向搜索（首选 — 先搜天下已有）
python 20-万法_Forge\forge_v3.py reverse "phone stand 70mm"     # 完整反向流水线
python 20-万法_Forge\forge_v3.py search-world "gear module 1.5" # 搜索天下20平台
python 20-万法_Forge\forge_v3.py analyze-model part.stl          # 分析已有模型

# ★ 反者 · 从 FreeCAD 件逆向突破 (10-反笙_FreeCAD/fc_reverse.py 本源)
python 20-万法_Forge\forge_v3.py fc_reverse model.FCStd          # FCStd → ops.json (特征+依赖+brep)
python 20-万法_Forge\forge_v3.py fc_probe   model.FCStd          # 诊断: op_count/warnings/replayable
python 20-万法_Forge\forge_v3.py fc_index --refresh              # 扫描527件
python 20-万法_Forge\forge_v3.py fc_search "involute" --kind fcstd
python 20-万法_Forge\forge_v3.py fc_replay ops.json --patch Body.L=120,Body.W=80
python 20-万法_Forge\forge_v3.py fc_adapt   existing.FCStd PDBox.L=100 PDBox.H=50   # 一键: 反演+改参+重放

# ★ 笙用 · 反向锚定 FreeCAD GUI 为天生展示台 (10-反笙_FreeCAD/fc_show.py 本源)
python 20-万法_Forge\forge_v3.py fc_launch                              # 启动 FreeCAD GUI + 远程服务器 :18920
python 20-万法_Forge\forge_v3.py fc_show assembly.FCStd                 # 一键: 清空→加载→4角度截图
python 20-万法_Forge\forge_v3.py fc_show model.step --shots isometric,front,top
python 20-万法_Forge\forge_v3.py fc_load_many part1.step part2.step ... # 批量加载至单一文档
python 20-万法_Forge\forge_v3.py fc_shot snap.png                       # 截屏当前视图 (1920×1080)
python 20-万法_Forge\forge_v3.py fc_view isometric                      # 视图: iso/front/top/right/home/perspective
python 20-万法_Forge\forge_v3.py fc_adapt model.FCStd Body.L=120 --show # 反演+改参+重放+GUI展示 一气呵成

# ★ SolidWorks 全境 (dao_solidworks v3.3.0 + dao_sw_live v4.0 · L0→L11 · 50 命令)
# 探测 / 深反 / 活体 (L0-L2):
python 20-万法_Forge\forge_v3.py sw_info                                 # SW 安装 + COM 诊断
python 20-万法_Forge\forge_v3.py sw_probe part.sldprt --json             # L1 OLE2 深反 (无需 SW)
python 20-万法_Forge\forge_v3.py sw_deep part.sldprt --json              # L1.5 深流 carve (特征+配置)
python 20-万法_Forge\forge_v3.py sw_geom part.sldprt                     # L6 几何反演 (Parasolid XT)
python 20-万法_Forge\forge_v3.py sw_live part.sldprt                     # 道法自然多路选优 (COM/eDrawings/OLE2)
# 打通 / 激活 (L5/L9 · v3.3.0 新):
python 20-万法_Forge\forge_v3.py sw_license                              # L0.5 许可系统诊断
python 20-万法_Forge\forge_v3.py sw_remediate                            # L5 打通规划 (dry_run)
python 20-万法_Forge\forge_v3.py sw_remediate --apply                    # L5 打通实执 (admin)
python 20-万法_Forge\forge_v3.py sw_activate                             # L9 一键激活 (dry_run)
python 20-万法_Forge\forge_v3.py sw_activate --apply --report act.json   # L9 实执 + 报告
python 20-万法_Forge\forge_v3.py sw_activate_verify --apply --launch --test-file part.sldprt
                                                                          # L9+ 激活+真启+截图
# 活体万象 (L11 · v4.0 新 · dao_sw_live · 从无到有真机建模):
python 20-万法_Forge\forge_v3.py sw_live_status                          # L11 活体状态 (版本/文档/连接)
python 20-万法_Forge\forge_v3.py sw_new_part --save-as out.sldprt        # 活体新建零件 (可选保存)
python 20-万法_Forge\forge_v3.py sw_build_demo --out D:\sw_demo         # 活体 demo: 建垫片 + 截图 + 多格式
python 20-万法_Forge\forge_v3.py sw_cmd SketchLine                        # 触发 SW 内部命令 (swCommands_e)
python 20-万法_Forge\forge_v3.py sw_list_cmds                            # 列 SW 常用命令 id 映射
python 20-万法_Forge\forge_v3.py sw_macro test.swp --module Main --proc main
                                                                          # 跑 VBA 宏
python 20-万法_Forge\forge_v3.py sw_prop_set Designer "Cascade" --type TXT
python 20-万法_Forge\forge_v3.py sw_eqn '"L"=100'                        # 追加方程
python 20-万法_Forge\forge_v3.py sw_material "普通碳钢"                  # 设材质
python 20-万法_Forge\forge_v3.py sw_live_snap iso.png --view iso          # L11 截图
python 30-验证_Verify\_sw_live_smoke_v2.py --timeout-per-step 30         # L11 真机 E2E (自保护超时)
# 夸克网盘桥 (Q · v3.3.0 新 · 需 CDP :19222):
python 20-万法_Forge\forge_v3.py sw_quark_status                         # 三态诊断
python 20-万法_Forge\forge_v3.py sw_quark_share https://pan.quark.cn/s/xxx --passcode XXX
python 20-万法_Forge\forge_v3.py sw_quark_find SolidWorks                # 全局搜索
python 20-万法_Forge\forge_v3.py sw_quark_locate                         # SW 资源自动定位
python 20-万法_Forge\forge_v3.py sw_from_quark --what installer --dst D:\sw
                                                                          # 一键拉 SW 安装包

# 分析
python forge_v3.py check                          # 环境+全引擎状态
python forge_v3.py mass <stl> [material]          # 质量/体积/重心
python forge_v3.py quality <stl>                  # 流形/法线/退化面
python forge_v3.py measure <stl>                  # 完整几何测量
python forge_v3.py collision <stl1> <stl2>        # 碰撞检测
python forge_v3.py compare <stl1> <stl2>          # 3D形状相似度
python forge_v3.py printability <stl> [fdm|sla]   # 可打印分析

# 空间推理（写代码前的认知层）
python forge_v3.py preflight <json|demo>          # 几何可行性预检+引擎建议

# 建模（多引擎）
python forge_v3.py scad <file> [out] [fn]         # OpenSCAD渲染
python forge_v3.py cq <code> [out]                # CadQuery
python forge_v3.py b3d <code> [out]               # build123d
python forge_v3.py freecad <script>               # FreeCAD脚本
python forge_v3.py fc_build <type> [params] [out] # FreeCAD参数化
python forge_v3.py fc_ops <ops_json>              # FreeCAD操作序列

# 工具
python forge_v3.py convert <in> <out>             # 格式转换
python forge_v3.py bom <dir>                      # 零件清单
python forge_v3.py batch <dir> [material]         # 批量分析
python forge_v3.py serve [port]                   # ModelHub :8872
```

## 制造性分析

`forge_v3.py printability`:

- **壁厚分析** — ray-casting采样500点，报告min/max/mean/中位数
- **悬臂分析** — 面法线角度，悬臂面积占比
- **底面接触** — 平底面积和稳定性
- **可打印评分** — 0-100综合评分
- **物理属性** — 质量/重心/惯性矩（`mass`命令）

## 环境要求

| 依赖 | 用途 | 状态 |
|------|------|------|
| Python 3.11 | 运行时 | ✅ |
| OpenSCAD 2021.01 | CSG渲染 | ✅ `D:\openscad\` |
| FreeCAD 1.0 | BREP/参数化/装配 | ✅ `D:\安装的软件\FreeCAD 1.0\` |
| FreeCAD 0.21 | 兼容性回退 | ✅ `D:\安装的软件\FreeCAD 0.21\` |
| CadQuery | 精密参数化 | ✅ pip |
| build123d | 现代造型 | ✅ pip |
| trimesh 4.11 | 几何分析/修复 | ✅ pip |
| rtree 1.4 | 空间索引 | ✅ pip |
| Pillow 10.3 | 图像处理 | ✅ pip |
| numpy/scipy | 数值计算 | ✅ pip |

## 代码规范（按引擎）

### OpenSCAD

```openscad
/* [杯身 / Body] */
body_height = 100;    // [60:1:150] 杯身高度 (mm)
body_diameter = 80;   // [50:1:120] 杯身外径 (mm)
wall_thickness = 3;   // [1.5:0.5:8] 壁厚 (mm)
```

### CadQuery

```python
result = (cq.Workplane("XY")
    .box(80, 80, 100)
    .edges("|Z").fillet(3)
    .faces(">Z").workplane().hole(60))
```

### FreeCAD (操作序列)

```json
{"ops": [
  {"op": "make_box", "id": "b1", "L": 80, "W": 80, "H": 100},
  {"op": "fillet", "id": "r1", "shape": "b1", "radius": 3}
]}
```

## 已知局限

- OpenSCAD CSG无法表达有机曲面 → 用FreeCAD Surface或build123d
- FreeCAD嵌入模式可能有DLL冲突 → 子进程模式更稳定
- 壁厚ray-casting有±0.1mm误差
- 渲染预览无PBR材质

## 文件索引 (按五层)

### 00-本源_Origin (道 · 一 · 二 · 三)
| 文件 | 角色 |
|------|------|
| `dao_kernel.py` | **道直连器**: OCP/OCCT零中间层BREP内核 |
| `dao_audit.py` | **审**: 八层审核 (拓扑→几何→工程→装配→格式→参数→意图→感知) |
| `dao_engine.py` | **执**: 增量执行引擎, 多引擎透明切换 |
| `dao_forge.py` | **锻**: FreeCAD 动态持久化, 模型注册/ops/画廊 |
| `dao_reverse.py` | **反·外**: 搜索天下20平台→排序→分析→适配 |
| `资源探针.py` | **天下连通器**: 20平台API逆向+Playwright |

### 10-反笙_FreeCAD (反·内 + 笙·用)
| 文件 | 角色 |
|------|------|
| `fc_reverse.py` | **反·内**: FCStd/STEP/BREP→ops→改参→重放 |
| `fc_show.py` | **笙·用**: FreeCAD GUI 远程控制·天生展示台 |
| `fc_model_builder.py` | FreeCAD参数化构建器 |
| `freecad_backend.py` | FreeCAD内核(运行在freecadcmd内, 60+ ops) |
| `freecad_bridge.py` | FreeCAD嵌入+子进程接口层 |
| `freecad_connection.py` | 连接管理器(嵌入/子进程/GUI远程) |
| `freecad_gui_launcher.py` | GUI 启动器 |
| `freecad_gui_macro.py` | GUI 宏 (动态链接 backend) |
| `_fc_remote_server.py` | GUI HTTP 服务器 :18920 (15 端点) |

### 20-万法_Forge (统一调度)
| 文件 | 角色 |
|------|------|
| `forge_v3.py` | 统一CLI入口（40+命令） |
| `model_hub.py` | HTTP Dashboard+API :8872 |
| `design_intent_compiler.py` | 设计意图编译器 (spec→DesignTree→BuildPlan) |
| `parametric_codegen.py` | 参数化代码生成 (DesignTree→代码) |
| `geometric_preflight.py` | **空间直觉层**: 几何预检/引擎选择 |
| `_playwright_scrapers.py` | Playwright浏览器抓取 |
| `model_viewer.html` | 浏览器 3D/VR 预览 |
| `spatial_reasoning.md` | **认知基底**: 约束规则/失败预测 |

### 30-验证_Verify (本源 + E2E)
| 文件 | 角色 |
|------|------|
| `_verify_reverse.py` | 反者本源验证 (20项, 万法.fcstd端到端) |
| `_verify_show.py` | 笙用本源验证 (20项 20/20, Grade S) |
| `_本源_verify.py`, `_万法归一_build.py` | 全域闭环验证 |
| `_audit_e2e_test.py` | 八层审核 E2E |
| `_e2e_verify.py`, `_e2e_ultimate_verify.py` | 连接管理器 E2E |
| `_fc_probe.py`, `_fc_gui_deep_probe.py` | FreeCAD 能力探针 |
| `_demo_hammer_crusher.py` | 实战·南京锤式破碎机 28件装配 GUI 三场展示 |
| `_bench_dao.py` | DaoKernel vs build123d vs CadQuery 基准 |
| `_test_*.py` | 单点测试 (OCP/STEP/CQ/FreeCAD ops) |
| `_run_*.py` | 运行器 (selftest/ops_test/full_e2e) |

### 资源层 (40 ~ 70)
| 目录 | 角色 |
|------|------|
| `40-模板_Templates/` | 4引擎黄金模板（CQ/b3d/SCAD/FC） |
| `50-演示_Demo/` | coffee_mug/chibi_robot 演示例 |
| `60-实战_Projects/` | 项目实例 + fc_output + 南京-吴鸿轩_锤式破碎机 |
| `70-天下_World/` | 网络资源库 + downloads + .resource_cache |
| `90-日志_Logs/` | .log 运行日志 |
| `_archive/` | 论文/旧资料归档 |
| `_paths.py` | **万法归一**: 五层路径自动引导 (根入口) |

## 详细Agent协议

→ `.windsurf/skills/3d-modeling/SKILL.md`

## 已验证案例

- `demo/coffee_mug.scad` — OpenSCAD: 2组件13参数，2.84s渲染，912面流形
- `demo/chibi_robot.scad` — OpenSCAD: 复杂多组件角色建模
- `forge_v3.py fc_build` — FreeCAD: 参数化box/cylinder/fillet/chamfer
- `forge_v3.py cq` — CadQuery: 内联代码→STL/STEP
- `forge_v3.py mass/quality/collision` — trimesh: 完整网格分析链
- `forge_v3.py preflight` — 空间推理: fillet/壁厚/孔径预检+引擎建议
- `forge_v3.py compare` — Hausdorff距离+体积+尺寸3D对比
- `forge_v3.py dxf` — 3D→2D DXF投影（激光切割/CNC）
- `templates/` — 6个黄金模板全Grade S watertight
