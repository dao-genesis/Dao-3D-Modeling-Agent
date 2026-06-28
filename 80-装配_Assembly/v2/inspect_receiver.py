"""v2/inspect_receiver.py -- find all rod-attachment pivots on the receiver.

Render the Receiver alone from several angles with detected cylinder axes drawn,
so we can read off the 4 main + 2 pitch clevis pin locations from real geometry.
"""
import os, sys, numpy as np, trimesh
sys.path.insert(0, os.path.dirname(__file__))
from cylinders import detect_cylinders
from render import render_views
import matplotlib
matplotlib.use("Agg")

STL_DIR = os.path.join(os.path.dirname(__file__), "..", "ground_truth", "stl")
OUT = os.path.join(os.path.dirname(__file__), "..", "results")


def cyl_marker(c, length=14.0, r=1.2, n=10):
    """small tube along the cylinder axis for visualization."""
    T = trimesh.transformations.translation_matrix(c.center)
    a = c.axis / np.linalg.norm(c.axis)
    z = np.array([0, 0, 1.0])
    v = np.cross(z, a); s = np.linalg.norm(v)
    if s < 1e-6:
        R = np.eye(4)
    else:
        cth = np.dot(z, a)
        vx = np.array([[0,-v[2],v[1]],[v[2],0,-v[0]],[-v[1],v[0],0]])
        Rm = np.eye(3) + vx + vx@vx*((1-cth)/(s*s))
        R = np.eye(4); R[:3,:3] = Rm
    m = trimesh.creation.cylinder(radius=r, height=length)
    m.apply_transform(R); m.apply_transform(T)
    return m


def main():
    m = trimesh.load(os.path.join(STL_DIR, "Receiver.stl"), process=True)
    cyls = detect_cylinders(m, min_faces=4, min_r=1.0, max_r=15, lam_max=0.18, round_tol=0.35)
    print("receiver small/mid cylinders (candidate pivots):")
    for c in cyls:
        print("   ", c)
    parts = [(m.vertices, m.faces, "#2a7fd0")]
    for c in cyls:
        mk = cyl_marker(c, length=40)
        parts.append((mk.vertices, mk.faces, "#ff0000"))
    render_views(parts, os.path.join(OUT, "v2_receiver_feats.png"),
                 title="Receiver + detected pivot axes (red)")
    print("saved v2_receiver_feats.png")


if __name__ == "__main__":
    main()
