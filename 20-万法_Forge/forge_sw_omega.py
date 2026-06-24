#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
forge_sw_omega.py — 万法 · SW-OMEGA (L11) · CLI 薄壁
═══════════════════════════════════════════════════════════════════════

本文件是 forge_v3 对 `dao_sw_live` (L11 活体万象) 的命令行包装.
与 forge_v3.py 里已有的 SW-ORIGIN / SW-LIVE / SW-DEEP / SW-BREAK /
SW-ACTIVATE / SW-QUARK 并列, 拓成第 7 组 SW-OMEGA.

命令集 (11 条):
    sw_live_status                        当前 L11 活体状态
    sw_new_part [--template T] [--save-as P]
                                          新建零件 (可选保存)
    sw_new_assembly [--template T] [--save-as P]
    sw_new_drawing [--template T]
    sw_cmd <id_or_name> [--title T]       触发 SW 内部命令 (swCommands_e)
    sw_list_cmds [--json]                 列出常用 SW 命令枚举
    sw_macro <path.swp> [--module M] [--proc P]
                                          跑 VBA 宏
    sw_build_demo [--out D] [--fmt step,stl]
                                          活体 demo: 建一个垫片 + 导出多格式
    sw_prop_set <name> <value> [--config C] [--type TXT|NUM|YN]
    sw_prop_get <name> [--config C]
    sw_prop_all [--config C]
    sw_eqn <equation>                     追加方程 (e.g. '\"L\"=100')
    sw_material <name> [--db DB] [--config C]
    sw_live_snap <out.png> [--view iso]   L11 截图 (复用桥)

设计原则
    · 极薄: 只转参数 + JSON 输出, 不含业务逻辑
    · 幂等: ensure_live 自动
    · 静默失败: 输出非零 exit code + JSON err, 不抛异常
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 路径引导 (五层 sys.path) ─────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_DAO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "_paths.py").is_file()),
    _HERE.parent,
)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
try:
    import _paths as _dao_paths  # noqa: F401
except Exception:  # noqa: BLE001
    _dao_paths = None


def _dump(d: Dict[str, Any]) -> None:
    print(json.dumps(d, ensure_ascii=False, indent=2, default=str))


def _parse_flag(args: List[str], key: str,
                default: Optional[str] = None) -> Optional[str]:
    """从 argv 提取 --key VAL."""
    for i, a in enumerate(args):
        if a == key and i + 1 < len(args):
            return args[i + 1]
    return default


def _parse_bool(args: List[str], key: str) -> bool:
    return key in args


# ── 状态 ────────────────────────────────────────────────────────────
def _cmd_sw_live_status(args: List[str]) -> int:
    from dao_sw_live import SWLive
    live = SWLive()
    try:
        live.ensure_live(visible=True, dismiss_welcome=True)
    except Exception as e:  # noqa: BLE001
        _dump({"ok": False, "err": f"{type(e).__name__}: {e}"})
        return 1
    _dump(live.status())
    return 0


# ── 新建文档 ───────────────────────────────────────────────────────
def _cmd_sw_new(args: List[str], kind: str) -> int:
    from dao_sw_live import SWLive
    tpl = _parse_flag(args, "--template")
    save_as = _parse_flag(args, "--save-as")
    live = SWLive()
    try:
        live.ensure_live(visible=True, dismiss_welcome=True)
        if kind == "part":
            d = live.new_part(template=tpl)
        elif kind == "assembly":
            d = live.new_assembly(template=tpl)
        elif kind == "drawing":
            d = live.new_drawing(template=tpl)
        else:
            _dump({"ok": False, "err": f"unknown kind: {kind}"})
            return 1
        out: Dict[str, Any] = {
            "ok": True,
            "kind": kind,
            "title": d.title(),
            "template": tpl or "<default>",
        }
        if save_as:
            r = d.save_as(save_as)
            out["save_as"] = r
        _dump(out)
        return 0 if not save_as or out["save_as"].get("ok") else 1
    except Exception as e:
        _dump({"ok": False, "err": f"{type(e).__name__}: {e}"})
        return 1


# ── RunCommand ─────────────────────────────────────────────────────
def _cmd_sw_cmd(args: List[str]) -> int:
    if not args:
        print("Usage: sw_cmd <id_or_name> [--title T]")
        return 1
    from dao_sw_live import SWLive
    target = args[0]
    title = _parse_flag(args, "--title", "") or ""
    try:
        cid: Any = int(target)
    except ValueError:
        cid = target
    live = SWLive()
    try:
        live.ensure_live(visible=True, dismiss_welcome=True)
        _dump(live.cmd.run(cid, title=title))
        return 0
    except Exception as e:
        _dump({"ok": False, "err": f"{type(e).__name__}: {e}"})
        return 1


def _cmd_sw_list_cmds(args: List[str]) -> int:
    from dao_sw_live import SW_CMD
    use_json = _parse_bool(args, "--json")
    if use_json:
        _dump(SW_CMD.BY_NAME)
    else:
        print("─── SW 常用内部命令 (swCommands_e 子集) ───")
        width = max(len(k) for k in SW_CMD.BY_NAME)
        for name in sorted(SW_CMD.BY_NAME):
            cid = SW_CMD.BY_NAME[name]
            print(f"  {name.ljust(width)}  {cid}")
    return 0


# ── VBA 宏 ─────────────────────────────────────────────────────────
def _cmd_sw_macro(args: List[str]) -> int:
    if not args:
        print("Usage: sw_macro <path.swp> [--module M] [--proc P]")
        return 1
    from dao_sw_live import SWLive
    path = args[0]
    module = _parse_flag(args, "--module", "Main") or "Main"
    proc = _parse_flag(args, "--proc", "main") or "main"
    live = SWLive()
    try:
        live.ensure_live(visible=True, dismiss_welcome=True)
        _dump(live.macro.run_file(path, module=module, proc=proc))
        return 0
    except Exception as e:
        _dump({"ok": False, "err": f"{type(e).__name__}: {e}"})
        return 1


# ── 自定义属性 ─────────────────────────────────────────────────────
_PROP_TYPE_MAP = {"TXT": 30, "TEXT": 30, "STR": 30,
                  "NUM": 3,  "NUMBER": 3,  "REAL": 3,
                  "YN": 11,  "BOOL": 11,   "YES/NO": 11}


def _cmd_sw_prop_set(args: List[str]) -> int:
    if len(args) < 2:
        print("Usage: sw_prop_set <name> <value> [--config C] [--type TXT|NUM|YN]")
        return 1
    from dao_sw_live import SWLive
    name, value = args[0], args[1]
    config = _parse_flag(args, "--config")
    tp = (_parse_flag(args, "--type") or "TXT").upper()
    code = _PROP_TYPE_MAP.get(tp, 30)
    live = SWLive()
    try:
        live.ensure_live(visible=True, dismiss_welcome=True)
        d = live.active()
        if d is None:
            _dump({"ok": False, "err": "no active document"})
            return 1
        _dump(d.props.set(name, value, config=config, prop_type=code))
        return 0
    except Exception as e:
        _dump({"ok": False, "err": f"{type(e).__name__}: {e}"})
        return 1


def _cmd_sw_prop_get(args: List[str]) -> int:
    if not args:
        print("Usage: sw_prop_get <name> [--config C]")
        return 1
    from dao_sw_live import SWLive
    name = args[0]
    config = _parse_flag(args, "--config")
    live = SWLive()
    try:
        live.ensure_live(visible=True, dismiss_welcome=True)
        d = live.active()
        if d is None:
            _dump({"ok": False, "err": "no active document"})
            return 1
        _dump(d.props.get(name, config=config))
        return 0
    except Exception as e:
        _dump({"ok": False, "err": f"{type(e).__name__}: {e}"})
        return 1


def _cmd_sw_prop_all(args: List[str]) -> int:
    from dao_sw_live import SWLive
    config = _parse_flag(args, "--config")
    live = SWLive()
    try:
        live.ensure_live(visible=True, dismiss_welcome=True)
        d = live.active()
        if d is None:
            _dump({"ok": False, "err": "no active document"})
            return 1
        _dump(d.props.all(config=config))
        return 0
    except Exception as e:
        _dump({"ok": False, "err": f"{type(e).__name__}: {e}"})
        return 1


# ── 方程 ────────────────────────────────────────────────────────────
def _cmd_sw_eqn(args: List[str]) -> int:
    if not args:
        print("Usage: sw_eqn <equation>  (e.g.  '\"L\"=100' )")
        return 1
    from dao_sw_live import SWLive
    eq = args[0]
    live = SWLive()
    try:
        live.ensure_live(visible=True, dismiss_welcome=True)
        d = live.active()
        if d is None:
            _dump({"ok": False, "err": "no active document"})
            return 1
        _dump(d.eqn.add(eq))
        return 0
    except Exception as e:
        _dump({"ok": False, "err": f"{type(e).__name__}: {e}"})
        return 1


# ── 材质 ────────────────────────────────────────────────────────────
def _cmd_sw_material(args: List[str]) -> int:
    if not args:
        print("Usage: sw_material <name> [--db DB] [--config C]")
        return 1
    from dao_sw_live import SWLive
    name = args[0]
    db = _parse_flag(args, "--db")
    config = _parse_flag(args, "--config", "") or ""
    live = SWLive()
    try:
        live.ensure_live(visible=True, dismiss_welcome=True)
        d = live.active()
        if d is None or not d.is_part:
            _dump({"ok": False, "err": "no active part document"})
            return 1
        _dump(d.material.set_material(name, database=db, config=config))
        return 0
    except Exception as e:
        _dump({"ok": False, "err": f"{type(e).__name__}: {e}"})
        return 1


# ── 截图 ────────────────────────────────────────────────────────────
def _cmd_sw_live_snap(args: List[str]) -> int:
    if not args:
        print("Usage: sw_live_snap <out.png> [--view iso]")
        return 1
    from dao_sw_live import SWLive
    out = args[0]
    view = _parse_flag(args, "--view")
    live = SWLive()
    try:
        live.ensure_live(visible=True, dismiss_welcome=True)
        _dump(live.snap(out, view=view))
        return 0
    except Exception as e:
        _dump({"ok": False, "err": f"{type(e).__name__}: {e}"})
        return 1


# ── Demo: 活体建一个垫片 + 截图 + 导出多格式 ──────────────────────
def _cmd_sw_build_demo(args: List[str]) -> int:
    """活体 demo: 新建零件 → 圆环垫片 → iso 截图 → STEP + STL.

    参数: [--out D] [--fmt step,stl]
    目的: 作为 L11 真机 smoke test.
    """
    import time
    from dao_sw_live import SWLive, SW_VIEW
    out_dir = Path(_parse_flag(args, "--out") or
                    (_HERE.parent / "30-验证_Verify" / "_sw_live_demo"))
    out_dir.mkdir(parents=True, exist_ok=True)
    fmts = [s.strip() for s in (_parse_flag(args, "--fmt") or "step,stl").split(",") if s.strip()]

    stem = f"washer_demo_{int(time.time())}"
    results: Dict[str, Any] = {"stem": stem, "out_dir": str(out_dir),
                                "steps": []}
    live = SWLive()
    try:
        r0 = live.ensure_live(visible=True, dismiss_welcome=True)
        results["steps"].append({"step": "ensure_live", **r0})

        part = live.new_part()
        results["steps"].append({"step": "new_part",
                                 "title": part.title()})

        r1 = part.sketch.start_front()
        results["steps"].append({"step": "sketch.start_front", **r1})

        # 外圆 R=30, 内圆 R=15  —— 圆环
        r2 = part.sketch.circle(0, 0, 30)
        r3 = part.sketch.circle(0, 0, 15)
        results["steps"].append({"step": "sketch.circle_outer", **r2})
        results["steps"].append({"step": "sketch.circle_inner", **r3})

        r4 = part.sketch.stop()
        results["steps"].append({"step": "sketch.stop", **r4})

        r5 = part.feature.extrude(depth=5)
        results["steps"].append({"step": "feature.extrude(5mm)", **r5})

        # rebuild 确保几何刷新 (mass/bbox 依赖)
        rb = part.rebuild(force=True)
        results["steps"].append({"step": "rebuild", **rb})

        # 材质
        rm = part.material.set_material("普通碳钢")
        results["steps"].append({"step": "material", **rm})

        # 属性
        rp = part.props.set("Designer", "ModelForge · L11 Omega")
        results["steps"].append({"step": "props.Designer", **rp})

        # iso 视图 + 截图
        live.view(SW_VIEW.ISOMETRIC)
        iso_png = out_dir / f"{stem}_iso.png"
        rs = live.snap(iso_png, view="iso")
        results["steps"].append({"step": "snap_iso", **rs})

        # 保存 .sldprt
        sldprt = out_dir / f"{stem}.sldprt"
        r_save = part.save_as(sldprt)
        results["steps"].append({"step": "save_as_sldprt", **r_save})

        # 多格式导出
        for fmt in fmts:
            dst = out_dir / f"{stem}.{fmt}"
            r_exp = part.export(dst, fmt=fmt)
            results["steps"].append({"step": f"export_{fmt}", **r_exp})

        # 质量属性快照
        try:
            mp = part.mass_properties()
            results["mass_properties"] = mp
        except Exception as e:
            results["mass_err"] = f"{type(e).__name__}: {e}"

        results["ok"] = True
        _dump(results)
        return 0
    except Exception as e:
        results["ok"] = False
        results["err"] = f"{type(e).__name__}: {e}"
        _dump(results)
        return 1


# ════════════════════════════════════════════════════════════════════
# dispatch
# ════════════════════════════════════════════════════════════════════
_DISPATCH = {
    "sw_live_status":  _cmd_sw_live_status,
    "sw_new_part":     lambda a: _cmd_sw_new(a, "part"),
    "sw_new_assembly": lambda a: _cmd_sw_new(a, "assembly"),
    "sw_new_drawing":  lambda a: _cmd_sw_new(a, "drawing"),
    "sw_cmd":          _cmd_sw_cmd,
    "sw_list_cmds":    _cmd_sw_list_cmds,
    "sw_macro":        _cmd_sw_macro,
    "sw_prop_set":     _cmd_sw_prop_set,
    "sw_prop_get":     _cmd_sw_prop_get,
    "sw_prop_all":     _cmd_sw_prop_all,
    "sw_eqn":          _cmd_sw_eqn,
    "sw_material":     _cmd_sw_material,
    "sw_live_snap":    _cmd_sw_live_snap,
    "sw_build_demo":   _cmd_sw_build_demo,
}


def dispatch(cmd: str, args: List[str]) -> Optional[int]:
    """forge_v3 可调入口. 未知命令返回 None (让 forge_v3 继续派发)."""
    key = cmd.replace("-", "_").lower()
    fn = _DISPATCH.get(key)
    if fn is None:
        return None
    return fn(args)


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        print("已注册命令:")
        for k in sorted(_DISPATCH):
            print(f"  {k}")
        return 0
    rc = dispatch(args[0], args[1:])
    if rc is None:
        print(f"Unknown command: {args[0]}")
        return 1
    return int(rc)


if __name__ == "__main__":
    sys.exit(main())
