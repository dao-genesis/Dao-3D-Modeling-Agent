# 80-实践_Practice · 通用闭环工具 (cold-start, numpy-only)

00-本源_Origin 的核心引擎(直连 OCCT)的**可冷启动提炼版**:在任意干净环境
`pip install numpy scipy` 即可自证,无需 CAD 内核。供任何装配做"建模是否成立"的
客观闭环判定,并被 CI 当作冒烟门。

| 文件 | 作用 |
|------|------|
| `verifier.py` | 八维装配审核器:topology / geometry / manufacture / assembly / stackup / strength / load_dist / stiffness。每维返回 `(status, score, detail)`。 |
| `self_heal.py` | 自愈闭环:给定参数化装配 + 审核器,对每个违反维度施加单调修复策略,反复 audit 直到 8 维全过;记录 score 收敛轨迹。 |

## 跑

```bash
python verifier.py        # 打印一个健全装配的 8 维报告 (全 PASS, score 1.000)
python self_heal.py       # 从蓄意三重违规出发, 收敛: [0.769, 0.95, 0.988, 1.0]
pytest tests/ -q          # 8 个冒烟测试
```

## 八维 (对应内核 Layer 0–7)

1. **topology** 拓扑闭合 (watertight)
2. **geometry** 体积>0、质心落在包围盒内
3. **manufacture** 最小壁厚 ≥ 工艺下限
4. **assembly** 两两零件 AABB 干涉 ≤ 许用间隙
5. **stackup** 公差累积 (最坏 + RSS) ≤ 配合间隙
6. **strength** 应力 F/A ≤ 屈服/安全系数
7. **load_dist** 多路径分担,无单路径过载
8. **stiffness** 轴向挠度 FL/AE ≤ 许用
