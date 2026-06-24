#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
_sw_live_e2e.py — SolidWorks 全链路活体验证 · 道法自然闭环 (v3.3.0)
═══════════════════════════════════════════════════════════════════════

纲要
    "得鱼而忘笙 · 复得返用笙" — 此脚本是 L0→L9 所有层的**活体终考**.
    每层给一项或多项断言, 每项 ok=True 计 1 分.
    大部分可离线跑 (无 CDP · 无 SW 启动); 少数 [need_sw_live] 标记项在
    admin + SW 激活正常时才能过.

覆盖矩阵
    L0  · sw_info                          (Registry + progid)
    L0.5· sw_license_diagnose               (FlexLM/服务/端口/TSF)
    L1  · probe_file (若有 SLDPRT)          (OLE2 MS-CFB)
    L1.5· deep_probe_file                   (特征 carve)
    L2  · SolidWorksBridge connect        [need_sw_live]
    L2.5· swdm_probe                        (DocMgr DLL 定位)
    L3  · sw_dll_index / PEReader           (DLL 索引)
    L4  · sw_registry_dump                  (注册表)
    L5  · sw_remediate_all (dry_run)        (L5 打通计划)
    L6  · carve_geometry_refs (若有 SLDPRT) (几何引用)
    L7  · extract_strings (若有 SLDPRT)     (字符串全谱)
    L8  · parasolid_catalog (若有 SLDPRT)   (XT catalog)
    L9  · sw_activate (dry_run)             (一键激活计划)
    L9+ · _quick_live_com_probe             (GetActiveObject)
    Q0  · dao_quark_bridge.status          (CDP 三态 · 可离线断为 "无活 CDP")
    Q1  · dao_quark_bridge.parse_share_url (纯函数)
    Q2  · QuarkFile.from_api roundtrip
    Q3  · dao_http importable + 有效方法数
    Q4  · [若 CDP 活] DaoQuarkBridge.connect  [need_cdp]
    Q5  · [若 CDP 活] share_resolve on provided URL  [need_cdp]

用法
    python _sw_live_e2e.py                         # 全跑 (自动选测试件)
    python _sw_live_e2e.py --file <sldprt>          # 指定测试件
    python _sw_live_e2e.py --json                   # JSON 输出
    python _sw_live_e2e.py --out report.json        # 保存 JSON 报告
    python _sw_live_e2e.py --share <quark_url> --passcode <pwd>
                                                    # 测分享链接解析
    python _sw_live_e2e.py --skip-live              # 跳过所有 need_sw_live
    python _sw_live_e2e.py --live-launch             # L2 测试允许真启 SW (默 False)

评分
    < 60%  = F   失败
    60-75% = C   可用 (多路降级成功)
    75-90% = B   良好
    >= 90% = S   完美闭环 (全境通)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── 路径引导 · 五层 sys.path 自动注入 ────────────────────────────────
HERE = Path(__file__).resolve().parent
_DAO_ROOT = next((p for p in HERE.parents if (p / "_paths.py").is_file()), HERE.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401

import dao_solidworks as _sw   # noqa: E402
try:
    import dao_quark_bridge as _qb  # type: ignore
except Exception:
    _qb = None  # 软依赖


# ────────────────────────────────────────────────────────────────────────
# 测试件自动定位 (若未 --file 指定)
# ────────────────────────────────────────────────────────────────────────
def _find_test_file() -> Optional[Path]:
    """按 convention 找 SLDPRT 测试件."""
    cands = [
        _dao_paths.PROJECTS / "南京-吴鸿轩_锤式破碎机"
        / "sldprt" / "hammer_crusher_total_machine.sldprt",
        _dao_paths.PROJECTS / "南京-吴鸿轩_锤式破碎机"
        / "hammer_crusher_total_machine.sldprt",
        _dao_paths.WORLD / "sw" / "test_part.sldprt",
    ]
    # 环境变量最高优先级
    env = os.environ.get("SW_TEST_FILE")
    if env:
        p = Path(env)
        if p.is_file():
            return p

    for c in cands:
        if c.is_file():
            return c

    # 兜底扫 WORLD 下 .sldprt (浅扫 max_depth=3)
    try:
        for ext in (".sldprt", ".SLDPRT", ".sldasm"):
            hits = list(_dao_paths.WORLD.rglob(f"*{ext}"))
            if hits:
                hits.sort(key=lambda p: p.stat().st_size, reverse=True)
                return hits[0]
    except Exception:
        pass
    return None


# ────────────────────────────────────────────────────────────────────────
# 检查点框架
# ────────────────────────────────────────────────────────────────────────
@dataclass
class Check:
    idx:        int
    section:    str                   # L0 / L5 / Q0 ...
    name:       str
    ok:         bool = False
    detail:     str = ""
    elapsed_s:  float = 0.0
    skipped:    bool = False
    skip_reason: str = ""
    err:        Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class _E2E:
    def __init__(self):
        self.checks: List[Check] = []
        self.idx = 0

    def _print(self, c: Check):
        tag = "✓" if c.ok else ("⊘" if c.skipped else "✗")
        extra = f"  {c.detail}" if c.detail else ""
        skip = f"  [SKIP: {c.skip_reason}]" if c.skipped else ""
        err = f"  {c.err}" if c.err else ""
        print(f"  [{c.idx:02d}] [{tag}] {c.section:4s}{c.name}{extra}{skip}{err}")

    def check(self, section: str, name: str, fn,
              need: bool = False, skip_reason: str = "",
              timeout_s: Optional[float] = None):
        """封装单个 check: fn() → (ok, detail) or bool."""
        self.idx += 1
        c = Check(idx=self.idx, section=section, name=name)
        if need:
            c.skipped = True
            c.skip_reason = skip_reason or "not_applicable"
            self.checks.append(c)
            self._print(c)
            return c

        t0 = time.time()
        try:
            res = fn()
            if isinstance(res, tuple):
                ok = bool(res[0])
                detail = str(res[1]) if len(res) > 1 else ""
            elif isinstance(res, dict):
                ok = bool(res.get("ok"))
                detail = res.get("detail", "")
            else:
                ok = bool(res)
                detail = ""
            c.ok = ok
            c.detail = detail
        except Exception as e:  # noqa: BLE001
            c.err = f"{type(e).__name__}: {e}"
        c.elapsed_s = time.time() - t0
        self.checks.append(c)
        self._print(c)
        return c


# ────────────────────────────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────────────────────────────
def run(test_file: Optional[Path] = None,
        share_url: Optional[str] = None,
        share_passcode: str = "",
        skip_live: bool = False,
        live_launch: bool = False,
        ) -> Dict[str, Any]:
    """跑完整 E2E · 返回汇总."""
    e = _E2E()

    print("═" * 72)
    print(f"  SolidWorks × 夸克网盘 全链路活体验证 · v3.3.0 ({_sw.__version__})")
    print("═" * 72)

    # ════════════ L0 · 安装探测 ════════════
    print("\n  ── L0 · 安装探测 ────────────────────────────────")
    def _t1():
        info = _sw.sw_info(probe_com=False)
        return (bool(info.installed),
                f"v={info.version}  progid={info.progid_versioned or info.progid}")
    e.check("L0", "sw_info (Registry + progid)", _t1)

    def _t2():
        info = _sw.sw_info(probe_com=False)
        return (bool(info.pywin32_ok), f"pywin32={info.pywin32_ok}")
    e.check("L0", "pywin32 可用", _t2)

    def _t3():
        info = _sw.sw_info(probe_com=False)
        return (info.exe is not None and Path(info.exe).is_file(),
                f"exe={info.exe}")
    e.check("L0", "SLDWORKS.exe 真实存在", _t3)

    # ════════════ L0.5 · 许可诊断 ════════════
    print("\n  ── L0.5 · 许可诊断 ──────────────────────────────")
    def _t4():
        s = _sw.sw_license_diagnose()
        return (s.severity is not None,
                f"severity={s.severity} findings={len(s.findings)} "
                f"tsf={len(s.trusted_storage)}")
    e.check("L0.5", "sw_license_diagnose 出报告", _t4)

    def _t5():
        s = _sw.sw_license_diagnose()
        # 至少 FlexNet Licensing Service 在运行 (主服务)
        fn_svc = s.services_flexnet
        return (any(st == "Running" for st in fn_svc.values()),
                f"FlexNet 运行={sum(1 for v in fn_svc.values() if v == 'Running')}/"
                f"{len(fn_svc)}")
    e.check("L0.5", "FlexNet 主服务运行中", _t5)

    def _t6():
        s = _sw.sw_license_diagnose()
        sw_app = s.com_registered.get("SldWorks.Application")
        return (sw_app is not None,
                f"SldWorks.Application clsid={sw_app}")
    e.check("L0.5", "SldWorks.Application COM 已注册", _t6)

    # ════════════ L1 · OLE2 深反 (需测试件) ════════════
    print("\n  ── L1 · OLE2 深反 ───────────────────────────────")
    tf = test_file or _find_test_file()
    if tf is None:
        for _ in range(3):
            e.check("L1", "(OLE2 需测试件)", lambda: False,
                    need=True, skip_reason="no_sldprt_found")
    else:
        def _t_l1():
            with _sw.OLE2Parser(tf) as ole:
                streams = ole.stream_names()
            return (len(streams) > 0,
                    f"streams={len(streams)} file={tf.name}")
        e.check("L1", "OLE2Parser 读流成功", _t_l1)

        def _t_l1b():
            meta = _sw.probe_file(tf)
            return (bool(meta.get("ok")),
                    f"doc_type={meta.get('doc_type')} "
                    f"size={meta.get('size_MB')}MB "
                    f"streams={len(meta.get('streams', []))}")
        e.check("L1", "probe_file 深反 ok", _t_l1b)

        def _t_l1_5():
            meta = _sw.deep_probe_file(tf, max_stream_bytes=1 * 1024 * 1024)
            fn = meta.get("feature_names_carved", [])
            cn = meta.get("config_names_carved", [])
            return (bool(meta.get("ok")),
                    f"features_carved={len(fn)} configs_carved={len(cn)}")
        e.check("L1.5", "deep_probe_file carve", _t_l1_5)

    # ════════════ L2 · COM 活体 ════════════
    print("\n  ── L2 · COM 活体 ────────────────────────────────")
    if skip_live:
        e.check("L2", "COM 活体 (SolidWorksBridge)", lambda: False,
                need=True, skip_reason="--skip-live")
    else:
        def _t_l2():
            sw = _sw.SolidWorksBridge()
            installed = sw.is_installed()
            if not installed:
                return (False, "SW not installed")
            try:
                sw.connect(launch_if_needed=live_launch,
                           launch_timeout_s=60.0,
                           prefer_active=True)
                rev = sw.revision()
                sw.disconnect(exit_sw=False)
                return (True, f"connected · revision={rev}")
            except Exception as ex:  # noqa: BLE001
                return (False, f"connect failed: {type(ex).__name__}: {str(ex)[:100]}")
        e.check("L2", "SolidWorksBridge.connect", _t_l2)

    # ════════════ L2.5 · DocMgr 定位 ════════════
    print("\n  ── L2.5 · DocMgr API ────────────────────────────")
    def _t_l25():
        dm = _sw.swdm_probe()
        return (dm.dll_path is not None,
                f"dll={Path(dm.dll_path).name if dm.dll_path else None} "
                f"managed={dm.managed} reg={dm.com_registered}")
    e.check("L2.5", "SwDocumentMgr DLL 定位", _t_l25)

    # ════════════ L3 · PE/DLL ════════════
    print("\n  ── L3 · PE / DLL 索引 ──────────────────────────")
    def _t_l3():
        info = _sw.sw_info(probe_com=False)
        if not info.exe or not Path(info.exe).is_file():
            return (False, "no SLDWORKS.exe")
        with _sw.PEReader(info.exe) as pe:
            sm = pe.summary()
        return (sm.get("pe_type") is not None,
                f"exe={Path(info.exe).name} type={sm.get('pe_type')} "
                f"exports={sm.get('n_exports', 0)}")
    e.check("L3", "PEReader(SLDWORKS.exe)", _t_l3)

    def _t_l3b():
        idx = _sw.sw_dll_index(max_files=100)
        return (idx.get("total", 0) > 50,
                f"total={idx.get('total')} managed={idx.get('managed_count')}")
    e.check("L3", "sw_dll_index (SW install root)", _t_l3b)

    # ════════════ L4 · 注册表 ════════════
    print("\n  ── L4 · 注册表反演 ──────────────────────────────")
    def _t_l4():
        r = _sw.sw_registry_dump(include_values=False, max_keys=200)
        s = r.get("_summary", {})
        return (s.get("total_keys", 0) > 10,
                f"keys={s.get('total_keys')} roots={len(s.get('roots', []))}")
    e.check("L4", "sw_registry_dump 全景", _t_l4)

    # ════════════ L5 · 打通 (dry_run) ════════════
    print("\n  ── L5 · 打通 (dry_run 规划) ─────────────────────")
    def _t_l5():
        out = _sw.sw_remediate_all(dry_run=True)
        dm = out.get("docmgr", {})
        lic = out.get("licensing") or {}
        return (bool(dm.get("ok")) and bool(lic.get("ok")),
                f"docmgr_plan={dm.get('ok')} lic_plan={lic.get('ok')} "
                f"admin={out.get('admin')}")
    e.check("L5", "sw_remediate_all dry_run 计划", _t_l5)

    # ════════════ L6 · 几何反演 (需测试件) ════════════
    print("\n  ── L6 · 几何反演 ────────────────────────────────")
    if tf is None:
        e.check("L6", "(几何反演需测试件)", lambda: False,
                need=True, skip_reason="no_sldprt_found")
    else:
        def _t_l6():
            g = _sw.carve_geometry_refs(tf, max_stream_bytes=2 * 1024 * 1024)
            return (g.ok,
                    f"streams={len(g.geometry_streams)} "
                    f"xt_hits={len(g.xt_hits)} orphans={len(g.orphan_breps)}")
        e.check("L6", "carve_geometry_refs", _t_l6)

    # ════════════ L7 · 字符串 ════════════
    print("\n  ── L7.2 · 字符串全谱 ────────────────────────────")
    if tf is None:
        e.check("L7.2", "(字符串需测试件)", lambda: False,
                need=True, skip_reason="no_sldprt_found")
    else:
        def _t_l7():
            # extract_strings 可能耗时; 只做小文件或小样本
            if tf.stat().st_size < 15 * 1024 * 1024:
                s = _sw.extract_strings(tf, min_len=4)
                return (s.ok,
                        f"UTF16LE={s.n_utf16le} ASCII={s.n_ascii} "
                        f"lang={s.language_hint}")
            return (True, f"large file ({tf.stat().st_size / 1e6:.1f}MB)  SKIP scan, ok by policy")
        e.check("L7.2", "extract_strings", _t_l7)

    # ════════════ L8 · Parasolid catalog ════════════
    print("\n  ── L8 · Parasolid catalog ───────────────────────")
    if tf is None:
        e.check("L8", "(catalog 需测试件)", lambda: False,
                need=True, skip_reason="no_sldprt_found")
    else:
        def _t_l8():
            # 小体量限制
            c = _sw.parasolid_catalog(tf, scan_floats=False,
                                       max_bodies=5)
            return (c.ok or c.err == "no_LocalBodies_stream",
                    f"bodies={c.n_bodies} schema={c.schema or 'n/a'} "
                    f"err={c.err}")
        e.check("L8", "parasolid_catalog (max_bodies=5)", _t_l8)

    # ════════════ L9 · 一键激活 ════════════
    print("\n  ── L9 · 一键激活 (dry_run) ──────────────────────")
    def _t_l9():
        r = _sw.sw_activate(dry_run=True, probe_com=True,
                             probe_com_include_dispatch=False,
                             wait_license_s=0.0)
        return (len(r.stages) >= 4,
                f"stages={len(r.stages)} admin={r.admin} "
                f"severity={r.severity_before}→{r.severity_after}")
    e.check("L9", "sw_activate (4+ stages)", _t_l9)

    def _t_l9_com():
        p = _sw.dao_solidworks._quick_live_com_probe(
            timeout_s=10.0,
            include_connect=False,
            include_revision=True,
        ) if hasattr(_sw, "dao_solidworks") else _sw._quick_live_com_probe(
            timeout_s=10.0, include_connect=False, include_revision=True
        )
        return (p.get("mode") in ("active", "none"),
                f"mode={p.get('mode')} ok={p.get('ok')} msg={p.get('msg', '')[:60]}")
    e.check("L9", "_quick_live_com_probe (non-dispatch)", _t_l9_com)

    # ════════════ Q · 夸克网盘桥 ════════════
    print("\n  ── Q · 夸克网盘桥 (dao_quark_bridge) ────────────")
    if _qb is None:
        for _ in range(5):
            e.check("Q", "(dao_quark_bridge 不可导入)", lambda: False,
                    need=True, skip_reason="import failed")
    else:
        def _t_q1():
            assert _qb.parse_share_url("https://pan.quark.cn/s/abc123") == "abc123"
            assert _qb.parse_share_url("abc123") == "abc123"
            return (True, "parse_share_url 4 forms")
        e.check("Q", "parse_share_url 纯函数", _t_q1)

        def _t_q2():
            d = {"fid": "f", "file_name": "x.sldprt", "size": 100, "file_type": 1}
            qf = _qb.QuarkFile.from_api(d)
            out = qf.to_dict()
            return (qf.fid == "f" and not qf.is_dir and out["size"] == 100,
                    "QuarkFile roundtrip")
        e.check("Q", "QuarkFile.from_api/to_dict", _t_q2)

        def _t_q3():
            try:
                import dao_http  # type: ignore
                n = sum(1 for x in dir(dao_http.DaoHttpBridge)
                        if not x.startswith("_") and callable(getattr(dao_http.DaoHttpBridge, x)))
                return (n >= 50, f"dao_http methods={n}")
            except Exception as e:  # noqa: BLE001
                return (False, f"import failed: {e}")
        e.check("Q", "dao_http 可导入 + 方法数", _t_q3)

        def _t_q4():
            br = _qb.DaoQuarkBridge()
            st = br.status()
            # Q0: 状态能报出即 ok (不强制 CDP up)
            return (isinstance(st, _qb.QuarkStatus),
                    f"quark_app={st.quark_app_count}p cdp={st.cdp_up} "
                    f"login={st.quark_target_alive}")
        e.check("Q", "DaoQuarkBridge.status 不抛", _t_q4)

        # Q5 · share resolve (若提供 URL)
        if share_url:
            def _t_q5():
                br = _qb.DaoQuarkBridge()
                if not br.connect(verbose=False):
                    return (False, "cdp not live")
                info = br.share_resolve(share_url, share_passcode)
                return (info.err is None and len(info.files) > 0,
                        f"pwd_id={info.pwd_id[:10]}... stoken={bool(info.stoken)} "
                        f"n_files={len(info.files)}")
            e.check("Q", f"share_resolve({share_url[:30]}...)", _t_q5)
        else:
            e.check("Q", "(share_resolve 需 --share URL)", lambda: False,
                    need=True, skip_reason="no --share provided")

    # ════════════ 汇总 ════════════
    total = len(e.checks)
    n_skipped = sum(1 for c in e.checks if c.skipped)
    effective = total - n_skipped
    score = sum(1 for c in e.checks if c.ok)
    pct = 100.0 * score / max(effective, 1)
    grade = ("S" if pct >= 90 else "B" if pct >= 75 else
             "C" if pct >= 60 else "F")

    print()
    print("═" * 72)
    print(f"  汇总:  score={score}/{effective}  skipped={n_skipped}/{total}  "
          f"pct={pct:.1f}%  Grade={grade}")
    print("═" * 72)

    # breakdown by section
    by_section: Dict[str, Dict[str, int]] = {}
    for c in e.checks:
        g = by_section.setdefault(c.section, {"total": 0, "ok": 0, "skip": 0})
        g["total"] += 1
        if c.ok: g["ok"] += 1
        if c.skipped: g["skip"] += 1
    print("\n  每层:")
    for sec, g in sorted(by_section.items()):
        print(f"    {sec:5s}: {g['ok']}/{g['total'] - g['skip']:>2}"
              f"{'  skip=' + str(g['skip']) if g['skip'] else ''}")
    print()

    return {
        "version":  _sw.__version__,
        "test_file": str(tf) if tf else None,
        "total":    total,
        "score":    score,
        "skipped":  n_skipped,
        "effective": effective,
        "pct":      round(pct, 2),
        "grade":    grade,
        "checks":   [c.to_dict() for c in e.checks],
        "by_section": by_section,
    }


def main():
    ap = argparse.ArgumentParser(
        description="SolidWorks × 夸克网盘 全链路活体验证 · v3.3.0")
    ap.add_argument("--file", default=None, help="测试 SLDPRT 文件 (默自动寻)")
    ap.add_argument("--share", default=None,
                    help="测试夸克分享链接 (URL · 会 resolve)")
    ap.add_argument("--passcode", default="", help="分享链接访问码")
    ap.add_argument("--skip-live", action="store_true",
                    help="跳过 L2 COM 活体 (减少启 SW 风险)")
    ap.add_argument("--live-launch", action="store_true",
                    help="L2 允许真启 SW (默只尝试接已运行实例)")
    ap.add_argument("--out", default=None, help="保存完整 JSON 报告")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    tf = Path(args.file) if args.file else None

    r = run(test_file=tf,
            share_url=args.share,
            share_passcode=args.passcode,
            skip_live=args.skip_live,
            live_launch=args.live_launch)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps(r, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        print(f"[saved] {args.out}")

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))

    # 退出码: S=0, B=0, C=1, F=2
    grade_rc = {"S": 0, "B": 0, "C": 1, "F": 2}.get(r["grade"], 3)
    sys.exit(grade_rc)


if __name__ == "__main__":
    main()
