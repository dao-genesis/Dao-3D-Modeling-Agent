#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical mapping of SR6 part keys -> extracted STL absolute paths.

STL meshes are NOT committed to the repo (large binaries).  Set the env var
SR6_STL_ROOT to the extracted archive's ``STLs`` directory to enable the
STL-driven scripts (``assemble.py`` / ``render.py`` / ``interference.py``).
Path resolution is lazy so this module imports cleanly without the STLs (the
committed ``assembly_transforms.json`` already captures every transform, and
``verify_assembly.py`` validates the build with no STL access).
"""
import os, glob

# key -> list of substring fragments that uniquely identify the STL
FRAGS = {
    "L_Frame":     ("L形框架",),
    "R_Frame":     ("R-Frame",),
    "Receiver":    ("Receiver",),
    "MainArm":     ("SR6 臂",),
    "L_Pitcher":   ("L-投手",),
    "R_Pitcher":   ("R-投手",),
    "MainLink":    ("Main Link",),
    "PitchLink":   ("Pitcher Link Alpha",),
    "Base":        ("底座",),
    "Lid":         ("盖子",),
}


def _root():
    r = os.environ.get("SR6_STL_ROOT")
    if not r:
        raise RuntimeError(
            "SR6_STL_ROOT not set; STL meshes are not committed. Point it at the "
            "extracted archive's STLs directory to run the STL-driven scripts.")
    return r


def find(key):
    """Resolve one STL path for `key` (raises if STL_ROOT unset / not unique)."""
    frags = FRAGS[key]
    hits = [p for p in glob.glob(os.path.join(_root(), "**", "*.stl"), recursive=True)
            if all(f in p for f in frags)]
    if len(hits) != 1:
        raise RuntimeError(f"{key} {frags} -> {len(hits)} hits: {hits}")
    return hits[0]


class _Lazy:
    def __getitem__(self, k):
        return find(k)
    def __contains__(self, k):
        return k in FRAGS

PARTS = _Lazy()
