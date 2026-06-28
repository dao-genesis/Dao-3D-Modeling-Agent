#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render the SR6 full assembly from build_v2's assembly_transforms.json.

Structure at identity; arms on measured servo shafts; receiver group at the
solved 6-DOF home pose; real Main/Pitch link STLs placed spanning each
arm-ball -> receiver-pivot.  Outputs 5 shaded views + a GLB.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, trimesh
from partmap import PARTS

HERE = os.path.dirname(__file__)
ASM = json.load(open(os.path.join(HERE, "assembly_transforms.json")))

RED=(0.82,0.11,0.10); WHITE=(0.90,0.90,0.92); GREY=(0.45,0.45,0.50)
DARK=(0.16,0.16,0.18); STEEL=(0.55,0.57,0.62)

def apply(M, mesh):
    m = mesh.copy(); m.apply_transform(np.array(M)); return m

def load(k):
    return trimesh.load(PARTS[k], force="mesh")

def link_local(mesh):
    """near ball (+Y extreme centroid), far ball (-Y extreme centroid)."""
    v = mesh.vertices; span = v[:,1].max()-v[:,1].min()
    near = v[v[:,1] >= v[:,1].max()-0.06*span].mean(0)
    far  = v[v[:,1] <= v[:,1].min()+0.06*span].mean(0)
    return near, far

def seg_register(mesh, p0, p1, q0, q1):
    """Rigid map local seg p0->p1 onto world q0->q1 (no scaling)."""
    a = p1-p0; b = q1-q0
    au = a/np.linalg.norm(a); bu = b/np.linalg.norm(b)
    v = np.cross(au, bu); s = np.linalg.norm(v); c = au@bu
    if s < 1e-9:
        R = np.eye(3) if c > 0 else np.diag([1.,-1,-1])
    else:
        vx = np.array([[0,-v[2],v[1]],[v[2],0,-v[0]],[-v[1],v[0],0]])
        R = np.eye(3)+vx+vx@vx*((1-c)/s**2)
    M = np.eye(4); M[:3,:3]=R; M[:3,3]=q0-R@p0
    return M

def build():
    items = []
    # structure (shared CAD frame -> identity)
    items.append(("Base", load("Base"), np.eye(4), RED))
    items.append(("Lid",  load("Lid"),  np.eye(4), RED))
    items.append(("L_Frame", load("L_Frame"), np.eye(4), DARK))
    items.append(("R_Frame", load("R_Frame"), np.eye(4), DARK))

    # arms
    marm = load("MainArm")
    for k in ("R_up","R_lo","L_up","L_lo"):
        items.append((f"Arm_{k}", marm, ASM["arm_xforms"][k], WHITE))
    items.append(("Arm_L_p", load("L_Pitcher"), np.eye(4), WHITE))
    items.append(("Arm_R_p", load("R_Pitcher"), np.eye(4), WHITE))

    # receiver group at solved home pose
    Mr = np.array(ASM["receiver_M"])
    items.append(("Receiver", load("Receiver"), Mr, RED))

    # links spanning ball(arm) -> pivot(receiver)
    ml = load("MainLink"); pl = load("PitchLink")
    mn, mf = link_local(ml); pn, pf = link_local(pl)
    for k, leg in ASM["legs"].items():
        ball = np.array(leg["ball"]); piv = np.array(leg["pivot"])
        if k.endswith("_p"):
            M = seg_register(pl, pn, pf, ball, piv)
            items.append((f"Link_{k}", pl, M, RED))
        else:
            M = seg_register(ml, mn, mf, ball, piv)
            items.append((f"Link_{k}", ml, M, RED))
    return items

def _shade(tris, base, key=(0.4,0.5,1.0), fill=(-0.6,-0.3,0.4), ka=0.32):
    n = np.cross(tris[:,1]-tris[:,0], tris[:,2]-tris[:,0])
    ln = np.linalg.norm(n,axis=1,keepdims=True); ln[ln==0]=1; n=n/ln
    def lit(L):
        L=np.array(L,float); L=L/np.linalg.norm(L); return np.clip(n@L,0,1)
    inten = np.clip(ka+0.60*lit(key)+0.28*lit(fill),0,1)[:,None]
    return np.clip(np.array(base,float)[None,:]*inten,0,1)

def render(items, out_prefix):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    all_tris=[]; all_col=[]
    for name, mesh, M, color in items:
        m = apply(M, mesh); tris = m.vertices[m.faces]
        all_tris.append(tris); all_col.append(_shade(tris,color))
    all_tris=np.concatenate(all_tris,0); all_col=np.concatenate(all_col,0)
    print(f"rendering {len(all_tris)} faces")
    views=[("iso",20,-58),("front",4,-90),("side",4,0),("top",88,-90),("hero",14,-120)]
    for vn,elev,azim in views:
        fig=plt.figure(figsize=(10,10)); ax=fig.add_subplot(111,projection="3d")
        pc=Poly3DCollection(all_tris,shade=False)
        pc.set_facecolor(all_col); pc.set_edgecolor("none"); ax.add_collection3d(pc)
        ax.set_xlim(-130,130); ax.set_ylim(-90,150); ax.set_zlim(-20,270)
        ax.set_box_aspect((260,240,290)); ax.view_init(elev=elev,azim=azim)
        ax.set_axis_off(); fig.patch.set_facecolor("white")
        p=f"{out_prefix}_{vn}.png"
        fig.savefig(p,dpi=145,bbox_inches="tight",facecolor="white"); plt.close(fig)
        print("wrote",p)

def export_glb(items, out_path):
    sc=trimesh.Scene()
    for name,mesh,M,color in items:
        m=apply(M,mesh)
        m.visual=trimesh.visual.ColorVisuals(mesh=m,
            face_colors=np.tile((np.array(color)*255).astype(np.uint8),(len(m.faces),1)))
        sc.add_geometry(m,node_name=name,geom_name=name)
    sc.export(out_path); print("wrote",out_path)

if __name__=="__main__":
    items=build()
    out=os.path.join(HERE,"renders")
    os.makedirs(out,exist_ok=True)
    render(items, os.path.join(out,"sr6v2"))
    export_glb(items, os.path.join(out,"sr6_assembly.glb"))
