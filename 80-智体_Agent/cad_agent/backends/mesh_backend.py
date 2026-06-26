#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mesh_backend.py — mesh 引擎后端 (trimesh) · 把几何能力注入统一工具协议
═══════════════════════════════════════════════════════════════════════════════
弱者道之用 — 以最轻、零外软件依赖的 mesh 引擎做 *参考实现*: 任何环境 (无 FreeCAD/
SolidWorks 亦可) 都能跑通 perceive→act→verify 全闭环. 其它后端 (FreeCAD COM、
SolidWorks COM) 只需登记 *同名同义* 的工具即可被 agent 无差别驱动.

注册的工具族 (引擎无关语义):
    scene.list / scene.clear        场景查询
    mesh.box / cylinder / sphere    参数化图元
    mesh.load / export              文件 IO
    mesh.translate/rotate/scale     刚体与缩放变换
    mesh.boolean                    布尔 (union/difference/intersection)
    mesh.duplicate/delete/rename    对象管理
    mesh.measure                    度量 (bbox/体积/面积/质心/最小间距)
    mesh.perceive                   感知 (多视角 + 结构报告 + 自然语言摘要)
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

try:
    import trimesh  # type: ignore
except Exception as e:  # pragma: no cover
    raise RuntimeError("mesh_backend 需要 trimesh: pip install trimesh") from e

from .. import perception
from ..tools import ToolParam, ToolRegistry, Workspace

__all__ = ["register_mesh_tools"]


# ── workspace 对象 ⇄ trimesh 互转 ──────────────────────────────────────────
def _to_tm(obj: Dict[str, Any]) -> "trimesh.Trimesh":
    return trimesh.Trimesh(vertices=obj["vertices"], faces=obj["faces"], process=False)


def _store(ws: Workspace, name: str, tm: "trimesh.Trimesh",
           meta: Dict[str, Any] | None = None) -> str:
    return ws.put(name, np.asarray(tm.vertices, float),
                  np.asarray(tm.faces, int), meta or {})


def _obj_summary(ws: Workspace, name: str) -> Dict[str, Any]:
    o = ws.get(name)
    V = o["vertices"]
    b = np.array([V.min(axis=0), V.max(axis=0)])
    return {
        "name": name,
        "n_vertices": int(len(V)),
        "n_faces": int(len(o["faces"])),
        "extents": [round(x, 4) for x in (b[1] - b[0])],
        "bbox_center": [round(x, 4) for x in (b[0] + b[1]) * 0.5],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 工具处理函数
# ═══════════════════════════════════════════════════════════════════════════
def _h_scene_list(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    return {"count": len(ws), "objects": [_obj_summary(ws, n) for n in ws.names()]}


def _h_scene_clear(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    n = len(ws)
    for name in ws.names():
        ws.delete(name)
    return {"cleared": n}


def _h_box(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    ext = (float(a["x"]), float(a["y"]), float(a["z"]))
    tm = trimesh.creation.box(extents=ext)
    center = a.get("center")
    if center:
        tm.apply_translation(np.asarray(center, float))
    name = a.get("name") or ws.fresh_name("box")
    _store(ws, name, tm, {"primitive": "box", "extents": ext})
    return {"name": name, **_obj_summary(ws, name)}


def _h_cylinder(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    r = float(a["radius"]); h = float(a["height"])
    sec = int(a.get("sections", 48))
    tm = trimesh.creation.cylinder(radius=r, height=h, sections=sec)
    center = a.get("center")
    if center:
        tm.apply_translation(np.asarray(center, float))
    name = a.get("name") or ws.fresh_name("cyl")
    _store(ws, name, tm, {"primitive": "cylinder", "radius": r, "height": h})
    return {"name": name, **_obj_summary(ws, name)}


def _h_sphere(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    r = float(a["radius"])
    sub = int(a.get("subdivisions", 3))
    tm = trimesh.creation.icosphere(subdivisions=sub, radius=r)
    center = a.get("center")
    if center:
        tm.apply_translation(np.asarray(center, float))
    name = a.get("name") or ws.fresh_name("sph")
    _store(ws, name, tm, {"primitive": "sphere", "radius": r})
    return {"name": name, **_obj_summary(ws, name)}


def _h_load(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    p = Path(a["path"])
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    loaded = trimesh.load(str(p), process=False, force="mesh")
    name = a.get("name") or ws.fresh_name(p.stem + "_")
    _store(ws, name, loaded, {"source": str(p)})
    return {"name": name, **_obj_summary(ws, name)}


def _h_export(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    o = ws.get(a["name"])
    p = Path(a["path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    _to_tm(o).export(str(p))
    return {"name": a["name"], "path": str(p), "bytes": p.stat().st_size}


def _h_translate(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    o = ws.get(a["name"])
    o["vertices"] = o["vertices"] + np.asarray(
        [float(a["dx"]), float(a["dy"]), float(a["dz"])], float)
    return _obj_summary(ws, a["name"])


def _h_rotate(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    o = ws.get(a["name"])
    axis = np.asarray(a.get("axis", [0, 0, 1]), float)
    ang = math.radians(float(a["angle_deg"]))
    center = a.get("center")
    c = np.asarray(center, float) if center else o["vertices"].mean(axis=0)
    M = trimesh.transformations.rotation_matrix(ang, axis, point=c)
    V = o["vertices"]
    hom = np.hstack([V, np.ones((len(V), 1))])
    o["vertices"] = (hom @ M.T)[:, :3]
    return _obj_summary(ws, a["name"])


def _h_scale(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    o = ws.get(a["name"])
    s = a.get("factor")
    if isinstance(s, (list, tuple)):
        sv = np.asarray(s, float)
    else:
        sv = np.asarray([float(s)] * 3, float)
    c = o["vertices"].mean(axis=0)
    o["vertices"] = (o["vertices"] - c) * sv + c
    return _obj_summary(ws, a["name"])


def _h_boolean(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    op = str(a["op"]).lower()
    if op not in {"union", "difference", "intersection"}:
        raise ValueError("op 须为 union/difference/intersection")
    ta = _to_tm(ws.get(a["a"]))
    tb = _to_tm(ws.get(a["b"]))
    if op == "union":
        res = ta.union(tb)
    elif op == "difference":
        res = ta.difference(tb)
    else:
        res = ta.intersection(tb)
    if res is None or len(res.faces) == 0:
        raise RuntimeError(f"布尔 {op} 结果为空 (检查两体是否相交/包含)")
    name = a.get("result") or ws.fresh_name(op[:3] + "_")
    _store(ws, name, res, {"op": op, "a": a["a"], "b": a["b"]})
    if a.get("consume"):
        for k in (a["a"], a["b"]):
            if ws.has(k) and k != name:
                ws.delete(k)
    return {"name": name, "op": op, **_obj_summary(ws, name)}


def _h_duplicate(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    o = ws.get(a["name"])
    name = a.get("new_name") or ws.fresh_name(a["name"] + "_copy")
    ws.put(name, o["vertices"].copy(), o["faces"].copy(), dict(o["meta"]))
    return {"name": name, **_obj_summary(ws, name)}


def _h_delete(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    ws.delete(a["name"])
    return {"deleted": a["name"], "remaining": ws.names()}


def _h_rename(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    ws.rename(a["name"], a["new_name"])
    return {"renamed_to": a["new_name"]}


def _h_measure(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    o = ws.get(a["name"])
    tm = _to_tm(o)
    V = o["vertices"]
    b = np.array([V.min(axis=0), V.max(axis=0)])
    out: Dict[str, Any] = {
        "name": a["name"],
        "bounds_min": [round(x, 4) for x in b[0]],
        "bounds_max": [round(x, 4) for x in b[1]],
        "extents": [round(x, 4) for x in (b[1] - b[0])],
        "centroid": [round(x, 4) for x in V.mean(axis=0)],
        "surface_area": round(float(tm.area), 4),
        "watertight": bool(tm.is_watertight),
        "volume": round(float(abs(tm.volume)), 4) if tm.is_watertight else None,
    }
    other = a.get("to")
    if other:
        ob = ws.get(other)
        # 最小顶点间距 (近似最小间距)
        Va, Vb = V, ob["vertices"]
        if len(Va) * len(Vb) <= 4_000_000:
            d = np.linalg.norm(Va[:, None, :] - Vb[None, :, :], axis=2).min()
        else:
            sa = Va[np.random.default_rng(0).choice(len(Va), min(2000, len(Va)), replace=False)]
            sb = Vb[np.random.default_rng(1).choice(len(Vb), min(2000, len(Vb)), replace=False)]
            d = np.linalg.norm(sa[:, None, :] - sb[None, :, :], axis=2).min()
        out["min_distance_to"] = {"other": other, "distance": round(float(d), 4)}
    return out


def _h_perceive(ws: Workspace, a: Dict[str, Any]) -> Dict[str, Any]:
    o = ws.get(a["name"])
    m = perception.Mesh(o["vertices"], o["faces"], a["name"])
    res = perception.perceive(
        m, resolution=int(a.get("resolution", 192)),
        out_dir=a.get("out_dir"), save_png=bool(a.get("save_png", False)))
    return {
        "name": a["name"],
        "summary": res["summary"],
        "report": res["report"],
        "renders": res["renders"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 注册
# ═══════════════════════════════════════════════════════════════════════════
def register_mesh_tools(reg: ToolRegistry) -> ToolRegistry:
    """把 mesh 后端的全部工具注入给定 registry, 返回该 registry."""
    P = ToolParam

    reg.add("scene.list", "列出工作区内所有几何对象及其尺寸概要.",
            _h_scene_list, [], category="scene")
    reg.add("scene.clear", "清空工作区所有对象.",
            _h_scene_clear, [], category="scene", mutates=True)

    reg.add("mesh.box", "创建长方体图元 (x/y/z 为三边长, 可选 center 中心点).",
            _h_box, [
                P("x", "number", "X 方向边长"),
                P("y", "number", "Y 方向边长"),
                P("z", "number", "Z 方向边长"),
                P("center", "array", "中心坐标 [x,y,z]", False, None),
                P("name", "string", "对象名 (省略自动命名)", False, None),
            ], category="primitive", mutates=True)

    reg.add("mesh.cylinder", "创建圆柱图元 (radius 半径, height 高, 轴向 Z).",
            _h_cylinder, [
                P("radius", "number", "半径"),
                P("height", "number", "高度"),
                P("sections", "integer", "圆周分段数", False, 48),
                P("center", "array", "中心坐标 [x,y,z]", False, None),
                P("name", "string", "对象名", False, None),
            ], category="primitive", mutates=True)

    reg.add("mesh.sphere", "创建球图元 (radius 半径).",
            _h_sphere, [
                P("radius", "number", "半径"),
                P("subdivisions", "integer", "细分级数 (越大越圆)", False, 3),
                P("center", "array", "中心坐标 [x,y,z]", False, None),
                P("name", "string", "对象名", False, None),
            ], category="primitive", mutates=True)

    reg.add("mesh.load", "从文件 (STL/OBJ/PLY/STEP 等 trimesh 支持格式) 载入网格.",
            _h_load, [
                P("path", "string", "文件路径"),
                P("name", "string", "对象名", False, None),
            ], category="io", mutates=True)

    reg.add("mesh.export", "把对象导出为文件 (按扩展名定格式).",
            _h_export, [
                P("name", "string", "对象名"),
                P("path", "string", "输出路径 (含扩展名)"),
            ], category="io")

    reg.add("mesh.translate", "平移对象.",
            _h_translate, [
                P("name", "string", "对象名"),
                P("dx", "number", "X 位移"),
                P("dy", "number", "Y 位移"),
                P("dz", "number", "Z 位移"),
            ], category="transform", mutates=True)

    reg.add("mesh.rotate", "绕轴旋转对象 (角度制).",
            _h_rotate, [
                P("name", "string", "对象名"),
                P("angle_deg", "number", "旋转角度 (度)"),
                P("axis", "array", "旋转轴向量 [x,y,z]", False, [0, 0, 1]),
                P("center", "array", "旋转中心 (省略=质心)", False, None),
            ], category="transform", mutates=True)

    reg.add("mesh.scale", "缩放对象 (factor 为标量或 [sx,sy,sz]).",
            _h_scale, [
                P("name", "string", "对象名"),
                P("factor", "number", "缩放因子 (标量或三元数组)"),
            ], category="transform", mutates=True)

    reg.add("mesh.boolean",
            "布尔运算: op∈{union,difference,intersection}; a-b 两对象; "
            "可选 result 命名、consume 是否消耗输入.",
            _h_boolean, [
                P("op", "string", "union/difference/intersection"),
                P("a", "string", "对象 A"),
                P("b", "string", "对象 B"),
                P("result", "string", "结果对象名", False, None),
                P("consume", "boolean", "完成后删除 A、B", False, False),
            ], category="boolean", mutates=True)

    reg.add("mesh.duplicate", "复制对象.",
            _h_duplicate, [
                P("name", "string", "对象名"),
                P("new_name", "string", "副本名", False, None),
            ], category="object", mutates=True)

    reg.add("mesh.delete", "删除对象.",
            _h_delete, [P("name", "string", "对象名")],
            category="object", mutates=True)

    reg.add("mesh.rename", "重命名对象.",
            _h_rename, [
                P("name", "string", "原名"),
                P("new_name", "string", "新名"),
            ], category="object", mutates=True)

    reg.add("mesh.measure",
            "度量对象: 包围盒/尺寸/质心/面积/体积/水密性; 可选 to 求到另一对象最小间距.",
            _h_measure, [
                P("name", "string", "对象名"),
                P("to", "string", "另一对象名 (求最小间距)", False, None),
            ], category="measure")

    reg.add("mesh.perceive",
            "感知对象: 返回结构化几何报告 + 多视角渲染覆盖率 + 自然语言摘要 "
            "(可 save_png 落盘到 out_dir).",
            _h_perceive, [
                P("name", "string", "对象名"),
                P("resolution", "integer", "渲染分辨率", False, 192),
                P("out_dir", "string", "PNG 输出目录", False, None),
                P("save_png", "boolean", "是否落盘 PNG", False, False),
            ], category="perceive")

    return reg
