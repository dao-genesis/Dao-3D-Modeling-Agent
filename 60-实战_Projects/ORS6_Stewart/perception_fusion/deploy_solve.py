# -*- coding: utf-8 -*-
"""道.感.校 · 展开位姿密搜: 在 T-Code 连续空间(thrust/fwd/side/roll/pitch)取网格,
每个真零件装配(6杆恒=175mm)→点云→相机位姿搜索→对照实物轮廓 IoU.
目的: 客观判定是否存在让接收环横向悬出、令 IoU 越过 home 的真实工作位姿."""
import os, sys, time, json, itertools
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_jiao as DJ
import fastfit as FF
import build_pose as BP

PHOTO = r"C:\Users\Administrator\attachments\1e3e689a-718b-47ac-a271-445caac3a39d\SmartSelect_20260626_115856_Baidu.jpg"
OUT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "output"))


def grid():
    """T-Code 候选. home=5000. 覆盖单轴大行程 + 关键双轴组合."""
    lvl = (1500, 3500, 5000, 6500, 8500)
    cand = {(5000, 5000, 5000, 5000, 5000, 5000)}
    # 单轴扫: thrust(L0), fwd(L1), side(L2), roll(R1), pitch(R2)
    for ax in range(6):
        if ax == 3:   # twist R0 视觉影响小, 跳过省时
            continue
        for v in lvl:
            p = [5000] * 6; p[ax] = v
            cand.add(tuple(p))
    # 双轴组合: fwd×side, thrust×fwd, thrust×side, roll×pitch
    pairs = [(1, 2), (0, 1), (0, 2), (4, 5)]
    for a, b in pairs:
        for va, vb in itertools.product((2500, 7500), repeat=2):
            p = [5000] * 6; p[a] = va; p[b] = vb
            cand.add(tuple(p))
    return sorted(cand)


def main():
    pm, rgb = DJ.load_photo(PHOTO)
    cands = grid()
    print(f"candidates: {len(cands)}", flush=True)
    results = []
    for i, pose in enumerate(cands):
        t = time.time()
        try:
            pts, info = BP.sample(pose, n=18000)
        except Exception as e:
            print(f"[{i}] {pose} build FAIL {e!r}", flush=True); continue
        ff = FF.FastFitter(pts)
        iou, az, el, mir, roll = ff.search(pm, az_step=36, els=(0, 20, 35, 50),
                                           coarse_res=140, fine=True, log=None)
        rmax = max(abs(x - 175.0) for x in info["rod_lens"])
        recv = info["recv"]
        results.append({"pose": list(pose), "iou": round(float(iou), 4),
                        "az": az, "el": el, "mir": mir, "roll": roll,
                        "rod_dev": round(rmax, 4),
                        "recv_xy": [round(recv[0], 1), round(recv[1], 1), round(recv[2], 1)]})
        print(f"[{i:2d}] {pose} IoU={iou:.4f} @az{az}el{el}m{mir}r{roll} "
              f"rod_dev={rmax:.3f} recvXY=({recv[0]:.0f},{recv[1]:.0f}) ({time.time()-t:.0f}s)",
              flush=True)
    results.sort(key=lambda r: -r["iou"])
    with open(os.path.join(OUT, "deploy_solve.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nTOP5:")
    for r in results[:5]:
        print(" ", r)


if __name__ == "__main__":
    main()
