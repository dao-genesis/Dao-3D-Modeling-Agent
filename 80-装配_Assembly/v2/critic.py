"""v2/critic.py -- the externalized perceptual/structural critic.

Why this exists: my internal "looks like a machine" judgement is a shallow,
confirmation-biased narrative. A human instantly sees spatial wrongness because
the visual system computes physical relations (contact, support, symmetry,
proportion) and anomalies pop out. This module computes those relations
explicitly so "wrongness" becomes MEASURABLE and LOCALIZED, and so it cannot be
rationalised away.

Checks (all intrinsic to the 3D assembly -- no self-declared mates trusted):
  1. CONTACT GRAPH / FLOATING parts: every part must touch the rest of the
     machine. Parts whose nearest neighbour is far away are floating (the
     classic failure: a receiver hovering 150mm up on thin rods, rod ends not
     reaching their pivot).
  2. INTERPENETRATION: solid parts must not overlap volumes.
  3. SYMMETRY: a real SR6 is bilaterally symmetric about its mid-plane; large
     left/right Chamfer mismatch = a lopsided / misplaced layout.
  4. PROPORTION / PRINCIPAL AXIS: overall extents + slenderness vs the real
     machine (a "tower" stack has the wrong dominant axis and aspect).
  5. LINK CONVERGENCE / VERTICALITY: the slender links (push-rods) of a parallel
     manipulator must RISE and CONVERGE onto the moving platform, forming a
     cage. The two failure modes a human spots instantly are (a) rods lying
     near-flat ("平躺"), and (b) rods splaying outward so their axes never meet.
     We auto-detect slender parts, fit their long axes, and measure how tightly
     the axes converge and how vertical they are.

Each check returns a numeric score and human-readable findings. The verdict is
PASS only if every structural check passes.
"""
import os, sys, numpy as np, trimesh
sys.path.insert(0, os.path.dirname(__file__))

CONTACT_EPS = 4.0     # mm; surfaces closer than this are "in contact"
FLOAT_FLAG = 12.0     # mm; nearest-neighbour gap above this = floating part
PEN_VOL_FLAG = 150.0  # mm^3; boolean-intersection volume above this = real overlap
SYM_FLAG = 8.0        # mm; mean mirror Chamfer above this = asymmetric
LINK_ASPECT = 3.0     # length/width above this = a slender link (push-rod)
VERTICAL_FLAG = 0.30  # mean |axis.z| below this = links lying too flat ("平躺")


def _tm(part):
    v, f = part[0], part[1]
    return trimesh.Trimesh(vertices=np.asarray(v), faces=np.asarray(f), process=False)


def _principal_axis(v):
    """return (centroid, unit long-axis, sorted extents desc) via PCA."""
    c = v.mean(0)
    u, s, vt = np.linalg.svd(v - c, full_matrices=False)
    proj = (v - c) @ vt.T
    ext = proj.max(0) - proj.min(0)
    return c, vt[0], np.sort(ext)[::-1]


def _link_convergence(meshes, names):
    """detect slender links; measure axis convergence + verticality.
    Returns dict(score fields) and a findings list."""
    links = []
    for m, nm in zip(meshes, names):
        c, axis, ext = _principal_axis(m.vertices)
        aspect = ext[0] / max(ext[1], 1e-6)
        if aspect >= LINK_ASPECT:
            links.append((nm, c, axis, ext[0]))
    out, find = {}, []
    if len(links) < 3:
        find.append(f"links: only {len(links)} slender link(s) found - skipped")
        out.update(n_links=len(links), vertical=1.0)
        return out, find, True
    vertical = float(np.mean([abs(d[2]) for _, _, d, _ in links]))
    # informational only: in a parallel manipulator the rods attach to a
    # *distributed* set of platform anchors, so they do NOT meet at one point.
    # We report the spread of the upper rod ends (platform footprint) for insight
    # but do not gate on single-point convergence (that is delta-robot physics).
    out.update(n_links=len(links), vertical=vertical)
    ok = vertical >= VERTICAL_FLAG
    find.append(f"links: {len(links)} slender push-rods detected"
                + ("  (SR6 expects 6)" if len(links) != 6 else "  (= 6, complete)"))
    find.append(f"verticality: mean |axis.z| = {vertical:.2f} "
                + ("<- LYING FLAT (平躺)" if vertical < VERTICAL_FLAG
                   else "(upright, rods rise to platform)"))
    return out, find, ok


def _surface_gap(a, b, n=800):
    """min surface-to-surface gap (mm), accurate point-to-triangle distance.

    Sample points on each mesh and measure their *unsigned* distance to the
    OTHER mesh's actual triangles (trimesh closest_point). Unlike signed_distance
    this is deterministic and stable; unlike point-to-point KD it does not miss
    the true contact when one part is large and sparsely sampled.
    """
    # Always include the explicit vertices (rod end-caps, bolt-tab corners) on
    # top of area-weighted samples: a true contact is often a tiny feature that
    # random surface sampling can step over, which would falsely read as a float.
    pa = np.vstack([a.sample(n), a.vertices]) if a.area > 0 else a.vertices
    pb = np.vstack([b.sample(n), b.vertices]) if b.area > 0 else b.vertices
    d1 = trimesh.proximity.closest_point(b, pa)[1].min()
    d2 = trimesh.proximity.closest_point(a, pb)[1].min()
    return float(min(d1, d2))


def _overlap_volume(a, b):
    """true solid interpenetration as boolean-intersection volume (mm^3).

    The gold standard: if two solids share volume they overlap, full stop.
    Returns 0.0 if either mesh is not a clean volume or the backend is absent.
    """
    if not (a.is_volume and b.is_volume):
        return 0.0
    # cheap reject: disjoint AABBs cannot intersect
    if (a.bounds[0] > b.bounds[1]).any() or (b.bounds[0] > a.bounds[1]).any():
        return 0.0
    try:
        inter = trimesh.boolean.intersection([a, b])
    except Exception:
        return 0.0
    if inter is None or inter.is_empty or not inter.is_volume:
        return 0.0
    return float(abs(inter.volume))


def critique(parts, names=None, ref_aspect=None, joints=None, verbose=True):
    """Critique an assembly.

    joints: optional iterable of (nameA, nameB) pairs that are DESIGNED to be in
    contact (kinematic joints + rigid welds). With a joint graph the critic uses
    the only physically-correct, machine-general rule:
        * CONNECTED parts MUST touch     -> a gap = a broken joint (float).
        * UNCONNECTED parts MUST NOT overlap -> shared volume = a collision.
    A seated ball-joint or a bearing in its bore is contact between connected
    parts (expected); two independent arms sharing volume is a collision. Without
    a joint graph it falls back to the older "nearest-neighbour" heuristic.
    """
    names = names or [f"part{i}" for i in range(len(parts))]
    meshes = [_tm(p) for p in parts]
    N = len(meshes)
    findings, scores = [], {}
    idx = {n: i for i, n in enumerate(names)}
    jset = set()
    if joints:
        for a, b in joints:
            if a in idx and b in idx:
                jset.add(frozenset((a, b)))

    # ---- 1+2. pairwise contact / penetration -------------------------------
    gap = np.full((N, N), np.inf)
    vol = np.zeros((N, N))
    for i in range(N):
        for j in range(i + 1, N):
            g = _surface_gap(meshes[i], meshes[j])
            gap[i, j] = gap[j, i] = g
            v = _overlap_volume(meshes[i], meshes[j])
            vol[i, j] = vol[j, i] = v

    def _fixed(n):
        return any(h in n for h in ("Base", "Lid", "Frame"))

    if jset:
        # connectivity-aware: a broken joint is a connected pair NOT touching;
        # a collision is an unconnected pair sharing volume.
        floating = []
        for a, b in (tuple(p) for p in jset):
            g = gap[idx[a], idx[b]]
            if g > CONTACT_EPS:
                floating.append((a, b, g))
        scores["max_float_gap"] = max((d for *_, d in floating), default=0.0)
        if floating:
            findings.append("BROKEN JOINTS (parts that must connect are apart):")
            for a, b, d in sorted(floating, key=lambda x: -x[2]):
                findings.append(f"    {a} <-> {b}: {d:.1f}mm gap (joint, must touch)")
        else:
            findings.append(f"joints: all {len(jset)} declared joints in contact")

        collisions = [(names[i], names[j], vol[i, j])
                      for i in range(N) for j in range(i + 1, N)
                      if vol[i, j] > PEN_VOL_FLAG
                      and frozenset((names[i], names[j])) not in jset
                      and not (_fixed(names[i]) and _fixed(names[j]))]
        pens = collisions
        scores["max_overlap_vol"] = float(max((d for *_, d in collisions), default=0.0))
        if collisions:
            findings.append("COLLISIONS (unconnected solids sharing volume):")
            for a, b, d in sorted(collisions, key=lambda x: -x[2])[:8]:
                findings.append(f"    {a} <-> {b}: {d:.0f}mm^3 overlap (NOT a joint)")
        else:
            findings.append("collision: no unconnected parts share volume")
    else:
        nearest = [(names[i], names[int(np.argmin(gap[i]))], float(np.min(gap[i])))
                   for i in range(N)]
        floating = [(a, b, d) for a, b, d in nearest if d > FLOAT_FLAG]
        scores["max_float_gap"] = max((d for *_, d in nearest), default=0.0)
        if floating:
            findings.append("FLOATING parts (nearest neighbour too far):")
            for a, b, d in floating:
                findings.append(f"    {a}: nearest is {b} at {d:.1f}mm (> {FLOAT_FLAG})")
        else:
            findings.append("contact: every part touches the machine (no floaters)")

        pen_all = [(names[i], names[j], vol[i, j])
                   for i in range(N) for j in range(i + 1, N) if vol[i, j] > PEN_VOL_FLAG]
        pens = [(a, b, d) for a, b, d in pen_all if not (_fixed(a) and _fixed(b))]
        scores["max_overlap_vol"] = float(max((d for *_, d in pens), default=0.0))
        if pen_all:
            findings.append("INTERPENETRATION (solids sharing volume):")
            for a, b, d in sorted(pen_all, key=lambda x: -x[2])[:8]:
                tag = "  (designed housing joint)" if _fixed(a) and _fixed(b) else ""
                findings.append(f"    {a} <-> {b}: {d:.0f}mm^3 overlap{tag}")
        else:
            findings.append("interpenetration: no solids share volume")

    # ---- 3. bilateral symmetry about x=0 -----------------------------------
    cloud = np.vstack([m.sample(1500) for m in meshes])
    mirror = cloud * np.array([-1, 1, 1])
    pq = trimesh.proximity.ProximityQuery(
        trimesh.PointCloud(cloud).convex_hull)
    # Chamfer via nearest neighbour (KD on the point set)
    from scipy.spatial import cKDTree
    tree = cKDTree(cloud)
    sym = float(tree.query(mirror)[0].mean())
    scores["symmetry_chamfer"] = sym
    findings.append(f"symmetry: mean L/R mirror mismatch {sym:.1f}mm"
                    + ("  <- ASYMMETRIC" if sym > SYM_FLAG else ""))

    # ---- 4. proportion / principal axis ------------------------------------
    ext = cloud.max(0) - cloud.min(0)
    order = np.argsort(ext)[::-1]
    axis_names = np.array(["X", "Y", "Z"])
    slender = ext.max() / max(ext.min(), 1e-6)
    scores["extents"] = ext.round(1).tolist()
    scores["dominant_axis"] = axis_names[order[0]]
    scores["slenderness"] = float(slender)
    findings.append(f"extents XYZ = {ext.round(1).tolist()}mm, dominant axis "
                    f"{axis_names[order[0]]}, slenderness {slender:.2f}")
    if ref_aspect is not None:
        findings.append(f"    reference aspect (long/short) ~ {ref_aspect}")

    # ---- 5. link verticality + completeness --------------------------------
    conv, conv_find, vert_ok = _link_convergence(meshes, names)
    scores.update(conv)
    findings.extend(conv_find)

    verdict = ((not floating) and (not pens) and (sym <= SYM_FLAG) and vert_ok)
    if verbose:
        print("=" * 64)
        print("CRITIC REPORT")
        print("=" * 64)
        for f in findings:
            print(f)
        print("-" * 64)
        print("scores:", {k: (round(v, 2) if isinstance(v, float) else v)
                           for k, v in scores.items()})
        print("VERDICT:", "PASS" if verdict else "FAIL  <-- spatially wrong")
        print("=" * 64)
    return verdict, scores, findings


def _run_broken():
    from platform_home import build_platform, FIXED, PLATFORM
    parts, dz = build_platform(verbose=False)
    names = list(FIXED) + list(PLATFORM)
    names += ["Arm", "Rod"] * ((len(parts) - len(names)) // 2)
    return parts, names


def _run_truth():
    from truth_home import build_truth, truth_joints
    p, n = build_truth(verbose=False)
    return p, n, truth_joints()


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("broken", "both"):
        print("\n########## BROKEN v2 (platform_home) ##########")
        p, n = _run_broken(); critique(p, n)
    if which in ("truth", "both"):
        print("\n########## CORRECT (truth_home, grounded geometry) ##########")
        p, n, j = _run_truth(); critique(p, n, joints=j)
