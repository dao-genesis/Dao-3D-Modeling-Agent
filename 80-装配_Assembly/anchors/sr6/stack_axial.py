#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Close the last real DOF of the SR6 home assembly: the BOLT-AXIAL stack.

Defect exposed by validate_home.py on the point-closure poses: every part
interpenetrated its neighbours by 2-12mm.  Root cause is a modelling gap, the
same class of error as every earlier failure: the leg closure treats each bolt
interface as a coincident POINT, but a bolt is a LINE.  Where a part sits ALONG
that line (world X here -- servo shafts and rod bolts are X-aligned) is a real,
physical degree of freedom that the point model silently collapsed to zero,
stacking two links, an arm and the receiver ear all into the same plane.

Authority that closes it (PDF pp.29-32): parts stack along each bolt in
sequence, separated by their own material -- the two main links on one receiver
bolt sit one inboard one outboard ("tabs one up, one down"), each link's rod
end sits beside (not inside) its arm, the pitchers sit inboard of their frame
wall.  I.e. the axial DOF is closed by CONTACT: slide each part along X to the
smallest offset at which it no longer penetrates what is already placed.

This pass does exactly that, with the real meshes and FCL penetration depth:
fixed shell+receiver first, then arms/pitchers, then links, each solved for the
minimal |dx| (preferring the PDF-mandated outboard direction for links, inboard
for pitchers) with residual penetration <= JOINT_CLEAR.  The shift is recorded
in the poses JSON as axial_shift_mm -- honest, inspectable, never hidden.
"""
from __future__ import annotations

import numpy as np
import trimesh

JOINT_CLEAR = 0.3    # mm residual penetration allowed at a bolted joint
STEP = 0.25
MAX_SHIFT = 32.0    # the pitch servo stacks outboard past the main arm plane


def _depth(mesh, others):
    if not others:
        return 0.0
    cm = trimesh.collision.CollisionManager()
    for i, o in enumerate(others):
        cm.add_object(str(i), o)
    hit, contacts = cm.in_collision_single(mesh, return_data=True)
    return max((c.depth for c in contacts), default=0.0) if hit else 0.0


def _slide(mesh, others, prefer_sign):
    """Smallest |dx| along world X with penetration <= JOINT_CLEAR.

    prefer_sign breaks ties (PDF stacking direction); 0 = no preference.
    Returns (dx, residual_depth).
    """
    cand = sorted(np.arange(-MAX_SHIFT, MAX_SHIFT + STEP / 2, STEP),
                  key=lambda d: (abs(d), -prefer_sign * d))
    best = (0.0, float("inf"))
    for dx in cand:
        m = mesh.copy()
        m.apply_translation([dx, 0.0, 0.0])
        d = _depth(m, others)
        if d <= JOINT_CLEAR:
            return float(dx), float(d)
        if d < best[1]:
            best = (float(dx), float(d))
    return best


def close_axial_stack(parts, stl_dir):
    """Mutates the poses dict: adds axial_shift_mm and shifts T for movables."""
    import os

    def placed(name):
        p = parts[name]
        m = trimesh.load(os.path.join(stl_dir, p["stl"]), process=False)
        m.apply_transform(np.asarray(p["T"], float))
        return m

    fixed_names = ["Base", "LFrame", "RFrame", "Lid", "Receiver"]
    world = {n: placed(n) for n in fixed_names}
    report = {}

    def solve(name, against, prefer):
        m = placed(name)
        dx, resid = _slide(m, [world[a] for a in against if a in world], prefer)
        T = np.asarray(parts[name]["T"], float)
        T[0, 3] += dx
        parts[name]["T"] = T.tolist()
        parts[name]["axial_shift_mm"] = dx
        parts[name]["stack_residual_depth_mm"] = resid
        m.apply_translation([dx, 0.0, 0.0])
        world[name] = m
        report[name] = (dx, resid)

    shell = ["Base", "LFrame", "RFrame", "Lid"]
    # arms outboard of the frame walls, pitchers inboard (PDF p.22)
    for nm in parts:
        if nm.startswith("Arm::"):
            # outboard = away from centreline
            sgn = +1 if _cx(parts[nm]) > 0 else -1
            solve(nm, shell, prefer=sgn)
    # pitchers inboard, clearing the shell AND the already-seated main arms
    for nm in parts:
        if nm.startswith("Pitcher::"):
            sgn = -1 if _cx(parts[nm]) > 0 else +1     # inboard
            solve(nm, list(world), prefer=sgn)
    # links last: against everything already placed
    for nm in parts:
        if nm.startswith("Link::"):
            out = +1 if _cx(parts[nm]) > 0 else -1
            # the two links sharing a receiver bolt straddle its ear (PDF p.31:
            # tabs one up one down): lower outboard, upper inboard
            sgn = -out if "upper" in nm else out
            solve(nm, list(world), prefer=sgn)
    return report


def _cx(p):
    """Mean world-x of the part's interface (which side of the machine)."""
    ifc = p.get("interface") or {}
    xs = [v[0] for k, v in ifc.items() if k.endswith("_world")]
    return float(np.mean(xs)) if xs else float(np.asarray(p["T"], float)[0, 3])
