#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
道 · FreeCAD 反者 — 从件逆向突破 · v1.0
═══════════════════════════════════════════════════════════════
反者道之动，弱者道之用。天下万物生于有，有生于无。

不从创造出发，从已有出发 — 任何 FreeCAD 件 (.FCStd/.STEP/.BREP)
皆可被逆向成可重放、可参数化修改的 DaoForge ops 序列。

最小化开发，最大化效果：一文件整合三能力
  ① Reverse  — FCStd/STEP/BREP → ops.json   (意图反演)
  ② Index    — 扫描天下件，建立统一索引      (资源整合)
  ③ Replay   — ops.json → 重建/改参/再导出   (无为而无不为)

═══════════════════════════════════════════════════════════════
CLI
───────────────────────────────────────────────────────────────
  python fc_reverse.py reverse  <file>             → ops.json
  python fc_reverse.py index    [--refresh]        → resource_index.json
  python fc_reverse.py search   <query> [--limit N]
  python fc_reverse.py replay   <ops.json> [--label L] [--patch key=val,...]
  python fc_reverse.py probe    <file>             → 完整诊断报告
  python fc_reverse.py adapt    <file> key=val...  → 反演+改参+重放 (一键)

═══════════════════════════════════════════════════════════════
Python API
───────────────────────────────────────────────────────────────
  from fc_reverse import FCReverse
  ops = FCReverse.reverse("model.FCStd")                      # → ops list
  patched = FCReverse.patch(ops, {"b1.L": 80, "c1.R": 15})    # 按id.param
  result = FCReverse.replay(patched, label="adapted")
  index = FCReverse.index()                                    # → dict
  hits  = FCReverse.search("gear")                             # → list
"""
from __future__ import annotations

import json
import os
import re
import sys
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
ROOT_DIR = _DAO_ROOT
# ═══════════════════════════════════════════════════════════════════

CACHE_DIR = _dao_paths.WORLD / ".resource_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
INDEX_FILE = CACHE_DIR / "resource_index.json"
BRP_CACHE = CACHE_DIR / "brp"  # 从FCStd提取的.brp文件缓存

__version__ = "1.0.0"
__all__ = ["FCReverse", "FC_TYPE_TO_OP", "REVERSE_ROOTS"]

# ═══════════════════════════════════════════════════════════════
# FreeCAD Type → DaoForge Op 映射表
# 由逆向解构 FreeCAD 本源 (Part/PartDesign/App) 推演
# ═══════════════════════════════════════════════════════════════
#   (op_name, {fc_property: op_key}, is_boolean)
FC_TYPE_TO_OP: Dict[str, Tuple[str, Dict[str, str], bool]] = {
    # ── 原始几何体 ────────────────────────────────────────────
    "Part::Box":         ("make_box",      {"Length": "L", "Width": "W", "Height": "H"}, False),
    "Part::Cylinder":    ("make_cylinder", {"Radius": "R", "Height": "H", "Angle": "angle"}, False),
    "Part::Sphere":      ("make_sphere",   {"Radius": "R"}, False),
    "Part::Cone":        ("make_cone",     {"Radius1": "R1", "Radius2": "R2", "Height": "H", "Angle": "angle"}, False),
    "Part::Torus":       ("make_torus",    {"Radius1": "R1", "Radius2": "R2"}, False),
    "Part::Ellipsoid":   ("make_ellipsoid", {"Radius1": "rx", "Radius2": "ry", "Radius3": "rz"}, False),
    "Part::Wedge":       ("make_wedge",    {"Xmin": "xmin", "Xmax": "xmax",
                                            "Ymin": "ymin", "Ymax": "ymax",
                                            "Zmin": "zmin", "Zmax": "zmax",
                                            "X2min": "x2min", "X2max": "x2max",
                                            "Z2min": "z2min", "Z2max": "z2max"}, False),
    "Part::Prism":       ("make_prism",    {"Polygon": "n", "Circumradius": "R", "Height": "H"}, False),
    "Part::RegularPolygon": ("make_reg_polygon", {"Polygon": "n", "Circumradius": "R"}, False),
    # ── 布尔运算 (Base/Tool → 依赖引用) ───────────────────────
    "Part::Cut":         ("cut",           {"Base": "base", "Tool": "tool"}, True),
    "Part::Fuse":        ("fuse",          {"Base": "base", "Tool": "tool"}, True),
    "Part::Common":      ("common",        {"Base": "base", "Tool": "tool"}, True),
    "Part::Section":     ("section",       {"Base": "base", "Tool": "tool"}, True),
    "Part::MultiFuse":   ("fuse",          {"Shapes": "shapes"}, True),
    "Part::MultiCommon": ("common",        {"Shapes": "shapes"}, True),
    "Part::Compound":    ("compound",      {"Links": "shapes"}, True),
    # ── 修饰器 ────────────────────────────────────────────────
    "Part::Fillet":      ("fillet",        {"Base": "shape", "Radius": "radius"}, True),
    "Part::Chamfer":     ("chamfer",       {"Base": "shape", "Size": "size"}, True),
    "Part::Offset":      ("offset3d",      {"Source": "shape", "Value": "offset"}, True),
    "Part::Thickness":   ("shell",         {"Faces": "shape", "Value": "thickness"}, True),
    "Part::Mirroring":   ("mirror",        {"Source": "shape", "Normal": "plane"}, True),
    # ── 衍生操作 ──────────────────────────────────────────────
    "Part::Extrusion":   ("extrude",       {"Base": "shape", "LengthFwd": "length"}, True),
    "Part::Revolution":  ("revolve",       {"Source": "shape", "Angle": "angle"}, True),
    "Part::Loft":        ("loft",          {"Sections": "profiles"}, True),
    "Part::Sweep":       ("pipe",          {"Sections": "profile", "Spine": "spine"}, True),
    # ── PartDesign (Body/Pad/Pocket) ─────────────────────────
    "PartDesign::Pad":     ("partdesign_pad",    {"Profile": "face", "Length": "length"}, True),
    "PartDesign::Pocket":  ("partdesign_pocket", {"Profile": "profile", "Length": "depth"}, True),
    "PartDesign::Fillet":  ("partdesign_fillet", {"Base": "base", "Radius": "radius"}, True),
    "PartDesign::Chamfer": ("chamfer",           {"Base": "shape", "Size": "size"}, True),
}

# 通用几何容器 (仅存BRep引用, 需要 import_brep 回放)
FC_FEATURE_TYPES = {"Part::Feature", "Part::FeaturePython"}

# 资源扫描根目录 (按优先级) — 定义天下之所在
_FC_1_0 = Path(r"D:\安装的软件\FreeCAD 1.0")
_FC_021 = Path(r"D:\安装的软件\FreeCAD 0.21")

REVERSE_ROOTS: List[Tuple[str, Path]] = [
    ("freecad_examples_1_0", _FC_1_0 / "data" / "examples"),
    ("freecad_mod_1_0",      _FC_1_0 / "Mod"),
    ("freecad_examples_0_21", _FC_021 / "data" / "examples"),
    ("projects",             _dao_paths.PROJECTS),
    ("templates",            _dao_paths.TEMPLATES),
    ("demo",                 _dao_paths.DEMO),
    ("网络资源库",           _dao_paths.WORLD / "网络资源库"),
]

SUPPORTED_EXT = {
    ".fcstd": "fcstd",
    ".FCStd": "fcstd",
    ".step": "step",
    ".stp":  "step",
    ".brep": "brep",
    ".brp":  "brep",
    ".stl":  "stl",
    ".iges": "iges",
    ".igs":  "iges",
    ".obj":  "obj",
    ".scad": "scad",
    ".py":   "py_cad",  # 仅在 templates/ 下视为参数化模型
}


# ═══════════════════════════════════════════════════════════════
# ① Reverse — FCStd / STEP / BREP → ops
# ═══════════════════════════════════════════════════════════════

_RE_OBJECT_ROOT = re.compile(r'<Object\s+type="([^"]+)"\s+name="([^"]+)"', re.DOTALL)
_RE_OBJECT_DATA = re.compile(r'<Object\s+name="([^"]+)"[^>]*>(.*?)</Object>', re.DOTALL)
_RE_FLOAT_PROP  = re.compile(
    r'<Property\s+name="([^"]+)"[^>]*>\s*<Float\s+value="([^"]+)"'
)
_RE_INT_PROP    = re.compile(
    r'<Property\s+name="([^"]+)"[^>]*>\s*<Integer\s+value="([^"]+)"'
)
_RE_BOOL_PROP   = re.compile(
    r'<Property\s+name="([^"]+)"[^>]*>\s*<Bool\s+value="([^"]+)"'
)
_RE_STRING_PROP = re.compile(
    r'<Property\s+name="([^"]+)"[^>]*>\s*<String\s+value="([^"]*)"'
)
_RE_LINK_PROP   = re.compile(
    r'<Property\s+name="([^"]+)"[^>]*>\s*<Link\s+value="([^"]+)"'
)
_RE_PLACEMENT   = re.compile(
    r'<Property\s+name="Placement"[^>]*>\s*<PropertyPlacement\s+'
    r'Px="([^"]+)"\s+Py="([^"]+)"\s+Pz="([^"]+)"'
    r'\s+Q0="([^"]+)"\s+Q1="([^"]+)"\s+Q2="([^"]+)"\s+Q3="([^"]+)"'
    r'\s+A="([^"]+)"'
    r'\s+Ox="([^"]+)"\s+Oy="([^"]+)"\s+Oz="([^"]+)"'
)
_RE_DEPS = re.compile(
    r'<ObjectDeps\s+Name="([^"]+)"[^>]*>(.*?)</ObjectDeps>',
    re.DOTALL,
)
_RE_DEP  = re.compile(r'<Dep\s+Name="([^"]+)"')
_RE_SHAPE_FILE = re.compile(
    r'<Property\s+name="Shape"[^>]*>\s*<Part\s+[^>]*file="([^"]+)"'
)


def _parse_object_properties(body: str) -> Dict[str, Any]:
    """从一个 <Object>...</Object> 块中提取所有属性值."""
    props: Dict[str, Any] = {}
    for m in _RE_FLOAT_PROP.finditer(body):
        props[m.group(1)] = float(m.group(2))
    for m in _RE_INT_PROP.finditer(body):
        try:
            props[m.group(1)] = int(m.group(2))
        except ValueError:
            pass
    for m in _RE_BOOL_PROP.finditer(body):
        props[m.group(1)] = (m.group(2).lower() == "true")
    for m in _RE_STRING_PROP.finditer(body):
        props[m.group(1)] = m.group(2)
    for m in _RE_LINK_PROP.finditer(body):
        # 保留原始 Link 结构，带 _LINK 前缀以便替换成 op_id
        props[m.group(1)] = {"_link": m.group(2)}
    # Placement
    pm = _RE_PLACEMENT.search(body)
    if pm:
        (px, py, pz, q0, q1, q2, q3, A, ox, oy, oz) = [float(v) for v in pm.groups()]
        props["Placement"] = {
            "pos": [round(px, 6), round(py, 6), round(pz, 6)],
            "axis": [round(ox, 6), round(oy, 6), round(oz, 6)],
            "angle": round(A, 6),
            "quat": [round(q0, 6), round(q1, 6), round(q2, 6), round(q3, 6)],
        }
    # Shape brp 引用 (Part::Feature 保留)
    sm = _RE_SHAPE_FILE.search(body)
    if sm:
        props["_brp_ref"] = sm.group(1)
    return props


def _parse_fcstd_full(path: Path) -> Dict[str, Any]:
    """完整解析 FCStd，返回 objects (含属性值) + dependencies + entries.

    使用 ElementTree 做结构解析 (Object 列表 / ObjectDeps)；
    用正则从每个 ObjectData/Object 子树的字符串化表示中提取 Properties 值.
    """
    info: Dict[str, Any] = {
        "path": str(path), "valid": False,
        "objects": [], "dependencies": {}, "entries": [],
        "document": {}, "thumbnail": False,
    }
    try:
        with zipfile.ZipFile(path) as z:
            info["entries"] = z.namelist()
            info["thumbnail"] = any(e.startswith("thumbnails/") for e in info["entries"])
            if "Document.xml" not in info["entries"]:
                info["error"] = "No Document.xml"
                return info
            xml_bytes = z.read("Document.xml")
        info["valid"] = True
    except zipfile.BadZipFile:
        info["error"] = "Not a valid zip (FCStd)"
        return info
    except Exception as e:
        info["error"] = f"Parse error: {e}"
        return info

    # 结构解析 (ElementTree 处理嵌套/自闭合标签正确)
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        info["error"] = f"XML parse error: {e}"
        return info

    # 文档版本
    info["document"]["schema_version"] = root.get("SchemaVersion")
    info["document"]["program_version"] = root.get("ProgramVersion")

    # Object 列表 (按原顺序 = 依赖拓扑顺序)
    obj_order: List[Tuple[str, str]] = []
    for obj in root.findall("./Objects/Object"):
        t = obj.get("type", "")
        n = obj.get("name", "")
        if t and n:
            obj_order.append((t, n))

    # 依赖图 (ObjectDeps)
    deps: Dict[str, List[str]] = {}
    for od in root.findall("./Objects/ObjectDeps"):
        owner = od.get("Name", "")
        if not owner:
            continue
        dep_list = [d.get("Name", "") for d in od.findall("Dep") if d.get("Name")]
        deps[owner] = dep_list
    info["dependencies"] = deps

    # Properties 值解析: 在每个 ObjectData/Object 的 XML 串上跑正则
    obj_data: Dict[str, Dict[str, Any]] = {}
    for obj in root.findall("./ObjectData/Object"):
        name = obj.get("name", "")
        if not name:
            continue
        # 序列化此节点为字符串再跑属性正则
        body = ET.tostring(obj, encoding="unicode")
        obj_data[name] = _parse_object_properties(body)

    for t, n in obj_order:
        info["objects"].append({
            "name": n,
            "type": t,
            "props": obj_data.get(n, {}),
            "deps": deps.get(n, []),
        })

    return info


def _safe_id(name: str, used: set) -> str:
    """把 FreeCAD name → 合法 ops id (去空格/非ASCII/保唯一)."""
    base = re.sub(r"[^A-Za-z0-9_]", "_", name) or "obj"
    base = base.strip("_") or "obj"
    if base[0].isdigit():
        base = f"x{base}"
    cand = base
    i = 1
    while cand in used:
        cand = f"{base}_{i}"
        i += 1
    used.add(cand)
    return cand


def _placement_pos(props: Dict[str, Any]) -> Optional[List[float]]:
    """提取 Placement 的平移向量 (若非零才返回)."""
    pm = props.get("Placement")
    if not isinstance(pm, dict):
        return None
    pos = pm.get("pos") or [0, 0, 0]
    if sum(abs(x) for x in pos) < 1e-6:
        return None
    return pos


def _fcstd_objects_to_ops(
    objects: List[Dict[str, Any]],
    brp_dir: Optional[Path] = None,
    fcstd_path: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    把 FCStd 的 Object 列表按依赖顺序转为 DaoForge ops 序列.

    Returns:
        (ops, meta): ops 列表 + 元信息 (含 name→id 映射)
    """
    used_ids: set = set()
    name_to_id: Dict[str, str] = {}
    ops: List[Dict[str, Any]] = []
    warnings: List[str] = []
    leaf_id: Optional[str] = None

    # 已处理 set — 避免依赖问题重复处理
    done: set = set()
    in_progress: set = set()  # 防止依赖环
    # 依赖表 (name → deps)
    deps_map = {o["name"]: o.get("deps", []) for o in objects}
    by_name  = {o["name"]: o for o in objects}

    def emit(name: str):
        nonlocal leaf_id
        if name in done:
            return
        if name in in_progress:
            warnings.append(f"{name}: dependency cycle detected (skipped)")
            return
        in_progress.add(name)
        # 先处理依赖 (跳过自依赖)
        for dep in deps_map.get(name, []):
            if dep == name:
                warnings.append(f"{name}: self-dependency (skipped)")
                continue
            if dep in by_name and dep not in done:
                emit(dep)
        obj = by_name[name]
        t, props = obj["type"], obj["props"]

        oid = _safe_id(name, used_ids)
        name_to_id[name] = oid

        if t in FC_TYPE_TO_OP:
            op_name, prop_map, is_dep = FC_TYPE_TO_OP[t]
            op: Dict[str, Any] = {"op": op_name, "id": oid}
            for fc_key, op_key in prop_map.items():
                val = props.get(fc_key)
                if val is None:
                    continue
                if isinstance(val, dict) and "_link" in val:
                    # Link → 引用已生成的 id
                    linked = name_to_id.get(val["_link"])
                    if linked is None:
                        warnings.append(f"{name}: Link '{val['_link']}' not found")
                        continue
                    op[op_key] = linked
                else:
                    op[op_key] = val
            # Placement → pos
            pos = _placement_pos(props)
            if pos is not None:
                op["pos"] = pos
            ops.append(op)
            leaf_id = oid

        elif t in FC_FEATURE_TYPES:
            # Part::Feature - 仅含 BRep 引用, 需提取并用 import_brep 重放
            brp_ref = props.get("_brp_ref")
            if brp_ref and fcstd_path and brp_dir:
                try:
                    brp_dir.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(fcstd_path) as z:
                        if brp_ref in z.namelist():
                            brp_out = brp_dir / f"{fcstd_path.stem}__{name}.brp"
                            brp_out.write_bytes(z.read(brp_ref))
                            op = {
                                "op": "import_brep",
                                "id": oid,
                                "path": str(brp_out),
                            }
                            pos = _placement_pos(props)
                            if pos is not None:
                                op["_placement_pos"] = pos
                            ops.append(op)
                            leaf_id = oid
                        else:
                            warnings.append(f"{name}: brp '{brp_ref}' not in archive")
                except Exception as e:
                    warnings.append(f"{name}: brp extract failed: {e}")
            else:
                warnings.append(f"{name}: Part::Feature without brp ref (skipped)")

        else:
            # 未知类型 - 记录警告, 不生成ops
            warnings.append(f"{name}: unsupported type '{t}' (skipped)")

        in_progress.discard(name)
        done.add(name)

    for obj in objects:
        emit(obj["name"])

    meta = {
        "name_to_id": name_to_id,
        "warnings": warnings,
        "leaf_id": leaf_id,
        "object_count": len(objects),
        "op_count": len(ops),
    }
    return ops, meta


# ═══════════════════════════════════════════════════════════════
# ② Index — 扫描天下件，建立统一索引
# ═══════════════════════════════════════════════════════════════


def _file_entry(fp: Path, root_name: str) -> Dict[str, Any]:
    """一个文件 → 索引条目."""
    try:
        stat = fp.stat()
    except OSError:
        return {"path": str(fp), "error": "stat_failed"}
    ext = fp.suffix.lower()
    kind = SUPPORTED_EXT.get(ext, "other")
    name_tokens = re.split(r"[_\-\s/\\\.]", fp.stem.lower())
    name_tokens = [t for t in name_tokens if t and not t.isdigit()]
    return {
        "path": str(fp),
        "root": root_name,
        "stem": fp.stem,
        "ext": ext,
        "kind": kind,
        "size_bytes": stat.st_size,
        "mtime": int(stat.st_mtime),
        "tokens": name_tokens,
    }


def _scan_root(root_name: str, root: Path, limit: int = 5000) -> List[Dict[str, Any]]:
    """扫描一个根目录下所有支持的文件."""
    if not root.exists():
        return []
    entries: List[Dict[str, Any]] = []
    # .py 文件只在 templates 下索引 (避免扫描整个 Python 环境)
    py_ok = root_name in ("templates", "网络资源库", "demo")
    for fp in root.rglob("*"):
        if not fp.is_file():
            continue
        ext = fp.suffix.lower()
        if ext not in SUPPORTED_EXT:
            continue
        if ext == ".py" and not py_ok:
            continue
        # 跳过 git / cache
        parts_lower = [p.lower() for p in fp.parts]
        if any(p in (".git", "__pycache__", ".resource_cache", ".venv", "node_modules")
               for p in parts_lower):
            continue
        entries.append(_file_entry(fp, root_name))
        if len(entries) >= limit:
            break
    return entries


def _build_index(refresh: bool = False) -> Dict[str, Any]:
    """扫描所有根，生成统一索引."""
    if INDEX_FILE.exists() and not refresh:
        try:
            idx = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            if idx.get("version") == __version__:
                return idx
        except Exception:
            pass
    t0 = time.time()
    all_entries: List[Dict[str, Any]] = []
    by_root: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}
    for root_name, root in REVERSE_ROOTS:
        chunk = _scan_root(root_name, root)
        by_root[root_name] = len(chunk)
        for e in chunk:
            by_kind[e.get("kind", "other")] = by_kind.get(e.get("kind", "other"), 0) + 1
        all_entries.extend(chunk)
    idx = {
        "version": __version__,
        "generated_at": int(time.time()),
        "elapsed_s": round(time.time() - t0, 3),
        "total": len(all_entries),
        "by_root": by_root,
        "by_kind": by_kind,
        "entries": all_entries,
    }
    INDEX_FILE.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    return idx


def _search_index(query: str, limit: int = 20, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """按名字/tokens 搜索索引，简单TF评分."""
    idx = _build_index(refresh=False)
    terms = [t for t in re.split(r"\s+", query.lower().strip()) if t]
    if not terms:
        return []
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for e in idx.get("entries", []):
        if kind and e.get("kind") != kind:
            continue
        stem_low = e.get("stem", "").lower()
        path_low = e.get("path", "").lower()
        tokens = set(e.get("tokens", []))
        score = 0.0
        for t in terms:
            if t == stem_low:
                score += 5
            if t in tokens:
                score += 3
            if t in stem_low:
                score += 2
            if t in path_low:
                score += 1
        if score > 0:
            scored.append((score, e))
    scored.sort(key=lambda x: (-x[0], x[1].get("size_bytes", 0)))
    return [e for _, e in scored[:limit]]


# ═══════════════════════════════════════════════════════════════
# ③ Replay — ops → DaoForge → 产物
# ═══════════════════════════════════════════════════════════════


def _apply_patch(ops: List[Dict[str, Any]], patch: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    对 ops 按 'id.param' 格式打补丁.
    patch 示例: {"PDBox.L": 80, "PDCyl.R": 15, "PDBox.H": 50}
    """
    if not patch:
        return ops
    # 构建 id → op 索引
    id_to_idx: Dict[str, int] = {}
    for i, op in enumerate(ops):
        if "id" in op:
            id_to_idx[op["id"]] = i
    out = [dict(o) for o in ops]  # 浅拷贝
    for key, val in patch.items():
        if "." not in key:
            continue
        oid, pname = key.split(".", 1)
        idx = id_to_idx.get(oid)
        if idx is None:
            continue
        try:
            # 数字参数自动转float
            if isinstance(val, str):
                try:
                    val_f = float(val)
                    val = val_f
                except ValueError:
                    pass
            out[idx][pname] = val
        except Exception:
            pass
    return out


def _find_leaves(ops: List[Dict[str, Any]]) -> List[str]:
    """
    找到所有叶子节点 id = 有id但未被其他ops引用的对象.

    规则:
      - 只考虑有 id 且 op 不是 export_* 的
      - 排除被其他op的 base/tool/shape/shapes/source/profile/sections 等字段引用的
      - 按原顺序返回
    """
    all_ids: List[str] = []
    referenced: set = set()
    REF_FIELDS = (
        "base", "tool", "shape", "shapes", "source", "profile", "profiles",
        "sections", "spine", "face", "edges", "parts", "tools",
    )
    for op in ops:
        oid = op.get("id")
        opname = op.get("op", "")
        if opname.startswith("export_"):
            continue
        if oid:
            all_ids.append(oid)
        for fld in REF_FIELDS:
            v = op.get(fld)
            if isinstance(v, str):
                referenced.add(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        referenced.add(item)
    leaves = [i for i in all_ids if i not in referenced]
    return leaves or (all_ids[-1:] if all_ids else [])


def _ensure_exports_multi(ops: List[Dict[str, Any]], label: str, out_dir: Path,
                          leaves: List[str]) -> List[Dict[str, Any]]:
    """
    若 ops 末尾没有 export_*，为所有叶子节点补充导出:
      - 多叶子时先 compound 合并为 <label>_all, 再导出 stl/step
      - 单叶子时直接导出
    """
    has_export = any(o.get("op", "").startswith("export_") for o in ops)
    if has_export or not leaves:
        return ops
    out_dir.mkdir(parents=True, exist_ok=True)
    extra: List[Dict[str, Any]] = []
    if len(leaves) == 1:
        target = leaves[0]
    else:
        target = f"_all_{label}"
        extra.append({"op": "compound", "id": target, "shapes": list(leaves)})
    extra += [
        {"op": "export_stl",  "shape": target, "path": str(out_dir / f"{label}.stl")},
        {"op": "export_step", "shape": target, "path": str(out_dir / f"{label}.step")},
    ]
    return ops + extra


def _replay(ops: List[Dict[str, Any]], label: str = "replay",
            timeout: int = 300) -> Dict[str, Any]:
    """通过 DaoForge headless 执行 ops."""
    try:
        from dao_forge import DaoForge  # type: ignore
    except Exception as e:
        return {"ok": False, "errors": [f"DaoForge import failed: {e}"]}
    forge = DaoForge()
    if not forge.available():
        return {"ok": False, "errors": ["freecadcmd not found — install FreeCAD"]}
    return forge.run(ops, label=label, timeout=timeout)


# ═══════════════════════════════════════════════════════════════
# 统一反演入口 (STEP/BREP/FCStd)
# ═══════════════════════════════════════════════════════════════


def _reverse_step(path: Path, out_id: str = "src") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """STEP 文件 → 通过 import_step 一步重放 (FreeCAD 1.0 headless 不支持, 保留声明)."""
    return [
        {"op": "import_step", "id": out_id, "path": str(path)},
    ], {"leaf_id": out_id, "warnings": ["STEP import requires GUI mode in FreeCAD 1.0"],
        "op_count": 1, "object_count": 0, "name_to_id": {"": out_id}}


def _reverse_brep(path: Path, out_id: str = "src") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """BREP → import_brep."""
    return [
        {"op": "import_brep", "id": out_id, "path": str(path)},
    ], {"leaf_id": out_id, "warnings": [],
        "op_count": 1, "object_count": 0, "name_to_id": {"": out_id}}


def _reverse_fcstd(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """FCStd → ops, 全特征逆向."""
    info = _parse_fcstd_full(path)
    if not info.get("valid"):
        return [], {"error": info.get("error", "parse failed"),
                    "op_count": 0, "object_count": 0, "leaf_id": None,
                    "name_to_id": {}, "warnings": []}
    objects = info["objects"]
    brp_dir = BRP_CACHE / path.stem
    ops, meta = _fcstd_objects_to_ops(objects, brp_dir=brp_dir, fcstd_path=path)
    meta["document"] = info["document"]
    meta["source"] = str(path)
    return ops, meta


# ═══════════════════════════════════════════════════════════════
# FCReverse — 顶层 API
# ═══════════════════════════════════════════════════════════════


class FCReverse:
    """道 · 反者. 任何件逆向为ops的统一门面."""

    # ── 反演 ──────────────────────────────────────────────────
    @staticmethod
    def reverse(path: str) -> Dict[str, Any]:
        """
        Reverse a FCStd/STEP/BREP file → ops list + meta.

        Returns:
            {"ok": bool, "ops": [...], "meta": {...}, "source": path}
        """
        fp = Path(path)
        if not fp.exists():
            return {"ok": False, "error": f"file not found: {path}", "ops": [], "meta": {}}
        ext = fp.suffix.lower()
        if ext == ".fcstd":
            ops, meta = _reverse_fcstd(fp)
        elif ext in (".step", ".stp"):
            ops, meta = _reverse_step(fp)
        elif ext in (".brep", ".brp"):
            ops, meta = _reverse_brep(fp)
        else:
            return {"ok": False, "error": f"unsupported: {ext}", "ops": [], "meta": {}}
        return {
            "ok": bool(ops) or not meta.get("error"),
            "ops": ops,
            "meta": meta,
            "source": str(fp),
            "source_ext": ext,
        }

    # ── 改参数 ────────────────────────────────────────────────
    @staticmethod
    def patch(ops: List[Dict[str, Any]], patch: Dict[str, Any]) -> List[Dict[str, Any]]:
        """按 {id.param: new_value} 打补丁."""
        return _apply_patch(ops, patch)

    # ── 重放 ──────────────────────────────────────────────────
    @staticmethod
    def replay(ops: List[Dict[str, Any]], label: str = "replay",
               out_dir: Optional[str] = None, timeout: int = 300) -> Dict[str, Any]:
        """
        通过 DaoForge 执行 ops. 若 ops 无 export_*，自动补充.
        导出所有叶子节点 (未被其他op引用的id) 为 stl + step，
        并用 compound 合并为完整 <label>.stl + .step.
        """
        out = Path(out_dir) if out_dir else (_dao_paths.PROJECTS / "fc_output")
        leaves = _find_leaves(ops)
        ops_final = _ensure_exports_multi(ops, label, out, leaves)
        result = _replay(ops_final, label=label, timeout=timeout)
        result["label"] = label
        result["leaf_id"] = leaves[-1] if leaves else None
        result["leaves"] = leaves
        result["out_dir"] = str(out)
        return result

    # ── 索引 ──────────────────────────────────────────────────
    @staticmethod
    def index(refresh: bool = False) -> Dict[str, Any]:
        """扫描天下之件，返回索引."""
        return _build_index(refresh=refresh)

    @staticmethod
    def search(query: str, limit: int = 20, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """从索引搜索文件."""
        return _search_index(query, limit=limit, kind=kind)

    # ── 一键适配 ──────────────────────────────────────────────
    @staticmethod
    def adapt(path: str, patch: Optional[Dict[str, Any]] = None,
              label: Optional[str] = None) -> Dict[str, Any]:
        """
        一键反演 → 改参 → 重放.

        Usage:
            FCReverse.adapt("my.FCStd", {"PDBox.L": 80})
        """
        rev = FCReverse.reverse(path)
        if not rev.get("ok"):
            return {"ok": False, "stage": "reverse", **rev}
        ops = FCReverse.patch(rev["ops"], patch or {})
        lbl = label or (Path(path).stem + ("_patched" if patch else "_replay"))
        result = FCReverse.replay(ops, label=lbl)
        return {
            "ok": result.get("ok", False),
            "stage": "replay" if not result.get("ok") else "done",
            "reverse": rev["meta"],
            "patch": patch or {},
            "replay": result,
            "ops": ops,
        }

    # ── 诊断 ──────────────────────────────────────────────────
    @staticmethod
    def probe(path: str) -> Dict[str, Any]:
        """完整诊断报告: 文件信息 + 反演结果 + 重放可行性评估."""
        fp = Path(path)
        if not fp.exists():
            return {"ok": False, "error": f"not found: {path}"}
        rev = FCReverse.reverse(path)
        meta = rev.get("meta", {})
        # 分类 ops
        op_types: Dict[str, int] = {}
        for op in rev.get("ops", []):
            op_types[op.get("op", "?")] = op_types.get(op.get("op", "?"), 0) + 1
        return {
            "ok": rev.get("ok"),
            "path": str(fp),
            "size_bytes": fp.stat().st_size,
            "ext": fp.suffix.lower(),
            "op_count": meta.get("op_count", 0),
            "object_count": meta.get("object_count", 0),
            "op_types": op_types,
            "warnings": meta.get("warnings", []),
            "leaf_id": meta.get("leaf_id"),
            "document": meta.get("document", {}),
            "replayable": bool(rev.get("ops")) and not meta.get("error"),
        }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

USAGE = f"""道 · FreeCAD 反者 v{__version__} — 反者道之动

用法:
  reverse <file>              逆向 FCStd/STEP/BREP → ops.json (打印到stdout)
  index [--refresh]           扫描天下件 → 索引
  search <query> [--limit N] [--kind fcstd|step|brep|stl|scad|py_cad]
  replay <ops.json> [--label L] [--patch k=v,k=v]
  adapt <file> [k=v,k=v]      反演+改参+重放 (一键)
  probe <file>                完整诊断报告

示例:
  python fc_reverse.py reverse projects/fc_output/_万法归一/万法.fcstd > ops.json
  python fc_reverse.py index --refresh
  python fc_reverse.py search "gear module" --limit 10
  python fc_reverse.py adapt projects/fc_output/_万法归一/万法.fcstd PDBox.L=100 PDBox.W=50
  python fc_reverse.py probe "D:/安装的软件/FreeCAD 1.0/data/examples/PartDesignExample.FCStd"
"""


def _parse_patch(pairs: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for p in pairs:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        try:
            out[k.strip()] = float(v.strip())
        except ValueError:
            out[k.strip()] = v.strip()
    return out


def _cmd_reverse(args: List[str]) -> int:
    if not args:
        print("Usage: reverse <file>"); return 1
    result = FCReverse.reverse(args[0])
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


def _cmd_index(args: List[str]) -> int:
    refresh = "--refresh" in args
    idx = FCReverse.index(refresh=refresh)
    # 精简输出
    summary = {
        "version": idx["version"],
        "generated_at": idx["generated_at"],
        "elapsed_s": idx["elapsed_s"],
        "total": idx["total"],
        "by_root": idx["by_root"],
        "by_kind": idx["by_kind"],
        "file": str(INDEX_FILE),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_search(args: List[str]) -> int:
    if not args:
        print("Usage: search <query> [--limit N] [--kind ...]"); return 1
    limit = 20
    kind = None
    q_parts: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2; continue
        if a == "--kind" and i + 1 < len(args):
            kind = args[i + 1]; i += 2; continue
        q_parts.append(a); i += 1
    query = " ".join(q_parts)
    hits = FCReverse.search(query, limit=limit, kind=kind)
    if not hits:
        print(json.dumps({"query": query, "count": 0, "hits": []}, ensure_ascii=False))
        return 0
    out = {
        "query": query,
        "count": len(hits),
        "hits": [
            {"kind": h["kind"], "root": h["root"], "stem": h["stem"],
             "size_kb": round(h["size_bytes"] / 1024, 1),
             "path": h["path"]}
            for h in hits
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_replay(args: List[str]) -> int:
    if not args:
        print("Usage: replay <ops.json> [--label L] [--patch k=v,...]"); return 1
    ops_path = Path(args[0])
    if not ops_path.exists():
        print(f"ops file not found: {ops_path}"); return 1
    data = json.loads(ops_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "ops" in data:
        ops = data["ops"]
        label = data.get("label", ops_path.stem)
    else:
        ops = data
        label = ops_path.stem
    patch: Dict[str, Any] = {}
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--label" and i + 1 < len(args):
            label = args[i + 1]; i += 2; continue
        if a == "--patch" and i + 1 < len(args):
            patch.update(_parse_patch(args[i + 1].split(",")))
            i += 2; continue
        i += 1
    if patch:
        ops = FCReverse.patch(ops, patch)
    result = FCReverse.replay(ops, label=label)
    print(json.dumps({
        "ok": result.get("ok"),
        "label": label,
        "op_count": len(ops),
        "patch": patch,
        "errors": result.get("errors", []),
        "exports": result.get("exports", []),
        "elapsed_s": result.get("elapsed_s"),
    }, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_adapt(args: List[str]) -> int:
    if not args:
        print("Usage: adapt <file> [k=v,k=v]"); return 1
    path = args[0]
    patch = _parse_patch(args[1:])
    result = FCReverse.adapt(path, patch=patch)
    # 精简输出
    out = {
        "ok": result.get("ok"),
        "stage": result.get("stage"),
        "source": path,
        "patch": patch,
        "reverse_meta": result.get("reverse", {}),
        "replay": {k: v for k, v in result.get("replay", {}).items()
                   if k not in ("shapes",)},
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


def _cmd_probe(args: List[str]) -> int:
    if not args:
        print("Usage: probe <file>"); return 1
    r = FCReverse.probe(args[0])
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE); return 0
    cmd, rest = args[0].lower(), args[1:]
    if cmd == "reverse": return _cmd_reverse(rest)
    if cmd == "index":   return _cmd_index(rest)
    if cmd == "search":  return _cmd_search(rest)
    if cmd == "replay":  return _cmd_replay(rest)
    if cmd == "adapt":   return _cmd_adapt(rest)
    if cmd == "probe":   return _cmd_probe(rest)
    print(f"Unknown command: {cmd}\n\n{USAGE}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
