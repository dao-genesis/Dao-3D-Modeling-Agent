#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_full_loop.py · 全链路打通 · 道法自然 · 万法归宗

> 大制不割. 圣人总而用之, 其数一也.
>
> 此脚本贯通从论文几何到 SolidWorks 实测仿真的全链路:
>   Stage 0  环境与路径锚定
>   Stage 1  几何重建      (build_*.py)
>   Stage 2  快速验证      (dao_verify_fast.py · 七相)
>   Stage 3  运动学/动力学 (dao_kinematic.py)
>   Stage 4  SW 实测仿真   (sw_simulate.py · 干涉/质量/配合/运动算例)
>   Stage 5  报告聚合      → _DAO_FULL_LOOP_REPORT.md

不发明新轮子: 调度已有引擎, 收集结果, 汇成一图, 一目可观.
道法自然 — 已成者顺之, 未成者补之, 不强求重来.

执行示例:
  python dao_full_loop.py                 # 全链路
  python dao_full_loop.py --skip-build    # 跳过 CadQuery 几何重建 (复用 output_cq/)
  python dao_full_loop.py --skip-sw       # 跳过 SolidWorks 实测仿真
  python dao_full_loop.py --skip-build --skip-sw   # 仅纯 Python 验证
"""
from __future__ import annotations
import sys, os, json, time, argparse, subprocess, shlex
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent.resolve()
REPORT_MD = HERE / "_DAO_FULL_LOOP_REPORT.md"
REPORT_JSON = HERE / "_DAO_FULL_LOOP_REPORT.json"


# ══════════════════════════════════════════════════════════════════════
# 日志
# ══════════════════════════════════════════════════════════════════════

def now() -> str:
    return datetime.now().strftime("%H:%M:%S")

def log(msg: str, level: str = "INFO"):
    sym = {"INFO": "·", "OK": "✓", "WARN": "⚠", "FAIL": "✗"}.get(level, "·")
    print(f"[{now()}] {sym} {msg}", flush=True)

def stage_banner(idx: int, title: str):
    bar = "═" * 60
    print(f"\n{bar}\n  Stage {idx} · {title}\n{bar}", flush=True)


# ══════════════════════════════════════════════════════════════════════
# 子流程执行 (统一封装 stdout/stderr 收集 + 超时)
# ══════════════════════════════════════════════════════════════════════

def run_step(name: str, cmd: List[str], timeout_s: int = 600,
             cwd: Optional[Path] = None, env_extra: Optional[Dict[str, str]] = None
             ) -> Dict[str, Any]:
    cwd = cwd or HERE
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    log(f"启动: {' '.join(shlex.quote(c) for c in cmd)}")
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), env=env,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout_s)
        rc = proc.returncode
        out = proc.stdout or ""
        err = proc.stderr or ""
    except subprocess.TimeoutExpired as e:
        rc = -1; out = ""; err = f"TIMEOUT after {timeout_s}s: {e}"
    except FileNotFoundError as e:
        rc = -2; out = ""; err = f"FileNotFound: {e}"
    except Exception as e:
        rc = -3; out = ""; err = f"Exception: {e}"
    dt = round(time.time() - t0, 2)
    status = "OK" if rc == 0 else ("WARN" if rc > 0 else "FAIL")
    log(f"完成: {name} · rc={rc} · {dt}s", status)
    # 截短日志保存
    return {
        "name": name,
        "cmd": cmd,
        "returncode": rc,
        "elapsed_s": dt,
        "stdout_tail": "\n".join(out.splitlines()[-40:]) if out else "",
        "stderr_tail": "\n".join(err.splitlines()[-20:]) if err else "",
    }


# ══════════════════════════════════════════════════════════════════════
# Stage 0 · 环境与路径锚定
# ══════════════════════════════════════════════════════════════════════

REQUIRED_FILES = {
    "config":        HERE / "config.py",
    "verify":        HERE / "dao_verify_fast.py",
    "kinematic":     HERE / "dao_kinematic.py",
    "sw_simulate":   HERE / "sw_simulate.py",
    "build_all":     HERE / "build_all_parts.py",
    "build_complete":HERE / "build_complete.py",
    "build_pulleys": HERE / "build_pulleys_v2.py",
    "build_motor":   HERE / "build_motor_y180l4.py",
    "build_vbelt":   HERE / "build_vbelt_step.py",
    "build_vbelt_pure": HERE / "build_vbelt_pure.py",
    "asm_sldasm":    HERE / "交付包_最终" / "锤式破碎机_总装配.SLDASM",
    "asm_step":      HERE / "交付包_最终" / "assembly_structured.step",
    "doc_v4":        HERE / "南京-吴鸿轩_v4_动平衡维护补充.docx",
}

def stage0_anchor() -> Dict[str, Any]:
    info: Dict[str, Any] = {"missing": [], "present": [], "python": sys.version.split()[0]}
    for k, p in REQUIRED_FILES.items():
        if p.exists():
            info["present"].append(k)
        else:
            info["missing"].append({"key": k, "path": str(p)})
            log(f"缺: {k} → {p}", "WARN")
    info["ok"] = len(info["missing"]) == 0
    info["sw_running"] = _check_sw_process()
    log(f"必备文件: {len(info['present'])}/{len(REQUIRED_FILES)} · SW 运行: {info['sw_running']}", "OK" if info["ok"] else "WARN")
    return info


def _check_sw_process() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe"],
                             capture_output=True, text=True, timeout=8)
        return "SLDWORKS.exe" in (out.stdout or "")
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════
# Stage 1 · 几何重建 (顺序: 旋转 → 结构 → 带轮 → 电机 → V带 → 整机装配)
# ══════════════════════════════════════════════════════════════════════

BUILD_STEPS = [
    ("build_all_parts",      "build_all_parts.py",       300),
    ("build_complete",       "build_complete.py",        300),
    ("build_pulleys_v2",     "build_pulleys_v2.py",      180),
    ("build_motor_y180l4",   "build_motor_y180l4.py",    180),
    ("build_vbelt_step",     "build_vbelt_step.py",      180),
    ("build_vbelt_pure",     "build_vbelt_pure.py",      180),
    ("build_complete_assembly", "build_complete_assembly.py", 300),
]

def stage1_build() -> List[Dict[str, Any]]:
    results = []
    for name, fn, to in BUILD_STEPS:
        py = HERE / fn
        if not py.exists():
            results.append({"name": name, "skipped": True, "reason": "missing"})
            log(f"跳过 (无文件): {name}", "WARN")
            continue
        r = run_step(name, [sys.executable, str(py)], timeout_s=to)
        results.append(r)
    return results


# ══════════════════════════════════════════════════════════════════════
# Stage 2 · 快速验证 (dao_verify_fast.py)
# ══════════════════════════════════════════════════════════════════════

def stage2_verify() -> Dict[str, Any]:
    r = run_step("verify", [sys.executable, str(HERE / "dao_verify_fast.py")], timeout_s=180)
    # 抓取核心评分
    score = None
    for line in (r.get("stdout_tail") or "").splitlines():
        if "评分" in line:
            # 例: "  审查完成  ✅84 ⚠️0  评分 100/100"
            try:
                tail = line.split("评分")[1].strip()
                score = tail.split()[0]
            except Exception:
                pass
    r["score"] = score
    return r


# ══════════════════════════════════════════════════════════════════════
# Stage 3 · 运动学 (dao_kinematic.py)
# ══════════════════════════════════════════════════════════════════════

def stage3_kinematic() -> Dict[str, Any]:
    return run_step("kinematic", [sys.executable, str(HERE / "dao_kinematic.py")], timeout_s=120)


# ══════════════════════════════════════════════════════════════════════
# Stage 4 · SolidWorks 实测仿真 (sw_simulate.py)
# ══════════════════════════════════════════════════════════════════════

def stage4_sw_simulate(skip_motion: bool = False) -> Dict[str, Any]:
    cmd = [sys.executable, str(HERE / "sw_simulate.py")]
    if skip_motion:
        cmd.append("--skip-motion")
    r = run_step("sw_simulate", cmd, timeout_s=900)
    # 直读 SW 仿真 JSON 报告, 把关键指标抽出来 (有则 surface 到主报告)
    sw_json = HERE / "sw_api" / "sw_simulate_report.json"
    if sw_json.exists():
        try:
            sw_rep = json.loads(sw_json.read_text(encoding="utf-8"))
        except Exception:
            sw_rep = None
        if sw_rep:
            asm_mp = (sw_rep.get("phase4_mass_properties") or {}).get("assembly") or {}
            r["sw_summary"] = {
                "sw_revision":   sw_rep.get("sw_revision"),
                "components":    (sw_rep.get("phase2_self_check") or {}).get("components_total"),
                "suppressed":    (sw_rep.get("phase2_self_check") or {}).get("components_suppressed"),
                "interferences": (sw_rep.get("phase3_interference") or {}).get("count"),
                "mass_kg":       asm_mp.get("mass_kg"),
                "cg_mm": [round((v or 0)*1000, 1) for v in (asm_mp.get("cg_m") or [0,0,0])],
                "volume_cm3":    round((asm_mp.get("volume_m3") or 0)*1e6, 1),
                "components_mp": len((sw_rep.get("phase4_mass_properties") or {}).get("components") or []),
                "mates":         (sw_rep.get("phase5_mates") or {}).get("total"),
                "snapshots":     sum(1 for v in ((sw_rep.get("phase7_render_export") or {}).get("snapshots") or {}).values() if v),
                "step_path":     (sw_rep.get("phase7_render_export") or {}).get("step"),
                "stl_path":      (sw_rep.get("phase7_render_export") or {}).get("stl"),
            }
    return r


# ══════════════════════════════════════════════════════════════════════
# Stage 5 · 报告聚合
# ══════════════════════════════════════════════════════════════════════

def aggregate_report(rep: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# 全链路打通报告 · 道法自然 · 万法归宗")
    lines.append("")
    lines.append(f"> 生成时间: {rep['timestamp']}")
    lines.append(f"> Python: {rep['stage0'].get('python','?')}")
    lines.append("")

    # 总览
    lines.append("## 五阶段总览")
    lines.append("")
    lines.append("| Stage | 名称 | 状态 |")
    lines.append("|---|---|---|")
    lines.append(f"| 0 | 环境锚定 | {'✅' if rep['stage0'].get('ok') else '⚠️'} 必备 {len(rep['stage0'].get('present',[]))}/{len(REQUIRED_FILES)} · SW {('运行中' if rep['stage0'].get('sw_running') else '未运行')} |")
    s1 = rep.get("stage1") or []
    s1_skipped_all = isinstance(s1, list) and len(s1) > 0 and all(isinstance(x, dict) and x.get("skipped") for x in s1)
    s1_ok = sum(1 for x in s1 if isinstance(x, dict) and x.get("returncode") == 0)
    s1_total = sum(1 for x in s1 if isinstance(x, dict) and not x.get("skipped"))
    if s1_skipped_all:
        lines.append("| 1 | 几何重建 | ○ 跳过 |")
    else:
        lines.append(f"| 1 | 几何重建 | {'✅' if s1_total and s1_ok == s1_total else '⚠️'} {s1_ok}/{s1_total} 步 |")
    s2 = rep.get("stage2") or {}
    if s2.get("skipped"):
        lines.append("| 2 | 快速验证 | ○ 跳过 |")
    else:
        lines.append(f"| 2 | 快速验证 | {'✅' if s2.get('returncode')==0 else '⚠️'} 评分 {s2.get('score','?')} |")
    s3 = rep.get("stage3") or {}
    if s3.get("skipped"):
        lines.append("| 3 | 运动学 | ○ 跳过 |")
    else:
        lines.append(f"| 3 | 运动学 | {'✅' if s3.get('returncode')==0 else '⚠️'} |")
    s4 = rep.get("stage4") or {}
    if s4.get("skipped"):
        lines.append("| 4 | SW 实测仿真 | ○ 跳过 |")
    else:
        sw_sum = s4.get("sw_summary") or {}
        if sw_sum:
            mass = sw_sum.get("mass_kg")
            ints = sw_sum.get("interferences", 0) or 0
            tag = "✅" if s4.get("returncode") == 0 else "⚠️"
            extra = f" · {mass}kg · 干涉×{ints} · 截图×{sw_sum.get('snapshots',0)}" if mass else ""
            lines.append(f"| 4 | SW 实测仿真 | {tag}{extra} |")
        else:
            lines.append(f"| 4 | SW 实测仿真 | {'✅' if s4.get('returncode')==0 else '⚠️'} |")
    lines.append(f"| 5 | 报告聚合 | ✅ |")
    lines.append("")
    lines.append(f"**总耗时: {rep.get('elapsed_s','?')}s**")
    lines.append("")

    # Stage 0 详
    s0 = rep["stage0"]
    if s0.get("missing"):
        lines.append("## Stage 0 · 缺失文件")
        lines.append("")
        for m in s0["missing"]:
            lines.append(f"- ⚠️ `{m['key']}` → `{m['path']}`")
        lines.append("")

    # Stage 1 详 (整体跳过时简短一句)
    if s1 and not s1_skipped_all:
        lines.append("## Stage 1 · 几何重建明细")
        lines.append("")
        lines.append("| 步骤 | 状态 | 耗时(s) |")
        lines.append("|---|---|---:|")
        for x in s1:
            if not isinstance(x, dict): continue
            if x.get("skipped"):
                lines.append(f"| {x.get('name','?')} | ○ 跳过 ({x.get('reason','?')}) | — |")
            else:
                rc = x.get("returncode", -1)
                tag = "✅" if rc == 0 else "⚠️"
                lines.append(f"| {x.get('name','?')} | {tag} rc={rc} | {x.get('elapsed_s','?')} |")
        lines.append("")
    elif s1_skipped_all:
        lines.append("## Stage 1 · 几何重建明细")
        lines.append("")
        lines.append("- ○ **已跳过** (user_skipped). 复用 `output_cq/` 已有产物.")
        lines.append("")

    # Stage 4 SW 仿真摘要 (优先展示, 道法自然 — 知者不言, 言者不知; 但工程师要看)
    sw_sum = (s4 or {}).get("sw_summary") or {}
    if sw_sum:
        lines.append("## Stage 4 · SolidWorks 仿真摘要")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|---|---|")
        lines.append(f"| SW 版本 | {sw_sum.get('sw_revision','?')} |")
        lines.append(f"| 组件数 | {sw_sum.get('components','?')} (含 {sw_sum.get('suppressed',0)} 抑制) |")
        ints = sw_sum.get('interferences', 0) or 0
        lines.append(f"| 干涉数 | {ints} {'⚠️ 需修' if ints else '✅'} |")
        lines.append(f"| 整机质量 | **{sw_sum.get('mass_kg','?')} kg** |")
        cg = sw_sum.get('cg_mm', [0,0,0])
        lines.append(f"| 整机重心 | ({cg[0]}, {cg[1]}, {cg[2]}) mm |")
        lines.append(f"| 整机体积 | {sw_sum.get('volume_cm3','?')} cm³ |")
        lines.append(f"| 组件级 | {sw_sum.get('components_mp', 0)} 件去重 |")
        mates = sw_sum.get('mates', 0) or 0
        lines.append(f"| 配合数 | {mates} {'(全 fixed 装配)' if mates == 0 else ''} |")
        lines.append(f"| 视图截图 | {sw_sum.get('snapshots', 0)} 张 |")
        if sw_sum.get('step_path'):
            lines.append(f"| STEP | `{sw_sum['step_path']}` |")
        if sw_sum.get('stl_path'):
            lines.append(f"| STL | `{sw_sum['stl_path']}` |")
        lines.append("")
        lines.append("> 完整 SW 仿真细节: `sw_api/sw_simulate_report.md`")
        lines.append("")

    # Stage 2 ~ 4 stdout 尾巴
    for sk, st in [("Stage 2 · 验证", s2), ("Stage 3 · 运动学", s3), ("Stage 4 · SW 实测仿真", s4)]:
        if not st: continue
        lines.append(f"## {sk}")
        lines.append("")
        if st.get("skipped"):
            lines.append(f"- ○ **已跳过** ({st.get('reason','user_skipped')})")
            lines.append("")
            continue
        lines.append(f"- **rc**: `{st.get('returncode','?')}`  ·  **耗时**: {st.get('elapsed_s','?')}s")
        if st.get("stdout_tail"):
            lines.append("")
            lines.append("```text")
            lines.append(st["stdout_tail"])
            lines.append("```")
        if st.get("stderr_tail"):
            lines.append("")
            lines.append("**stderr 尾**:")
            lines.append("")
            lines.append("```text")
            lines.append(st["stderr_tail"])
            lines.append("```")
        lines.append("")

    # 关联报告
    lines.append("## 关联报告")
    lines.append("")
    refs = [
        ("Phase 1-7 验证", "_DAO_REVIEW_REPORT.md"),
        ("V6 归元根治", "ROOT_CAUSE_FIX_REPORT_V6_归元_反者道之动.md"),
        ("V5 完善", "COMPLETION_REPORT_V5_大制不割_万法归宗.md"),
        ("SW 仿真 JSON", "sw_api/sw_simulate_report.json"),
        ("SW 仿真 MD",   "sw_api/sw_simulate_report.md"),
        ("运动学关键帧", "output_cq/kinematic_keyframes.json"),
    ]
    for desc, path in refs:
        p = HERE / path
        if p.exists():
            lines.append(f"- ✅ {desc}: `{path}` ({p.stat().st_size//1024}KB)")
        else:
            lines.append(f"- ○ {desc}: `{path}` (待生成)")
    lines.append("")

    lines.append("---")
    lines.append("*道法自然 · 大制不割 · 万法归宗 · 全链路打通*")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="全链路打通 · 道法自然")
    ap.add_argument("--skip-build", action="store_true", help="跳过 Stage 1 几何重建")
    ap.add_argument("--skip-verify", action="store_true", help="跳过 Stage 2 快速验证")
    ap.add_argument("--skip-kinematic", action="store_true", help="跳过 Stage 3 运动学")
    ap.add_argument("--skip-sw", action="store_true", help="跳过 Stage 4 SolidWorks 实测仿真")
    ap.add_argument("--skip-motion", action="store_true", help="SW 仿真内跳过运动算例")
    args = ap.parse_args()

    print("\n" + "═" * 60)
    print("  锤式破碎机 · 全链路打通 · 道法自然 · 万法归宗")
    print("═" * 60)

    t0 = time.time()
    rep: Dict[str, Any] = {"timestamp": datetime.now().isoformat()}

    stage_banner(0, "环境与路径锚定")
    rep["stage0"] = stage0_anchor()

    # Stage 1
    if args.skip_build:
        stage_banner(1, "几何重建 (跳过)")
        rep["stage1"] = [{"skipped": True, "reason": "user_skipped"}]
    else:
        stage_banner(1, "几何重建 (CadQuery)")
        rep["stage1"] = stage1_build()

    # Stage 2
    if args.skip_verify:
        stage_banner(2, "快速验证 (跳过)")
        rep["stage2"] = {"skipped": True, "reason": "user_skipped"}
    else:
        stage_banner(2, "快速验证 (七相)")
        rep["stage2"] = stage2_verify()

    # Stage 3
    if args.skip_kinematic:
        stage_banner(3, "运动学 (跳过)")
        rep["stage3"] = {"skipped": True, "reason": "user_skipped"}
    else:
        stage_banner(3, "运动学 / 动平衡")
        rep["stage3"] = stage3_kinematic()

    # Stage 4
    if args.skip_sw:
        stage_banner(4, "SolidWorks 实测仿真 (跳过)")
        rep["stage4"] = {"skipped": True, "reason": "user_skipped"}
    else:
        stage_banner(4, "SolidWorks 实测仿真")
        rep["stage4"] = stage4_sw_simulate(skip_motion=args.skip_motion)

    # Stage 5
    stage_banner(5, "报告聚合")
    rep["elapsed_s"] = round(time.time() - t0, 2)
    md_text = aggregate_report(rep)
    REPORT_MD.write_text(md_text, encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"报告 → {REPORT_MD}", "OK")
    log(f"JSON → {REPORT_JSON}", "OK")

    print(f"\n{'═'*60}")
    print(f"  全链路 · {rep['elapsed_s']}s · 报告: {REPORT_MD.name}")
    print(f"{'═'*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
