"""v2/probe_pivots.py -- firmware-grounded receiver pivots.

For each of the 6 real servo bearings (4 main + 2 pitch), build the servo's
in-plane basis and place the home receiver pivot exactly where the SR6 firmware
puts it:
  main : 162.48 mm forward + 15 mm up   (SetMainServo home x=16248,y=1500)
  pitch: pitch upper pivot via SetPitchServo home (x=16248,y=4500,z=+-side)
Render these predicted pivots as markers on the body to see if they land on the
real Receiver geometry (the validation that the servo-plane convention is right).
"""
import os, sys, numpy as np, trimesh
sys.path.insert(0, os.path.dirname(__file__))
from cylinders import detect_cylinders
from render import render_views

STL_DIR = os.path.join(os.path.dirname(__file__), "..", "ground_truth", "stl")
OUT = os.path.join(os.path.dirname(__file__), "..", "results")
BODY = ["Base", "Lid", "LFrame", "RFrame", "Receiver"]
COLORS = {"Base": "#9aa0a6", "Lid": "#3c4043", "LFrame": "#1f6fbf",
          "RFrame": "#1f6fbf", "Receiver": "#2a7fd0"}


def all_bearings(M):
    out = []
    for fn in ["LFrame", "RFrame"]:
        for c in detect_cylinders(M[fn], min_faces=8, min_r=15, max_r=25,
                                  lam_max=0.18, round_tol=0.35):
            a = c.axis / np.linalg.norm(c.axis)
            out.append((fn, c.center.copy(), a, c.radius))
    return out


def plane_basis(P, a, center):
    """servo in-plane basis: y=world-up in plane, x=toward receiver centre."""
    a = a / np.linalg.norm(a)
    z = np.array([0, 0, 1.0])
    y = z - np.dot(z, a) * a
    y = y / np.linalg.norm(y)
    x = np.cross(y, a); x = x / np.linalg.norm(x)
    if np.dot(center - P, x) < 0:   # point x toward the receiver
        x = -x
    return x, y


def sphere(c, r=4.0):
    s = trimesh.creation.icosphere(subdivisions=1, radius=r)
    s.apply_translation(c)
    return s


def main():
    M = {n: trimesh.load(os.path.join(STL_DIR, n + ".stl"), process=True) for n in BODY}
    rc = M["Receiver"].vertices.mean(axis=0)
    bearings = all_bearings(M)
    parts = [(M[n].vertices, M[n].faces, COLORS[n]) for n in BODY]
    print("receiver centroid", np.round(rc, 1))
    for fn, P, a, r in bearings:
        x, y = plane_basis(P, a, rc)
        kind = "main" if abs(abs(P[0]) - 88.4) < 4 else "pitch"
        if kind == "main":
            Q = P + 162.48 * x + 15.0 * y
            col = "#ff3030"
        else:
            Q = P + 162.48 * x + 45.0 * y   # pitch upper, simplified home
            col = "#30c030"
        d = np.linalg.norm(Q - rc)
        print(f"  {fn} {kind} P={np.round(P,1)} -> Q={np.round(Q,1)} |Q-rc|={d:.1f}")
        sp = sphere(Q)
        parts.append((sp.vertices, sp.faces, col))
    render_views(parts, os.path.join(OUT, "v2_pivots.png"),
                 title="firmware-predicted receiver pivots (red=main, green=pitch) on body")
    print("saved v2_pivots.png")


if __name__ == "__main__":
    main()
