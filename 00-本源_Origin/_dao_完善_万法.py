#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
_dao_完善_万法.py — 道法自然 · 传动系统彻底完善 · 损之又损·而后大制不割

"大道氾兮, 其可左右. 万物恃之以生而不辞."
"以其终不自为大, 故能成其大."

六段完善 (与根治对称 · 反者道之动):
  ① 诊 · 读 SW 当前组件, 决定需补何物
  ② 预 · 批量 OpenDoc6 预加载 SLDPRT (规避 AddComponent5 路径1 失败)
  ③ 插 · AddComponent5 注入 motor_body / drive_pulley / motor_mount / v_belt×4
  ④ 定 · 应用 config.py 正典坐标 (绕过 SW bbox-center bug)
  ⑤ 固 · 锚定所有新件 · 防无意拖动
  ⑥ 验 · V带传动几何验算 (中心距 · 皮带长度 · 包角)
  ⑦ 存 · 保存装配 + 多视角渲染

规范依据 (网络之资):
  · Y180L-4 电机: GB 755-2008 / JB/T 10391-2008
    功率 22 kW, 额定转速 1470 r/min, 中心高 H=180, 轴伸 Ø48×110
  · 主动带轮 B 型 4 槽: GB/T 13575.1-2008 · 基准直径 PD=180
  · V 带 B 型: GB/T 11544-2012 · 宽度顶部 17 mm, 高度 11 mm
  · 从动带轮 B 型 4 槽: GB/T 13575.1-2008 · 基准直径 PD=224
  · 传动比 i = 1470/1200 = 1.225 (2% 滑移后 1.222 符合论文)
  · 中心距 C = 600 mm (在 0.7(D1+D2)~2(D1+D2) = [283,808] 合理区间)
"""
from __future__ import annotations
import math
import sys
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机"))

from 道_直连_底层 import Dao, _safe, _nothing  # noqa: E402
import 道_直连_底层_facets  # noqa: E402, F401
from dao_sw_omni import intent_to_rt  # noqa: E402

OUT = HERE / "_产物输出"
OUT.mkdir(exist_ok=True)
REPORT = OUT / "完善_万法_报告.json"

PROJECT_ROOT = HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机"
SLDPRT_DIR = PROJECT_ROOT / "交付包_最终" / "sldprt"

# ═══════════════════════════════════════════════════════════════
# 需要插入的辅助组件清单 (道法自然 · 一次推进到底)
# ═══════════════════════════════════════════════════════════════
# 坐标来源: config.py:ASSEMBLY_POSITIONS (正典) + 历史 EXTRA_POSITIONS (motor_mount)
# V 带 4 根: Y 偏置 ±9.5/±28.5 (B型皮带宽度间隔 19 mm), tz 取两轮中点
# ═══════════════════════════════════════════════════════════════

# 规范电机/传动参数 (遵 GB/T 755-2008 / GB/T 13575.1-2008)
DRIVE_PULLEY_PD = 180.0    # mm, 基准直径
DRIVEN_PULLEY_PD = 224.0   # mm
MOTOR_SHAFT_Z = -600.0     # mm, 电机轴Z坐标 (相对主轴)
BELT_MIDPOINT_Z = (0.0 + MOTOR_SHAFT_Z) / 2.0  # = -300

# B 型皮带宽度 17 mm, 4 根均布于主动带轮 4 槽
# 带轮宽度 90 mm, 槽中心间距 ~19 mm
BELT_Y_OFFSETS = [-28.5, -9.5, 9.5, 28.5]

IMPORTS: List[Tuple[str, Dict[str, Any]]] = [
    ("motor_body",  {"tx": -495.0,  "ty": 0.0,   "tz": -600.0, "rv": None, "ra": 0.0}),
    ("drive_pulley",{"tx":  -90.0,  "ty": 0.0,   "tz": -600.0, "rv": None, "ra": 0.0}),
    ("motor_mount", {"tx": -432.5,  "ty": 0.0,   "tz": -780.0, "rv": None, "ra": 0.0}),
    # 4 根 V 带: X 方向跨两轮中点, Z 为两轮中心连线中点
    ("v_belt",      {"tx":  -45.0,  "ty": -28.5, "tz": BELT_MIDPOINT_Z, "rv": None, "ra": 0.0}),
    ("v_belt",      {"tx":  -45.0,  "ty":  -9.5, "tz": BELT_MIDPOINT_Z, "rv": None, "ra": 0.0}),
    ("v_belt",      {"tx":  -45.0,  "ty":   9.5, "tz": BELT_MIDPOINT_Z, "rv": None, "ra": 0.0}),
    ("v_belt",      {"tx":  -45.0,  "ty":  28.5, "tz": BELT_MIDPOINT_Z, "rv": None, "ra": 0.0}),
]


# ═══════════════════════════════════════════════════════════════
# 工具 · 预加载 SLDPRT
# ═══════════════════════════════════════════════════════════════
def preload_part(dao: Dao, sldprt: Path) -> bool:
    """OpenDoc6 预加载 · 让 AddComponent5 走路径1 (bbox-center bug 少)."""
    import pythoncom
    from win32com.client import VARIANT
    e_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    w_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    try:
        doc = dao.sw.OpenDoc6(str(sldprt), 1, 1, "", e_v, w_v)
        return doc is not None
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# 工具 · 插入组件
# ═══════════════════════════════════════════════════════════════
def add_one(dao: Dao, sldprt: Path) -> Optional[str]:
    """AddComponent5 插入, 返回新组件名或 None · 三路回退."""
    if dao.asm is None:
        return None
    path_str = str(sldprt)

    # 获取插入前组件快照
    before = set(dao.build_comp_map(force=True).keys())

    # 路 1: AddComponent5 (位置 0,0,0)
    try:
        comp = dao.asm.AddComponent5(path_str, 0, "", False, "", 0.0, 0.0, 0.0)
        if comp is None:
            # 路 2: AddComponents2 批量
            try:
                comps = dao.asm.AddComponents2([path_str], [0.0], [0.0], [0.0])
                if comps is not None and hasattr(comps, "__iter__"):
                    for c in comps:
                        if c is not None:
                            comp = c
                            break
            except Exception:
                pass
        if comp is None:
            # 路 3: AddComponent4
            try:
                comp = dao.asm.AddComponent4(path_str, "", 0.0, 0.0, 0.0)
            except Exception:
                pass
    except Exception:
        comp = None

    if comp is None:
        return None

    # Rebuild + 对比 snapshot 找新组件名
    dao.rebuild(force=True)
    time.sleep(0.2)
    after = set(dao.build_comp_map(force=True).keys())
    new_names = after - before
    if not new_names:
        return None
    # 期望恰一个 (若多个取最后数字后缀)
    return sorted(new_names)[-1] if len(new_names) > 1 else next(iter(new_names))


# ═══════════════════════════════════════════════════════════════
# ① 诊 · 决定需补何物
# ═══════════════════════════════════════════════════════════════
def phase_1_diagnose(dao: Dao) -> Dict[str, Any]:
    cmap = dao.build_comp_map(force=True)
    present = sorted(cmap.keys())
    title = _safe(lambda: str(dao.doc.GetTitle()), "?")

    # 期望的新件基名计数
    need_count = {"motor_body": 0, "drive_pulley": 0, "motor_mount": 0, "v_belt": 0}
    for base, _ in IMPORTS:
        need_count[base] += 1

    # 已有计数
    have_count: Dict[str, int] = {k: 0 for k in need_count}
    for name in present:
        for base in have_count:
            if name.startswith(base + "-") or name.startswith(base):
                have_count[base] += 1
                break

    # 要插入的数量 = need - have
    to_insert: Dict[str, int] = {}
    for base in need_count:
        delta = need_count[base] - have_count[base]
        if delta > 0:
            to_insert[base] = delta

    print(f"  Doc: {title}")
    print(f"  组件: {len(cmap)}")
    print(f"  需求 need: {need_count}")
    print(f"  现有 have: {have_count}")
    print(f"  待插 delta: {to_insert}")

    # 验证 SLDPRT 文件存在
    missing_sldprt = []
    for base in need_count:
        f = SLDPRT_DIR / f"{base}.SLDPRT"
        if not f.exists():
            missing_sldprt.append(str(f))

    if missing_sldprt:
        print(f"  ✗ 缺 SLDPRT: {missing_sldprt}")
    else:
        print(f"  ✓ SLDPRT 文件齐全于 {SLDPRT_DIR}")

    return {
        "ok": len(missing_sldprt) == 0,
        "doc": title,
        "total_comps": len(cmap),
        "need": need_count,
        "have": have_count,
        "to_insert": to_insert,
        "missing_sldprt": missing_sldprt,
    }


# ═══════════════════════════════════════════════════════════════
# ② 预 · 批量 OpenDoc6 预加载
# ═══════════════════════════════════════════════════════════════
def phase_2_preload(dao: Dao) -> Dict[str, Any]:
    unique_bases = sorted({base for base, _ in IMPORTS})
    results = {}
    for base in unique_bases:
        f = SLDPRT_DIR / f"{base}.SLDPRT"
        if not f.exists():
            results[base] = False
            print(f"  ✗ {base}: {f} 不存在")
            continue
        ok = preload_part(dao, f)
        results[base] = ok
        flag = "✓" if ok else "✗"
        print(f"  {flag} preload {base}")
        time.sleep(0.1)

    # 切回装配体 (预加载改变了活动文档)
    try:
        asm_title = _safe(lambda: str(dao.doc.GetTitle()), "")
        if asm_title:
            dao.sw.ActivateDoc3(asm_title, False, 0, 0)
            time.sleep(0.3)
    except Exception:
        pass

    return {"ok": all(results.values()), "results": results}


# ═══════════════════════════════════════════════════════════════
# ③ 插 · AddComponent5 注入
# ═══════════════════════════════════════════════════════════════
def phase_3_insert(dao: Dao, diag: Dict[str, Any]) -> Dict[str, Any]:
    to_insert = diag.get("to_insert", {})
    if not to_insert:
        print("  已满 (无缺件)")
        return {"ok": True, "inserted": [], "failed": []}

    inserted: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    # 按 IMPORTS 顺序, 但仅处理需补的
    remaining = dict(to_insert)
    for base, pos in IMPORTS:
        if remaining.get(base, 0) <= 0:
            continue

        sldprt = SLDPRT_DIR / f"{base}.SLDPRT"
        new_name = add_one(dao, sldprt)
        if new_name:
            inserted.append({"base": base, "name": new_name, "target_pos": pos})
            remaining[base] -= 1
            print(f"  ✓ {base} → {new_name}")
        else:
            failed.append({"base": base, "target_pos": pos, "err": "AddComponent5 returned None"})
            print(f"  ✗ {base} 插入失败")

        time.sleep(0.3)

    dao.rebuild(force=True)
    time.sleep(0.5)

    return {
        "ok": len(failed) == 0,
        "inserted": inserted,
        "failed": failed,
    }


# ═══════════════════════════════════════════════════════════════
# ④ 定 · 应用 config.py 正典坐标
# ═══════════════════════════════════════════════════════════════
def phase_4_position(dao: Dao, insert_r: Dict[str, Any]) -> Dict[str, Any]:
    inserted = insert_r.get("inserted", [])
    results = []
    ok_count = 0

    for item in inserted:
        name = item["name"]
        pos = item["target_pos"]

        tx, ty, tz = float(pos["tx"]), float(pos["ty"]), float(pos["tz"])
        rv = pos.get("rv")
        ra = float(pos.get("ra") or 0)

        if rv and ra:
            R, t_mm = intent_to_rt("origin", (tx, ty, tz), rv, ra)
            rot_flat = tuple(R[r][c] for c in range(3) for r in range(3))
        else:
            rot_flat = None
            t_mm = (tx, ty, tz)

        # 应用 transform.set (绕过 AddComponent5 的 bbox-center bug)
        ok = dao.transform.set(name, t_mm, rot=rot_flat)
        if ok:
            ok_count += 1
        flag = "✓" if ok else "✗"
        actual = dao.transform.origin_mm(name)
        actual_str = (f"({actual[0]:+.0f},{actual[1]:+.0f},{actual[2]:+.0f})"
                      if actual else "?")
        print(f"  {flag} {name:20s} → ({tx:+.0f},{ty:+.0f},{tz:+.0f}) actual={actual_str}")

        results.append({
            "name": name, "target": t_mm,
            "actual": list(actual) if actual else None,
            "ok": bool(ok),
        })

    dao.rebuild(force=True)
    time.sleep(0.3)

    return {
        "ok": ok_count == len(inserted),
        "positioned": ok_count,
        "total": len(inserted),
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════
# ⑤ 固 · 锚定所有新件
# ═══════════════════════════════════════════════════════════════
def phase_5_fix(dao: Dao, insert_r: Dict[str, Any]) -> Dict[str, Any]:
    inserted = insert_r.get("inserted", [])
    fixed_count = 0
    for item in inserted:
        name = item["name"]
        try:
            if not dao.comp.is_fixed(name):
                if dao.comp.fix(name):
                    fixed_count += 1
        except Exception as e:
            print(f"  ✗ fix {name}: {e}")
    dao.rebuild(force=True)
    time.sleep(0.3)

    print(f"  固定: {fixed_count}/{len(inserted)}")
    return {"ok": fixed_count == len(inserted), "fixed": fixed_count}


# ═══════════════════════════════════════════════════════════════
# ⑥ 验 · V 带传动几何验算
# ═══════════════════════════════════════════════════════════════
def phase_6_transmission_verify(dao: Dao) -> Dict[str, Any]:
    """按 GB/T 13575.1 公式验算传动几何."""
    # 两轮中心距 · 基准直径
    C = 600.0                    # 中心距 (mm)
    D1 = DRIVE_PULLEY_PD         # 主动轮基准直径 180
    D2 = DRIVEN_PULLEY_PD        # 从动轮基准直径 224

    # 理论皮带长度 (开口传动)
    # L = 2C + π(D1+D2)/2 + (D2-D1)²/(4C)
    L_theory = 2 * C + math.pi * (D1 + D2) / 2.0 + (D2 - D1)**2 / (4 * C)

    # 传动比
    i = D2 / D1

    # 小轮包角 (deg)
    alpha = 180.0 - (D2 - D1) / C * (180.0 / math.pi)

    # 中心距合理性
    C_min = 0.7 * (D1 + D2)
    C_max = 2.0 * (D1 + D2)
    C_ok = C_min <= C <= C_max

    # 实际装配中两轮几何
    drive_origin = dao.transform.origin_mm("drive_pulley-1")
    driven_origin = dao.transform.origin_mm("driven_pulley-1")
    actual_C = None
    if drive_origin and driven_origin:
        # 两轮中心距 (忽略 X, X 方向轴向距离不计)
        actual_C = math.hypot(
            driven_origin[1] - drive_origin[1],
            driven_origin[2] - drive_origin[2],
        )

    print(f"  基准直径: D1={D1:.0f}mm D2={D2:.0f}mm")
    print(f"  中心距 C={C:.0f}mm (合理区 [{C_min:.0f},{C_max:.0f}]): "
          f"{'✓' if C_ok else '✗'}")
    print(f"  传动比 i = D2/D1 = {i:.3f}")
    print(f"  小轮包角 α1 ≈ {alpha:.1f}° (≥120° 良好)")
    print(f"  理论皮带长度 L = {L_theory:.1f}mm")
    if actual_C is not None:
        drift = abs(actual_C - C)
        print(f"  实测中心距: {actual_C:.1f}mm (偏差 {drift:.1f}mm)")

    return {
        "ok": C_ok and alpha >= 120.0,
        "D1_mm": D1, "D2_mm": D2, "C_mm": C,
        "C_min_mm": C_min, "C_max_mm": C_max, "C_ok": C_ok,
        "ratio": round(i, 4),
        "wrap_angle_deg": round(alpha, 2),
        "belt_length_theory_mm": round(L_theory, 1),
        "actual_C_mm": round(actual_C, 1) if actual_C else None,
    }


# ═══════════════════════════════════════════════════════════════
# ⑦ 存 · 保存 + 多视角渲染
# ═══════════════════════════════════════════════════════════════
def phase_7_save_render(dao: Dao) -> Dict[str, Any]:
    sr = dao.save()
    print(f"  Save: ok={sr.get('ok')} err={sr.get('errors',0)} warn={sr.get('warnings',0)}")

    views = {
        "iso": 7, "front": 1, "back": 2,
        "top": 5, "right": 3, "left": 4,
    }
    captured = []
    for label, vid in views.items():
        try:
            dao.doc.ShowNamedView2(label.capitalize(), vid)
            dao.doc.ViewZoomtofit2()
            time.sleep(0.2)
            bmp = str(OUT / f"完善_{label}.bmp")
            dao.doc.SaveBMP(bmp, 1920, 1080)
            captured.append(label)
            print(f"  {label} → 完善_{label}.bmp")
        except Exception as e:
            print(f"  {label} ✗ {e}")

    return {"ok": bool(sr.get("ok")), "captured": captured}


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    print("═══ 道·完善引擎 · 万法归宗 ═══")
    print("═══ 大道氾兮, 其可左右 ═══")
    print("═══ 以其终不自为大, 故能成其大 ═══\n")

    t0 = time.time()
    dao = Dao().connect()
    report: Dict[str, Any] = {"phases": {}}

    # Phase 1: 诊断
    print(f"\n{'━'*60}\n  Phase: 1_diagnose\n{'━'*60}")
    diag = phase_1_diagnose(dao)
    report["phases"]["1_diagnose"] = diag

    # Phase 2: 预加载
    print(f"\n{'━'*60}\n  Phase: 2_preload\n{'━'*60}")
    preload_r = phase_2_preload(dao)
    report["phases"]["2_preload"] = preload_r

    # Phase 3: 插入
    print(f"\n{'━'*60}\n  Phase: 3_insert\n{'━'*60}")
    insert_r = phase_3_insert(dao, diag)
    report["phases"]["3_insert"] = insert_r

    # Phase 4: 定位
    print(f"\n{'━'*60}\n  Phase: 4_position\n{'━'*60}")
    pos_r = phase_4_position(dao, insert_r)
    report["phases"]["4_position"] = pos_r

    # Phase 5: 固定
    print(f"\n{'━'*60}\n  Phase: 5_fix\n{'━'*60}")
    fix_r = phase_5_fix(dao, insert_r)
    report["phases"]["5_fix"] = fix_r

    # Phase 6: 传动验证
    print(f"\n{'━'*60}\n  Phase: 6_transmission_verify\n{'━'*60}")
    tv_r = phase_6_transmission_verify(dao)
    report["phases"]["6_transmission_verify"] = tv_r

    # Phase 7: 保存+渲染
    print(f"\n{'━'*60}\n  Phase: 7_save_render\n{'━'*60}")
    save_r = phase_7_save_render(dao)
    report["phases"]["7_save_render"] = save_r

    total = round(time.time() - t0, 2)
    n_ok = sum(1 for v in report["phases"].values() if v.get("ok"))
    n_total = len(report["phases"])

    print(f"\n{'═'*60}")
    print(f"  ═══ 完善汇总 ═══")
    print(f"  阶段: {n_total} · 成功: {n_ok} · 耗时: {total}s")
    for name, r in report["phases"].items():
        flag = "✓" if r.get("ok") else "✗"
        print(f"    {flag} {name}")
    print(f"{'═'*60}")

    report["summary"] = {"total": n_total, "ok": n_ok, "elapsed_s": total}
    with REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  → {REPORT.name}")


if __name__ == "__main__":
    main()
