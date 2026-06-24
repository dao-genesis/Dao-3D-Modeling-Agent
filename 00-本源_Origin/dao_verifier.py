#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_verifier.py · 通用 N 相验证本源 · 万法之资归一
══════════════════════════════════════════════════════════════════════════════
反者道之动 — 不从项目脚本出发, 从 "断言" 的本源出发.
弱者道之用 — 零外部依赖 (只用 re/dataclasses/pathlib/datetime).
无为而无不为 — 三层: Check → Phase → Verifier; 每层可拼装, 可增量, 可序列化.

用法:
  v = Verifier(title="锤式破碎机 · 七相审查")
  with v.phase("P1 — DXF源文件验证") as ph:
      ph.ok("dxf/hammer", "hammer_A3.dxf 存在")
      ph.warn("dxf/xyz", "xyz_A3.dxf 未找到")
  v.dump_markdown(Path("_REPORT.md"))
  v.dump_json(Path("_REPORT.json"))
  print(v.summary_line())
  sys.exit(0 if v.all_passed() else 1)

与 dao_loop.py 配合: Verifier 结果的 warnings[] 可驱动自愈 Handler.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Union

__version__ = "1.0.0"
__all__ = [
    "CheckStatus", "Check", "Phase", "Verifier",
    "parse_verifier_output",
]

PathLike = Union[str, Path]

# ══════════════════════════════════════════════════════════════════════════════
# 一、状态枚举 · ASCII + emoji 双通道
# ══════════════════════════════════════════════════════════════════════════════

class CheckStatus:
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    INFO = "INFO"
    SKIP = "SKIP"

_ICON = {
    CheckStatus.PASS: "✅",
    CheckStatus.WARN: "⚠️ ",
    CheckStatus.FAIL: "❌",
    CheckStatus.INFO: "ℹ️ ",
    CheckStatus.SKIP: "⏭️ ",
}


# ══════════════════════════════════════════════════════════════════════════════
# 二、Check · 单条断言
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Check:
    tag: str                        # 形如 "P1/hammer" 或 "shape/volume"
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None  # 可选的结构化附加

    @property
    def icon(self) -> str:
        return _ICON.get(self.status, "?")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["icon"] = self.icon
        return d

    def __str__(self) -> str:
        return f"  {self.icon} [{self.tag}] {self.message}"


# ══════════════════════════════════════════════════════════════════════════════
# 三、Phase · 相 (若干 check)
# ══════════════════════════════════════════════════════════════════════════════

class Phase:
    """一个相 = 一组相关检查 + 标题 + 概要."""
    def __init__(self, title: str, verifier: "Verifier"):
        self.title = title
        self._v = verifier
        self.checks: List[Check] = []
        self.started_at: Optional[datetime] = None
        self.ended_at:   Optional[datetime] = None

    # Context manager: with v.phase(...) as ph:
    def __enter__(self) -> "Phase":
        self.started_at = datetime.now()
        self._v._begin_phase(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.ended_at = datetime.now()
        if exc_type is not None:
            self.fail("phase/exception", f"{exc_type.__name__}: {exc_val}")
            # Don't swallow: let caller handle
            return False
        return False

    # ── Assertion shortcuts ───────────────────────────────────────────────
    def _emit(self, c: Check) -> Check:
        self.checks.append(c)
        self._v._on_check(c, self)
        return c

    def ok(self,   tag: str, message: str, data: Optional[Dict[str, Any]] = None) -> Check:
        return self._emit(Check(tag=tag, status=CheckStatus.PASS, message=message, data=data))

    def warn(self, tag: str, message: str, data: Optional[Dict[str, Any]] = None) -> Check:
        return self._emit(Check(tag=tag, status=CheckStatus.WARN, message=message, data=data))

    def fail(self, tag: str, message: str, data: Optional[Dict[str, Any]] = None) -> Check:
        return self._emit(Check(tag=tag, status=CheckStatus.FAIL, message=message, data=data))

    def info(self, tag: str, message: str, data: Optional[Dict[str, Any]] = None) -> Check:
        return self._emit(Check(tag=tag, status=CheckStatus.INFO, message=message, data=data))

    def skip(self, tag: str, message: str, data: Optional[Dict[str, Any]] = None) -> Check:
        return self._emit(Check(tag=tag, status=CheckStatus.SKIP, message=message, data=data))

    # Declarative: assert/expect
    def assert_eq(self, tag: str, label: str, actual: Any, expected: Any,
                  *, tol: float = 0.0) -> Check:
        try:
            if tol > 0 and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
                delta = abs(float(actual) - float(expected))
                if delta <= tol:
                    return self.ok(tag, f"{label}={expected} → {actual} (Δ{delta:.3g}≤{tol})")
                return self.warn(tag, f"{label}={expected} → {actual} (Δ{delta:.3g}>{tol})")
            if actual == expected:
                return self.ok(tag, f"{label}={expected}")
            return self.warn(tag, f"{label} expected={expected} actual={actual}")
        except Exception as e:
            return self.fail(tag, f"{label} check error: {e}")

    def assert_true(self, tag: str, cond: bool, on_true: str, on_false: str) -> Check:
        return self.ok(tag, on_true) if cond else self.warn(tag, on_false)

    def assert_path_exists(self, tag: str, path: PathLike, *, min_size: int = 0) -> Check:
        p = Path(path)
        if not p.exists():
            return self.warn(tag, f"不存在: {p}")
        sz = p.stat().st_size
        if sz < min_size:
            return self.warn(tag, f"过小 ({sz}B < {min_size}B): {p.name}")
        return self.ok(tag, f"{p.name} ({sz//1024}KB)")

    # ── Stats ─────────────────────────────────────────────────────────────
    def count(self, status: str) -> int:
        return sum(1 for c in self.checks if c.status == status)

    def n_pass(self) -> int: return self.count(CheckStatus.PASS)
    def n_warn(self) -> int: return self.count(CheckStatus.WARN)
    def n_fail(self) -> int: return self.count(CheckStatus.FAIL)

    def elapsed_ms(self) -> float:
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds() * 1000.0
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "checks": [c.to_dict() for c in self.checks],
            "summary": {
                "pass": self.n_pass(), "warn": self.n_warn(), "fail": self.n_fail(),
                "total": len(self.checks),
            },
            "elapsed_ms": round(self.elapsed_ms(), 2),
        }


# ══════════════════════════════════════════════════════════════════════════════
# 四、Verifier · 整个审查框架
# ══════════════════════════════════════════════════════════════════════════════

class Verifier:
    """
    N 相审查容器. 支持 streaming print, markdown/json dump, 评分.

    评分 = 100 * (passes) / max(1, passes + warns + fails)
    all_passed: 无 fail 且 (warns == 0 OR warnings 均为可接受 tag).
    """
    def __init__(self, title: str = "dao_verifier", *,
                 stream: Any = sys.stdout,
                 verbose: bool = True,
                 subtitle: str = ""):
        self.title = title
        self.subtitle = subtitle
        self.phases: List[Phase] = []
        self._stream = stream
        self._verbose = verbose
        self._started = datetime.now()

    # ── Phase creation ────────────────────────────────────────────────────
    def phase(self, title: str) -> Phase:
        return Phase(title, self)

    # ── Internal hooks ────────────────────────────────────────────────────
    def _begin_phase(self, ph: Phase) -> None:
        self.phases.append(ph)
        if self._verbose:
            sep = "─" * 60
            print(f"\n{sep}\n{ph.title}\n{sep}", file=self._stream, flush=True)

    def _on_check(self, c: Check, ph: Phase) -> None:
        if self._verbose:
            print(str(c), file=self._stream, flush=True)

    # ── Aggregation ────────────────────────────────────────────────────────
    def all_checks(self) -> List[Check]:
        out: List[Check] = []
        for ph in self.phases:
            out.extend(ph.checks)
        return out

    def n_pass(self) -> int: return sum(1 for c in self.all_checks() if c.status == CheckStatus.PASS)
    def n_warn(self) -> int: return sum(1 for c in self.all_checks() if c.status == CheckStatus.WARN)
    def n_fail(self) -> int: return sum(1 for c in self.all_checks() if c.status == CheckStatus.FAIL)
    def total(self)  -> int: return self.n_pass() + self.n_warn() + self.n_fail()

    def score(self) -> int:
        t = self.total()
        return round(self.n_pass() / max(1, t) * 100)

    def all_passed(self) -> bool:
        return self.n_fail() == 0 and self.n_warn() == 0

    def warnings(self) -> List[Check]:
        return [c for c in self.all_checks() if c.status == CheckStatus.WARN]

    def failures(self) -> List[Check]:
        return [c for c in self.all_checks() if c.status == CheckStatus.FAIL]

    def summary_line(self) -> str:
        return (f"审查完成 ✅{self.n_pass()} ⚠️{self.n_warn()} ❌{self.n_fail()}"
                f"  评分 {self.score()}/100")

    # ── Serialization ──────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "started_at": self._started.isoformat(timespec="seconds"),
            "phases": [ph.to_dict() for ph in self.phases],
            "summary": {
                "pass": self.n_pass(), "warn": self.n_warn(), "fail": self.n_fail(),
                "total": self.total(), "score": self.score(),
                "all_passed": self.all_passed(),
            },
        }

    def dump_json(self, path: PathLike, *, indent: int = 2) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=indent),
                     encoding="utf-8")
        return p

    def dump_markdown(self, path: PathLike, *, title_prefix: str = "") -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines: List[str] = []
        lines.append(f"# {title_prefix}{self.title}" if title_prefix else f"# {self.title}")
        if self.subtitle:
            lines += ["", f"> {self.subtitle}"]
        lines += ["", f"> 时间: {self._started.strftime('%Y-%m-%d %H:%M:%S')}",
                  f"> 评分: **{self.score()}/100** "
                  f"(✅{self.n_pass()} ⚠️{self.n_warn()} ❌{self.n_fail()})",
                  "", "---", ""]
        for ph in self.phases:
            lines.append(f"## {ph.title}")
            lines.append("")
            s = ph.to_dict()["summary"]
            lines.append(f"*{s['pass']} passes · {s['warn']} warnings · {s['fail']} failures*")
            lines.append("")
            lines.append("| 状态 | 标签 | 说明 |")
            lines.append("|------|------|------|")
            for c in ph.checks:
                icon = c.icon
                # Escape pipes in message to avoid breaking table
                msg = c.message.replace("|", "\\|")
                lines.append(f"| {icon} {c.status} | `{c.tag}` | {msg} |")
            lines.append("")
        lines += ["---", "",
                  "*道法自然 · 万法归宗 · 锚定本源 · 闭环自验证*"]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    # ── CLI: exit code ────────────────────────────────────────────────────
    def exit_code(self) -> int:
        if self.n_fail() > 0:
            return 2
        if self.n_warn() > 0:
            return 1
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# 五、逆向 · 从 Verifier 的 stdout 反向重建 Check 列表 (给 dao_loop 用)
# ══════════════════════════════════════════════════════════════════════════════

_OK_RX   = re.compile(r"^\s*✅\s*\[([^\]]+)\]\s*(.*)$")
_WARN_RX = re.compile(r"^\s*⚠️?\s*\[([^\]]+)\]\s*(.*)$")
_FAIL_RX = re.compile(r"^\s*❌\s*\[([^\]]+)\]\s*(.*)$")
_INFO_RX = re.compile(r"^\s*ℹ️?\s*\[([^\]]+)\]\s*(.*)$")


def parse_verifier_output(stdout: str) -> List[Check]:
    """
    从 print 输出反向解析出 Check 流. 给 dao_loop 监控外部 verifier 用.
    """
    out: List[Check] = []
    for line in stdout.splitlines():
        for rx, st in ((_OK_RX,   CheckStatus.PASS),
                       (_FAIL_RX, CheckStatus.FAIL),
                       (_WARN_RX, CheckStatus.WARN),
                       (_INFO_RX, CheckStatus.INFO)):
            m = rx.match(line)
            if m:
                out.append(Check(tag=m.group(1), status=st, message=m.group(2).strip()))
                break
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 六、自验证 · python dao_verifier.py
# ══════════════════════════════════════════════════════════════════════════════

def _self_test() -> int:
    v = Verifier(title="dao_verifier 自测", subtitle="本源自验证", verbose=False)
    with v.phase("P1 — 基础断言") as ph:
        ph.ok("base/a", "a 通过")
        ph.warn("base/b", "b 警告")
        ph.fail("base/c", "c 失败")
    with v.phase("P2 — 断言助手") as ph:
        ph.assert_eq("eq/x", "x", 42, 42)
        ph.assert_eq("eq/y", "y", 3.14, 3.15, tol=0.01)
        ph.assert_eq("eq/z", "z", 5.0, 10.0, tol=0.1)       # 警告
        ph.assert_true("bool/t", True, "真", "假")
        ph.assert_true("bool/f", False, "真", "假")          # 警告
    assert v.n_pass() == 4, f"n_pass={v.n_pass()}"
    assert v.n_warn() == 3, f"n_warn={v.n_warn()}"
    assert v.n_fail() == 1, f"n_fail={v.n_fail()}"
    assert 0 <= v.score() <= 100

    # Serialization round-trip
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        md = v.dump_markdown(Path(td) / "report.md", title_prefix="TEST ")
        assert md.exists() and md.stat().st_size > 200, md
        js = v.dump_json(Path(td) / "report.json")
        data = json.loads(js.read_text("utf-8"))
        assert data["summary"]["pass"] == 4 and data["summary"]["fail"] == 1, data["summary"]

    # Streaming parse round-trip via stdout-like buffer
    import io
    buf = io.StringIO()
    v2 = Verifier(title="stream", stream=buf, verbose=True)
    with v2.phase("P") as ph:
        ph.ok("alpha", "hello")
        ph.warn("beta", "careful")
    checks = parse_verifier_output(buf.getvalue())
    assert any(c.tag == "alpha" and c.status == CheckStatus.PASS for c in checks), checks
    assert any(c.tag == "beta" and c.status == CheckStatus.WARN for c in checks), checks

    print(f"  OK  Verifier: {v.summary_line()}")
    print(f"  OK  phases: {len(v.phases)} total_checks: {v.total()}")
    print(f"  OK  round-trip: markdown + json + streaming-parse")
    print("\n  dao_verifier self-test: all assertions passed ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
