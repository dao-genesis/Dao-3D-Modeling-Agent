#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_sw_chamfer_probe.py · 反笙 · 实调 InsertFeatureChamfer 穷举参数

策略: 新建 part → 拉出立方体 → 选边 → 穷 6/7/8 参调用 → 找真签名.
"""
from __future__ import annotations
import sys, math, json
from pathlib import Path
import pythoncom
import win32com.client.dynamic as wcd

_HERE = Path(__file__).resolve().parent
_DAO_ROOT = _HERE.parent
sys.path.insert(0, str(_DAO_ROOT / "00-本源_Origin"))


def main():
    pythoncom.CoInitialize()
    result = {"trials": []}

    # 用 SWLive 建立部件 (稳健通路)
    from dao_sw_live import SWLive
    live = SWLive()
    live.ensure_live(visible=True, dismiss_welcome=False, launch_timeout_s=60)
    doc_live = live.new_part()
    part = doc_live.base._raw  # 拿 IModelDoc2
    app = live.app

    # 拉一个 40x40x20 立方体
    try:
        sk = part.SketchManager
        sk.InsertSketch(True)
        sk.CreateCornerRectangle(-0.02, -0.02, 0, 0.02, 0.02, 0)
        sk.InsertSketch(True)  # exit
        fm = part.FeatureManager
        feat = fm.FeatureExtrusion3(
            True, False, False, 0, 0, 0.02, 0.01,
            False, False, False, False, 0, 0, False, False, False, False,
            True, True, True, 0, 0, False,
        )
        print(f"拉伸 OK: {feat is not None}")
    except Exception as e:
        print(f"拉伸失败: {e}")
        result["pre_err"] = f"{type(e).__name__}: {e}"

    # 选一条边 (顶面外环)
    try:
        ext = part.Extension
        ok_sel = ext.SelectByID2(
            "", "EDGE", 0.02, 0.0, 0.02,  # 顶面右边中点
            False, 1, None, 0,
        )
        print(f"选边 OK: {ok_sel}")
        # 再选一条以防
        ext.SelectByID2("", "EDGE", -0.02, 0.0, 0.02, True, 1, None, 0)
    except Exception as e:
        print(f"选边失败: {e}")

    # ── 穷 InsertFeatureChamfer 参数 ──
    # SW API: InsertFeatureChamfer(Options, Type, Width, Angle, OtherDist, VertexChamDist3)
    # Options: swChamferFlag_e (4=propagate tangent)
    # Type: swChamferType_e 0=angle-dist, 1=dist-dist, 2=vertex, 3=offset-face, 4=face-face
    # 注: 反弹 "非选择性的参数" 意味着 Invoke 层参数数量与 IDispatch typelib 签名不符.
    # SolidWorks 2016+ InsertFeatureChamfer 实际 6 arg.
    # 2023 可能需要 extra 参数 (FaceFaceFlip).

    combos = [
        ("6arg_angle_dist", [0, 0, 0.001, math.radians(45), 0.0, 0.0]),         # Type=0
        ("6arg_dist_dist",  [0, 1, 0.001, 0.0, 0.001, 0.0]),                    # Type=1
        ("6arg_opt4",       [4, 0, 0.001, math.radians(45), 0.0, 0.0]),
        ("7arg",            [0, 0, 0.001, math.radians(45), 0.0, 0.0, False]),
        ("8arg",            [0, 0, 0.001, math.radians(45), 0.0, 0.0, False, 0]),
    ]

    for label, args in combos:
        # 每次重新选边 (之前调可能清选)
        try:
            part.ClearSelection2(True)
            part.Extension.SelectByID2("", "EDGE", 0.02, 0.0, 0.02, False, 1, None, 0)
            part.Extension.SelectByID2("", "EDGE", -0.02, 0.0, 0.02, True, 1, None, 0)
            sel_n = part.SelectionManager.GetSelectedObjectCount2(-1)
        except Exception as e:
            sel_n = f"sel_err:{e}"

        t = {"label": label, "n_args": len(args), "sel_count": sel_n}
        try:
            feat = part.FeatureManager.InsertFeatureChamfer(*args)
            t["ok"] = feat is not None
            t["feat_name"] = feat.Name if feat is not None else None
            # 撤销, 避免下个试受影响
            if feat is not None:
                try:
                    part.EditUndo2(1)
                except Exception:
                    pass
        except Exception as e:
            t["err"] = f"{type(e).__name__}: {e}"
        result["trials"].append(t)
        print(f"  [{label}] sel={sel_n} → {t}")

    # 写 JSON
    out = _HERE / "_sw_chamfer_probe.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] {out}")

    # 清理 · 不保存关闭
    try:
        app.CloseDoc(part.GetTitle)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
