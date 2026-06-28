# 闭环冷启动 (CLOSED_LOOP) · 三道门一条命令跑通

本文件是**冷启动**指南:在一台干净机器上,只装轻量依赖(无需 OCCT/CAD 内核),即可复现
本仓库三条客观闭环证据。CI (`.github/workflows/ci.yml`) 跑的就是这三道门。

```bash
pip install -r requirements-ci.txt      # numpy scipy matplotlib pytest
```

## Gate 1 · 通用八维装配审核器 (numpy-only)

逆向"人如何判断一个 3D 装配是否成立",提炼为 8 个正交维度(拓扑/几何/工艺/装配/尺寸链/
强度/载荷分布/刚度),对解析装配描述客观打分。

```bash
python "80-实践_Practice/verifier.py"
pytest "80-实践_Practice/tests/test_verifier.py" -v
```

## Gate 2 · 自愈闭环 (build → audit → heal → 收敛)

给参数化装配 + 审核器,对每个违反维度施加单调修复策略,反复 audit 直到 8 维全过。
从蓄意三重违规出发,score 严格单调收敛 `[0.769, 0.95, 0.988, 1.0]`。

```bash
python "80-实践_Practice/self_heal.py"
pytest "80-实践_Practice/tests/test_self_heal.py" -v
```

## Gate 3 · SR6 真·3D 并联机构闭环 (residual ≈ 0)

从测量真值建刚性约束并联机构:逐腿解析 IK(杆长恒为 175mm)+ 数值 6-DOF FK(LM 反解位姿)。
闭环残差到机器精度 (~1e-13 mm / deg)。

```bash
pytest "60-实战_Projects/ORS6_Stewart/closed_loop/tests/test_closure.py" -v
python "60-实战_Projects/ORS6_Stewart/closed_loop/closure_report.py"   # 出 json + 图
```

详见各包内 `README.md`。

---

> 反者道之动:旧 SR6 模型把"杆长算出多少就是多少"当成闭环,实为视觉错觉。本次回到
> **测量真值 + 刚性约束**,闭环按构造成立。无为而无不为。
