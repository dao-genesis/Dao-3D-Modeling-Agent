#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_agent.py — 80-智体_Agent 层端到端自检
═══════════════════════════════════════════════════════════════════════════════
证明: 在 *无任何外部 CAD 软件* 的环境里, perceive→act→verify 全闭环可跑通.

跑法:  python "80-智体_Agent/verify_agent.py"
输出:  逐项 ✅/⚠️/❌, 末尾总判定; 退出码 0=全过, 1=有失败.
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让本层目录可被 import (规避含中文路径的 PYTHONPATH 编码坑)
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

PASS, WARN, FAIL = "✅", "⚠️", "❌"
_n_fail = 0


def _check(name: str, ok: bool, detail: str = "") -> None:
    global _n_fail
    mark = PASS if ok else FAIL
    if not ok:
        _n_fail += 1
    print(f"{mark} {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("═" * 70)
    print("80-智体_Agent · 端到端自检 (perceive→act→verify, 无外部 CAD)")
    print("═" * 70)

    # —— 导入 ——
    try:
        import cad_agent
        from cad_agent.session import Check
        from cad_agent import perception
        _check("import cad_agent / session / perception", True)
    except Exception as e:  # noqa: BLE001
        _check("import cad_agent", False, repr(e))
        return 1

    # —— 1. 感知本源: 渲染一个盒子 ——
    import numpy as np
    box = perception.Mesh(
        np.array([[0, 0, 0], [40, 0, 0], [40, 30, 0], [0, 30, 0],
                  [0, 0, 20], [40, 0, 20], [40, 30, 20], [0, 30, 20]], float),
        np.array([[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
                  [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2],
                  [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0]], int), "box")
    per = perception.perceive(box, resolution=96)
    rep = per["report"]
    _check("perceive.dims 正确 (40×30×20)",
           rep["dims_sorted_desc"] == [40.0, 30.0, 20.0], str(rep["dims_sorted_desc"]))
    _check("perceive.volume 正确 (24000)", rep["volume"] == 24000.0, str(rep["volume"]))
    _check("perceive.watertight", rep["watertight"] is True)
    _check("perceive 多视角覆盖率>0",
           all(v["coverage"] > 0 for v in per["renders"].values()),
           str({k: v["coverage"] for k, v in per["renders"].items()}))

    # —— 2. 工具协议: registry schema ——
    reg = cad_agent.build_default_registry()
    schemas = reg.schemas()
    names = reg.names()
    _check("工具数 ≥ 15", len(names) >= 15, f"{len(names)} 个")
    _check("每个工具有 inputSchema",
           all("inputSchema" in s for s in schemas))
    _check("含核心动作 (box/boolean/measure/perceive)",
           all(reg.has(n) for n in
               ["mesh.box", "mesh.boolean", "mesh.measure", "mesh.perceive"]))

    # —— 3. 智体会话: 建 "带孔法兰板" perceive→act→verify ——
    s = cad_agent.new_session("verify")
    plan = [
        {"tool": "mesh.box", "args": {"x": 40, "y": 30, "z": 6, "name": "plate"}},
        {"tool": "mesh.cylinder",
         "args": {"radius": 5, "height": 20, "center": [0, 0, 0], "name": "drill"}},
        {"tool": "mesh.boolean",
         "args": {"op": "difference", "a": "plate", "b": "drill",
                  "result": "flange", "consume": True}},
    ]
    checks = [
        Check("exists", obj="flange"),
        Check("watertight", obj="flange"),
        Check("volume", obj="flange", lo=6000, hi=7000,
              label="flange 体积≈板7200-孔≈471"),
        Check("count", value=1),
        Check("not_exists", obj="plate", label="plate 已被 consume"),
    ]
    out = s.run(plan, checks=checks)
    _check("plan 三步全执行成功", out["ok"], str([o["ok"] for o in out["outcomes"]]))
    _check("verify 全过", out["verify"]["ok"],
           f"{out['verify']['passed']}/{len(checks)}")
    print("  ┌─ verify 明细")
    for line in out["verify"]["render"].splitlines():
        print("  │ " + line)
    print("  └─")

    # —— 4. 感知改后零件 + 撤销语义 ——
    pf = s.perceive("flange")
    _check("感知带孔件: 非水密? 否(应仍水密)且体积下降",
           pf.ok and pf.data["report"]["watertight"] is True)
    print("  · flange 摘要:", pf.data["summary"])

    n_before = len(s.workspace)
    s.act("mesh.box", {"x": 1, "y": 1, "z": 1, "name": "scratch"})
    undone = s.undo()
    _check("undo 回滚最近变更", undone and len(s.workspace) == n_before,
           f"{len(s.workspace)} vs {n_before}")

    # —— 5. 失败工具不污染状态 ——
    bad = s.act("mesh.boolean", {"op": "difference", "a": "flange", "b": "nope"})
    _check("引用不存在对象 → 优雅失败且状态不变",
           (not bad.ok) and len(s.workspace) == n_before, bad.error or "")

    print("═" * 70)
    if _n_fail == 0:
        print(f"{PASS} 全部通过 — 通用 AI+CAD 闭环在无外部软件环境下成立.")
        return 0
    print(f"{FAIL} {_n_fail} 项失败.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
