# -*- coding: utf-8 -*-
"""fc_dag — ops 特征依赖图 (纯 python, 不依赖 FreeCAD).

把线性 ops 序列升级为显式依赖 DAG:
  - build:      ops → {deps, rdeps, order, roots, leaves, cycles}
  - affected:   改参后需要重算的下游闭包 (含自身)
  - subset:     目标集及其上游闭包的最小 ops 切片 (可独立重放)
  - patch_plan: 补丁 → {changed, affected, replay_ops} 增量重放计划,
                只带受影响链路, 无关旁支不再重算.

用法:
  from fc_dag import FCDag
  g = FCDag.build(ops)
  plan = FCDag.patch_plan(ops, {"PDBox.L": 80})
  FCReverse.replay(plan["replay_ops"], ...)   # 增量重放
"""
from typing import Any, Dict, List

REF_FIELDS = (
    "base", "tool", "shape", "shapes", "source", "profile", "profiles",
    "sections", "spine", "face", "edges", "parts", "tools",
)


def _refs(op: Dict[str, Any]) -> List[str]:
    out = []
    for fld in REF_FIELDS:
        v = op.get(fld)
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            out.extend(x for x in v if isinstance(x, str))
    return out


def build(ops: List[Dict[str, Any]]) -> Dict[str, Any]:
    """构建依赖图. deps[x] = x 直接依赖的 id 集; rdeps[x] = 直接依赖 x 的 id 集."""
    ids = [op["id"] for op in ops if op.get("id")]
    idset = set(ids)
    deps: Dict[str, List[str]] = {i: [] for i in ids}
    rdeps: Dict[str, List[str]] = {i: [] for i in ids}
    for op in ops:
        oid = op.get("id")
        if not oid:
            continue
        for r in _refs(op):
            if r in idset and r != oid and r not in deps[oid]:
                deps[oid].append(r)
                rdeps[r].append(oid)
    # Kahn 拓扑排序 (稳定: 按原 ops 顺序出队)
    indeg = {i: len(deps[i]) for i in ids}
    order: List[str] = []
    ready = [i for i in ids if indeg[i] == 0]
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in rdeps[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
    cycles = sorted(set(ids) - set(order))
    return {
        "deps": deps,
        "rdeps": rdeps,
        "order": order,
        "roots": [i for i in ids if not deps[i]],
        "leaves": [i for i in ids if not rdeps[i]],
        "cycles": cycles,
        "node_count": len(ids),
    }


def _closure(seed: List[str], edges: Dict[str, List[str]]) -> List[str]:
    seen, stack = set(), [s for s in seed if s in edges]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(edges.get(n, []))
    return sorted(seen)


def affected(ops: List[Dict[str, Any]], changed_ids: List[str]) -> List[str]:
    """changed_ids 变更后必须重算的节点 (下游闭包, 含自身)."""
    return _closure(changed_ids, build(ops)["rdeps"])


def subset(ops: List[Dict[str, Any]], targets: List[str]) -> List[Dict[str, Any]]:
    """targets 及其上游闭包的最小 ops 切片, 保持原顺序, 可独立重放."""
    keep = set(_closure(targets, build(ops)["deps"]))
    return [op for op in ops if op.get("id") in keep]


def patch_plan(ops: List[Dict[str, Any]], patch: Dict[str, Any]) -> Dict[str, Any]:
    """补丁 → 增量重放计划.

    changed:    补丁直接命中的 id
    affected:   需要重算的下游闭包
    replay_ops: 打好补丁的最小切片 (affected + 其上游依赖), 直接交给 replay
    skipped:    本次无需重算的节点数
    """
    changed = sorted({k.split(".", 1)[0] for k in patch if "." in k})
    g = build(ops)
    changed = [c for c in changed if c in g["deps"]]
    aff = _closure(changed, g["rdeps"])
    patched = _apply(ops, patch)
    replay_ops = subset(patched, aff) if aff else []
    kept = {op.get("id") for op in replay_ops}
    return {
        "changed": changed,
        "affected": aff,
        "replay_ops": replay_ops,
        "skipped": g["node_count"] - len(kept),
    }


def _apply(ops: List[Dict[str, Any]], patch: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        from fc_reverse import _apply_patch
        return _apply_patch(ops, patch)
    except Exception:
        idx = {op.get("id"): i for i, op in enumerate(ops)}
        out = [dict(o) for o in ops]
        for key, val in patch.items():
            if "." in key:
                oid, pname = key.split(".", 1)
                if oid in idx:
                    out[idx[oid]][pname] = val
        return out


class FCDag:
    """ops 特征依赖图门面."""

    build = staticmethod(build)
    affected = staticmethod(affected)
    subset = staticmethod(subset)
    patch_plan = staticmethod(patch_plan)
