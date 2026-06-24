#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
_dao_清理_固定.py — 道法自然 · 除幽灵 · 固真实

"故有之以为利, 无之以为用."
"生而不有, 为而不恃, 长而不宰, 是谓玄德."

五段终章:
  ① 诊 · 盘点所有组件并识别幽灵 (未被正确定位的重复件)
  ② 除 · 删除 motor_mount-2, v_belt-5, v_belt-6, v_belt-7, v_belt-8
  ③ 固 · 锚定所有真实件 · 防位移
  ④ 存 · 保存 + 多视角渲染
  ⑤ 报 · 产 清理_固定_报告.json
"""
from __future__ import annotations
import sys, time, json
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机"))

from 道_直连_底层 import Dao, _safe, _nothing  # noqa
import 道_直连_底层_facets  # noqa

OUT = HERE / "_产物输出"
OUT.mkdir(exist_ok=True)
REPORT = OUT / "清理_固定_报告.json"

# 幽灵清单 (从诊断 bbox 识别: 在原点附近 · 未定位)
GHOSTS = [
    "motor_mount-2",
    "v_belt-5", "v_belt-6", "v_belt-7", "v_belt-8",
]


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
        try:
            doc = doc.GetNext
        except:
            break
    return None


def close_non_assembly_docs(dao, keep_title):
    app = _dyn_app(dao)
    titles, doc, g = [], app.GetFirstDocument, 0
    while doc is not None and g < 60:
        g += 1
        try: titles.append(str(doc.GetTitle))
        except: pass
        try: doc = doc.GetNext
        except: break
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
        except: pass
    time.sleep(0.5)
    return closed


def rebind(dao):
    try:
        active = dao.sw.ActiveDoc
        if active is not None:
            dao._doc_raw = active._ole if hasattr(active, "_ole") else active
            from 道_直连_底层 import DaoDispatch
            dao.doc = DaoDispatch(dao._doc_raw, "IModelDoc2", dao.mt, dao)
            try:
                dao.asm = dao.doc.cast("IAssemblyDoc")
            except: pass
            dao._comp_map_cache = None
            return True
    except: pass
    return False


def main():
    print("═══ 道·清理·固定 · 除幽灵 · 固真实 ═══\n")
    t0 = time.time()
    dao = Dao().connect()
    report = {"phases": {}}

    # Phase 0: 找装配体 · 切回 · 关掉其它 · rebind
    asm_doc = get_assembly_doc(dao)
    if asm_doc is None:
        print("✗ 无装配体"); return
    asm_title = str(asm_doc.GetTitle)
    print(f"Assembly: {asm_title}")

    cur = _safe(lambda: str(dao.doc.GetTitle()), "")
    if cur != asm_title:
        closed = close_non_assembly_docs(dao, asm_title)
        print(f"关闭 {closed} 非装配文档")
        time.sleep(0.5)
        rebind(dao)

    # Phase 1: 盘点
    print(f"\n{'━'*60}\n  Phase: 1_audit\n{'━'*60}")
    cmap = dao.build_comp_map(force=True)
    total = len(cmap)
    ghosts_present = [g for g in GHOSTS if g in cmap]
    print(f"  总组件: {total}")
    print(f"  幽灵待除: {len(ghosts_present)} / {len(GHOSTS)}  · {ghosts_present}")
    report["phases"]["1_audit"] = {
        "ok": True, "total": total,
        "ghosts_present": ghosts_present,
    }

    # Phase 2: 删幽灵 (用 IComponent2.Select4 直接选中 + DeleteSelection2)
    print(f"\n{'━'*60}\n  Phase: 2_exorcise\n{'━'*60}")
    if ghosts_present:
        # 解锁幽灵 (固定状态下可能删不掉)
        for name in ghosts_present:
            try:
                if dao.comp.is_fixed(name):
                    dao.comp.unfix(name)
            except: pass
        time.sleep(0.3)

        # 用 IComponent2.Select4 直接选 · 不走 SelectByID2 的名字解析
        ext = asm_doc.Extension
        try:
            asm_doc.ClearSelection2(True)
        except: pass
        selected = 0
        comps = asm_doc.GetComponents(False) or []
        ghost_set = set(ghosts_present)
        for c in comps:
            try:
                nm = str(c.Name2)
                if nm not in ghost_set:
                    continue
                # IComponent2.Select(Append) 最简版 · 兼容性最好
                ok = False
                try:
                    ok = bool(c.Select(True))
                except Exception:
                    # 尝试 SelectByID2 按组件名
                    try:
                        ok = bool(ext.SelectByID2(
                            nm, "COMPONENT", 0.0, 0.0, 0.0,
                            True, 0, _nothing(), 0))
                    except Exception:
                        pass
                if ok:
                    selected += 1
                    print(f"  ✓ 选中: {nm}")
                else:
                    print(f"  ✗ 选择失败: {nm}")
            except Exception as e:
                print(f"  ✗ 遍历异常 {e}")

        deleted = 0
        if selected > 0:
            try:
                ok_del = ext.DeleteSelection2(18)
                print(f"  DeleteSelection2: {ok_del}")
                if ok_del:
                    deleted = selected
            except Exception as e:
                print(f"  删异常: {e}")
            asm_doc.ClearSelection2(True)

        dao.rebuild(force=True)
        time.sleep(0.5)
        dao._comp_map_cache = None
        cmap2 = dao.build_comp_map(force=True)
        survivors = [n for n in ghosts_present if n in cmap2]

        print(f"  已选: {selected} · 已删: {deleted} · 残留: {len(survivors)}")
        if survivors:
            print(f"  残留名: {survivors}")
        report["phases"]["2_exorcise"] = {
            "ok": not survivors,
            "selected": selected,
            "deleted": deleted,
            "survivors": survivors,
        }
    else:
        print("  无幽灵, 跳过")
        report["phases"]["2_exorcise"] = {"ok": True, "deleted": 0}

    # Phase 3: 固全部
    print(f"\n{'━'*60}\n  Phase: 3_fix_all\n{'━'*60}")
    cmap3 = dao.build_comp_map(force=True)
    to_fix = [n for n in cmap3 if not dao.comp.is_fixed(n)]
    print(f"  待固: {len(to_fix)} / {len(cmap3)}")
    fixed = 0
    for n in to_fix:
        try:
            if dao.comp.fix(n):
                fixed += 1
        except Exception as e:
            print(f"    ✗ fix {n}: {e}")
    dao.rebuild(force=True)
    time.sleep(0.3)
    # 验证
    cmap4 = dao.build_comp_map(force=True)
    still_free = [n for n in cmap4 if not dao.comp.is_fixed(n)]
    print(f"  已固: {fixed} · 仍自由: {len(still_free)}")
    if still_free:
        print(f"  自由组件: {still_free[:10]}...")
    report["phases"]["3_fix_all"] = {
        "ok": len(still_free) == 0,
        "fixed": fixed,
        "still_free": still_free,
    }

    # Phase 4: 保存 + 渲染
    print(f"\n{'━'*60}\n  Phase: 4_save_render\n{'━'*60}")
    sr = dao.save()
    print(f"  Save: ok={sr.get('ok')}")
    captured = []
    views = {"iso": 7, "front": 1, "back": 2, "top": 5, "right": 3, "left": 4}
    for label, vid in views.items():
        try:
            dao.doc.ShowNamedView2(label.capitalize(), vid)
            dao.doc.ViewZoomtofit2()
            time.sleep(0.2)
            bmp = str(OUT / f"清理_{label}.bmp")
            dao.doc.SaveBMP(bmp, 1920, 1080)
            captured.append(label)
            print(f"  {label} ✓")
        except Exception as e:
            print(f"  {label} ✗ {e}")
    report["phases"]["4_save_render"] = {
        "ok": sr.get("ok") and len(captured) == 6,
        "captured": captured,
    }

    # 汇总
    total_t = round(time.time() - t0, 2)
    n_ok = sum(1 for v in report["phases"].values() if v.get("ok"))
    n_total = len(report["phases"])
    print(f"\n{'═'*60}")
    print(f"  ═══ 清理·固定 汇总 ═══")
    print(f"  阶段: {n_total} · 成功: {n_ok} · 耗时: {total_t}s")
    for name, r in report["phases"].items():
        flag = "✓" if r.get("ok") else "✗"
        print(f"    {flag} {name}")
    print(f"{'═'*60}")

    report["summary"] = {"total": n_total, "ok": n_ok, "elapsed_s": total_t}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                      encoding="utf-8")
    print(f"\n  → {REPORT.name}")


if __name__ == "__main__":
    main()
