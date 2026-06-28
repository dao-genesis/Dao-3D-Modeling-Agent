"""v2/mate.py -- universal SE(3) mate kernel.

A part is placed by mating one of its local features to a world feature.
The primitive is COAXIAL: bring a part's local axis (through a local point)
into coincidence with a world axis (through a world point). One rotational
degree of freedom about that axis remains (the real mechanism DOF) and is
set by `spin_deg`.

All placement is derived from real mesh-feature geometry; only the residual
spin DOF (a genuine joint freedom) is a free parameter.
"""
import numpy as np


def _unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def rot_between(a, b):
    """rotation matrix taking unit vector a -> unit vector b."""
    a = _unit(a); b = _unit(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    s = np.linalg.norm(v)
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        # 180 deg: rotate about any axis perpendicular to a
        perp = np.array([1.0, 0, 0])
        if abs(a[0]) > 0.9:
            perp = np.array([0, 1.0, 0])
        ax = _unit(np.cross(a, perp))
        return rot_axis(ax, np.pi)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


def rot_axis(axis, ang):
    """rotation matrix of angle `ang` (rad) about unit `axis` (Rodrigues)."""
    axis = _unit(axis)
    x, y, z = axis
    c, s = np.cos(ang), np.sin(ang)
    C = 1 - c
    return np.array([
        [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
    ])


def place_coaxial(verts, local_pt, local_axis, world_pt, world_axis, spin_deg=0.0):
    """Transform `verts` (Nx3) so the part's local feature axis coincides with
    the world axis, local_pt maps onto world_pt, plus a spin about the axis.

    Returns (new_verts, T) where T is the 4x4 homogeneous transform applied.
    """
    verts = np.asarray(verts, float)
    R0 = rot_between(local_axis, world_axis)
    R = rot_axis(world_axis, np.deg2rad(spin_deg)) @ R0
    lp = np.asarray(local_pt, float)
    wp = np.asarray(world_pt, float)
    t = wp - R @ lp
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    out = verts @ R.T + t
    return out, T


def apply_T(verts, T):
    verts = np.asarray(verts, float)
    return verts @ T[:3, :3].T + T[:3, 3]


def transform_pt(T, p):
    return T[:3, :3] @ np.asarray(p, float) + T[:3, 3]


def transform_dir(T, d):
    return T[:3, :3] @ np.asarray(d, float)
