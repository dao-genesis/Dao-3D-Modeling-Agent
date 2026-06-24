#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_dao_诊断_位置.py — 读当前装配体所有组件的真实 origin + world bbox."""
from __future__ import annotations
import sys, time, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机"))

from 道_直连_底层 import Dao, _safe  # noqa
import 道_直连_底层_facets  # noqa

def main():
    dao = Dao().connect()
    title = _safe(lambda: str(dao.doc.GetTitle()), "?")
    print(f"Doc: {title}")

    # 若非装配体, 找装配体 doc
    import win32com.client.dynamic as _d
    app = _d.Dispatch(dao._sw_raw)
    asm_doc = None
    try:
        doc = app.GetFirstDocument
        while doc is not None:
            try:
                if int(doc.GetType) == 2:
                    asm_doc = doc
                    break
            except: pass
            try: doc = doc.GetNext
            except: break
    except: pass

    if asm_doc is None:
        print("无装配体"); return

    comps = asm_doc.GetComponents(False) or []
    records = []
    print(f"{'Name':30s} {'Origin (mm)':35s} {'World bbox (mm)':50s}")
    print("─" * 130)
    for c in comps:
        try:
            name = str(c.Name2)
        except:
            continue
        # Origin via Transform2
        origin = None
        try:
            xf = c.Transform2
            if xf is not None:
                arr = xf.ArrayData
                if arr and len(arr) >= 16:
                    # column-major: T 在 12,13,14 (m)
                    origin = (arr[12]*1000, arr[13]*1000, arr[14]*1000)
        except Exception as e:
            pass

        # World bbox via IComponent2.GetBox
        bbox = None
        try:
            box = c.GetBox(False, False)
            if box and len(box) >= 6:
                bbox = [v*1000 for v in box[:6]]
        except: pass

        ostr = (f"({origin[0]:+8.1f},{origin[1]:+8.1f},{origin[2]:+8.1f})"
                if origin else "?")
        bstr = (f"X[{bbox[0]:+.0f},{bbox[3]:+.0f}] "
                f"Y[{bbox[1]:+.0f},{bbox[4]:+.0f}] "
                f"Z[{bbox[2]:+.0f},{bbox[5]:+.0f}]"
                if bbox else "?")
        print(f"{name[:30]:30s} {ostr:35s} {bstr:50s}")
        records.append({"name": name, "origin_mm": origin, "bbox_mm": bbox})

    out = HERE / "_产物输出" / "诊断_位置.json"
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str),
                   encoding="utf-8")
    print(f"\n→ {out}")

if __name__ == "__main__":
    main()
