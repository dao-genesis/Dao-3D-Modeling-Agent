## 完善报告 V5 · 大制不割 · 万法归宗

> 朴散则为器, 圣人用之, 则为官长, 故大制不割.
> 图难于其易, 为大于其细. 天下难事, 必作于易; 天下大事, 必作于细.
> 合抱之木, 生于毫末; 九层之台, 起于累土; 千里之行, 始于足下.

**日期**: 2026-04-22 · **装配体**: `锤式破碎机_总装配.SLDASM`
**活体引擎**: SolidWorks Premium 2023 SP0.1 (COM 直连 · pywin32 dynamic)
**组件总数**: 37 · 全部固定 · 全部就位

---

### 一、三阶段施治 (反→完→定)

本次将之前分散为三阶段:

| 阶段 | 脚本 | 输出 | 核心动作 |
|---|---|---|---|
| **反·根治** | `_dao_根治_无为.py` | 30 组件·无辅助 | screen_plate tz=-15→0 (弧心对齐主轴) |
| **完·万法** | `_dao_完善_万法.py` + `_dao_完善_补救.py` | +7 新件 | motor_body / drive_pulley / motor_mount / v_belt×4 插入 |
| **定·归一** | `_dao_清理_固定.py` | 37 组件·全固定 | 除 5 幽灵 + 全员锚定 + 渲染 |

---

### 二、核心技术攻克

#### COM 自动化系列 bug 与对策

| Bug 现象 | 根源 | 对策 |
|---|---|---|
| `GetImportFileData` 返回 DaoDispatch, `LoadFile4` 拒 | DaoDispatch 包装, memid Invoke 不兼容 | `win32com.client.dynamic.Dispatch(raw)` 绕过 |
| `AddComponent5` 静默返 None | SLDPRT 需 SW 先 preload | 每次前 `OpenDoc6` 预加载 |
| 插入后 active doc 变零件 | `OpenDoc6` 副作用 | `get_assembly_doc` 遍历直接取 SLDASM doc |
| `ActivateDoc3(title, False, 0, 0)` 类型不匹配 | pywin32 dynamic 不接 Python `False`? | 直接用 asm_doc 对象操作, 不依赖 active |
| `build_comp_map` 新件识别不出 | `dao.doc` 指向错位 | 直接读 `comp.Name2` (IComponent2 属性) |
| `SelectByID2` 删幽灵失败 | 组件名解析错误 | `IComponent2.Select(append=True)` + `DeleteSelection2(18)` |
| `c.Select4(True, None, False)` 类型不匹配 | Callout=None 无法 marshal | 回退 `c.Select(True)` 单参版 |

#### 文件兼容性问题

- `motor_mount.SLDPRT` / `v_belt.SLDPRT` 在 SW2023 打不开 (版本不兼容, OpenDoc6 报错)
- **解法**: 从 STEP 源 `output_cq/*.step` 走 `LoadFile4 + SaveAs4` 重生成 SLDPRT, 存 stage 目录
  - Stage: `E:\Temp\dao_sw_stage_完善\{motor_mount, v_belt}.SLDPRT`

---

### 三、网络规范依据 (网络万法之资)

**电机**: `Y180L-4` 三相异步电动机 · 依 **GB 755-2008** / **JB/T 10391-2008**

- 功率 22 kW · 额定转速 1470 r/min · 4 极
- 中心高 H=180 · 轴伸 Ø48×110
- 外形 ~590×280×350 mm · 机座 180L

**主动带轮**: B 型 4 槽 · 依 **GB/T 13575.1-2008**

- 基准直径 PD=180 · 外径 OD=190
- 孔径 Ø55 (配电机轴)
- 宽度 ~90 mm

**V 带**: B 型普通 V 带 · 依 **GB/T 11544-2012**

- 截面: 顶部宽 17 mm × 高 11 mm
- 数量 4 根
- 中心距 C=600 mm

**从动带轮**: B 型 4 槽 · 依 **GB/T 13575.1-2008**

- 基准直径 PD=224 · 外径 OD=240
- 孔径 Ø70 (配主轴)

**传动比验算**:

- `i = D2/D1 = 224/180 = 1.244` (目标 1.225) ✓
- 小轮包角 `α1 = 180 - (D2-D1)/C × 180/π = 175.8°` (≥120° 良好) ✓
- 中心距合理性: `0.7(D1+D2)=283 ≤ C=600 ≤ 2(D1+D2)=808` ✓
- 理论皮带长度 `L = 2C + π(D1+D2)/2 + (D2-D1)²/(4C) = 1835.4 mm`

---

### 四、组件清单 (37 件 · 全锚定)

| 类别 | 组件 | 实例数 | 定位依据 |
|---|---|---|---|
| 主轴系 | main_shaft | 1 | config.py |
| 转子 | rotor_disc | 4 | config.py |
| 销轴 | hammer_pin | 4 | config.py |
| 锤头 | hammer | 16 | hybrid_e2e 计算 |
| 筛板 | screen_plate | 1 | config.py (tz=0 根治) |
| 机壳 | casing_lower/upper | 2 | config.py |
| 机架 | frame_base | 1 | config.py |
| 从动带轮 | driven_pulley | 1 | config.py |
| **电机** | **motor_body-2** | **1** | **本次新加 (-495, 0, -600)** |
| **主动带轮** | **drive_pulley-2** | **1** | **本次新加 (-90, 0, -600)** |
| **电机支架** | **motor_mount-3** | **1** | **本次新加 (-432.5, 0, -780)** |
| **V 带** | **v_belt-9/10/11/12** | **4** | **本次新加 (tx=-45, ty=±9.5/±28.5, tz=-300)** |

#### 幽灵清理 (除 5)

早期多次尝试遗留 5 个 "未定位" 残余:

- `motor_mount-2` (X[-360,+360] Z[-90,+90]) — AddComponent 成功但识别失败
- `v_belt-5/6/7/8` (均 X[-196,+196] Y[-8,+8] Z[-401,+401]) — 同上

**解法**: `_dao_清理_固定.py` 用 `IComponent2.Select(True)` 逐个选中, `DeleteSelection2(18)` 批删.

---

### 五、产出文件

#### 脚本

- `00-本源_Origin/_dao_根治_无为.py` — **反**·根治·筛板坐标根因修正
- `00-本源_Origin/_dao_完善_万法.py` — **完**·传动七段装配 (v1)
- `00-本源_Origin/_dao_完善_补救.py` — **完**·STEP→SLDPRT 中转 + 直接装配体插入 (v2)
- `00-本源_Origin/_dao_清理_固定.py` — **定**·除幽灵+固37件
- `00-本源_Origin/_dao_诊断_位置.py` — 诊断工具 (读 bbox + origin)

#### 报告

- `_产物输出/根治_无为_报告.json` + `ROOT_CAUSE_FIX_REPORT_V4_道法自然_无为.md`
- `_产物输出/完善_万法_报告.json`
- `_产物输出/完善_补救_报告.json`
- `_产物输出/清理_固定_报告.json`
- `_产物输出/诊断_位置.json`
- 本文件 `COMPLETION_REPORT_V5_大制不割_万法归宗.md`

#### 渲染 (6 视图 1920×1080 BMP)

- `_产物输出/根治_{iso,front,back,top,right,left}.bmp`
- `_产物输出/完善_{iso,...}.bmp` + `完善2_{iso,...}.bmp`
- `_产物输出/清理_{iso,...}.bmp` ← **最终版本**
- JPG 预览: `_诊断_爆炸图_修复后/清理_*.jpg`

---

### 六、传动链目视印证

- **Front 视图**: 左侧黑色电机 + 主动带轮 + 绿色从动带轮 → 主轴贯通 → 右侧螺纹端; 中间 4×4 锤头矩阵
- **Top 视图**: V 带作为弯曲黑线从主动轮延伸到从动轮清晰可见; 电机体置于机壳左方 · motor_mount 为底基
- **ISO 视图**: 机壳半透明 · 内含转子链 · 左后方电机传动组件完整
- **Left 视图**: 主轴轴心 (Y=0,Z=0) 位圆心 · 筛板弧面包住下半 120° · 电机偏置于机壳旁

---

### 七、道之所在

> **为学日益, 为道日损. 损之又损, 以至于无为. 无为而无不为.**

此次三部曲应合道:

1. **反** (损) — 去除偏离的 screen_plate tz=-15 + 故障辅助模块 → 归零基准
2. **完** (益) — 按规范 (GB) 与资源 (STEP) 有序复建传动 → 功能齐备
3. **定** (静) — 除幽灵 + 锁全局 → 稳定不动

> **图难于其易, 为大于其细.**
> 7 段活体脚本, 数十次 COM bug 迭代修复, 每一个细节都经得起 bbox 数据验证.

> **大道氾兮, 其可左右. 以其终不自为大, 故能成其大.**
> 不强求一次完美 · 通过三脚本接力 · 最终 37 组件完整且全固定.

**完善毕 · 大制不割 · 万法归宗.**
