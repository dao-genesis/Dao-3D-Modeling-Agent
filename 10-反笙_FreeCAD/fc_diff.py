# -*- coding: utf-8 -*-
"""fc_diff — 模型级语义 diff/merge (纯 python, 不依赖 FreeCAD).

在 fc_reverse 的 ops 表示之上做语义比较:
  - 对象级: 新增/删除/变更 (按 op id 对齐)
  - 参数级: 嵌套 dict/list 逐字段, 数值容差比较
  - 草图级: geometry 按 (type, 序号) 对齐, constraints 按规范键对齐
  - 三方 merge: base/ours/theirs 非重叠变更自动合并, 重叠列为 conflicts

用法:
  from fc_diff import FCDiff
  d = FCDiff.diff(ops_a, ops_b)              # 或 FCDiff.diff_files(a.FCStd, b.FCStd)
  m = FCDiff.merge3(base_ops, ours, theirs)  # -> {"ops": ..., "conflicts": [...]}
"""
from typing import Any, Dict, List, Tuple

TOL = 1e-9


def _num_eq(a: float, b: float) -> bool:
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def _eq(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        return _num_eq(float(a), float(b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    return a == b


def _flat_changes(a: Any, b: Any, path: str = "") -> List[Dict[str, Any]]:
    """递归收集 a→b 的字段级变更, 返回 [{path, before, after}]."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else str(k)
            if k not in a:
                out.append({"path": p, "before": None, "after": b[k]})
            elif k not in b:
                out.append({"path": p, "before": a[k], "after": None})
            else:
                out.extend(_flat_changes(a[k], b[k], p))
        return out
    if isinstance(a, list) and isinstance(b, list):
        out = []
        n = max(len(a), len(b))
        for i in range(n):
            p = f"{path}[{i}]"
            if i >= len(a):
                out.append({"path": p, "before": None, "after": b[i]})
            elif i >= len(b):
                out.append({"path": p, "before": a[i], "after": None})
            else:
                out.extend(_flat_changes(a[i], b[i], p))
        return out
    if _eq(a, b):
        return []
    return [{"path": path, "before": a, "after": b}]


def _op_key(op: Dict[str, Any]) -> str:
    return str(op.get("id") or op.get("name") or "")


def _index(ops: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {_op_key(o): o for o in ops if _op_key(o)}


def diff(ops_a: List[Dict[str, Any]], ops_b: List[Dict[str, Any]]) -> Dict[str, Any]:
    ia, ib = _index(ops_a), _index(ops_b)
    added = sorted(set(ib) - set(ia))
    removed = sorted(set(ia) - set(ib))
    changed = []
    for k in sorted(set(ia) & set(ib)):
        ch = _flat_changes(ia[k], ib[k])
        if ch:
            entry: Dict[str, Any] = {"id": k, "op": ib[k].get("op"), "changes": ch}
            if ia[k].get("op") == "sketch" and ib[k].get("op") == "sketch":
                entry["sketch"] = _sketch_diff(ia[k], ib[k])
            changed.append(entry)
    return {
        "added": [{"id": k, "op": ib[k].get("op")} for k in added],
        "removed": [{"id": k, "op": ia[k].get("op")} for k in removed],
        "changed": changed,
        "identical": not added and not removed and not changed,
        "summary": {"added": len(added), "removed": len(removed), "changed": len(changed)},
    }


def _con_key(c: Dict[str, Any]) -> Tuple:
    return (c.get("type"), c.get("first"), c.get("first_pos"),
            c.get("second"), c.get("second_pos"), c.get("third"), c.get("third_pos"))


def _sketch_diff(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """草图内: geometry 按 (type, 同类型内序号) 对齐, constraints 按规范键集合对齐."""
    def geo_keys(sk):
        cnt: Dict[str, int] = {}
        out = []
        for g in sk.get("geometry", []):
            t = g.get("type", "?")
            cnt[t] = cnt.get(t, 0) + 1
            out.append((f"{t}#{cnt[t]}", g))
        return dict(out)

    ga, gb = geo_keys(a), geo_keys(b)
    geo = {
        "added": sorted(set(gb) - set(ga)),
        "removed": sorted(set(ga) - set(gb)),
        "changed": [
            {"key": k, "changes": _flat_changes(ga[k], gb[k])}
            for k in sorted(set(ga) & set(gb))
            if not _eq(ga[k], gb[k])
        ],
    }
    ca = {_con_key(c): c for c in a.get("constraints", [])}
    cb = {_con_key(c): c for c in b.get("constraints", [])}
    cons = {
        "added": [cb[k] for k in cb if k not in ca],
        "removed": [ca[k] for k in ca if k not in cb],
        "changed": [
            {"key": list(k), "changes": _flat_changes(ca[k], cb[k])}
            for k in ca if k in cb and not _eq(ca[k], cb[k])
        ],
    }
    return {"geometry": geo, "constraints": cons}


def merge3(base: List[Dict[str, Any]], ours: List[Dict[str, Any]],
           theirs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """三方语义合并: 对象级取非重叠变更; 双方都改同一对象且不一致时列为冲突."""
    ib, io, it = _index(base), _index(ours), _index(theirs)
    keys = sorted(set(ib) | set(io) | set(it))
    merged: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    order = {k: i for i, k in enumerate(
        [_op_key(o) for o in base] + [_op_key(o) for o in ours] + [_op_key(o) for o in theirs])}
    for k in sorted(keys, key=lambda x: order.get(x, 1 << 30)):
        b, o, t = ib.get(k), io.get(k), it.get(k)
        o_ch = not _eq(b, o)
        t_ch = not _eq(b, t)
        if not o_ch and not t_ch:
            pick = b
        elif o_ch and not t_ch:
            pick = o
        elif t_ch and not o_ch:
            pick = t
        elif _eq(o, t):
            pick = o
        else:
            conflicts.append({"id": k, "base": b, "ours": o, "theirs": t,
                              "ours_changes": _flat_changes(b, o),
                              "theirs_changes": _flat_changes(b, t)})
            pick = o  # 冲突默认保留 ours, 由调用方按 conflicts 决断
        if pick is not None:
            merged.append(pick)
    return {"ops": merged, "conflicts": conflicts, "clean": not conflicts}


class FCDiff:
    """模型级语义 diff/merge 门面."""

    diff = staticmethod(diff)
    merge3 = staticmethod(merge3)

    @staticmethod
    def diff_files(path_a: str, path_b: str) -> Dict[str, Any]:
        from fc_reverse import FCReverse
        ra, rb = FCReverse.reverse(path_a), FCReverse.reverse(path_b)
        out = diff(ra.get("ops", []), rb.get("ops", []))
        out["source_a"], out["source_b"] = path_a, path_b
        return out


def main() -> int:
    import json
    import sys
    if len(sys.argv) != 3:
        print("用法: python fc_diff.py A.FCStd B.FCStd", file=sys.stderr)
        return 2
    print(json.dumps(FCDiff.diff_files(sys.argv[1], sys.argv[2]),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
