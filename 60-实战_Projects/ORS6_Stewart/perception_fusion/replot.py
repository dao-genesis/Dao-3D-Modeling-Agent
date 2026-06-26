# -*- coding: utf-8 -*-
"""Fast re-render of the fusion diagnosis using cached best poses (no search).

The expensive pose search in fuse_validate.py is cached here as BEST so the
annotated figure + metrics can be regenerated in seconds.  ASCII titles avoid
missing-CJK tofu in matplotlib.
"""
from __future__ import annotations
import os, sys, json
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dao_jiao as dj
import trimesh

PHOTO = r"C:\Users\Administrator\attachments\1e3e689a-718b-47ac-a271-445caac3a39d\SmartSelect_20260626_115856_Baidu.jpg"
OUT = os.path.join(HERE, "output")
os.makedirs(OUT, exist_ok=True)

# cached best poses from fuse_validate.py search (envelope-IoU)
BEST = {
    "Tripo visual mesh":          dict(dir=1, iou=0.687, az=355, el=28, mir=1, roll=210),
    "firmware skeleton (home)":   dict(dir=2, iou=0.638, az=270, el=60, mir=1, roll=45),
    "firmware skeleton (forward)":dict(dir=2, iou=0.626, az=270, el=60, mir=1, roll=45),
    "firmware skeleton (extreme)":dict(dir=2, iou=0.657, az=270, el=60, mir=0, roll=45),
    "firmware skeleton (thrust_up)":dict(dir=2, iou=0.648, az=270, el=60, mir=0, roll=45),
    "firmware skeleton (combo_diag)":dict(dir=2, iou=0.647, az=270, el=60, mir=0, roll=45),
}


def decimate(V, F, target=14000):
    import fast_simplification as fs
    if len(F) <= target:
        return V, F
    Vd, Fd = fs.simplify(V.astype(np.float32), F.astype(np.int32),
                         target_reduction=1.0 - target / len(F))
    return Vd.astype(float), Fd.astype(int)


def main():
    photo_mask, photo_rgb = dj.load_photo(PHOTO)

    d = np.load(os.path.join(HERE, "tripo_prepped.npz"))
    pf_tripo = dj.PoseFitter(d["V"], d["F"], d["vcol"])
    bt = BEST["Tripo visual mesh"]
    tripo_img, _ = pf_tripo.fitted_render(bt["az"], bt["el"], bt["mir"], bt["roll"])

    m = trimesh.load(os.path.join(HERE, "..", "output", "ORS6_extreme.stl"), force="mesh")
    V, F = decimate(np.asarray(m.vertices, float), np.asarray(m.faces, int))
    pf_fw = dj.PoseFitter(V, F)
    bf = BEST["firmware skeleton (extreme)"]
    fw_img, _ = pf_fw.fitted_render(bf["az"], bf["el"], bf["mir"], bf["roll"])

    fig, axs = plt.subplots(1, 3, figsize=(15, 5.4))
    axs[0].imshow(photo_rgb)
    axs[0].set_title("real SR6 photo (ground truth)", fontsize=12)
    axs[1].imshow(tripo_img)
    axs[1].set_title("Dir.1  Tripo visual mesh\nenvelope-IoU=%.2f  (has rods+arms, RING MISSING)"
                     % bt["iou"], fontsize=11)
    axs[2].imshow(fw_img)
    axs[2].set_title("Dir.2  firmware skeleton (extreme)\nenvelope-IoU=%.2f  (has RING, rod-fan missing)"
                     % bf["iou"], fontsize=11)
    for a in axs:
        a.axis("off")
    fig.suptitle("Dao.Gan.Jiao perception oracle - three directions vs real photo  (judge: silhouette IoU)",
                 fontsize=12)
    plt.tight_layout()
    figp = os.path.join(OUT, "fusion_compare.png")
    plt.savefig(figp, dpi=110, bbox_inches="tight")
    print("saved figure")

    results = []
    for name, b in BEST.items():
        results.append({"model": name, "direction": b["dir"], "iou": b["iou"],
                        "pose": {"az": b["az"], "el": b["el"], "mirror": b["mir"], "roll": b["roll"]}})
    fw_ious = [b["iou"] for n, b in BEST.items() if b["dir"] == 2]
    summary = {
        "photo": os.path.basename(PHOTO),
        "judge": "Dao.Gan.Jiao envelope-silhouette IoU (scale/rotation/mirror invariant)",
        "note": ("envelope-IoU compares only the gross outer blob, so it saturates ~0.66-0.69 "
                 "for ALL models; the decisive difference is internal/topological: Tripo carries "
                 "the rod-fan + servo arms but not the receiver ring, the firmware skeleton carries "
                 "the ring + kinematics but not the crossed rod-fan. The two directions are "
                 "complementary -> fusion is required."),
        "results": sorted(results, key=lambda r: -r["iou"]),
        "tripo_best_iou": BEST["Tripo visual mesh"]["iou"],
        "firmware_best_iou": max(fw_ious),
    }
    with open(os.path.join(OUT, "fusion_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("tripo=%.3f firmware=%.3f" % (summary["tripo_best_iou"], summary["firmware_best_iou"]))


if __name__ == "__main__":
    main()
