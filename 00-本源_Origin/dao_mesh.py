#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_mesh.py · 通用网格本源 · 万法之资归一
══════════════════════════════════════════════════════════════════════════════
反者道之动 — 不从 CAD 工具出发, 从网格字节的本源出发.
弱者道之用 — 零外部依赖 (只用 struct/math/json/base64), 可嵌入任意环境.
无为而无不为 — 单一 API read_mesh(path) 覆盖 STL-binary / STL-ASCII / GLB / OBJ.

读取:
  · STL binary  (Magics-style, 80B header + UINT32 tri_count + 50B/face)
  · STL ASCII   (solid ... endsolid, 容忍多 solid / 混合缩进)
  · OBJ         (仅 v + f, 支持四边形自动三角化)
  · GLB         (glTF 2.0 二进制, JSON-chunk + BIN-chunk, 读 mesh/position 即可算 bbox+faces)

统计量 (通过 MeshStats):
  · faces, bbox_min, bbox_max, bbox_size, volume (signed divergence theorem)
  · is_closed (启发式: 所有边出现偶数次, 仅 STL 可推断)
  · surface_area

从锤式破碎机项目 hoist: dao_verify_fast.read_stl_stats, 道法自然_闭环._read_stl_{ascii,binary}/read_stl_volume_bbox,
_crosscheck_cq_dao, merge_vbelt 中重复实现的 STL 解析全部统一于此.
"""
from __future__ import annotations

import base64
import json
import math
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

__version__ = "1.1.0"
__all__ = [
    "MeshStats", "read_mesh", "read_stl", "read_stl_binary", "read_stl_ascii",
    "read_obj", "read_glb", "is_stl_binary",
    "signed_volume_tri", "triangle_area",
    # Triangle-level access (for mesh composition / merging)
    "read_stl_triangles", "write_stl_binary",
]

Vec3 = Tuple[float, float, float]
PathLike = Union[str, Path]

EPS = 1e-12


# ══════════════════════════════════════════════════════════════════════════════
# 零、几何基元 · 三角带符号体积 / 面积 / 本源数学
# ══════════════════════════════════════════════════════════════════════════════

def signed_volume_tri(p0: Vec3, p1: Vec3, p2: Vec3) -> float:
    """三角带符号体积 = (1/6) · p0·(p1×p2). 散度定理: 闭合壳体积 = Σ signed_vol."""
    return (p0[0] * (p1[1]*p2[2] - p1[2]*p2[1])
          + p0[1] * (p1[2]*p2[0] - p1[0]*p2[2])
          + p0[2] * (p1[0]*p2[1] - p1[1]*p2[0])) / 6.0


def triangle_area(p0: Vec3, p1: Vec3, p2: Vec3) -> float:
    """三角面积 = 0.5 · |(p1-p0) × (p2-p0)|."""
    ax, ay, az = p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2]
    bx, by, bz = p2[0]-p0[0], p2[1]-p0[1], p2[2]-p0[2]
    cx = ay*bz - az*by
    cy = az*bx - ax*bz
    cz = ax*by - ay*bx
    return 0.5 * math.sqrt(cx*cx + cy*cy + cz*cz)


# ══════════════════════════════════════════════════════════════════════════════
# 一、统计量 · MeshStats
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MeshStats:
    """网格统计: 所有长度单位遵循文件原单位 (STL 通常 mm)."""
    faces: int = 0
    bbox_min: Vec3 = (0.0, 0.0, 0.0)
    bbox_max: Vec3 = (0.0, 0.0, 0.0)
    volume: float = 0.0           # 绝对值, 散度定理 (闭合壳)
    volume_signed: float = 0.0    # 带符号体积 (法线一致性判据)
    surface_area: float = 0.0
    n_vertices: int = 0
    format: str = ""              # stl_binary / stl_ascii / obj / glb
    closed_heuristic: Optional[bool] = None   # None = 未计算, True/False = 结论

    @property
    def bbox_size(self) -> Vec3:
        return (self.bbox_max[0]-self.bbox_min[0],
                self.bbox_max[1]-self.bbox_min[1],
                self.bbox_max[2]-self.bbox_min[2])

    @property
    def bbox_center(self) -> Vec3:
        return ((self.bbox_min[0]+self.bbox_max[0])/2,
                (self.bbox_min[1]+self.bbox_max[1])/2,
                (self.bbox_min[2]+self.bbox_max[2])/2)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["bbox_size"] = list(self.bbox_size)
        d["bbox_center"] = list(self.bbox_center)
        # 列表化 tuple 以便 JSON
        d["bbox_min"] = list(self.bbox_min)
        d["bbox_max"] = list(self.bbox_max)
        return d


# ══════════════════════════════════════════════════════════════════════════════
# 二、累加器 · 单遍内存高效 (不保留全部顶点, 仅累加极值+体积+面积)
# ══════════════════════════════════════════════════════════════════════════════

class _Accumulator:
    __slots__ = ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax",
                 "vol", "area", "n_face", "n_vert",
                 "edges", "track_edges")

    def __init__(self, track_edges: bool = False):
        self.xmin = self.ymin = self.zmin = float("inf")
        self.xmax = self.ymax = self.zmax = float("-inf")
        self.vol = 0.0
        self.area = 0.0
        self.n_face = 0
        self.n_vert = 0
        self.track_edges = track_edges
        self.edges: Dict[Tuple[Tuple[int,int,int], Tuple[int,int,int]], int] = {}

    def _accept_point(self, p: Vec3) -> None:
        x, y, z = p
        if x < self.xmin: self.xmin = x
        if y < self.ymin: self.ymin = y
        if z < self.zmin: self.zmin = z
        if x > self.xmax: self.xmax = x
        if y > self.ymax: self.ymax = y
        if z > self.zmax: self.zmax = z
        self.n_vert += 1

    def add_triangle(self, p0: Vec3, p1: Vec3, p2: Vec3) -> None:
        self._accept_point(p0); self._accept_point(p1); self._accept_point(p2)
        self.vol += signed_volume_tri(p0, p1, p2)
        self.area += triangle_area(p0, p1, p2)
        self.n_face += 1
        if self.track_edges:
            # Quantize to 6 decimal places to form hashable keys
            q = lambda p: (int(round(p[0]*1e6)), int(round(p[1]*1e6)), int(round(p[2]*1e6)))
            k0, k1, k2 = q(p0), q(p1), q(p2)
            for a, b in ((k0, k1), (k1, k2), (k2, k0)):
                key = (a, b) if a <= b else (b, a)
                self.edges[key] = self.edges.get(key, 0) + 1

    def finalize(self, fmt: str) -> MeshStats:
        if self.n_face == 0:
            return MeshStats(faces=0, format=fmt)
        closed: Optional[bool] = None
        if self.track_edges:
            # Manifold heuristic: every edge shared by exactly 2 triangles
            closed = all(v == 2 for v in self.edges.values()) if self.edges else None
        return MeshStats(
            faces=self.n_face,
            bbox_min=(self.xmin, self.ymin, self.zmin),
            bbox_max=(self.xmax, self.ymax, self.zmax),
            volume=abs(self.vol),
            volume_signed=self.vol,
            surface_area=self.area,
            n_vertices=self.n_vert,
            format=fmt,
            closed_heuristic=closed,
        )


# ══════════════════════════════════════════════════════════════════════════════
# 三、STL 读取 · 二进制 / ASCII 自动识别
# ══════════════════════════════════════════════════════════════════════════════

def is_stl_binary(data: bytes) -> bool:
    """严谨判据: 二进制 STL 大小必须精确等于 84 + 50·n_tri, 且头部无 'facet' 关键字."""
    if len(data) < 84:
        return False
    n_tri = struct.unpack_from("<I", data, 80)[0]
    if n_tri == 0:
        return False
    expected = 84 + n_tri * 50
    if expected != len(data):
        return False
    # If header text contains 'facet' or 'solid ' at offset 0, it's ASCII
    header_sniff = bytes(data[:256]).lower()
    if b"facet" in header_sniff or b"endloop" in header_sniff:
        return False
    return True


def read_stl_binary(data: bytes, *, check_manifold: bool = False) -> Optional[MeshStats]:
    """解析二进制 STL bytes → MeshStats. 失败返回 None."""
    if len(data) < 84:
        return None
    n_tri = struct.unpack_from("<I", data, 80)[0]
    if len(data) < 84 + n_tri * 50 or n_tri == 0:
        return None
    acc = _Accumulator(track_edges=check_manifold)
    off = 84
    for _ in range(n_tri):
        off += 12                                       # skip normal
        p0 = struct.unpack_from("<3f", data, off); off += 12
        p1 = struct.unpack_from("<3f", data, off); off += 12
        p2 = struct.unpack_from("<3f", data, off); off += 12
        off += 2                                        # skip attr
        acc.add_triangle(p0, p1, p2)
    return acc.finalize("stl_binary")


def read_stl_ascii(data: bytes, *, check_manifold: bool = False) -> Optional[MeshStats]:
    """解析 ASCII STL bytes → MeshStats. 容忍多 solid / 不规范缩进."""
    try:
        text = data.decode("ascii", errors="replace")
    except Exception:
        return None
    acc = _Accumulator(track_edges=check_manifold)
    cur: List[Vec3] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("vertex"):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    cur.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except ValueError:
                    return None
                if len(cur) == 3:
                    acc.add_triangle(cur[0], cur[1], cur[2])
                    cur = []
        elif line.startswith("endfacet"):
            cur = []
    if acc.n_face == 0:
        return None
    return acc.finalize("stl_ascii")


def read_stl(path: PathLike, *, check_manifold: bool = False) -> Optional[MeshStats]:
    """自动识别 binary/ASCII, 读取 STL → MeshStats."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = p.read_bytes()
    except Exception:
        return None
    if is_stl_binary(data):
        st = read_stl_binary(data, check_manifold=check_manifold)
        if st: return st
    return read_stl_ascii(data, check_manifold=check_manifold)


# ══════════════════════════════════════════════════════════════════════════════
# 四、OBJ 读取 (最小子集: v + f, 含四边形三角化)
# ══════════════════════════════════════════════════════════════════════════════

def read_obj(path: PathLike, *, check_manifold: bool = False) -> Optional[MeshStats]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    verts: List[Vec3] = []
    acc = _Accumulator(track_edges=check_manifold)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("v "):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except ValueError:
                    return None
        elif line.startswith("f "):
            parts = line.split()[1:]
            # OBJ face indices are 1-based; supports `v`, `v/t`, `v/t/n`, `v//n`
            idxs: List[int] = []
            for tok in parts:
                head = tok.split("/")[0]
                try:
                    i = int(head)
                    if i < 0:
                        i = len(verts) + i + 1
                    idxs.append(i - 1)
                except ValueError:
                    idxs = []
                    break
            if len(idxs) < 3:
                continue
            # Fan triangulation for polygons
            for k in range(1, len(idxs) - 1):
                try:
                    p0 = verts[idxs[0]]; p1 = verts[idxs[k]]; p2 = verts[idxs[k+1]]
                except IndexError:
                    continue
                acc.add_triangle(p0, p1, p2)
    if acc.n_face == 0:
        return None
    return acc.finalize("obj")


# ══════════════════════════════════════════════════════════════════════════════
# 五、GLB 读取 (glTF 2.0 binary; 读取 POSITION + 三角面, 不依赖 pygltflib)
# ══════════════════════════════════════════════════════════════════════════════

_GLTF_COMPONENT_TYPES = {
    5120: ("b", 1),    # BYTE
    5121: ("B", 1),    # UNSIGNED_BYTE
    5122: ("h", 2),    # SHORT
    5123: ("H", 2),    # UNSIGNED_SHORT
    5125: ("I", 4),    # UNSIGNED_INT
    5126: ("f", 4),    # FLOAT
}
_GLTF_TYPE_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
                     "MAT2": 4, "MAT3": 9, "MAT4": 16}


def _gltf_read_accessor(accessor_idx: int, gltf: dict, buffer_bytes: bytes) -> List[Any]:
    """读取 glTF accessor → Python list. 返回 [scalar|tuple] 列表."""
    acc = gltf["accessors"][accessor_idx]
    count = acc["count"]
    fmt_char, elem_bytes = _GLTF_COMPONENT_TYPES[acc["componentType"]]
    ncomp = _GLTF_TYPE_COUNTS[acc["type"]]
    bv = gltf["bufferViews"][acc["bufferView"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride", ncomp * elem_bytes)
    out: List[Any] = []
    struct_fmt = "<" + fmt_char * ncomp
    struct_size = struct.calcsize(struct_fmt)
    for i in range(count):
        off = start + i * stride
        tup = struct.unpack_from(struct_fmt, buffer_bytes, off)
        out.append(tup if ncomp > 1 else tup[0])
    return out


def read_glb(path: PathLike, *, check_manifold: bool = False) -> Optional[MeshStats]:
    """
    解析 GLB → MeshStats. 遍历所有 mesh.primitives, 应用节点层级变换.
    只处理 TRIANGLES (mode=4 或缺省) 和 POSITION + indices.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = p.read_bytes()
    except Exception:
        return None
    if len(data) < 20 or data[:4] != b"glTF":
        return None
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2:
        return None
    # JSON chunk
    off = 12
    json_len, json_type = struct.unpack_from("<II", data, off); off += 8
    if json_type != 0x4E4F534A:  # 'JSON'
        return None
    try:
        gltf = json.loads(data[off:off+json_len].decode("utf-8"))
    except Exception:
        return None
    off += json_len
    # BIN chunk (optional but needed for embedded buffers)
    buffer_bytes = b""
    if off < len(data):
        bin_len, bin_type = struct.unpack_from("<II", data, off); off += 8
        if bin_type == 0x004E4942:  # 'BIN\0'
            buffer_bytes = bytes(data[off:off+bin_len])
    # Handle buffers[0].uri = 'data:application/octet-stream;base64,...' fallback
    if not buffer_bytes and gltf.get("buffers"):
        buf0 = gltf["buffers"][0]
        uri = buf0.get("uri", "")
        if uri.startswith("data:") and "base64," in uri:
            try:
                buffer_bytes = base64.b64decode(uri.split("base64,", 1)[1])
            except Exception:
                buffer_bytes = b""
    if not buffer_bytes:
        return None

    # Compute node transforms (row-major 4x4) via recursion of default scene
    nodes = gltf.get("nodes", []) or []
    scenes = gltf.get("scenes", []) or []
    scene_idx = gltf.get("scene", 0)
    root_nodes: List[int] = list(scenes[scene_idx].get("nodes", [])) if scenes else list(range(len(nodes)))

    def node_mat(n: dict) -> List[float]:
        if "matrix" in n and len(n["matrix"]) == 16:
            return list(n["matrix"])                  # column-major per glTF spec
        # Trs → M = T · R · S (column-major result, consistent with glTF spec)
        t = n.get("translation", [0.0, 0.0, 0.0])
        r = n.get("rotation", [0.0, 0.0, 0.0, 1.0])   # quaternion xyzw
        s = n.get("scale", [1.0, 1.0, 1.0])
        # Rotation matrix (row-major), then layout column-major
        qx, qy, qz, qw = r
        xx, yy, zz = qx*qx, qy*qy, qz*qz
        xy, xz, yz = qx*qy, qx*qz, qy*qz
        wx, wy, wz = qw*qx, qw*qy, qw*qz
        R = [
            1-2*(yy+zz),  2*(xy - wz),  2*(xz + wy),
            2*(xy + wz),  1-2*(xx+zz),  2*(yz - wx),
            2*(xz - wy),  2*(yz + wx),  1-2*(xx+yy),
        ]
        # Column-major 4x4: [col0 col1 col2 col3]
        sx, sy, sz = s
        tx, ty, tz = t
        return [
            R[0]*sx, R[3]*sx, R[6]*sx, 0.0,  # col 0 = scale x · first basis
            R[1]*sy, R[4]*sy, R[7]*sy, 0.0,
            R[2]*sz, R[5]*sz, R[8]*sz, 0.0,
            tx, ty, tz, 1.0,
        ]

    def mat_mul(A: List[float], B: List[float]) -> List[float]:
        """Column-major 4x4 multiply: C = A · B."""
        out = [0.0] * 16
        for c in range(4):
            for r in range(4):
                s = 0.0
                for k in range(4):
                    s += A[k*4 + r] * B[c*4 + k]
                out[c*4 + r] = s
        return out

    def mat_apply(M: List[float], p: Vec3) -> Vec3:
        x, y, z = p
        return (
            M[0]*x + M[4]*y + M[8]*z + M[12],
            M[1]*x + M[5]*y + M[9]*z + M[13],
            M[2]*x + M[6]*y + M[10]*z + M[14],
        )

    acc = _Accumulator(track_edges=check_manifold)

    def walk(node_idx: int, parent_mat: List[float]) -> None:
        if node_idx < 0 or node_idx >= len(nodes):
            return
        n = nodes[node_idx]
        M = mat_mul(parent_mat, node_mat(n))
        mesh_idx = n.get("mesh")
        if mesh_idx is not None and mesh_idx < len(gltf.get("meshes", [])):
            for prim in gltf["meshes"][mesh_idx].get("primitives", []):
                mode = prim.get("mode", 4)
                if mode != 4:            # only TRIANGLES (4) — skip lines/points
                    continue
                pos_acc = prim.get("attributes", {}).get("POSITION")
                if pos_acc is None:
                    continue
                positions = _gltf_read_accessor(pos_acc, gltf, buffer_bytes)
                # Transform positions
                tpos = [mat_apply(M, p) for p in positions]
                idx_acc = prim.get("indices")
                if idx_acc is None:
                    for i in range(0, len(tpos) - 2, 3):
                        acc.add_triangle(tpos[i], tpos[i+1], tpos[i+2])
                else:
                    indices = _gltf_read_accessor(idx_acc, gltf, buffer_bytes)
                    for i in range(0, len(indices) - 2, 3):
                        try:
                            acc.add_triangle(tpos[indices[i]],
                                             tpos[indices[i+1]],
                                             tpos[indices[i+2]])
                        except IndexError:
                            continue
        for child in n.get("children", []) or []:
            walk(child, M)

    identity = [1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0]
    for rn in root_nodes:
        walk(rn, identity)

    if acc.n_face == 0:
        return None
    return acc.finalize("glb")


# ══════════════════════════════════════════════════════════════════════════════
# 五点五、三角面级读写 · 用于网格合并/写出 (merge_vbelt 等场景)
# ══════════════════════════════════════════════════════════════════════════════

Triangle = Tuple[Vec3, Vec3, Vec3, Vec3]   # (normal, v0, v1, v2)


def read_stl_triangles(path: PathLike) -> List[Triangle]:
    """
    读取二进制 STL → 三角列表 [(normal, v0, v1, v2), ...].
    非二进制或读取失败时返回空列表.
    """
    p = Path(path)
    try:
        data = p.read_bytes()
    except Exception:
        return []
    if not is_stl_binary(data):
        return []
    n_tri = struct.unpack_from("<I", data, 80)[0]
    tris: List[Triangle] = []
    off = 84
    for _ in range(n_tri):
        n  = struct.unpack_from("<3f", data, off); off += 12
        v0 = struct.unpack_from("<3f", data, off); off += 12
        v1 = struct.unpack_from("<3f", data, off); off += 12
        v2 = struct.unpack_from("<3f", data, off); off += 12
        off += 2
        tris.append((n, v0, v1, v2))
    return tris


def write_stl_binary(path: PathLike, triangles: List[Triangle],
                     header: bytes = b"dao_mesh") -> int:
    """
    将三角列表写为 Magics 风格二进制 STL. 返回写入的字节数.

    triangles 元素结构: (normal, v0, v1, v2), 每个都是 (x, y, z) 三元组.
    header 会被填/截到 80 字节.
    """
    h = header[:80].ljust(80, b"\x00")
    out = bytearray()
    out.extend(h)
    out.extend(struct.pack("<I", len(triangles)))
    for n, v0, v1, v2 in triangles:
        out.extend(struct.pack("<3f", *n))
        out.extend(struct.pack("<3f", *v0))
        out.extend(struct.pack("<3f", *v1))
        out.extend(struct.pack("<3f", *v2))
        out.extend(struct.pack("<H", 0))
    Path(path).write_bytes(bytes(out))
    return len(out)


# ══════════════════════════════════════════════════════════════════════════════
# 六、统一入口 · read_mesh(path)
# ══════════════════════════════════════════════════════════════════════════════

def read_mesh(path: PathLike, *, check_manifold: bool = False) -> Optional[MeshStats]:
    """
    按文件扩展名分派到对应读取器.
    失败统一返回 None, 调用方可简洁处理.
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".stl":
        return read_stl(p, check_manifold=check_manifold)
    if ext == ".obj":
        return read_obj(p, check_manifold=check_manifold)
    if ext == ".glb":
        return read_glb(p, check_manifold=check_manifold)
    # Last-resort sniff
    try:
        data = p.read_bytes()
        if is_stl_binary(data):
            return read_stl_binary(data, check_manifold=check_manifold)
        if data.startswith(b"solid "):
            return read_stl_ascii(data, check_manifold=check_manifold)
        if data.startswith(b"glTF"):
            return read_glb(p, check_manifold=check_manifold)
    except Exception:
        return None
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 七、自验证 · python dao_mesh.py
# ══════════════════════════════════════════════════════════════════════════════

def _self_test() -> int:
    """生成最小 STL (unit tetra) → 读回 → 验证面数 / bbox / 体积."""
    # Unit tetrahedron vertices:
    v0 = (0.0, 0.0, 0.0)
    v1 = (1.0, 0.0, 0.0)
    v2 = (0.0, 1.0, 0.0)
    v3 = (0.0, 0.0, 1.0)
    # Outward-facing triangles (ccw from outside)
    tris = [
        (v1, v2, v3),  # far face
        (v0, v3, v2),  # -x
        (v0, v1, v3),  # -y
        (v0, v2, v1),  # -z
    ]

    # ── Build binary STL ──
    import io
    buf = io.BytesIO()
    buf.write(b"Unit Tetra - dao_mesh self-test".ljust(80, b" "))
    buf.write(struct.pack("<I", len(tris)))
    for p0, p1, p2 in tris:
        # normal = 0 (ignored)
        buf.write(struct.pack("<3f", 0.0, 0.0, 0.0))
        for p in (p0, p1, p2):
            buf.write(struct.pack("<3f", *p))
        buf.write(struct.pack("<H", 0))
    data = buf.getvalue()
    assert is_stl_binary(data), "is_stl_binary must recognise generated file"
    st = read_stl_binary(data, check_manifold=True)
    assert st is not None, "binary STL parse failed"
    assert st.faces == 4, f"faces={st.faces}"
    assert abs(st.volume - 1.0/6.0) < 1e-6, f"volume={st.volume}"
    assert st.bbox_min == (0.0, 0.0, 0.0), st.bbox_min
    assert st.bbox_max == (1.0, 1.0, 1.0), st.bbox_max
    assert st.closed_heuristic is True, f"manifold={st.closed_heuristic}"
    assert abs(st.surface_area - (1.5 + math.sqrt(3)/2)) < 1e-4, st.surface_area
    print(f"  OK  binary STL: faces={st.faces} vol={st.volume:.6f} area={st.surface_area:.6f} closed={st.closed_heuristic}")

    # ── Build ASCII STL ──
    lines = ["solid tetra"]
    for p0, p1, p2 in tris:
        lines.append("  facet normal 0 0 0")
        lines.append("    outer loop")
        for p in (p0, p1, p2):
            lines.append(f"      vertex {p[0]} {p[1]} {p[2]}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid tetra")
    ascii_data = "\n".join(lines).encode("ascii")
    st2 = read_stl_ascii(ascii_data, check_manifold=True)
    assert st2 is not None, "ASCII STL parse failed"
    assert st2.faces == 4, f"faces={st2.faces}"
    assert abs(st2.volume - 1.0/6.0) < 1e-6, f"volume={st2.volume}"
    assert st2.closed_heuristic is True
    print(f"  OK  ascii  STL: faces={st2.faces} vol={st2.volume:.6f} closed={st2.closed_heuristic}")

    # ── OBJ round-trip (tetra, fan-triangulated from face quad) ──
    obj_text = """
v 0 0 0
v 1 0 0
v 0 1 0
v 0 0 1
f 2 3 4
f 1 4 3
f 1 2 4
f 1 3 2
""".strip()
    tmp = Path("__dao_mesh_test.obj")
    tmp.write_text(obj_text, encoding="utf-8")
    try:
        st3 = read_obj(tmp)
        assert st3 is not None and st3.faces == 4, f"obj faces={st3 and st3.faces}"
        assert abs(st3.volume - 1.0/6.0) < 1e-6, f"obj vol={st3.volume}"
        print(f"  OK  obj       : faces={st3.faces} vol={st3.volume:.6f}")
    finally:
        tmp.unlink(missing_ok=True)

    # ── Dispatcher ──
    tmp2 = Path("__dao_mesh_test.stl")
    tmp2.write_bytes(data)
    try:
        st4 = read_mesh(tmp2)
        assert st4 and st4.format == "stl_binary"
        print(f"  OK  dispatch stl_binary via read_mesh")
    finally:
        tmp2.unlink(missing_ok=True)

    # ── Triangle-level read/write round-trip ──
    tri_path = Path("__dao_mesh_test_tri.stl")
    tri_path.write_bytes(data)
    try:
        tris = read_stl_triangles(tri_path)
        assert len(tris) == 4, f"triangles={len(tris)}"
        out_path = Path("__dao_mesh_test_roundtrip.stl")
        n_bytes = write_stl_binary(out_path, tris, header=b"dao_mesh test")
        try:
            assert n_bytes == 84 + 4 * 50, f"bytes={n_bytes}"
            st5 = read_stl(out_path)
            assert st5 and st5.faces == 4, f"rt_faces={st5 and st5.faces}"
            assert abs(st5.volume - 1.0/6.0) < 1e-6, f"rt_vol={st5.volume}"
            print(f"  OK  triangles round-trip: {len(tris)} tris, {n_bytes} bytes")
        finally:
            out_path.unlink(missing_ok=True)
    finally:
        tri_path.unlink(missing_ok=True)

    print("\n  dao_mesh self-test: all assertions passed ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
