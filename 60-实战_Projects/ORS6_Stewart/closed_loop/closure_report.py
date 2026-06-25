#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SR6 closure report + figures.

产出 (写到 ./out/):
  closure_report.json   每个位姿的 IK角 / 闭环残差 / 杆长误差 + 聚合统计
  closure_figure.png    3 联图: (1) 杆长恒=175 (2) 闭环残差量级 (3) 工作空间俯视
运行: python closure_report.py
"""
from __future__ import annotations
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import true_kinematics as tk

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def build_report():
    poses = tk.default_workspace()
    rows = []
    for pose in poses:
        r = tk.closure_error(pose)
        row = {"pose": [round(float(x), 4) for x in pose], "reachable": r["reachable"]}
        if r["reachable"]:
            row.update({
                "angles_deg": {s: round(math.degrees(v), 4) for s, v in r["angles"].items()},
                "rods_mm": {s: round(L, 9) for s, L in tk.rod_lengths(r["angles"], pose).items()},
                "closure_dt_mm": r["dt_mm"],
                "closure_dr_deg": r["dr_deg"],
                "max_rod_err_mm": r["max_rod_err"],
            })
        rows.append(row)
    reach = [x for x in rows if x["reachable"]]
    agg = {
        "poses_total": len(rows),
        "poses_reachable": len(reach),
        "worst_rod_err_mm": max((x["max_rod_err_mm"] for x in reach), default=None),
        "worst_closure_dt_mm": max((x["closure_dt_mm"] for x in reach), default=None),
        "worst_closure_dr_deg": max((x["closure_dr_deg"] for x in reach), default=None),
        "rod_nominal_mm": tk.ROD,
        "home_height_mm": tk.HOME_H,
    }
    return {"aggregate": agg, "poses": rows}


def make_figure(report, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    reach = [r for r in report["poses"] if r["reachable"]]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))

    # (1) 每条腿每位姿杆长 —— 应全部贴在 175
    for i, s in enumerate(tk.SERVOS):
        ys = [r["rods_mm"][s] for r in reach]
        ax[0].plot(range(len(ys)), ys, "o-", ms=3, label=s)
    ax[0].axhline(tk.ROD, color="k", ls="--", lw=1)
    ax[0].set_title("Rod length stays 175mm (rigid constraint)")
    ax[0].set_xlabel("pose idx"); ax[0].set_ylabel("rod length (mm)")
    ax[0].set_ylim(tk.ROD - 1, tk.ROD + 1); ax[0].legend(fontsize=6, ncol=2)

    # (2) 闭环残差量级 (log)
    dts = [max(r["closure_dt_mm"], 1e-18) for r in reach]
    drs = [max(r["closure_dr_deg"], 1e-18) for r in reach]
    ax[1].semilogy(range(len(dts)), dts, "o-", ms=3, label="translation (mm)")
    ax[1].semilogy(range(len(drs)), drs, "s-", ms=3, label="rotation (deg)")
    ax[1].axhline(1e-6, color="r", ls="--", lw=1, label="CI tol 1e-6")
    ax[1].set_title("FK(IK(pose)) closure residual ~ machine eps")
    ax[1].set_xlabel("pose idx"); ax[1].set_ylabel("residual (log)")
    ax[1].legend(fontsize=7)

    # (3) 工作空间俯视 (X-Y) reachable vs not
    allp = report["poses"]
    for r in allp:
        x, y = r["pose"][0], r["pose"][1]
        ax[2].scatter(x, y, c=("tab:green" if r["reachable"] else "tab:red"),
                      s=40, marker=("o" if r["reachable"] else "x"))
    ax[2].set_title("Sampled workspace (green=closed, red=unreachable)")
    ax[2].set_xlabel("tx (mm)"); ax[2].set_ylabel("ty (mm)")
    ax[2].axhline(0, color="gray", lw=.5); ax[2].axvline(0, color="gray", lw=.5)
    ax[2].set_aspect("equal", "box")

    fig.suptitle("SR6 TRUE 3D parallel-mechanism closure (measured-truth geometry)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    rep = build_report()
    with open(os.path.join(OUT, "closure_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    make_figure(rep, os.path.join(OUT, "closure_figure.png"))
    a = rep["aggregate"]
    print("== SR6 closure report ==")
    print(f"  reachable {a['poses_reachable']}/{a['poses_total']}")
    print(f"  worst rod-length error : {a['worst_rod_err_mm']:.3e} mm")
    print(f"  worst closure (transl) : {a['worst_closure_dt_mm']:.3e} mm")
    print(f"  worst closure (rotate) : {a['worst_closure_dr_deg']:.3e} deg")
    print(f"  -> wrote {OUT}/closure_report.json + closure_figure.png")


if __name__ == "__main__":
    main()
