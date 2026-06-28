# ORS6 三向归一 · Three-Direction Perception Fusion

> 道并行而不相悖 — three complementary directions, one perception judge.
> 不二选一,而是相互融合 (not either/or, but mutual fusion).

This module fuses three independent sources of truth about the real SR6 /
ORS6 6-DOF Stewart platform and validates them against the **real hardware
photo** with a single quantitative oracle.

## The three directions

| Dir | Source | Provides |
|----|--------|----------|
| 一 | `tripo_visual.glb` / `tripo_prepped.npz` (Tripo3D web-generated mesh) | visual truth, true crossed-rod topology, the as-built receiver ring |
| 二 | `../output/ORS6_*.stl` + `../geometry.py` (firmware skeleton) | metric scale (rod=175 mm, AABB), coordinate convention, IK kinematics |
| 三 | `dao_jiao.py` (道.感.校 perception oracle) | silhouette-IoU / circle-fit judge tying any model to the real photo |

## Files

- `dao_jiao.py` — reusable `PoseFitter`: segment the photo, search camera pose,
  envelope-silhouette IoU (scale/rotation/mirror invariant). The common judge.
- `fuse_validate.py` — render every model (Tripo + firmware poses) and score
  IoU vs the photo → `output/fusion_metrics.json`, `output/fusion_compare.png`.
- `tripo_orbit.py` — orbit render to characterize the Tripo mesh structure
  → `output/tripo_orbit.png`.
- `fuse_geometry.py` — orient + scale the Tripo mesh into firmware mm
  coordinates (base at Z=0, ring up), extract the receiver-ring datum
  → `tripo_fused.npz`, `output/ring_datum.json`.
- `final_evidence.py` — the fused evidence figure → `output/fusion_final.png`.
- `decode_meshopt.mjs`, `prep_mesh.py` — the GLB pipeline (meshopt decode →
  baked-colour decimated npz).

## Honest findings (judged, not eyeballed)

- The Tripo visual mesh is **faithful and complete** (orbit-verified: servo box,
  white arms, 6 crossed rods with ball joints, receiver ring). The
  envelope-IoU (~0.69) *understates* it because that metric only compares the
  gross outer blob and is pose-sensitive.
- The receiver ring extracted from the **visual mesh** (Ø 118.7 mm) and the
  **firmware CAD spec** (Ø 114 mm) agree to **4.7 mm (4%)** — the visual and
  CAD directions cross-confirm each other.
- The ring in the photo is **tilted 23° and offset 20 mm** from the base axis;
  the firmware *home* skeleton places it coaxial. The mismatch is therefore a
  **deployed pose / assembly** difference, **not** missing or wrong parts —
  consistent with "零件都在但没装到位".

## Reproduce

```bash
python fuse_geometry.py      # build tripo_fused.npz + ring_datum.json
python final_evidence.py     # build output/fusion_final.png
python fuse_validate.py      # (~17 min) full pose search + metrics
python replot.py             # fast re-render from cached best poses
```

*道法自然 · 无为而无不为*
