#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SR6 full assembly, measurement-driven, in the shared CAD (STL identity) frame.

Structure (base/lid/frames/twist) is authored in a shared assembly frame -> placed
at identity.  Arms are authored sitting on their servo horns; the single MainArm STL
is replicated to the 4 measured main-servo shafts (L/R x upper/lower).  The receiver
ring is authored at print origin and is moved (rigid translation solved by least
squares) to its home pose so the 6 ball-jointed links span ~link-length.  The real
Main/Pitch link STLs are then placed spanning each arm ball -> receiver pivot.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, trimesh
from scipy.optimize import least_squares
from partmap import PARTS

# ---- measured servo shaft centres (identity frame, axis || X) ----------------
SERVO = {
    "R_up": (83.2,  30.0, 24.0),
    "R_lo": (87.2, -31.5, 21.0),
    "L_up": (-83.2, 30.0, 24.0),
    "L_lo": (-87.3,-31.5, 21.4),
    "R_p":  (84.4,   0.1, 20.6),
    "L_p":  (-84.4,  0.1, 20.6),
}
# receiver pivot axles (identity receiver frame, axis || X)
MAIN_AXLE  = np.array([0.0, -6.7, 26.1])     # main bearing bore
PITCH_AXLE = np.array([0.0, -14.2, 53.1])    # pitch axle (== firmware pitch pivot)


def T(t):
    M = np.eye(4); M[:3, 3] = t; return M

def mirror_x():
    M = np.eye(4); M[0, 0] = -1; return M

def apply(M, mesh):
    m = mesh.copy(); m.apply_transform(M); return m

def ball_of(mesh, frac=0.06):
    """Ball-socket centre = centroid of the vertices nearest the +Y extreme."""
    v = mesh.vertices
    ymax = v[:, 1].max()
    sel = v[v[:, 1] >= ymax - (v[:,1].max()-v[:,1].min())*frac]
    return sel.mean(0)


def main():
    # ---------------- arms -----------------------------------------------------
    main_arm = trimesh.load(PARTS["MainArm"], force="mesh")
    # reference arm sits on R_up; build the 4 placements
    s0 = np.array(SERVO["R_up"])
    arm_xforms = {
        "R_up": T(np.zeros(3)),
        "R_lo": T(np.array(SERVO["R_lo"]) - s0),
        "L_up": mirror_x(),
        "L_lo": mirror_x() @ T(np.array(SERVO["R_lo"]) - s0),
    }
    arm_meshes = {k: apply(M, main_arm) for k, M in arm_xforms.items()}
    l_pit = trimesh.load(PARTS["L_Pitcher"], force="mesh")
    r_pit = trimesh.load(PARTS["R_Pitcher"], force="mesh")
    arm_meshes["L_p"] = l_pit
    arm_meshes["R_p"] = r_pit

    balls = {k: ball_of(m) for k, m in arm_meshes.items()}

    # ---------------- receiver pivots (identity, before move) ------------------
    piv0 = {
        "R_up": MAIN_AXLE + [ 60, 0, 0],
        "R_lo": MAIN_AXLE + [ 33, 0, 0],
        "L_up": MAIN_AXLE + [-60, 0, 0],
        "L_lo": MAIN_AXLE + [-33, 0, 0],
        "R_p":  PITCH_AXLE + [ 57, 0, 0],
        "L_p":  PITCH_AXLE + [-57, 0, 0],
    }
    legs = ["R_up", "R_lo", "L_up", "L_lo", "R_p", "L_p"]
    target = {k: (186.0 if k.endswith("_p") else 175.0) for k in legs}

    B = np.array([balls[k] for k in legs])
    P0 = np.array([piv0[k] for k in legs])     # receiver-local pivots
    tg = np.array([target[k] for k in legs])

    def rot(rx, ry, rz):
        cx,sx=np.cos(rx),np.sin(rx); cy,sy=np.cos(ry),np.sin(ry); cz,sz=np.cos(rz),np.sin(rz)
        Rx=np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
        Ry=np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
        Rz=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])
        return Rz@Ry@Rx

    def resid(p):
        R = rot(*p[3:]); t = p[:3]
        P = (R @ P0.T).T + t
        d = np.linalg.norm(P - B, axis=1)
        return d - tg
    sol = least_squares(resid, x0=[0, 60, 185, 0, 0, 0])
    t_recv = sol.x[:3]; R_recv = rot(*sol.x[3:])
    Mrecv = np.eye(4); Mrecv[:3,:3]=R_recv; Mrecv[:3,3]=t_recv
    P = (R_recv @ P0.T).T + t_recv
    d = np.linalg.norm(P - B, axis=1)
    print("receiver pose t=",np.round(t_recv,1)," rot(deg)=",np.round(np.degrees(sol.x[3:]),1))
    print("=== leg ball -> pivot lengths (target main175 / pitch186) ===")
    for i, k in enumerate(legs):
        print("  %-5s ball=%s pivot=%s  len=%.1f (tgt %.0f)"
              % (k, np.round(B[i],1), np.round(P[i],1), d[i], tg[i]))

    print("  link RMS error = %.2f mm" % np.sqrt(np.mean((d-tg)**2)))
    out = {"servo": SERVO,
           "arm_xforms": {k: M.tolist() for k, M in arm_xforms.items()},
           "receiver_M": Mrecv.tolist(),
           "legs": {k: {"ball": B[i].tolist(), "pivot": P[i].tolist(),
                        "length": float(d[i]), "target": float(tg[i])}
                    for i, k in enumerate(legs)}}
    json.dump(out, open(os.path.join(os.path.dirname(__file__),
              "assembly_transforms.json"), "w"), indent=2)
    print("wrote assembly_transforms.json")


if __name__ == "__main__":
    main()
