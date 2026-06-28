#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""感·三维感知 · 自洽验证 (零外部平台 · 纯 numpy)

    見小曰明 · 以神遇而不以目視

跑法:
    python 30-验证_Verify/test_dao_perception.py

覆盖五能:
    渲(render) z-buffer 软光栅 → 简单几何掩膜/深度
    写(sketch) Marr 2.5D 初草图 → 轮廓/深度棱/折痕非空
    述(describe) 结构理解 → ORS6 连通件=20 · 五问俱全
    复(recover) 分析-综合反演 → 角度<2° 位移<5mm IoU>0.95
    校(compare) 同模型=0 · 异模型>0
    一(整合) 万法·道.感 facet 贯通
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import _paths  # noqa: F401  触发五层 sys.path 注入
import numpy as np
import dao_perception as dp

ORS6 = ROOT / "60-实战_Projects" / "ORS6_Stewart" / "output" / "ORS6_home.stl"
PITCH = ROOT / "60-实战_Projects" / "ORS6_Stewart" / "output" / "ORS6_pitch_up.stl"

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    mark = "PASS" if cond else "FAIL"
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
    print(f"  [{mark}] {name}" + (f"  · {detail}" if detail else ""))


def _unit_cube():
    """单位立方体 (8 顶点, 12 三角面)."""
    V = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=float) * 50.0
    F = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    return V, F


def test_render():
    print("渲 · z-buffer 软光栅")
    V, F = _unit_cube()
    cam = dp._auto_cam(V, "iso", 128)
    rr = dp.render(V, F, cam)
    px = int(rr.mask.sum())
    check("立方体掩膜非空", px > 200, f"mask px={px}")
    check("掩膜内深度有限", np.isfinite(rr.depth[rr.mask]).all())
    check("明暗图范围 [0,1]", float(rr.shaded.max()) <= 1.0 and float(rr.shaded.min()) >= 0.0)


def test_sketch():
    print("写 · Marr 2.5D 初草图")
    V, F = _unit_cube()
    rr = dp.render(V, F, dp._auto_cam(V, "iso", 160))
    sk = dp.sketch(rr)
    check("轮廓非空", int(sk["silhouette"].sum()) > 0)
    check("深度棱/折痕至少其一非空",
          int(sk["depth_edge"].sum()) + int(sk["crease"].sum()) > 0)


def test_weld():
    print("述 · weld 焊点 (STL 面独立顶点 → 真拓扑)")
    V, F = _unit_cube()
    # 复制每个面成独立顶点 (模拟 STL 非共享顶点)
    Vd = V[F].reshape(-1, 3)
    Fd = np.arange(len(Vd), dtype=np.int64).reshape(-1, 3)
    Vw, Fw = dp.weld(Vd, Fd)
    check("焊接后顶点数大幅下降", len(Vw) < len(Vd), f"{len(Vd)} → {len(Vw)}")
    check("焊接保面数", len(Fw) == len(Fd))


def test_describe():
    print("述 · 结构理解 (ORS6 五问)")
    if not ORS6.exists():
        check("ORS6 网格存在", False, str(ORS6))
        return
    V, F = dp.load_mesh(str(ORS6))
    d = dp.describe(V, F)
    fq = d["five_questions"]
    for q in ("拓扑", "最易失败操作", "关键尺寸约束", "手感(质心/对称)", "不能做(负空间)"):
        check(f"五问·{q} 已答", bool(fq.get(q)))
    check("连通件=20 (装配真件数)", d["n_components"] == 20, f"n_components={d['n_components']}")


def test_recover():
    print("复 · 分析-综合位姿反演 (藏一姿→多视轮廓→从头复原)")
    if not ORS6.exists():
        check("ORS6 网格存在", False, str(ORS6))
        return
    V, F = dp.load_mesh(str(ORS6))
    r = dp.recover_selftest(V, F)
    check("旋转误差 < 2°", r["rotation_error_deg"] < 2.0, f"{r['rotation_error_deg']}°")
    check("平移误差 < 5mm", r["translation_error_mm"] < 5.0, f"{r['translation_error_mm']}mm")
    check("收敛 IoU > 0.95", r["recovered_IoU"] > 0.95, f"IoU={r['recovered_IoU']}")


def test_compare():
    print("校 · 两模型差异 (抓错坐标/幻觉)")
    if not (ORS6.exists() and PITCH.exists()):
        check("ORS6 + pitch_up 网格存在", False)
        return
    Va, Fa = dp.load_mesh(str(ORS6))
    Vb, Fb = dp.load_mesh(str(PITCH))
    same = dp.compare(Va, Fa, Va, Fa, align=False)
    diff = dp.compare(Va, Fa, Vb, Fb, align=False)
    check("同模型 Hausdorff = 0", same["hausdorff"] == 0.0)
    check("异模型 Hausdorff > 0", diff["hausdorff"] > 1.0, f"{diff['hausdorff']}mm")
    check("异模型匹配率 < 1.0", diff["match_ratio@1%diag"] < 1.0,
          f"{diff['match_ratio@1%diag']}")


def test_facet():
    print("一 · 万法·道.感 贯通")
    try:
        from 万法 import 道
    except Exception as e:
        check("万法 可导入", False, str(e)[:80])
        return
    if not ORS6.exists():
        check("ORS6 网格存在", False)
        return
    r = 道.感.述(str(ORS6))
    check("道.感.述 → ok", bool(r.ok))
    r2 = 道.感.校(str(ORS6), str(ORS6), align=False)
    check("道.感.校 同模型 → ok·Hausdorff=0",
          bool(r2.ok) and r2.data["hausdorff"] == 0.0)


def main() -> int:
    print("=" * 64)
    print("感 · 三维感知自洽验证 · 道法自然 · 不依赖任何外部平台")
    print("=" * 64)
    for fn in (test_render, test_sketch, test_weld, test_describe,
               test_recover, test_compare, test_facet):
        fn()
        print()
    print("=" * 64)
    print(f"结果: PASS={_PASS}  FAIL={_FAIL}")
    print("=" * 64)
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
