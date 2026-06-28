# -*- coding: utf-8 -*-
"""三向归一 — fuse the Tripo visual mesh into the firmware coordinate frame.

道并行而不相悖.  This is the concrete fusion of the three directions:

  方向一 (Tripo mesh)   provides the *visual truth* + the true crossed-rod
                        topology + the receiver ring as actually built.
  方向二 (firmware)     provides the *metric scale* (rod=175mm, AABB) and the
                        coordinate convention (base at Z=0, ring up at +Z).
  方向三 (道.感.校)      is the judge that ties the fused model to the photo.

Output:
  - tripo_fused.npz  : Tripo mesh re-oriented to base-at-origin / ring-up,
                       scaled to millimetres, with per-vertex semantic labels.
  - the receiver-ring datum (center, radius, normal) extracted from the mesh,
    i.e. the *correct* assembly geometry that the firmware skeleton lacked.
"""
from __future__ import annotations
import os, sys, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# firmware metric reference (from geometry.py / prior verify): real device AABB
FW_AABB = np.array([277.7, 192.2, 289.5])  # mm
ROD_LEN_MM = 175.0
FW_RING_DIAM_MM = 114.0  # firmware receiver ring outer Ø


def classify(C):
    """Per-vertex semantic class from baked colour. white arms are cream, so
    use saturation/brightness rather than pure-white test."""
    r, g, b = C[:, 0], C[:, 1], C[:, 2]
    mx, mn = C.max(1), C.min(1)
    sat = mx - mn
    red = (r > 0.40) & (r - g > 0.16) & (r - b > 0.13)
    metal = (~red) & (sat < 0.10) & (mx >= 0.30) & (mx < 0.72)
    cream = (~red) & (~metal) & (mx >= 0.55)  # light arms
    lab = np.zeros(len(C), int)  # 0=other
    lab[red] = 1
    lab[metal] = 2
    lab[cream] = 3
    return lab  # 1 red(frame/rods/ring) 2 metal(joints) 3 cream(arms)


def fit_circle_3d(P):
    """Fit a circle to ~coplanar 3D points. Returns center, radius, normal."""
    c = P.mean(0)
    Q = P - c
    _, _, Wt = np.linalg.svd(Q, full_matrices=False)
    normal = Wt[2]
    u, v = Wt[0], Wt[1]
    x, y = Q @ u, Q @ v
    A = np.c_[2 * x, 2 * y, np.ones(len(x))]
    sol, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    cx, cy = sol[0], sol[1]
    radius = float(np.sqrt(max(sol[2] + cx * cx + cy * cy, 0)))
    center = c + cx * u + cy * v
    return center, radius, normal


def main():
    d = np.load(os.path.join(HERE, "tripo_prepped.npz"))
    V, F, C = d["V"].astype(float), d["F"].astype(int), d["vcol"].astype(float)
    lab = classify(C)
    print("classes red=%d metal=%d cream=%d other=%d" %
          ((lab == 1).sum(), (lab == 2).sum(), (lab == 3).sum(), (lab == 0).sum()))

    # ---- principal axis = base->ring ----
    ctr = V.mean(0)
    Vc = V - ctr
    _, _, Wt = np.linalg.svd(Vc, full_matrices=False)
    axis = Wt[0]
    t = Vc @ axis
    # orient axis so the cream arms (servo side / base) sit at NEGATIVE t,
    # ring at positive t
    if (t[lab == 3].mean() if (lab == 3).any() else 0) > 0:
        axis, t = -axis, -t

    # build orthonormal frame with axis -> +Z
    z = axis / np.linalg.norm(axis)
    x = Wt[1] - (Wt[1] @ z) * z
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    Rot = np.c_[x, y, z]            # columns are new basis in old coords
    Vrot = Vc @ Rot                # now axis is +Z

    # ---- scale to mm: match the longest AABB edge to firmware AABB max ----
    size = Vrot.max(0) - Vrot.min(0)
    scale = float(FW_AABB.max() / size.max())
    Vmm = Vrot * scale
    # drop base to Z=0
    Vmm[:, 2] -= Vmm[:, 2].min()
    size_mm = Vmm.max(0) - Vmm.min(0)
    print("fused AABB mm", np.round(size_mm, 1), " scale=%.1f mm/unit" % scale)

    # ---- extract receiver ring: red verts in the top axial band ----
    z_mm = Vmm[:, 2]
    top = z_mm > (z_mm.max() - 0.18 * size_mm[2])
    ring_pts = Vmm[(lab == 1) & top]
    center, radius, normal = fit_circle_3d(ring_pts)
    # tilt of ring plane vs base XY-plane
    tilt_deg = float(np.degrees(np.arccos(min(abs(normal[2]), 1.0))))
    print("RING center mm", np.round(center, 1), "radius %.1f mm" % radius,
          "tilt %.1f deg" % tilt_deg)

    # ---- base centroid (cream arms / lower red) ----
    base_band = z_mm < (z_mm.min() + 0.30 * size_mm[2])
    base_ctr = Vmm[base_band].mean(0)
    standoff = float(center[2] - base_ctr[2])  # base->ring axial standoff
    lateral = float(np.hypot(center[0] - base_ctr[0], center[1] - base_ctr[1]))
    print("base->ring axial standoff %.1f mm, lateral offset %.1f mm" % (standoff, lateral))

    np.savez_compressed(os.path.join(HERE, "tripo_fused.npz"),
                        V=Vmm.astype(np.float32), F=F.astype(np.int32),
                        vcol=C.astype(np.float32), label=lab.astype(np.int8))

    datum = {
        "frame": "base centroid at origin region, +Z = base->ring axis, millimetres",
        "scale_mm_per_unit": round(scale, 2),
        "fused_aabb_mm": [round(float(s), 1) for s in size_mm],
        "receiver_ring": {
            "center_mm": [round(float(c), 1) for c in center],
            "radius_mm": round(radius, 1),
            "outer_diam_mm": round(radius * 2, 1),
            "plane_tilt_deg": round(tilt_deg, 1),
        },
        "base_to_ring_axial_standoff_mm": round(standoff, 1),
        "ring_lateral_offset_mm": round(lateral, 1),
        "firmware_ring_outer_diam_mm": FW_RING_DIAM_MM,
        "ring_diam_vs_firmware": {
            "tripo_mm": round(radius * 2, 1), "firmware_mm": FW_RING_DIAM_MM,
            "delta_mm": round(radius * 2 - FW_RING_DIAM_MM, 1),
        },
        "note": ("Tripo mesh carries a tilted, laterally-offset receiver ring held out "
                 "from the base by the crossed rod-fan; the firmware skeleton placed the "
                 "ring coaxial & centred over the base (lateral offset ~0). That lateral "
                 "offset + plane tilt is the assembly error the firmware lacked."),
    }
    with open(os.path.join(HERE, "output", "ring_datum.json"), "w", encoding="utf-8") as f:
        json.dump(datum, f, ensure_ascii=False, indent=2)
    print(json.dumps(datum, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
