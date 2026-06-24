#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_dao_产物.py — 道直连器 · 实操终章 · 输出活体装配所有产物

"既以为人己愈有, 既以与人己愈多."

全程纯 memid 直调 sldworks.tlb · 无 Builder/Bridge 中间层 · 证直连器可驾驭 SW 全域.

产物:
  ① BOM.csv           — 按 comp 名/Part 路径/数量
  ② health_report.md  — 每 mate rebuild 状态 · feature tree 摘要
  ③ iso.png / ...     — 4 视图渲染 (isometric / front / right / top)
  ④ skeleton.png      — 隐藏 casing_upper 后 "内脏" 可视
  ⑤ summary.json      — 结构化汇总
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from 道_直连_底层 import Dao, DaoDispatch, _safe


OUT_DIR = Path(__file__).resolve().parent / "_产物输出"
OUT_DIR.mkdir(exist_ok=True)


# ════════════════════════════════════════════════════════════════════════
# ① BOM
# ════════════════════════════════════════════════════════════════════════
def export_bom(dao: Dao) -> Path:
    """从 Components 构建 BOM · 按 Part 路径去重 · 统计数量."""
    cmap = dao.build_comp_map()
    by_part: Dict[str, Dict[str, Any]] = {}
    for name, comp in cmap.items():
        path = _safe(lambda c=comp: str(c.GetPathName()), "")
        part = Path(path).name if path else "(unknown)"
        suppressed = dao.comp.is_suppressed(name)
        key = part
        if key not in by_part:
            by_part[key] = {
                "part": part,
                "path": path,
                "qty": 0,
                "suppressed": 0,
                "instances": [],
            }
        by_part[key]["qty"] += 1
        if suppressed:
            by_part[key]["suppressed"] += 1
        by_part[key]["instances"].append(name)

    csv_path = OUT_DIR / "BOM.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["#", "Part", "Qty", "Active", "Suppressed",
                    "Instances", "Path"])
        rows = sorted(by_part.values(), key=lambda x: (-x["qty"], x["part"]))
        for i, r in enumerate(rows, 1):
            w.writerow([
                i,
                r["part"],
                r["qty"],
                r["qty"] - r["suppressed"],
                r["suppressed"],
                " / ".join(r["instances"]),
                r["path"],
            ])
    return csv_path


# ════════════════════════════════════════════════════════════════════════
# ② health report
# ════════════════════════════════════════════════════════════════════════
def export_health(dao: Dao) -> Dict[str, Any]:
    """装配健康度 · rebuild + 每 mate error_status + feature count."""
    result: Dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "doc_title": _safe(lambda: str(dao.doc.GetTitle())),
    }
    # 强制 rebuild
    try:
        ok = dao.doc.ForceRebuild3(False)
        result["rebuild"] = {"ok": bool(ok)}
    except Exception as e:
        result["rebuild"] = {"ok": False, "error": str(e)}

    # mate 状态
    mates = dao.mate.list_all()
    err_mates = [m for m in mates if m.get("error_status", -1) > 0]
    result["mates"] = {
        "total": len(mates),
        "by_type": {},
        "error_mates": err_mates,
    }
    for m in mates:
        tn = m.get("type_name", "?")
        result["mates"]["by_type"][tn] = \
            result["mates"]["by_type"].get(tn, 0) + 1

    # feature tree
    counts: Dict[str, int] = {}
    feat = dao.asm.FirstFeature() if dao.asm else None
    n = 0
    while feat and n < 5000:
        n += 1
        f = feat.cast("IFeature")
        tn = _safe(lambda fx=f: str(fx.GetTypeName2()), "?")
        counts[tn] = counts.get(tn, 0) + 1
        try:
            feat = feat.GetNextFeature()
        except Exception:
            break
    result["feature_tree"] = counts
    result["feature_total"] = n

    # 组件状态
    cmap = dao.build_comp_map()
    result["components"] = {
        "total": len(cmap),
        "fixed": sum(1 for n in cmap if dao.comp.is_fixed(n)),
        "suppressed": sum(1 for n in cmap if dao.comp.is_suppressed(n)),
    }

    # 写 MD
    md_path = OUT_DIR / "health_report.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write(f"# 装配健康报告 · {result['ts']}\n\n")
        f.write(f"- **Doc**: `{result['doc_title']}`\n")
        rb = result["rebuild"]
        f.write(f"- **Rebuild**: {'✓ OK' if rb.get('ok') else '✗ ' + rb.get('error', '?')}\n")
        f.write(f"- **Features**: {result['feature_total']}\n\n")
        f.write("## 组件\n\n")
        c = result["components"]
        f.write(f"- 总计: {c['total']}\n")
        f.write(f"- fixed: {c['fixed']}\n")
        f.write(f"- suppressed: {c['suppressed']}\n")
        f.write(f"- free: {c['total'] - c['fixed'] - c['suppressed']}\n\n")
        f.write("## Mates\n\n")
        m = result["mates"]
        f.write(f"- 总计: {m['total']}\n")
        for tn, ct in sorted(m["by_type"].items(), key=lambda x: -x[1]):
            f.write(f"  - {tn}: {ct}\n")
        if m["error_mates"]:
            f.write(f"\n### ⚠ 错误 Mate ({len(m['error_mates'])})\n\n")
            for em in m["error_mates"]:
                f.write(f"  - `{em.get('name')}` err={em.get('error_status')}\n")
        else:
            f.write("\n✓ 所有 mate 无错误\n")
        f.write("\n## 特征树\n\n")
        for tn, ct in sorted(result["feature_tree"].items(),
                              key=lambda x: -x[1])[:20]:
            f.write(f"- {tn}: {ct}\n")

    return result


# ════════════════════════════════════════════════════════════════════════
# ③ 视图渲染 (4 views · PNG)
# ════════════════════════════════════════════════════════════════════════
def render_views(dao: Dao) -> List[Path]:
    """用 ISldWorks.RunCommand + ModelView.SaveAsImage 出 4 视图."""
    out: List[Path] = []

    # SW 标准视图 enum (swStandardViews_e): isometric=7, front=1,
    # back=2, left=3, right=4, top=5, bottom=6
    views = {"iso": 7, "front": 1, "top": 5, "right": 4}

    for vname, vid in views.items():
        try:
            # 1) 切视图 · IModelDocExtension.ViewOrientation3
            #    或 ModelDoc2.ShowNamedView2
            dao.doc.ShowNamedView2("", vid)
            # 2) ViewZoomToFit2
            dao.doc.ViewZoomtofit2()
            time.sleep(0.3)
            # 3) SaveBMP (简单位图 · w, h)
            png_path = OUT_DIR / f"view_{vname}.bmp"
            try:
                dao.doc.SaveBMP(str(png_path), 1600, 1000)
                out.append(png_path)
                print(f"    ✓ {vname} → {png_path.name}")
            except Exception as e:
                print(f"    ✗ {vname}: SaveBMP 失败 {e}")
        except Exception as e:
            print(f"    ✗ {vname} 渲染失败: {e}")

    return out


# ════════════════════════════════════════════════════════════════════════
# ④ "内脏" 图 — 隐藏 casing · 露出 shaft/hammer/disc
# ════════════════════════════════════════════════════════════════════════
def _select_comp(dao: Dao, name: str, append: bool = False) -> bool:
    """facet select.by_id · 返 True 若选择生效 (通过 sel count 验证)."""
    try:
        comp = dao.comp[name]
        full_name = _safe(lambda: str(comp.Name2), name)
        if callable(full_name):
            full_name = _safe(lambda: str(full_name()), name)
        before = _safe(
            lambda: int(dao.sel.GetSelectedObjectCount2(-1)), -1)
        dao.select.by_id(full_name, "COMPONENT", append=append)
        after = _safe(
            lambda: int(dao.sel.GetSelectedObjectCount2(-1)), -1)
        return after > before
    except Exception as e:
        print(f"    select {name}: {e}")
        return False


def _batch_hide(dao: Dao, names: List[str]) -> List[str]:
    """批量隐 · IAssemblyDoc.HideComponent() 对选中集生效."""
    dao.doc.ClearSelection2(True)
    hidden: List[str] = []
    for i, name in enumerate(names):
        if _select_comp(dao, name, append=(i > 0)):
            hidden.append(name)
    if hidden and dao.asm is not None:
        try:
            dao.asm.HideComponent()
            time.sleep(0.2)
            print(f"    已隐藏 {len(hidden)} 件")
        except Exception as e:
            print(f"    HideComponent: {e}")
    dao.doc.ClearSelection2(True)
    return hidden


def _batch_show(dao: Dao, names: List[str]):
    """批量恢复 · IAssemblyDoc.ShowComponent()."""
    if not names:
        return
    dao.doc.ClearSelection2(True)
    selected: List[str] = []
    for i, name in enumerate(names):
        if _select_comp(dao, name, append=(i > 0)):
            selected.append(name)
    if selected and dao.asm is not None:
        try:
            dao.asm.ShowComponent()
            time.sleep(0.2)
            print(f"    已恢复 {len(selected)} 件")
        except Exception as e:
            print(f"    ShowComponent: {e}")
    dao.doc.ClearSelection2(True)


def render_skeleton(dao: Dao) -> Path:
    """临时隐藏 casing + frame · 渲染 iso."""
    targets = ["casing_upper-1", "casing_lower-1", "frame_base-1"]
    hidden = _batch_hide(dao, targets)
    png = Path()
    try:
        dao.doc.ShowNamedView2("", 7)
        time.sleep(0.3)
        dao.doc.ViewZoomtofit2()
        time.sleep(0.4)
        png = OUT_DIR / "skeleton_iso.bmp"
        dao.doc.SaveBMP(str(png), 1600, 1000)
        print(f"    ✓ skeleton → {png.name}")
    except Exception as e:
        print(f"    skeleton 渲染失败: {e}")
    _batch_show(dao, hidden)
    return png


def render_xray(dao: Dao) -> Path:
    """深透 · 露 shaft/hammer/disc/pin."""
    to_hide = [
        "casing_upper-1", "casing_lower-1", "frame_base-1",
        "motor_body-1", "motor_mount-1", "drive_pulley-1",
        "v_belt_dao_240x190x600_004333-1",
        "v_belt_dao_240x190x600_004333-2",
        "v_belt_dao_240x190x600_004333-3",
        "v_belt_dao_240x190x600_004333-4",
    ]
    hidden = _batch_hide(dao, to_hide)
    png = Path()
    try:
        dao.doc.ShowNamedView2("", 7)
        time.sleep(0.3)
        dao.doc.ViewZoomtofit2()
        time.sleep(0.4)
        png = OUT_DIR / "xray_iso.bmp"
        dao.doc.SaveBMP(str(png), 1600, 1000)
        print(f"    ✓ xray → {png.name}")
    except Exception as e:
        print(f"    xray 失败: {e}")
    _batch_show(dao, hidden)
    return png


def interference_detect(dao: Dao) -> Dict[str, Any]:
    """IAssemblyDoc.InterferenceDetectionManager · 全装配碰撞检测."""
    result: Dict[str, Any] = {"ok": False}
    try:
        idm = dao.asm.InterferenceDetectionManager
        # idm 是 IInterferenceDetectionMgr
        # 参数: TreatCoincidenceAsInterference=False, IncludeMultibodyPartInterferences=True,
        #       MakeInterferingPartsTransparent=False, CreateFastenersFolder=False,
        #       IgnoreHiddenComponents=True
        try:
            idm.TreatCoincidenceAsInterference = False
            idm.IncludeMultibodyPartInterferences = True
            idm.IgnoreHiddenBodies = True
        except Exception:
            pass
        # 运行
        interferences = idm.GetInterferences()
        if interferences is None:
            result["ok"] = True
            result["count"] = 0
            result["details"] = []
            print("    ✓ 无碰撞")
            return result
        # interferences 是 list of IInterference
        count = len(interferences) if hasattr(interferences, "__len__") else 0
        if count == 0:
            try:
                count = int(idm.GetInterferenceCount())
            except Exception:
                count = 0
        result["count"] = count
        details: List[Dict[str, Any]] = []
        try:
            n = int(idm.GetInterferenceCount())
        except Exception:
            n = 0
        # 用 GetInterferences() 拿数组 · 或回退 IGetInterferences
        arr = None
        try:
            arr = idm.GetInterferences()
            if callable(arr):
                arr = arr()
        except Exception as e:
            print(f"    GetInterferences 失败: {e}")
        if arr is None:
            try:
                arr = idm.IGetInterferences()
                if callable(arr):
                    arr = arr()
            except Exception:
                pass
        if arr is None:
            print("    无法取 IInterference 数组 · 仅记 count")
        else:
            # arr 可能是 tuple/list of IDispatch
            for i, inter in enumerate(list(arr)):
                try:
                    if inter is None:
                        continue
                    # 包成 DaoDispatch("IInterference")
                    if hasattr(inter, "cast"):
                        inter_c = inter.cast("IInterference")
                    else:
                        from 道_直连_底层 import DaoDispatch, _ole_of
                        inter_c = DaoDispatch(_ole_of(inter),
                                               "IInterference",
                                               dao.mt, dao)
                    vol_raw = _safe(lambda ix=inter_c: ix.Volume, None)
                    if callable(vol_raw):
                        vol_raw = _safe(lambda vr=vol_raw: vr(), None)
                    vol = float(vol_raw) if vol_raw is not None else 0.0
                    comps_raw = _safe(lambda ix=inter_c: ix.Components, None)
                    if callable(comps_raw):
                        comps_raw = _safe(lambda cx=comps_raw: cx(), None)
                    names: List[str] = []
                    if comps_raw:
                        try:
                            for c in list(comps_raw):
                                from 道_直连_底层 import DaoDispatch, _ole_of
                                cw = (c.cast("IComponent2")
                                      if hasattr(c, "cast")
                                      else DaoDispatch(_ole_of(c),
                                                       "IComponent2",
                                                       dao.mt, dao))
                                nm = _safe(lambda cx=cw: str(cx.Name2), "?")
                                if callable(nm):
                                    nm = _safe(
                                        lambda cx=cw: str(cx.Name2()), "?")
                                names.append(nm)
                        except Exception:
                            pass
                    details.append({
                        "idx": i,
                        "volume_mm3": vol * 1e9,  # m³ -> mm³
                        "components": names,
                    })
                except Exception as e:
                    details.append({"idx": i, "error": str(e)})
        result["details"] = details
        result["ok"] = True
        print(f"    ✓ 碰撞数: {n}")
        for d in details[:5]:
            if "error" in d:
                print(f"      [{d.get('idx')}] ERR: {d['error']}")
            else:
                v = d.get("volume_mm3", 0)
                print(f"      [{d.get('idx')}] vol={v:.2f}mm³  "
                      f"{d.get('components')}")
        # 关闭检测
        try:
            idm.Done()
        except Exception:
            pass
    except Exception as e:
        result["error"] = str(e)
        print(f"    碰撞检测失败: {e}")
    return result


def mass_properties(dao: Dao) -> Dict[str, Any]:
    """装配的质量属性 (体积/质量/重心)."""
    result: Dict[str, Any] = {}
    try:
        mp = dao.ext.CreateMassProperty()
        if mp is None:
            result["error"] = "CreateMassProperty 返 None"
            return result
        # mp is IMassProperty
        mass = _safe(lambda: float(mp.Mass), 0.0)
        volume = _safe(lambda: float(mp.Volume), 0.0)
        # CenterOfMass 是 array of 3 doubles (m)
        com = _safe(lambda: list(mp.CenterOfMass), [0, 0, 0])
        density = _safe(lambda: float(mp.Density), 0.0)
        surface_area = _safe(lambda: float(mp.SurfaceArea), 0.0)
        result["mass_kg"] = mass
        result["volume_mm3"] = volume * 1e9
        result["density_kg_m3"] = density
        result["surface_area_mm2"] = surface_area * 1e6
        result["center_of_mass_mm"] = [x * 1000 for x in (com or [0, 0, 0])]
        print(f"    mass={result['mass_kg']:.3f} kg  "
              f"vol={result['volume_mm3']:.1f} mm³  "
              f"CoM={result['center_of_mass_mm']}")
    except Exception as e:
        result["error"] = str(e)
        print(f"    质量属性失败: {e}")
    return result


# ════════════════════════════════════════════════════════════════════════
# 主
# ════════════════════════════════════════════════════════════════════════
def main():
    print("═══ 道直连器 · 产物输出 · 实操终章 ═══")
    dao = Dao().connect()
    print(f"  SW: {_safe(lambda: str(dao.sw.RevisionNumber()))}")
    print(f"  Doc: {_safe(lambda: str(dao.doc.GetTitle()))}")
    print(f"  输出目录: {OUT_DIR}")

    print("\n─── ① BOM 导出 ───")
    bom_path = export_bom(dao)
    print(f"  ✓ BOM → {bom_path}")

    print("\n─── ② 健康报告 ───")
    health = export_health(dao)
    print(f"  ✓ Rebuild: {health['rebuild'].get('ok')}")
    print(f"  ✓ 组件: {health['components']}")
    print(f"  ✓ Mates: {health['mates']['total']} 总 · "
          f"{len(health['mates']['error_mates'])} 错")
    print(f"  ✓ 特征: {health['feature_total']}")

    print("\n─── ③ 4 视图渲染 ───")
    views = render_views(dao)

    print("\n─── ④ 内脏渲染 (隐 casing) ───")
    skel = render_skeleton(dao)

    print("\n─── ⑤ 透视渲染 (隐 casing+motor+pulley+belt) ───")
    xray = render_xray(dao)

    print("\n─── ⑥ 碰撞检测 (InterferenceDetectionMgr) ───")
    interference = interference_detect(dao)

    print("\n─── ⑦ 质量属性 ───")
    mass = mass_properties(dao)

    print("\n─── ⑧ summary.json ───")
    summary = {
        "overview": {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sw_revision": _safe(lambda: str(dao.sw.RevisionNumber())),
            "doc_title": _safe(lambda: str(dao.doc.GetTitle())),
            "doc_path": _safe(lambda: str(dao.doc.GetPathName())),
        },
        "health": health,
        "interference": interference,
        "mass_properties": mass,
        "products": {
            "bom_csv": str(bom_path),
            "health_md": str(OUT_DIR / "health_report.md"),
            "views": [str(p) for p in views],
            "skeleton_view": str(skel) if skel.name else None,
            "xray_view": str(xray) if xray.name else None,
        },
    }
    sum_path = OUT_DIR / "summary.json"
    sum_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    print(f"  ✓ summary → {sum_path}")

    print("\n═══ 实操终 · 所有产物已出 ═══")


if __name__ == "__main__":
    main()
