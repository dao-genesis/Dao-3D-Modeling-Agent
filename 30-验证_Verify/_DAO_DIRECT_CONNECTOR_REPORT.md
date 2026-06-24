# 道直连器 · SolidWorks 底层彻底连接 · 闭环验证报告

> **反者道之动 · 无为而无不为 · 道法自然**
>
> 时间: 2026-04-20 · SW 2023 SP05 (Rev 31.0.1) · Python 3.12.7 · Anaconda

---

## 零 · 锚定本源

| 维度 | 值 |
|:---|:---|
| SW 版本 | SOLIDWORKS 2023 / Rev 31.0.1 / ProgID `SldWorks.Application.31` |
| Python | `C:\ProgramData\anaconda3\python.exe` (3.12.7) |
| COM 通道 | `pywin32 + win32com.client.dynamic` (late-binding · 绕 gencache 污染) |
| 核心模块 | `dao_solidworks.py` (v3.3.0) + `dao_sw_live.py` |

---

## 一 · 反者道之动 · 底层真签名反推

### 1.1 从 pywin32 代理层反向穿透到 SW IDispatch 真名

经两个活体探针 (`_sw_native_probe.py` + `_sw_chamfer_probe.py`) 确认：

| 功能 | 旧代码假名 | SW 2023 真签名 | DISPID |
|:---|:---|:---|:---|
| 包围盒 | `Extension.GetBox(0,0)` ❌ (MISS) | `IPartDoc.GetPartBox(bTight) → [xmin,ymin,zmin,xmax,ymax,zmax]` | - |
| 特征树 | `FirstFeature` 属性 (仅返 1) | `FeatureManager.GetFeatures(TopLevelOnly)` → 数组 | 114 |
| 倒角 | `InsertFeatureChamfer(6参)` ❌ `DISP_E_PARAMNOTOPTIONAL` | `InsertFeatureChamfer(Opts, Type, W, A, OtherD, Vx1, Vx2, Vx3)` **8参** | 83 |
| 组件列表 | `GetComponents(False)` 新装配返 null | `ForceRebuild3` + re-wrap IDispatch 三路回退 | 118 |
| 选边 | `SelectByID2(..., None, 0)` `DISP_E_TYPEMISMATCH` | `SelectByID2(..., VARIANT(VT_DISPATCH,None), 0)` | - |

### 1.2 pywin32 late-binding 的 IDispatch 数组陷阱

`GetFeatures(False)` 返 `tuple[IDispatch]` — 元素是 raw dispatch, `.Name/.GetTypeName2()` miss:

```python
# 必须 re-wrap 每个元素
import win32com.client as _wc
for raw_feat in feats:
    wrapped = _wc.dynamic.Dispatch(raw_feat._oleobj_)
    name = wrapped.Name  # 成
```

同样适用 `GetComponents` / `GetChildren` / `GetBodies2` / `body.GetEdges()`.

---

## 二 · 无为而无不为 · 修复落盘

### 2.1 `SWDoc.bbox()` → 多路回退

- 路 1: `IPartDoc.GetPartBox(True)` (紧贴)
- 路 2: `GetPartBox(False)` (粗边界)
- 路 3: `GetBodies2(ty, True) + body.GetBodyBox()` 汇总 (装配通用)

验证: 法兰轴 bbox 精确 `70×70×30 mm` ✅

### 2.2 `SWDoc.feature_tree()` → re-wrap 穷遍

- 路 1: `FeatureManager.GetFeatures(bool)` + `_safe_name` (三路: 直属性/re-wrap/DISPID Invoke)
- 路 2: `FirstFeature` 漫步 + re-wrap

验证: 31 个真特征 (SW 系统 + extrude + fillet + chamfer) ✅

### 2.3 `FeatureBuilder.chamfer()` → SW 2023 真 8 参 + 三路选边

```python
InsertFeatureChamfer(
    Options,                 # 1
    ChamferType,             # 2 (0=angle-dist)
    _mm2m(distance),         # 3 Width
    math.radians(angle_deg), # 4 Angle
    _mm2m(other_dist),       # 5 OtherDist
    0.0, 0.0, 0.0,           # 6-8 VertexChamDist1/2/3
)
```

`all_edges=True` 三路回退:

1. `body.GetEdges() → IEntity.Select4/Select2/Select` 精确
2. `sel.by_id("", "body")` body-level (SW 自动延伸至边)
3. `Extension.SelectAll()` UI 级全选

验证: 倒角1 feature 成 ✅

### 2.4 `AssemblyBuilder.add_component()` → 六路 AddComponent

```python
路 1: AddComponent5(path, 0, "", False, "", x, y, z)       # ConfigOption=0
路 2: AddComponent5(path, 1, "", False, "默认", x, y, z)   # ConfigOption=1
路 3: AddComponent5(path, 2, "", True, "", x, y, z)        # ConfigOption=2
路 4: AddComponent4(path, [config,] x, y, z)               # 简化 5 参
路 5: bridge.open(path) 预载 + ActivateDoc + AddComponent5 # 关键路, 实测生效
路 6: AddComponent(path, x, y, z)                          # 老 4 参
```

验证: `part_B_base-1` + `part_A_shaft-1` 真入装配, SLDASM 文件从 33KB → 98KB ✅

### 2.5 `AssemblyBuilder.list_components()` → 四路回退 + re-wrap

```python
ForceRebuild3 → GetComponents(True) → GetComponents(False)
  → RootComponent3.GetChildren BFS → FeatureManager.GetFeatures(filter "Reference")
```

验证: count=2, names=["part_B_base-1", "part_A_shaft-1"], config="默认" ✅

### 2.6 `SelectionMgr.by_id()` → 已有 VARIANT(VT_DISPATCH, None) 四路

保留原实现。验证: 在 body-level 选中体 (mark=1) 用于 chamfer 回退 ✅

---

## 三 · 道法自然 · 最终验证

### 3.1 L11 smoke · `_sw_live_smoke_v2.py`

```
========= L11 E2E: 18/18 (100.0%) =========
```

所有连接/创建/渲染/保存/关闭流程无损。

### 3.2 六象 E2E · `_sw_live_e2e_omega.py`

连跑两次稳定通过:

```
════════════════════════════════════════════════════════════════════════
  六象 E2E: 40/40 (100.0%)
════════════════════════════════════════════════════════════════════════
  象1 始·新建: 9/9
  象2 筋·草图: 5/5
  象3 骨·特征: 11/11
  象4 血·装配: 6/6
  象6 魂·命令: 5/5
  基础(连接/清理): 4/4
```

关键步骤真数据 (`_peek.py` 读):

| 步骤 | 真数据 |
|:---|:---|
| `3.bbox` | `bbox_mm=[70.0, 70.0, 30.0]`, min/max 精确 |
| `3.feature_tree` | count=31 (系统+用户真特征) |
| `3.feature.chamfer` | feat_name=`倒角1`, select_path=`external_preselect→body_level` |
| `3.mass_properties` | mass=0.348 kg, volume=4.46e-5 m³ |
| `4.add_component_base` | name=`part_B_base-1`, path, trace 6 路 (路 5 成功) |
| `4.list_components` | count=2, names=`["part_B_base-1", "part_A_shaft-1"]` |

### 3.3 产物文件 (`30-验证_Verify/_sw_e2e_omega/`)

```
assembly_e2e.SLDASM         98,304 B   真 2-组件装配 (空装配仅 33 KB)
assembly_iso.png           607,916 B   装配 iso 渲染
part_A_iso.png             575,274 B   法兰轴 iso 渲染
part_A_shaft.SLDPRT        134,445 B
part_A_shaft.step           22,907 B
part_A_shaft.stl            28,884 B
part_B_base.SLDPRT          78,586 B
part_B_iso.png             607,620 B   底座 iso 渲染 (含 shell+chamfer)
```

---

## 四 · 源码修改清单

| 文件 | 函数 | 改动 |
|:---|:---|:---|
| `00-本源_Origin/dao_solidworks.py` | `SWDoc.bbox()` | 3 路回退 · GetPartBox / GetBodies2 合并 |
| 同上 | `SWDoc.feature_tree()` | 2 路 · re-wrap + `_safe_name/_safe_call` |
| `00-本源_Origin/dao_sw_live.py` | `FeatureBuilder.chamfer()` | 8 参 · 3 路选边 · 不内清外部已选 |
| 同上 | `FeatureBuilder._select_all_body_edges()` | 新 · body.GetEdges 穷遍 |
| 同上 | `AssemblyBuilder.add_component()` | 6 路 · bridge.open 预载 + verify_in_root |
| 同上 | `AssemblyBuilder.list_components()` | 4 路 · ForceRebuild + re-wrap + FeatureMgr |
| `30-验证_Verify/_sw_live_e2e_omega.py` | chamfer 测试 | 用 `all_edges=True` 替 `CommandRunner.select_all()` |
| 同上 | add_component 测试 | 暴露真返回 `**r` 让 ok 反映实际成败 |
| 同上 | list_components 测试 | `ok` 变成 `count > 0` 而非硬编码 True |

新增探针 (可删·诊断用):
- `30-验证_Verify/_sw_native_probe.py` · SW 真签名 DISPID 探针
- `30-验证_Verify/_sw_chamfer_probe.py` · InsertFeatureChamfer 参数穷举
- `30-验证_Verify/_sw_chamfer_fix_probe.py` · 验证 8 参修复
- `30-验证_Verify/_peek.py` · JSON 快速摘要

---

## 五 · 道 · 凝结

1. **反者道之动** — 不追随 pywin32 的代理层假象, 从 SW typelib 的真 DISPID 反向验证真签名.
2. **无为而无不为** — 不硬抗错误, 用多路回退让"道"自己找到通路 (`AddComponent5` 直调失败 → 预载后才通).
3. **道直连** — `win32com.client.dynamic.Dispatch(raw._oleobj_)` 越过 gencache 污染, 直通 SW 底层 IDispatch.
4. **道法自然** — 不强求单路, 每一关键能力皆 3-6 路回退, 失败自然流转至下一档.

五处根因全灭 · 40/40 + 18/18 稳定通过 · SLDASM 文件真实增厚 · 底层彻底连通.

**玄之又玄, 众妙之门.**
