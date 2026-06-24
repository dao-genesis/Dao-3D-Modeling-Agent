#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
_dao_完善_补救.py — 道法自然 · 补 motor_mount + v_belt×4 · STEP→SLDPRT 中转

"将欲取之, 必固与之. 是谓微明. 柔弱胜刚强."
"大巧若拙, 大辩若讷."

原 SLDPRT 文件 SW 打不开 (SW2023 与保存版本不兼容), 本脚本:
  ① 从 STEP 源 (output_cq/*.step) 重建 SLDPRT, 存入 stage 目录
  ② 切回活体装配体, AddComponent5 注入
  ③ 应用 config.py 正典坐标
  ④ 固定 · 保存 · 渲染
"""
from __future__ import annotations
import sys
import time
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机"))

from 道_直连_底层 import Dao, _safe  # noqa: E402
import 道_直连_底层_facets  # noqa: E402, F401
from dao_sw_omni import intent_to_rt  # noqa: E402

OUT = HERE / "_产物输出"
OUT.mkdir(exist_ok=True)
REPORT = OUT / "完善_补救_报告.json"

PROJECT_ROOT = HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机"
OUT_CQ = PROJECT_ROOT / "output_cq"
STAGE = Path(r"E:\Temp\dao_sw_stage_完善")
STAGE.mkdir(parents=True, exist_ok=True)

# 待补组件 (base_name, 目标位置)
NEEDED: List[Tuple[str, Dict[str, Any]]] = [
    ("motor_mount", {"tx": -432.5, "ty":   0.0, "tz": -780.0, "rv": None, "ra": 0.0}),
    ("v_belt",      {"tx":  -45.0, "ty": -28.5, "tz": -300.0, "rv": None, "ra": 0.0}),
    ("v_belt",      {"tx":  -45.0, "ty":  -9.5, "tz": -300.0, "rv": None, "ra": 0.0}),
    ("v_belt",      {"tx":  -45.0, "ty":   9.5, "tz": -300.0, "rv": None, "ra": 0.0}),
    ("v_belt",      {"tx":  -45.0, "ty":  28.5, "tz": -300.0, "rv": None, "ra": 0.0}),
]


# ═══════════════════════════════════════════════════════════════
# 工具 · STEP → SLDPRT 转换 (走 pywin32 dynamic · 绕 DaoDispatch)
# ═══════════════════════════════════════════════════════════════
def _dyn_app(dao: Dao):
    """从 Dao 取原 pyIDispatch → 转为 pywin32 dynamic Dispatch, 兼容传 Dispatch 作为参数."""
    import win32com.client.dynamic as _d
    return _d.Dispatch(dao._sw_raw)


def step_to_sldprt(dao: Dao, step_path: Path, out_sldprt: Path) -> bool:
    import pythoncom
    from win32com.client import VARIANT
    import win32com.client.dynamic as _d

    if not step_path.exists():
        print(f"  ✗ STEP 不存在: {step_path}")
        return False
    if out_sldprt.exists() and out_sldprt.stat().st_size > 1000:
        print(f"  = 已有 stage SLDPRT ({out_sldprt.stat().st_size//1024}KB), 跳过")
        return True

    app = _dyn_app(dao)

    # 关闭 STEP-as-assembly (单零件模式)
    try:
        app.SetUserPreferenceToggle(64, False)
    except Exception:
        pass

    # 路径 1: LoadFile4 + GetImportFileData (pywin32 dynamic · 参数兼容)
    doc = None
    try:
        ifd = app.GetImportFileData(str(step_path))
        if ifd is not None:
            e = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            ret = app.LoadFile4(str(step_path), "r", ifd, e)
            if ret is not None:
                doc = _d.Dispatch(ret) if hasattr(ret, "_oleobj_") else ret
                if doc is None or (isinstance(ret, int) and ret == 0):
                    doc = None
                if doc is not None:
                    print(f"    LoadFile4 ok (err={e.value})")
    except Exception as ex:
        print(f"    LoadFile4 exc: {ex}")

    # 路径 2: OpenDoc6
    if doc is None:
        try:
            err = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warn = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            ret = app.OpenDoc6(str(step_path), 1, 1, "", err, warn)
            if ret is not None:
                doc = _d.Dispatch(ret) if hasattr(ret, "_oleobj_") else ret
                if doc is not None:
                    print(f"    OpenDoc6 ok (err={err.value} warn={warn.value})")
        except Exception as ex:
            print(f"    OpenDoc6 exc: {ex}")

    if doc is None:
        print(f"  ✗ 打开失败")
        return False

    time.sleep(1.5)

    # ForceRebuild3
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    time.sleep(0.5)

    # Capture title before save (避免 SaveAs 后 title 改变)
    try:
        orig_title = str(doc.GetTitle)
    except Exception:
        orig_title = ""

    # SaveAs4
    ok = False
    try:
        e4 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        w4 = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        ret = doc.SaveAs4(str(out_sldprt), 0, 1, e4, w4)
        print(f"    SaveAs4 ret={ret} err={e4.value} warn={w4.value}")
    except Exception as ex:
        print(f"    SaveAs4 exc: {ex}")

    time.sleep(1.0)
    if out_sldprt.exists() and out_sldprt.stat().st_size > 1000:
        ok = True
        print(f"    ✓ {out_sldprt.name} ({out_sldprt.stat().st_size//1024}KB)")

    # SaveAs3 fallback
    if not ok:
        try:
            ret3 = doc.SaveAs3(str(out_sldprt), 0, 1)
            print(f"    SaveAs3 ret={ret3}")
        except Exception:
            pass
        time.sleep(0.8)
        if out_sldprt.exists() and out_sldprt.stat().st_size > 1000:
            ok = True

    # 关闭 STEP 源文档以及 SaveAs 后的零件
    for t in (orig_title, out_sldprt.name):
        if not t:
            continue
        try:
            app.CloseDoc(str(t))
        except Exception:
            pass
    time.sleep(0.5)

    return ok


# ═══════════════════════════════════════════════════════════════
# 工具 · 以神遇不以目视 · 直接找装配体 doc 对象
# ═══════════════════════════════════════════════════════════════
def get_assembly_doc(dao: Dao):
    """遍历所有打开文档, 返回 IAssemblyDoc (pywin32 dynamic · type=2)."""
    app = _dyn_app(dao)
    try:
        doc = app.GetFirstDocument
        guard = 0
        while doc is not None and guard < 60:
            guard += 1
            try:
                if int(doc.GetType) == 2:
                    return doc
            except Exception:
                pass
            try:
                doc = doc.GetNext
            except Exception:
                break
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════
# 工具 · 插入组件 (不依赖 active doc · 直接操作装配体句柄)
# ═══════════════════════════════════════════════════════════════
def add_one(dao: Dao, sldprt: Path, asm_title: str,
            verbose: bool = True) -> Optional[str]:
    import pythoncom
    from win32com.client import VARIANT
    app = _dyn_app(dao)

    # 1) preload SLDPRT (让 SW 认识文件)
    try:
        e_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        w_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        app.OpenDoc6(str(sldprt), 1, 1, "", e_v, w_v)
        time.sleep(0.4)
    except Exception as ex:
        if verbose:
            print(f"    preload exc: {ex}")

    # 2) 直接拿装配体 doc 对象 (不依赖 active 状态)
    asm_doc = get_assembly_doc(dao)
    if asm_doc is None:
        if verbose:
            print(f"    no assembly doc found")
        return None

    path_str = str(sldprt)
    before = set(dao.build_comp_map(force=True).keys())

    comp = None
    # 路径 1: AddComponent5 直接在装配体 doc 上
    try:
        comp = asm_doc.AddComponent5(path_str, 0, "", False, "", 0.0, 0.0, 0.0)
        if verbose:
            r = "OK" if comp is not None else "None"
            print(f"    AddComponent5: {r}")
    except Exception as ex:
        if verbose:
            print(f"    AddComponent5 exc: {ex}")

    # 路径 2: AddComponent4 fallback
    if comp is None:
        try:
            comp = asm_doc.AddComponent4(path_str, "", 0.0, 0.0, 0.0)
            if verbose:
                r = "OK" if comp is not None else "None"
                print(f"    AddComponent4: {r}")
        except Exception as ex:
            if verbose:
                print(f"    AddComponent4 exc: {ex}")

    if comp is None:
        return None

    # 3) Rebuild 装配体 (在装配体 doc 上调用)
    try:
        asm_doc.ForceRebuild3(False)
    except Exception:
        dao.rebuild(force=True)
    time.sleep(0.5)

    # 4) 直接从 comp (IComponent2) 读 Name2 · 最稳
    name_from_comp = None
    for attr in ("Name2", "Name"):
        try:
            v = getattr(comp, attr)
            if v:
                name_from_comp = str(v)
                break
        except Exception:
            pass
    if name_from_comp:
        if verbose:
            print(f"    → name (comp.Name2): {name_from_comp}")
        return name_from_comp

    # fallback: snapshot diff (通过 asm_doc, 不用 dao.doc)
    try:
        after_comps = asm_doc.GetComponents(False) or []
        after_names = set()
        for c in after_comps:
            try:
                after_names.add(str(c.Name2))
            except Exception:
                pass
        new_names = after_names - before
        if new_names:
            return sorted(new_names)[-1] if len(new_names) > 1 else next(iter(new_names))
    except Exception:
        pass
    return None


def activate_assembly(dao: Dao, asm_title: str) -> bool:
    try:
        dao.sw.ActivateDoc3(asm_title, False, 0, 0)
        time.sleep(0.4)
        return True
    except Exception:
        return False


def find_assembly_title(dao: Dao) -> Optional[str]:
    """遍历所有打开文档, 返回第一个 SLDASM (装配体) 标题."""
    import win32com.client.dynamic as _d
    app = _dyn_app(dao)
    try:
        doc = app.GetFirstDocument
        guard = 0
        while doc is not None and guard < 60:
            guard += 1
            try:
                title = str(doc.GetTitle)
                dtype = int(doc.GetType)
                # swDocASSEMBLY = 2
                if dtype == 2 or title.lower().endswith(".sldasm"):
                    return title
            except Exception:
                pass
            try:
                doc = doc.GetNext
            except Exception:
                break
    except Exception:
        pass
    return None


def close_non_assembly_docs(dao: Dao, keep_title: str) -> int:
    """关闭除指定装配体之外的所有打开文档, 让装配体成为唯一 active doc."""
    app = _dyn_app(dao)
    # 收集所有打开文档的标题
    titles: List[str] = []
    try:
        doc = app.GetFirstDocument
        guard = 0
        while doc is not None and guard < 60:
            guard += 1
            try:
                titles.append(str(doc.GetTitle))
            except Exception:
                pass
            try:
                doc = doc.GetNext
            except Exception:
                break
    except Exception:
        pass
    # 去重保序
    uniq, seen = [], set()
    for t in titles:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)

    closed = 0
    for t in uniq:
        if t == keep_title:
            continue
        try:
            app.CloseDoc(t)
            closed += 1
            print(f"  closed: {t}")
        except Exception as e:
            print(f"  close({t}) failed: {e}")
    time.sleep(0.8)
    return closed


def rebind_dao_to_assembly(dao: Dao) -> bool:
    """让 Dao 重新绑定当前活动文档为装配体."""
    try:
        active = dao.sw.ActiveDoc
        if active is not None:
            dao._doc_raw = active._ole if hasattr(active, "_ole") else active
            from 道_直连_底层 import DaoDispatch
            dao.doc = DaoDispatch(dao._doc_raw, "IModelDoc2", dao.mt, dao)
            try:
                asm_raw = dao.doc.cast("IAssemblyDoc")
                dao.asm = asm_raw
            except Exception:
                pass
            dao._comp_map_cache = None
            return True
    except Exception as e:
        print(f"  rebind err: {e}")
    return False


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    print("═══ 道·完善·补救 · 道并行而不相悖 ═══")
    print("═══ 柔弱胜刚强 · 大巧若拙 ═══\n")

    t0 = time.time()
    dao = Dao().connect()
    report: Dict[str, Any] = {"phases": {}}

    # Phase 0: 定位 SLDASM 并切回 (当前 doc 可能是 SLDPRT 残留)
    asm_title = find_assembly_title(dao)
    cur_title = _safe(lambda: str(dao.doc.GetTitle()), "")
    print(f"  Current doc: {cur_title}")
    print(f"  Assembly:    {asm_title}")
    if asm_title and cur_title != asm_title:
        activate_assembly(dao, asm_title)
        time.sleep(0.8)
        rebind_dao_to_assembly(dao)
        cur_title = _safe(lambda: str(dao.doc.GetTitle()), "")
        print(f"  Rebound to:  {cur_title}")
    elif not asm_title:
        print("  ✗ 未找到打开的装配体!")
        return

    # Phase 1: STEP → SLDPRT 转换 (motor_mount + v_belt)
    print(f"\n{'━'*60}\n  Phase: 1_step_to_sldprt\n{'━'*60}")
    unique_bases = sorted({b for b, _ in NEEDED})
    conv_results = {}
    for base in unique_bases:
        step = OUT_CQ / f"{base}.step"
        out = STAGE / f"{base}.SLDPRT"
        print(f"\n── {base} ──")
        ok = step_to_sldprt(dao, step, out)
        conv_results[base] = {"ok": ok, "path": str(out)}

    all_converted = all(r["ok"] for r in conv_results.values())
    report["phases"]["1_step_to_sldprt"] = {
        "ok": all_converted, "results": conv_results,
    }

    if not all_converted:
        print(f"\n✗ 转换有失败, 终止")
        with REPORT.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        return

    # Phase 2: 关闭非装配体文档 + 重新绑定 (最稳路径)
    print(f"\n{'━'*60}\n  Phase: 2_activate_assembly\n{'━'*60}")
    closed = close_non_assembly_docs(dao, asm_title)
    print(f"  关闭 {closed} 非装配文档")
    time.sleep(0.8)
    rebind_dao_to_assembly(dao)
    cur_title2 = _safe(lambda: str(dao.doc.GetTitle()), "")
    act_ok = (cur_title2 == asm_title) and (dao.asm is not None)
    print(f"  现活 doc: {cur_title2} · asm 绑定: {'✓' if dao.asm else '✗'}")
    report["phases"]["2_activate_assembly"] = {
        "ok": act_ok, "title": asm_title,
        "current_after": cur_title2, "closed_docs": closed,
    }
    print(f"  切回 {asm_title}: {'✓' if act_ok else '✗'}")

    # Phase 3: 插入 motor_mount + v_belt×4 (按 NEEDED 顺序)
    print(f"\n{'━'*60}\n  Phase: 3_insert\n{'━'*60}")
    inserted: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    for base, pos in NEEDED:
        staged_sldprt = STAGE / f"{base}.SLDPRT"
        new_name = add_one(dao, staged_sldprt, asm_title)
        if new_name:
            # 插入成功 · 重新 rebind 以防 preload 切换了 active
            rebind_dao_to_assembly(dao)
            inserted.append({"base": base, "name": new_name, "target": pos})
            print(f"  ✓ {base} → {new_name}")
        else:
            failed.append({"base": base, "target": pos})
            print(f"  ✗ {base} 插入失败")
        time.sleep(0.4)

    report["phases"]["3_insert"] = {
        "ok": len(failed) == 0,
        "inserted": inserted, "failed": failed,
    }

    dao.rebuild(force=True)
    time.sleep(0.5)

    # Phase 4: 定位
    print(f"\n{'━'*60}\n  Phase: 4_position\n{'━'*60}")
    pos_results = []
    for item in inserted:
        name = item["name"]
        pos = item["target"]
        tx, ty, tz = float(pos["tx"]), float(pos["ty"]), float(pos["tz"])
        rv = pos.get("rv")
        ra = float(pos.get("ra") or 0)
        if rv and ra:
            R, t_mm = intent_to_rt("origin", (tx, ty, tz), rv, ra)
            rot_flat = tuple(R[r][c] for c in range(3) for r in range(3))
        else:
            rot_flat = None
            t_mm = (tx, ty, tz)
        ok = dao.transform.set(name, t_mm, rot=rot_flat)
        actual = dao.transform.origin_mm(name)
        flag = "✓" if ok else "✗"
        actual_str = (f"({actual[0]:+.0f},{actual[1]:+.0f},{actual[2]:+.0f})"
                      if actual else "?")
        print(f"  {flag} {name:20s} → ({tx:+.0f},{ty:+.0f},{tz:+.0f}) actual={actual_str}")
        pos_results.append({"name": name, "ok": bool(ok),
                            "target": t_mm, "actual": list(actual) if actual else None})
    dao.rebuild(force=True)
    time.sleep(0.3)
    report["phases"]["4_position"] = {
        "ok": all(r["ok"] for r in pos_results),
        "results": pos_results,
    }

    # Phase 5: 固定
    print(f"\n{'━'*60}\n  Phase: 5_fix\n{'━'*60}")
    fixed = 0
    for item in inserted:
        name = item["name"]
        try:
            if not dao.comp.is_fixed(name):
                if dao.comp.fix(name):
                    fixed += 1
        except Exception:
            pass
    dao.rebuild(force=True)
    time.sleep(0.3)
    print(f"  固定: {fixed}/{len(inserted)}")
    report["phases"]["5_fix"] = {"ok": fixed == len(inserted), "fixed": fixed}

    # Phase 6: 保存 + 渲染
    print(f"\n{'━'*60}\n  Phase: 6_save_render\n{'━'*60}")
    sr = dao.save()
    print(f"  Save: ok={sr.get('ok')} err={sr.get('errors',0)} warn={sr.get('warnings',0)}")
    captured = []
    views = {"iso": 7, "front": 1, "back": 2, "top": 5, "right": 3, "left": 4}
    for label, vid in views.items():
        try:
            dao.doc.ShowNamedView2(label.capitalize(), vid)
            dao.doc.ViewZoomtofit2()
            time.sleep(0.2)
            bmp = str(OUT / f"完善2_{label}.bmp")
            dao.doc.SaveBMP(bmp, 1920, 1080)
            captured.append(label)
            print(f"  {label} → 完善2_{label}.bmp")
        except Exception as e:
            print(f"  {label} ✗ {e}")
    report["phases"]["6_save_render"] = {
        "ok": bool(sr.get("ok")), "captured": captured,
    }

    # 汇总
    total = round(time.time() - t0, 2)
    n_ok = sum(1 for v in report["phases"].values() if v.get("ok"))
    n_total = len(report["phases"])
    print(f"\n{'═'*60}")
    print(f"  ═══ 补救汇总 ═══")
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
