#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
_dao_hybrid_e2e.py — 道并行而不相悖 · 坐标+意图 双轨引擎

"万物并育而不相害, 道并行而不相悖."
"天之道, 利而不害. 圣人之道, 为而不争."

三段:
  ① 清道 · 删除全部累积配合 + 解除非锚固定
  ② 定位 · 按 config.py 正典坐标 transform.set 全部组件
  ③ 配合 · 在正确位置上施加几何约束 (意图引擎)
  ④ 验证 · 位置精度 + 配合正确性 双重校验
"""
from __future__ import annotations
import math, sys, time, json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机"))

from 道_直连_底层 import Dao, _safe
import 道_直连_底层_facets  # noqa
from 道_意图_引擎 import (
    DaoIntentEngine, MateIntent, R, GeoSpec,
    coaxial, coincident, anchor, MATE, ALIGN
)
from config import ASSEMBLY_POSITIONS
from dao_sw_omni import intent_to_rt

OUT = HERE / "_产物输出"
OUT.mkdir(exist_ok=True)


# ════════════════════════════════════════════════════════════════
# Component → Config mapping
# ════════════════════════════════════════════════════════════════
# SW instance names → config.py keys
# The assembly has: main_shaft-1, rotor_disc-1..4, hammer_pin-1..4, etc.
COMP_CONFIG_MAP = {
    "main_shaft-1":    "main_shaft",
    "driven_pulley-1": "driven_pulley",
    "rotor_disc-1":    "rotor_disc_1",
    "rotor_disc-2":    "rotor_disc_2",
    "rotor_disc-3":    "rotor_disc_3",
    "rotor_disc-4":    "rotor_disc_4",
    "hammer_pin-1":    "hammer_pin_T",
    "hammer_pin-2":    "hammer_pin_B",
    "hammer_pin-3":    "hammer_pin_F",
    "hammer_pin-4":    "hammer_pin_K",
    # 根治·无为 (v2): 筛板回归 config.py 正典坐标 tz=0 (弧心对齐主轴)
    "screen_plate-1":  "screen_plate",
    # 辅助模块已移除 (根治·无为): motor_body-1, drive_pulley-1, motor_mount-1, v_belt_*
    # 若重新装配需补之, 直接从 config.py:ASSEMBLY_POSITIONS 读取
    "casing_lower-1":  "casing_lower",
    "casing_upper-1":  "casing_upper",
    "frame_base-1":    "frame_base",
}

# 16 hammers: 4 discs × 4 PCD directions
# hammer-1..4 = disc1 TBFK, hammer-5..8 = disc2 TBFK, etc.
X_DISCS = [207, 408, 610, 810]
PCD_RADIUS = 220
PCD_DIRS = [
    ("T", +1,  0,    0,   0, -20),
    ("F",  0, +1,  +90, +20,   0),
    ("B", -1,  0, +180,   0, +20),
    ("K",  0, -1,  -90, -20,   0),
]

def _build_hammer_positions() -> Dict[str, Dict[str, Any]]:
    """Build position dict for 16 hammers → hammer-1 .. hammer-16."""
    positions = {}
    hidx = 1
    for disc_i, dx in enumerate(X_DISCS):
        for tag, dy_u, dz_u, rot_deg, y_off, z_off in PCD_DIRS:
            tx = float(dx)
            ty = float(dy_u * PCD_RADIUS + y_off)
            tz = float(dz_u * PCD_RADIUS + z_off)
            rv = [1, 0, 0] if rot_deg != 0 else None
            ra = float(rot_deg)
            positions[f"hammer-{hidx}"] = {
                "tx": tx, "ty": ty, "tz": tz,
                "rv": rv, "ra": ra,
            }
            hidx += 1
    return positions

HAMMER_POSITIONS = _build_hammer_positions()

# ════════════════════════════════════════════════════════════════
# EXTRA_POSITIONS · 根治·无为 v2 (2026-04-22)
# ════════════════════════════════════════════════════════════════
# 曾用 screen_plate tz=-15 规避 casing 分界线"视觉穿模", 但导致:
#   · 弧圆心从主轴轴线 Z=0 偏移 15mm → 锤头 R=350 与筛板 Ri=390 间隙失守
#   · 运动学矛盾: 主轴旋转时锤头必然碰撞筛板下半弧面
# 根治: 回归 config.py 正典 tz=0, 令弧心严格重合主轴轴线.
# 筛板 Z 顶面=0 与 casing 分界线齐平乃物理合理(筛板螺栓夹于分型面).
#
# motor_mount-1: 辅助模块, 已随 motor_body / drive_pulley / v_belts 一并移除.
# ════════════════════════════════════════════════════════════════
EXTRA_POSITIONS: Dict[str, Dict[str, Any]] = {}


# ════════════════════════════════════════════════════════════════
# Phase functions
# ════════════════════════════════════════════════════════════════
def phase_0_connect(dao: Dao) -> Dict[str, Any]:
    """连接诊断."""
    rev = _safe(lambda: str(dao.sw.RevisionNumber()), "?")
    title = _safe(lambda: str(dao.doc.GetTitle()), "?")
    path = _safe(lambda: str(dao.doc.GetPathName()), "?")
    is_asm = dao.asm is not None
    cmap = dao.build_comp_map()
    mates = dao.mate.list_all()
    fixed = sum(1 for n in cmap if dao.comp.is_fixed(n))
    ec_dist = dict(Counter(m.get("error_status", -1) for m in mates))
    print(f"  SW: {rev}")
    print(f"  Doc: {title}")
    print(f"  Components: {len(cmap)} (fixed={fixed})")
    print(f"  Mates: {len(mates)} ec={ec_dist}")
    return {"ok": is_asm, "comps": len(cmap), "mates": len(mates)}


def phase_1_clean(dao: Dao) -> Dict[str, Any]:
    """清道 · 删除全部配合, 解除全部固定. 循环直到清零."""
    # 1. Delete ALL mates — retry loop until none remain
    total_deleted = 0
    for attempt in range(5):
        mates = dao.mate.list_all()
        mate_names = [m["name"] for m in mates if m.get("name")]
        if not mate_names:
            break
        print(f"  [{attempt}] 删除 {len(mate_names)} 配合...")
        result = dao.mate.delete_many(mate_names)
        d = result.get("deleted", 0)
        total_deleted += d
        dao.rebuild(force=True)
        time.sleep(0.3)
        if d == 0:
            break
    print(f"  已删: {total_deleted}")

    # 2. Unfix all components
    cmap = dao.build_comp_map()
    unfixed = 0
    for name in cmap:
        if dao.comp.is_fixed(name):
            dao.comp.unfix(name)
            unfixed += 1
    print(f"  解除固定: {unfixed} 组件")

    # 3. Rebuild
    dao.rebuild(force=True)
    time.sleep(0.5)

    # Verify clean state
    mates_after = dao.mate.list_all()
    print(f"  清理后: mates={len(mates_after)}")
    return {"ok": True, "deleted": total_deleted, "unfixed": unfixed,
            "mates_after": len(mates_after)}


def phase_2_position(dao: Dao) -> Dict[str, Any]:
    """定位 · 按正典坐标放置全部组件."""
    cmap = dao.build_comp_map()
    results = []
    ok_count = 0
    skip_count = 0

    for comp_name in sorted(cmap.keys()):
        # Determine position
        pos = None
        source = None

        if comp_name in COMP_CONFIG_MAP:
            cfg_key = COMP_CONFIG_MAP[comp_name]
            if cfg_key in ASSEMBLY_POSITIONS:
                pos = ASSEMBLY_POSITIONS[cfg_key]
                source = f"config:{cfg_key}"
        elif comp_name in HAMMER_POSITIONS:
            pos = HAMMER_POSITIONS[comp_name]
            source = "hammer_calc"
        elif comp_name in EXTRA_POSITIONS:
            pos = EXTRA_POSITIONS[comp_name]
            source = "extra"
        elif comp_name.startswith("v_belt"):
            skip_count += 1
            continue  # V-belt: keep current position

        if pos is None:
            print(f"  ✗ {comp_name}: 无坐标映射")
            results.append({"comp": comp_name, "ok": False, "err": "no_mapping"})
            continue

        tx = float(pos["tx"])
        ty = float(pos["ty"])
        tz = float(pos["tz"])
        rv = pos.get("rv")
        ra = float(pos.get("ra") or 0)

        # Compute rotation matrix
        if rv and ra:
            R, t_mm = intent_to_rt("origin", (tx, ty, tz), rv, ra)
            rot_flat = [R[r][c] for c in range(3) for r in range(3)]  # col-major
        else:
            rot_flat = None
            t_mm = (tx, ty, tz)

        # Apply transform
        ok = dao.transform.set(comp_name, t_mm, rot=tuple(rot_flat) if rot_flat else None)

        if ok:
            ok_count += 1
        flag = "✓" if ok else "✗"
        print(f"  {flag} {comp_name:25s} → ({tx:8.1f},{ty:8.1f},{tz:8.1f}) [{source}]")
        results.append({"comp": comp_name, "ok": ok, "pos": t_mm, "source": source})

    # Rebuild after all positions set
    dao.rebuild(force=True)
    time.sleep(0.5)

    print(f"\n  定位: ok={ok_count} skip={skip_count} fail={len(results)-ok_count}")
    return {"ok": ok_count > 0, "positioned": ok_count, "skipped": skip_count,
            "results": results}


def phase_3_verify_positions(dao: Dao) -> Dict[str, Any]:
    """验证位置精度."""
    cmap = dao.build_comp_map()
    ok_count = 0
    fail_count = 0
    max_err = 0.0

    for comp_name in sorted(cmap.keys()):
        if comp_name.startswith("v_belt"):
            continue

        expected = None
        if comp_name in COMP_CONFIG_MAP:
            cfg_key = COMP_CONFIG_MAP[comp_name]
            if cfg_key in ASSEMBLY_POSITIONS:
                p = ASSEMBLY_POSITIONS[cfg_key]
                rv = p.get("rv")
                ra = float(p.get("ra") or 0)
                if rv and ra:
                    _, t = intent_to_rt("origin",
                                        (float(p["tx"]), float(p["ty"]), float(p["tz"])),
                                        rv, ra)
                    expected = t
                else:
                    expected = (float(p["tx"]), float(p["ty"]), float(p["tz"]))
        elif comp_name in HAMMER_POSITIONS:
            p = HAMMER_POSITIONS[comp_name]
            rv = p.get("rv")
            ra = float(p.get("ra") or 0)
            if rv and ra:
                _, t = intent_to_rt("origin",
                                    (float(p["tx"]), float(p["ty"]), float(p["tz"])),
                                    rv, ra)
                expected = t
            else:
                expected = (float(p["tx"]), float(p["ty"]), float(p["tz"]))
        elif comp_name in EXTRA_POSITIONS:
            p = EXTRA_POSITIONS[comp_name]
            expected = (float(p["tx"]), float(p["ty"]), float(p["tz"]))

        if expected is None:
            continue

        actual = dao.transform.origin_mm(comp_name)
        if actual is None:
            fail_count += 1
            continue

        dist = math.sqrt(sum((actual[i] - expected[i])**2 for i in range(3)))
        max_err = max(max_err, dist)
        if dist < 5.0:
            ok_count += 1
        else:
            fail_count += 1
            print(f"  ✗ {comp_name:25s} Δ={dist:.1f}mm "
                  f"actual=({actual[0]:.1f},{actual[1]:.1f},{actual[2]:.1f}) "
                  f"expected=({expected[0]:.1f},{expected[1]:.1f},{expected[2]:.1f})")

    print(f"  位置验证: ok={ok_count} fail={fail_count} max_err={max_err:.1f}mm")
    return {"ok": fail_count == 0, "ok_count": ok_count,
            "fail_count": fail_count, "max_err_mm": round(max_err, 1)}


def phase_4_fix_and_mate(dao: Dao) -> Dict[str, Any]:
    """固万物 + 选择性配合.

    道并行而不相悖:
    - 坐标为体: 全部组件先固定在正确位置
    - 意图为用: 仅对几何探测证实共轴的组件解锁并施加配合
    - 验证: 配合后位置偏移不超过阈值
    """
    cmap = dao.build_comp_map()

    # ① 固定全部
    for name in cmap:
        if not dao.comp.is_fixed(name):
            dao.comp.fix(name)
    dao.rebuild(force=True)
    time.sleep(0.3)
    print(f"  固定: {len(cmap)} 组件")

    # ② 选择性配合 — 仅对探测证实共轴的组件
    # 配合策略: 解锁 source → 加配合 → rebuild → 验位移 → 若偏移>阈值则回退
    mate_pairs = _build_verified_mate_pairs()

    # 已有配合去重索引 (frozenset of comp pair)
    existing_mates = dao.mate.list_all()
    existing_pairs = set()
    for m in existing_mates:
        cs = m.get("components", [])
        if len(cs) == 2:
            existing_pairs.add(frozenset(cs))
    ok_count = 0
    fail_count = 0
    skip_count = 0
    DRIFT_TOL_MM = 10.0  # 配合后位移容忍度

    for desc, src, tgt, r_src, r_tgt, through_tgt in mate_pairs:
        # 去重: 已有配合的对不再添加
        if frozenset([src, tgt]) in existing_pairs:
            ok_count += 1
            print(f"  = {desc:35s} 已有配合, 跳过")
            continue

        # 记录配合前位置
        pos_before = dao.transform.origin_mm(src)
        if pos_before is None:
            skip_count += 1
            continue

        # 查找圆柱面 (through_point 精选正确的孔)
        f_src = dao.face.find_cylinder(src, radius_mm=r_src)
        f_tgt = dao.face.find_cylinder(tgt, radius_mm=r_tgt,
                                       through_point_mm=through_tgt,
                                       tol_mm=5.0)
        if f_src is None or f_tgt is None:
            skip_count += 1
            print(f"  - {desc:35s} skip: no cyl (src={f_src is not None} tgt={f_tgt is not None})")
            continue

        # 添加同心配合 (concentric 内部自动 TempUnfix)
        mr = dao.mate.concentric(f_src, f_tgt, align=ALIGN.CLOSEST,
                                 unfix_comp=src)

        if not mr.get("ok"):
            fail_count += 1
            print(f"  ✗ {desc:35s} mate_error={mr.get('error','?')}")
            continue

        # Rebuild + 检查位移
        dao.rebuild(force=True)

        pos_after = dao.transform.origin_mm(src)
        if pos_after is None:
            ok_count += 1  # can't verify but mate ok
            print(f"  ? {desc:35s} mate_ok, pos unreadable")
            continue

        drift = math.sqrt(sum((pos_after[i] - pos_before[i])**2 for i in range(3)))

        if drift > DRIFT_TOL_MM:
            # 位移过大 · 删除配合 + 回退位置
            mate_name = mr.get("name")
            if mate_name:
                dao.mate.delete_many([mate_name])
            dao.transform.set(src, pos_before)
            dao.comp.fix(src)
            dao.rebuild(force=True)
            fail_count += 1
            print(f"  ✗ {desc:35s} drift={drift:.1f}mm > {DRIFT_TOL_MM}mm → 回退")
        else:
            ok_count += 1
            existing_pairs.add(frozenset([src, tgt]))
            print(f"  ✓ {desc:35s} drift={drift:.1f}mm ✓")

    # 最终 rebuild
    dao.rebuild(force=True)
    time.sleep(0.3)

    print(f"\n  配合: ok={ok_count} fail={fail_count} skip={skip_count}")
    return {"ok": True, "mated": ok_count, "failed": fail_count, "skipped": skip_count}


def _build_verified_mate_pairs():
    """构建经几何探测验证的配合对.

    以神遇而不以目视 — 仅包含几何探测证实共轴的对:
    - main_shaft ↔ driven_pulley (0mm, 同轴)
    - main_shaft ↔ rotor_disc-1..4 (0mm, 盘中心孔套轴)
    - rotor_disc ↔ hammer_pin (0mm, 盘PCD孔套销轴 · 需through_point精选)

    排除:
    - hammer ↔ hammer_pin: 锤头圆柱轴(0,0,-1)⊥销轴(-1,0,0), 不可共轴
    - casing/frame/motor: 无共轴几何关系

    返回: [(desc, src, tgt, r_src, r_tgt, through_tgt)]
    """
    pairs = []

    # main_shaft ↔ driven_pulley (同轴 r=30↔r=35)
    pairs.append(("main_shaft↔driven_pulley",
                  "driven_pulley-1", "main_shaft-1",
                  35, 30, None))

    # main_shaft ↔ rotor_disc (同轴 r=40盘中心孔↔r=30轴段)
    for i in range(1, 5):
        pairs.append((f"main_shaft↔rotor_disc-{i}",
                      f"rotor_disc-{i}", "main_shaft-1",
                      40, 30, None))

    # rotor_disc ↔ hammer_pin (盘PCD孔r=20 ↔ 销轴r=15)
    # 关键: 用through_point精选正确的PCD孔
    # pin-1=T(Y=+220), pin-2=B(Y=-220), pin-3=F(Z=+220), pin-4=K(Z=-220)
    _PIN_PCD = {
        1: (194.5,  220.0,    0.0),   # T: +Y
        2: (194.5, -220.0,    0.0),   # B: -Y
        3: (194.5,    0.0,  220.0),   # F: +Z
        4: (194.5,    0.0, -220.0),   # K: -Z
    }
    for pin_i, tp in _PIN_PCD.items():
        pairs.append((f"rotor_disc-1↔hammer_pin-{pin_i}",
                      f"hammer_pin-{pin_i}", "rotor_disc-1",
                      15, 20, tp))

    # 注: 锤头(hammer)仅靠坐标定位, 不加配合
    # 锤头唯一圆柱 axis=(0,0,-1), 销轴 axis=(-1,0,0) → 正交, 不可共轴

    return pairs


def phase_5_products(dao: Dao) -> Dict[str, Any]:
    """保存 + 截图."""
    save = dao.save()
    print(f"  Save: ok={save.get('ok')} err={save.get('errors',0)} warn={save.get('warnings',0)}")

    views = {"iso": 7, "front": 1, "top": 5, "right": 3}
    for label, vid in views.items():
        try:
            dao.doc.ShowNamedView2(label.capitalize(), vid)
            dao.doc.ViewZoomtofit2()
            bmp = str(OUT / f"hybrid_{label}.bmp")
            dao.doc.SaveBMP(bmp, 0, 0)
            print(f"  {label} → hybrid_{label}.bmp")
        except Exception:
            pass
    return {"ok": True}


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════
def main():
    print("═══ 道·混元引擎 · 坐标+意图 并行不悖 ═══")
    print("═══ 万物并育而不相害 道并行而不相悖 ═══\n")

    t0 = time.time()
    dao = Dao().connect()
    report = {"phases": {}}

    phases = [
        ("0_connect",          lambda: phase_0_connect(dao)),
        ("1_clean",            lambda: phase_1_clean(dao)),
        ("2_position",         lambda: phase_2_position(dao)),
        ("3_verify_position",  lambda: phase_3_verify_positions(dao)),
        ("4_fix_and_mate",     lambda: phase_4_fix_and_mate(dao)),
        ("5_verify_final",     lambda: phase_3_verify_positions(dao)),
        ("6_products",         lambda: phase_5_products(dao)),
    ]

    for name, fn in phases:
        print(f"\n{'━'*60}")
        print(f"  Phase: {name}")
        print(f"{'━'*60}")
        pt0 = time.time()
        try:
            result = fn()
            elapsed = round(time.time() - pt0, 2)
            result["elapsed_s"] = elapsed
            report["phases"][name] = result
            ok = result.get("ok", False)
            flag = "✓" if ok else "✗"
            print(f"\n  {flag} {name} · {elapsed}s")
        except Exception as e:
            elapsed = round(time.time() - pt0, 2)
            report["phases"][name] = {"ok": False, "error": str(e), "elapsed_s": elapsed}
            print(f"\n  ✗ {name} · {elapsed}s · ERROR: {e}")
            import traceback; traceback.print_exc()

    total = round(time.time() - t0, 2)
    n_ok = sum(1 for v in report["phases"].values() if v.get("ok"))
    n_total = len(report["phases"])

    print(f"\n{'═'*60}")
    print(f"  ═══ 混元汇总 ═══")
    print(f"  总: {n_total} 阶段 · 成功: {n_ok} · 耗时: {total}s")
    for name, r in report["phases"].items():
        flag = "✓" if r.get("ok") else "✗"
        print(f"    {flag} {name:20s} {r.get('elapsed_s', '?')}s")
    print(f"{'═'*60}")

    report["summary"] = {"total": n_total, "ok": n_ok, "elapsed_s": total}
    rp = OUT / "hybrid_e2e_report.json"
    with rp.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  → {rp.name}")


if __name__ == "__main__":
    main()
