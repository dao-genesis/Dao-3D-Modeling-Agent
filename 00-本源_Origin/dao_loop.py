#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_loop.py · 通用闭环控制本源 · 万法之资归一
══════════════════════════════════════════════════════════════════════════════
反者道之动 — 不从一次通过出发, 从 "失败→诊断→自愈→再验" 的螺旋出发.
弱者道之用 — 零外部依赖 (只用 stdlib).
无为而无不为 — 产物已就绪则跳过 (无为), 警告出现则自动修复 (为而无不为), 连续同态或零警告收敛退出 (自然止).

循环形态:
       ┌───────────────── converge ──────────────────┐
       ▼                                              │
  probe  → build  → verify → diagnose → heal → reverify
    │        │       │                       │
    │        │       └── trajectory append ──┘
    │        └── skip if products exist
    └── environment snapshot

核心抽象:
  Environment  — 环境探针的结果 (操作系统/依赖/服务状态)
  BuildStage   — 一个构建阶段 (脚本 + 期望产物)
  HealHandler  — 针对某类 warning tag 的自愈回调
  LoopController — 编排 probe/build/verify/diagnose/heal/reverify

使用范式:
  loop = LoopController(
      working_dir = HERE,
      verifier_cmd = [sys.executable, "my_verify.py"],
      build_stages = [...],
      heal_registry = [...],
      max_iterations = 5,
  )
  result = loop.run()
  result.dump_trajectory(HERE / "_LOOP_TRAJECTORY.json")
  result.dump_markdown(HERE / "_LOOP_REPORT.md")
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Pattern, Sequence, Tuple, Union

__version__ = "1.0.0"
__all__ = [
    "Environment", "BuildStage", "HealHandler", "HealResult",
    "LoopIteration", "LoopResult", "LoopController",
    "run_subproc",
]

PathLike = Union[str, Path]


# ══════════════════════════════════════════════════════════════════════════════
# 一、环境探针 · 外部依赖的状态快照
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Environment:
    python: str = ""
    platform: str = ""
    cwd: str = ""
    modules_present: Dict[str, bool] = field(default_factory=dict)
    executables: Dict[str, Optional[str]] = field(default_factory=dict)
    services: Dict[str, bool] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def snapshot(*,
                 modules: Sequence[str] = (),
                 executables: Dict[str, Sequence[PathLike]] = {},
                 services: Dict[str, Callable[[], bool]] = {},
                 cwd: Optional[PathLike] = None,
                 extra_probes: Dict[str, Callable[[], Any]] = {}) -> "Environment":
        env = Environment(
            python=sys.version.split()[0],
            platform=sys.platform,
            cwd=str(cwd or Path.cwd()),
        )
        # Modules
        for mod in modules:
            env.modules_present[mod] = importlib.util.find_spec(mod) is not None
        # Executables: first existing candidate wins
        for name, candidates in executables.items():
            found: Optional[str] = None
            for c in candidates:
                p = Path(c)
                if p.exists():
                    found = str(p); break
            env.executables[name] = found
        # Services: each callable returns bool
        for name, probe in services.items():
            try:
                env.services[name] = bool(probe())
            except Exception:
                env.services[name] = False
        # Extra
        for name, probe in extra_probes.items():
            try:
                env.extra[name] = probe()
            except Exception as e:
                env.extra[name] = {"error": str(e)[:200]}
        return env

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════════════
# 二、构建阶段 · 脚本 + 期望产物 + 可选前置条件
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BuildStage:
    """
    一个构建阶段:
      · script:   执行脚本路径 (相对 working_dir)
      · desc:     人类可读描述
      · expected: 期望产物 (若全部存在则跳过)
      · timeout:  秒
      · cwd:      执行目录 (默认 working_dir)
      · require:  可选前置回调, 返回 True 才执行
      · args:     附加命令行参数
    """
    script: str
    desc: str
    expected: Sequence[PathLike] = field(default_factory=list)
    timeout: int = 600
    cwd: Optional[PathLike] = None
    require: Optional[Callable[[Environment], bool]] = None
    args: Sequence[str] = field(default_factory=list)

    def expected_missing(self) -> List[Path]:
        return [Path(p) for p in self.expected if not Path(p).exists()]

    def needs_build(self) -> bool:
        return any(not Path(p).exists() for p in self.expected)


# ══════════════════════════════════════════════════════════════════════════════
# 三、子进程执行 · 统一 UTF-8 解码
# ══════════════════════════════════════════════════════════════════════════════

def run_subproc(cmd: Sequence[str], cwd: Optional[PathLike] = None,
                timeout: int = 300, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """执行命令, 捕获 stdout/stderr 为 UTF-8 文本. 返回统一字典."""
    t0 = time.time()
    try:
        r = subprocess.run(
            list(cmd),
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            env=env,
        )
        return {
            "cmd": list(cmd),
            "rc": r.returncode,
            "elapsed": round(time.time() - t0, 2),
            "stdout": r.stdout, "stderr": r.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"cmd": list(cmd), "rc": -1, "elapsed": timeout,
                "stdout": "", "stderr": f"TIMEOUT after {timeout}s"}
    except Exception as e:
        return {"cmd": list(cmd), "rc": -2,
                "elapsed": round(time.time() - t0, 2),
                "stdout": "", "stderr": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# 四、自愈 Handler · pattern → action
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class HealResult:
    tag: str
    action: str
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


HealFn = Callable[[str, str, Environment, Dict[str, Any]], HealResult]


@dataclass
class HealHandler:
    """Warning tag pattern → heal function."""
    pattern: str                 # regex (re.match)
    handler: HealFn
    once_per_iter: bool = True   # 一轮内同一 handler 只跑一次

    _rx: Optional[Pattern[str]] = field(default=None, repr=False, init=False)

    def matches(self, tag: str) -> bool:
        if self._rx is None:
            self._rx = re.compile(self.pattern)
        return bool(self._rx.match(tag))


# ══════════════════════════════════════════════════════════════════════════════
# 五、迭代与结果
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LoopIteration:
    iter: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    build_records: List[Dict[str, Any]] = field(default_factory=list)
    verify_summary: Dict[str, Any] = field(default_factory=dict)
    heal_records:   List[Dict[str, Any]] = field(default_factory=list)

    def score(self) -> int:
        return int(self.verify_summary.get("score", 0))

    def n_warn(self) -> int:
        return int(self.verify_summary.get("n_warn", 0))

    def n_fail(self) -> int:
        return int(self.verify_summary.get("n_fail", 0))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LoopResult:
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    environment: Dict[str, Any] = field(default_factory=dict)
    iterations: List[LoopIteration] = field(default_factory=list)
    converged: bool = False
    convergence_reason: str = ""
    final_summary: Dict[str, Any] = field(default_factory=dict)

    def final_iteration(self) -> Optional[LoopIteration]:
        return self.iterations[-1] if self.iterations else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "environment": self.environment,
            "iterations": [it.to_dict() for it in self.iterations],
            "converged": self.converged,
            "convergence_reason": self.convergence_reason,
            "final_summary": self.final_summary,
        }

    def dump_trajectory(self, path: PathLike) -> Path:
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return p

    def dump_markdown(self, path: PathLike, *, title: str = "dao_loop 闭环报告") -> Path:
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# {title}", "",
                 f"> 起始: {self.started_at}",
                 f"> 迭代: {len(self.iterations)} 轮",
                 f"> 收敛: {'✅ 是' if self.converged else '❌ 否'} "
                 f"({self.convergence_reason})",
                 "", "---", ""]
        lines.append("## 环境")
        lines.append("")
        lines.append(f"- Python: {self.environment.get('python')}")
        lines.append(f"- Platform: {self.environment.get('platform')}")
        if self.environment.get("executables"):
            lines.append("- 可执行:")
            for name, path in self.environment["executables"].items():
                lines.append(f"  - `{name}`: {path or '未找到'}")
        if self.environment.get("services"):
            lines.append("- 服务:")
            for name, up in self.environment["services"].items():
                lines.append(f"  - `{name}`: {'✅ UP' if up else '❌ DOWN'}")
        lines.append("")
        for it in self.iterations:
            vs = it.verify_summary
            lines.append(f"## 轮 {it.iter} · {it.timestamp}")
            lines.append("")
            lines.append(f"- 构建: {sum(1 for b in it.build_records if b.get('status') == 'OK')}/"
                         f"{len(it.build_records)}")
            lines.append(f"- 验证: ✅{vs.get('n_pass', 0)} ⚠️{vs.get('n_warn', 0)} "
                         f"❌{vs.get('n_fail', 0)} · 评分 {vs.get('score', 0)}/100")
            if it.heal_records:
                lines.append("- 自愈行动:")
                for hr in it.heal_records:
                    lines.append(f"  - `{hr.get('tag')}` → {hr.get('action')}")
            lines.append("")
        lines += ["---", "", "*道法自然 · 万法归宗 · 锚定本源 · 闭环自循环*"]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p


# ══════════════════════════════════════════════════════════════════════════════
# 六、主控制器
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LoopController:
    """
    通用闭环控制器.

    必填:
      · working_dir:   工作目录
      · verifier_cmd:  验证命令 (在 working_dir 中运行, 统计 ✅/⚠️/❌)

    可选:
      · build_stages:  构建阶段列表
      · heal_registry: 自愈处理器列表
      · env_spec:      传给 Environment.snapshot 的配置
      · max_iterations: 最大迭代次数
      · initial_build_force: 首轮强制重建
    """
    working_dir: PathLike
    verifier_cmd: Sequence[str]
    build_stages: Sequence[BuildStage] = field(default_factory=list)
    heal_registry: Sequence[HealHandler] = field(default_factory=list)
    env_spec: Dict[str, Any] = field(default_factory=dict)
    max_iterations: int = 5
    initial_build_force: bool = False
    verifier_timeout: int = 300
    verbose: bool = True

    def _log(self, level: str, msg: str) -> None:
        if not self.verbose:
            return
        icon = {"I": "  ", "OK": "✅", "WARN": "⚠️ ", "ERR": "❌",
                "STEP": "▶ ", "HEAL": "🔧", "CONV": "🌀"}.get(level, "  ")
        print(f"  {icon} {msg}", flush=True)

    # ── Build phase ───────────────────────────────────────────────────────
    def run_build(self, env: Environment, *, force: bool = False) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        wd = Path(self.working_dir)
        for stage in self.build_stages:
            script_path = wd / stage.script
            if not script_path.exists():
                records.append({"script": stage.script, "desc": stage.desc,
                                "status": "SCRIPT_MISSING"})
                self._log("WARN", f"构建脚本不存在: {stage.script}")
                continue
            if stage.require is not None:
                try:
                    if not stage.require(env):
                        records.append({"script": stage.script, "desc": stage.desc,
                                        "status": "REQUIRE_FAIL"})
                        self._log("I", f"✗ {stage.desc} (前置条件未满足, 跳过)")
                        continue
                except Exception as e:
                    records.append({"script": stage.script, "desc": stage.desc,
                                    "status": "REQUIRE_ERR", "error": str(e)[:200]})
                    continue
            if not force and not stage.needs_build():
                records.append({"script": stage.script, "desc": stage.desc,
                                "status": "SKIP_FRESH"})
                self._log("I", f"✓ {stage.desc} (产物已就绪, 跳过)")
                continue
            self._log("STEP", f"构建 {stage.desc} — {stage.script}")
            cmd = [sys.executable, str(script_path), *stage.args]
            r = run_subproc(cmd, cwd=stage.cwd or wd, timeout=stage.timeout)
            ok = r["rc"] == 0 and not stage.needs_build()
            rec = {
                "script": stage.script, "desc": stage.desc,
                "status": "OK" if ok else "FAIL",
                "rc": r["rc"], "elapsed": r["elapsed"],
                "missing_after": [str(Path(p).relative_to(wd)) if Path(p).is_relative_to(wd) else str(p)
                                  for p in stage.expected_missing()],
                "stderr_tail": r["stderr"][-400:] if r["stderr"] else "",
            }
            records.append(rec)
            self._log("OK" if ok else "ERR",
                      f"{stage.desc} rc={r['rc']} elapsed={r['elapsed']}s")
        return records

    # ── Verify phase ──────────────────────────────────────────────────────
    def run_verify(self) -> Dict[str, Any]:
        # Defer import to avoid hard dependency when verifier is external
        try:
            from dao_verifier import parse_verifier_output, CheckStatus
        except Exception:
            parse_verifier_output = None  # type: ignore

        r = run_subproc(self.verifier_cmd, cwd=self.working_dir,
                        timeout=self.verifier_timeout)
        passes: List[Dict[str, str]] = []
        warns:  List[Dict[str, str]] = []
        fails:  List[Dict[str, str]] = []
        if parse_verifier_output is not None:
            for c in parse_verifier_output(r["stdout"]):
                bucket = {"PASS": passes, "WARN": warns, "FAIL": fails}.get(c.status)
                if bucket is not None:
                    bucket.append({"tag": c.tag, "msg": c.message})
        else:
            # Minimal fallback regex
            for line in r["stdout"].splitlines():
                m = re.match(r"^\s*✅\s*\[([^\]]+)\]\s*(.*)$", line)
                if m: passes.append({"tag": m.group(1), "msg": m.group(2).strip()}); continue
                m = re.match(r"^\s*⚠️?\s*\[([^\]]+)\]\s*(.*)$", line)
                if m: warns.append({"tag": m.group(1), "msg": m.group(2).strip()}); continue
                m = re.match(r"^\s*❌\s*\[([^\]]+)\]\s*(.*)$", line)
                if m: fails.append({"tag": m.group(1), "msg": m.group(2).strip()})
        total = len(passes) + len(warns) + len(fails)
        score = round(len(passes) / max(1, total) * 100)
        return {
            "rc": r["rc"], "elapsed": r["elapsed"],
            "n_pass": len(passes), "n_warn": len(warns), "n_fail": len(fails),
            "total": total, "score": score,
            "passes": passes, "warns": warns, "fails": fails,
            "stdout_tail": r["stdout"][-800:],
            "stderr_tail": r["stderr"][-400:] if r["stderr"] else "",
        }

    # ── Heal phase ────────────────────────────────────────────────────────
    def run_heal(self, warns: List[Dict[str, str]], env: Environment,
                 shared_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        healed: List[Dict[str, Any]] = []
        seen: set = set()
        for w in warns:
            tag, msg = w["tag"], w["msg"]
            matched_any = False
            for h in self.heal_registry:
                if not h.matches(tag):
                    continue
                matched_any = True
                key = (h.pattern, h.handler.__name__)
                if h.once_per_iter and key in seen:
                    healed.append({"tag": tag,
                                   "action": "handler_already_invoked_this_round"})
                    break
                seen.add(key)
                try:
                    res = h.handler(tag, msg, env, shared_state)
                    healed.append(res.to_dict() if isinstance(res, HealResult) else dict(res))
                    self._log("HEAL", f"{tag} → {res.action if isinstance(res, HealResult) else res}")
                except Exception as e:
                    healed.append({"tag": tag, "action": "handler_exception",
                                   "error": str(e)[:200]})
                    self._log("ERR", f"heal handler exception on {tag}: {e}")
                break
            if not matched_any:
                healed.append({"tag": tag, "action": "no_handler"})
        return healed

    # ── Orchestration ─────────────────────────────────────────────────────
    def run(self) -> LoopResult:
        result = LoopResult()
        env = Environment.snapshot(**self.env_spec,
                                   cwd=self.working_dir)
        result.environment = env.to_dict()
        self._log("STEP", f"环境: py={env.python} plat={env.platform}")

        shared_state: Dict[str, Any] = {"env": env, "heal_history": []}

        prev_warn_tags: Optional[Tuple[str, ...]] = None
        for i in range(1, self.max_iterations + 1):
            it = LoopIteration(iter=i)
            self._log("STEP", f"────── 轮 {i}/{self.max_iterations} ──────")

            # Build
            force = self.initial_build_force if i == 1 else False
            it.build_records = self.run_build(env, force=force)

            # Verify
            it.verify_summary = self.run_verify()
            vs = it.verify_summary
            self._log("OK" if vs["n_warn"] == 0 and vs["n_fail"] == 0 else "WARN",
                      f"验证: ✅{vs['n_pass']} ⚠️{vs['n_warn']} ❌{vs['n_fail']} "
                      f"评分 {vs['score']}/100")

            # Convergence checks
            if vs["n_warn"] == 0 and vs["n_fail"] == 0:
                result.converged = True
                result.convergence_reason = "zero-warn-zero-fail"
                result.iterations.append(it)
                self._log("CONV", f"收敛 ({result.convergence_reason})")
                break
            cur_warn_tags = tuple(sorted(w["tag"] for w in vs["warns"]))
            if prev_warn_tags is not None and cur_warn_tags == prev_warn_tags:
                result.converged = True
                result.convergence_reason = "warn-set-stable"
                result.iterations.append(it)
                self._log("CONV", f"收敛 ({result.convergence_reason})")
                break
            prev_warn_tags = cur_warn_tags

            # Heal (only for non-final iteration)
            if i < self.max_iterations:
                it.heal_records = self.run_heal(vs["warns"], env, shared_state)
                shared_state["heal_history"].extend(it.heal_records)

            result.iterations.append(it)

        # Final summary
        if result.iterations:
            last = result.iterations[-1]
            result.final_summary = {
                "n_pass": last.verify_summary.get("n_pass", 0),
                "n_warn": last.verify_summary.get("n_warn", 0),
                "n_fail": last.verify_summary.get("n_fail", 0),
                "score": last.verify_summary.get("score", 0),
                "iterations": len(result.iterations),
                "converged": result.converged,
                "reason": result.convergence_reason,
            }
        return result


# ══════════════════════════════════════════════════════════════════════════════
# 七、自验证
# ══════════════════════════════════════════════════════════════════════════════

def _self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create a dummy verifier script that prints two OK lines
        verifier = td_path / "dummy_verifier.py"
        verifier.write_text(
            "print('  ✅ [a/ok] alpha')\n"
            "print('  ✅ [b/ok] bravo')\n"
            "print('  ⚠️ [c/warn] charlie')\n",
            encoding="utf-8",
        )

        # Healer that marks c/warn as fixed by creating a file
        healed_marker = td_path / ".healed"

        def heal_c(tag, msg, env, state):
            healed_marker.write_text("ok", encoding="utf-8")
            # After heal, verifier will be replaced (cheat for test)
            verifier.write_text(
                "print('  ✅ [a/ok] alpha')\n"
                "print('  ✅ [b/ok] bravo')\n"
                "print('  ✅ [c/ok] charlie-fixed')\n",
                encoding="utf-8",
            )
            return HealResult(tag=tag, action="wrote_marker", detail={"path": str(healed_marker)})

        loop = LoopController(
            working_dir=td_path,
            verifier_cmd=[sys.executable, str(verifier)],
            build_stages=[],
            heal_registry=[HealHandler(pattern=r"^c/.*$", handler=heal_c)],
            env_spec={"modules": ["json"], "executables": {}, "services": {}},
            max_iterations=3,
            verbose=False,
        )
        res = loop.run()
        assert res.converged, f"did not converge: {res.convergence_reason}"
        assert res.convergence_reason == "zero-warn-zero-fail", res.convergence_reason
        assert healed_marker.exists(), "heal handler did not fire"
        final = res.final_iteration()
        assert final is not None and final.verify_summary["n_pass"] == 3, final

        # Serialization
        traj = res.dump_trajectory(td_path / "traj.json")
        md   = res.dump_markdown(td_path / "report.md")
        assert traj.exists() and md.exists(), "dump failed"
        data = json.loads(traj.read_text("utf-8"))
        assert data["converged"] is True, data
        assert len(data["iterations"]) == 2, f"iterations={len(data['iterations'])}"

    # parse_verifier_output via dao_verifier (confirms dependency works)
    from dao_verifier import parse_verifier_output, CheckStatus
    checks = parse_verifier_output("  ✅ [x/y] ok\n  ⚠️ [z/w] warn\n")
    assert len(checks) == 2 and checks[0].status == CheckStatus.PASS, checks

    print("  OK  environment snapshot + build skip + verify + heal + converge")
    print("  OK  trajectory.json + report.md dump")
    print("  OK  dao_verifier round-trip")
    print("\n  dao_loop self-test: all assertions passed ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
