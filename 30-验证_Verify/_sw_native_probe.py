#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_sw_native_probe.py · 反笙 · SW 底层真签名探针 · 道直连

目的:
  反 pywin32 gencache 代理, 直接查 SW 2023 活体暴露的真实方法 + DISPID.
  列穷:
    - IModelDoc2: FirstFeature, GetBodies2, FeatureByPositionReverse
    - IPartDoc:   GetPartBox
    - ModelDocExtension: GetBox
    - IAssemblyDoc: GetComponents, GetChildren, GetComponentCount
    - IFeatureManager: InsertFeatureChamfer 系列真签名
    - IFeature: GetNextFeature, GetTypeName2

无为而无不为: 不自己建文档, 直接拿 ActiveDoc 或新建临时 part.
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
import pythoncom
import win32com.client as wc
import win32com.client.dynamic as wcd

_HERE = Path(__file__).resolve().parent
_DAO_ROOT = _HERE.parent
sys.path.insert(0, str(_DAO_ROOT / "00-本源_Origin"))


def _probe_dispids(obj, names):
    """穷举 DISPID, 不动表面."""
    out = {}
    try:
        oleobj = getattr(obj, "_oleobj_", None)
        if oleobj is None:
            return {"_err": "no _oleobj_"}
        for n in names:
            try:
                ids = oleobj.GetIDsOfNames(n)
                out[n] = ids if isinstance(ids, int) else list(ids)
            except Exception as e:
                out[n] = f"MISS({type(e).__name__})"
    except Exception as e:
        out["_fatal"] = f"{type(e).__name__}: {e}"
    return out


def main():
    pythoncom.CoInitialize()
    result = {"ok": False, "targets": {}}

    # late-binding app · 绕 gencache 污染
    app = wcd.Dispatch("SldWorks.Application")
    result["revision"] = getattr(app, "RevisionNumber", "?")
    app.Visible = True

    # ── ModelDoc2 级真签名 ──
    # 不新建, 复用 ActiveDoc; 若无则新建临时 part (用 NewPart 零参)
    doc = app.ActiveDoc
    if doc is None:
        print("ActiveDoc=None, 新建 part")
        doc = app.NewPart()
    if doc is None:
        result["err"] = "无法获取活动文档"
        Path(_HERE / "_sw_native_probe.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 1

    md_names = [
        "FirstFeature", "IFirstFeature", "Extension",
        "GetBodies2", "FeatureByPositionReverse", "FeatureManager",
        "SelectionManager",
    ]
    result["targets"]["IModelDoc2"] = _probe_dispids(doc, md_names)

    # ── Part 层 (若是 part) ──
    try:
        doc_type = doc.GetType() if callable(doc.GetType) else doc.GetType
    except TypeError:
        doc_type = int(doc.GetType)
    result["doc_type"] = doc_type  # 1=part, 2=assembly, 3=drawing
    if doc_type == 1:
        part_names = ["GetPartBox", "GetBox", "GetBodies2"]
        result["targets"]["IPartDoc"] = _probe_dispids(doc, part_names)
        # 实调 GetPartBox
        try:
            arr = doc.GetPartBox(True)
            result["GetPartBox"] = {"type": type(arr).__name__, "len": len(arr) if arr else 0,
                                     "sample": list(arr)[:8] if arr else []}
        except Exception as e:
            result["GetPartBox"] = {"err": f"{type(e).__name__}: {e}"}

    # ── Extension 层 ──
    try:
        ext = doc.Extension
        ext_names = ["GetBox", "SelectAll", "SaveAs"]
        result["targets"]["IModelDocExtension"] = _probe_dispids(ext, ext_names)
    except Exception as e:
        result["Extension_err"] = f"{type(e).__name__}: {e}"

    # ── FeatureManager 真签名 ──
    try:
        fm = doc.FeatureManager
        fm_names = [
            "InsertFeatureChamfer", "InsertFeatureChamfer2", "InsertFeatureChamfer3",
            "FeatureExtrusion2", "FeatureExtrusion3", "FeatureFillet3",
            "InsertFeatureShell", "GetFeatures", "FirstFeature",
        ]
        result["targets"]["IFeatureManager"] = _probe_dispids(fm, fm_names)
        # 实调 GetFeatures (默认返所有顶层特征)
        try:
            feats = fm.GetFeatures(False)  # False=不含 subfeatures, True=只含顶层
            n = len(feats) if feats else 0
            sample = []
            if feats:
                for f in feats[:10]:
                    try:
                        sample.append({"name": f.Name, "type": f.GetTypeName2()})
                    except Exception:
                        break
            result["GetFeatures_False"] = {"count": n, "sample": sample}
        except Exception as e:
            result["GetFeatures_False"] = {"err": f"{type(e).__name__}: {e}"}

        try:
            feats2 = fm.GetFeatures(True)
            n2 = len(feats2) if feats2 else 0
            result["GetFeatures_True"] = {"count": n2}
        except Exception as e:
            result["GetFeatures_True"] = {"err": f"{type(e).__name__}: {e}"}
    except Exception as e:
        result["FeatureManager_err"] = f"{type(e).__name__}: {e}"

    # ── FirstFeature 实调验 ──
    try:
        ff = doc.FirstFeature  # property 形式
        nf = 0
        if ff is not None:
            cur = ff
            while cur is not None and nf < 50:
                nf += 1
                try:
                    cur = cur.GetNextFeature()
                except Exception:
                    break
        result["FirstFeature_walk"] = {"count": nf}
    except Exception as e:
        result["FirstFeature_walk"] = {"err": f"{type(e).__name__}: {e}"}

    # ── 若是装配, 探 GetComponents ──
    if doc_type == 2:
        asm_names = ["GetComponents", "GetChildren", "GetComponentCount"]
        result["targets"]["IAssemblyDoc"] = _probe_dispids(doc, asm_names)
        try:
            comps_t = doc.GetComponents(True)   # topLevelOnly=True
            result["GetComponents_True"] = {"count": len(comps_t) if comps_t else 0}
        except Exception as e:
            result["GetComponents_True"] = {"err": f"{type(e).__name__}: {e}"}
        try:
            comps_f = doc.GetComponents(False)  # topLevelOnly=False → 所有
            result["GetComponents_False"] = {"count": len(comps_f) if comps_f else 0}
        except Exception as e:
            result["GetComponents_False"] = {"err": f"{type(e).__name__}: {e}"}

    # ── InsertFeatureChamfer 实调穷验 ──
    # 仅收集参数计数; 不实调(需选边)
    try:
        fm = doc.FeatureManager
        for name in ("InsertFeatureChamfer", "InsertFeatureChamfer2", "InsertFeatureChamfer3"):
            try:
                fn = getattr(fm, name, None)
                if fn is None:
                    result.setdefault("chamfer_attrs", {})[name] = "MISS"
                else:
                    result.setdefault("chamfer_attrs", {})[name] = f"{type(fn).__name__}"
            except Exception as e:
                result.setdefault("chamfer_attrs", {})[name] = f"ERR:{type(e).__name__}"
    except Exception as e:
        result["chamfer_probe_err"] = f"{type(e).__name__}: {e}"

    result["ok"] = True
    out_path = _HERE / "_sw_native_probe.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {out_path}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
