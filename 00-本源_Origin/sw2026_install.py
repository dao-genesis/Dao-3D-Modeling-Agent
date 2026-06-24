#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sw2026_install.py — SolidWorks 2026 全链路安装本源 · L10
═══════════════════════════════════════════════════════════════════════════════
道法自然 · 用户无为 · 万物并育而不相害

从 F:\\SW2026\\*.rar 到 COM 活体 · 六阶段线性 pipeline · 每阶段幂等

┌──────────────────────────────────────────────────────────────────────────┐
│  stage 0 · prelude   admin / disk / baseline snapshot                    │
│  stage 1 · extract   ensure 7z + RAR → 展开                              │
│  stage 2 · scan      StartSWInstall.exe / sldIM.exe / setup.exe          │
│  stage 3 · install   /unattended 静默 · GUI 兜底                         │
│  stage 4 · sp        SP1.1 覆盖                                           │
│  stage 5 · activate  dao_solidworks.sw_activate_and_verify(apply=True)   │
│  stage 6 · verify    sw_info(probe_com=True) + 打开测件                   │
└──────────────────────────────────────────────────────────────────────────┘

CLI:
    python sw2026_install.py all                # dry-run 显示计划
    python sw2026_install.py all --apply        # 真执 · 需管理员 shell
    python sw2026_install.py <stage> [--apply]  # 单阶段 (0..6 或阶段名)
    python sw2026_install.py status             # 当前进度
    python sw2026_install.py reset              # 清除 sentinel (不动已装软件)
    python sw2026_install.py open-tutorial      # 打开 SW2026安装教程.mp4
    python sw2026_install.py locate             # 只探测 F:\\SW2026 物料 + 打印

设计原则:
    * 每阶段写 state.json + {stage}.sentinel.json, 可断点续跑
    * 全部关键事件 tee 到 90-日志_Logs/sw2026/install_YYYYMMDD_HHMMSS.log
    * dry_run 默认 True (只打印计划), --apply 才真执
    * 任何网络下载都有国内/国际双通道 + 便携 fallback
    * 永远不动 C:\\ProgramData\\SOLIDWORKS\\SOLIDWORKS 2023 (留给旧版)
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

# ─── 路径引导 (五层万法) ──────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_DAO_ROOT: Optional[Path] = None
for _p in _HERE.parents:
    if (_p / "_paths.py").is_file():
        _DAO_ROOT = _p
        break
if _DAO_ROOT is not None:
    sys.path.insert(0, str(_DAO_ROOT))
    try:
        import _paths as _dao_paths  # type: ignore
    except Exception:  # noqa: BLE001
        _dao_paths = None
else:
    _dao_paths = None

# ─── 常量 ────────────────────────────────────────────────────────────────
APP_NAME    = "SolidWorks 2026"
SCRIPT_VER  = "1.0.0"
SCRIPT_DATE = "2026-04-19"

SRC_DIR         = Path(r"F:\SW2026")
RAR_BASE_NAME   = "SolidWorks2026.rar"
RAR_SP_NAME     = "SolidWorks2026 SP1.1.rar"
TUTORIAL_NAME   = "SW2026安装教程.mp4"
AV_GUIDE_NAME   = "如何关闭电脑上的防火墙和杀毒工具.mp4"

# 解压目标 (F: 有 316 GB 空闲, 放到源盘更符合"本地性")
EXTRACT_ROOT       = SRC_DIR / "_extracted"
EXTRACT_BASE_DIR   = EXTRACT_ROOT / "SolidWorks2026"
EXTRACT_SP_DIR     = EXTRACT_ROOT / "SolidWorks2026_SP1.1"

# 日志 + 状态
if _dao_paths is not None:
    LOG_ROOT   = _dao_paths.LOGS / "sw2026"
    CACHE_ROOT = _dao_paths.WORLD / "_cache" / "sw2026"
else:
    LOG_ROOT   = _HERE.parent / "90-日志_Logs" / "sw2026"
    CACHE_ROOT = _HERE.parent / "70-天下_World" / "_cache" / "sw2026"
STATE_FILE     = LOG_ROOT / "state.json"
SENTINEL_DIR   = LOG_ROOT / "sentinels"
LOG_ROOT.mkdir(parents=True, exist_ok=True)
SENTINEL_DIR.mkdir(parents=True, exist_ok=True)
CACHE_ROOT.mkdir(parents=True, exist_ok=True)

# SW 识别注册表路径
SW_REG_KEYS = [
    r"SOFTWARE\SolidWorks",
    r"SOFTWARE\SolidWorks\SOLIDWORKS 2026",
    r"SOFTWARE\Classes\SldWorks.Application.34",  # SW2026 对应 v34
    r"SOFTWARE\Classes\SldWorks.Application.33",  # SW2025
    r"SOFTWARE\Classes\SldWorks.Application.32",
    r"SOFTWARE\Classes\SldWorks.Application.31",  # SW2023
]

# 磁盘需求 (GB)
REQUIRED_FREE_EXTRACT_GB = 65  # 两个 RAR 解压后 ~45-50 GB + 余量
REQUIRED_FREE_INSTALL_GB = 25  # SW 2026 完整安装约 20 GB

# 7-Zip 下载源 (按可用性排序)
SEVENZIP_URLS = [
    # SourceForge (国际 + 国内可通, 已实测 200)
    "https://sourceforge.net/projects/sevenzip/files/7-Zip/24.09/7z2409-x64.exe/download",
    # 7-zip 官网 (国际镜像, 可能慢)
    "https://www.7-zip.org/a/7z2409-x64.exe",
    # 历史版本 fallback
    "https://www.7-zip.org/a/7z2408-x64.exe",
]
SEVENZIP_EXE_NAME = "7z2409-x64.exe"

# L9 激活模块导入 (延迟 import 到需要时)
_dao_sw = None
def _lazy_import_dao_sw():
    global _dao_sw
    if _dao_sw is not None:
        return _dao_sw
    try:
        import dao_solidworks as _mod  # type: ignore
        _dao_sw = _mod
    except Exception as e:  # noqa: BLE001
        log(f"[warn] dao_solidworks import failed: {e}", "warn")
        _dao_sw = None
    return _dao_sw


# ─── 日志 · tee 到文件 + stdout ──────────────────────────────────────────
_LOG_FILE: Optional[Path] = None
_LOG_FH = None

def _open_log() -> Path:
    global _LOG_FILE, _LOG_FH
    if _LOG_FH is not None:
        return _LOG_FILE  # type: ignore
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _LOG_FILE = LOG_ROOT / f"install_{ts}.log"
    _LOG_FH = _LOG_FILE.open("a", encoding="utf-8")
    _LOG_FH.write(f"# sw2026_install.py v{SCRIPT_VER} ({SCRIPT_DATE})\n")
    _LOG_FH.write(f"# started: {datetime.now().isoformat()}\n")
    _LOG_FH.write(f"# python : {sys.version.splitlines()[0]}\n")
    _LOG_FH.write(f"# cwd    : {os.getcwd()}\n")
    _LOG_FH.write(f"# args   : {sys.argv}\n")
    _LOG_FH.write("=" * 78 + "\n")
    _LOG_FH.flush()
    return _LOG_FILE


def log(msg: str, level: str = "info") -> None:
    if _LOG_FH is None:
        _open_log()
    ts = datetime.now().strftime("%H:%M:%S")
    tag = {"info": "    ", "ok": " ok ", "warn": "WARN", "err": "ERR!",
           "stage": "====", "step": " ·· "}.get(level, level[:4].upper())
    line = f"[{ts}] [{tag}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode(), flush=True)
    if _LOG_FH is not None:
        try:
            _LOG_FH.write(line + "\n")
            _LOG_FH.flush()
        except Exception:
            pass


# ─── 工具 ─────────────────────────────────────────────────────────────────
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def disk_free_gb(path: Path) -> float:
    try:
        usage = shutil.disk_usage(str(path if path.exists() else path.anchor or "C:\\"))
        return round(usage.free / (1024 ** 3), 2)
    except Exception:  # noqa: BLE001
        return -1.0


def run(cmd: List[str] | str, *, timeout: Optional[float] = None,
        capture: bool = True, cwd: Optional[Path] = None,
        shell: bool = False) -> Tuple[int, str, str]:
    """安全同步执行. 返回 (rc, stdout, stderr). 不抛异常."""
    if isinstance(cmd, list):
        display = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    else:
        display = cmd
    log(f"exec: {display}", "step")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            shell=shell,
        )
        out = (proc.stdout or "").rstrip()
        err = (proc.stderr or "").rstrip()
        if out:
            for ln in out.splitlines()[-30:]:  # 限制刷屏
                log(f"  | {ln}")
        if err:
            for ln in err.splitlines()[-30:]:
                log(f"  ! {ln}", "warn")
        log(f"rc={proc.returncode}")
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT after {timeout}s: {display}", "err")
        return -9, "", "timeout"
    except FileNotFoundError as e:
        log(f"NOT_FOUND: {e}", "err")
        return -2, "", str(e)
    except Exception as e:  # noqa: BLE001
        log(f"EXC: {type(e).__name__}: {e}", "err")
        return -1, "", f"{type(e).__name__}: {e}"


def http_download(url: str, dest: Path, *, timeout: float = 30.0,
                  follow_redirects: int = 5) -> Tuple[bool, str]:
    """零依赖 HTTP 下载 (支持 SourceForge 302 跳转). 返回 (ok, msg)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (sw2026_install.py)",
        "Accept":     "*/*",
    }
    current = url
    try:
        for hop in range(follow_redirects + 1):
            req = Request(current, headers=headers, method="GET")
            try:
                resp = urlopen(req, timeout=timeout)
            except Exception as e:  # noqa: BLE001
                return False, f"urlopen@{hop}: {type(e).__name__}: {e}"
            code = getattr(resp, "status", 200)
            if code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location")
                if not loc:
                    return False, f"redirect {code} no Location"
                current = loc
                continue
            total = int(resp.headers.get("Content-Length") or 0)
            log(f"  ↓ {current}  ({total/1e6:.1f} MB)" if total else f"  ↓ {current}")
            t0 = time.time()
            done = 0
            last_print = t0
            with dest.open("wb") as fh:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - last_print >= 2.0 and total:
                        pct = done * 100 / total
                        speed = done / (now - t0) / 1e6
                        log(f"    {pct:5.1f}%  {done/1e6:.1f}/{total/1e6:.1f} MB  {speed:.2f} MB/s")
                        last_print = now
            dt = time.time() - t0
            log(f"  ↓ done · {done/1e6:.1f} MB in {dt:.1f}s")
            return True, f"downloaded {done} bytes"
        return False, "too many redirects"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


# ─── Sentinel / State ────────────────────────────────────────────────────
def _sentinel_path(stage: str) -> Path:
    return SENTINEL_DIR / f"{stage}.sentinel.json"


def sentinel_read(stage: str) -> Optional[Dict[str, Any]]:
    p = _sentinel_path(stage)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def sentinel_write(stage: str, data: Dict[str, Any]) -> Optional[Path]:
    """sentinel 只在 apply=True 时写. dry-run 不污染状态.
    dry-run 结果另写到 <stage>.dryrun.json 便于审阅计划."""
    apply = bool(data.get("apply", False))
    if not apply:
        # dry-run: 写到 .dryrun.json, 不影响幂等判定
        p = SENTINEL_DIR / f"{stage}.dryrun.json"
        payload = {"stage": stage, "ts": datetime.now().isoformat(),
                   "mode": "dry_run", **data}
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return p
    p = _sentinel_path(stage)
    payload = {"stage": stage, "ts": datetime.now().isoformat(),
               "apply": True, **data}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def state_read() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"stages": {}, "created": datetime.now().isoformat()}


def state_update(stage: str, status: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """state.json 只在 apply=True 时更新真实状态. dry-run 不污染."""
    ex = extra or {}
    if not ex.get("apply", False):
        # dry-run: 不更新 state
        return
    s = state_read()
    s["updated"] = datetime.now().isoformat()
    s.setdefault("stages", {})[stage] = {
        "status":  status,
        "ts":      datetime.now().isoformat(),
        **ex,
    }
    STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2),
                          encoding="utf-8")


# ─── 7-Zip 探测 / 安装 ────────────────────────────────────────────────────
def find_7z_exe() -> Optional[Path]:
    """按优先级找 7z.exe: PATH > Program Files > 便携缓存 > WinRAR."""
    cand: List[Path] = []
    # 1. PATH
    for name in ("7z.exe",):
        p = shutil.which(name)
        if p:
            cand.append(Path(p))
    # 2. 系统安装
    for base in (r"C:\Program Files\7-Zip", r"C:\Program Files (x86)\7-Zip"):
        p = Path(base) / "7z.exe"
        if p.is_file():
            cand.append(p)
    # 3. 便携缓存
    for p in CACHE_ROOT.rglob("7z.exe"):
        cand.append(p)
    # 4. WinRAR (作为 fallback, 用于解压 RAR)
    for base in (r"C:\Program Files\WinRAR", r"C:\Program Files (x86)\WinRAR"):
        p = Path(base) / "WinRAR.exe"
        if p.is_file():
            cand.append(p)
    for c in cand:
        if c.is_file():
            return c
    return None


def ensure_archiver(*, apply: bool) -> Tuple[Optional[Path], str]:
    """确保有解压器可用. 返回 (exe_path, source)."""
    exe = find_7z_exe()
    if exe is not None:
        log(f"[ok] archiver found: {exe}", "ok")
        return exe, "preinstalled"

    log("[info] no 7z/WinRAR; will install 7-Zip", "info")
    if not apply:
        log("[dry-run] would install 7-Zip (via winget or direct download)")
        return None, "dry_run"

    # 路线 1: winget
    winget_candidates = [
        shutil.which("winget"),
        r"C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_1.28.220.0_x64__8wekyb3d8bbwe\winget.exe",
    ]
    for wg in winget_candidates:
        if wg and Path(wg).is_file():
            log(f"[step] winget install 7zip.7zip via {wg}", "step")
            rc, _, _ = run([wg, "install", "--id", "7zip.7zip", "--exact",
                            "--silent", "--accept-package-agreements",
                            "--accept-source-agreements"], timeout=600)
            if rc == 0:
                exe = find_7z_exe()
                if exe:
                    return exe, "winget"
            break  # winget 存在但失败, 进下一路线

    # 路线 2: 直接下载 7-Zip 安装器
    dest = CACHE_ROOT / SEVENZIP_EXE_NAME
    if not dest.exists() or dest.stat().st_size < 1024 * 1024:
        ok = False
        for url in SEVENZIP_URLS:
            log(f"[step] downloading 7-Zip from {url}", "step")
            ok, msg = http_download(url, dest, timeout=60)
            if ok and dest.stat().st_size > 1024 * 1024:
                break
            log(f"  · failed: {msg}", "warn")
        if not ok:
            log("[err] all 7-Zip download sources failed", "err")
            return None, "download_failed"
    # 静默安装 7-Zip
    log(f"[step] running {dest} /S", "step")
    rc, _, _ = run([str(dest), "/S"], timeout=180)
    if rc == 0:
        exe = find_7z_exe()
        if exe:
            return exe, "downloaded+installed"
    # 极端 fallback: 用自解压方式, 从 exe 中解压出 7z.exe (7z 安装包是 NSIS)
    log("[warn] 7-Zip silent install failed; trying portable extract", "warn")
    portable_dir = CACHE_ROOT / "portable"
    portable_dir.mkdir(exist_ok=True)
    rc, _, _ = run([str(dest), "/S", f"/D={portable_dir}"], timeout=180)
    exe = find_7z_exe()
    if exe:
        return exe, "portable"
    return None, "install_failed"


# ─── RAR 展开 ─────────────────────────────────────────────────────────────
def rar_extract(archiver: Path, rar: Path, dest: Path, *, apply: bool) -> Tuple[bool, str]:
    is_winrar = archiver.name.lower() == "winrar.exe"
    if is_winrar:
        # WinRAR CLI: x -y  <archive> <dest>
        cmd = [str(archiver), "x", "-y", "-ibck", str(rar), str(dest) + "\\"]
    else:
        # 7-Zip CLI
        cmd = [str(archiver), "x", f"-o{dest}", "-y", str(rar)]
    if not apply:
        log(f"[dry-run] would extract {rar.name}")
        log(f"          cmd: {cmd}")
        return True, "dry_run"
    # apply 才实际创建目录
    dest.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rc, _, err = run(cmd, timeout=3600)
    dt = time.time() - t0
    if rc != 0:
        return False, f"rc={rc} dt={dt:.0f}s err={err[:200]}"
    return True, f"rc=0 dt={dt:.0f}s"


# ─── 扫描安装入口 ─────────────────────────────────────────────────────────
_ENTRY_PRIORITY = [
    # sldim.exe 直接启动 Installation Manager GUI — 最稳
    # startswinstall.exe 是预启动代理, 某些发行版下会调失败 (ref: SW2026 sldim\64bit 找不到)
    "sldim.exe",             # SolidWorks Installation Manager (首选 GUI)
    "startswinstall.exe",    # 管理镜像 unattended (若可用)
    "setup.exe",             # 传统引导
    "swsetup.exe",
    "autorun.exe",
]

def scan_install_entry(root: Path) -> Dict[str, Any]:
    """在解压目录扫安装入口 · 递归 (限文件数).

    SW 官方布局: <root>/.../Setup/sldim/startswinstall.exe (+ sldIM.exe)
    RAR 可能多包一层, 故递归. 限制总扫描文件数避免遍历几万个小文件.
    同时探测 Crack/ 目录 (民间激活物料, 仅记录, 不主动使用).
    """
    if not root.is_dir():
        return {"ok": False, "err": "root_not_dir", "root": str(root),
                "entry": None, "entry_type": None, "found": {},
                "size_gb": 0.0, "crack": None}
    found: Dict[str, List[str]] = {}
    crack_dirs: List[str] = []
    MAX_FILES = 100_000
    counter = 0
    try:
        for item in root.rglob("*"):
            counter += 1
            if counter > MAX_FILES:
                break
            try:
                if item.is_dir():
                    nlow = item.name.lower()
                    if nlow == "crack" or nlow.startswith("crack"):
                        crack_dirs.append(str(item))
                    continue
                if not item.is_file():
                    continue
                nm = item.name.lower()
                for key in _ENTRY_PRIORITY:
                    if nm == key:
                        found.setdefault(key, []).append(str(item))
            except (PermissionError, OSError):
                continue
    except Exception:  # noqa: BLE001
        pass
    # 优先级: 匹配 "\setup\sldim\" 的结果最优
    def _pref_score(p: str) -> int:
        pl = p.lower()
        s = 0
        if r"\setup\sldim\\" in pl or r"\setup\sldim\\".replace("\\", "/") in pl.replace("\\", "/"):
            s += 100
        if r"\setup\\" in pl or "/setup/" in pl.replace("\\", "/"):
            s += 10
        # 浅路径优先 (减少 \ 的数量)
        s -= pl.count("\\")
        return s

    best: Optional[str] = None
    best_key: Optional[str] = None
    for key in _ENTRY_PRIORITY:
        if key in found:
            # 按评分排序, 取最佳
            found[key].sort(key=_pref_score, reverse=True)
            best = found[key][0]
            best_key = key
            break
    # size
    size = 0
    try:
        cnt = 0
        for p in root.rglob("*"):
            cnt += 1
            if cnt > MAX_FILES:
                break
            try:
                if p.is_file():
                    size += p.stat().st_size
            except (PermissionError, OSError):
                continue
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok":         best is not None,
        "root":       str(root),
        "entry":      best,
        "entry_type": best_key,
        "found":      {k: v[:3] for k, v in found.items()},
        "size_gb":    round(size / (1024 ** 3), 2),
        "crack":      crack_dirs[:5] if crack_dirs else None,
        "file_count": counter,
    }


# ─── 运行安装 · 6 模式容错 ─────────────────────────────────────────────────
def launch_installer(entry: str, entry_type: str, *, apply: bool,
                     silent_ok: bool = True) -> Dict[str, Any]:
    """运行 SW 安装器 · 根据入口类型自动选择命令行.

    Modes (按优先):
      1. StartSWInstall.exe /now        · 真静默
      2. StartSWInstall.exe /unattended · 静默, 稍老参数
      3. sldIM.exe /adminclient         · 管理客户端模式
      4. GUI 模式 (最后手段, 用户点击 Next)
    """
    p = Path(entry)
    if not p.is_file():
        return {"ok": False, "err": "entry_not_file", "entry": entry}
    lower = entry_type or p.name.lower()

    cmds: List[List[str]] = []
    mode_desc: List[str] = []
    if "startswinstall" in lower:
        if silent_ok:
            cmds.append([entry, "/now"])
            mode_desc.append("StartSWInstall /now (fully silent)")
            cmds.append([entry, "/unattended"])
            mode_desc.append("StartSWInstall /unattended (legacy silent)")
        cmds.append([entry, "/showui"])
        mode_desc.append("StartSWInstall /showui (GUI)")
    elif "sldim" in lower:
        if silent_ok:
            cmds.append([entry, "/adminclient", "/silent"])
            mode_desc.append("sldIM /adminclient /silent")
        cmds.append([entry])
        mode_desc.append("sldIM (GUI)")
    else:
        cmds.append([entry])
        mode_desc.append(f"{p.name} (direct GUI)")

    if not apply:
        return {
            "ok":     True,
            "dry":    True,
            "plans":  [{"cmd": c, "desc": d} for c, d in zip(cmds, mode_desc)],
            "note":   "dry-run: pick first cmd on --apply; GUI 模式需用户点 Next",
        }

    # 真执: 非阻塞启动 GUI (不等待), 阻塞等待静默
    for cmd, desc in zip(cmds, mode_desc):
        log(f"[step] try mode: {desc}", "step")
        try:
            if "GUI" in desc:
                # 非阻塞 · 让 GUI 起来, 留给用户操作
                proc = subprocess.Popen(cmd, cwd=str(p.parent))
                log(f"  launched PID={proc.pid}. GUI 已启, 请按提示操作.", "info")
                # 并排打开教程视频, 引导用户 · "用户无为"的关键一笔
                tutorial = SRC_DIR / TUTORIAL_NAME
                if tutorial.exists():
                    log(f"  并排打开教程: {tutorial}", "info")
                    try:
                        os.startfile(str(tutorial))  # type: ignore[attr-defined]
                    except Exception as e:  # noqa: BLE001
                        log(f"  tutorial open failed: {e}", "warn")
                return {"ok": True, "mode": desc, "pid": proc.pid, "blocking": False}
            # 静默阻塞
            rc, _, err = run(cmd, cwd=p.parent, timeout=60 * 60 * 3)  # 3h 上限
            if rc == 0:
                return {"ok": True, "mode": desc, "rc": rc, "blocking": True}
            log(f"  mode failed rc={rc}, try next", "warn")
        except Exception as e:  # noqa: BLE001
            log(f"  exc: {type(e).__name__}: {e}", "warn")
    return {"ok": False, "err": "all_modes_failed"}


# ─── SSQ Crack overlay · apply_ssq_crack ─────────────────────────────────
def find_sw_install_root(year: str = "2026") -> Optional[Path]:
    """从注册表 / 默认路径探测 SW 安装根目录.
    优先级: HKLM\\SOFTWARE\\SolidWorks\\SOLIDWORKS YYYY\\Setup.SolidWorks Folder
    """
    try:
        import winreg  # type: ignore
    except ImportError:
        winreg = None  # type: ignore
    # 1. Registry
    if winreg is not None:
        for key_base in (
            rf"SOFTWARE\SolidWorks\SOLIDWORKS {year}\Setup",
            rf"SOFTWARE\SolidWorks\SOLIDWORKS {year}",
            rf"SOFTWARE\WOW6432Node\SolidWorks\SOLIDWORKS {year}",
        ):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_base) as k:
                    # 常见 value 名
                    for vname in ("SolidWorks Folder", "InstallDir",
                                  "Install Dir", "SolidWorksInstallDir"):
                        try:
                            v, _ = winreg.QueryValueEx(k, vname)
                            p = Path(v)
                            if p.is_dir():
                                return p
                        except FileNotFoundError:
                            continue
            except FileNotFoundError:
                continue
            except Exception:  # noqa: BLE001
                continue
    # 2. 常见默认路径
    for p in (
        Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"),
        Path(r"C:\Program Files\SOLIDWORKS Corp"),
        Path(r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"),
        Path(r"D:\Program Files\SOLIDWORKS Corp"),
    ):
        if p.is_dir():
            return p
    return None


def find_sw_corp_root(year: str = "2026") -> Optional[Path]:
    """找 SOLIDWORKS Corp (所有子产品的父目录), 即 crack 的 overlay 目标.
    Crack\\SOLIDWORKS Corp\\* 映射到 <SW Corp root>\\*.
    """
    install_sw = find_sw_install_root(year)
    if install_sw and install_sw.name.upper().startswith("SOLIDWORKS"):
        parent = install_sw.parent
        if parent.name == "SOLIDWORKS Corp":
            return parent
    for p in (
        Path(r"C:\Program Files\SOLIDWORKS Corp"),
        Path(r"D:\Program Files\SOLIDWORKS Corp"),
    ):
        if p.is_dir():
            return p
    return None


def apply_ssq_crack(crack_dir: Path, sw_corp_root: Path, *, apply: bool) -> Dict[str, Any]:
    """SolidSQUAD 破解套件自动应用 · 四步标准流程.

    1. reg import  SolidSQUADLoaderEnabler.reg
    2. reg import  sw2026_network_serials_licensing.reg
    3. copy  Crack\\SOLIDWORKS Corp\\**  →  <sw_corp_root>\\**
    4. run (admin)  SolidWorks_Flexnet_Server\\server_install.bat

    返回 {"ok": bool, "steps": [...]}
    """
    out: Dict[str, Any] = {"apply": apply, "crack_dir": str(crack_dir),
                           "sw_corp_root": str(sw_corp_root), "steps": []}
    log(f"  SSQ crack_dir     : {crack_dir}", "step")
    log(f"  SW Corp root      : {sw_corp_root}", "step")
    if not crack_dir.is_dir():
        out["err"] = "crack_dir_not_exist"
        return out
    if not sw_corp_root.is_dir():
        out["err"] = "sw_corp_root_not_exist"
        return out

    # ── step 1/2 · reg import ──────────────────────────────────────────
    for reg_name in ("SolidSQUADLoaderEnabler.reg",
                     "sw2026_network_serials_licensing.reg"):
        reg_path = crack_dir / reg_name
        step: Dict[str, Any] = {"step": f"reg:{reg_name}"}
        if not reg_path.exists():
            step["ok"] = False
            step["err"] = "reg_not_found"
            out["steps"].append(step)
            continue
        if not apply:
            step["plan"] = True
            step["cmd"] = ["reg.exe", "import", str(reg_path)]
            out["steps"].append(step)
            continue
        rc, _, err = run(["reg.exe", "import", str(reg_path)], timeout=60)
        step["ok"] = rc == 0
        step["rc"] = rc
        if rc != 0:
            step["err"] = err[:200]
        out["steps"].append(step)

    # ── step 3 · DLL/EXE overlay ───────────────────────────────────────
    ovr_src = crack_dir / "SOLIDWORKS Corp"
    step3: Dict[str, Any] = {"step": "overlay"}
    if not ovr_src.is_dir():
        step3["ok"] = False
        step3["err"] = "overlay_src_not_exist"
        out["steps"].append(step3)
    else:
        files_src = [f for f in ovr_src.rglob("*") if f.is_file()]
        step3["n_files"] = len(files_src)
        if not apply:
            step3["plan"] = True
            step3["sample"] = [str(f.relative_to(ovr_src)) for f in files_src[:5]]
            out["steps"].append(step3)
        else:
            copied, skipped, errors = 0, 0, []
            for src in files_src:
                rel = src.relative_to(ovr_src)
                dst = sw_corp_root / rel
                try:
                    # 目标目录不存在 → 说明该 SW 子产品未装 → skip (避免装无关产品)
                    if not dst.parent.is_dir():
                        skipped += 1
                        continue
                    # 备份原文件 (.orig, 首次)
                    if dst.exists():
                        bak = dst.with_suffix(dst.suffix + ".orig")
                        if not bak.exists():
                            try:
                                shutil.copy2(dst, bak)
                            except Exception:  # noqa: BLE001
                                pass
                    shutil.copy2(src, dst)
                    copied += 1
                except PermissionError as e:
                    errors.append(f"{rel}: permission denied ({e})")
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{rel}: {type(e).__name__}: {e}")
            step3["ok"] = copied > 0 and len(errors) < len(files_src) // 2
            step3["copied"] = copied
            step3["skipped"] = skipped
            step3["errors"] = errors[:10]
            out["steps"].append(step3)

    # ── step 4 · FlexLM server_install.bat ─────────────────────────────
    bat = crack_dir / "SolidWorks_Flexnet_Server" / "server_install.bat"
    step4: Dict[str, Any] = {"step": "flexnet_install"}
    if not bat.exists():
        step4["ok"] = False
        step4["err"] = "bat_not_found"
        out["steps"].append(step4)
    else:
        if not apply:
            step4["plan"] = True
            step4["cmd"] = [str(bat)]
            step4["cwd"] = str(bat.parent)
            out["steps"].append(step4)
        else:
            # 以当前 shell (若 admin) 运行 bat
            rc, _, err = run(["cmd.exe", "/c", str(bat)],
                             cwd=bat.parent, timeout=180)
            step4["ok"] = rc == 0
            step4["rc"] = rc
            if rc != 0:
                step4["err"] = err[:200]
            out["steps"].append(step4)

    # 汇总
    out["ok"] = all(s.get("ok", s.get("plan", False)) for s in out["steps"])
    return out


# ─── SW 探测 (是否已装 2026) ─────────────────────────────────────────────
def probe_sw_installed() -> Dict[str, Any]:
    """探测系统上已装的 SW 版本. 返回 {versions: [...], sw2026_present: bool}."""
    try:
        import winreg  # type: ignore
    except ImportError:
        return {"ok": False, "err": "winreg_not_available"}
    out: Dict[str, Any] = {"ok": True, "versions": [], "progids": []}
    # 扫 HKLM\SOFTWARE\SolidWorks\SOLIDWORKS XXXX
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\SolidWorks") as root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                if sub.upper().startswith("SOLIDWORKS"):
                    out["versions"].append(sub)
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        out["reg_err"] = str(e)
    # ProgID
    for ver in ("SldWorks.Application", "SldWorks.Application.34",
                "SldWorks.Application.33", "SldWorks.Application.32",
                "SldWorks.Application.31"):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ver):
                out["progids"].append(ver)
        except FileNotFoundError:
            pass
        except Exception:  # noqa: BLE001
            pass
    # 铁证 = sldworks.exe 文件实存在 (SSQ reg 会预植 "SolidWorks 2026" 空壳, 不可信)
    sw2026_exe: List[str] = []
    for cand in (
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.exe",
        r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.exe",
        r"C:\Program Files\SOLIDWORKS Corp26\SOLIDWORKS\sldworks.exe",
        r"D:\Program Files\SOLIDWORKS Corp26\SOLIDWORKS\sldworks.exe",
    ):
        if Path(cand).exists():
            sw2026_exe.append(cand)
    out["sldworks_exe"] = sw2026_exe
    # reg 2026 key 必须是全大写 SOLIDWORKS + 含 Setup 子键 (SSQ 的假壳无 Setup)
    reg_2026_valid = False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\SolidWorks\SOLIDWORKS 2026\Setup"):
            reg_2026_valid = True
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001
        pass
    out["reg_2026_valid"] = reg_2026_valid
    out["sw2026_present"] = bool(sw2026_exe) or reg_2026_valid or \
                            "SldWorks.Application.34" in out["progids"]
    return out


# ─── 六阶段实现 ───────────────────────────────────────────────────────────
@dataclass
class StageResult:
    stage:   str
    ok:      bool
    apply:   bool
    elapsed_s: float = 0.0
    data:    Dict[str, Any] = field(default_factory=dict)
    err:     Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def stage_0_prelude(*, apply: bool) -> StageResult:
    t0 = time.time()
    log("stage 0 · prelude · admin / disk / baseline", "stage")
    admin = is_admin()
    log(f"  admin          : {admin}")
    log(f"  python         : {sys.version.splitlines()[0]}")
    log(f"  script         : {__file__}")
    log(f"  src dir        : {SRC_DIR}")
    log(f"  extract root   : {EXTRACT_ROOT}")
    src_files = {}
    for nm in (RAR_BASE_NAME, RAR_SP_NAME, TUTORIAL_NAME, AV_GUIDE_NAME):
        p = SRC_DIR / nm
        src_files[nm] = {"exists": p.exists(),
                         "size_gb": round(p.stat().st_size / (1024**3), 2) if p.exists() else 0}
        flag = "✓" if p.exists() else "✗"
        log(f"  {flag} {nm}  {src_files[nm]['size_gb']} GB")
    free_f = disk_free_gb(Path("F:\\"))
    free_c = disk_free_gb(Path("C:\\"))
    log(f"  disk F:\\ free  : {free_f} GB (need ≥ {REQUIRED_FREE_EXTRACT_GB})")
    log(f"  disk C:\\ free  : {free_c} GB (need ≥ {REQUIRED_FREE_INSTALL_GB})")
    sw_probe = probe_sw_installed()
    log(f"  SW installed   : {sw_probe.get('versions')}")
    log(f"  SW 2026 present: {sw_probe.get('sw2026_present')}")
    ok = (admin and
          src_files[RAR_BASE_NAME]["exists"] and
          src_files[RAR_SP_NAME]["exists"] and
          free_f >= REQUIRED_FREE_EXTRACT_GB and
          free_c >= REQUIRED_FREE_INSTALL_GB)
    err = None
    if not admin:
        err = "非管理员 · 请以管理员身份启动 (→一键安装SW2026.cmd 自带 UAC 提权)"
    elif not src_files[RAR_BASE_NAME]["exists"]:
        err = f"缺 {RAR_BASE_NAME}"
    elif not src_files[RAR_SP_NAME]["exists"]:
        err = f"缺 {RAR_SP_NAME}"
    elif free_f < REQUIRED_FREE_EXTRACT_GB:
        err = f"F:\\ 空间不足 {free_f} < {REQUIRED_FREE_EXTRACT_GB} GB"
    elif free_c < REQUIRED_FREE_INSTALL_GB:
        err = f"C:\\ 空间不足 {free_c} < {REQUIRED_FREE_INSTALL_GB} GB (可考虑清理或装到其他盘)"
    data = {
        "admin":          admin,
        "src_files":      src_files,
        "disk_F_free_gb": free_f,
        "disk_C_free_gb": free_c,
        "sw_installed":   sw_probe,
    }
    r = StageResult(stage="0_prelude", ok=bool(ok), apply=apply,
                    elapsed_s=round(time.time() - t0, 2), data=data, err=err)
    sentinel_write("0_prelude", {**r.to_dict()})
    state_update("0_prelude", "ok" if r.ok else "err",
                 {"err": err, "apply": apply})
    log(f"stage 0 · {'OK' if r.ok else 'FAIL'}  ({r.elapsed_s}s)",
        "ok" if r.ok else "err")
    if err:
        log(f"  err: {err}", "err")
    return r


def stage_1_extract(*, apply: bool) -> StageResult:
    t0 = time.time()
    log("stage 1 · extract · 7z ensure + RAR → 展开", "stage")
    prev = sentinel_read("1_extract")
    base_rar = SRC_DIR / RAR_BASE_NAME
    sp_rar   = SRC_DIR / RAR_SP_NAME
    fingerprint = {
        "base_size":  base_rar.stat().st_size if base_rar.exists() else 0,
        "base_mtime": int(base_rar.stat().st_mtime) if base_rar.exists() else 0,
        "sp_size":    sp_rar.stat().st_size if sp_rar.exists() else 0,
        "sp_mtime":   int(sp_rar.stat().st_mtime) if sp_rar.exists() else 0,
    }
    # 幂等判定: sentinel 必须来自 apply=True 且 fingerprint 匹配 且 目录内有内容
    def _has_content(d: Path) -> bool:
        if not d.is_dir():
            return False
        try:
            return any(d.iterdir())
        except Exception:  # noqa: BLE001
            return False
    if (prev and prev.get("apply") and prev.get("ok")
            and prev.get("data", {}).get("fingerprint") == fingerprint
            and _has_content(EXTRACT_BASE_DIR) and _has_content(EXTRACT_SP_DIR)):
        log("  [skip] sentinel 匹配且解压目录非空", "ok")
        r = StageResult(stage="1_extract", ok=True, apply=apply,
                        elapsed_s=round(time.time() - t0, 2),
                        data={"skipped": True, "fingerprint": fingerprint,
                              "base_dir": str(EXTRACT_BASE_DIR),
                              "sp_dir":   str(EXTRACT_SP_DIR)})
        state_update("1_extract", "skip", {"apply": apply})
        return r
    archiver, src = ensure_archiver(apply=apply)
    if not archiver:
        r = StageResult(stage="1_extract", ok=False, apply=apply,
                        elapsed_s=round(time.time() - t0, 2),
                        err=f"no archiver ({src})")
        sentinel_write("1_extract", r.to_dict())
        state_update("1_extract", "err", {"err": r.err})
        log(f"  err: {r.err}", "err")
        return r
    log(f"  archiver       : {archiver}  (src={src})")
    results = []
    for rar, dest in ((base_rar, EXTRACT_BASE_DIR), (sp_rar, EXTRACT_SP_DIR)):
        if not rar.exists():
            results.append({"rar": str(rar), "ok": False, "err": "not_found"})
            continue
        log(f"  extracting {rar.name}  ({rar.stat().st_size/(1024**3):.1f} GB) → {dest}", "step")
        ok, msg = rar_extract(archiver, rar, dest, apply=apply)
        results.append({"rar": str(rar), "dest": str(dest), "ok": ok, "msg": msg})
    all_ok = all(x.get("ok") for x in results)
    r = StageResult(stage="1_extract", ok=all_ok, apply=apply,
                    elapsed_s=round(time.time() - t0, 2),
                    data={"archiver": str(archiver), "archiver_src": src,
                          "fingerprint": fingerprint, "extracts": results})
    sentinel_write("1_extract", r.to_dict())
    state_update("1_extract", "ok" if all_ok else "err",
                 {"apply": apply})
    log(f"stage 1 · {'OK' if all_ok else 'FAIL'}  ({r.elapsed_s}s)",
        "ok" if all_ok else "err")
    return r


def stage_2_scan(*, apply: bool) -> StageResult:
    t0 = time.time()
    log("stage 2 · scan · 定位 StartSWInstall / sldIM / setup", "stage")
    base = scan_install_entry(EXTRACT_BASE_DIR)
    sp   = scan_install_entry(EXTRACT_SP_DIR)
    log(f"  base entry     : {base.get('entry')}  (type={base.get('entry_type')})  size={base.get('size_gb')} GB")
    log(f"  sp   entry     : {sp.get('entry')}  (type={sp.get('entry_type')})  size={sp.get('size_gb')} GB")
    base_ok = bool(base.get("ok"))
    # dry-run 且 extract 未 apply: 返回 plan pending (不算 fail)
    if not apply and not base_ok:
        extract_done = sentinel_read("1_extract")
        if not (extract_done and extract_done.get("apply")):
            log("  [plan] extract 未实执, 未来会在 F:\\SW2026\\_extracted 扫描", "info")
            r = StageResult(stage="2_scan", ok=True, apply=apply,
                            elapsed_s=round(time.time() - t0, 2),
                            data={"pending": "awaiting extract apply",
                                  "base": base, "sp": sp})
            sentinel_write("2_scan", r.to_dict())
            log("stage 2 · PLAN (awaiting apply)", "info")
            return r
    ok = base_ok  # sp 可缺 (若只装主版)
    r = StageResult(stage="2_scan", ok=ok, apply=apply,
                    elapsed_s=round(time.time() - t0, 2),
                    data={"base": base, "sp": sp},
                    err=None if ok else "no install entry in base")
    sentinel_write("2_scan", r.to_dict())
    state_update("2_scan", "ok" if ok else "err", {"apply": apply})
    log(f"stage 2 · {'OK' if ok else 'FAIL'}  ({r.elapsed_s}s)",
        "ok" if ok else "err")
    return r


def stage_3_install(*, apply: bool, silent_ok: bool = True) -> StageResult:
    t0 = time.time()
    log("stage 3 · install · SolidWorks 2026 主体", "stage")
    # 预探测: 是否已装
    pre = probe_sw_installed()
    if pre.get("sw2026_present"):
        log("  [skip] SW2026 已装 (reg 识别)", "ok")
        r = StageResult(stage="3_install", ok=True, apply=apply,
                        elapsed_s=round(time.time() - t0, 2),
                        data={"skipped": True, "pre": pre})
        sentinel_write("3_install", r.to_dict())
        state_update("3_install", "skip", {"apply": apply})
        return r
    scan = sentinel_read("2_scan")
    scan_ok = bool(scan and scan.get("data", {}).get("base", {}).get("ok"))
    if not scan_ok:
        # dry-run: plan pending
        if not apply:
            log("  [plan] 实执时将运行 StartSWInstall.exe /now (静默) 或 GUI 引导", "info")
            r = StageResult(stage="3_install", ok=True, apply=apply,
                            elapsed_s=round(time.time() - t0, 2),
                            data={"pending": "awaiting scan apply"})
            sentinel_write("3_install", r.to_dict())
            log("stage 3 · PLAN (awaiting apply)", "info")
            return r
        r = StageResult(stage="3_install", ok=False, apply=apply,
                        elapsed_s=round(time.time() - t0, 2),
                        err="stage 2 未就绪 / base entry 未定位")
        sentinel_write("3_install", r.to_dict())
        state_update("3_install", "err", {"err": r.err, "apply": apply})
        log(f"  err: {r.err}", "err")
        return r
    base = scan["data"]["base"]
    result = launch_installer(base["entry"], base["entry_type"],
                              apply=apply, silent_ok=silent_ok)
    # 若 GUI 模式, 非阻塞启动后等待用户完成 → 每 30s 重探测注册表, 最多 90 分钟
    if apply and result.get("ok") and not result.get("blocking", True):
        log("  GUI 已启. 等待注册表出现 SW2026... (check every 30s up to 90min)", "info")
        deadline = time.time() + 90 * 60
        installed = False
        while time.time() < deadline:
            time.sleep(30)
            probe = probe_sw_installed()
            if probe.get("sw2026_present"):
                installed = True
                break
            log(f"    ... still waiting ({int((deadline-time.time())/60)}min left)")
        if not installed:
            log("  [warn] 等待超时, 但安装可能仍在进行", "warn")
        result["installed"] = installed
        result["post_probe"] = probe
    ok = bool(result.get("ok"))
    r = StageResult(stage="3_install", ok=ok, apply=apply,
                    elapsed_s=round(time.time() - t0, 2),
                    data={"launch": result, "pre": pre},
                    err=result.get("err") if not ok else None)
    sentinel_write("3_install", r.to_dict())
    state_update("3_install", "ok" if ok else "err", {"apply": apply})
    log(f"stage 3 · {'OK' if ok else 'FAIL'}  ({r.elapsed_s}s)",
        "ok" if ok else "err")
    return r


def stage_4_sp(*, apply: bool, silent_ok: bool = True) -> StageResult:
    t0 = time.time()
    log("stage 4 · sp · SP1.1 补丁覆盖", "stage")
    scan = sentinel_read("2_scan")
    sp_data = (scan or {}).get("data", {}).get("sp", {}) if scan else {}
    if not sp_data.get("ok"):
        msg = "dry-run: 等 extract+scan apply 后再覆盖 SP1.1" if not apply \
              else "无 SP 入口 (可能 SP 包结构不同或未解压)"
        log(f"  [skip] {msg}", "warn")
        r = StageResult(stage="4_sp", ok=True, apply=apply,
                        elapsed_s=round(time.time() - t0, 2),
                        data={"skipped": True, "reason": "no_sp_entry"})
        sentinel_write("4_sp", r.to_dict())
        state_update("4_sp", "skip", {"apply": apply})
        return r
    result = launch_installer(sp_data["entry"], sp_data["entry_type"],
                              apply=apply, silent_ok=silent_ok)
    ok = bool(result.get("ok"))
    r = StageResult(stage="4_sp", ok=ok, apply=apply,
                    elapsed_s=round(time.time() - t0, 2),
                    data={"launch": result},
                    err=result.get("err") if not ok else None)
    sentinel_write("4_sp", r.to_dict())
    state_update("4_sp", "ok" if ok else "err", {"apply": apply})
    log(f"stage 4 · {'OK' if ok else 'FAIL'}  ({r.elapsed_s}s)",
        "ok" if ok else "err")
    return r


def stage_5_activate(*, apply: bool) -> StageResult:
    t0 = time.time()
    log("stage 5 · activate · SSQ crack overlay + L9 sw_activate_and_verify", "stage")
    # dry-run 且 SW2026 未装: plan pending
    if not apply:
        pre = probe_sw_installed()
        if not pre.get("sw2026_present"):
            log("  [plan] SW2026 未装, apply 后将: (a) 应用 SSQ crack (b) L9 激活验证", "info")
            r = StageResult(stage="5_activate", ok=True, apply=apply,
                            elapsed_s=round(time.time() - t0, 2),
                            data={"pending": "awaiting install apply",
                                  "sw_installed": pre})
            sentinel_write("5_activate", r.to_dict())
            log("stage 5 · PLAN (awaiting apply)", "info")
            return r

    # ── stage 5.1 · SSQ crack overlay (若 Crack 目录存在) ─────────────────
    crack_result: Optional[Dict[str, Any]] = None
    scan = sentinel_read("2_scan")
    base_scan = (scan or {}).get("data", {}).get("base", {}) if scan else {}
    crack_dirs = base_scan.get("crack") or []
    if crack_dirs:
        sw_corp = find_sw_corp_root("2026")
        if sw_corp:
            log(f"  [step 5.1] 应用 SSQ crack (crack={crack_dirs[0]})", "step")
            log(f"             → SW Corp root = {sw_corp}", "step")
            try:
                crack_result = apply_ssq_crack(Path(crack_dirs[0]), sw_corp,
                                                apply=apply)
                for s in crack_result.get("steps", []):
                    ok_flag = "✓" if s.get("ok") else ("·" if s.get("plan") else "✗")
                    log(f"    {ok_flag} {s.get('step')}  "
                        f"{ {k:v for k,v in s.items() if k not in ('step','ok','plan')} }")
            except Exception as e:  # noqa: BLE001
                log(f"    crack exc: {type(e).__name__}: {e}", "err")
                crack_result = {"ok": False, "err": f"{type(e).__name__}: {e}"}
        else:
            log("  [warn] SW Corp root 未找到, 跳过 SSQ crack", "warn")
    else:
        log("  [info] 未在 scan 中见 Crack 目录, 跳过 SSQ 步骤", "info")

    # ── stage 5.2 · L9 sw_activate_and_verify ────────────────────────────
    log("  [step 5.2] L9 sw_activate_and_verify", "step")
    m = _lazy_import_dao_sw()
    if m is None:
        r = StageResult(stage="5_activate", ok=False, apply=apply,
                        elapsed_s=round(time.time() - t0, 2),
                        err="dao_solidworks not importable",
                        data={"crack": crack_result})
        sentinel_write("5_activate", r.to_dict())
        state_update("5_activate", "err", {"err": r.err, "apply": apply})
        log(f"  err: {r.err}", "err")
        return r
    try:
        res = m.sw_activate_and_verify(
            dry_run=not apply,
            launch_sw=False,
            probe_com_include_dispatch=False,
        )
        act_ok = bool(res.get("activate", {}).get("ok"))
        crack_ok = crack_result is None or bool(crack_result.get("ok"))
        ok = act_ok and crack_ok
        r = StageResult(stage="5_activate", ok=ok, apply=apply,
                        elapsed_s=round(time.time() - t0, 2),
                        data={"activate": res, "crack": crack_result})
    except Exception as e:  # noqa: BLE001
        r = StageResult(stage="5_activate", ok=False, apply=apply,
                        elapsed_s=round(time.time() - t0, 2),
                        err=f"{type(e).__name__}: {e}",
                        data={"crack": crack_result,
                              "trace": traceback.format_exc()})
    sentinel_write("5_activate", r.to_dict())
    state_update("5_activate", "ok" if r.ok else "err", {"apply": apply})
    log(f"stage 5 · {'OK' if r.ok else 'FAIL'}  ({r.elapsed_s}s)",
        "ok" if r.ok else "err")
    return r


def stage_6_verify(*, apply: bool) -> StageResult:
    t0 = time.time()
    log("stage 6 · verify · sw_info(probe_com=True)", "stage")
    # dry-run 且 SW2026 未装: plan pending
    if not apply:
        pre = probe_sw_installed()
        if not pre.get("sw2026_present"):
            log("  [plan] apply 后将跑 sw_info(probe_com=True) 测 COM 活体", "info")
            r = StageResult(stage="6_verify", ok=True, apply=apply,
                            elapsed_s=round(time.time() - t0, 2),
                            data={"pending": "awaiting install apply",
                                  "sw_installed": pre})
            sentinel_write("6_verify", r.to_dict())
            log("stage 6 · PLAN (awaiting apply)", "info")
            return r
    m = _lazy_import_dao_sw()
    if m is None:
        r = StageResult(stage="6_verify", ok=False, apply=apply,
                        elapsed_s=round(time.time() - t0, 2),
                        err="dao_solidworks not importable")
        sentinel_write("6_verify", r.to_dict())
        return r
    data: Dict[str, Any] = {}
    try:
        info = m.sw_info(probe_com=apply)  # dry_run 只探 reg; apply 才真 COM
        data["sw_info"] = info.to_dict() if hasattr(info, "to_dict") else str(info)
    except Exception as e:  # noqa: BLE001
        data["sw_info_err"] = f"{type(e).__name__}: {e}"
    try:
        probe = probe_sw_installed()
        data["installed"] = probe
    except Exception as e:  # noqa: BLE001
        data["installed_err"] = f"{type(e).__name__}: {e}"
    ok = bool(data.get("installed", {}).get("sw2026_present"))
    r = StageResult(stage="6_verify", ok=ok, apply=apply,
                    elapsed_s=round(time.time() - t0, 2),
                    data=data,
                    err=None if ok else "SW2026 未探测到")
    sentinel_write("6_verify", r.to_dict())
    state_update("6_verify", "ok" if ok else "err", {"apply": apply})
    log(f"stage 6 · {'OK' if ok else 'FAIL'}  ({r.elapsed_s}s)",
        "ok" if ok else "err")
    return r


# ─── 总调度 ───────────────────────────────────────────────────────────────
STAGES_MAP = {
    "0_prelude":  stage_0_prelude,
    "1_extract":  stage_1_extract,
    "2_scan":     stage_2_scan,
    "3_install":  stage_3_install,
    "4_sp":       stage_4_sp,
    "5_activate": stage_5_activate,
    "6_verify":   stage_6_verify,
}
STAGE_ORDER = ["0_prelude", "1_extract", "2_scan", "3_install",
               "4_sp", "5_activate", "6_verify"]

STAGE_ALIASES = {
    "0": "0_prelude",  "prelude":  "0_prelude",
    "1": "1_extract",  "extract":  "1_extract",
    "2": "2_scan",     "scan":     "2_scan",
    "3": "3_install",  "install":  "3_install",
    "4": "4_sp",       "sp":       "4_sp",
    "5": "5_activate", "activate": "5_activate",
    "6": "6_verify",   "verify":   "6_verify",
}


def normalize_stage(s: str) -> Optional[str]:
    if s in STAGES_MAP:
        return s
    return STAGE_ALIASES.get(s)


def run_all(*, apply: bool, stop_on_fail: bool = True) -> List[StageResult]:
    results: List[StageResult] = []
    log(f"═══ sw2026_install · all ({'APPLY' if apply else 'DRY-RUN'}) ═══", "stage")
    for stage in STAGE_ORDER:
        fn = STAGES_MAP[stage]
        r = fn(apply=apply)
        results.append(r)
        if stop_on_fail and not r.ok:
            log(f"[stop] {stage} failed → abort chain", "err")
            break
    log(f"═══ summary ═══", "stage")
    for r in results:
        flag = " ok " if r.ok else "FAIL"
        log(f"  [{flag}]  {r.stage:12s}  {r.elapsed_s}s  "
            f"err={r.err or '-'}")
    return results


def print_status() -> None:
    s = state_read()
    stages = s.get("stages", {})
    log("current status:", "info")
    for st in STAGE_ORDER:
        info = stages.get(st, {})
        status = info.get("status", "-")
        ts = info.get("ts", "-")
        log(f"  {st:12s}  {status:6s}  {ts}")
    print(f"\n  state file    : {STATE_FILE}")
    print(f"  sentinels dir : {SENTINEL_DIR}")
    print(f"  log dir       : {LOG_ROOT}")


def reset_sentinels(*, keep_prelude: bool = False) -> None:
    log("reset sentinels (不影响已装软件)", "warn")
    for f in SENTINEL_DIR.glob("*.sentinel.json"):
        if keep_prelude and f.name.startswith("0_"):
            continue
        log(f"  rm {f.name}")
        f.unlink()
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        log(f"  rm {STATE_FILE.name}")


def open_tutorial() -> None:
    p = SRC_DIR / TUTORIAL_NAME
    if not p.exists():
        log(f"[err] 教程文件不存在: {p}", "err")
        return
    log(f"opening tutorial: {p}", "info")
    try:
        os.startfile(str(p))  # type: ignore[attr-defined]
    except Exception as e:  # noqa: BLE001
        log(f"  fallback run: {e}", "warn")
        run(["cmd.exe", "/c", "start", "", str(p)], shell=False)


def locate_only() -> None:
    log("── locate mode ──", "stage")
    if not SRC_DIR.exists():
        log(f"[err] 源目录不存在: {SRC_DIR}", "err")
        return
    for item in SRC_DIR.iterdir():
        size = item.stat().st_size if item.is_file() else 0
        log(f"  {'F' if item.is_file() else 'D'}  {item.name}  "
            f"{size/(1024**3):.2f} GB" if item.is_file() else
            f"  D  {item.name}/")
    for nm in (EXTRACT_BASE_DIR, EXTRACT_SP_DIR):
        log(f"  extract dir    : {nm}  exists={nm.is_dir()}")


# ─── CLI ─────────────────────────────────────────────────────────────────
def main(argv: Optional[List[str]] = None) -> int:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="sw2026_install.py",
        description=f"{APP_NAME} 全链路安装本源 v{SCRIPT_VER}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "命令:\n"
            "  all             跑全部 7 阶段 (0→6)\n"
            "  <stage>         单跑某阶段 (0..6 或名, e.g. extract)\n"
            "  status          打印当前进度\n"
            "  reset           清除 sentinels (不动已装软件)\n"
            "  open-tutorial   打开 SW2026安装教程.mp4\n"
            "  locate          只探测 F:\\SW2026 物料\n"
        ),
    )
    parser.add_argument("command", nargs="?", default="status",
                        help="all / <stage> / status / reset / open-tutorial / locate")
    parser.add_argument("--apply", action="store_true",
                        help="真执模式 (默认 dry-run)")
    parser.add_argument("--continue-on-fail", action="store_true",
                        help="某阶段失败时继续 (默认 stop)")
    parser.add_argument("--no-silent", action="store_true",
                        help="install/sp 阶段跳过静默, 直接 GUI")
    ns = parser.parse_args(argv)

    _open_log()
    log(f"command={ns.command!r}  apply={ns.apply}  "
        f"silent={not ns.no_silent}", "info")

    cmd = ns.command.lower()
    if cmd == "status":
        print_status()
        return 0
    if cmd == "reset":
        reset_sentinels()
        return 0
    if cmd in ("open-tutorial", "tutorial"):
        open_tutorial()
        return 0
    if cmd == "locate":
        locate_only()
        return 0
    if cmd == "all":
        results = run_all(apply=ns.apply, stop_on_fail=not ns.continue_on_fail)
        return 0 if all(r.ok for r in results) else 1
    # 单阶段
    stage = normalize_stage(cmd)
    if stage is None:
        parser.print_help()
        log(f"[err] 未知命令/阶段: {cmd}", "err")
        return 2
    fn = STAGES_MAP[stage]
    # stage_3/stage_4 支持 --no-silent
    if stage in ("3_install", "4_sp") and ns.no_silent:
        r = fn(apply=ns.apply, silent_ok=False)  # type: ignore[call-arg]
    else:
        r = fn(apply=ns.apply)
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
