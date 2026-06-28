# -*- coding: utf-8 -*-
"""三向融合校验 — fuse & judge all three directions against the real photo.

道并行而不相悖 — the three directions are complementary, judged by one oracle:

  方向一 (Tripo 视觉网格)  : tripo_prepped.npz   — the human-validated visual mesh
  方向二 (固件骨架 STL)    : ../output/ORS6_*.stl — the trusted IK/CAD skeleton
  方向三 (道.感.校 感知)   : dao_jiao.PoseFitter  — the silhouette IoU judge

For every model we search camera pose for the best envelope-silhouette IoU vs
the segmented SR6 photo, then assemble one comparison figure + a metrics table.
This is honest perception: no model is praised by the eye, only by the number.
"""
from __future__ import annotations
import os, sys, json, time
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

PHOTO = r"C:\Users\Administrator\attachments\1e3e689a-718b-47ac-a271-445caac3a39d\SmartSelect_20260626_115856_Baidu.jpg"
OUT = os.path.join(HERE, "output")
os.makedirs(OUT, exist_ok=True)

# firmware skeleton poses to test (subset; deployment ≠ home)
FW_POSES = ["home", "forward", "extreme", "thrust_up", "combo_diag"]


def decimate(V, F, target_faces=14000):
    try:
        import fast_simplification as fs
        if len(F) <= target_faces:
            return V, F
        Vd, Fd = fs.simplify(V.astype(np.float32), F.astype(np.int32),
                             target_reduction=1.0 - target_faces / len(F))
        return Vd.astype(float), Fd.astype(int)
    except Exception as e:
        print("  (decimate skipped:", e, ")")
        return V, F


def main():
    photo_mask, photo_rgb = dj.load_photo(PHOTO)
    print(f"photo silhouette coverage {photo_mask.mean():.3f}")

    results = []
    renders = {}

    # ---- 方向一: Tripo visual mesh ----
    d = np.load(os.path.join(HERE, "tripo_prepped.npz"))
    pf = dj.PoseFitter(d["V"], d["F"], d["vcol"])
    t0 = time.time()
    print("[Tripo] searching pose ...")
    s, az, el, mir, roll = pf.search(photo_mask)
    img, mm = pf.fitted_render(az, el, mir, roll)
    fiou = dj.iou(dj.fit_norm(photo_mask), dj.fit_norm(mm))
    print(f"[Tripo] IoU={fiou:.3f} pose=az{az}el{el}m{mir}r{roll} ({time.time()-t0:.0f}s)")
    results.append({"model": "Tripo visual mesh", "direction": 1, "iou": round(fiou, 3),
                    "pose": {"az": int(az), "el": int(el), "mirror": int(mir), "roll": int(roll)}})
    renders["Tripo"] = (img, fiou, f"az{az} el{el} m{mir} r{roll}")

    # ---- 方向二: firmware skeleton STLs ----
    import trimesh
    best_fw = None
    for name in FW_POSES:
        p = os.path.join(HERE, "..", "output", f"ORS6_{name}.stl")
        if not os.path.exists(p):
            print(f"[fw:{name}] missing, skip")
            continue
        m = trimesh.load(p, force="mesh")
        V, F = decimate(np.asarray(m.vertices, float), np.asarray(m.faces, int))
        fitter = dj.PoseFitter(V, F)
        t0 = time.time()
        print(f"[fw:{name}] searching pose ({len(F)} faces) ...")
        s, az, el, mir, roll = fitter.search(photo_mask, az_step=30,
                                             els=(-20, 0, 20, 40, 60), fine=False)
        img, mm = fitter.fitted_render(az, el, mir, roll)
        fiou = dj.iou(dj.fit_norm(photo_mask), dj.fit_norm(mm))
        print(f"[fw:{name}] IoU={fiou:.3f} pose=az{az}el{el}m{mir}r{roll} ({time.time()-t0:.0f}s)")
        results.append({"model": f"firmware skeleton ({name})", "direction": 2,
                        "iou": round(fiou, 3),
                        "pose": {"az": int(az), "el": int(el), "mirror": int(mir), "roll": int(roll)}})
        if best_fw is None or fiou > best_fw[1]:
            best_fw = (name, fiou, img)

    # ---- figure ----
    cols = 3
    fig, axs = plt.subplots(1, cols, figsize=(cols * 5, 5.2))
    axs[0].imshow(photo_rgb); axs[0].set_title("real SR6 photo (本源)"); axs[0].axis("off")
    ti, tiou, tpose = renders["Tripo"]
    axs[1].imshow(ti); axs[1].set_title(f"方向一 Tripo  IoU={tiou:.2f}\n{tpose}"); axs[1].axis("off")
    if best_fw is not None:
        axs[2].imshow(best_fw[2])
        axs[2].set_title(f"方向二 固件骨架 best={best_fw[0]}\nIoU={best_fw[1]:.2f}")
    axs[2].axis("off")
    plt.tight_layout()
    figp = os.path.join(OUT, "fusion_compare.png")
    plt.savefig(figp, dpi=100, bbox_inches="tight")
    print("saved figure")

    summary = {
        "photo": os.path.basename(PHOTO),
        "judge": "道.感.校 envelope-silhouette IoU (scale/rotation/mirror invariant)",
        "results": sorted(results, key=lambda r: -r["iou"]),
        "tripo_best_iou": round(renders["Tripo"][1], 3),
        "firmware_best_iou": round(best_fw[1], 3) if best_fw else None,
    }
    with open(os.path.join(OUT, "fusion_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("saved metrics; tripo=%.3f firmware=%.3f" % (
        summary["tripo_best_iou"], summary["firmware_best_iou"]))


if __name__ == "__main__":
    main()
