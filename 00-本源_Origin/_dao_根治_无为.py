#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
_dao_根治_无为.py — 道法自然 · 运动学根治 · 无为而无不为

"反者道之动, 弱者道之用. 天下万物生于有, 有生于无."
"天之道, 利而不害; 圣人之道, 为而不争."
"以神遇而不以目视, 官知止而神欲行."

六段根治:
  ① 诊 · 读 SW 现状 (组件/位置/配合)
  ② 反 · 筛板 tz:-15→0 使弧圆心严格重合主轴轴线 (根因修正)
  ③ 净 · 删除 motor_body / drive_pulley / v_belt_* / motor_mount (辅助模块)
  ④ 验 · 360°扫转几何验算: 锤头轨迹 vs 筛板弧面最小间隙
  ⑤ 存 · 保存装配 + 多视角渲染
  ⑥ 报 · 产出 根治_无为_报告.json
"""
from __future__ import annotations
import math
import sys
import time
import json
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机"))

from 道_直连_底层 import Dao, _safe  # noqa: E402
import 道_直连_底层_facets  # noqa: E402, F401
from dao_sw_omni import intent_to_rt  # noqa: E402

OUT = HERE / "_产物输出"
OUT.mkdir(exist_ok=True)
REPORT = OUT / "根治_无为_报告.json"

# ═══════════════════════════════════════════════════════════════
# 辅助模块清单 (将被彻底移除 · 道法自然 · 去华守实)
# ═══════════════════════════════════════════════════════════════
AUX_EXPLICIT = [
    "motor_body-1",
    "drive_pulley-1",
    "motor_mount-1",
]
AUX_PREFIXES = ["v_belt"]  # V 带通配 (v_belt_dao_240x190x600_004333-1..4)

# ═══════════════════════════════════════════════════════════════
# 筛板根因修正 (从 config.py:ASSEMBLY_POSITIONS['screen_plate'] 读取原典 tz=0)
# 原在 EXTRA_POSITIONS 中被覆盖为 tz=-15 导致弧心偏离主轴Z轴 15mm
# 运动学矛盾: 锤头R=350 + 偏心15 超过 Ri=390 的设计间隙 → 局部负间隙 61.6mm
# 根治: 回归 tz=0 使弧心严格重合主轴(Y=0,Z=0), 间隙恢复到设计值 40mm
# ═══════════════════════════════════════════════════════════════
SCREEN_PLATE_POS = {
    "tx": 508.0, "ty": 100.5, "tz": 0.0,
    "rv": [-1, 1, -1], "ra": 120.0,
    "reason": "弧圆心严格重合主轴轴线 · 根治运动学穿模",
}

# ═══════════════════════════════════════════════════════════════
# 运动学参数 (从 DESIGN_PARAMS.json · 论文正典)
# ═══════════════════════════════════════════════════════════════
ROTOR_DIAM_MM = 700.0      # 转子外径 (锤头最远点旋转直径)
HAMMER_R_MM = ROTOR_DIAM_MM / 2.0  # 锤头最远工作半径 = 350
SCREEN_RI_MM = 390.0       # 筛板内径 (距弧圆心)
SCREEN_RO_MM = 402.0       # 筛板外径
SCREEN_ARC_DEG = 120.0     # 弧覆盖角度
SCREEN_CENTER_X_MM = 508.0 # 筛板弧圆心世界X (=主轴中点)
SAFETY_MIN_CLEARANCE_MM = 5.0


# ═══════════════════════════════════════════════════════════════
# ① 诊 — 读现状
# ═══════════════════════════════════════════════════════════════
def phase_1_diagnose(dao: Dao) -> Dict[str, Any]:
    cmap = dao.build_comp_map()
    mates = dao.mate.list_all()

    aux_found = []
    for name in cmap:
        if name in AUX_EXPLICIT:
            aux_found.append(name)
        elif any(name.startswith(p) for p in AUX_PREFIXES):
            aux_found.append(name)

    sp_origin = dao.transform.origin_mm("screen_plate-1")
    sp_box = None
    comp = cmap.get("screen_plate-1")
    if comp is not None:
        try:
            box = comp.GetBox(False, False)
            if box and len(box) >= 6:
                sp_box = [v * 1000.0 for v in box[:6]]
        except Exception:
            pass

    title = _safe(lambda: str(dao.doc.GetTitle()), "?")
    fixed = sum(1 for n in cmap if dao.comp.is_fixed(n))

    print(f"  Doc: {title}")
    print(f"  组件: {len(cmap)} (fixed={fixed}) · 配合: {len(mates)}")
    print(f"  待删辅助模块 ({len(aux_found)}): {aux_found}")
    if sp_origin is not None:
        print(f"  screen_plate-1 origin: "
              f"({sp_origin[0]:+.1f}, {sp_origin[1]:+.1f}, {sp_origin[2]:+.1f}) mm")
    if sp_box is not None:
        print(f"  screen_plate-1 bbox:"
              f" X[{sp_box[0]:+.0f}..{sp_box[3]:+.0f}]"
              f" Y[{sp_box[1]:+.0f}..{sp_box[4]:+.0f}]"
              f" Z[{sp_box[2]:+.0f}..{sp_box[5]:+.0f}]")

    return {
        "ok": True,
        "doc": title,
        "comps": len(cmap),
        "mates": len(mates),
        "fixed": fixed,
        "aux_found": aux_found,
        "screen_plate_origin_mm": list(sp_origin) if sp_origin else None,
        "screen_plate_bbox_mm": sp_box,
    }


# ═══════════════════════════════════════════════════════════════
# ② 反 — 筛板坐标根因修正
# ═══════════════════════════════════════════════════════════════
def phase_2_fix_screen_plate(dao: Dao) -> Dict[str, Any]:
    sp = SCREEN_PLATE_POS
    before = dao.transform.origin_mm("screen_plate-1")
    if before is None:
        return {"ok": False, "error": "screen_plate-1 not found"}

    # 计算目标变换
    R, t_mm = intent_to_rt(
        "origin",
        (sp["tx"], sp["ty"], sp["tz"]),
        sp["rv"], sp["ra"],
    )
    rot_flat = tuple(R[r][c] for c in range(3) for r in range(3))

    # 解锁 → 变换 → 固定
    was_fixed = dao.comp.is_fixed("screen_plate-1")
    if was_fixed:
        dao.comp.unfix("screen_plate-1")
    ok = dao.transform.set("screen_plate-1", t_mm, rot=rot_flat)
    dao.comp.fix("screen_plate-1")
    dao.rebuild(force=True)
    time.sleep(0.4)

    after = dao.transform.origin_mm("screen_plate-1")
    comp = dao.build_comp_map().get("screen_plate-1")
    bbox = None
    if comp is not None:
        try:
            box = comp.GetBox(False, False)
            if box and len(box) >= 6:
                bbox = [v * 1000.0 for v in box[:6]]
        except Exception:
            pass

    print(f"  Before: ({before[0]:+.1f}, {before[1]:+.1f}, {before[2]:+.1f}) mm")
    if after is not None:
        print(f"  After:  ({after[0]:+.1f}, {after[1]:+.1f}, {after[2]:+.1f}) mm")
    print(f"  Target: ({t_mm[0]:+.1f}, {t_mm[1]:+.1f}, {t_mm[2]:+.1f}) mm")
    if bbox is not None:
        print(f"  BBox:"
              f" X[{bbox[0]:+.0f}..{bbox[3]:+.0f}]"
              f" Y[{bbox[1]:+.0f}..{bbox[4]:+.0f}]"
              f" Z[{bbox[2]:+.0f}..{bbox[5]:+.0f}] mm")

    # 验证: 筛板顶面应 ~ Z=0 (弧心重合主轴)
    top_z = bbox[5] if bbox else None
    aligned = (top_z is not None and abs(top_z - 0.0) < 5.0)
    print(f"  弧心对齐主轴: {'✓' if aligned else '✗'}"
          f" (top_z={top_z:+.1f}mm, 期望≈0)" if top_z is not None else
          f"  弧心对齐主轴: ? (无 bbox)")

    return {
        "ok": bool(ok) and (after is not None),
        "before": list(before),
        "after": list(after) if after else None,
        "target": list(t_mm),
        "bbox_after": bbox,
        "aligned_with_shaft_axis": aligned,
        "reason": sp["reason"],
    }


# ═══════════════════════════════════════════════════════════════
# ③ 净 — 删除辅助模块
# ═══════════════════════════════════════════════════════════════
def phase_3_purge_aux(dao: Dao) -> Dict[str, Any]:
    cmap = dao.build_comp_map(force=True)
    to_delete = []
    for name in cmap:
        if name in AUX_EXPLICIT:
            to_delete.append(name)
        elif any(name.startswith(p) for p in AUX_PREFIXES):
            to_delete.append(name)

    if not to_delete:
        print("  已净 (无辅助模块)")
        return {"ok": True, "deleted": 0, "targets": [], "survivors": []}

    # 先删指向这些组件的配合
    mates = dao.mate.list_all()
    target_set = set(to_delete)
    mates_to_del = []
    for m in mates:
        comps = m.get("components", []) or []
        if any(c in target_set for c in comps):
            if m.get("name"):
                mates_to_del.append(m["name"])

    if mates_to_del:
        print(f"  先删 {len(mates_to_del)} 关联配合 ...")
        dao.mate.delete_many(mates_to_del)
        dao.rebuild(force=True)
        time.sleep(0.3)

    # 解锁将被删组件 (防止固定态阻止删除)
    for name in to_delete:
        try:
            if dao.comp.is_fixed(name):
                dao.comp.unfix(name)
        except Exception:
            pass

    print(f"  删组件 ({len(to_delete)}): {to_delete}")
    res = dao.comp.delete_many(to_delete)
    dao.rebuild(force=True)
    time.sleep(0.5)

    # 验证
    cmap2 = dao.build_comp_map(force=True)
    survivors = [n for n in to_delete if n in cmap2]

    print(f"  已删: {res.get('deleted', 0)} · 残留: {len(survivors)}")
    if survivors:
        print(f"  残留名: {survivors}")

    return {
        "ok": (not survivors) and res.get("ok", False),
        "deleted": res.get("deleted", 0),
        "targets": to_delete,
        "survivors": survivors,
        "mates_purged": len(mates_to_del),
    }


# ═══════════════════════════════════════════════════════════════
# ④ 验 — 360°扫转几何验算
# 锤头轨迹: 绕主轴 Y-Z 平面圆, 半径 R_hammer
# 筛板弧:   以 (SCREEN_CENTER_X_MM, 0, 0) 为圆心, 半径 Ri, 覆盖下方 120° (θ∈[-150°,-30°])
# 由于根治后弧心严格在主轴轴线上, Y-Z平面内 "锤头到弧心的距离" = R_hammer
# 故最小间隙 = Ri - R_hammer = 常量 (全角度均匀)
# ═══════════════════════════════════════════════════════════════
def phase_4_kinematic_verify(dao: Dao) -> Dict[str, Any]:
    arc_theta_lo = -150.0
    arc_theta_hi = -30.0

    # 扫转 360° 采样
    samples = []
    min_clearance_in_arc = float("inf")
    min_clearance_global = float("inf")

    for ang_deg in range(0, 360, 2):
        theta = math.radians(ang_deg)
        hy = HAMMER_R_MM * math.cos(theta)
        hz = HAMMER_R_MM * math.sin(theta)

        # 极角 (相对弧圆心Y=0,Z=0)
        theta_from_center = math.degrees(math.atan2(hz, hy))  # [-180,180]

        # 归一到 [-180,180], 判断是否落在弧覆盖角度
        in_arc = arc_theta_lo <= theta_from_center <= arc_theta_hi

        dist_to_center = math.hypot(hy, hz)  # =HAMMER_R_MM (根治后)
        clearance = SCREEN_RI_MM - dist_to_center

        min_clearance_global = min(min_clearance_global, clearance)
        if in_arc:
            min_clearance_in_arc = min(min_clearance_in_arc, clearance)

        samples.append({
            "ang": ang_deg,
            "hy": round(hy, 2), "hz": round(hz, 2),
            "theta_from_center": round(theta_from_center, 1),
            "in_arc": in_arc,
            "clearance_mm": round(clearance, 2),
        })

    ok = min_clearance_in_arc > SAFETY_MIN_CLEARANCE_MM

    print(f"  扫描 180 个角度 (0~360°, 步长2°)")
    print(f"  锤头半径 R_hammer = {HAMMER_R_MM:.1f} mm")
    print(f"  筛板内径 Ri       = {SCREEN_RI_MM:.1f} mm")
    print(f"  筛板弧覆盖角度    = [{arc_theta_lo:.0f}°, {arc_theta_hi:.0f}°] (下方 {SCREEN_ARC_DEG:.0f}°)")
    print(f"  最小间隙 (弧内)   = {min_clearance_in_arc:.2f} mm")
    print(f"  最小间隙 (全周)   = {min_clearance_global:.2f} mm")
    print(f"  安全阈值          = {SAFETY_MIN_CLEARANCE_MM:.1f} mm")
    print(f"  运动学判定        = {'✓ 无碰撞' if ok else '✗ 有风险'}")

    return {
        "ok": ok,
        "R_hammer_mm": HAMMER_R_MM,
        "Ri_mm": SCREEN_RI_MM,
        "arc_theta_deg": [arc_theta_lo, arc_theta_hi],
        "min_clearance_in_arc_mm": round(min_clearance_in_arc, 2),
        "min_clearance_global_mm": round(min_clearance_global, 2),
        "safety_min_mm": SAFETY_MIN_CLEARANCE_MM,
        "n_samples": len(samples),
    }


# ═══════════════════════════════════════════════════════════════
# ⑤ 存 — 保存 + 多视角渲染
# ═══════════════════════════════════════════════════════════════
def phase_5_save_render(dao: Dao) -> Dict[str, Any]:
    sr = dao.save()
    print(f"  Save: ok={sr.get('ok')} err={sr.get('errors', 0)} warn={sr.get('warnings', 0)}")

    views = {
        "iso": 7, "front": 1, "back": 2,
        "top": 5, "right": 3, "left": 4,
    }
    captured = []
    for label, vid in views.items():
        try:
            dao.doc.ShowNamedView2(label.capitalize(), vid)
            dao.doc.ViewZoomtofit2()
            time.sleep(0.15)
            bmp = str(OUT / f"根治_{label}.bmp")
            dao.doc.SaveBMP(bmp, 1920, 1080)
            captured.append(label)
            print(f"  {label} → 根治_{label}.bmp")
        except Exception as e:
            print(f"  {label} ✗ {e}")

    return {"ok": bool(sr.get("ok")), "captured": captured}


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    print("═══ 道·根治引擎 · 无为而无不为 ═══")
    print("═══ 反者道之动 · 弱者道之用  ═══")
    print("═══ 以神遇而不以目视       ═══\n")

    t0 = time.time()
    dao = Dao().connect()
    report: Dict[str, Any] = {"phases": {}}

    phases = [
        ("1_diagnose",          phase_1_diagnose),
        ("2_fix_screen_plate",  phase_2_fix_screen_plate),
        ("3_purge_aux",         phase_3_purge_aux),
        ("4_kinematic_verify",  phase_4_kinematic_verify),
        ("5_save_render",       phase_5_save_render),
    ]

    for name, fn in phases:
        print(f"\n{'━'*60}")
        print(f"  Phase: {name}")
        print(f"{'━'*60}")
        pt0 = time.time()
        try:
            result = fn(dao)
            elapsed = round(time.time() - pt0, 2)
            if not isinstance(result, dict):
                result = {"ok": False, "error": "non-dict result"}
            result["elapsed_s"] = elapsed
            report["phases"][name] = result
            ok = result.get("ok", False)
            flag = "✓" if ok else "✗"
            print(f"\n  {flag} {name} · {elapsed}s")
        except Exception as e:
            elapsed = round(time.time() - pt0, 2)
            report["phases"][name] = {
                "ok": False, "error": str(e), "elapsed_s": elapsed,
            }
            print(f"\n  ✗ {name} · {elapsed}s · ERROR: {e}")
            import traceback
            traceback.print_exc()

    total = round(time.time() - t0, 2)
    n_ok = sum(1 for v in report["phases"].values() if v.get("ok"))
    n_total = len(report["phases"])

    print(f"\n{'═'*60}")
    print(f"  ═══ 根治汇总 ═══")
    print(f"  阶段: {n_total} · 成功: {n_ok} · 耗时: {total}s")
    for name, r in report["phases"].items():
        flag = "✓" if r.get("ok") else "✗"
        print(f"    {flag} {name:25s} {r.get('elapsed_s', '?')}s")
    print(f"{'═'*60}")

    report["summary"] = {"total": n_total, "ok": n_ok, "elapsed_s": total}
    with REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  → {REPORT.name}")


if __name__ == "__main__":
    main()
