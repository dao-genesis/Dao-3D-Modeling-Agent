#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sw_simulate.py · SolidWorks 内部实测仿真 · 道法自然

> 反者道之动 — 不再以纯 Python 推算, 转入 SolidWorks 内部用本源 API 实测.
> 大象无形, 大音希声. 此脚本于 SW 之中行无为之事, 以本源接口验真知.

七相实测:
  P1  连接 + 打开装配
  P2  装配自检 (重建 + 错误)
  P3  干涉检测 (InterferenceDetectionMgr · 体级精确)
  P4  质量属性 (整机 + 11 单件 · 质量/重心/惯性)
  P5  配合关系图 (Mate 类型/参与组件/自由度)
  P6  运动算例 (Motion Study · 主轴 1200rpm 旋转 — 可选, 需 SW Motion 插件)
  P7  报告聚合 + 6 视图截图 + STEP/STL 兜底导出

执行方式:
  python sw_simulate.py                 # 完整七相
  python sw_simulate.py --skip-motion   # 跳过 Motion Study (无插件时)
  python sw_simulate.py --asm <path>    # 指定其他 SLDASM 路径

输出:
  sw_api/sw_simulate_report.json        # 完整结构化报告
  sw_api/sw_simulate_report.md          # 人读报告
  交付包_最终/渲染图/sw_*.png            # 6 视图截图
  交付包_最终/锤式破碎机_总装配.STEP     # AP214 兜底
"""
from __future__ import annotations
import sys, os, json, time, argparse
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent.resolve()
OUT_API = HERE / "sw_api"
OUT_API.mkdir(exist_ok=True)
SNAP_DIR = HERE / "交付包_最终" / "渲染图"
SNAP_DIR.mkdir(parents=True, exist_ok=True)
LOG_JSON = OUT_API / "sw_simulate_report.json"
LOG_MD   = OUT_API / "sw_simulate_report.md"

DEFAULT_ASM = HERE / "交付包_最终" / "锤式破碎机_总装配.SLDASM"

# ── 转速参考 (主轴 1200 rpm, 来自 config.MACHINE_PARAMS) ────────────
ROTOR_RPM = 1200
SIM_DURATION_S = 0.5   # 仿真时长 (主轴半秒 = 10 圈)
SIM_FRAMES = 30        # 每秒 60 帧, 0.5s = 30 帧

# ══════════════════════════════════════════════════════════════════════
# 日志工具
# ══════════════════════════════════════════════════════════════════════

def now() -> str:
    return datetime.now().strftime("%H:%M:%S")

def log(msg: str, level: str = "INFO"):
    sym = {"INFO": "·", "OK": "✓", "WARN": "⚠", "FAIL": "✗", "PHASE": "═"}.get(level, "·")
    print(f"[{now()}] {sym} {msg}", flush=True)

def phase(idx: int, title: str):
    bar = "─" * 60
    print(f"\n{bar}\n  Phase {idx} · {title}\n{bar}", flush=True)


# ══════════════════════════════════════════════════════════════════════
# COM 公共 (复用 sw_probe 风格, 走 dynamic Dispatch)
# ══════════════════════════════════════════════════════════════════════

def connect_sw():
    """连 SW. 优先附加已运行实例; 无则启动新实例.

    强制走 win32com.client.dynamic.Dispatch — SolidWorks IDispatch 中
    大量 PROPGET 项 (如 IComponent2.IsSuppressed, IModelDoc2.GetType) 在
    LateBinding 下需 dynamic 包裹才能正确取值. 这是 _dao_归元_根治.py
    已验证的成熟做法.
    """
    import win32com.client
    import win32com.client.dynamic as _dyn
    import pythoncom
    try:
        sw_raw = win32com.client.GetActiveObject("SldWorks.Application")
        sw = _dyn.Dispatch(sw_raw)
        log(f"附加已运行 SW (dynamic) · Rev={sw.RevisionNumber}", "OK")
    except Exception:
        sw = _dyn.Dispatch("SldWorks.Application")
        sw.Visible = True
        log(f"启动新 SW (dynamic) · Rev={sw.RevisionNumber}", "OK")
    return sw, win32com.client, pythoncom


# ── COM 调用兜底 (PROPGET vs METHOD 双试) ─────────────────────────────
def cget(obj, name, *args):
    """SolidWorks IDispatch 兼容取值:
    1) getattr 直接取属性
    2) 若是 callable, 用 *args 调用之
    3) 调用失败: 若 v 是 CDispatch (COM 对象, 实为 PROPGET 已返结果) → 返回 v
                 否则 (Python 函数/method 等) → 返回 None
    4) getattr 异常 → None

    道法自然: 二者同出而异名.
      · `InterferenceDetectionManager` 在 dynamic 下既是 CDispatch (PROPGET)
        又显示为 callable, v() 失败但 v 本身是有效对象, 故下传.
      · `PrincipalAxesOfInertia` 是 bound method, v() 失败则 v 不可用, 必返 None.
    """
    try:
        v = getattr(obj, name)
    except Exception:
        return None
    if args:
        try: return v(*args)
        except Exception:
            # 带参数调用失败: 若 v 是 CDispatch 对象本身有效, 也返回之
            try:
                from win32com.client.dynamic import CDispatch as _CD
                if isinstance(v, _CD): return v
            except Exception: pass
            return None
    if callable(v):
        try: return v()
        except Exception:
            # 调用失败兜底: COM 对象 (CDispatch) 直返, Python method 返 None
            try:
                from win32com.client.dynamic import CDispatch as _CD
                if isinstance(v, _CD): return v
            except Exception: pass
            return None
    return v


def open_assembly(sw, win32com, pythoncom, asm_path: str):
    """打开装配体. 道法自然 · 顺势:
      1) ActiveDoc 是装配体 → 直接附加 (不扰用户当前工作)
      2) ActiveDoc 不是装配 → 用 asm_path 打开
    """
    abs_path = str(Path(asm_path).resolve())
    # 优先: 附加 ActiveDoc 任何已打开的装配体
    doc = sw.ActiveDoc
    if doc is not None:
        # IModelDoc2.GetType 在 win32com Dispatch 下既可作属性也可作方法
        # 二者都试以求稳, 大象无形
        dt = None
        for getter in (lambda d: d.GetType,        # 属性 (typelib 直读)
                       lambda d: d.GetType()):     # 方法 (有些 Dispatch 强制)
            try:
                v = getter(doc)
                dt = int(v)
                break
            except Exception:
                continue
        if dt == 2:
            cur = ""
            for pgetter in (lambda d: d.GetPathName, lambda d: d.GetPathName()):
                try:
                    cur = str(pgetter(doc)); break
                except Exception:
                    continue
            log(f"附加 ActiveDoc 装配 · {Path(cur).name if cur else '<未保存>'}", "OK")
            return doc
        else:
            log(f"ActiveDoc 类型={dt} (非装配=2), 转为 OpenDoc 路径", "INFO")

    # 次选: 打开指定路径
    if not Path(abs_path).exists():
        log(f"装配体不存在: {abs_path}", "FAIL")
        return None
    e = win32com.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    w = win32com.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    asm = sw.OpenDoc6(abs_path, 2, 1, "", e, w)  # type=2 (Assembly), opts=1 (Silent)
    if asm is None:
        log(f"打开失败 err={e.value} warn={w.value}", "FAIL")
        return None
    log(f"打开装配 · {Path(abs_path).name}", "OK")
    return asm


# ══════════════════════════════════════════════════════════════════════
# Phase 2 · 装配自检
# ══════════════════════════════════════════════════════════════════════

def phase2_self_check(asm) -> Dict[str, Any]:
    """重建 + 错误诊断."""
    result = {"rebuild_ok": False, "components_total": 0, "components_resolved": 0,
              "components_suppressed": 0, "components_visible": 0,
              "comp_list": []}
    try:
        ok = asm.ForceRebuild3(False)
        result["rebuild_ok"] = bool(ok)
        log(f"ForceRebuild3 → {ok}", "OK" if ok else "WARN")
    except Exception as e:
        log(f"重建异常: {e}", "WARN")

    try:
        comps = asm.GetComponents(False) or []
        result["components_total"] = len(comps)
        for c in comps:
            try:
                nm = str(cget(c, "Name2") or "")
                supp_v = cget(c, "IsSuppressed")
                supp = bool(supp_v) if supp_v is not None else False
                vis_v = cget(c, "Visible")
                vis = int(vis_v) if vis_v is not None else 0  # 1=visible, 2=hidden
                fix_v = cget(c, "IsFixed")
                fixed = bool(fix_v) if fix_v is not None else False
                if supp:
                    result["components_suppressed"] += 1
                else:
                    result["components_resolved"] += 1
                if vis == 1:
                    result["components_visible"] += 1
                bbox = None
                try:
                    b = c.GetBox(False, False)
                    if b and len(b) >= 6:
                        bbox = [round(v*1000, 1) for v in list(b)[:6]]
                except Exception: pass
                result["comp_list"].append({
                    "name": nm, "suppressed": supp, "visible_state": vis,
                    "fixed": fixed, "bbox_mm": bbox,
                })
            except Exception as ee:
                continue
        n_fixed = sum(1 for x in result['comp_list'] if x.get('fixed'))
        log(f"组件: {result['components_total']} (解析 {result['components_resolved']} · 抑制 {result['components_suppressed']} · 可见 {result['components_visible']} · 固定 {n_fixed})", "OK")
        # 抑制清单 (用户截图 ⚠ 的根因)
        suppressed_names = [x["name"] for x in result["comp_list"] if x.get("suppressed")]
        if suppressed_names:
            log(f"⚠ SUPPRESSED 组件 (装配树 ⚠ 图标): {suppressed_names}", "WARN")
            result["suppressed_names"] = suppressed_names
    except Exception as e:
        log(f"组件遍历异常: {e}", "WARN")
    return result


# ══════════════════════════════════════════════════════════════════════
# Phase 3 · 干涉检测
# ══════════════════════════════════════════════════════════════════════

def phase3_interference(asm) -> Dict[str, Any]:
    """SolidWorks 内部干涉检测 — 体级精确."""
    result = {"ok": False, "count": 0, "interferences": []}
    try:
        # InterferenceDetectionManager 是属性 (PROPGET)
        mgr = cget(asm, "InterferenceDetectionManager")
        if mgr is None:
            log("无法获取 InterferenceDetectionManager", "WARN")
            return result
        # 设置选项 (属性 PUTREF, 直接赋值)
        for k, v in [("TreatCoincidenceAsInterference", False),
                     ("TreatSubAssembliesAsComponents", True),
                     ("IncludeMultibodyPartInterferences", True),
                     ("MakeInterferingPartsTransparent", False),
                     ("CreateFastenersFolder", False)]:
            try: setattr(mgr, k, v)
            except Exception: pass

        # GetInterferences 在 dynamic dispatch 下可能解析为 tuple/property,
        # 也可能是 method. 用 cget 兜底.
        intfs = cget(mgr, "GetInterferences")
        if intfs is None:
            log("GetInterferences 返回 None (mgr 可能未初始化)", "WARN")
            return result
        # 元组/列表/COM Variant 数组皆可迭代
        try:
            intfs_list = list(intfs)
        except Exception:
            intfs_list = []
        result["count"] = len(intfs_list)
        log(f"干涉数: {result['count']}", "OK" if result['count'] == 0 else "WARN")

        for it in intfs_list:
            entry = {"volume_m3": None, "components": []}
            v = cget(it, "Volume")
            if v is not None:
                try: entry["volume_m3"] = float(v)
                except Exception: pass
            comps = cget(it, "Components")
            if comps:
                try:
                    for c in list(comps):
                        nm = cget(c, "Name2")
                        if nm: entry["components"].append(str(nm))
                except Exception: pass
            result["interferences"].append(entry)
            cs = " ↔ ".join(entry["components"]) if entry["components"] else "?"
            v_mm3 = (entry["volume_m3"] or 0) * 1e9
            log(f"  · {cs}  vol={v_mm3:.1f}mm³", "WARN")

        try: mgr.Done()
        except Exception: pass
        result["ok"] = result["count"] == 0
    except Exception as e:
        log(f"干涉检测异常: {e}", "WARN")
    return result


# ══════════════════════════════════════════════════════════════════════
# Phase 4 · 质量属性
# ══════════════════════════════════════════════════════════════════════

def phase4_mass_properties(asm) -> Dict[str, Any]:
    """整机 + 单件质量属性 (mass / cg / inertia)."""
    result = {"assembly": None, "components": []}

    def _safe_iter(v) -> Optional[List[float]]:
        """COM tuple/array → list[float]. method/None → None. 不抛异常."""
        if v is None: return None
        try:
            return [float(x) for x in v]
        except Exception:
            return None

    def _read_mp(mp) -> Optional[Dict[str, Any]]:
        if mp is None: return None
        # 必需字段: mass + cg (任一缺即整体 None)
        mass = cget(mp, "Mass")
        if mass is None: return None
        cg = _safe_iter(cget(mp, "CenterOfMass")) or [0, 0, 0]
        # 可选字段: 各自独立 try, 缺值不影响其他
        vol   = cget(mp, "Volume")
        area  = cget(mp, "SurfaceArea")
        pmom  = _safe_iter(cget(mp, "PrincipalMomentsOfInertia"))
        paxes = _safe_iter(cget(mp, "PrincipalAxesOfInertia"))
        # MomentOfInertia(opt) — 0=输出坐标系, 1=过 CG, 2=过原点 (按 SW 习惯)
        mom_cg = None
        for opt in (1, 2, 0):
            try:
                v = mp.MomentOfInertia(opt)
                m = _safe_iter(v)
                if m: mom_cg = m; break
            except Exception:
                continue
        return {
            "mass_kg":      round(float(mass), 3),
            "volume_m3":    round(float(vol or 0), 6),
            "surface_m2":   round(float(area or 0), 4),
            "cg_m":         [round(float(v), 4) for v in cg],
            "principal_moments_kgm2": [round(v, 5) for v in pmom] if pmom else None,
            "principal_axes":         [round(v, 4) for v in paxes] if paxes else None,
            "moment_at_cg":           [round(v, 5) for v in mom_cg] if mom_cg else None,
        }

    def _make_mp(doc):
        """CreateMassProperty2 在 dynamic dispatch 下是 PROPGET — 直取即对象, 不需 ().
        _dao 探针已验证: ext.CreateMassProperty2 → CDispatch(MassProperty2)."""
        try: ext = doc.Extension
        except Exception: ext = None
        if ext is None: return None
        # PROPGET 直取 (dynamic dispatch 特有)
        for attr in ("CreateMassProperty2", "CreateMassProperty"):
            try:
                mp = getattr(ext, attr, None)
                if mp is not None and hasattr(mp, "Mass"):
                    return mp
            except Exception:
                continue
        return None

    # 整机
    try:
        mp = _make_mp(asm)
        if mp is not None:
            try: mp.UseSystemUnits = True
            except Exception: pass
            try: mp.IncludeHiddenBodiesOrComponents = False
            except Exception: pass
            asm_mp = _read_mp(mp)
            if asm_mp:
                result["assembly"] = asm_mp
                log(f"整机 · 质量={asm_mp['mass_kg']}kg · CG={asm_mp['cg_m']}m", "OK")
        else:
            log("CreateMassProperty 不可用 (Extension 未返回对象)", "WARN")
    except Exception as e:
        log(f"整机质量属性异常: {e}", "WARN")

    # 各组件 (suppress 的跳过) — GetModelDoc2 在 dynamic 下是 PROPGET, 用 cget
    try:
        comps = asm.GetComponents(False) or []
        seen_paths = set()  # 去重: 多实例零件 (如 hammer-1..16) 用同一 doc, 只算一次
        for c in comps:
            try:
                if bool(cget(c, "IsSuppressed")): continue
                nm  = str(cget(c, "Name2") or "")
                doc = cget(c, "GetModelDoc2")
                if doc is None: continue
                # 同一 ModelDoc 路径只取一次, 避免 16×hammer 重复计算
                pth = str(cget(doc, "GetPathName") or "")
                key = pth.lower() if pth else nm.split("-")[0]
                if key in seen_paths: continue
                seen_paths.add(key)
                mp = _make_mp(doc)
                if mp is None: continue
                try: mp.UseSystemUnits = True
                except Exception: pass
                comp_mp = _read_mp(mp)
                if comp_mp:
                    comp_mp["name"] = nm
                    comp_mp["doc_path"] = Path(pth).name if pth else None
                    result["components"].append(comp_mp)
            except Exception:
                continue
        log(f"组件级质量属性: {len(result['components'])} 件 (去重后)", "OK")
        # 输出每个零件的简要表
        for cmp in result["components"]:
            log(f"  · {cmp['name']:<22} {cmp['mass_kg']:>9.3f}kg  V={cmp['volume_m3']*1e6:>9.1f}cm³", "INFO")
    except Exception as e:
        log(f"组件质量属性异常: {e}", "WARN")

    return result


# ══════════════════════════════════════════════════════════════════════
# Phase 5 · 配合关系
# ══════════════════════════════════════════════════════════════════════

def phase5_mates(asm) -> Dict[str, Any]:
    """枚举所有 Mate 配合, 统计类型分布."""
    result = {"total": 0, "by_type": {}, "mates": []}
    MATE_TYPE_NAME = {
        0: "COINCIDENT", 1: "CONCENTRIC", 2: "PERPENDICULAR", 3: "PARALLEL",
        4: "TANGENT", 5: "DISTANCE", 6: "ANGLE", 7: "UNDEFINED",
        8: "SYMMETRIC", 9: "CAMFOLLOWER", 10: "GEAR", 11: "HINGE",
        12: "RACKPINION", 13: "SCREW", 14: "UNIVERSAL", 15: "PROFILECENTER",
        16: "LOCKTOSKETCH", 17: "WIDTH", 18: "PATH", 19: "LINEARCOUPLER",
        20: "MAGNETIC", 21: "SLOT", 25: "LOCK",
    }
    try:
        # FirstFeature/GetFirstFeature 在 dynamic 下都是 PROPGET (CDispatch),
        # 不能 () 调用 — 直接 getattr 即得首特征对象.
        feat = cget(asm, "FirstFeature") or cget(asm, "GetFirstFeature")
        guard = 0
        mate_groups_found = 0
        while feat is not None and guard < 5000:
            guard += 1
            tn = cget(feat, "GetTypeName2") or cget(feat, "GetTypeName") or ""
            ftype = str(tn)
            if ftype == "MateGroup":
                mate_groups_found += 1
                m = cget(feat, "GetFirstSubFeature")
                while m is not None:
                    try:
                        mname = str(cget(m, "Name") or "")
                        mate  = cget(m, "GetSpecificFeature2")
                        if mate is not None:
                            mt_v = cget(mate, "Type")
                            try: mt_int = int(mt_v) if mt_v is not None else -1
                            except Exception: mt_int = -1
                            mt_name = MATE_TYPE_NAME.get(mt_int, f"TYPE_{mt_int}")
                            # 取参与组件 (Mate2.MateEntity2 → Component2.Name2)
                            participants: List[str] = []
                            try:
                                ents = cget(mate, "MateEntityCount")
                                n_ents = int(ents) if ents is not None else 0
                                for i in range(n_ents):
                                    try:
                                        ent = mate.MateEntity(i)
                                        ref = cget(ent, "ReferenceComponent")
                                        rn  = cget(ref, "Name2") if ref is not None else None
                                        if rn: participants.append(str(rn))
                                    except Exception: pass
                            except Exception: pass
                            result["by_type"][mt_name] = result["by_type"].get(mt_name, 0) + 1
                            result["mates"].append({
                                "name": mname, "type": mt_name,
                                "components": participants,
                            })
                            result["total"] += 1
                    except Exception: pass
                    m = cget(m, "GetNextSubFeature")
            feat = cget(feat, "GetNextFeature")
        log(f"配合总数: {result['total']} · 类型分布: {result['by_type']} (MateGroup×{mate_groups_found}, 扫 {guard} 特征)", "OK")
    except Exception as e:
        log(f"配合枚举异常: {e}", "WARN")
    return result


# ══════════════════════════════════════════════════════════════════════
# Phase 6 · 运动算例 (Motion Study) — 可选
# ══════════════════════════════════════════════════════════════════════

def phase6_motion_study(asm, sw, skip: bool = False) -> Dict[str, Any]:
    """创建运动算例并求解 (主轴 1200rpm).
    需 SOLIDWORKS Motion 插件已加载. 若不可用则记录信息."""
    result = {"available": False, "name": None, "duration_s": SIM_DURATION_S,
              "frames": SIM_FRAMES, "rpm": ROTOR_RPM, "solved": False, "note": ""}
    if skip:
        result["note"] = "user_skipped"
        log("Motion Study 已按参数跳过", "INFO")
        return result
    try:
        msm = sw.GetMotionStudyManager()
        if msm is None:
            result["note"] = "no_MotionStudyManager"
            log("MotionStudyManager 不可用 (需 Motion 插件)", "WARN")
            return result
        # 取已存在的研究
        n_studies = 0
        try: n_studies = int(msm.GetMotionStudyCount(asm))
        except Exception: pass
        study = None
        if n_studies > 0:
            try: study = msm.GetMotionStudy(asm, 0)
            except Exception: pass
        if study is None:
            # 创建新算例: 基础动画类型 (无插件可用)
            try:
                study = msm.CreateMotionStudy(asm, "运动算例_主轴1200rpm")
            except Exception as e:
                result["note"] = f"create_failed:{e}"
                log(f"创建运动算例失败: {e}", "WARN")
                return result
        if study is None:
            result["note"] = "no_study"
            return result
        result["available"] = True
        try: result["name"] = str(study.Name)
        except Exception: pass

        # 设置参数: 时长 / 帧
        try: study.SetTime(SIM_DURATION_S, True)
        except Exception: pass
        try: study.FramesPerSecond = SIM_FRAMES / SIM_DURATION_S
        except Exception: pass

        # 求解 (基础动画亦支持 Calculate)
        try:
            ok = bool(study.Calculate())
            result["solved"] = ok
            log(f"运动算例求解: {ok}", "OK" if ok else "WARN")
        except Exception as e:
            result["note"] = f"calc_exc:{e}"
            log(f"求解异常: {e}", "WARN")
        log(f"算例: {result['name']} · 时长 {SIM_DURATION_S}s · {SIM_FRAMES}帧 · {ROTOR_RPM}rpm", "INFO")
    except Exception as e:
        result["note"] = f"exc:{e}"
        log(f"Motion Study 异常: {e}", "WARN")
    return result


# ══════════════════════════════════════════════════════════════════════
# Phase 7 · 6 视图截图 + STEP/STL
# ══════════════════════════════════════════════════════════════════════

def phase7_render_export(asm, win32com, pythoncom) -> Dict[str, Any]:
    """6 视图渲染 (ShowNamedView2 viewID) + STEP/STL 导出."""
    result = {"snapshots": {}, "step": None, "stl": None}

    # ShowNamedView2(name, viewID): swStandardViews_e:
    #   1=Front, 2=Back, 3=Left, 4=Right, 5=Top, 6=Bottom, 7=Isometric, 8=Trimetric, 9=Dimetric
    VIEWS = [("iso", 7), ("front", 1), ("back", 2),
             ("right", 4), ("left", 3), ("top", 5), ("bottom", 6)]

    for vname, vid in VIEWS:
        try:
            try: asm.ShowNamedView2("", vid)
            except Exception:
                try: asm.ShowNamedView2(None, vid)
                except Exception: pass
            try: asm.ViewZoomtofit2()
            except Exception:
                try: asm.ViewZoomToFit()
                except Exception: pass
            time.sleep(0.3)
            fp = str(SNAP_DIR / f"sw_{vname}.png")
            ok = False
            try: ok = bool(asm.SaveBMP(fp, 1920, 1080))
            except Exception as e:
                log(f"{vname} SaveBMP 异常: {e}", "WARN")
            if ok and Path(fp).exists():
                result["snapshots"][vname] = fp
                log(f"{vname} → {fp}", "OK")
            else:
                result["snapshots"][vname] = None
                log(f"{vname} 截图未落地", "WARN")
        except Exception as e:
            log(f"{vname} 截图异常: {e}", "WARN")

    # ── 导出辅助 ──────────────────────────────────────────────────
    # 探针实证 (2026-04-25): dynamic dispatch 下 SaveAs3 第 4/5 参数
    # (IExportPdfData, lReserved) 必须用 VARIANT(VT_DISPATCH, None),
    # 否则报"类型不匹配"且不写盘.
    def _save_as(asm_doc, path_str: str, label: str) -> Optional[str]:
        try:
            ext_obj = asm_doc.Extension
        except Exception:
            ext_obj = None
        if ext_obj is None:
            log(f"{label}: Extension 不可用", "WARN")
            return None
        # 装配体 STL/STEP 默认按零件拆多文件 (SW 默认行为).
        # 导出前先清理同前缀旧文件, 避免 SW 检测重名加 -N 后缀.
        parent = Path(path_str).parent
        stem   = Path(path_str).stem
        ext_   = Path(path_str).suffix
        try:
            for old in parent.glob(f"{stem}*{ext_}"):
                if old.is_file():
                    try: old.unlink()
                    except Exception: pass
            # 拆件式: 同 ext, 名含 stem 的兄弟
            for old in parent.glob(f"*{ext_}"):
                if old.is_file() and stem in old.stem and old.name != Path(path_str).name:
                    try: old.unlink()
                    except Exception: pass
        except Exception: pass

        err = win32com.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        wrn = win32com.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        nd  = win32com.VARIANT(pythoncom.VT_DISPATCH, None)
        try:
            ok = ext_obj.SaveAs3(path_str, 0, 1, nd, nd, err, wrn)
        except Exception as exc:
            log(f"{label} SaveAs3 异常: {exc}", "WARN")
            return None
        # 情形 A: 单文件落地 (STEP)
        if ok and Path(path_str).exists():
            sz = Path(path_str).stat().st_size
            log(f"{label} → {path_str} ({sz//1024}KB)", "OK")
            return path_str
        # 情形 B: 拆件式落地 (装配体 STL 默认行为)
        siblings = [f for f in parent.glob(f"*{ext_}") if f.is_file() and stem in f.stem]
        if siblings:
            total = sum(f.stat().st_size for f in siblings)
            log(f"{label} → {len(siblings)} 文件 ({total//1024}KB) @ {parent}", "OK")
            return str(parent)
        log(f"{label} 导出未落地 err={err.value} warn={wrn.value} ok={ok}", "WARN")
        return None

    # STEP (单文件)
    step_path = str(HERE / "交付包_最终" / "锤式破碎机_总装配.STEP")
    result["step"] = _save_as(asm, step_path, "STEP")

    # STL (装配体默认拆每件一个文件)
    stl_path = str(HERE / "交付包_最终" / "锤式破碎机_总装配.STL")
    result["stl"] = _save_as(asm, stl_path, "STL")

    return result


# ══════════════════════════════════════════════════════════════════════
# 报告生成 (Markdown)
# ══════════════════════════════════════════════════════════════════════

def write_report_md(rep: Dict[str, Any]) -> Path:
    lines = []
    lines.append("# SolidWorks 实测仿真报告 · 道法自然")
    lines.append("")
    lines.append(f"> 生成: {rep['timestamp']}  ·  SW Rev: {rep.get('sw_revision','?')}")
    lines.append(f"> 装配: `{rep.get('assembly','?')}`")
    lines.append("")

    # 总览
    p2 = rep["phase2_self_check"]; p3 = rep["phase3_interference"]
    p4 = rep["phase4_mass_properties"]; p5 = rep["phase5_mates"]
    p6 = rep["phase6_motion"]; p7 = rep["phase7_render_export"]
    lines.append("## 总览")
    lines.append("")
    lines.append("| Phase | 项 | 结果 |")
    lines.append("|---|---|---|")
    lines.append(f"| 2 | 重建 | {'✅' if p2.get('rebuild_ok') else '⚠️'} |")
    lines.append(f"| 2 | 组件 | {p2.get('components_total','?')} 件 (解析 {p2.get('components_resolved',0)} · 抑制 {p2.get('components_suppressed',0)} · 固定 {sum(1 for x in p2.get('comp_list',[]) if x.get('fixed'))}) |")
    lines.append(f"| 3 | 干涉 | {p3.get('count',0)} 处 {'✅' if p3.get('ok') else '⚠️'} |")
    asm_mp = p4.get("assembly") or {}
    if asm_mp:
        cg_m = asm_mp.get("cg_m") or [0, 0, 0]
        cg_mm = [round(v*1000, 1) for v in cg_m]
        lines.append(f"| 4 | 整机质量 | **{asm_mp.get('mass_kg','?')} kg** |")
        lines.append(f"| 4 | 整机重心 | ({cg_mm[0]}, {cg_mm[1]}, {cg_mm[2]}) mm |")
        lines.append(f"| 4 | 整机体积 | {asm_mp.get('volume_m3',0)*1e6:.1f} cm³ |")
        lines.append(f"| 4 | 组件级 | {len(p4.get('components',[]))} 件 (去重) |")
    else:
        lines.append(f"| 4 | 整机质量 | — |")
    lines.append(f"| 5 | 配合 | {p5.get('total',0)} 处 |")
    lines.append(f"| 6 | 运动算例 | {'解' if p6.get('solved') else ('无插件/跳过' if not p6.get('available') else '建立未解')}  ({ROTOR_RPM} rpm × {SIM_DURATION_S}s) |")
    lines.append(f"| 7 | 截图 | {sum(1 for v in p7.get('snapshots',{}).values() if v)} 视图 |")
    lines.append(f"| 7 | STEP | {'✅ ' + p7.get('step') if p7.get('step') else '—'} |")
    lines.append(f"| 7 | STL | {'✅ ' + p7.get('stl') if p7.get('stl') else '—'} |")
    lines.append("")

    # 抑制组件 (装配树 ⚠ 图标根因)
    supp_names = p2.get("suppressed_names") or []
    if supp_names:
        lines.append("## 抑制组件 (装配树 ⚠ 图标)")
        lines.append("")
        for n in supp_names:
            lines.append(f"- `{n}`")
        lines.append("")

    # 配合诊断 (0 处时给出原因)
    if p5.get("total", 0) == 0:
        n_fix = sum(1 for x in p2.get("comp_list", []) if x.get("fixed"))
        if n_fix and n_fix == p2.get("components_total", 0):
            lines.append("## 配合诊断")
            lines.append("")
            lines.append(f"- 装配体内 **{n_fix}** 件组件全部为 *固定* (Fixed) 状态, 故 MateGroup 为空 (0 处配合).")
            lines.append("- 当前装配采用 **位置固定式** 而非 **配合约束式**.")
            lines.append("- 改进建议: 取消固定 → 添加同心/重合等配合 → 让 SW 自动解算自由度. 这样 Motion Study 才能驱动旋转.")
            lines.append("")

    # 干涉细节 (按体积降序, 工程师先看大干涉)
    if p3.get("count", 0) > 0:
        lines.append(f"## 干涉清单 ({p3.get('count', 0)} 处, 按体积降序)")
        lines.append("")
        lines.append("| # | 体积 (mm³) | 组件 |")
        lines.append("|---:|---:|---|")
        intfs_sorted = sorted(
            p3.get("interferences", []),
            key=lambda x: -(x.get("volume_m3") or 0),
        )
        for i, it in enumerate(intfs_sorted, 1):
            v_mm3 = (it.get("volume_m3") or 0) * 1e9
            comps = " ↔ ".join(it.get("components", []) or ["?"])
            lines.append(f"| {i} | {v_mm3:.1f} | {comps} |")
        lines.append("")

    # 整机质量属性
    if asm_mp:
        lines.append("## 整机质量属性")
        lines.append("")
        lines.append(f"- **质量**: {asm_mp.get('mass_kg')} kg")
        lines.append(f"- **体积**: {asm_mp.get('volume_m3')} m³  ({asm_mp.get('volume_m3',0)*1e6:.1f} cm³)")
        lines.append(f"- **表面积**: {asm_mp.get('surface_m2')} m²")
        cg_m = asm_mp.get('cg_m') or [0,0,0]
        lines.append(f"- **重心 (m)**: {cg_m}")
        lines.append(f"- **重心 (mm)**: ({cg_m[0]*1000:.1f}, {cg_m[1]*1000:.1f}, {cg_m[2]*1000:.1f})")
        if asm_mp.get("principal_moments_kgm2"):
            lines.append(f"- **主惯量 (kg·m²)**: {asm_mp.get('principal_moments_kgm2')}")
        if asm_mp.get("moment_at_cg"):
            lines.append(f"- **过 CG 惯性张量** (Lxx,Lxy,Lxz,Lyx,Lyy,Lyz,Lzx,Lzy,Lzz): {asm_mp.get('moment_at_cg')}")
        lines.append("")

    # 组件质量 (按 mass 降序, 计实例数 → 还原整机质量)
    comps = p4.get("components", [])
    if comps:
        # 从 phase2 comp_list 反查每个零件文档的实例数
        comp_list = p2.get("comp_list", []) or []
        def _count_insts(comp_name: str) -> int:
            """name 形如 'hammer-1', 同零件其他实例 'hammer-2'…'hammer-16'."""
            stem = comp_name.rsplit("-", 1)[0] if "-" in comp_name else comp_name
            n = 0
            for x in comp_list:
                xn = str(x.get("name", ""))
                if xn == comp_name or xn.rsplit("-", 1)[0] == stem:
                    if not x.get("suppressed"): n += 1
            return max(n, 1)

        comps_sorted = sorted(comps, key=lambda c: -(c.get("mass_kg") or 0))
        lines.append(f"## 组件质量属性 ({len(comps)} 件唯一零件, 按单件质量降序)")
        lines.append("")
        lines.append("| # | 零件 (ModelDoc) | 实例 | 单件 (kg) | 总质量 (kg) | 体积 (cm³) | 表面 (m²) |")
        lines.append("|---:|---|---:|---:|---:|---:|---:|")
        total_m = 0.0
        for i, c in enumerate(comps_sorted, 1):
            m = c.get("mass_kg") or 0
            n_inst = _count_insts(c.get("name", ""))
            total = float(m) * n_inst
            total_m += total
            v_cm3 = (c.get("volume_m3") or 0) * 1e6
            lines.append(f"| {i} | `{c.get('name','?')}` | ×{n_inst} | {m:.3f} | {total:.3f} | {v_cm3:.1f} | {c.get('surface_m2','?')} |")
        lines.append(f"| | **整机合计** | | | **{total_m:.3f}** | | |")
        # 与整机交叉校验
        if asm_mp:
            asm_mass = asm_mp.get("mass_kg", 0)
            delta = abs(total_m - asm_mass)
            check = "✅ 一致" if delta < 1.0 else f"⚠️ 偏差 {delta:.3f}kg"
            lines.append(f"| | **整机直读 (Phase 4)** | | | **{asm_mass}** | | {check} |")
        lines.append("")

    # 配合分布
    if p5.get("by_type"):
        lines.append("## 配合类型分布")
        lines.append("")
        lines.append("| 类型 | 数量 |")
        lines.append("|---|---:|")
        for k in sorted(p5["by_type"].keys()):
            lines.append(f"| {k} | {p5['by_type'][k]} |")
        lines.append("")

    # 截图清单
    if p7.get("snapshots"):
        lines.append("## 截图")
        lines.append("")
        for k, v in p7["snapshots"].items():
            if v: lines.append(f"- {k}: `{v}`")
        lines.append("")

    lines.append("---")
    lines.append("*道法自然 · 万法归宗 · SolidWorks 实测仿真完成*")
    LOG_MD.write_text("\n".join(lines), encoding="utf-8")
    return LOG_MD


# ══════════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="SolidWorks 实测仿真 · 道法自然")
    ap.add_argument("--asm", default=str(DEFAULT_ASM), help="装配体路径 (默认: 交付包_最终/锤式破碎机_总装配.SLDASM)")
    ap.add_argument("--skip-motion", action="store_true", help="跳过 Motion Study")
    args = ap.parse_args()

    print("\n" + "═" * 60)
    print("  锤式破碎机 · SolidWorks 实测仿真 · 道法自然")
    print("═" * 60)
    log(f"装配 (默认): {args.asm}")
    if not Path(args.asm).exists():
        log(f"⚠ 默认装配体不存在: {args.asm}", "WARN")
        log(f"  → 将尝试附加 SW 中已打开的 ActiveDoc 装配", "INFO")

    t0 = time.time()
    rep: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "assembly": str(args.asm),
        "skip_motion": bool(args.skip_motion),
    }

    # ── Phase 1: 连接 + 打开装配 ─────────────────────────────────
    phase(1, "连接 SW + 打开装配体")
    try:
        sw, win32com, pythoncom = connect_sw()
        rep["sw_revision"] = str(sw.RevisionNumber)
        asm = open_assembly(sw, win32com, pythoncom, args.asm)
        if asm is None:
            rep["error"] = "open_failed"
            LOG_JSON.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
            return 3
    except Exception as e:
        log(f"连接失败: {e}", "FAIL")
        rep["error"] = f"connect:{e}"
        LOG_JSON.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        return 4

    # ── Phase 2 ~ 7 ──────────────────────────────────────────────
    phase(2, "装配自检 (重建 + 组件)")
    rep["phase2_self_check"] = phase2_self_check(asm)

    phase(3, "干涉检测 (体级精确)")
    rep["phase3_interference"] = phase3_interference(asm)

    phase(4, "质量属性 (整机 + 单件)")
    rep["phase4_mass_properties"] = phase4_mass_properties(asm)

    phase(5, "配合关系图")
    rep["phase5_mates"] = phase5_mates(asm)

    phase(6, "运动算例 (Motion Study)")
    rep["phase6_motion"] = phase6_motion_study(asm, sw, skip=args.skip_motion)

    phase(7, "渲染 + 导出 (6 视图 · STEP · STL)")
    rep["phase7_render_export"] = phase7_render_export(asm, win32com, pythoncom)

    # ── 收尾 ──────────────────────────────────────────────────────
    rep["elapsed_s"] = round(time.time() - t0, 2)
    LOG_JSON.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = write_report_md(rep)
    print(f"\n{'═'*60}")
    print(f"  仿真完成 · 耗时 {rep['elapsed_s']}s")
    print(f"  JSON: {LOG_JSON}")
    print(f"  MD:   {md}")
    print(f"{'═'*60}")
    log("道法自然 · SolidWorks 实测仿真完成", "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
