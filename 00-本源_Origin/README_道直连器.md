# 道直连器 (Dao Direct Connector)

> **反者道之动, 弱者道之用. 圣人执古之道, 以御今之有.**

从 Python 直达 SolidWorks 底层 · 无中间层 · 唯官方 `sldworks.tlb` 为源.

---

## 架构 · 去芜存菁

### 既存中间层 (淘汰对象 · ~800 KB 累赘)

| 文件 | 大小 | 角色 | 淘汰理由 |
| ---- | ---- | ---- | -------- |
| `dao_sw_live.py` | 140 KB | SketchBuilder / FeatureBuilder / AssemblyBuilder / ... | Python 包装层 · 每操作经两次转译 |
| `dao_sw_omni.py` | 65 KB | SWOmni wrapper | 再一重包装 · 叠床架屋 |
| `dao_sw_bridge.py` | 3 KB | re-exporter | 仅做 import 转发 |
| `dao_solidworks.py` | 287 KB | SolidWorksBridge · L0-L9 巨量逻辑 | property-vs-method 补丁 · gencache 污染对抗 |
| _com_prop / _com_call / _dyn_wrap | — | 动态分派二义性补丁 | memid 天然无歧义, 此类补丁全废 |

### 道直连器 (两文件 · 约 35 KB)

```text
  Python                 memid Invoke              COM                  SolidWorks
  ─────── ─────────────────────────────── ──────── ────────
  Dao    ·  DaoDispatch   → oleobj.Invoke(memid) → IDispatch        → 活体文档
   │        ↑                                         ↑
   │        └── MemidTable (从 sldworks.tlb 读 memid/ret/参数签名)
   │
   ├── sw/doc/asm/part/ext/sel/fm/sm/math  (顶级 DaoDispatch)
   └── mate/transform/select/face/comp     (域便捷 facets)
```

**tlb 已扫描**:

- 710 interfaces
- 14,916 methods
- 4,262 properties
- 1,064 enums
- 18 个 .tlb 文件 (sldworks.tlb + 17 辅助)

---

## 核心设计

### ① MemidTable — 单例 · 从官方 tlb 载入

```python
from 道_直连_底层 import MemidTable

mt = MemidTable()
mt.load()   # 自动定位 SolidWorks Corp23 下 sldworks.tlb + 辅助 .tlb
mt.stats()  # { interfaces: 710, methods: 14916, ... }

# 查 memid · 继承链 + 全局搜
mid = mt.memid("IAssemblyDoc", "FirstFeature")
# → SW 的 dispinterface 扁平 · FirstFeature 实际在 IModelDoc2 (memid 65801)
# MemidTable 透明处理 · 调用者无需关心

# 查签名
mt.signature("IAssemblyDoc", "AddMate5")
# → "IMate2* IAssemblyDoc::AddMate5(MateTypeFromEnum: long,
#     AlignFromEnum: long, Flip: bool, Distance: double,
#     DistanceAbsUpperLimit: double, DistanceAbsLowerLimit: double,
#     GearRatioNumerator: double, GearRatioDenominator: double,
#     Angle: double, AngleAbsUpperLimit: double, AngleAbsLowerLimit: double,
#     ForPositioningOnly: bool, LockRotation: bool,
#     WidthMateOption: long, ErrorStatus: long*)"
```

### ② DaoDispatch — 动态代理 · 按 memid 自动 Invoke

```python
from 道_直连_底层 import Dao

dao = Dao().connect()  # 或 connect_or_launch()

# 任意 SW API 直达 (__getattr__ 自动解析)
comps = dao.asm.GetComponentCount(False)       # 方法: 立即调用返 int
title = dao.doc.GetTitle()                      # 方法: 返 str
doc = dao.sw.ActiveDoc                          # 属性: 立即返 DaoDispatch

# 链式自动类型推断 (返回 IDispatch* 时包为 DaoDispatch)
feat = dao.asm.FirstFeature()                   # → DaoDispatch(IDispatch)
feat.cast("IFeature").GetTypeName2()            # → str
```

**智能判定** (关键):
- 属性 (PROPERTYGET, 0 args) → 立即 Invoke 返值
- 方法 (FUNC) → 返回闭包, 显式 `()` 调用
- 属性有参 (indexed property) → 返闭包
- 按 `DISPATCH_METHOD` / `DISPATCH_PROPERTYGET` 分别 flag (SW 对混合 flag 严格)

### ③ Dao — 单例 · 绑定活体

```python
dao.sw     # DaoDispatch(ISldWorks)         — 应用顶层
dao.doc    # DaoDispatch(IModelDoc2)        — 活文档
dao.asm    # DaoDispatch(IAssemblyDoc)      — 若文档是装配
dao.part   # DaoDispatch(IPartDoc)          — 若文档是零件
dao.drw    # DaoDispatch(IDrawingDoc)       — 若文档是工程图
dao.ext    # DaoDispatch(IModelDocExtension)
dao.sel    # DaoDispatch(ISelectionMgr)
dao.fm     # DaoDispatch(IFeatureManager)
dao.sm     # DaoDispatch(ISketchManager)
dao.math   # DaoDispatch(IMathUtility)
```

### ④ 域便捷 · 五大 facets

```python
# 配合 (face-direct, 无射线)
dao.mate.concentric(face_a, face_b, align=1, unfix_comp="hammer-1")
dao.mate.coincident(face_a, face_b)
dao.mate.distance(face_a, face_b, distance_mm=10)
dao.mate.parallel(face_a, face_b)
dao.mate.list_all()  # 返 [{name, type_name, type, error_status}]

# 变换 · Transform2 PUTREF 正途
dao.transform.set("hammer-1", pos_mm=(207, 220, 0),
                  rot=(0,0,-1, 0,1,0, 1,0,0))
origin = dao.transform.origin_mm("main_shaft-1")  # → (572.5, 0.0, 0.0)

# 选择
dao.select.by_id("main_shaft-1", "COMPONENT")
dao.select.component("hammer-1", append=True)
dao.select.plane("Front Plane")
dao.select.face_on_comp(face_ref, append=True)

# Face 扫描 (B-Rep · 装配上下文 · 世界坐标)
scan = dao.face.scan("hammer_pin-1")
# 返 faces: [{type, radius_mm, origin_mm, axis, face}]
face = dao.face.find_cylinder("hammer_pin-1",
                               radius_mm=15,
                               axis=(-1, 0, 0),
                               through_point_mm=(496, 220, 0))
# 返 face 句柄 · 可直送 mate

# 组件
dao.comp["main_shaft-1"]           # DaoDispatch(IComponent2)
dao.comp.is_fixed("hammer-1")      # bool
dao.comp.is_suppressed("belt_1")   # bool
dao.comp.fix("hammer-1")
dao.comp.unfix("hammer-1")
dao.comp.suppress("old_belt")
dao.comp.resolve("new_belt")
dao.comp.names()                    # [...]
dao.comp.fixed_names()              # [...]
dao.comp.suppressed_names()         # [...]
```

---

## 验道 · 烟雾测结果 (活体 SW 31.0.1)

测试装配: `锤式破碎机_总装配.SLDASM` (42 components)

```text
═══ 道直连器 · 烟雾测 ═══

[1] tlb 载入: True
    接口 710 · 方法 14916 · 属性 4262 · 枚举 1064

[5] 组件摘要:
    组件数: 42
      main_shaft-1     fixed=True supp=False
      driven_pulley-1  fixed=True supp=False
      hammer_pin-1     fixed=True supp=False
      ...

[6] Transform 读:
    main_shaft-1: origin_mm=(572.5, 0.0, 0.0)
    rotor_disc-1: origin_mm=(194.5, 0.0, 0.0)
    hammer_pin-1: origin_mm=(496.0, 220.0, 0.0)

[7] face 扫描 (hammer_pin-1):
    cyl: R=15.0mm O=(1141.0, 220.0, 0.0) axis=(-1.0, 0.0, 0.0)  ← pin 顶端
    cyl: R=15.0mm O=(496.0,  220.0, 0.0) axis=(-1.0, 0.0, 0.0)  ← pin 底端
    cyl: R=20.0mm O=(521.0,  220.0, 0.0) axis=(-1.0, 0.0, 0.0)  ← hub

[8] 当前 mate 列表 (共 27):
    同心26-51 (MateConcentric) × 26
    平行1     (MateParallel)   × 1

═══ 道直连 · 活体验毕 ═══
```

**与 `progress.txt` 记载完全一致**: 10 spine Concentric (26-35) + 16 hammer-pin
Concentric (36-51) + 1 drive-motor Parallel.

---

## Migration · 从旧中间层迁移

### 旧代码 (dao_sw_live / dao_sw_bridge)

```python
from dao_sw_bridge import sw_connect
live = sw_connect()
doc = live.active()
part = live.new_part()
part.sketch.start_front()
part.sketch.rect(-25, -25, 25, 25)
part.feature.extrude(depth=10)

# 配合
comp1 = live.find_comp("shaft-1")
comp2 = live.find_comp("hub-1")
live.mate.concentric(comp1, comp2)  # 通过 ray-cast selection
```

### 新代码 (道直连器)

```python
from 道_直连_底层 import Dao

dao = Dao().connect()

# 草图 / 特征 — 直调 SW API (无 Builder 包装)
dao.doc.Extension.SelectByID2("Front Plane", "PLANE",
                               0, 0, 0, False, 0, None, 0)
dao.sm.InsertSketch(True)  # ISketchManager.InsertSketch
dao.sm.CreateCenterRectangle(-0.025, -0.025, 0, 0.025, 0.025, 0)
dao.sm.InsertSketch(True)
dao.fm.FeatureExtrusion3(...)

# 配合 — face 句柄 (无射线墙)
face_a = dao.face.find_cylinder("shaft-1", radius_mm=10, axis=(0, 0, 1))
face_b = dao.face.find_cylinder("hub-1",   radius_mm=10, axis=(0, 0, 1))
dao.mate.concentric(face_a, face_b, align=1)
```

### 共存 · 渐进迁移

旧中间层仍可独立使用. 两者共用同一 SW COM 连接:

```python
from 道_直连_底层 import Dao
from dao_solidworks import SolidWorksBridge  # 仅用 OLE2 / XT 深反这类老 feature

dao = Dao().connect()
bridge = SolidWorksBridge()  # 共享 SW 活体

# 用 dao 做日常操作, 用 bridge 做 L1 深反
parts_xt = bridge.dump_parasolid("xxx.sldprt")
```

---

## CLI

```bash
# 连接 + 打印摘要 (tlb 统计, 活文档)
python 道_直连_底层.py connect

# 探活 (活文档基本状态)
python 道_直连_底层.py probe

# 列 top 20 接口 (按方法数)
python 道_直连_底层.py interfaces

# 查任意方法签名
python 道_直连_底层.py sig IAssemblyDoc AddMate5

# 任意调用 (iface method args...)
python 道_直连_底层.py call IAssemblyDoc GetComponentCount false
```

---

## 关键 COM 知识点 (血泪经验)

### 1. SW tlb 是 **扁平** dispinterface · 无显式继承

- `IAssemblyDoc` 不 declared-inherits `IModelDoc2` — 每个接口独立存 memid 表
- 但活体 `AssemblyDoc` 对象通过 IDispatch **共享** 父接口的 memid
- 解法: `MemidTable.find_anywhere()` 全局搜 · 偏好 IModelDoc2 / IModelDoc / ISldWorks

### 2. Property 与 Method 严格区分 flag

- SW COM 对 `DISPATCH_METHOD | DISPATCH_PROPERTYGET` 组合敏感
- 纯方法 (invkind=1) → `DISPATCH_METHOD` 单独
- 纯属性 (invkind=2 无参) → `DISPATCH_PROPERTYGET` 单独, 立即 Invoke
- Property-with-args (PROPERTYPUTREF) → 闭包延迟调用

### 3. IMate2.ErrorStatus 已迁移至 IMateFeatureData (SW 2023+)

```python
mate = ...  # DaoDispatch(IMate2)
mfd = mate.MateFeatureData.cast("IMateFeatureData")
err = mfd.ErrorStatus
```

### 4. IComponent2.Transform2 是 property-with-args (GET 无参 · PUTREF 1 参)

```python
# 读
xf = dao.transform.get("hammer-1")  # 16-float list

# 强设 (绕 AddComponent5 bbox-center bug)
dao.transform.set("hammer-1", pos_mm=(207, 220, 0),
                  rot=(0,0,-1, 0,1,0, 1,0,0))
```

### 5. face 句柄 · `face.Select4` 直选 (无射线墙)

```python
# 通过 IComponent2.GetBody 拿装配上下文 body
# body.GetFaces 枚举 · ISurface.CylinderParams 取几何
# face.Select4(append, _nothing()) 直选
```

---

## 约束 · 已知边缘情形

| 项 | 说明 |
| ---- | ---- |
| `ErrorStatus -1` | SW 2023+ · IMate2 直接访问失败 · 已改走 MateFeatureData 路径 |
| pywin32 dynamic dispatch 失败 | 对某些 SW 对象 `d.FirstFeature` 报 "找不到成员" · 故彻底不用 dyn fallback, 全走 memid |
| `Callable` property 残留 | 个别 ArrayData 等在某些版本登记为 method, 代码兼容 callable + 非 callable |
| `IDispatch` 无类型推断 | 当 tlb ret_type = `IDispatch*`, 包为 `DaoDispatch("IDispatch")` · 用户需 `.cast("IFeature")` 等 |

---

## 目录结构

```text
00-本源_Origin/
├── 道_直连_底层.py          # 核心 · MemidTable + DaoDispatch + Dao (约 45 KB)
├── 道_直连_底层_facets.py   # 域便捷 · mate/transform/select/face/comp (约 30 KB)
├── README_道直连器.md       # 本文档
├── _dao_直连_smoke.py       # 烟雾测 · 9 步连通验证
├── _dao_快照.py             # 装配快照 · JSON+MD 导出
├── _dao_产物.py             # 产物终章 · BOM/health/4 视图/xray/碰撞/质量
├── _产物输出/               # 生成产物目录
│   ├── BOM.csv              # Part Qty 表
│   ├── health_report.md     # 装配健康度
│   ├── view_iso/front/top/right.png  # 4 标准视图
│   ├── skeleton_iso.png     # 隐 casing 后内脏
│   ├── xray_iso.png         # 深透 · 露 shaft/disc/pin/hammer
│   └── summary.json         # 全量结构化汇总
│
├── [LEGACY · 仅保留深反功能]
├── dao_solidworks.py        # OLE2 / XT 字节级深反 · L0-L9 (287 KB · 保留)
├── dao_sw_live.py           # Builder 群 (140 KB · 可淘汰)
├── dao_sw_omni.py           # 再一重包装 (65 KB · 可淘汰)
├── dao_sw_bridge.py         # re-exporter (3 KB · 可淘汰)
└── 道_本源_逆向万法.py       # v2.2.0 · 早期 MemidRegistry 原型 (120 KB · 已被本器吸收)
```

---

## 正途进阶

1. **用直连器重写 `道_抱一_带传动.py`** (89 KB, 传动建造)
   - 旧: 依赖 SolidWorksBridge + SketchBuilder
   - 新: 纯 memid 直调 sldworks.tlb

2. **用直连器重写 `sw_show.SWShow`** (笙·用)
   - 旧: dao_sw_live.CommandRunner
   - 新: `dao.sw.RunCommand(swCmdID)` 直调

3. **抽 `dao_solidworks.py` 的 L1 深反** 成独立文件 `dao_sw_ole2.py`
   - 保留 OLE2Parser / XTBlockInfo / ParasolidCatalog 字节级能力
   - 去除 L2 COM 层 (归 道直连器)

---

**道者, 万物之奥. 善人之宝, 不善人之所保.**

> 此器成矣 · 无为而无不为 · 以御万法
