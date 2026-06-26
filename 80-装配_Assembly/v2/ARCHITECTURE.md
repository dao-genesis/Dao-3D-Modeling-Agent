# OSR6 通用特征装配架构 (v2)

从零重建。核心信念:**朝向与勾接必须由真实网格几何自动解出**,而不是把零件当抽象棍子逐个手摆。
旧架构把约束残差优化到 1e-14 却"完全不合运动学",根因即在此:它从未对真实网格特征(轴承孔、销轴、贴合面)做配合。

## 三层内核(通用,与具体机器无关)

1. **特征提取 `cylinders.py`**
   从任意 STL 的真实网格里提取圆柱特征(轴承孔/凸台):聚类非平面三角面 → PCA 求轴线 → 圆拟合求半径/圆心 →
   按法向朝内/朝外判定 `hole`/`boss`。输出 `Cylinder(center, axis, radius, half_len, kind)`。
   已在全部 12 个 STL 上验证(Arm 2、MainLink 4、Receiver 6、Frame 3…)。

2. **SE(3) 配合内核 `mate.py`**
   `place_coaxial(local_pt, local_axis, world_pt, world_axis, spin)`:把零件的局部特征轴/点
   贴合到世界特征轴/点上,残留 1 个绕轴自转自由度(=真实关节自由度)。这是"孔↔轴共轴"配合的最小原语,
   对任何零件/机器通用。

3. **实体渲染 `render.py`**
   画家算法 + 法向平面着色的无头多视图渲染;零件读作实体而非线框,可与真机照片同角度叠加验证。

## 装配树(SR6,authority = 真实网格 + 固件 IK)

- **固定机架(共享坐标系,identity)**:Base / Lid / LFrame / RFrame —— 实测发现这几件 STL **本就在同一装配坐标系**,
  identity 直接拼上即真机机体(`v2_body_vs_ref.png` 与 Ayva 参考同形:蓝侧框竖直、套筒架居中、紧凑实体)。
- **6 个伺服**:L/RFrame 上实测出 6 个 r≈19.4 轴承孔 = 固件里的 6 个伺服
  (LowerLeft / UpperLeft / LowerRight / UpperRight 主臂 + Left / Right 俯仰),与固件 `SR6 Kinematics` 段一一对应。
- **6 个曲柄臂**:每个 Arm 的伺服孔(局部 Z@(68,0,54))共轴配合到真实轴承轴线,曲柄自转设为朝接收器伸展。
  全部由真实特征确定,无手填(`v2_arms_vs_ref.png`)。

## 关键运动学发现(rod/receiver 闭合层)

固件 IK(`SetMainServo`/`SetPitchServo`)解码:
- 主臂:arm=50mm, rod=175mm;home 时接收器主销在伺服平面 (x=162.48, y=15) mm,即**距伺服轴 162.48mm**。
- 俯仰:arm=75mm, rod=175mm, 偏置 55mm@15°;home (x=162.48, y=45, z=±side)。

**但**:固件这些绝对常数**与本组 STL 的坐标系/尺度不吻合**——
- 实测主销长杆 STL 端孔跨距 ≈180mm,俯仰杆 ≈190mm。
- 实测伺服轴到接收器最近真实销孔(俯仰耳 ±61,−14.2,53.1)仅 32–76mm;到对侧 ≈150–165mm。
- 固件 home 反推的 6 个销点落在机体外 ±130mm 处(`v2_pivots.png`),与真实网格不重合。

结论:**固件是控制坐标系(针对某次实体标定),其绝对常数不能直接套到这组网格上**。
静态装配的销点必须取自**真实网格特征**。本组 Receiver STL 只干净暴露 2/6 个杆销(两个俯仰耳)+ 1 个中心长孔,
4 个主臂销孔未在网格中清晰建模 —— 这是闭合最后一层(6 杆落到接收器)的**数据边界**。

## 复用性(这才是本阶段的本源目标)

`cylinders.py` + `mate.py` + `render.py` 不含任何 SR6 专有量,是"特征→配合→位姿"的通用内核:
任何零件、任何机器,只要 STL 有圆柱/平面配合特征,同一套代码即可提特征、定配合、解 SE(3) 位姿、渲染验证。
SR6 只是第一台验证机。

## 文件
- `cylinders.py` 特征提取  ·  `mate.py` SE(3) 配合内核  ·  `render.py` 实体渲染
- `assemble.py` / `hero.py` 机体基准  ·  `place_arms.py` / `arms_hero.py` 伺服臂
- `inspect_receiver.py` / `probe_pivots.py` 接收器销点勘察(运动学发现)
- 产物:`results/v2_body*.png`, `v2_arms*.png`, `v2_pivots.png`, `v2_receiver_feats.png`
