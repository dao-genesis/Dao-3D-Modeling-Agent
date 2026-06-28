# ORS6 / SR6 · 真·3D 并联机构闭环 (closed_loop)

把 SR6 (6-DOF 并联舵机机器人) 从**测量真值**出发建成一个**刚性约束**的 3D 并联机构,
并严格证明正/逆运动学闭环。这是对旧模型的根因纠偏。

## 旧模型为何是假闭环

旧 viewer (`viewer/index.html:783–824`) 把**臂尖**和**接收器铰点各自独立算出**,再在两点
间画一根杆——杆长"算出多少就多少",**从未施加 175mm 刚性约束**。叠加 4 处硬编码铰点错误
(见 `../HALLUCINATION_MAP.md`),自然与 PDF/真件对不上。"闭环"只是视觉错觉。

## 本模型 (true_kinematics.py)

测量真值: 主臂 horn→ball 50mm、俯仰臂 75mm、刚性杆 **175mm**、接收器主销 (±59.98,0,0)∥X、
俯仰销 (±61,−14.235,53.126)∥X、舵机轴平面 Z=46 (= servoPivotH,与固件 baseH=162.48 自洽)。

- **逐腿解析 IK** (`Leg.ik`):解臂角使 |臂尖 − 接收器铰点| **恒等于 175mm**(化为臂平面内
  圆-点距离方程,取两根中靠近上一解者)。
- **数值 6-DOF FK** (`fk`):给定 6 个臂角,以 6 根杆长残差作最小二乘 (Levenberg–Marquardt)
  反解接收器六自由度位姿。
- **闭环** = 位姿 → IK(6θ) → FK(6θ) → 位姿′,残差到机器精度,且全程 6 根杆恒为 175mm。

## 跑

```bash
pip install numpy scipy            # (+ matplotlib 才出图)
pytest tests/test_closure.py -q    # 16 passed, 3 skipped (越界位姿)
python closure_report.py           # -> out/closure_report.json + closure_figure.png
```

## 实测闭环 (最新)

```
home 可装配: True       工作空间可达: 12/15 位姿
最差杆长误差 (IK 时)  : 2.842e-14 mm
最差闭环平移残差      : 8.317e-14 mm
最差闭环旋转残差      : 1.336e-13 deg
```

机器精度闭环——刚性 175mm 约束**按构造成立**,不再是旧模型的视觉错觉。
