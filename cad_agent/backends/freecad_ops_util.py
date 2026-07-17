"""Shared pure helpers for the ``solid.*`` op modules (split from freecad_ops)."""

import itertools
import math

import FreeCAD as App
import Part

V = App.Vector

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _round(x, n=4):
    return round(float(x), n)


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v) if n else tuple(v)


def _unit_v(v):
    """Normalise an ``App.Vector`` (returns it unchanged if it has zero length)."""
    n = v.Length
    return V(v.x / n, v.y / n, v.z / n) if n else v


def _vec(seq, default=(0, 0, 0), label="vector"):
    if seq is None:
        seq = default
    # a non-sequence (e.g. a bare string) or a wrong-length / non-numeric list
    # otherwise leaks a raw IndexError / 'could not convert string to float'.
    if isinstance(seq, (str, bytes)) or not isinstance(seq, (list, tuple)):
        raise ValueError(
            "%s must be a list of 3 numbers [x, y, z] (got %r)" % (label, seq))
    if len(seq) != 3:
        raise ValueError(
            "%s must have exactly 3 components [x, y, z] (got %r)" % (label, seq))
    try:
        return V(float(seq[0]), float(seq[1]), float(seq[2]))
    except (TypeError, ValueError):
        raise ValueError(
            "%s components must all be numbers (got %r)" % (label, seq))


def _pt2(seq, label):
    """Coerce a 2-element [x, y] sequence to floats with a guided error -- a
    bare ``w, h = spec[...]`` leaks 'not enough values to unpack' / 'could not
    convert' when the value is a string or a wrong-length / non-numeric list."""
    if isinstance(seq, (str, bytes)) or not isinstance(seq, (list, tuple)):
        raise ValueError("%s must be an [x, y] pair (got %r)" % (label, seq))
    if len(seq) < 2:
        raise ValueError("%s must have 2 components [x, y] (got %r)" % (label, seq))
    out = []
    for v in seq[:2]:
        if isinstance(v, bool) or not isinstance(v, (int, float, str)):
            raise ValueError("%s must hold numbers (got %r)" % (label, seq))
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            raise ValueError("%s must hold numbers (got %r)" % (label, seq))
    return out[0], out[1]


_MISSING = object()


def _num(a, key, default=_MISSING, label=None):
    """Coerce ``a[key]`` to float with a guided error instead of a raw
    ``TypeError`` / ``ValueError: could not convert string to float``."""
    name = label or key
    if key not in a or a[key] is None:
        if default is _MISSING:
            # let the kernel turn a bare missing key into the canonical
            # "<op> missing required argument '<key>'" guidance.
            raise KeyError(key)
        return float(default)
    v = a[key]
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ValueError("%s must be a number (got %r)" % (name, v))
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError("%s must be a number (got %r)" % (name, v))


def _int(a, key, default=_MISSING, label=None):
    """Coerce ``a[key]`` to int with a guided error instead of a raw
    ``ValueError: invalid literal for int()``."""
    name = label or key
    if key not in a or a[key] is None:
        if default is _MISSING:
            raise KeyError(key)
        return int(default)
    v = a[key]
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ValueError("%s must be an integer (got %r)" % (name, v))
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError("%s must be an integer (got %r)" % (name, v))
    if f != int(f):
        raise ValueError("%s must be a whole number (got %r)" % (name, v))
    return int(f)


def _path(a, key, op):
    """Validate ``a[key]`` is a non-empty filesystem string; a non-string
    otherwise leaks a raw 'TypeError: expected str, bytes or os.PathLike'."""
    p = a.get(key)
    if not isinstance(p, str) or not p:
        raise ValueError(
            "%s '%s' must be a non-empty file path string (got %r)"
            % (op, key, p))
    return p


def _name(a, key, op):
    """A solid name must be a string; a non-string otherwise leaks a raw
    ``TypeError`` (e.g. on ``name + '_part'`` or ``addObject``)."""
    v = a.get(key)
    if not isinstance(v, str) or not v:
        raise ValueError(
            "%s '%s' must be a non-empty solid name string (got %r)"
            % (op, key, v))
    return v


def _names(a, key, op):
    """``names`` must be a list/tuple of solid names; a bare int leaks a raw
    'TypeError: int object is not iterable' and a string iterates characters."""
    v = a[key] if key in a else None
    if not isinstance(v, (list, tuple)):
        raise ValueError(
            "%s '%s' must be a list of solid names (got %r)" % (op, key, v))
    return list(v)


def _proper_rotations():
    """The 24 axis-aligned proper rotations (signed permutation matrices, det +1).

    These are exactly the rigid rotations that map an axis-aligned inertia frame
    onto itself, so testing all of them aligns two bodies brought into their own
    principal frames regardless of any moment degeneracy.
    """
    mats = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            cols = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
            for i, p in enumerate(perm):
                cols[i][p] = signs[i]
            m = [[cols[r][c] for c in range(3)] for r in range(3)]
            det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                   - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                   + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
            if det == 1:
                mats.append(App.Matrix(
                    m[0][0], m[0][1], m[0][2], 0,
                    m[1][0], m[1][1], m[1][2], 0,
                    m[2][0], m[2][1], m[2][2], 0, 0, 0, 0, 1))
    return mats


_PROPER_ROTATIONS = _proper_rotations()


def _face_entries(shape):
    """(centroid, area, surface-type) per face — the rotation/reflection-stable
    signature an isometry must preserve. Shared by the fast 'invariant' paths of
    ``symmetry`` and ``chirality`` (no BREP booleans, so it scales to high-face
    real parts the volumetric proof must refuse)."""
    return [(f.CenterOfMass, f.Area, f.Surface.__class__.__name__)
            for f in shape.Faces]


def _face_bijection(src, dst, tol, dtol):
    """True iff every ``src`` face maps one-to-one onto a ``dst`` face of the
    same surface type and (relatively) equal area whose centroid lands within
    ``dtol``. Returns ``(ok, max_centroid_deviation)``. A necessary condition
    for two face sets to be the same shape under an isometry — strong for real
    parts, but not a volumetric proof, so callers mark ``proven=False``."""
    if len(src) != len(dst):
        return False, None
    used = [False] * len(dst)
    maxdev = 0.0
    for c, ar, ty in src:
        best, bestd = None, None
        for i, (c0, ar0, ty0) in enumerate(dst):
            if used[i] or ty0 != ty:
                continue
            if abs(ar0 - ar) > tol * max(ar, ar0, 1e-9):
                continue
            d = c.distanceToPoint(c0)
            if bestd is None or d < bestd:
                best, bestd = i, d
        if best is None or bestd > dtol:
            return False, None
        used[best] = True
        if bestd > maxdev:
            maxdev = bestd
    return True, maxdev


def _guard_boolean_budget(op, body, a, default_max=120):
    """Refuse loudly (not with an opaque RPC timeout) when a boolean-proof
    operation would be too expensive.

    ``solid.symmetry`` / ``solid.chirality`` prove their result with dozens of
    full BREP boolean cuts, each O(faces). On a high-face real part (e.g. a
    toothed pulley with hundreds of cylindrical faces) that silently blows the
    request budget and surfaces as an unactionable timeout -- the very "silent
    failure" we forbid. So we check the face count up front and raise a clear,
    actionable error. ``max_faces`` tunes the ceiling; ``force=True`` runs it
    anyway when the caller knowingly accepts the cost.
    """
    if a.get("force"):
        return
    limit = _int(a, "max_faces", default_max, "max_faces")
    nf = len(body.Faces)
    if nf > limit:
        raise ValueError(
            "%s proves its result with O(faces) boolean cuts; this part has %d "
            "faces (> max_faces=%d) and would exceed the time budget. Defeature "
            "or simplify the part first, raise max_faces, or pass force=true to "
            "run it anyway." % (op, nf, limit))


def _metrics(shape):
    bb = shape.BoundBox
    data = {
        "valid": bool(shape.isValid()),
        "volume": _round(shape.Volume),
        "area": _round(shape.Area),
        "solids": len(shape.Solids),
        "shells": len(shape.Shells),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
        "vertices": len(shape.Vertexes),
        "bbox": [_round(bb.XMin), _round(bb.YMin), _round(bb.ZMin),
                 _round(bb.XMax), _round(bb.YMax), _round(bb.ZMax)],
        "bbox_size": [_round(bb.XLength), _round(bb.YLength), _round(bb.ZLength)],
    }
    try:
        data["closed"] = bool(shape.isClosed())
    except Exception:
        pass
    try:
        com = shape.CenterOfMass
        data["center_of_mass"] = [_round(com.x), _round(com.y), _round(com.z)]
    except Exception:
        pass
    return data


def _center(shape):
    """Centroid of a shape, tolerant of compounds.

    Boolean ops (``cut``/``union``/``common``) routinely return a
    ``Part.Compound`` which — unlike a single ``Solid`` — has no
    ``CenterOfMass``. The mould-half classification only needs a representative
    interior point, so fall back to the bounding-box centre when the true
    centroid is unavailable.
    """
    try:
        return shape.CenterOfMass
    except (AttributeError, RuntimeError):
        sols = getattr(shape, "Solids", None)
        if sols:
            tv = sum(s.Volume for s in sols) or 1.0
            return V(sum(s.CenterOfMass.x * s.Volume for s in sols) / tv,
                     sum(s.CenterOfMass.y * s.Volume for s in sols) / tv,
                     sum(s.CenterOfMass.z * s.Volume for s in sols) / tv)
        bb = shape.BoundBox
        return V(bb.Center.x, bb.Center.y, bb.Center.z)


def _inertia_about(shape, density, about):
    """Mass and inertia tensor of a solid about a chosen reference point.

    FreeCAD's ``Shape.MatrixOfInertia`` is the *geometric* (density = 1, i.e.
    mass = volume) inertia tensor taken about the **centroid** — it silently
    ignores both the material density and where you actually want the moments.
    A real rigid-body calculation needs neither assumption: scale by density and
    shift the reference with the parallel-axis theorem

        I_P = I_cm + m(|d|^2 E - d (x) d),   d = com - P.

    ``about`` is ``"centroid"`` (default), ``"origin"`` or an explicit
    ``[x, y, z]`` point. Returns ``(mass, com, tensor3x3, ref_point)``.
    """
    m = float(shape.Volume) * density
    com = _center(shape)
    if about in (None, "centroid", "center", "com"):
        ref = com
    elif about == "origin":
        ref = V(0, 0, 0)
    else:
        ref = _vec(about)
    # Boolean results are routinely a Part.Compound, which (unlike a single
    # Solid) exposes no MatrixOfInertia. Accumulate each constituent solid's
    # centroidal tensor and parallel-axis-shift it to the common reference, so
    # the op works on cut/union/multi-body shapes, not just primitives.
    solids = shape.Solids or [shape]
    tensor = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    for s in solids:
        mi = float(s.Volume) * density
        ci = s.CenterOfMass
        mat = s.MatrixOfInertia
        ti = [[mat.A11 * density, mat.A12 * density, mat.A13 * density],
              [mat.A12 * density, mat.A22 * density, mat.A23 * density],
              [mat.A13 * density, mat.A23 * density, mat.A33 * density]]
        d = (ci.x - ref.x, ci.y - ref.y, ci.z - ref.z)
        d2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2]
        for i in range(3):
            for j in range(3):
                tensor[i][j] += ti[i][j] + mi * ((d2 if i == j else 0.0)
                                                 - d[i] * d[j])
    return m, com, tensor, ref


def _cyl_axes(shape, tol=1e-6):
    """Cylindrical faces of a shape as (center, unit-axis, radius) records.

    The raw material for joint inference: a revolute joint shows up as two
    parts sharing a coaxial cylindrical face (a pin in a hole). Coincident
    duplicates (the same axis reported by several faces) are merged.
    """
    out = []
    for f in shape.Faces:
        surf = f.Surface
        if surf.__class__.__name__ != "Cylinder":
            continue
        ax = surf.Axis
        al = ax.Length or 1.0
        ax = (ax.x / al, ax.y / al, ax.z / al)
        c = surf.Center
        rec = {"center": (c.x, c.y, c.z), "dir": ax, "radius": float(surf.Radius)}
        dup = False
        for e in out:
            if (abs(e["radius"] - rec["radius"]) < 1e-4
                    and abs(abs(e["dir"][0] * ax[0] + e["dir"][1] * ax[1]
                                + e["dir"][2] * ax[2]) - 1.0) < 1e-6):
                # same radius & parallel axis: coaxial if centre offset is axial
                dx = (c.x - e["center"][0], c.y - e["center"][1], c.z - e["center"][2])
                cross = (dx[1] * ax[2] - dx[2] * ax[1],
                         dx[2] * ax[0] - dx[0] * ax[2],
                         dx[0] * ax[1] - dx[1] * ax[0])
                if math.sqrt(sum(v * v for v in cross)) < 1e-4:
                    dup = True
                    break
        if not dup:
            out.append(rec)
    return out


def _plane_faces(shape):
    """Planar faces as (outward unit-normal, centre, bbox).

    ``Surface.Axis`` is the underlying plane normal and ignores which side is
    solid, so two faces flat against each other report the *same* sign. Flip by
    the face orientation to get the true outward normal — only then do opposing
    contact faces come out anti-parallel.
    """
    out = []
    for f in shape.Faces:
        if f.Surface.__class__.__name__ != "Plane":
            continue
        n = f.Surface.Axis
        nl = n.Length or 1.0
        sgn = -1.0 if f.Orientation == "Reversed" else 1.0
        c = f.CenterOfMass
        out.append({"n": (sgn * n.x / nl, sgn * n.y / nl, sgn * n.z / nl),
                    "p": (c.x, c.y, c.z), "bb": f.BoundBox})
    return out


def _bb_overlap(b1, b2, tol):
    return (b1.XMin <= b2.XMax + tol and b2.XMin <= b1.XMax + tol
            and b1.YMin <= b2.YMax + tol and b2.YMin <= b1.YMax + tol
            and b1.ZMin <= b2.ZMax + tol and b2.ZMin <= b1.ZMax + tol)


def _contact_normals(sa, sb, gap=1e-3):
    """Unit normals where a planar face of ``sa`` lies flat against an opposing
    face of ``sb`` (anti-parallel, coincident plane, overlapping footprint).

    These are the directions the contact removes from relative translation —
    the raw material for telling a slider (prismatic) from a free part.
    """
    normals = []
    for a in _plane_faces(sa):
        for b in _plane_faces(sb):
            na, nb = a["n"], b["n"]
            dot = na[0] * nb[0] + na[1] * nb[1] + na[2] * nb[2]
            if dot > -0.999:                       # require facing (opposed) planes
                continue
            dp = (b["p"][0] - a["p"][0], b["p"][1] - a["p"][1], b["p"][2] - a["p"][2])
            if abs(dp[0] * na[0] + dp[1] * na[1] + dp[2] * na[2]) > max(gap, 1e-6):
                continue                            # planes not coincident -> no contact
            if not _bb_overlap(a["bb"], b["bb"], gap):
                continue                            # footprints do not overlap
            # canonicalise direction sign so +n and -n collapse to one
            key = na if (na[0], na[1], na[2]) >= (0, 0, 0) else (-na[0], -na[1], -na[2])
            if not any(abs(abs(key[0] * m[0] + key[1] * m[1] + key[2] * m[2]) - 1.0) < 1e-6
                       for m in normals):
                normals.append(key)
    return normals


def _free_axis(normals):
    """The single free translation axis of a part pinned by ``normals``.

    Contact normals remove translation along themselves. A slider is boxed in by
    contacts spanning exactly two directions, leaving one free line (their cross
    product). Rank<=1 leaves a plane free (planar joint, not prismatic); rank 3
    is fully constrained.
    """
    for i in range(len(normals)):
        for j in range(i + 1, len(normals)):
            a, b = normals[i], normals[j]
            cx = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
                  a[0] * b[1] - a[1] * b[0])
            length = math.sqrt(sum(v * v for v in cx))
            if length <= 1e-6:
                continue
            ax = (cx[0] / length, cx[1] / length, cx[2] / length)
            if all(abs(ax[0] * n[0] + ax[1] * n[1] + ax[2] * n[2]) < 1e-6 for n in normals):
                return ax           # rank exactly 2 -> one free axis
            return None             # a third independent normal -> fully constrained
    return None                     # rank <= 1 -> a free plane, not a slider


def _signature(shape):
    """Compact geometry fingerprint of a solid, for reverse-engineering."""
    bb = shape.BoundBox
    com = _center(shape)
    axes = _cyl_axes(shape)
    return {
        "volume": _round(shape.Volume),
        "bbox_size": [_round(bb.XLength), _round(bb.YLength), _round(bb.ZLength)],
        "center_of_mass": [_round(com.x), _round(com.y), _round(com.z)],
        "faces": len(shape.Faces),
        "cyl_axes": [{"center": [_round(c) for c in r["center"]],
                      "dir": [_round(c, 6) for c in r["dir"]],
                      "radius": _round(r["radius"], 4)} for r in axes],
    }


def _profile_face(spec):
    """Build a planar face (on XY) from a profile spec dict.

    Supported: {"rect":[w,h], "centered":bool}, {"circle":r},
    {"polygon":[[x,y],...]}, {"slot":[length,width]}.
    """
    # a non-dict spec (e.g. the bare string "rect") otherwise satisfies the
    # `"rect" in spec` substring test and then leaks 'TypeError: string indices
    # must be integers' on spec["rect"]; demand a real profile dict up front.
    if not isinstance(spec, dict):
        raise ValueError(
            "profile must be a dict like {'rect':[w,h]} / {'circle':r} / "
            "{'polygon':[[x,y],...]} / {'slot':[l,w]}; got %r" % (spec,))
    if "rect" in spec:
        w, h = _pt2(spec["rect"], "profile rect [w, h]")
        if spec.get("centered", True):
            x0, y0 = -w / 2.0, -h / 2.0
        else:
            x0, y0 = 0.0, 0.0
        pts = [V(x0, y0, 0), V(x0 + w, y0, 0), V(x0 + w, y0 + h, 0), V(x0, y0 + h, 0), V(x0, y0, 0)]
        wire = Part.makePolygon(pts)
    elif "circle" in spec:
        r = _num(spec, "circle", label="profile circle radius")
        # a non-positive circle radius leaks a bare 'OCCError: Radius value is
        # negative'; refuse it with guidance like the other dimension guards.
        if r <= 0:
            raise ValueError(
                "profile circle radius must be positive (got %g)" % r)
        wire = Part.Wire(Part.Circle(V(0, 0, 0), V(0, 0, 1), r).toShape())
    elif "polygon" in spec:
        poly = spec["polygon"]
        if isinstance(poly, (str, bytes)) or not isinstance(poly, (list, tuple)):
            raise ValueError(
                "profile 'polygon' must be a list of [x, y] points (got %r)"
                % (poly,))
        pts = [V(*_pt2(p, "polygon point"), 0) for p in poly]
        if len(pts) < 3:
            raise ValueError(
                "profile 'polygon' needs at least 3 points (got %d)" % len(pts))
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        wire = Part.makePolygon(pts)
    elif "slot" in spec:
        length, width = _pt2(spec["slot"], "profile slot [length, width]")
        if length <= 0 or width <= 0:
            raise ValueError(
                "profile slot needs positive [length, width] (got [%g, %g])"
                % (length, width))
        r = width / 2.0
        cx = length / 2.0 - r
        e = []
        e.append(Part.LineSegment(V(-cx, -r, 0), V(cx, -r, 0)).toShape())
        e.append(Part.Arc(V(cx, -r, 0), V(cx + r, 0, 0), V(cx, r, 0)).toShape())
        e.append(Part.LineSegment(V(cx, r, 0), V(-cx, r, 0)).toShape())
        e.append(Part.Arc(V(-cx, r, 0), V(-cx - r, 0, 0), V(-cx, -r, 0)).toShape())
        wire = Part.Wire(e)
    else:
        raise ValueError("unknown profile spec: %r" % (spec,))
    return Part.Face(wire)
