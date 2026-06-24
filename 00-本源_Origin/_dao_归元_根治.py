#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
_dao_归元_根治.py — 反者道之动 · 归元三治

"反者道之动, 弱者道之用. 天下万物生于有, 有生于无."
"知其雄, 守其雌, 为天下谿. 知其白, 守其黑, 为天下式."

三治:
  ① 皮带归元 · 删 4 根幽灵 v_belt · 回归 1 根本源单件
  ② 锤头归正 · 销孔对齐销轴 · 世界 Y/Z 范围缩至 ≤280 (<Ri=390, 不穿筛板)
  ③ 电机归位 · 电机底面与 motor_mount 顶面贴合 · 解穿模

根因:
  · 原 hammer 位置 ty=dy_u·220 + y_off=0, 使局部 Y=[0,180] 平移后 world Y=[220,400]
    销孔局部 Y=120 置于 world Y=340, 与销轴 (Y=220) 错开 120mm, 且 R_max=400 > Ri=390
  · 新 hammer 位置: 令销孔 (局部 120) 对齐销轴 (world 220) → ty=100, world Y=[100,280]
    R_max=280 < Ri=390 ✓ 不穿模; 销孔对齐 ✓
  · 电机 Z=-600 使底面 Z=-800, motor_mount 顶面 Z=-780 → 电机穿入 mount 顶 20mm
    修正: motor_mount 下移 25mm (tz=-780 → -805), 顶面贴电机底
"""
from __future__ import annotations
import sys, time, json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机"))

from 道_直连_底层 import Dao, _safe, _nothing  # noqa
import 道_直连_底层_facets  # noqa
from dao_sw_omni import intent_to_rt

PROJ = HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机"
SLDPRT_SRC = PROJ / "交付包_最终" / "sldprt"
OUT = HERE / "_产物输出"
OUT.mkdir(exist_ok=True)
REPORT = OUT / "归元_根治_报告.json"

# 要删的 4 根幽灵 V 带
GHOST_VBELTS = ["v_belt-9", "v_belt-10", "v_belt-11", "v_belt-12"]

# V 带本源单件路径
VBELT_SLDPRT = SLDPRT_SRC / "v_belt.SLDPRT"

# ────────────────────────────────────────────────────────────────
# 新 PCD_DIRS — 销孔对齐销轴, 世界径向半径=280 < Ri=390
# hammer 几何: W_BOTTOM=80 · W_TOP=40 · HEIGHT=180 · HOLE_Y=120 (局部)
# 销孔在 (0, 120, 20) 局部
# 旋转矩阵 Rx(ra) · 平移 (tx,ty,tz): 使销孔 world = 销轴位置 (PCD 圆周)
# ────────────────────────────────────────────────────────────────
X_DISCS = [207, 408, 610, 810]
PCD_RADIUS = 220
HOLE_Y = 120

# (tag, dy_u, dz_u, rot_deg, y_off, z_off)
# y_off/z_off 为厚度对齐补偿 (使 hammer 厚度 40 居中于销轴轴线)
# ty = dy_u * PCD + y_off; tz = dz_u * PCD + z_off
# 新配方: 加 -dy_u * HOLE_Y 到 y_off / -dz_u * HOLE_Y 到 z_off
# 使销孔 (局部 120 → rot · 120 → world 120·方向) 对齐销轴 world (PCD·方向)
PCD_DIRS_FIXED = [
    # T: ra=0, 局部 Y → world Y: 销孔 world Y = ty+120 = 220 → ty = 100; y_off = 100-220 = -120
    ("T", +1,  0,    0,  -HOLE_Y, -20),
    # F: ra=+90 绕 X, 局部 Y → world Z, 局部 Z → world -Y
    #   销孔 (0,120,20) → (0,-20,120), ty-20=0→ty=20(原), tz+120=220→tz=100; z_off = 100-220 = -120
    ("F",  0, +1,  +90,  +20,  -HOLE_Y),
    # B: ra=180 绕 X, 局部 Y → world -Y, 局部 Z → world -Z
    #   销孔 → (0,-120,-20), ty-120=-220→ty=-100; y_off = -100-(-220) = +120
    ("B", -1,  0, +180, +HOLE_Y, +20),
    # K: ra=-90 绕 X, 局部 Y → world -Z, 局部 Z → world Y
    #   销孔 → (0,20,-120), ty+20=0→ty=-20(原), tz-120=-220→tz=-100; z_off = -100-(-220) = +120
    ("K",  0, -1,  -90,  -20, +HOLE_Y),
]


def build_new_hammer_positions() -> Dict[str, Dict[str, Any]]:
    positions = {}
    hidx = 1
    for dx in X_DISCS:
        for tag, dy_u, dz_u, rot_deg, y_off, z_off in PCD_DIRS_FIXED:
            tx = float(dx)
            ty = float(dy_u * PCD_RADIUS + y_off)
            tz = float(dz_u * PCD_RADIUS + z_off)
            rv = [1, 0, 0] if rot_deg != 0 else None
            ra = float(rot_deg)
            positions[f"hammer-{hidx}"] = {
                "tx": tx, "ty": ty, "tz": tz,
                "rv": rv, "ra": ra, "tag": tag,
            }
            hidx += 1
    return positions


# 新电机系位置 — motor_mount 下移 25mm 使顶面贴电机底
MOTOR_SYSTEM = {
    "motor_body-2":  {"tx": -495,   "ty": 0, "tz": -600,  "rv": None, "ra": 0},
    "drive_pulley-2":{"tx":  -90,   "ty": 0, "tz": -600,  "rv": None, "ra": 0},
    # 原 -780 → -805 (下移 25mm 使 mount 顶面 = 电机底面 = -805)
    "motor_mount-3": {"tx": -432.5, "ty": 0, "tz": -805,  "rv": None, "ra": 0},
}

# V 带单件本源位置: 绕从动带轮 (X=0 处), 世界 X 从 -28.5 到 +28.5 (4 带并排)
# 但 v_belt.SLDPRT 是复合 4 带绕从动轮一圈 — 位置 (0, 0, 0) + 可能有局部偏移
VBELT_SINGLE_POS = {"tx": 0, "ty": 0, "tz": 0, "rv": None, "ra": 0}


# ────────────────────────────────────────────────────────────────
# 公共 · 工具
# ────────────────────────────────────────────────────────────────
def _dyn_app(dao):
    import win32com.client.dynamic as _d
    return _d.Dispatch(dao._sw_raw)


def get_assembly_doc(dao):
    app = _dyn_app(dao)
    doc = app.GetFirstDocument
    guard = 0
    while doc is not None and guard < 60:
        guard += 1
        try:
            if int(doc.GetType) == 2:
                return doc
        except: pass
        try: doc = doc.GetNext
        except: break
    return None


def close_non_asm(dao, keep_title):
    app = _dyn_app(dao)
    titles, doc, g = [], app.GetFirstDocument, 0
    while doc is not None and g < 60:
        g += 1
        try: titles.append(str(doc.GetTitle))
        except: pass
        try: doc = doc.GetNext
        except: break
    uniq = []
    seen = set()
    for t in titles:
        if t and t not in seen:
            seen.add(t); uniq.append(t)
    closed = 0
    for t in uniq:
        if t == keep_title: continue
        try:
            app.CloseDoc(t); closed += 1
        except: pass
    return closed


def rebind(dao):
    try:
        active = dao.sw.ActiveDoc
        if active is not None:
            dao._doc_raw = active._ole if hasattr(active, "_ole") else active
            from 道_直连_底层 import DaoDispatch
            dao.doc = DaoDispatch(dao._doc_raw, "IModelDoc2", dao.mt, dao)
            try: dao.asm = dao.doc.cast("IAssemblyDoc")
            except: pass
            dao._comp_map_cache = None
            return True
    except: pass
    return False


def apply_transform(dao, name, pos):
    tx, ty, tz = float(pos["tx"]), float(pos["ty"]), float(pos["tz"])
    rv = pos.get("rv"); ra = float(pos.get("ra") or 0)
    if rv and ra:
        R, t_mm = intent_to_rt("origin", (tx, ty, tz), rv, ra)
        rot_flat = tuple(R[r][c] for c in range(3) for r in range(3))
    else:
        rot_flat = None
        t_mm = (tx, ty, tz)
    return dao.transform.set(name, t_mm, rot=rot_flat)


def delete_comps(dao, asm_doc, names):
    cmap = dao.build_comp_map(force=True)
    present = [n for n in names if n in cmap]
    if not present:
        return 0
    # 解锁
    for n in present:
        try:
            if dao.comp.is_fixed(n):
                dao.comp.unfix(n)
        except: pass
    time.sleep(0.2)
    asm_doc.ClearSelection2(True)
    sel = 0
    comps = asm_doc.GetComponents(False) or []
    ns = set(present)
    for c in comps:
        try:
            if str(c.Name2) in ns and bool(c.Select(True)):
                sel += 1
        except: pass
    deleted = 0
    if sel > 0:
        try:
            if asm_doc.Extension.DeleteSelection2(18):
                deleted = sel
        except: pass
        asm_doc.ClearSelection2(True)
    dao.rebuild(force=True); time.sleep(0.4)
    dao._comp_map_cache = None
    return deleted


def insert_component(dao, sldprt: Path, asm_doc, title: str):
    import pythoncom
    from win32com.client import VARIANT
    app = _dyn_app(dao)
    try:
        e = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        w = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        app.OpenDoc6(str(sldprt), 1, 1, "", e, w)
        time.sleep(0.3)
    except: pass
    # 强制回装配体
    try:
        app.ActivateDoc3(title, False, 0, VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0))
    except: pass
    time.sleep(0.2)
    comp = None
    for fn in ("AddComponent5", "AddComponent4"):
        try:
            if fn == "AddComponent5":
                comp = asm_doc.AddComponent5(str(sldprt), 0, "", False, "", 0.0, 0.0, 0.0)
            else:
                comp = asm_doc.AddComponent4(str(sldprt), "", 0.0, 0.0, 0.0)
            if comp is not None:
                break
        except: pass
    if comp is None:
        return None
    try: asm_doc.ForceRebuild3(False)
    except: dao.rebuild(force=True)
    time.sleep(0.4)
    try: return str(comp.Name2)
    except: return None


# ────────────────────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────────────────────
def main():
    print("═══ 道·归元·根治 · 皮带 · 锤头 · 电机 ═══\n")
    t0 = time.time()
    dao = Dao().connect()
    report = {"phases": {}, "config": {
        "new_hammer_positions": build_new_hammer_positions(),
        "motor_system": MOTOR_SYSTEM,
    }}

    asm_doc = get_assembly_doc(dao)
    if asm_doc is None:
        print("✗ 无装配体"); return
    asm_title = str(asm_doc.GetTitle)
    print(f"Assembly: {asm_title}")
    close_non_asm(dao, asm_title)
    time.sleep(0.3); rebind(dao)

    # ─── Phase 1: 除 4 根幽灵 v_belt ───
    print(f"\n{'━'*60}\n  Phase 1: 皮带归元 · 除 4 根幽灵\n{'━'*60}")
    deleted = delete_comps(dao, asm_doc, GHOST_VBELTS)
    cmap = dao.build_comp_map(force=True)
    surv = [n for n in GHOST_VBELTS if n in cmap]
    print(f"  删: {deleted} · 残留: {len(surv)}")
    report["phases"]["1_vbelt_purge"] = {"ok": not surv, "deleted": deleted, "survivors": surv}

    # ─── Phase 2: 重定位 16 hammer (销孔对齐销轴) ───
    print(f"\n{'━'*60}\n  Phase 2: 锤头归正 · 销孔对齐销轴\n{'━'*60}")
    # 解锁 hammer (如已固定)
    cmap = dao.build_comp_map(force=True)
    hammers = sorted([n for n in cmap if n.startswith("hammer-")],
                     key=lambda s: int(s.split("-")[1]))
    for h in hammers:
        try:
            if dao.comp.is_fixed(h):
                dao.comp.unfix(h)
        except: pass
    time.sleep(0.3)

    new_pos = build_new_hammer_positions()
    relocate_ok = 0
    for h in hammers:
        if h in new_pos:
            p = new_pos[h]
            ok = apply_transform(dao, h, p)
            tag = p.get("tag", "?")
            if ok:
                relocate_ok += 1
                print(f"  ✓ {h:12s} [{tag}] → ({p['tx']:+4.0f},{p['ty']:+4.0f},{p['tz']:+4.0f})")
            else:
                print(f"  ✗ {h:12s} relocate failed")
    dao.rebuild(force=True); time.sleep(0.5)

    # 验证 hammer 世界 bbox Y/Z 范围 ≤ 390
    max_radial = 0.0
    for c in (asm_doc.GetComponents(False) or []):
        try:
            nm = str(c.Name2)
            if not nm.startswith("hammer-"):
                continue
            box = c.GetBox(False, False)
            if box and len(box) >= 6:
                b_mm = [v*1000 for v in box[:6]]
                # 径向半径 = max(|Y|, |Z|) 的 bbox 角点
                r = max(abs(b_mm[1]), abs(b_mm[2]), abs(b_mm[4]), abs(b_mm[5]))
                if r > max_radial:
                    max_radial = r
        except: pass
    print(f"  16 hammer max radial = {max_radial:.1f} mm (vs Ri=390 screen)")
    report["phases"]["2_hammer_realign"] = {
        "ok": relocate_ok == 16 and max_radial < 390,
        "relocated": relocate_ok,
        "max_radial_mm": round(max_radial, 1),
        "screen_Ri_mm": 390,
        "clearance_mm": round(390 - max_radial, 1),
    }

    # ─── Phase 3: 电机系归位 · motor_mount 下移 25 贴电机底 ───
    print(f"\n{'━'*60}\n  Phase 3: 电机归位 · mount 贴电机底\n{'━'*60}")
    cmap = dao.build_comp_map(force=True)
    motor_ok = 0
    for n, p in MOTOR_SYSTEM.items():
        if n in cmap:
            try:
                if dao.comp.is_fixed(n):
                    dao.comp.unfix(n)
            except: pass
            if apply_transform(dao, n, p):
                motor_ok += 1
                print(f"  ✓ {n:18s} → ({p['tx']:+5.0f},{p['ty']:+4.0f},{p['tz']:+5.0f})")
    dao.rebuild(force=True); time.sleep(0.4)

    # 验证电机-mount 贴合
    motor_bot = None; mount_top = None
    for c in (asm_doc.GetComponents(False) or []):
        try:
            nm = str(c.Name2)
            box = c.GetBox(False, False)
            if box and len(box) >= 6:
                b = [v*1000 for v in box[:6]]
                if nm == "motor_body-2":
                    motor_bot = b[2]  # Z_min
                elif nm == "motor_mount-3":
                    mount_top = b[5]  # Z_max
        except: pass
    gap = None
    if motor_bot is not None and mount_top is not None:
        gap = mount_top - motor_bot  # >0 穿模, <0 悬空
    print(f"  motor底 Z={motor_bot} · mount顶 Z={mount_top} · 重叠 {gap}mm "
          f"(-={'贴合'if gap==0 else '悬空' if gap and gap<0 else '穿模'})")
    report["phases"]["3_motor_realign"] = {
        "ok": motor_ok == 3 and (gap is None or abs(gap) < 5),
        "repositioned": motor_ok,
        "motor_bot_z": motor_bot, "mount_top_z": mount_top, "gap_mm": gap,
    }

    # ─── Phase 4: V 带单件本源插入 (可选) ───
    print(f"\n{'━'*60}\n  Phase 4: V 带本源 · 单件插入\n{'━'*60}")
    belt_result = {"ok": False, "action": "skipped"}
    if VBELT_SLDPRT.exists():
        try:
            name = insert_component(dao, VBELT_SLDPRT, asm_doc, asm_title)
            if name:
                print(f"  插入 V 带: {name}")
                # 尝试放置在原中心位置
                apply_transform(dao, name, VBELT_SINGLE_POS)
                belt_result = {"ok": True, "name": name, "action": "inserted"}
            else:
                belt_result = {"ok": False, "action": "insert_failed"}
                print(f"  插入失败")
        except Exception as e:
            print(f"  异常: {e}")
            belt_result = {"ok": False, "action": f"exception:{e}"}
    else:
        print(f"  无 SLDPRT 源: {VBELT_SLDPRT}")
        belt_result = {"ok": False, "action": "no_source"}
    report["phases"]["4_vbelt_restore"] = belt_result

    # ─── Phase 5: 固定所有组件 ───
    print(f"\n{'━'*60}\n  Phase 5: 固定全部\n{'━'*60}")
    cmap = dao.build_comp_map(force=True)
    to_fix = [n for n in cmap if not dao.comp.is_fixed(n)]
    fixed = 0
    for n in to_fix:
        try:
            if dao.comp.fix(n):
                fixed += 1
        except: pass
    dao.rebuild(force=True); time.sleep(0.3)
    cmap2 = dao.build_comp_map(force=True)
    free = [n for n in cmap2 if not dao.comp.is_fixed(n)]
    print(f"  组件: {len(cmap2)} · 固定: {fixed} · 自由: {len(free)}")
    report["phases"]["5_fix_all"] = {"ok": len(free) == 0,
                                      "total": len(cmap2), "fixed": fixed,
                                      "free": free}

    # ─── Phase 6: 保存 + 6 视图渲染 ───
    print(f"\n{'━'*60}\n  Phase 6: 保存 · 渲染\n{'━'*60}")
    sr = dao.save()
    print(f"  Save: {sr.get('ok')}")
    captured = []
    views = {"iso": 7, "front": 1, "back": 2, "top": 5, "right": 3, "left": 4}
    for label, vid in views.items():
        try:
            dao.doc.ShowNamedView2(label.capitalize(), vid)
            dao.doc.ViewZoomtofit2()
            time.sleep(0.2)
            bmp = str(OUT / f"归元_{label}.bmp")
            dao.doc.SaveBMP(bmp, 1920, 1080)
            captured.append(label)
        except Exception as e:
            print(f"  {label} ✗ {e}")
    print(f"  渲染: {len(captured)}/6 视图")
    report["phases"]["6_save_render"] = {"ok": sr.get("ok") and len(captured) == 6,
                                          "captured": captured}

    # 汇总
    t = round(time.time() - t0, 2)
    n_ok = sum(1 for v in report["phases"].values() if v.get("ok"))
    n_total = len(report["phases"])
    print(f"\n{'═'*60}")
    print(f"  归元·根治 · {n_ok}/{n_total} 通过 · {t}s")
    for k, v in report["phases"].items():
        f = "✓" if v.get("ok") else "✗"
        print(f"    {f} {k}")
    print(f"{'═'*60}")

    report["summary"] = {"ok": n_ok, "total": n_total, "elapsed_s": t}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                      encoding="utf-8")
    print(f"\n  → {REPORT.name}")


if __name__ == "__main__":
    main()
