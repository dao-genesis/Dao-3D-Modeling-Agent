#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_sw_chamfer_fix_probe.py · 验证 8 参数 chamfer 真调用"""
from __future__ import annotations
import sys, math, json
from pathlib import Path
import pythoncom

_HERE = Path(__file__).resolve().parent
_DAO_ROOT = _HERE.parent
sys.path.insert(0, str(_DAO_ROOT / "00-本源_Origin"))


def main():
    pythoncom.CoInitialize()
    result = {"trials": []}

    from dao_sw_live import SWLive
    live = SWLive()
    live.ensure_live(visible=True, dismiss_welcome=False, launch_timeout_s=60)
    doc_live = live.new_part()
    part = doc_live.base._raw
    app = live.app

    # 拉立方体 40x40x20
    sk = part.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(-0.02, -0.02, 0, 0.02, 0.02, 0)
    sk.InsertSketch(True)
    fm = part.FeatureManager
    feat = fm.FeatureExtrusion3(
        True, False, False, 0, 0, 0.02, 0.01,
        False, False, False, False, 0, 0, False, False, False, False,
        True, True, True, 0, 0, False,
    )
    result["extrude_ok"] = feat is not None

    # ── 用 Extension.SelectByID2 选 2 条顶面的边 ──
    # 关键: Callout 传 VT_DISPATCH NULL, 不是 Python None
    ext = part.Extension
    part.ClearSelection2(True)

    # SelectByID2 真签名:
    # (Name, Type, X, Y, Z, Append, Mark, Callout, SelectOption)
    # 在 pywin32 late-binding 下, Callout 用 pythoncom.Empty (VT_EMPTY) 可避免类型不匹配
    sel_ok_a = False
    sel_ok_b = False
    try:
        # 直接传入 8 参, 让 pywin32 推断 Callout 默认
        sel_ok_a = ext.SelectByID2("", "EDGE", 0.02, 0.0, 0.02, False, 1,
                                    pythoncom.Empty, 0)
    except Exception as e:
        result["sel_a_err"] = f"{type(e).__name__}: {e}"
        # 试 win32com.client.VARIANT
        try:
            from win32com.client import VARIANT
            sel_ok_a = ext.SelectByID2("", "EDGE", 0.02, 0.0, 0.02, False, 1,
                                        VARIANT(pythoncom.VT_DISPATCH, None), 0)
            result["sel_a_path"] = "VARIANT_VT_DISPATCH"
        except Exception as e2:
            result["sel_a_err2"] = f"{type(e2).__name__}: {e2}"

    try:
        sel_ok_b = ext.SelectByID2("", "EDGE", -0.02, 0.0, 0.02, True, 1,
                                    pythoncom.Empty, 0)
    except Exception as e:
        result["sel_b_err"] = f"{type(e).__name__}: {e}"

    result["sel_ok_a"] = bool(sel_ok_a)
    result["sel_ok_b"] = bool(sel_ok_b)

    # 检查选中数
    try:
        n = part.SelectionManager.GetSelectedObjectCount2(-1)
        result["sel_count_after"] = n
    except Exception as e:
        result["sel_count_err"] = str(e)

    # ── 8 参 chamfer ──
    # Options=0, ChamferType=0 (angle-distance), Width=1mm, Angle=45°, rest=0
    try:
        feat_c = fm.InsertFeatureChamfer(
            0,                           # Options
            0,                           # ChamferType (angle-dist)
            0.001,                       # Width (1 mm)
            math.radians(45),            # Angle
            0.0, 0.0, 0.0, 0.0,          # OtherDist + 3 VertexChamDist
        )
        result["chamfer_8arg_ok"] = feat_c is not None
        if feat_c is not None:
            try:
                result["chamfer_name"] = feat_c.Name
                result["chamfer_type"] = feat_c.GetTypeName2()
            except Exception:
                pass
    except Exception as e:
        result["chamfer_8arg_err"] = f"{type(e).__name__}: {e}"

    # 落盘
    out = _HERE / "_sw_chamfer_fix_probe.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 清
    try:
        part.ClearSelection2(True)
        app.CloseDoc(part.GetTitle)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
