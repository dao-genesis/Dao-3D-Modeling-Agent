# HANDOFF — 3D建模Agent 交接文档

> **道法自然 · 无为而无不为 · 为而不争**
>
> 此文档为后续 Agent / 开发者接手之入口。读此一文档，即可知全貌、可推进。

---

## 一句话

**3D建模Agent** 是一个以"反者道之动"为核心理念的通用 3D 建模 Agent：
收到任何建模需求 → **先搜天下已有** → 排序择优 → 下载分析 → 最小适配 → 交付。
仅当天下无有，方从无到有构建。

---

## 快速开始

```python
from 万法 import 道

道.summary()                                    # 系统状态
道.意("手机支架 70mm 可调角")                    # 意念直达 · 自动反向优先
道.反.外("phone stand 70mm")                    # 天下搜索 20 平台
道.反.内("model.FCStd", patch={"Body.L": 120})  # 本地件改参重放
道.秀.live_show("part.step")                    # FreeCAD GUI 展示
dao = 道.活体.connect()                         # SolidWorks memid 活体直连
```

CLI:
```bash
python 万法.py summary       # 系统状态
python 万法.py verify        # 万法验 · 23/23 PASS
python 万法.py intent "..."  # 意念直达
python 万法.py reverse "..." # 反·外(天下20平台)
python 万法.py show file.step # FreeCAD GUI 展示
python 万法.py live          # SolidWorks 活体直连
```

---

## 五层闭环架构

```
00-本源_Origin       道·一·二·三 (dao_kernel/audit/engine/forge/reverse/kinematics/...)
    ▲▼
10-反笙_FreeCAD      反·内 + 笙·用 (fc_reverse/show + freecad_backend/bridge/...)
    ▲▼
20-万法_Forge        统一调度 (forge_v3/model_hub/parametric_codegen/...)
    ▲▼
30-验证_Verify       本源验证 + 实战测试 (_verify_*/_e2e_*/_test_*)
    ▲▼
40/50/60/70          模板/演示/实战/天下
    ▲
_paths.py            路径自动引导 (五层 sys.path + 别名)
万法.py              单一入口 · 十五妙门懒加载
```

任意脚本开头四行即可贯通万法:
```python
import sys; from pathlib import Path
_DAO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / '_paths.py').is_file())
sys.path.insert(0, str(_DAO_ROOT)); import _paths as _dao_paths
```

---

## 十五妙门

| # | 门 | 入口 | 核心文件 | 用途 |
|---|---|---|---|---|
| ① | **核** | `道.核` | `dao_kernel.py` | OCP/OCCT BREP 零中间层建模 |
| ② | **反·外** | `道.反.外()` | `dao_reverse.py` | 20平台+GitHub+Web 搜索 |
| ②b | **反·内** | `道.反.内()` | `fc_reverse.py` | FCStd/STEP/BREP → ops → 改参 → 重放 |
| ③ | **秀** | `道.秀` | `fc_show.py` | FreeCAD GUI 天生展示台 (:18920) |
| ④ | **活体** | `道.活体` | `道_直连_底层.py` | SW memid 直连 (710接口, 14916方法) |
| ⑤ | **审** | `道.审` | `dao_audit.py` | 八层审核 (拓扑→感知) |
| ⑥ | **验** | `道.验` | `dao_verifier.py` | N相验证框架 |
| ⑦ | **循** | `道.循` | `dao_loop.py` | 闭环控制 probe→build→verify→heal |
| ⑧ | **运动** | `道.运动` | `dao_kinematics.py` | FK/IK/干涉/临界转速 |
| ⑨ | **网格** | `道.网格` | `dao_mesh.py` | STL/OBJ/GLB 读写 |
| ⑩ | **图纸** | `道.图纸` | `dao_dxf.py` | DXF 解析 + 尺寸抽取 |
| ⑪ | **文档** | `道.文档` | `dao_docx.py` | docx 段落/图/表 |
| ⑫ | **锻** | `道.锻` | `dao_forge.py` | FreeCAD 动态持久化 |
| ⑬ | **执** | `道.执` | `dao_engine.py` | 多引擎透明执行 |
| ⑭ | **宗** | `道.宗` | `dao_归宗.py` | 源码总摄 · 16宗221仓 |
| ⑮ | **同** | `道.同` | `dao_xuantong.py` | 玄同协议 · 多peer去中心化协作 |

---

## 三原则

### ① 反者道之动 — 先反后正
```
意念 → [反·外] 搜天下 → [反·内] 本地件 → [核] 从无到有
         (首选)         (次选)          (末选)
```
天下有 → 用天下的 · 天下近 → 改天下的 · 天下无 → 才自建

### ② 为而不争 — 不重造轮子
- 万法.py 不改既有代码, 仅 facade 聚合
- 新功能优先实现于最底层 (dao_*), 再由万法暴露
- 遇到多个实现, 选最底层的

### ③ 以神遇而不以目视 — 数理验证
- 装配几何矛盾, 用运动学扫描+计算取代视觉判断
- 审核先于修正: `道.审.full(shape)` → grade ≥ A 方交付
- 闭环优于一试: `道.循.controller(...)` 带 heal_registry 自动补救

---

## 状态契约 (Res)

所有 `道.*` 方法返回 `Res`:
```python
Res = {
    "ok": bool,          # 成功与否
    "data": Any,         # 主体结果
    "warnings": List[str],
    "error": Optional[str],
    "elapsed_s": float,
}
# 支持 dict 访问 (r["ok"]) 与 attr 访问 (r.ok)
```

---

## 核心文件索引

### 00-本源_Origin (道·一·二·三)

| 文件 | 大小 | 职责 |
|------|------|------|
| `dao_kernel.py` | 46KB | OCP/OCCT 直连 BREP 内核 · 43项自验 |
| `dao_audit.py` | 54KB | 八层审核 (拓扑→感知) + heal_shape |
| `dao_engine.py` | 37KB | 多引擎统一执行 |
| `dao_forge.py` | 39KB | FreeCAD 动态持久化 · 60+ ops |
| `dao_reverse.py` | 53KB | 反·外 5类 (IntentParser→WorldSearch→Ranker→Analyzer→Adapter) |
| `dao_kinematics.py` | 57KB | FK/IK/8关节/干涉/ISO 1940平衡 |
| `dao_mesh.py` | 29KB | STL/OBJ/GLB + 流形检测 |
| `dao_dxf.py` | 18KB | AC1009+ DXF 解析 |
| `dao_docx.py` | 22KB | docx ZIP 解析 |
| `dao_verifier.py` | 18KB | N相验证框架 |
| `dao_loop.py` | 27KB | 闭环控制器 |
| `道_直连_底层.py` | 46KB | SW memid 直连 · MemidTable + DaoDispatch + Dao |
| `道_直连_底层_facets.py` | 41KB | 五大facet: mate/transform/select/face/comp |
| `dao_solidworks.py` | 287KB | SW L0-L9 全境 · OLE2/COM/XT字节级深反 |
| `dao_sw_live.py` | 141KB | SW Builder群 (遗产·可被道直连器替代) |
| `dao_quark_bridge.py` | 60KB | 夸克网盘桥 · CDP借客户端登录态 |
| `dao_xuantong.py` | 24KB | 玄同协议接入桥 · 第十五妙门 |
| `dao_image.py` | 36KB | 图意处理 (第十六妙门方向) |
| `dao_mesh2brep.py` | 37KB | mesh → BREP 转换 |
| `dao_visual_search.py` | 27KB | 视觉相似度搜索 |
| `资源探针.py` | 65KB | 20平台 HTTP/Playwright 连接 |
| `sw2026_install.py` | 60KB | SW2026 全链路安装 |
| `道_抱一_带传动.py` | 90KB | 传动几何自涌现 · 动态识别带轮+皮带装配 |
| `道_意图_引擎.py` | 25KB | 意图→DesignTree→BuildPlan |
| `道_庖丁解牛.py` | 52KB | 装配拆解为拓扑图 |

### 10-反笙_FreeCAD

| 文件 | 职责 |
|------|------|
| `fc_reverse.py` | 反·内本源 · FCStd/STEP/BREP → ops → patch → replay |
| `fc_show.py` | 笙·用本源 · FC GUI 天生展示台 (HTTP :18920) |
| `fc_model_builder.py` | 参数化构建器 |
| `freecad_backend.py` | FC 内核 (在freecadcmd内跑 · 60+ ops) |
| `freecad_bridge.py` | 嵌入+子进程接口层 |
| `freecad_connection.py` | 连接管理器 (嵌入/子进程/GUI远程) |
| `freecad_gui_launcher.py` | GUI 启动器 |
| `freecad_gui_macro.py` | GUI 宏 |
| `_fc_remote_server.py` | HTTP 服务器 :18920 · 15端点 |
| `sw_show.py` | SW COM 展示台 |

### 20-万法_Forge

| 文件 | 职责 |
|------|------|
| `forge_v3.py` | 统一CLI (50+命令) |
| `model_hub.py` | HTTP Dashboard+API :8872 |
| `design_intent_compiler.py` | 意图编译器 |
| `parametric_codegen.py` | 参数化代码生成 |
| `geometric_preflight.py` | 空间预检 |
| `spatial_reasoning.md` | 认知基底 · 约束规则 |
| `model_viewer.html` | 浏览器 3D/VR 预览 |

---

## 验证状态

- **万法验**: `python 30-验证_Verify/_万法验.py` → **23/23 PASS · 0 FAIL · 0 WARN** (2026-04-23)
- **反者本源验**: 20/20 S (53 FCStd件, 62.3%可反演, 477 ops成功)
- **笙用本源验**: 20/20 S
- **七本源验**: 7/7 S (kinematics/mesh/dxf/docx/verifier/loop)
- **道直连器烟雾测**: 31.0.1 活体SW · 42组件 · 27 mate 全通过
- **实战·南京锤式破碎机**: 28件装配 · 5/5 PASS · 9.78s

---

## 实战项目

### 南京-吴鸿轩_锤式破碎机
- 30组件 (原37去7辅助) · 4×4锤头矩阵
- 完整闭环: 建模 → 装配 → 运动学 → 干涉 → 根治 → 交付
- 产物: STEP/STL/GLB/OBJ + BOM + 渲染图 + 工程图 + SW装配体
- 根治报告: V1-V6 (篮板tz修正 · 运动学根治 · 过约束清理)

### ORS6_Stewart
- Stewart并联机构 · 6-DOF
- 完整Python实现: geometry/kinematics/assembly/analysis

### chibi_mech
- Chibi Robot角色建模演示

---

## 环境要求

| 依赖 | 用途 |
|------|------|
| Python 3.11 | 运行时 |
| OpenSCAD 2021.01 | CSG渲染 |
| FreeCAD 1.0 | BREP/参数化/装配 |
| CadQuery | 精密参数化 |
| build123d | 现代造型 |
| trimesh 4.11 | 几何分析/修复 |
| OCP 7.7+ | OpenCascade Python绑定 |
| numpy/scipy | 数值计算 |
| Pillow | 图像处理 |
| rtree | 空间索引 |
| pywin32 | SolidWorks COM (Windows only) |

---

## 图意融合路线 (下一步)

详见 `反者道之动·图意融合·万法本源.md`

核心洞见: **ops 是 Mesh-Track 与 CAD-Track 的共同语言**

五阶落地:
1. **零增量** (1周): dao_reverse 加 image_query, CLIP视觉相似度搜天下
2. **低增量** (2-3周): dao_mesh2brep, RANSAC原语拟合 + dao_kernel BRep sewing
3. **中增量** (1月): dao_image_recode, 桥接 cadrille (开源多模态CAD)
4. **高增量** (2月): 桥接 Hunyuan3D/TRELLIS 为兜底
5. **玄同自治** (持续): graph.db 立图意leaves, 待真peer推进

---

## 玄同协议 (多peer协作)

详见 `反者道之动·玄同接入·退者之悟.md`

```python
from dao_xuantong import XuanTongPeer
p = XuanTongPeer.bootstrap(peer_id='your-id', kind='cascade', fingerprint={...})
p.status()           # 全局态
leaf = p.next_leaf() # 下一只leaf
p.claim(leaf['id'])  # 取
p.finding(leaf['id'], data={...}, evidence=[...])  # 提交
```

核心原则: **peer自取 · 不夺民事 · 不立王**

---

## 已排除内容 (不在本仓库)

以下内容因冗余/临时/过大而未上传，原路径可查:
- `90-日志_Logs/` — 运行日志 (可重新生成)
- `_archive/` — 跨层历史归档
- `00-本源_Origin/_archive_临时调试_2026Q2/` — 205件临时调试脚本
- `00-本源_Origin/` 中的 `_V7-V16_*`, `_probe_*`, `_inspect_*` 等 — 调试探针/临时修复
- `70-天下_World/源码_Sources/` — 16宗221仓源码 (75.6%覆盖, 可通过 `道.宗.取()` 重新拉取)
- `SolidWorks插件/` — 大型ZIP安装包 (419MB+)
- `60-实战_Projects/*.zip` — 项目打包ZIP
- `60-实战_Projects/南京-吴鸿轩_锤式破碎机/_archive/` — 调试归档
- `__pycache__/`, `.pytest_cache/` — Python缓存

---

## 版本

- 万法.py: v1.0.0 (2026-04-23)
- 道直连器: 710接口 · 14916方法 · 4262属性
- 验证: 23/23 PASS
- 项目版本: v1.1.0 (15妙门) → 待 v1.2.0 (16妙门含「图」)

---

**大道至简 · 此器成矣 · 以御万法**

> 上善若水, 水善利万物而不争. 处众人之所恶, 故几于道.
> 反者道之动, 弱者道之用. 天下之物生于有, 有生于无.
