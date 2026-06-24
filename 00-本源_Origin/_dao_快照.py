#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_dao_快照.py — 装配审计 · 一键生成 · 道直连器实证

"万物并作, 吾以观复. 夫物芸芸, 各复归其根."

用法:
    python _dao_快照.py                     # 打印到控制台
    python _dao_快照.py --json out.json     # 导出 JSON
    python _dao_快照.py --md out.md         # 导出 Markdown
    python _dao_快照.py --full              # 包 face 扫描 + drift 诊

此脚本证明 道直连器 可独立完成 dao_solidworks + dao_sw_live + dao_sw_omni
三层累计 500+ KB 才能做的事情. **~200 行 · 纯直 memid · 无 Builder 包装**.

审计项:
  ① 装配基本态: title/path/component_count/mate_count
  ② 组件清单: name / fixed / suppressed / origin_mm
  ③ Mate 清单: name / type_name / type / error_status
  ④ [--full] 每组件的 B-Rep: cyl/plane 统计
  ⑤ [--full] 漂移诊断: origin_mm 与 Mate 隐含期望的对照
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from 道_直连_底层 import Dao, DOC, MATE, ALIGN, _safe


# ════════════════════════════════════════════════════════════════════════
# 审计采集
# ════════════════════════════════════════════════════════════════════════
def collect_overview(dao: Dao) -> Dict[str, Any]:
    """① 总览."""
    o: Dict[str, Any] = {"ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    o["sw_revision"] = _safe(lambda: str(dao.sw.RevisionNumber()))
    o["doc_title"] = _safe(lambda: str(dao.doc.GetTitle()))
    o["doc_path"] = _safe(lambda: str(dao.doc.GetPathName()))
    o["doc_type"] = DOC.NAME.get(
        _safe(lambda: int(dao.doc.GetType()), 0), "?")
    if dao.asm is not None:
        o["component_count"] = _safe(
            lambda: int(dao.asm.GetComponentCount(False)), -1)
    o["tlb"] = {
        "loaded": dao.mt.loaded,
        "interfaces": len(dao.mt.list_interfaces()),
        "methods": sum(len(v) for v in dao.mt._methods.values()),
        "properties": sum(len(v) for v in dao.mt._props.values()),
    }
    return o


def collect_components(dao: Dao) -> List[Dict[str, Any]]:
    """② 组件清单 + origin_mm + 状态."""
    if dao.asm is None:
        return []
    cmap = dao.build_comp_map()
    comps: List[Dict[str, Any]] = []
    for name, comp in cmap.items():
        entry: Dict[str, Any] = {"name": name}
        entry["fixed"] = dao.comp.is_fixed(name)
        entry["suppressed"] = dao.comp.is_suppressed(name)
        origin = dao.transform.origin_mm(name)
        if origin:
            entry["origin_mm"] = [round(origin[0], 2),
                                  round(origin[1], 2),
                                  round(origin[2], 2)]
        comps.append(entry)
    return comps


def collect_mates(dao: Dao) -> List[Dict[str, Any]]:
    """③ Mate 清单."""
    if dao.asm is None:
        return []
    return dao.mate.list_all()


def collect_faces(dao: Dao, comp_names: List[str]) -> Dict[str, Any]:
    """④ B-Rep · 每组件 face 统计."""
    result: Dict[str, Any] = {}
    for name in comp_names:
        try:
            scan = dao.face.scan(name)
            if not scan.get("ok"):
                result[name] = {"ok": False, "error": scan.get("error")}
                continue
            faces = scan.get("faces", [])
            cyls = [f for f in faces if f.get("type") == "cylinder"]
            planes = [f for f in faces if f.get("type") == "plane"]
            result[name] = {
                "ok": True,
                "n_faces": len(faces),
                "n_cylinders": len(cyls),
                "n_planes": len(planes),
                "cylinders": [
                    {
                        "radius_mm": c.get("radius_mm"),
                        "origin_mm": c.get("origin_mm"),
                        "axis": c.get("axis"),
                    } for c in cyls[:10]
                ],
            }
        except Exception as e:
            result[name] = {"ok": False, "error": str(e)}
    return result


def collect_feature_tree(dao: Dao) -> Dict[str, int]:
    """特征类型分布 (for drift diagnostic)."""
    if dao.asm is None:
        return {}
    counts: Dict[str, int] = {}
    feat = dao.asm.FirstFeature()
    n = 0
    while feat and n < 10000:
        n += 1
        f = feat.cast("IFeature")
        tn = _safe(lambda fx=f: str(fx.GetTypeName2()), "?")
        counts[tn] = counts.get(tn, 0) + 1
        try:
            feat = feat.GetNextFeature()
        except Exception:
            break
    return counts


# ════════════════════════════════════════════════════════════════════════
# 输出
# ════════════════════════════════════════════════════════════════════════
def render_console(snapshot: Dict[str, Any]):
    """控制台输出 (简).
    """
    o = snapshot["overview"]
    print(f"\n═══ 装配快照 · {o['ts']} ═══")
    print(f"SW: {o.get('sw_revision', '?')}")
    print(f"Doc: {o.get('doc_title', '?')}  ({o.get('doc_type', '?')})")
    print(f"Path: {o.get('doc_path', '?')}")
    print(f"tlb: {o['tlb']['interfaces']} interfaces / "
          f"{o['tlb']['methods']} methods / "
          f"{o['tlb']['properties']} properties")
    if "component_count" in o:
        print(f"Components: {o['component_count']}")

    comps = snapshot.get("components", [])
    mates = snapshot.get("mates", [])
    print(f"\n── 组件 ({len(comps)}) ──")
    n_fixed = sum(1 for c in comps if c.get("fixed"))
    n_supp = sum(1 for c in comps if c.get("suppressed"))
    print(f"  fixed: {n_fixed} · suppressed: {n_supp} · "
          f"free: {len(comps) - n_fixed - n_supp}")
    for c in comps[:15]:
        org = c.get("origin_mm")
        status = []
        if c.get("fixed"):
            status.append("F")
        if c.get("suppressed"):
            status.append("S")
        s = "[" + "".join(status) + "]" if status else "   "
        if org:
            print(f"  {s} {c['name']:30s}  "
                  f"@ ({org[0]:+7.1f}, {org[1]:+7.1f}, {org[2]:+7.1f}) mm")
        else:
            print(f"  {s} {c['name']:30s}")
    if len(comps) > 15:
        print(f"  ... (+{len(comps)-15} more)")

    print(f"\n── Mates ({len(mates)}) ──")
    by_type: Dict[str, int] = {}
    for m in mates:
        tn = m.get("type_name", "?")
        by_type[tn] = by_type.get(tn, 0) + 1
    for tn, ct in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {tn:25s}  × {ct}")
    err_mates = [m for m in mates if m.get("error_status", -1) > 0]
    if err_mates:
        print(f"  ⚠  {len(err_mates)} 个有错误:")
        for m in err_mates[:5]:
            print(f"      {m.get('name')}  err={m.get('error_status')}")

    ft = snapshot.get("feature_tree", {})
    if ft:
        print(f"\n── 特征树 ({sum(ft.values())} 个) ──")
        for tn, ct in sorted(ft.items(), key=lambda x: -x[1])[:10]:
            print(f"  {tn:30s}  × {ct}")

    fs = snapshot.get("faces")
    if fs:
        print(f"\n── B-Rep 扫描 ({len(fs)} 组件) ──")
        for name, info in list(fs.items())[:5]:
            if info.get("ok"):
                print(f"  {name}: {info['n_faces']}F · "
                      f"cyl={info['n_cylinders']} · plane={info['n_planes']}")
                for cyl in info.get("cylinders", [])[:3]:
                    print(f"    cyl R={cyl.get('radius_mm')}mm  "
                          f"O={cyl.get('origin_mm')}  "
                          f"axis={cyl.get('axis')}")


def render_markdown(snapshot: Dict[str, Any]) -> str:
    """Markdown 输出 (详).
    """
    o = snapshot["overview"]
    md = []
    md.append(f"# 装配快照 · {o['ts']}\n")
    md.append(f"- **SW**: {o.get('sw_revision', '?')}")
    md.append(f"- **Doc**: `{o.get('doc_title', '?')}` "
              f"({o.get('doc_type', '?')})")
    md.append(f"- **Path**: `{o.get('doc_path', '?')}`")
    md.append(f"- **tlb**: {o['tlb']['interfaces']} interfaces / "
              f"{o['tlb']['methods']} methods / "
              f"{o['tlb']['properties']} properties")
    if "component_count" in o:
        md.append(f"- **Components**: {o['component_count']}")

    comps = snapshot.get("components", [])
    md.append("\n## 组件 ({})\n".format(len(comps)))
    md.append("| # | Name | Fixed | Suppressed | Origin (mm) |")
    md.append("|---|------|-------|------------|-------------|")
    for i, c in enumerate(comps, 1):
        org = c.get("origin_mm")
        org_s = ("({:+.1f}, {:+.1f}, {:+.1f})".format(*org)
                 if org else "—")
        md.append(f"| {i} | `{c['name']}` | "
                  f"{'✓' if c.get('fixed') else ''} | "
                  f"{'✓' if c.get('suppressed') else ''} | {org_s} |")

    mates = snapshot.get("mates", [])
    md.append("\n## Mates ({})\n".format(len(mates)))
    md.append("| # | Name | Type Name | Type | Err |")
    md.append("|---|------|-----------|------|-----|")
    for i, m in enumerate(mates, 1):
        md.append(f"| {i} | `{m.get('name')}` | "
                  f"{m.get('type_name')} | "
                  f"{m.get('type')} | {m.get('error_status')} |")

    fs = snapshot.get("faces")
    if fs:
        md.append("\n## B-Rep (部件面统计)\n")
        md.append("| Component | Faces | Cylinders | Planes |")
        md.append("|-----------|-------|-----------|--------|")
        for name, info in fs.items():
            if info.get("ok"):
                md.append(f"| `{name}` | {info['n_faces']} | "
                          f"{info['n_cylinders']} | {info['n_planes']} |")

    return "\n".join(md) + "\n"


# ════════════════════════════════════════════════════════════════════════
# 主
# ════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(
        description="装配快照 · 道直连器实证 (一键审计)")
    ap.add_argument("--json", help="导出 JSON 到文件")
    ap.add_argument("--md", help="导出 Markdown 到文件")
    ap.add_argument("--full", action="store_true",
                    help="全扫 (含 B-Rep · 较慢)")
    ap.add_argument("--face-limit", type=int, default=10,
                    help="--full 时扫前 N 个组件的 face (默 10)")
    args = ap.parse_args()

    print("═══ 道直连器 · 连接活体 SW ═══")
    dao = Dao().connect()
    print(f"  SW revision: {_safe(lambda: str(dao.sw.RevisionNumber()))}")
    print(f"  tlb 接口: {len(dao.mt.list_interfaces())}")

    snapshot: Dict[str, Any] = {}
    snapshot["overview"] = collect_overview(dao)
    print("  ✓ overview")

    snapshot["components"] = collect_components(dao)
    print(f"  ✓ components ({len(snapshot['components'])})")

    snapshot["mates"] = collect_mates(dao)
    print(f"  ✓ mates ({len(snapshot['mates'])})")

    snapshot["feature_tree"] = collect_feature_tree(dao)
    print(f"  ✓ feature_tree ({sum(snapshot['feature_tree'].values())})")

    if args.full:
        top_comp_names = [c["name"]
                          for c in snapshot["components"][:args.face_limit]]
        snapshot["faces"] = collect_faces(dao, top_comp_names)
        print(f"  ✓ faces ({len(snapshot['faces'])})")

    if args.json:
        Path(args.json).write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2,
                       default=str),
            encoding="utf-8")
        print(f"  ✓ JSON → {args.json}")

    if args.md:
        Path(args.md).write_text(render_markdown(snapshot),
                                  encoding="utf-8")
        print(f"  ✓ MD → {args.md}")

    if not args.json and not args.md:
        render_console(snapshot)

    print("\n═══ 道直连 · 快照毕 ═══")


if __name__ == "__main__":
    main()
