# -*- coding: utf-8 -*-
"""Prepare Tripo mesh for perception: merge, bake texture->vertex color,
decimate, save a compact npz (V, F, vertex_colors) for fast iteration."""
import os, sys, time
import numpy as np
import trimesh
ROOT = os.path.dirname(os.path.abspath(__file__))

t0 = time.time()
scene = trimesh.load(os.path.join(ROOT, "tripo_decoded.glb"), process=False)
m = scene.to_geometry() if hasattr(scene, "to_geometry") else scene.dump(concatenate=True)
print("loaded", len(m.vertices), "V", len(m.faces), "F", round(time.time()-t0, 1), "s")

# bake texture -> vertex colors
try:
    cv = m.visual.to_color()
    vcol = np.asarray(cv.vertex_colors)[:, :3].astype(np.float64) / 255.0
    print("baked vertex colors", vcol.shape, "mean", np.round(vcol.mean(0), 3).tolist())
except Exception as e:
    print("color bake failed:", e)
    vcol = np.ones((len(m.vertices), 3)) * 0.7

# decimate for fast rendering
target = 120000
t1 = time.time()
try:
    md = m.simplify_quadric_decimation(face_count=target)
    print("decimated ->", len(md.vertices), "V", len(md.faces), "F", round(time.time()-t1, 1), "s")
    # remap colors by nearest original vertex
    from scipy.spatial import cKDTree
    tree = cKDTree(m.vertices)
    _, idx = tree.query(md.vertices, k=1)
    dvcol = vcol[idx]
    V, F = np.asarray(md.vertices), np.asarray(md.faces)
except Exception as e:
    print("decimation failed:", e, "-> using full mesh")
    V, F, dvcol = np.asarray(m.vertices), np.asarray(m.faces), vcol

np.savez_compressed(os.path.join(ROOT, "tripo_prepped.npz"),
                    V=V.astype(np.float32), F=F.astype(np.int32),
                    vcol=dvcol.astype(np.float32))
print("SAVED tripo_prepped.npz  V", V.shape, "F", F.shape)
print("bounds", np.round(V.min(0), 3).tolist(), np.round(V.max(0), 3).tolist())
