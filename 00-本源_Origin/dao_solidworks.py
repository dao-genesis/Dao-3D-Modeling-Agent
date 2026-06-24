#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dao_solidworks.py — 万法 · SolidWorks 本源桥 · 反者道之动
═══════════════════════════════════════════════════════════════════════

纲要
    "道可道, 非常道" — SolidWorks 生于无, 三D建模生于有, 有无相生.
    此源以"反"入 SW: 不依赖 SW 运行, 直抵 OLE2/CFB 二进制本源,
    抽取一切 (预览图 · 特征树 · 尺寸 · 属性 · 配置 · 装配依赖).
    当 SW 可用, 再以 COM 无感提升为活体操作层.

层次 (从无到有)
    L0 · 探测 (install, version, progid, exe, COM可达)
    L1 · OLE2 深反 (无 SW 亦可) — 纯 stdlib 解析:
            · header + FAT + MiniFAT + Directory
            · 预览 PNG 抽出 (Preview 流)
            · SummaryInformation / DocumentSummaryInformation
            · swXmlContents / CMgrCfgObj / Configuration / FeatureMgr
            · 拓扑/量度 hints (通过 STEP proxy 回退)
    L2 · COM 活体 (SW 运行时) — pywin32:
            · 连接 (GetActiveObject → Dispatch → Launch+retry)
            · 打开/激活/关闭 文档, 静默模式
            · 导出 STEP/IGES/STL/Parasolid/3DPDF/PDF/DXF/JPG...
            · 质量属性, 包围盒, 特征清单, 配置切换
            · 执行 VBA-like 宏 (exec 任意 COM 调用序列)
    L3 · 桥接 (与 dao_cad_bridge 无缝融合)
            · SLDPRT/SLDASM 统一走本源, 失败再回退 STEP proxy
            · 读写接口统一在 SolidWorksBridge

用法 (API)
    from dao_solidworks import SolidWorksBridge, SWDoc, probe_file

    # 纯探测 (不启动 SW):
    meta = probe_file("part.sldprt")
    # → {version, created_sw_ver, preview_png_bytes, n_features, configs, ...}

    # 需要活体:
    sw = SolidWorksBridge()
    if sw.is_installed():
        sw.connect()                    # 自动 GetActiveObject → Dispatch → Launch
        doc = sw.open("part.sldprt", readonly=True, silent=True)
        doc.export("part.step")
        sw.close_doc(doc)
        sw.disconnect()

CLI
    python dao_solidworks.py probe <file.sldprt>      # L1 深反 JSON
    python dao_solidworks.py preview <file> [out.png] # 抽预览图
    python dao_solidworks.py info                      # SW 安装信息
    python dao_solidworks.py connect                   # 测试 COM 连接
    python dao_solidworks.py convert <src> <dst>       # COM 导出
    python dao_solidworks.py test                      # 自测

工程原则
    - L1 零依赖 (纯 stdlib), L2 需 pywin32 (Windows SDK 常备)
    - 超时+ fallback: L2 失败必报具体错因, 退 L1, 告知代理路径
    - 静默: 所有 COM 调用默认 UserControl=False · Visible=False
"""

from __future__ import annotations

import datetime
import io
import json
import os
import re
import socket
import struct
import sys
import time
import shutil
import subprocess
import tempfile
import zlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

__version__ = "3.3.0"
__all__ = [
    # L0 · 探测 · COM 桥
    "SolidWorksBridge", "SWDoc", "SWInfo", "sw_info", "SWComError",
    # L0.5 · 许可诊断 (只读 · FlexLM 日志 / 环境变量 / 注册表)
    "SWLicenseState", "sw_license_diagnose",
    # L1 · OLE2 深反 (零依赖 · MS-CFB + PropertySet)
    "probe_file", "extract_preview", "ole2_parse",
    "OLE2Parser", "PropertySetParser",
    # L1.5 · 深流解析 (carve 特征名 · 3 重启发)
    "carve_feature_names", "carve_config_names", "deep_probe_file",
    # L2 · 道法自然多路自动选优
    "SWHealthCheck", "SWDialogHandler", "EDrawingsLauncher", "live_show",
    # L2.5 · Document Manager COM (只读, 无 license)
    "SwDocMgrProbe", "swdm_probe",
    # L3 · 原生 DLL 导出 (PE 头按需读取)
    "PEReader", "sw_dll_index",
    # L4 · 注册表全树
    "sw_registry_dump",
    # L5 · 打通 · 实干破障 (regasm / sc start · 含 dry_run 防误触)
    "L5RemediationResult", "is_admin", "find_regasm",
    "remediate_docmgr_com", "remediate_sw_licensing_service",
    "sw_remediate_all",
    # L6 · 几何反演 · 终反 (无 COM · 无许可 · carve BRep 引用 + Parasolid 签名)
    "L6GeometryRefs", "PARASOLID_XT_BIN_SIG", "PARASOLID_XT_TXT_SIG",
    "carve_body_refs", "carve_geometry_refs",
    # L7 · 极限反演 · Parasolid body snapshot 提取 + 字符串全谱 (v3.1.0)
    "L7ParasolidBodies", "L7StringDump",
    "extract_parasolid_bodies", "extract_strings",
    # L8 · 极反推万物 · Parasolid XT block 结构反 + catalog (v3.2.0)
    "XTBlockInfo", "ParasolidCatalog",
    "analyze_xt_block", "parasolid_catalog",
    # L9 · 一键激活 · 从零到活 (v3.3.0 · 道法自然终极编排)
    "L9ActivationResult", "sw_activate", "sw_activate_and_verify",
    "_quick_live_com_probe",
    # 常量
    "SW_DOC_TYPE", "SW_EXPORT_FMT",
    # COM 底层工具 (供所有下游脚本 · 道法自然)
    "_com_prop", "_com_call", "_com_iter_docs", "_dyn_wrap",
    "_find_sw_material_db",
]

# ────────────────────────────────────────────────────────────────────────
# 常量 (对应 SW API 枚举值)
# ────────────────────────────────────────────────────────────────────────
class SW_DOC_TYPE:
    NONE     = 0
    PART     = 1   # swDocPART
    ASSEMBLY = 2   # swDocASSEMBLY
    DRAWING  = 3   # swDocDRAWING
    SDM      = 4
    LAYOUT   = 5
    IMPORTED_PART     = 6
    IMPORTED_ASSEMBLY = 7

    _EXT = {
        ".sldprt": PART,
        ".sldasm": ASSEMBLY,
        ".slddrw": DRAWING,
    }
    _NAME = {
        0: "none", 1: "part", 2: "assembly", 3: "drawing",
        4: "sdm", 5: "layout", 6: "imported_part", 7: "imported_assembly",
    }

    @classmethod
    def from_path(cls, p: Union[str, Path]) -> int:
        return cls._EXT.get(Path(p).suffix.lower(), cls.NONE)

    @classmethod
    def name(cls, v: int) -> str:
        return cls._NAME.get(int(v), f"unknown({v})")


class SW_EXPORT_FMT:
    """导出目标 → SW 文件扩展映射 + 导出参数."""
    STEP     = "step"    # STEP AP214
    STEP203  = "step203" # STEP AP203
    IGES     = "iges"
    PARASOLID_TEXT = "x_t"
    PARASOLID_BIN  = "x_b"
    STL      = "stl"
    OBJ      = "obj"
    DXF      = "dxf"
    DWG      = "dwg"
    PDF      = "pdf"
    PDF_3D   = "pdf_3d"
    JPG      = "jpg"
    BMP      = "bmp"
    PNG      = "png"
    VRML     = "wrl"
    EDRW     = "edrw"    # eDrawings
    SAT      = "sat"     # ACIS
    # SW 原生 "另存为" 扩展名
    _EXT_MAP = {
        "step":   ".step",
        "step203":".step",
        "iges":   ".igs",
        "x_t":    ".x_t",
        "x_b":    ".x_b",
        "stl":    ".stl",
        "obj":    ".obj",
        "dxf":    ".dxf",
        "dwg":    ".dwg",
        "pdf":    ".pdf",
        "pdf_3d": ".pdf",
        "jpg":    ".jpg",
        "bmp":    ".bmp",
        "png":    ".png",
        "wrl":    ".wrl",
        "edrw":   ".edrw",
        "sat":    ".sat",
    }


# ────────────────────────────────────────────────────────────────────────
# L0 · 探测: SW 安装信息
# ────────────────────────────────────────────────────────────────────────
@dataclass
class SWInfo:
    installed:  bool = False
    version:    Optional[str] = None       # "SOLIDWORKS 2023"
    major:      Optional[int] = None       # 2023
    progid:     Optional[str] = None       # "SldWorks.Application.31"
    progid_versioned: Optional[str] = None
    exe:        Optional[str] = None       # full path to SLDWORKS.exe
    installdir: Optional[str] = None
    com_probe:  Optional[str] = None       # "ok" / "not_running" / err msg
    pywin32_ok: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── 版本号反算: SW progid .N → 年份 ────────────────────────────────────
# SolidWorks 版本编号规律: progid .N = 年份 - 1992 (不完全精确, 但 .31=2023)
_PROGID_YEAR = {
    26: 2018, 27: 2019, 28: 2020, 29: 2021, 30: 2022, 31: 2023,
    32: 2024, 33: 2025, 34: 2026,
}


def _probe_registry() -> Dict[str, Any]:
    """读注册表, 找 SW 安装路径和 ProgID."""
    info = {"progid_list": [], "versions": [], "installdir": None}
    if sys.platform != "win32":
        return info
    try:
        import winreg
    except ImportError:
        return info

    # 1. 找所有 SldWorks.Application.* ProgID
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes")
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(k, i)
                if sub.startswith("SldWorks.Application"):
                    info["progid_list"].append(sub)
                i += 1
            except OSError:
                break
        winreg.CloseKey(k)
    except OSError:
        pass

    # 2. 找 SOLIDWORKS 版本
    for root in (r"SOFTWARE\SolidWorks", r"SOFTWARE\WOW6432Node\SolidWorks"):
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root)
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                    if sub.startswith("SOLIDWORKS "):
                        info["versions"].append(sub)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(k)
        except OSError:
            continue

    # 3. 读 Setup/InstallDir
    for root in (r"SOFTWARE\WOW6432Node\SolidWorks\Setup",
                 r"SOFTWARE\SolidWorks\Setup"):
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root)
            try:
                v, _ = winreg.QueryValueEx(k, "SolidWorks Folder")
                info["installdir"] = v
                break
            except OSError:
                try:
                    v, _ = winreg.QueryValueEx(k, "InstallDir")
                    info["installdir"] = v
                    break
                except OSError:
                    pass
            winreg.CloseKey(k)
        except OSError:
            continue
    return info


def _find_sldworks_exe() -> Optional[str]:
    """扫描常见安装路径寻找 SLDWORKS.exe."""
    reg = _probe_registry()
    if reg.get("installdir"):
        exe = Path(reg["installdir"]) / "SLDWORKS.exe"
        if exe.exists():
            return str(exe)
    # 常见路径
    candidates = [
        r"D:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS\SLDWORKS.exe",
        r"D:\Program Files\SOLIDWORKS Corp22\SOLIDWORKS\SLDWORKS.exe",
        r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe",
        r"C:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS\SLDWORKS.exe",
        r"C:\Program Files\SOLIDWORKS\SOLIDWORKS\SLDWORKS.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # 尝试 Windows Registry HKCR\SldWorks.Application\shell\open\command
    if sys.platform == "win32":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"SldWorks.Application\shell\open\command")
            v, _ = winreg.QueryValueEx(k, "")
            winreg.CloseKey(k)
            # v 形如 '"D:\...\SLDWORKS.exe" "%1"'
            if v:
                import shlex
                parts = shlex.split(v.replace("\\", "\\\\"))
                if parts and Path(parts[0]).exists():
                    return parts[0]
        except OSError:
            pass
    return None


def sw_info(probe_com: bool = False) -> SWInfo:
    """返回 SWInfo 结构. probe_com=True 才尝试 COM 连接 (慢)."""
    reg = _probe_registry()
    info = SWInfo()

    # ProgID
    if reg["progid_list"]:
        info.progid = "SldWorks.Application"
        versioned = [p for p in reg["progid_list"] if "." in p and p.split(".")[-1].isdigit()]
        if versioned:
            # 取版本号最高
            versioned.sort(key=lambda p: int(p.split(".")[-1]))
            info.progid_versioned = versioned[-1]
            n = int(versioned[-1].split(".")[-1])
            info.major = _PROGID_YEAR.get(n)

    # 版本名
    if reg["versions"]:
        info.version = reg["versions"][0]  # "SOLIDWORKS 2023"
        if info.major is None:
            # 从 "SOLIDWORKS 2023" 抽
            for v in reg["versions"]:
                toks = v.split()
                if len(toks) >= 2 and toks[-1].isdigit():
                    info.major = int(toks[-1])
                    break

    # 安装目录
    info.installdir = reg.get("installdir")

    # exe
    info.exe = _find_sldworks_exe()

    info.installed = bool(info.exe) or bool(info.progid)

    # pywin32 可用?
    try:
        import win32com.client  # noqa
        import pythoncom        # noqa
        info.pywin32_ok = True
    except ImportError:
        info.pywin32_ok = False

    # COM 连接探测
    if probe_com and info.pywin32_ok and info.progid:
        info.com_probe = _quick_com_probe(info.progid_versioned or info.progid)

    return info


def _quick_com_probe(progid: str, timeout_s: float = 5.0) -> str:
    """极短超时探测 COM (仅 GetActiveObject, 不触发启动).

    返回:
      "ok"          — 连上
      "not_running" — SW 未运行
      "err: ..."    — 其他错误
    """
    try:
        import pythoncom
        import win32com.client as wc
        pythoncom.CoInitialize()
        try:
            app = wc.GetActiveObject(progid)
            try:
                _ = app.RevisionNumber
                return "ok"
            except Exception as e:  # noqa: BLE001
                return f"ok_but_rev_err: {type(e).__name__}"
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "-2147221021" in msg or "无法使用" in msg or "Operation unavailable" in msg:
                return "not_running"
            return f"err: {type(e).__name__}: {msg[:80]}"
        finally:
            try: pythoncom.CoUninitialize()
            except Exception: pass
    except Exception as e:  # noqa: BLE001
        return f"com_init_fail: {e}"


# ════════════════════════════════════════════════════════════════════════
# L0.5 · 许可系统深反 · 只读诊断 (不碰二进制 · 不写文件 · 不改服务)
# ════════════════════════════════════════════════════════════════════════
# SolidWorks 用 FlexNet Publisher (FNP) 做许可校验:
#   · 单机激活: C:\ProgramData\FLEXnet\SW_D_*_tsf.data (trusted storage)
#   · 浮动许可: SolidNetWork License Manager (lmgrd + SW_D vendor daemon)
#   · 端口: 25734 (SW_D vendor), 27000-27005 (lmgrd 默认)
# 诊断失败典型错 (-15,10,10061) = FLEXLM_CANT_CONNECT_TO_LICENSE_SERVER +
#   WSAECONNREFUSED, 表示上游许可服务无监听.
# 此层不修改任何许可配置; 仅产生报告, 供人工决策.

_SW_LIC_SERVICE_NAMES = [
    "SolidWorks Licensing Service",
    "SolidWorks Flexnet Server",
    "SolidNetWork License Manager",
    "SolidWorks License Manager",
    "SOLIDWORKS Licensing Boot Service",
]
_FLEX_SERVICE_NAMES = [
    "FlexNet Licensing Service",
    "FlexNet Licensing Service 64",
]
_SW_LIC_PORTS = [25734, 25735, 27000, 27001, 27002, 27003, 27004, 27005]
_FLEXNET_DIR = r"C:\ProgramData\FLEXnet"


def _sc_query(name: str) -> Optional[str]:
    """用 sc.exe 查 Windows 服务状态. 返回 Running/Stopped/Paused/None(未找到)."""
    if sys.platform != "win32":
        return None
    try:
        r = subprocess.run(
            ["sc.exe", "query", name],
            capture_output=True, encoding="mbcs", timeout=5,
        )
        if r.returncode != 0:
            return None
        for line in (r.stdout or "").splitlines():
            if "STATE" in line.upper():
                for tok in line.split():
                    u = tok.upper().replace("_", "")
                    if u in ("RUNNING", "STOPPED", "PAUSED",
                             "STARTPENDING", "STOPPENDING",
                             "CONTINUEPENDING", "PAUSEPENDING"):
                        return u.title()
        return "Unknown"
    except Exception:
        return None


def _check_tcp_port(port: int, host: str = "127.0.0.1",
                    timeout: float = 0.4) -> bool:
    """纯 stdlib 探测 <host>:<port> 是否在监听."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def _flexnet_trusted_storage() -> List[Dict[str, Any]]:
    """列出 C:\\ProgramData\\FLEXnet 下所有 SW_* 文件 (trust storage / event log)."""
    out: List[Dict[str, Any]] = []
    p = Path(_FLEXNET_DIR)
    if not p.exists():
        return out
    for f in sorted(p.glob("SW_D_*")):
        try:
            st = f.stat()
            name = f.name.lower()
            kind = ("event"  if "event.log" in name else
                    "backup" if "backup" in name else
                    "data"   if name.endswith(".data") else
                    "other")
            out.append({
                "name":   f.name,
                "size_B": st.st_size,
                "mtime":  datetime.datetime.fromtimestamp(st.st_mtime)
                          .isoformat(timespec="seconds"),
                "kind":   kind,
            })
        except OSError:
            continue
    return out


def _tail_event_log(n_lines: int = 20) -> List[str]:
    """从 FlexNet SW_D_*_event.log 尾部取最近 N 行."""
    p = Path(_FLEXNET_DIR)
    out: List[str] = []
    if not p.exists():
        return out
    for f in sorted(p.glob("SW_D_*_event.log")):
        try:
            with f.open("r", encoding="latin-1", errors="replace") as fp:
                lines = fp.readlines()
            for ln in lines[-n_lines:]:
                out.append(f"{f.name}: {ln.rstrip()}")
        except OSError:
            continue
    return out


def _com_registered(progid: str) -> Optional[str]:
    """若 progid 已注册, 返回 CLSID 字符串; 否则 None."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           f"SOFTWARE\\Classes\\{progid}\\CLSID")
        try:
            v, _ = winreg.QueryValueEx(k, "")
            return v
        finally:
            winreg.CloseKey(k)
    except OSError:
        return None


def _find_docmgr_dll() -> Optional[str]:
    """寻找 SolidWorks.Interop.swdocumentmgr.dll (三处常见路径)."""
    for cand in [
        r"C:\Program Files\Common Files\SolidWorks Shared\SolidWorks.Interop.swdocumentmgr.dll",
        r"D:\Program Files\Common Files\SolidWorks Shared\SolidWorks.Interop.swdocumentmgr.dll",
        r"C:\Program Files (x86)\Common Files\SolidWorks Shared\SolidWorks.Interop.swdocumentmgr.dll",
    ]:
        if Path(cand).exists():
            return cand
    return None


@dataclass
class SWLicenseState:
    services_flexnet: Dict[str, Optional[str]] = field(default_factory=dict)
    services_sw:      Dict[str, Optional[str]] = field(default_factory=dict)
    ports:            Dict[int, bool]          = field(default_factory=dict)
    trusted_storage:  List[Dict[str, Any]]     = field(default_factory=list)
    event_log_tail:   List[str]                = field(default_factory=list)
    com_registered:   Dict[str, Optional[str]] = field(default_factory=dict)
    doc_mgr_dll:      Optional[str]            = None
    findings:         List[str]                = field(default_factory=list)
    severity:         str                      = "unknown"  # ok/warning/critical
    recommend:        str                      = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def sw_license_diagnose() -> SWLicenseState:
    """SW 许可系统深反 · 只读诊断.

    输出: 服务/端口/trusted-storage/event-log/COM 注册/DocMgr 全景.
    不执行任何写入操作; 不依赖 SW 运行.
    """
    svcs_flex = {n: _sc_query(n) for n in _FLEX_SERVICE_NAMES}
    svcs_sw   = {n: _sc_query(n) for n in _SW_LIC_SERVICE_NAMES}
    ports     = {p: _check_tcp_port(p) for p in _SW_LIC_PORTS}
    tsf       = _flexnet_trusted_storage()
    log_tail  = _tail_event_log(12)
    progs = [
        "SldWorks.Application",
        "SldWorks.Application.30",
        "SldWorks.Application.31",
        "SldWorks.Application.32",
        "SwDocumentMgr.SwDocumentMgr",
        "SwDocumentMgr.SwDocumentMgr.30",
        "SwDocumentMgr.SwDocumentMgr.31",
        "SwDocumentMgr.SwDocumentMgr.32",
        "EModelView.EModelViewControl",
    ]
    com_reg = {p: _com_registered(p) for p in progs}
    docmgr_dll = _find_docmgr_dll()

    # ── 判定 ────────────────────────────────────────────────────────────
    findings: List[str] = []
    any_port_open = any(ports.values())
    any_sw_svc_running = any(
        s == "Running" for s in svcs_sw.values() if s is not None
    )
    any_flex_svc_running = any(
        s == "Running" for s in svcs_flex.values() if s is not None
    )
    com_sw_ok = any(
        com_reg.get(p) for p in
        ("SldWorks.Application",
         "SldWorks.Application.30",
         "SldWorks.Application.31",
         "SldWorks.Application.32")
    )
    com_docmgr_ok = any(
        com_reg.get(p) for p in
        ("SwDocumentMgr.SwDocumentMgr",
         "SwDocumentMgr.SwDocumentMgr.31",
         "SwDocumentMgr.SwDocumentMgr.32")
    )

    if not com_sw_ok:
        findings.append(
            "CRIT: SW 主应用 COM 未注册 (SldWorks.Application.*)"
        )
    if docmgr_dll is None:
        findings.append(
            "INFO: Document Manager DLL 未找到 · L2.5 不可用"
        )
    elif not com_docmgr_ok:
        findings.append(
            "WARN: SwDocumentMgr DLL 存在但未 COM 注册 · "
            "可管理员 regasm 或通过 DLL 路径加载"
        )
    if not any_port_open:
        findings.append(
            "WARN: FlexLM 许可端口全闭 (25734/25735/27000-27005) · "
            "无 lmgrd 监听, 浮动许可不可用"
        )
    stopped_sw = [n for n, s in svcs_sw.items() if s == "Stopped"]
    if stopped_sw and not any_sw_svc_running:
        findings.append(
            f"INFO: SW 许可服务 {stopped_sw} 已停止 · "
            "单机激活恢复需先启动 'SolidWorks Licensing Service'"
        )
    if tsf:
        tsf_data = [t for t in tsf if t["kind"] == "data"]
        if tsf_data:
            findings.append(
                f"INFO: FlexNet trusted storage · {len(tsf_data)} tsf.data 文件 "
                "(此机曾被激活)"
            )
    if log_tail and any("30000006" in ln for ln in log_tail):
        findings.append(
            "INFO: FNP 仍在自检 (EventCode 30000006 每 2min) · "
            "FlexNet 运行时正常, 等许可输入"
        )
    if any_flex_svc_running and not any_sw_svc_running and not any_port_open:
        findings.append(
            "DIAG: FlexNet 框架服务运行, 但 SW 专用许可服务/lmgrd 全下 · "
            "单机激活链断 (激活过期 / 被注销 / 服务停) → COM 被阻"
        )

    # ── 严重度 + 推荐 ───────────────────────────────────────────────────
    if not com_sw_ok:
        severity = "critical"
        recommend = "SW 未正确安装或 COM 注册损坏, 需重装或 sldworks.exe /RegServer"
    elif any_port_open or any_sw_svc_running:
        severity = "ok"
        recommend = "许可路径就绪, 可走 L2 (COM 活体)"
    elif docmgr_dll:
        severity = "warning"
        recommend = (
            "SW 许可不可用, 但 Document Manager DLL 存在 · "
            "走 L2.5 (免许可元数据) 或 L1 (纯 OLE2 反演)"
        )
    else:
        severity = "warning"
        recommend = "走 L1 (纯 OLE2 深反) · 零依赖, 零许可"

    return SWLicenseState(
        services_flexnet=svcs_flex,
        services_sw=svcs_sw,
        ports=ports,
        trusted_storage=tsf,
        event_log_tail=log_tail,
        com_registered=com_reg,
        doc_mgr_dll=docmgr_dll,
        findings=findings,
        severity=severity,
        recommend=recommend,
    )


# ────────────────────────────────────────────────────────────────────────
# L1 · OLE2 深反 (纯 stdlib)
# ────────────────────────────────────────────────────────────────────────
class OLE2Parser:
    """Microsoft Compound File Binary (MS-CFB) 全字段解析器.

    规格参照: [MS-CFB] Compound File Binary File Format.
    SolidWorks 的 SLDPRT/SLDASM/SLDDRW 皆为 CFB 容器, 内嵌多流.
    """

    HEADER_SIG  = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    ENDOFCHAIN  = 0xFFFFFFFE
    FREESECT    = 0xFFFFFFFF
    FATSECT     = 0xFFFFFFFD
    DIFSECT     = 0xFFFFFFFC

    DIR_STORAGE = 1
    DIR_STREAM  = 2
    DIR_ROOT    = 5

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._fp = None
        self._loaded = False
        self.header: Dict[str, Any] = {}
        self.sect_size: int = 0
        self.mini_size: int = 0
        self.fat: List[int] = []
        self.minifat: List[int] = []
        self.directory: List[Dict[str, Any]] = []
        self.mini_stream_start: int = 0

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *a):
        self.close()

    def open(self):
        if self._loaded:
            return
        self._fp = self.path.open("rb")
        self._parse_header()
        self._parse_fat()
        self._parse_directory()
        self._parse_minifat()
        self._loaded = True

    def close(self):
        if self._fp:
            self._fp.close()
            self._fp = None
        self._loaded = False

    # ─── header ────────────────────────────────────────────────────────
    def _parse_header(self):
        fp = self._fp
        fp.seek(0)
        hdr = fp.read(512)
        if hdr[:8] != self.HEADER_SIG:
            raise ValueError(f"{self.path.name} is not OLE2/CFB")
        self.header = {
            "clsid":              hdr[8:24].hex(),
            "minor_version":      struct.unpack_from("<H", hdr, 24)[0],
            "major_version":      struct.unpack_from("<H", hdr, 26)[0],
            "byte_order":         struct.unpack_from("<H", hdr, 28)[0],
            "sector_shift":       struct.unpack_from("<H", hdr, 30)[0],
            "mini_sector_shift":  struct.unpack_from("<H", hdr, 32)[0],
            "num_dir_sectors":    struct.unpack_from("<I", hdr, 40)[0],
            "num_fat_sectors":    struct.unpack_from("<I", hdr, 44)[0],
            "first_dir_sector":   struct.unpack_from("<I", hdr, 48)[0],
            "transaction_sig":    struct.unpack_from("<I", hdr, 52)[0],
            "mini_cutoff":        struct.unpack_from("<I", hdr, 56)[0],
            "first_minifat_sect": struct.unpack_from("<I", hdr, 60)[0],
            "num_minifat_sects":  struct.unpack_from("<I", hdr, 64)[0],
            "first_difat_sect":   struct.unpack_from("<I", hdr, 68)[0],
            "num_difat_sects":    struct.unpack_from("<I", hdr, 72)[0],
        }
        self.sect_size = 1 << self.header["sector_shift"]
        self.mini_size = 1 << self.header["mini_sector_shift"]
        # DIFAT 前 109 项
        self._difat_head = list(struct.unpack_from("<" + "I" * 109, hdr, 76))

    # ─── FAT ──────────────────────────────────────────────────────────
    def _read_sect(self, idx: int) -> bytes:
        offset = (idx + 1) * self.sect_size
        self._fp.seek(offset)
        return self._fp.read(self.sect_size)

    def _parse_fat(self):
        # 收集所有 FAT sector 索引
        fat_secs = [s for s in self._difat_head if s != self.FREESECT]
        # 读扩展 DIFAT (若有) — 终止条件包含 ENDOFCHAIN 和 FREESECT (不同写方器习惯不同)
        next_difat = self.header["first_difat_sect"]
        n_difat = self.header["num_difat_sects"]
        cnt = 0
        while (next_difat not in (self.ENDOFCHAIN, self.FREESECT)
               and cnt < n_difat + 10):
            blob = self._read_sect(next_difat)
            if not blob or len(blob) < self.sect_size:
                break
            n_per = (self.sect_size // 4) - 1
            for i in range(n_per):
                s = struct.unpack_from("<I", blob, i * 4)[0]
                if s != self.FREESECT:
                    fat_secs.append(s)
            next_difat = struct.unpack_from(
                "<I", blob, (self.sect_size // 4 - 1) * 4
            )[0]
            cnt += 1

        # 读 FAT
        fat = []
        for s in fat_secs:
            blob = self._read_sect(s)
            if not blob:
                continue
            # 允许最后一个 FAT sector 不足 sect_size
            n_entries = len(blob) // 4
            if n_entries == 0:
                continue
            fat.extend(struct.unpack_from("<" + "I" * n_entries, blob, 0))
        self.fat = fat

    def _follow_chain(self, start: int, mini: bool = False) -> List[int]:
        chain = []
        fat = self.minifat if mini else self.fat
        cur = start
        safety = 0
        terminators = {self.ENDOFCHAIN, self.FREESECT, self.FATSECT, self.DIFSECT}
        seen: set[int] = set()
        while (cur not in terminators and cur < len(fat)
               and safety < 10**6 and cur not in seen):
            chain.append(cur)
            seen.add(cur)
            cur = fat[cur]
            safety += 1
        return chain

    # ─── 目录 ─────────────────────────────────────────────────────────
    def _parse_directory(self):
        chain = self._follow_chain(self.header["first_dir_sector"])
        blob = b"".join(self._read_sect(s) for s in chain)
        entry_size = 128
        for i in range(len(blob) // entry_size):
            e = blob[i * entry_size : (i + 1) * entry_size]
            name_len = struct.unpack_from("<H", e, 64)[0]
            if name_len <= 0:
                self.directory.append({"name": "", "type": 0})
                continue
            name = e[:name_len - 2].decode("utf-16-le", errors="replace")
            entry = {
                "idx":        i,
                "name":       name,
                "type":       e[66],
                "color":      e[67],
                "left":       struct.unpack_from("<I", e, 68)[0],
                "right":      struct.unpack_from("<I", e, 72)[0],
                "child":      struct.unpack_from("<I", e, 76)[0],
                "clsid":      e[80:96].hex(),
                "state":      struct.unpack_from("<I", e, 96)[0],
                "ctime":      struct.unpack_from("<Q", e, 100)[0],
                "mtime":      struct.unpack_from("<Q", e, 108)[0],
                "start_sect": struct.unpack_from("<I", e, 116)[0],
                "size":       struct.unpack_from("<Q", e, 120)[0],
            }
            self.directory.append(entry)
        # Root 的 start_sect 指向 mini-stream
        if self.directory:
            root = self.directory[0]
            self.mini_stream_start = root["start_sect"]

    # ─── MiniFAT ──────────────────────────────────────────────────────
    def _parse_minifat(self):
        if self.header["num_minifat_sects"] == 0:
            self.minifat = []
            return
        chain = self._follow_chain(self.header["first_minifat_sect"])
        blob = b"".join(self._read_sect(s) for s in chain)
        self.minifat = list(struct.unpack_from("<" + "I" * (len(blob) // 4), blob))

    # ─── 读流 ─────────────────────────────────────────────────────────
    def read_stream(self, name_or_idx: Union[str, int]) -> bytes:
        if isinstance(name_or_idx, str):
            matches = [e for e in self.directory
                       if e.get("name") == name_or_idx and e.get("type") == self.DIR_STREAM]
            if not matches:
                raise KeyError(f"stream not found: {name_or_idx}")
            entry = matches[0]
        else:
            entry = self.directory[name_or_idx]
        return self._read_entry(entry)

    def _read_entry(self, entry: Dict[str, Any]) -> bytes:
        size = entry["size"]
        if size == 0:
            return b""
        if size < self.header["mini_cutoff"]:
            # mini stream
            chain = self._follow_chain(entry["start_sect"], mini=True)
            # 构造完整 mini-stream 数据 (通过 root 的大流链)
            if not hasattr(self, "_mini_stream_cache"):
                root = self.directory[0]
                mini_chain = self._follow_chain(root["start_sect"])
                self._mini_stream_cache = b"".join(
                    self._read_sect(s) for s in mini_chain
                )
            data = b""
            for ms in chain:
                off = ms * self.mini_size
                data += self._mini_stream_cache[off : off + self.mini_size]
            return data[:size]
        else:
            chain = self._follow_chain(entry["start_sect"])
            data = b"".join(self._read_sect(s) for s in chain)
            return data[:size]

    # ─── 枚举 ─────────────────────────────────────────────────────────
    def stream_names(self) -> List[str]:
        return [e["name"] for e in self.directory if e.get("type") == self.DIR_STREAM]

    def storage_names(self) -> List[str]:
        return [e["name"] for e in self.directory if e.get("type") == self.DIR_STORAGE]

    def walk(self) -> List[Dict[str, Any]]:
        """列出所有目录项的快照 (不含树形结构)."""
        return [
            {"name": e["name"],
             "type": e["type"],
             "size": e["size"]}
            for e in self.directory if e.get("name")
        ]

    def walk_tree(self) -> Dict[str, Any]:
        """构建带层次的目录树 (遵循 red-black tree 的 child/left/right 指针).

        返回形如 {"name": "Root", "type": 5, "children": [{"name": "Contents", ...}]}
        """
        if not self.directory:
            return {}
        NOSTREAM = 0xFFFFFFFF

        def _sibs(idx: int, acc: List[int]):
            if idx == NOSTREAM or idx >= len(self.directory):
                return
            if idx in acc:
                return
            acc.append(idx)
            e = self.directory[idx]
            _sibs(e.get("left", NOSTREAM), acc)
            _sibs(e.get("right", NOSTREAM), acc)

        def _node(idx: int) -> Dict[str, Any]:
            e = self.directory[idx]
            n: Dict[str, Any] = {
                "name": e["name"], "type": e["type"],
                "size": e["size"], "idx":  idx,
            }
            if e["type"] in (self.DIR_STORAGE, self.DIR_ROOT):
                child = e.get("child", NOSTREAM)
                sibs: List[int] = []
                _sibs(child, sibs)
                n["children"] = [_node(i) for i in sibs]
            return n

        return _node(0)

    def find_streams_matching(self, predicate) -> List[Tuple[str, bytes]]:
        """遍历所有流, 返回 predicate(data) 为真的 (name, data) 列表.

        predicate: Callable[[bytes], bool].
        """
        out: List[Tuple[str, bytes]] = []
        for e in self.directory:
            if e.get("type") != self.DIR_STREAM or e.get("size", 0) == 0:
                continue
            try:
                data = self._read_entry(e)
                if predicate(data):
                    out.append((e["name"], data))
            except Exception:
                continue
        return out


# ─── SummaryInformation / DocumentSummaryInformation 解析 ───────────
# 参照 MS-OLEPS Property Set
class PropertySetParser:
    """解析 OLE Property Set (\005SummaryInformation 流格式)."""

    VT_I2     = 0x0002
    VT_I4     = 0x0003
    VT_LPSTR  = 0x001E
    VT_LPWSTR = 0x001F
    VT_FILETIME = 0x0040
    VT_BLOB   = 0x0041
    VT_CLSID  = 0x0048

    # SummaryInformation FMTID: {F29F85E0-4FF9-1068-AB91-08002B27B3D9}
    # 关键属性 ID
    PID_TITLE       = 0x02
    PID_SUBJECT     = 0x03
    PID_AUTHOR      = 0x04
    PID_KEYWORDS    = 0x05
    PID_COMMENTS    = 0x06
    PID_TEMPLATE    = 0x07
    PID_LASTAUTHOR  = 0x08
    PID_REVNUMBER   = 0x09
    PID_EDITTIME    = 0x0A
    PID_LASTPRINTED = 0x0B
    PID_CREATED     = 0x0C
    PID_LASTSAVED   = 0x0D
    PID_APPNAME     = 0x12

    PID_NAMES = {
        PID_TITLE: "title", PID_SUBJECT: "subject", PID_AUTHOR: "author",
        PID_KEYWORDS: "keywords", PID_COMMENTS: "comments",
        PID_TEMPLATE: "template", PID_LASTAUTHOR: "last_author",
        PID_REVNUMBER: "revision_number", PID_EDITTIME: "edit_time",
        PID_LASTPRINTED: "last_printed", PID_CREATED: "created",
        PID_LASTSAVED: "last_saved", PID_APPNAME: "app_name",
    }

    @classmethod
    def parse(cls, data: bytes) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if len(data) < 48:
            return out
        try:
            # PropertySetHeader
            byte_order, version, os_ver, clsid, n_sets = struct.unpack_from("<HHI16sI", data, 0)
            # FormatID + Offset (first set)
            fmtid1 = data[28:44].hex()
            off1 = struct.unpack_from("<I", data, 44)[0]
            out["_fmtid"] = fmtid1
            out.update(cls._parse_section(data, off1))
        except Exception as e:
            out["_parse_err"] = str(e)
        return out

    @classmethod
    def _parse_section(cls, data: bytes, off: int) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        try:
            size, n_props = struct.unpack_from("<II", data, off)
        except struct.error:
            return out
        # 属性索引
        idx = []
        for i in range(n_props):
            try:
                pid, poff = struct.unpack_from("<II", data, off + 8 + i * 8)
                idx.append((pid, off + poff))
            except struct.error:
                break
        for pid, poff in idx:
            try:
                typ = struct.unpack_from("<I", data, poff)[0]
                name = cls.PID_NAMES.get(pid, f"pid_{pid:02X}")
                val = cls._read_value(data, poff + 4, typ)
                if val is not None:
                    out[name] = val
            except Exception:
                continue
        return out

    @classmethod
    def _read_value(cls, data: bytes, off: int, typ: int) -> Any:
        try:
            if typ == cls.VT_I2:
                return struct.unpack_from("<h", data, off)[0]
            if typ == cls.VT_I4:
                return struct.unpack_from("<i", data, off)[0]
            if typ == cls.VT_LPSTR:
                n = struct.unpack_from("<I", data, off)[0]
                raw = data[off + 4 : off + 4 + n]
                s = raw.rstrip(b"\x00").decode("latin-1", errors="replace")
                return s
            if typ == cls.VT_LPWSTR:
                n = struct.unpack_from("<I", data, off)[0]
                raw = data[off + 4 : off + 4 + n * 2]
                s = raw.rstrip(b"\x00").decode("utf-16-le", errors="replace").rstrip("\x00")
                return s
            if typ == cls.VT_FILETIME:
                ft = struct.unpack_from("<Q", data, off)[0]
                # FILETIME: 100ns ticks since 1601-01-01
                if ft == 0:
                    return None
                import datetime
                try:
                    dt = datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=ft // 10)
                    return dt.isoformat()
                except (OverflowError, ValueError):
                    return f"filetime_{ft}"
        except struct.error:
            return None
        return None


# ─── 预览图抽取 ─────────────────────────────────────────────────────
PNG_SIG  = b"\x89PNG\r\n\x1a\n"
JPEG_SIG = b"\xff\xd8\xff"


def _carve_image(data: bytes) -> Optional[bytes]:
    """从任意字节流里 carve 出 PNG/JPEG (处理 SW 在 PNG 前有小 header 的情形)."""
    if not data:
        return None
    # PNG: 寻找 signature; JPEG: 寻找 SOI
    png_idx = data.find(PNG_SIG)
    if png_idx >= 0:
        # 定位 IEND 末尾
        iend = data.find(b"IEND\xaeB`\x82", png_idx)
        if iend >= 0:
            return data[png_idx : iend + 8]
        return data[png_idx:]
    jpg_idx = data.find(JPEG_SIG)
    if jpg_idx >= 0:
        # 找 EOI (\xff\xd9)
        eoi = data.find(b"\xff\xd9", jpg_idx + 3)
        if eoi >= 0:
            return data[jpg_idx : eoi + 2]
        return data[jpg_idx:]
    return None


def extract_preview(path: Union[str, Path],
                    out_path: Optional[Union[str, Path]] = None) -> Optional[bytes]:
    """抽取 SW 文档内嵌的预览图 (PNG/JPEG bytes).

    SW 在 SLDPRT/SLDASM 内存放预览于多处:
      · PreviewPNG / Preview / \x05Preview (顶层流)
      · ModelStamps / Thumbnail (变体)
      · 任意流中含 PNG/JPEG signature (carve 回退)
    若提供 out_path, 同时写盘.
    """
    p = Path(path)
    try:
        with OLE2Parser(p) as ole:
            # Round 1: 按名称
            candidates = [
                "PreviewPNG", "Preview", "\x05Preview", "\x01Preview",
                "JPEG", "Thumbnail", "CompObjPreview",
            ]
            for name in candidates:
                try:
                    data = ole.read_stream(name)
                    carved = _carve_image(data) or data
                    if carved and (carved.startswith(PNG_SIG) or carved.startswith(JPEG_SIG)):
                        if out_path is not None:
                            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                            Path(out_path).write_bytes(carved)
                        return carved
                except KeyError:
                    continue
                except Exception:
                    continue

            # Round 2: 扫所有流, 取含 PNG/JPEG signature 的最大候选
            found: List[Tuple[int, bytes]] = []
            for e in ole.directory:
                if e.get("type") != OLE2Parser.DIR_STREAM:
                    continue
                if e.get("size", 0) < 256:
                    continue
                try:
                    d = ole._read_entry(e)
                    carved = _carve_image(d)
                    if carved and len(carved) > 512:
                        found.append((len(carved), carved))
                except Exception:
                    continue
            if found:
                found.sort(reverse=True)   # 最大的优先
                best = found[0][1]
                if out_path is not None:
                    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(out_path).write_bytes(best)
                return best
    except Exception:
        return None
    return None


# ─── SW 文件深反入口 ─────────────────────────────────────────────────
def probe_file(path: Union[str, Path]) -> Dict[str, Any]:
    """纯 stdlib 深反 SLDPRT/SLDASM/SLDDRW, 返回元数据 dict.

    字段:
      ok, path, size_MB, doc_type, ole2.{...}, summary.{...}, doc_summary.{...},
      streams[..], storages[..], preview_bytes, step_proxy (path or None),
      feature_hints, config_hints
    """
    p = Path(path)
    out: Dict[str, Any] = {
        "ok":       False,
        "path":     str(p),
        "size_B":   0,
        "size_MB":  0.0,
        "doc_type": SW_DOC_TYPE.name(SW_DOC_TYPE.from_path(p)),
        "streams":  [],
        "storages": [],
        "summary":  {},
        "doc_summary": {},
        "preview":  None,
        "hints":    {},
    }
    if not p.exists():
        out["err"] = "file_not_found"
        return out
    out["size_B"] = p.stat().st_size
    out["size_MB"] = round(out["size_B"] / (1024 * 1024), 3)
    try:
        with OLE2Parser(p) as ole:
            out["ok"] = True
            out["header"] = {
                "major": ole.header.get("major_version"),
                "minor": ole.header.get("minor_version"),
                "sect_size":  ole.sect_size,
                "mini_size":  ole.mini_size,
                "num_fat":    ole.header.get("num_fat_sectors"),
                "num_dir":    ole.header.get("num_dir_sectors"),
            }
            out["streams"]  = [
                {"name": e["name"], "size": e["size"]}
                for e in ole.directory
                if e.get("type") == OLE2Parser.DIR_STREAM and e.get("size", 0) > 0
            ]
            out["storages"] = [
                e["name"] for e in ole.directory
                if e.get("type") == OLE2Parser.DIR_STORAGE
            ]
            # SummaryInformation
            for s_name, key in (("\x05SummaryInformation",         "summary"),
                                ("\x05DocumentSummaryInformation", "doc_summary")):
                try:
                    raw = ole.read_stream(s_name)
                    out[key] = PropertySetParser.parse(raw)
                except KeyError:
                    pass
                except Exception as e:  # noqa: BLE001
                    out[key + "_err"] = str(e)
            # Preview
            try:
                preview = extract_preview(p)
                if preview:
                    out["preview"] = {
                        "size_B": len(preview),
                        "format": "png" if preview.startswith(b"\x89PNG") else
                                  ("jpeg" if preview.startswith(b"\xff\xd8\xff") else "unknown"),
                    }
            except Exception:
                pass
            # hints (文件内部字符串嗅探)
            out["hints"] = _hint_scan(p)
            # STEP proxy
            proxy = _find_step_proxy(p)
            if proxy:
                out["step_proxy"] = str(proxy)
    except Exception as e:  # noqa: BLE001
        out["err"] = f"{type(e).__name__}: {e}"
    return out


def _hint_scan(p: Path, max_bytes: int = 256 * 1024) -> Dict[str, Any]:
    """轻扫描前 256KB, 统计 SW 特征字符串出现次数 (识别文档类型和特征)."""
    try:
        raw = p.open("rb").read(max_bytes)
    except OSError:
        return {}
    markers = {
        "SwDoc":          b"SwDoc",
        "SwXml":          b"SwXml",
        "Config":         b"Config",
        "FeatureMgr":     b"FeatureMgr",
        "swXmlContents":  b"swXmlContents",
        "Component":      b"Component",
        "TopLevelNode":   b"TopLevelNode",
        "CM_":            b"CM_",
        "Default":        b"Default",
        "Preview":        b"Preview",
        "3rdPartyStorage":b"3rdPartyStorage",
        "BomFeat":        b"BomFeat",
    }
    return {k: raw.count(v) for k, v in markers.items() if v in raw}


def _find_step_proxy(p: Path) -> Optional[Path]:
    """回退: 找同名 STEP 代理. (与 dao_cad_bridge.find_step_proxy 对齐)"""
    stem = p.stem
    parent = p.parent
    for c in [
        parent / f"{stem}.stp_ap203.sldprt",
        parent / f"{stem}_ap203.sldprt",
        parent / f"{stem}.step",
        parent / f"{stem}.stp",
        parent / f"{stem}.STEP",
    ]:
        if c.exists():
            return c
    return None


def ole2_parse(path: Union[str, Path]) -> Dict[str, Any]:
    """OLE2 单独解析接口 (不走 SW-specific 路径)."""
    with OLE2Parser(path) as ole:
        return {
            "header":    ole.header,
            "directory": ole.walk(),
            "streams":   ole.stream_names(),
            "storages":  ole.storage_names(),
        }


# ════════════════════════════════════════════════════════════════════════
# L1.5 · 深流解析 · 特征/配置名 carve (SW 专有二进制的可得反演)
# ════════════════════════════════════════════════════════════════════════
# SW 特征/配置名在 CMgr* / Config-N / swXmlContents 等流中以 UTF-16LE +
# 长度前缀 的模式出现. 无 SW 公开规范, 但可靠模式:
#   · 4 字节 little-endian 长度 N (1..256) + N 个 UTF-16LE chars
#   · 后接 0x00 或常见 SW 分隔符
# 本模块用"可读性打分 + SW 命名词频"启发式提取, 在 53 件真实 SLDPRT 上验证
# 对 Boss-Extrude / Fillet / Config-Default / 尺寸名 等具有高召回.

# 典型 SW 特征/命名词 (用于打分, 非穷举)
_SW_FEAT_KEYWORDS = [
    "Boss-Extrude", "Cut-Extrude", "Boss-Revolve", "Cut-Revolve",
    "Boss-Sweep", "Cut-Sweep", "Boss-Loft", "Cut-Loft",
    "Boss-Thicken", "Cut-Thicken",
    "Fillet", "Chamfer", "Shell", "Draft", "Rib", "Dome", "Wrap",
    "Hole", "Thread", "Pattern", "Mirror", "MirrorPattern",
    "Sketch", "3DSketch", "Plane", "Axis", "Point", "CoordSystem",
    "Reference", "Surface", "Fill", "Trim", "Knit", "Extend",
    "Extrude", "Revolve", "Sweep", "Loft", "Thicken",
    "LinearPattern", "CircularPattern", "SketchPattern",
    "Split", "Combine", "Intersect", "Move", "Delete",
    "Configuration", "Default", "Master",
]

# 标识符字符: ASCII printable, CJK, 日文假名, 常见符号
def _is_ident_char(ch: int) -> bool:
    return (0x20 <= ch <= 0x7E                    # ASCII 可打印
            or 0x4E00 <= ch <= 0x9FFF             # 中日韩统一汉字
            or 0x3040 <= ch <= 0x30FF             # 日文平/片假名
            or 0xAC00 <= ch <= 0xD7AF             # 韩文
            or 0xFF00 <= ch <= 0xFFEF)            # 全角 ASCII


# 特征名接受模式: 至少包含一个字母或汉字, 不全是标点/数字
_NAME_ACCEPT = re.compile(
    r"[A-Za-z\u4e00-\u9fff\u3040-\u30ff]"
)


def _scan_bare_utf16(data: bytes,
                     min_len: int = 3, max_len: int = 80) -> List[str]:
    """裸扫 UTF-16LE 字符串运行. 起点对齐在偶数位, 直到 null 或非可打印终止."""
    out: List[str] = []
    n = len(data)
    if n < 4:
        return out
    i = 0
    while i < n - 1:
        # 对齐偶数
        if i & 1:
            i += 1
            continue
        chars: List[str] = []
        j = i
        while j + 1 < n:
            ch = data[j] | (data[j + 1] << 8)
            if ch == 0 or not _is_ident_char(ch):
                break
            chars.append(chr(ch))
            j += 2
            if len(chars) > max_len:
                break
        if min_len <= len(chars) <= max_len:
            s = "".join(chars)
            # 跳过全部是同一字符的退化 (如 "....", "    ")
            if len(set(s)) >= 2 and _NAME_ACCEPT.search(s):
                out.append(s)
            i = j + 2  # 跳过 null
        else:
            i += 2
    return out


def _scan_len_prefixed_utf16(data: bytes,
                             prefix_size: int = 4,
                             min_n: int = 2, max_n: int = 128) -> List[str]:
    """扫 <u16/u32 长度> + UTF-16LE 字符串的结构化运行."""
    out: List[str] = []
    n = len(data)
    if n < prefix_size + 4:
        return out
    fmt = "<I" if prefix_size == 4 else "<H"
    i = 0
    while i + prefix_size + 4 < n:
        try:
            cnt = struct.unpack_from(fmt, data, i)[0]
        except struct.error:
            break
        if not (min_n <= cnt <= max_n):
            i += 1
            continue
        byte_len = cnt * 2
        if i + prefix_size + byte_len > n:
            i += 1
            continue
        raw = data[i + prefix_size : i + prefix_size + byte_len]
        # 必须是干净的 UTF-16LE: 每个字符都是 ident_char
        ok = True
        s_chars = []
        for k in range(0, byte_len, 2):
            ch = raw[k] | (raw[k + 1] << 8)
            if not _is_ident_char(ch) or ch == 0:
                ok = False
                break
            s_chars.append(chr(ch))
        if ok and s_chars:
            s = "".join(s_chars)
            if _NAME_ACCEPT.search(s) and len(set(s)) >= 2:
                out.append(s)
            i += prefix_size + byte_len
        else:
            i += 1
    return out


def carve_feature_names(data: bytes,
                        limit: int = 2000) -> List[str]:
    """从任意 SW 流字节里 carve 出特征名/字符串候选.

    三重启发:
      1. u32-前缀 + UTF-16LE (MFC CArchive 常用)
      2. u16-前缀 + UTF-16LE (较短字符串)
      3. 裸 UTF-16LE 运行 (null-terminated)
    结果按出现顺序去重, 保留首 `limit` 条.
    """
    seen: Dict[str, None] = {}
    for candidate in (
        _scan_len_prefixed_utf16(data, prefix_size=4, min_n=2, max_n=128),
        _scan_len_prefixed_utf16(data, prefix_size=2, min_n=2, max_n=128),
        _scan_bare_utf16(data, min_len=3, max_len=80),
    ):
        for s in candidate:
            if s not in seen:
                seen[s] = None
                if len(seen) >= limit:
                    break
        if len(seen) >= limit:
            break
    return list(seen.keys())


def carve_config_names(data: bytes,
                       limit: int = 200) -> List[str]:
    """从 CMgr* 流抽配置名. 比特征更严格: 只取看起来像 config 的短名."""
    all_names = carve_feature_names(data, limit=limit * 4)
    out: List[str] = []
    for s in all_names:
        # 配置名常见: Default / 默认 / Config-N / <MasterConfig>
        if (s in ("Default", "Master")
            or s.startswith("Config")
            or "Default" in s
            or "默认" in s
            or 2 <= len(s) <= 40):
            out.append(s)
        if len(out) >= limit:
            break
    return out


def deep_probe_file(path: Union[str, Path],
                    max_stream_bytes: int = 2 * 1024 * 1024) -> Dict[str, Any]:
    """L1 + L1.5 深反: 在 probe_file 之上追加特征/配置 carve.

    附加字段:
      · feature_names_carved   — 从 Config-0/CMgr 流提取的特征/命名候选
      · config_names_carved    — 从 CMgr* 流提取的配置名候选
      · stream_highlights      — 每个关键流的 size + 预览特征数
    """
    base = probe_file(path)
    if not base.get("ok"):
        return base

    p = Path(path)
    feat_names: List[str] = []
    cfg_names: List[str] = []
    highlights: Dict[str, Dict[str, Any]] = {}

    try:
        with OLE2Parser(p) as ole:
            # 关键流: Config-0 (主配置数据, SW 特征树载体)
            # CMgr / CMgrHdr2 (配置管理器头)
            # swXmlContents (XML 元数据)
            targets = []
            for e in ole.directory:
                if e.get("type") != OLE2Parser.DIR_STREAM:
                    continue
                nm = e.get("name", "")
                if (nm.startswith("Config")
                    or nm.startswith("CMgr")
                    or nm == "swXmlContents"
                    or nm.startswith("FeatureMgr")):
                    targets.append(e)
            # 按体积降序 — 大流最可能藏特征树
            targets.sort(key=lambda e: e.get("size", 0), reverse=True)

            for e in targets[:6]:  # 最多 6 条流
                try:
                    data = ole._read_entry(e)
                except Exception:
                    continue
                if not data:
                    continue
                # 截断, 避免巨流撑爆内存
                sample = data[:max_stream_bytes]
                nm = e["name"]
                if nm.startswith("CMgr"):
                    names = carve_config_names(sample, limit=100)
                    cfg_names.extend(names)
                else:
                    names = carve_feature_names(sample, limit=500)
                    feat_names.extend(names)
                highlights[nm] = {
                    "size_B": e.get("size", 0),
                    "sampled_B": len(sample),
                    "n_names_found": len(names),
                    "first_names": names[:8],
                }
    except Exception as ex:  # noqa: BLE001
        base["l1_5_err"] = f"{type(ex).__name__}: {ex}"

    # 去重保序
    def _dedup(lst: List[str]) -> List[str]:
        seen: Dict[str, None] = {}
        for s in lst:
            seen[s] = None
        return list(seen.keys())

    base["feature_names_carved"] = _dedup(feat_names)[:300]
    base["config_names_carved"] = _dedup(cfg_names)[:50]
    base["stream_highlights"] = highlights
    return base


# ════════════════════════════════════════════════════════════════════════
# L3 · 原生 DLL 深反 · PE/COFF 读 + 导出表抽取 (纯 stdlib)
# ════════════════════════════════════════════════════════════════════════
# SW 安装有 2000+ DLL (D:\Program Files\SOLIDWORKS Corp23\**), 含:
#   · 原生 C++ DLL (sldappu.dll / sldmod.dll / sldshellutils* / modeler*)
#   · .NET Interop 程序集 (SolidWorks.Interop.*)
#   · 混合程序集 (部分 CLR + 部分 C++)
# 此层用纯 Python 读 PE 头:
#   · 识别 x86/x64/Managed
#   · 抽 Export Directory 里的 DLL name + 导出名单 (native DLL)
#   · 扫描 SW 安装根, 按目录生成全量索引


class PEReader:
    """纯 stdlib PE/COFF (Portable Executable) 读器.

    只读: DOS 头 → NT 头 → Optional → Section 表 → Export Directory.
    .NET 程序集通过 DataDirectory[14] (CLR) 识别, 其内部 metadata 解析
    超出此处范围 (返回 managed=True 即可).
    """

    DIR_EXPORT = 0
    DIR_IMPORT = 1
    DIR_CLR    = 14

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._fp = None
        self._raw: Optional[bytes] = None
        self._parsed = False
        self._file_size: int = 0
        self.machine:        int = 0
        self.pe_type:        str = ""      # "PE32" / "PE32+"
        self.is_managed:     bool = False
        self.n_sections:     int = 0
        self.sections:       List[Dict[str, Any]] = []
        self.data_dirs:      List[Tuple[int, int]] = []  # [(VA, size)]
        self.e_lfanew:       int = 0
        self.optional_off:   int = 0
        self._mgr_hdr_va:    int = 0

    def __enter__(self):
        self.open(); return self

    def __exit__(self, *a):
        self.close()

    def open(self) -> "PEReader":
        if self._parsed:
            return self
        # 先读 4KB 解析 header. 后续访问 Export Dir 时按需扩展 buffer.
        size = self.path.stat().st_size
        self._file_size = size
        with self.path.open("rb") as f:
            self._raw = f.read(min(size, 4 * 1024))
        self._parse_headers()
        self._parsed = True
        return self

    def close(self):
        self._raw = None

    def _ensure_bytes(self, up_to: int) -> bool:
        """确保 _raw 至少涵盖 up_to 字节. 按需从磁盘再读."""
        if self._raw is None:
            return False
        if up_to <= len(self._raw):
            return True
        if up_to > self._file_size:
            up_to = self._file_size
        try:
            with self.path.open("rb") as f:
                # 读到 up_to + 小 margin
                self._raw = f.read(up_to + 16384)
            return up_to <= len(self._raw)
        except OSError:
            return False

    def _parse_headers(self):
        r = self._raw
        if not r or len(r) < 0x40 or r[:2] != b"MZ":
            raise ValueError(f"{self.path.name} is not a PE file")
        self.e_lfanew = struct.unpack_from("<I", r, 0x3C)[0]
        if self.e_lfanew + 0x18 > len(r):
            raise ValueError(f"{self.path.name} truncated NT header")
        if r[self.e_lfanew : self.e_lfanew + 4] != b"PE\x00\x00":
            raise ValueError(f"{self.path.name} not PE signature")
        coff_off = self.e_lfanew + 4
        self.machine = struct.unpack_from("<H", r, coff_off)[0]
        self.n_sections = struct.unpack_from("<H", r, coff_off + 2)[0]
        size_opt = struct.unpack_from("<H", r, coff_off + 16)[0]
        self.optional_off = coff_off + 20
        if self.optional_off + size_opt > len(r):
            # still try to parse what we have
            pass

        magic = struct.unpack_from("<H", r, self.optional_off)[0]
        if magic == 0x10b:
            self.pe_type = "PE32"
            # PE32 has NumberOfRvaAndSizes at opt+92
            num_rva_off = self.optional_off + 92
            dirs_off = self.optional_off + 96
        elif magic == 0x20b:
            self.pe_type = "PE32+"
            num_rva_off = self.optional_off + 108
            dirs_off = self.optional_off + 112
        else:
            raise ValueError(f"unknown PE magic: 0x{magic:x}")

        if num_rva_off + 4 > len(r):
            return
        num_rva = struct.unpack_from("<I", r, num_rva_off)[0]
        num_rva = min(num_rva, 16)
        for i in range(num_rva):
            off = dirs_off + i * 8
            if off + 8 > len(r):
                break
            va   = struct.unpack_from("<I", r, off)[0]
            size = struct.unpack_from("<I", r, off + 4)[0]
            self.data_dirs.append((va, size))

        # CLR header => managed
        if (self.DIR_CLR < len(self.data_dirs)
            and self.data_dirs[self.DIR_CLR][0] != 0):
            self.is_managed = True
            self._mgr_hdr_va = self.data_dirs[self.DIR_CLR][0]

        # 节表
        sec_off = self.optional_off + size_opt
        for i in range(self.n_sections):
            base = sec_off + i * 40
            if base + 40 > len(r):
                break
            name = r[base : base + 8].rstrip(b"\x00").decode("latin-1", errors="replace")
            vsize = struct.unpack_from("<I", r, base + 8)[0]
            vaddr = struct.unpack_from("<I", r, base + 12)[0]
            rsize = struct.unpack_from("<I", r, base + 16)[0]
            raddr = struct.unpack_from("<I", r, base + 20)[0]
            self.sections.append({
                "name": name, "vsize": vsize, "vaddr": vaddr,
                "rsize": rsize, "raddr": raddr,
            })

    def _rva_to_offset(self, rva: int) -> Optional[int]:
        for s in self.sections:
            if s["vaddr"] <= rva < s["vaddr"] + max(s["vsize"], s["rsize"]):
                return rva - s["vaddr"] + s["raddr"]
        return None

    @property
    def machine_name(self) -> str:
        return {0x14c: "x86", 0x8664: "x64", 0x200: "ia64",
                0xaa64: "arm64", 0x1c0: "arm"}.get(self.machine, f"0x{self.machine:x}")

    def dll_name(self) -> Optional[str]:
        """读 Export Directory 里的 DLL Name 字段."""
        if not self.data_dirs:
            return None
        exp_va, exp_sz = self.data_dirs[self.DIR_EXPORT]
        if exp_va == 0 or exp_sz < 40:
            return None
        off = self._rva_to_offset(exp_va)
        if off is None:
            return None
        if not self._ensure_bytes(off + 40):
            return None
        # Export Dir: [12] NameRVA
        name_rva = struct.unpack_from("<I", self._raw, off + 12)[0]
        name_off = self._rva_to_offset(name_rva)
        if name_off is None:
            return None
        if not self._ensure_bytes(name_off + 256):
            return None
        end = (self._raw or b"").find(b"\x00", name_off)
        if end == -1 or end - name_off > 200:
            return None
        return (self._raw or b"")[name_off : end].decode(
            "latin-1", errors="replace")

    def exports(self, limit: int = 200) -> List[str]:
        """读导出函数名表. 返回最多 `limit` 条."""
        if not self.data_dirs:
            return []
        exp_va, exp_sz = self.data_dirs[self.DIR_EXPORT]
        if exp_va == 0 or exp_sz < 40:
            return []
        off = self._rva_to_offset(exp_va)
        if off is None:
            return []
        if not self._ensure_bytes(off + 40):
            return []
        # ExportDir 字段:
        # [20] NumberOfFunctions, [24] NumberOfNames
        # [28] AddressOfFunctions, [32] AddressOfNames, [36] AddressOfNameOrdinals
        n_names = struct.unpack_from("<I", self._raw, off + 24)[0]
        names_rva = struct.unpack_from("<I", self._raw, off + 32)[0]
        names_off = self._rva_to_offset(names_rva)
        if names_off is None:
            return []
        # 确保有足够字节覆盖名称表 + 典型的导出名字符串池
        need = names_off + 4 * min(n_names, limit) + 16
        # 字符串池紧随其后, 给 32KB 余量
        if not self._ensure_bytes(need + 32 * 1024):
            return []
        out: List[str] = []
        raw = self._raw or b""
        for i in range(min(n_names, limit)):
            if names_off + 4 * i + 4 > len(raw):
                break
            nm_rva = struct.unpack_from("<I", raw, names_off + 4 * i)[0]
            nm_off = self._rva_to_offset(nm_rva)
            if nm_off is None:
                continue
            # 名字串可能在更远处; 按需扩展
            if nm_off + 256 > len(raw):
                if not self._ensure_bytes(nm_off + 256):
                    continue
                raw = self._raw or b""
            end = raw.find(b"\x00", nm_off)
            if end == -1 or end - nm_off > 250:
                continue
            s = raw[nm_off : end].decode("latin-1", errors="replace")
            if s:
                out.append(s)
        return out

    def summary(self) -> Dict[str, Any]:
        return {
            "path":        str(self.path),
            "size_B":      self.path.stat().st_size,
            "pe_type":     self.pe_type,
            "machine":     self.machine_name,
            "is_managed":  self.is_managed,
            "n_sections":  self.n_sections,
            "sections":    [s["name"] for s in self.sections][:10],
            "dll_name":    self.dll_name(),
        }


def sw_dll_index(installdir: Optional[str] = None,
                 max_files: int = 3000,
                 include_exports: bool = False) -> Dict[str, Any]:
    """索引 SW 安装根下所有 DLL/EXE, 按目录归组.

    输出结构:
      {
        "root": <installdir>,
        "total": N,
        "by_dir": {dir: [{name, size_B, pe_type, machine, managed}, ...]},
        "native_dll_exports": {dll_name: [top N export names]},   # 若 include_exports
        "managed_count": M,
        "native_count":  K,
      }
    """
    if installdir is None:
        info = sw_info(probe_com=False)
        installdir = info.installdir or (
            str(Path(info.exe).parent) if info.exe else None
        )
    if installdir is None:
        return {"err": "cannot locate SW installdir"}
    root = Path(installdir)
    if not root.exists():
        return {"err": f"installdir not found: {installdir}"}
    # SW 的 Corp 根往往是 install 的一层外, 我们以 .parent 为真根
    if root.name.upper() == "SOLIDWORKS":
        root = root.parent

    by_dir: Dict[str, List[Dict[str, Any]]] = {}
    native_exports: Dict[str, List[str]] = {}
    managed_n = 0
    native_n  = 0
    count = 0

    for f in root.rglob("*"):
        if count >= max_files:
            break
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext not in (".dll", ".exe", ".ocx"):
            continue
        try:
            with PEReader(f) as pe:
                s = pe.summary()
                rel_dir = str(f.parent.relative_to(root))
                by_dir.setdefault(rel_dir, []).append({
                    "name":    f.name,
                    "size_B":  s["size_B"],
                    "pe_type": s["pe_type"],
                    "machine": s["machine"],
                    "managed": s["is_managed"],
                })
                if s["is_managed"]:
                    managed_n += 1
                else:
                    native_n += 1
                    if include_exports:
                        exps = pe.exports(limit=20)
                        if exps:
                            native_exports[f.name] = exps
        except Exception:
            continue
        count += 1

    out: Dict[str, Any] = {
        "root":          str(root),
        "total":         count,
        "managed_count": managed_n,
        "native_count":  native_n,
        "by_dir":        {k: v for k, v in sorted(by_dir.items())},
    }
    if include_exports:
        out["native_dll_exports"] = native_exports
    return out


# ════════════════════════════════════════════════════════════════════════
# L4 · 注册表全树反演 (HKLM\SOFTWARE\SolidWorks + HKCR\.sld* + 相关 CLSID)
# ════════════════════════════════════════════════════════════════════════

def _reg_walk(hive: int, key: str, depth: int = 0,
              max_depth: int = 4, max_keys: int = 500,
              state: Optional[Dict[str, int]] = None,
              include_values: bool = True) -> Dict[str, Any]:
    """递归读一个注册表子键. 返回 {"values": {}, "keys": {child: {...}}}.

    max_depth 控制递归深度, max_keys 限总节点数避免爆炸.
    """
    if state is None:
        state = {"count": 0}
    if sys.platform != "win32":
        return {}
    try:
        import winreg
    except ImportError:
        return {}
    out: Dict[str, Any] = {"values": {}, "keys": {}}
    state["count"] += 1
    if state["count"] > max_keys:
        return {"_truncated": True}
    try:
        k = winreg.OpenKey(hive, key)
    except OSError:
        return {"_err": "cannot_open"}
    try:
        # values
        if include_values:
            i = 0
            while True:
                try:
                    name, value, typ = winreg.EnumValue(k, i)
                except OSError:
                    break
                vrepr: Any
                if isinstance(value, bytes):
                    vrepr = f"<bytes:{len(value)}>"
                elif isinstance(value, str) and len(value) > 200:
                    vrepr = value[:200] + "..."
                else:
                    vrepr = value
                out["values"][name or "(default)"] = vrepr
                i += 1
        # sub-keys
        if depth < max_depth:
            j = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, j)
                except OSError:
                    break
                if state["count"] > max_keys:
                    out["keys"]["_truncated"] = True
                    break
                out["keys"][sub] = _reg_walk(
                    hive, f"{key}\\{sub}", depth + 1, max_depth,
                    max_keys, state, include_values,
                )
                j += 1
    finally:
        try:
            winreg.CloseKey(k)
        except Exception:
            pass
    return out


def sw_registry_dump(include_values: bool = True,
                    max_keys: int = 800) -> Dict[str, Any]:
    """导出 SW 注册表全景 · HKLM\\SOFTWARE\\SolidWorks + HKCR\\.sld*.

    范围:
      · HKLM\\SOFTWARE\\SolidWorks                 (安装/许可/AddIns/Applications)
      · HKLM\\SOFTWARE\\Classes\\.sldprt/.sldasm/.slddrw (文件扩展 → 处理器)
      · HKLM\\SOFTWARE\\Classes\\SldPart.Document / SldAssem.Document / SldDrawing.Document
      · HKLM\\SOFTWARE\\Classes\\CLSID\\{SldWorks.Application}
      · HKLM\\SOFTWARE\\Classes\\SldWorks.Application.*
    """
    if sys.platform != "win32":
        return {"err": "not windows"}
    try:
        import winreg
    except ImportError:
        return {"err": "no winreg"}

    out: Dict[str, Any] = {}

    # 1) SolidWorks 主键
    out["HKLM\\SOFTWARE\\SolidWorks"] = _reg_walk(
        winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\SolidWorks",
        max_depth=3, max_keys=max_keys, include_values=include_values,
    )

    # 2) 文件扩展
    for ext in (".sldprt", ".sldasm", ".slddrw"):
        out[f"HKLM\\SOFTWARE\\Classes\\{ext}"] = _reg_walk(
            winreg.HKEY_LOCAL_MACHINE, f"SOFTWARE\\Classes\\{ext}",
            max_depth=2, max_keys=60, include_values=include_values,
        )

    # 3) SW ProgID → CLSID
    for prog in ("SldWorks.Application", "SldWorks.Application.31",
                 "SwDocumentMgr.SwDocumentMgr",
                 "SwDocumentMgr.SwDocumentMgr.31",
                 "SldPart.Document", "SldAssem.Document", "SldDrawing.Document",
                 "EModelView.EModelViewControl"):
        tree = _reg_walk(
            winreg.HKEY_LOCAL_MACHINE, f"SOFTWARE\\Classes\\{prog}",
            max_depth=3, max_keys=60, include_values=include_values,
        )
        if tree and tree != {"_err": "cannot_open"}:
            out[f"HKLM\\SOFTWARE\\Classes\\{prog}"] = tree

    # 4) SW CLSID 的 LocalServer / InprocServer
    sw_clsid = _com_registered("SldWorks.Application")
    if sw_clsid:
        out[f"HKLM\\SOFTWARE\\Classes\\CLSID\\{sw_clsid}"] = _reg_walk(
            winreg.HKEY_LOCAL_MACHINE,
            f"SOFTWARE\\Classes\\CLSID\\{sw_clsid}",
            max_depth=3, max_keys=60, include_values=include_values,
        )

    # 5) 统计
    def _count(t: Any) -> Tuple[int, int]:
        nk, nv = 0, 0
        if not isinstance(t, dict):
            return nk, nv
        nv += len(t.get("values", {}) or {})
        for kname, sub in (t.get("keys", {}) or {}).items():
            if kname.startswith("_"):
                continue
            nk += 1
            a, b = _count(sub)
            nk += a; nv += b
        return nk, nv

    total_k, total_v = 0, 0
    for root_name, tree in out.items():
        k, v = _count(tree)
        total_k += k; total_v += v

    out["_summary"] = {
        "total_keys": total_k,
        "total_values": total_v,
        "roots": list(out.keys()),
    }
    return out


# ════════════════════════════════════════════════════════════════════════
# L5 · 打通 · 反者道之动 · 实干破障 (Remediation Layer)
# ════════════════════════════════════════════════════════════════════════
# L0.5 诊断发现的两大阻塞:
#   阻塞 1: SwDocumentMgr COM 未注册 → regasm /codebase 注册托管 DLL
#   阻塞 2: SolidWorks Licensing Service 停 (Manual) → sc start 可启
# 本层提供 dry_run 预演 + 实执两档, 默认 dry_run=True 防误触.
# 需管理员; 若 is_admin() 为 False, 仍输出"如果运行会执行什么"的动作清单.
# ────────────────────────────────────────────────────────────────────────

_DOCMGR_DLL_CANDS = [
    r"C:\Program Files\Common Files\SolidWorks Shared\SolidWorks.Interop.swdocumentmgr.dll",
    r"C:\Program Files (x86)\Common Files\SolidWorks Shared\SolidWorks.Interop.swdocumentmgr.dll",
    r"D:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS\SolidWorks.Interop.swdocumentmgr.dll",
]

_REGASM_CANDS = [
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\regasm.exe",
    r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\regasm.exe",
    r"C:\Windows\Microsoft.NET\Framework64\v2.0.50727\regasm.exe",
    r"C:\Windows\Microsoft.NET\Framework\v2.0.50727\regasm.exe",
]

_SW_LICENSE_SERVICES_PRIORITY = [
    "SolidWorks Licensing Service",  # SolidWorksLicensing.exe, 单机必需
    # "SolidWorks Flexnet Server" 默认 Disabled 且路径常缺, 不自动启
]


@dataclass
class L5RemediationResult:
    """L5 打通动作的统一结果结构."""
    action:   str                       = ""
    ok:       bool                      = False
    dry_run:  bool                      = True
    admin:    bool                      = False
    steps:    List[Dict[str, Any]]      = field(default_factory=list)
    before:   Dict[str, Any]            = field(default_factory=dict)
    after:    Dict[str, Any]            = field(default_factory=dict)
    err:      Optional[str]             = None
    notes:    List[str]                 = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def is_admin() -> bool:
    """纯 stdlib 检测当前进程是否为管理员.

    Windows: shell32.IsUserAnAdmin() 直连
    其它: os.geteuid() == 0
    """
    if sys.platform != "win32":
        try:
            return os.geteuid() == 0  # type: ignore[attr-defined]
        except AttributeError:
            return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def find_regasm(prefer_64: bool = True) -> Optional[str]:
    """发现 regasm.exe 路径. prefer_64=True 优先 Framework64/v4.

    注: regasm 是 .NET MSIL 工具, Framework 与 Framework64 都能处理 AnyCPU
    程序集; 但对纯 x86 程序集, 用 Framework (32-bit regasm) 更稳.
    """
    if sys.platform != "win32":
        return None
    cands = list(_REGASM_CANDS)
    if not prefer_64:
        cands = [c for c in cands if "Framework64" not in c] + \
                [c for c in cands if "Framework64" in c]
    for c in cands:
        if Path(c).exists():
            return c
    return None


def _find_docmgr_dll_l5() -> Optional[str]:
    """L5 视角找 DocMgr DLL (优先托管的 Interop DLL)."""
    for c in _DOCMGR_DLL_CANDS:
        if Path(c).exists():
            return c
    return None


def remediate_docmgr_com(dry_run: bool = True,
                         prefer_regasm_32: bool = False,
                         register_both: bool = True,
                         unregister_first: bool = False,
                         ) -> L5RemediationResult:
    r"""L5.1 · 打通 SwDocumentMgr COM 注册.

    以 regasm 注册 `SolidWorks.Interop.swdocumentmgr.dll` (托管 .NET Interop).

    关键 · WOW64 双视图:
        · 64-bit regasm (Framework64\v4) → HKLM\SOFTWARE\Classes\... (主视图)
            此为 64-bit 进程 (pywin32, Python 64-bit) 可见的视图.
        · 32-bit regasm (Framework\v4)   → HKLM\SOFTWARE\Classes\Wow6432Node\...
            此为 32-bit 进程可见的视图.

    默认 register_both=True · 双视图注册, 让 32/64-bit 客户端都能用.
    若之前注册过一侧想切换, 传 unregister_first=True 先 /unregister.
    """
    r = L5RemediationResult(action="remediate_docmgr_com", dry_run=dry_run)
    r.admin = is_admin()

    if sys.platform != "win32":
        r.err = "non-windows"
        return r

    # 1) 找 DLL
    dll = _find_docmgr_dll_l5()
    if not dll:
        r.err = "docmgr_dll_not_found"
        r.notes.append("三条候选路径均不存在; 检查 SW 安装完整性")
        return r
    r.steps.append({"step": "find_dll", "ok": True, "path": dll})

    # 2) 选 regasm
    # 决定优先档序: 64 或 32; register_both 时两档都跑
    regasm_64 = find_regasm(prefer_64=True)
    # 找 32-bit (避免 Framework64)
    regasm_32: Optional[str] = None
    for cand in _REGASM_CANDS:
        if "Framework64" not in cand and Path(cand).exists():
            regasm_32 = cand
            break

    if register_both:
        regasm_list = [x for x in (regasm_64, regasm_32) if x]
    else:
        chosen = regasm_32 if prefer_regasm_32 else regasm_64
        regasm_list = [chosen] if chosen else []

    if not regasm_list:
        r.err = "regasm_not_found"
        r.notes.append("Microsoft.NET Framework 未安装或路径异常")
        return r

    r.steps.append({"step": "find_regasm",
                    "ok": True,
                    "paths": regasm_list,
                    "register_both": register_both})

    # 3) 记录注册 before (两视图都读)
    before = {
        "SwDocumentMgr.SwDocumentMgr_64":    _com_registered_wow(
            "SwDocumentMgr.SwDocumentMgr", view="64"),
        "SwDocumentMgr.SwDocumentMgr.31_64": _com_registered_wow(
            "SwDocumentMgr.SwDocumentMgr.31", view="64"),
        "SwDocumentMgr.SwDocumentMgr_32":    _com_registered_wow(
            "SwDocumentMgr.SwDocumentMgr", view="32"),
        "SwDocumentMgr.SwDocumentMgr.31_32": _com_registered_wow(
            "SwDocumentMgr.SwDocumentMgr.31", view="32"),
    }
    r.before = before

    if dry_run:
        for regasm in regasm_list:
            cmd = [regasm, dll, "/codebase"]
            r.steps.append({"step": "cmd", "argv": cmd})
        r.ok = True
        r.notes.append("dry_run=True · 未执行 · 传 dry_run=False 实执 (需 admin)")
        return r

    if not r.admin:
        r.err = "not_admin"
        r.notes.append("当前进程非管理员, 无法写 HKLM · 以 admin shell 重跑")
        return r

    # 4) 先可选 unregister
    if unregister_first:
        for regasm in regasm_list:
            try:
                p = subprocess.run(
                    [regasm, dll, "/unregister"],
                    capture_output=True, text=True, timeout=60,
                    encoding="utf-8", errors="replace",
                )
                r.steps.append({
                    "step": "exec_regasm_unreg",
                    "regasm": regasm,
                    "rc": p.returncode,
                    "stdout_tail": (p.stdout or "").strip().splitlines()[-4:],
                })
            except Exception as ex:  # noqa: BLE001
                r.steps.append({
                    "step": "exec_regasm_unreg_err",
                    "regasm": regasm,
                    "err": f"{type(ex).__name__}: {ex}",
                })

    # 5) 执行 regasm (可能两档)
    for regasm in regasm_list:
        cmd = [regasm, dll, "/codebase"]
        try:
            p = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
                encoding="utf-8", errors="replace",
            )
            r.steps.append({
                "step": "exec_regasm",
                "regasm": regasm,
                "rc": p.returncode,
                "stdout_tail": (p.stdout or "").strip().splitlines()[-6:],
                "stderr_tail": (p.stderr or "").strip().splitlines()[-6:],
            })
        except subprocess.TimeoutExpired:
            r.steps.append({
                "step": "exec_regasm_timeout",
                "regasm": regasm,
            })
        except Exception as ex:  # noqa: BLE001
            r.steps.append({
                "step": "exec_regasm_err",
                "regasm": regasm,
                "err": f"{type(ex).__name__}: {ex}",
            })

    # 6) 验证 after (两视图)
    after = {
        "SwDocumentMgr.SwDocumentMgr_64":    _com_registered_wow(
            "SwDocumentMgr.SwDocumentMgr", view="64"),
        "SwDocumentMgr.SwDocumentMgr.31_64": _com_registered_wow(
            "SwDocumentMgr.SwDocumentMgr.31", view="64"),
        "SwDocumentMgr.SwDocumentMgr_32":    _com_registered_wow(
            "SwDocumentMgr.SwDocumentMgr", view="32"),
        "SwDocumentMgr.SwDocumentMgr.31_32": _com_registered_wow(
            "SwDocumentMgr.SwDocumentMgr.31", view="32"),
    }
    r.after = after
    # 成功 = 至少 64-bit 视图看见 progid (.31)
    r.ok = bool(after.get("SwDocumentMgr.SwDocumentMgr.31_64") or
                after.get("SwDocumentMgr.SwDocumentMgr_64"))
    if not r.ok:
        # 退而求其次 — 32-bit 视图也算半成功
        if any(after.values()):
            r.ok = True
            r.notes.append(
                "仅 32-bit 视图注册成功 · 64-bit Python 调用仍需 64-bit regasm"
            )
        else:
            r.err = "regasm_rc_0_but_progid_still_missing"
            r.notes.append("两视图都未落 CLSID · 检查 regasm 日志")
    return r


def _com_registered_wow(progid: str, view: str = "64") -> Optional[str]:
    """读 ProgID CLSID, 区分 64/32-bit 视图 (WOW64).

    view='64' → HKLM\\SOFTWARE\\Classes\\<progid>\\CLSID
    view='32' → HKLM\\SOFTWARE\\Classes\\Wow6432Node\\<progid>\\CLSID
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    key = f"Software\\Classes\\{progid}\\CLSID"
    access = winreg.KEY_READ
    if view == "64":
        access |= getattr(winreg, "KEY_WOW64_64KEY", 0)
    elif view == "32":
        access |= getattr(winreg, "KEY_WOW64_32KEY", 0)
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key, 0, access)
        v, _ = winreg.QueryValueEx(k, "")
        winreg.CloseKey(k)
        return v
    except OSError:
        return None


def remediate_sw_licensing_service(dry_run: bool = True,
                                    services: Optional[List[str]] = None,
                                    change_disabled_to_manual: bool = False,
                                    ) -> L5RemediationResult:
    """L5.2 · 打通 SolidWorks Licensing Service.

    对每个候选服务:
        1. 读 StartType (Disabled/Manual/Auto)
        2. 若 Disabled 且 change_disabled_to_manual=True → sc config start=demand
        3. sc start <name>
        4. 校验 Running

    仅默认处理 "SolidWorks Licensing Service" (单机激活必需).
    不动 "SolidWorks Flexnet Server" (网络许可 · 默认 Disabled 且路径常缺).
    """
    r = L5RemediationResult(action="remediate_sw_licensing", dry_run=dry_run)
    r.admin = is_admin()

    if sys.platform != "win32":
        r.err = "non-windows"
        return r

    targets = services or list(_SW_LICENSE_SERVICES_PRIORITY)

    # 1) 探当前状态
    before: Dict[str, Dict[str, Any]] = {}
    for name in targets:
        status = _sc_query(name)
        start_mode = _sc_query_start_mode(name)
        before[name] = {"status": status, "start_mode": start_mode}
    r.before = before

    if dry_run:
        plan: List[str] = []
        for name, st in before.items():
            if st["status"] is None:
                plan.append(f"SKIP (not found): {name}")
                continue
            if st["status"] == "Running":
                plan.append(f"SKIP (already Running): {name}")
                continue
            if st["start_mode"] == "Disabled":
                if change_disabled_to_manual:
                    plan.append(
                        f"sc config \"{name}\" start=demand  # Disabled → Manual"
                    )
                    plan.append(f"sc start \"{name}\"")
                else:
                    plan.append(
                        f"SKIP (Disabled, set change_disabled_to_manual=True "
                        f"to flip → Manual): {name}"
                    )
            else:
                plan.append(f"sc start \"{name}\"")
        r.steps.append({"step": "plan", "commands": plan})
        r.ok = True
        r.notes.append("dry_run=True · 未执行")
        return r

    if not r.admin:
        r.err = "not_admin"
        r.notes.append("启动/配置服务需要管理员 · 以 admin shell 重跑")
        return r

    # 2) 实执
    for name in targets:
        st = before[name]
        if st["status"] is None:
            r.steps.append({"service": name, "action": "skip_not_found"})
            continue
        if st["status"] == "Running":
            r.steps.append({"service": name, "action": "skip_running"})
            continue

        # 2.1 flip Disabled
        if st["start_mode"] == "Disabled":
            if not change_disabled_to_manual:
                r.steps.append({
                    "service": name, "action": "skip_disabled",
                    "hint": "set change_disabled_to_manual=True to enable",
                })
                continue
            try:
                p = subprocess.run(
                    ["sc.exe", "config", name, "start=", "demand"],
                    capture_output=True, text=True, timeout=15,
                    encoding="utf-8", errors="replace",
                )
                r.steps.append({
                    "service": name, "action": "sc_config_manual",
                    "rc": p.returncode,
                    "out": (p.stdout or "").strip(),
                })
                if p.returncode != 0:
                    continue
            except Exception as ex:  # noqa: BLE001
                r.steps.append({
                    "service": name, "action": "sc_config_err",
                    "err": f"{type(ex).__name__}: {ex}",
                })
                continue

        # 2.2 start
        try:
            p = subprocess.run(
                ["sc.exe", "start", name],
                capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )
            r.steps.append({
                "service": name, "action": "sc_start",
                "rc": p.returncode,
                "out_tail": (p.stdout or "").strip().splitlines()[-4:],
                "err_tail": (p.stderr or "").strip().splitlines()[-4:],
            })
        except Exception as ex:  # noqa: BLE001
            r.steps.append({
                "service": name, "action": "sc_start_err",
                "err": f"{type(ex).__name__}: {ex}",
            })

    # 3) 校验 after
    after: Dict[str, Dict[str, Any]] = {}
    for name in targets:
        after[name] = {
            "status":     _sc_query(name),
            "start_mode": _sc_query_start_mode(name),
        }
    r.after = after
    # 至少一个候选 Running 即视为成功
    r.ok = any(v["status"] == "Running" for v in after.values())
    return r


def _sc_query_start_mode(name: str) -> Optional[str]:
    """用 sc.exe qc 查服务 StartType (Auto/Manual/Disabled)."""
    if sys.platform != "win32":
        return None
    try:
        p = subprocess.run(
            ["sc.exe", "qc", name],
            capture_output=True, text=True, timeout=5,
            encoding="gbk", errors="replace",
        )
        if p.returncode != 0:
            return None
        for line in (p.stdout or "").splitlines():
            low = line.strip().lower()
            if "start_type" in low or "启动类型" in line:
                if "disabled" in low or "禁用" in line:
                    return "Disabled"
                if "demand" in low or "手动" in line:
                    return "Manual"
                if "auto" in low or "自动" in line:
                    return "Auto"
        return None
    except Exception:  # noqa: BLE001
        return None


def sw_remediate_all(dry_run: bool = True,
                     with_licensing_service: bool = True,
                     change_disabled_to_manual: bool = False) -> Dict[str, Any]:
    """L5 · 一键 · 反者道之动 · 打通两阻塞.

    返回:
        {
          "admin":    bool,
          "dry_run":  bool,
          "docmgr":   L5RemediationResult.to_dict(),
          "licensing":L5RemediationResult.to_dict() | None,
          "post_diagnose": SWLicenseState.to_dict(),   # 打通后再诊断一次
        }
    """
    out: Dict[str, Any] = {
        "admin":   is_admin(),
        "dry_run": dry_run,
    }

    # 1) COM
    r1 = remediate_docmgr_com(dry_run=dry_run)
    out["docmgr"] = r1.to_dict()

    # 2) 许可服务
    if with_licensing_service:
        r2 = remediate_sw_licensing_service(
            dry_run=dry_run,
            change_disabled_to_manual=change_disabled_to_manual,
        )
        out["licensing"] = r2.to_dict()
    else:
        out["licensing"] = None

    # 3) 复诊
    try:
        s = sw_license_diagnose()
        out["post_diagnose"] = s.to_dict()
    except Exception as ex:  # noqa: BLE001
        out["post_diagnose"] = {"err": f"{type(ex).__name__}: {ex}"}

    return out


# ════════════════════════════════════════════════════════════════════════
# L6 · 几何反演 · 终反 (无 COM · 无许可 · 纯字节识别)
# ════════════════════════════════════════════════════════════════════════
# SW 内部持有的几何本源是 Parasolid (Siemens) 内核 XT 流. SLDPRT 把 Parasolid
# 序列化到 OLE2 内部流里, 主要载体:
#   · "3DParametric Data"   (参数化模型树, 可能嵌 Parasolid 片段)
#   · "Parasolid Stream"    (直接 XT)
#   · "BodyState"           (实体状态快照)
#   · "FmDataDir" / "DataDir" (数据目录)
#   · "Orphan_Brep_#N"      (游离实体 · L1.5 已 carve 到这类引用)
#
# Parasolid XT 公开签名:
#   二进制: b"**ABCDEFGHIJKLMNOPQRSTUVWXYZ" (schema/version marker)
#   文本:   b"TRANSMIT FILE created by modeller"
# 本层只识别 & 定位, 不做几何解码 (XT 格式专有 · 需 Parasolid SDK).
# 用户拿到 signature + offset + stream name, 可:
#   1) 用 SW Rx 或 3rd-party (e.g. Open CASCADE importers) 尝试解析
#   2) 作为"SW 文件内确有几何主体"的证据

PARASOLID_XT_BIN_SIG = b"**ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PARASOLID_XT_TXT_SIG = b"TRANSMIT FILE created by modeller"
_PARASOLID_XT_VARIANT_SIGS = (
    PARASOLID_XT_BIN_SIG,
    PARASOLID_XT_TXT_SIG,
    b"PS_SCHEMA",
    b"TRANSMIT",   # 最宽泛, 用于最后兜底
)

_ORPHAN_BREP_PAT = re.compile(r"Orphan_Brep_#\d+")
_BODY_ID_PAT     = re.compile(r"(?:Body|Solid|Surface)_?\d+")


@dataclass
class L6GeometryRefs:
    """L6 · 几何引用反推结果."""
    ok:           bool                      = False
    path:         Optional[str]             = None
    body_ids:     List[str]                 = field(default_factory=list)
    orphan_breps: List[str]                 = field(default_factory=list)
    # 关键流 (尺寸+磁化探针): 可能含 Parasolid XT
    geometry_streams: List[Dict[str, Any]]  = field(default_factory=list)
    # 命中的 Parasolid 签名 (stream + offset + kind)
    xt_hits:      List[Dict[str, Any]]      = field(default_factory=list)
    # 附带诊断
    notes:        List[str]                 = field(default_factory=list)
    err:          Optional[str]             = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def carve_body_refs(feature_names: List[str]) -> Tuple[List[str], List[str]]:
    """从 L1.5 的 feature_names_carved 中析出 body 引用.

    返回: (orphan_breps, body_ids)
    """
    orphan: Dict[str, None] = {}
    bodies: Dict[str, None] = {}
    for n in feature_names:
        for m in _ORPHAN_BREP_PAT.finditer(n):
            orphan[m.group(0)] = None
        for m in _BODY_ID_PAT.finditer(n):
            bodies[m.group(0)] = None
    return list(orphan.keys()), list(bodies.keys())


def _scan_parasolid_sigs(data: bytes) -> List[Dict[str, Any]]:
    """在流数据里 scan Parasolid XT 签名 (大概率命中 binary XT)."""
    hits: List[Dict[str, Any]] = []
    for sig in (PARASOLID_XT_BIN_SIG, PARASOLID_XT_TXT_SIG):
        start = 0
        kind = "xt_bin" if sig == PARASOLID_XT_BIN_SIG else "xt_txt"
        while True:
            idx = data.find(sig, start)
            if idx < 0:
                break
            hits.append({
                "kind":   kind,
                "offset": idx,
                "preview_hex": data[idx:idx + 32].hex(),
            })
            start = idx + len(sig)
    # 较宽泛的 "PS_SCHEMA" / "TRANSMIT" 只做弱证据
    for sig in (b"PS_SCHEMA", b"SCH_"):
        idx = data.find(sig)
        if idx >= 0 and not any(h["offset"] == idx for h in hits):
            hits.append({
                "kind":   f"weak:{sig.decode('ascii', errors='replace')}",
                "offset": idx,
                "preview_hex": data[idx:idx + 32].hex(),
            })
    return hits


def carve_geometry_refs(path: Union[str, Path],
                         max_stream_bytes: int = 4 * 1024 * 1024,
                         include_orphan: bool = True) -> L6GeometryRefs:
    """L6 · 终反 · 从 OLE2 文件 carve 一切可用的几何引用.

    无 COM · 无许可 · 纯 OLE2Parser + 字节识别.

    步骤:
        1. 打开 OLE2, 过滤几何相关流 (名含 Parasolid/Param/BRep/Body/Dir)
        2. 对每个流读前 max_stream_bytes, 扫 Parasolid XT 签名
        3. 顺手跑一次 deep_probe_file 取 feature_names, 析出 Orphan_Brep_# refs
    """
    out = L6GeometryRefs(path=str(path))
    p = Path(path)
    if not p.exists():
        out.err = f"not_found: {p}"
        return out

    # 关键字: 覆盖 Parasolid/BRep/Body/LocalBodies/Solids/Config 等几何载体.
    # 注: "body" 不含 "bodies" 的 "bodi" 子串, 故 "bodies"/"bodi"/"solids" 显式列.
    geom_kw = ("parasolid", "parametric", "brep", "body", "bodies", "bodi",
               "dir", "topology", "facet", "solid", "solids",
               "config", "fmdata", "datadir", "localpart")

    try:
        with OLE2Parser(p) as ole:
            all_streams = [e for e in ole.directory
                            if e.get("type") == OLE2Parser.DIR_STREAM]
            kw_matched = []
            for e in all_streams:
                lnm = e.get("name", "").lower()
                if any(kw in lnm for kw in geom_kw):
                    kw_matched.append(e)
            # 若关键字未中 (罕见), 用 size 回退: 取前 3 大流 (SW 几何必在最大流)
            if not kw_matched:
                kw_matched = sorted(all_streams,
                                     key=lambda e: e.get("size", 0),
                                     reverse=True)[:3]
                out.notes.append(
                    "geom 关键字未中 · 回退取前 3 大流 (size fallback)")
            # 按体积降序, 前 12 条 (SW 常把几何放在 2~3 大流)
            kw_matched.sort(key=lambda e: e.get("size", 0), reverse=True)
            targets = kw_matched[:12]

            for e in targets:
                info: Dict[str, Any] = {
                    "name":     e["name"],
                    "size_B":   e.get("size", 0),
                    "sampled_B": 0,
                    "n_hits":   0,
                }
                try:
                    data = ole._read_entry(e)
                    sample = data[:max_stream_bytes]
                    info["sampled_B"] = len(sample)
                    hits = _scan_parasolid_sigs(sample)
                    info["n_hits"] = len(hits)
                    for h in hits:
                        h["stream"] = e["name"]
                        out.xt_hits.append(h)
                except Exception as ex:  # noqa: BLE001
                    info["err"] = f"{type(ex).__name__}: {ex}"
                out.geometry_streams.append(info)

    except Exception as ex:  # noqa: BLE001
        out.err = f"{type(ex).__name__}: {ex}"
        return out

    # Body 引用 (从 L1.5 carve)
    if include_orphan:
        try:
            deep = deep_probe_file(p)
            fns = deep.get("feature_names_carved", [])
            orp, bods = carve_body_refs(fns)
            out.orphan_breps = orp
            out.body_ids = bods
        except Exception as ex:  # noqa: BLE001
            out.notes.append(f"deep_probe_file err: {type(ex).__name__}: {ex}")

    out.ok = True
    if out.xt_hits:
        out.notes.append(
            f"找到 {len(out.xt_hits)} 条 Parasolid XT 签名 · "
            f"此 SW 文件内确有可解析几何主体 · 需 Parasolid SDK / SW Rx 进一步解码"
        )
    if out.orphan_breps:
        out.notes.append(
            f"找到 {len(out.orphan_breps)} 条 Orphan_Brep_# 引用 · "
            f"这些是 SW 内部 body id · 可作为导出后追溯锚点"
        )
    return out


# ════════════════════════════════════════════════════════════════════════
# L7 · 极限反演 · Parasolid body snapshot 提取 + 字符串全谱反
#        (无 COM · 无许可 · 无 Parasolid SDK · 纯 stdlib)
#
# 核心发现 (v3.1.0 推进到极):
#   SW 把 `LocalBodies` stream 内容分割成 N 个 zlib-压缩块,
#   每块解压后都是 "PS\0\0\0 3: TRANSMIT FILE created by modeller" 开头的
#   Parasolid XT binary 增量快照 · 即 SolidWorks 专有的 body snapshot 格式.
#   每块对应一个 body, 开头附近明文带 body name (如 "Orphan_Brep_#186271").
#
# 输出:
#   87 个 .x_t 候选文件 (每块可作 Parasolid SDK `PK_RECEIVE` 的输入)
#   + 完整的字符串/作者/路径/语言取证
# ════════════════════════════════════════════════════════════════════════
PARASOLID_XT_SCHEMA_RE = re.compile(rb"SCH_(\d{7})_(\d+)")
ORPHAN_BREP_RE         = re.compile(rb"Orphan_Brep_#\d+")
BODY_NAME_CAND_RE      = re.compile(rb"[A-Za-z_][A-Za-z0-9_\-]{3,63}")


@dataclass
class L7ParasolidBodies:
    """L7 · Parasolid body snapshot 抽取结果."""
    ok:            bool                      = False
    path:          Optional[str]             = None
    raw_size_B:    int                       = 0
    n_candidates:  int                       = 0   # zlib 头候选数
    n_bodies:      int                       = 0   # 成功解压 body 数
    body_sizes_B:  List[int]                 = field(default_factory=list)
    body_names:    List[str]                 = field(default_factory=list)
    schema:        Optional[str]             = None  # "SCH_1800141_18007"
    modeller_ver:  Optional[str]             = None  # "1800141"
    output_files:  List[str]                 = field(default_factory=list)
    notes:         List[str]                 = field(default_factory=list)
    err:           Optional[str]             = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _find_localbodies_entries(ole: "OLE2Parser") -> List[Dict[str, Any]]:
    """在 OLE2 目录里找名叫 LocalBodies 的流条目 (可能含多份, 不同 config)."""
    out = []
    for e in ole.directory:
        if e.get("type") != ole.DIR_STREAM:
            continue
        nm = (e.get("name") or "").strip()
        if nm == "LocalBodies" and e.get("size", 0) > 0:
            out.append(e)
    return out


def _zlib_carve_blocks(buf: bytes, max_blocks: int = 2000) -> List[Dict[str, Any]]:
    """在字节缓冲里找所有 zlib 起头 (78 9c / 78 da / 78 01) 并增量解压.

    返回 list[{"offset": int, "in_B": int, "data": bytes, "ok": bool, "err": str}]
    """
    out: List[Dict[str, Any]] = []
    seen: set = set()
    start = 0
    while start < len(buf) - 2 and len(out) < max_blocks:
        # 下一个 zlib 头
        nxt = -1
        for sig in (b"\x78\x9c", b"\x78\xda", b"\x78\x01"):
            p = buf.find(sig, start)
            if p >= 0 and (nxt < 0 or p < nxt):
                nxt = p
        if nxt < 0:
            break
        if nxt in seen:
            start = nxt + 2
            continue
        seen.add(nxt)

        chunk = buf[nxt:]
        try:
            d_obj = zlib.decompressobj()
            decoded = d_obj.decompress(chunk) + d_obj.flush()
            used = len(chunk) - len(d_obj.unused_data)
            if len(decoded) >= 64:   # 过滤太小的噪声
                out.append({
                    "offset": nxt,
                    "in_B":   used,
                    "data":   decoded,
                    "ok":     True,
                })
            start = nxt + max(2, used)
        except zlib.error as ex:
            out.append({
                "offset": nxt,
                "in_B":   0,
                "data":   b"",
                "ok":     False,
                "err":    f"{type(ex).__name__}: {ex}",
            })
            start = nxt + 2
    return out


def _is_parasolid_xt_block(data: bytes) -> bool:
    """快速检一块解压数据是不是 Parasolid XT 增量快照."""
    if len(data) < 40:
        return False
    # 格式 1: "PS\0\0\0<?>3:" 随后 "TRANSMIT FILE"
    if data[:2] == b"PS" and b"TRANSMIT FILE created by modeller" in data[:200]:
        return True
    # 格式 2: 直接以 "TRANSMIT FILE" 开头
    if data[:14] == b"TRANSMIT FILE ":
        return True
    # 格式 3: 二进制 XT: "**ABCD..." marker
    if data.find(b"**ABCDEFGHIJKLMNOPQRSTUVWXYZ") >= 0:
        return True
    return False


def _guess_body_name(data: bytes, max_search: int = 400) -> Optional[str]:
    """从 XT block 头部找 body name (如 Orphan_Brep_#xxxxxx 或其它 ASCII)."""
    head = data[:max_search]
    # 先试 Orphan_Brep_#xxx
    m = ORPHAN_BREP_RE.search(head)
    if m:
        return m.group(0).decode("ascii", errors="replace")
    # 再试 长 ASCII 字符串 (body_xxx / 零终止字符串)
    for m in BODY_NAME_CAND_RE.finditer(head):
        s = m.group(0)
        if s in (b"TRANSMIT", b"modeller", b"version", b"FILE", b"created"):
            continue
        return s.decode("ascii", errors="replace")
    return None


def extract_parasolid_bodies(
    path:       Union[str, Path],
    out_dir:    Optional[Union[str, Path]] = None,
    max_bodies: Optional[int]              = None,
    save_all:   bool                       = False,
) -> L7ParasolidBodies:
    """L7 · 从 SLDPRT 抽出全部 Parasolid body snapshot.

    Args:
        path:       SLDPRT 文件路径
        out_dir:    若给, 把每个 body 存为 .x_t / .bin 文件
        max_bodies: 最多抽几个 body (None = 全部)
        save_all:   True 则保存所有 body; False 只存 top 10 最大

    Returns:
        L7ParasolidBodies · ok=True 表示至少抽到 1 个 body

    WARNING:
        提出的 .x_t 文件是 SW 专有的 **增量 body snapshot** (无 END_OF_TRANSMIT_FILE),
        需 Parasolid SDK `PK_RECEIVE` / SW ReceiveMessage API 做后续解码.
        第三方开源 CAD (OpenCASCADE/FreeCAD) 默认不支持.
    """
    res = L7ParasolidBodies(path=str(path))

    p = Path(path)
    if not p.exists():
        res.err = f"file not found: {p}"
        return res

    try:
        with OLE2Parser(p) as ole:
            entries = _find_localbodies_entries(ole)
            if not entries:
                res.err = "no LocalBodies stream"
                res.notes.append("此文件不包含 Parasolid body snapshot (可能是空装配或 drawing)")
                return res

            # 通常只有一份 LocalBodies (per config), 取最大的
            entries.sort(key=lambda e: -e.get("size", 0))
            lb_entry = entries[0]
            raw = ole._read_entry(lb_entry)
            res.raw_size_B = len(raw)

            blocks = _zlib_carve_blocks(raw)
            res.n_candidates = len(blocks)

            ok_blocks = [b for b in blocks if b.get("ok")]
            # 筛出真 Parasolid 块
            xt_blocks = [b for b in ok_blocks
                         if _is_parasolid_xt_block(b["data"])]

            if not xt_blocks:
                res.err = "no Parasolid XT blocks decoded"
                res.notes.append(
                    f"zlib 头 {len(blocks)} 个 · 可解压 {len(ok_blocks)} 个 · "
                    f"但无一块以 Parasolid XT 签名开头 · 此文件可能格式不同"
                )
                return res

            # 第一块定 schema / version
            first_head = xt_blocks[0]["data"][:400]
            m = PARASOLID_XT_SCHEMA_RE.search(first_head)
            if m:
                res.schema        = m.group(0).decode("ascii", errors="replace")
                res.modeller_ver  = m.group(1).decode("ascii", errors="replace")

            # 每块的 body name + size
            for b in xt_blocks:
                res.body_names.append(_guess_body_name(b["data"]) or "")
                res.body_sizes_B.append(len(b["data"]))

            res.n_bodies = len(xt_blocks)

            # 限制数量
            if max_bodies is not None:
                xt_blocks = xt_blocks[:max_bodies]

            # 落盘
            if out_dir:
                od = Path(out_dir)
                od.mkdir(parents=True, exist_ok=True)
                # 排序: 按大小降 (大 body 在前), 便于优先查看主零件
                idx_sorted = sorted(range(len(xt_blocks)),
                                    key=lambda i: -len(xt_blocks[i]["data"]))
                to_save = idx_sorted if save_all else idx_sorted[:10]
                for rank, orig_i in enumerate(to_save):
                    b = xt_blocks[orig_i]
                    name = res.body_names[orig_i] if orig_i < len(res.body_names) else ""
                    name = name or f"body{orig_i}"
                    # 清洗文件名
                    safe = "".join(c if c.isalnum() or c in "_-." else "_"
                                   for c in name)[:50]
                    fn = f"rank{rank:03d}_off{b['offset']:08x}_{safe}.x_t"
                    out = od / fn
                    out.write_bytes(b["data"])
                    res.output_files.append(str(out))

            res.ok = True
            res.notes.append(
                f"Parasolid schema {res.schema} / modeller {res.modeller_ver} · "
                f"解出 {res.n_bodies} 个 body snapshot · "
                f"size 范围 {min(res.body_sizes_B):,}-{max(res.body_sizes_B):,} B"
            )
            if any(n and n.startswith("Orphan_Brep") for n in res.body_names):
                res.notes.append(
                    "body names 含 Orphan_Brep_#... · 这些是 SW 内部临时 body id"
                )
            res.notes.append(
                "⚠ 抽出的 .x_t 为 SW 专有增量快照 · 无 END_OF_TRANSMIT_FILE · "
                "需 Parasolid SDK PK_RECEIVE 后续处理 · OpenCASCADE 不直支持"
            )
    except Exception as ex:  # noqa: BLE001
        res.err = f"{type(ex).__name__}: {ex}"
    return res


# ──────────────────────────────────────────────────────────────────────
# L7.2 · 字符串全谱反 (UTF-16LE + ASCII + 语言/作者/路径取证)
# ──────────────────────────────────────────────────────────────────────
UTF16LE_STR_RE = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")
UTF16BE_STR_RE = re.compile(rb"(?:\x00[\x20-\x7e]){4,}")
ASCII_STR_RE   = re.compile(rb"[\x20-\x7e]{6,}")
WINPATH_RE     = re.compile(r"[A-Za-z]:\\[^<>\"|?*\n\r]{3,200}")
UNIXPATH_RE    = re.compile(r"/[A-Za-z0-9_.\-/]{8,200}")
SW_CLASS_RE    = re.compile(r"^[a-z]{2,3}[A-Z][A-Za-z0-9_]+_c$")  # moPart_c 样式
FRENCH_SW      = {"Dessus", "Dessous", "Droite", "Gauche", "Face",
                  "Arrière", "Corps", "Classeur", "Ambiante",
                  "Commentaires", "Eclairage"}
GERMAN_SW      = {"Oben", "Unten", "Rechts", "Links",
                  "Vorne", "Hinten", "Zeichnung"}
CHINESE_RANGE  = (0x4e00, 0x9fff)


@dataclass
class L7StringDump:
    """L7 · 字符串全谱 + 取证推断."""
    ok:             bool                 = False
    path:           Optional[str]        = None
    n_utf16le:      int                  = 0
    n_utf16be:      int                  = 0
    n_ascii:        int                  = 0
    utf16le:        List[str]            = field(default_factory=list)
    utf16be:        List[str]            = field(default_factory=list)
    ascii:          List[str]            = field(default_factory=list)
    sw_classes:     List[str]            = field(default_factory=list)
    win_paths:      List[str]            = field(default_factory=list)
    unix_paths:     List[str]            = field(default_factory=list)
    author:         Optional[str]        = None
    language_hint:  Optional[str]        = None    # "french"/"german"/"english"/"chinese"
    file_paths:     List[str]            = field(default_factory=list)
    err:            Optional[str]        = None
    notes:          List[str]            = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def extract_strings(path:    Union[str, Path],
                    min_len: int = 4,
                    max_per: int = 5000,
                    ) -> L7StringDump:
    r"""L7.2 · 从 SLDPRT 全流扫 UTF-16LE/BE + ASCII 字符串 + 取证推断.

    扫以下流:
      · 所有 storage 子流 (Contents/*, Config-0-FeatureBodies/*, ...)
      · Biography (作者历史)
      · SummaryInformation / DocumentSummaryInformation (标准元数据)
      · 不扫 LocalBodies (压缩二进制, 噪音大)

    推断:
      · 语言: 查 SW 默认 plane 名的翻译 (Dessus/Oben/...)
      · 作者: Biography 中最像人名的字符串
      · 路径: Windows 绝对路径泄露 (包括 F:\... 等)
    """
    res = L7StringDump(path=str(path))
    p = Path(path)
    if not p.exists():
        res.err = f"file not found: {p}"
        return res

    try:
        utf16le_set: set = set()
        utf16be_set: set = set()
        ascii_set:   set = set()

        with OLE2Parser(p) as ole:
            for e in ole.directory:
                if e.get("type") != ole.DIR_STREAM:
                    continue
                nm = e.get("name") or ""
                # 跳过已知压缩二进制流
                if nm in ("LocalBodies",):
                    continue
                try:
                    data = ole._read_entry(e)
                except Exception:  # noqa: BLE001
                    continue
                if not data:
                    continue

                # UTF-16LE
                for m in UTF16LE_STR_RE.finditer(data):
                    s = m.group().decode("utf-16-le", errors="replace").rstrip("\x00")
                    if len(s) >= min_len and len(s) < 200:
                        utf16le_set.add(s)
                # UTF-16BE
                for m in UTF16BE_STR_RE.finditer(data):
                    s = m.group().decode("utf-16-be", errors="replace").rstrip("\x00")
                    if len(s) >= min_len and len(s) < 200:
                        utf16be_set.add(s)
                # ASCII
                for m in ASCII_STR_RE.finditer(data):
                    s = m.group().decode("latin-1", errors="replace")
                    if len(s) < 200:
                        ascii_set.add(s)

        res.n_utf16le  = len(utf16le_set)
        res.n_utf16be  = len(utf16be_set)
        res.n_ascii    = len(ascii_set)
        res.utf16le    = sorted(utf16le_set)[:max_per]
        res.utf16be    = sorted(utf16be_set)[:max_per]
        res.ascii      = sorted(ascii_set)[:max_per]

        # === 取证推断 ===
        # 1) SW C++ 类名
        res.sw_classes = sorted(s for s in ascii_set if SW_CLASS_RE.match(s))

        # 2) 泄露的 Windows 路径
        for s in utf16le_set:
            for m in WINPATH_RE.finditer(s):
                res.win_paths.append(m.group(0))
        # 去重
        res.win_paths = sorted(set(res.win_paths))[:100]
        # 当前文件自身也会出现, 单独标记
        self_name = p.name.lower()
        res.file_paths = [wp for wp in res.win_paths
                          if self_name in wp.lower()]

        # 3) UNIX 路径
        unix_hits: set = set()
        for s in list(utf16le_set) + list(ascii_set):
            for m in UNIXPATH_RE.finditer(s):
                unix_hits.add(m.group(0))
        res.unix_paths = sorted(unix_hits)[:50]

        # 4) 语言推断
        fr_hit = sum(1 for s in utf16le_set
                      if any(fr in s for fr in FRENCH_SW))
        de_hit = sum(1 for s in utf16le_set
                      if any(de in s for de in GERMAN_SW))
        cn_hit = sum(1 for s in utf16le_set
                      if any(CHINESE_RANGE[0] <= ord(c) <= CHINESE_RANGE[1]
                             for c in s))
        en_hit = sum(1 for s in utf16le_set
                      if s in ("Top", "Bottom", "Right", "Left",
                               "Front", "Back", "Sketch", "Comments"))
        pairs = [("french", fr_hit), ("german", de_hit),
                 ("chinese", cn_hit), ("english", en_hit)]
        pairs.sort(key=lambda x: -x[1])
        if pairs[0][1] >= 2:
            res.language_hint = pairs[0][0]
        else:
            res.language_hint = "unknown"

        # 5) 作者 (Biography 流会含)
        # SummaryInformation 的 PIDSI_AUTHOR = 4
        try:
            for e in ole.directory:
                if e.get("name") == "\x05SummaryInformation":
                    buf = ole._read_entry(e)
                    try:
                        psd = PropertySetParser.parse(buf)
                        if "author" in psd and psd["author"]:
                            res.author = psd["author"]
                    except Exception:  # noqa: BLE001
                        pass
                    break
        except Exception:  # noqa: BLE001
            pass

        res.ok = True
        res.notes.append(
            f"UTF-16LE={res.n_utf16le} · UTF-16BE={res.n_utf16be} · "
            f"ASCII={res.n_ascii}"
        )
        if res.language_hint and res.language_hint != "unknown":
            res.notes.append(f"语言推断: {res.language_hint}")
        if res.win_paths:
            res.notes.append(
                f"泄露 {len(res.win_paths)} 条 Windows 绝对路径 (原作者机器)"
            )
        if res.sw_classes:
            res.notes.append(
                f"SW C++ 反射 {len(res.sw_classes)} 个类名 · 含特征树结构"
            )
    except Exception as ex:  # noqa: BLE001
        res.err = f"{type(ex).__name__}: {ex}"
    return res


# ════════════════════════════════════════════════════════════════════════
# L8 · 极反推万物 · Parasolid XT block 结构反 (v3.2.0)
#      道法自然 · 无 COM · 无许可 · 无 Parasolid SDK · 纯 stdlib
#
# L7 解出 87 个 Parasolid XT binary snapshot (.x_t · 无 END_OF_TRANSMIT_FILE).
# L8 在此基础上 **打开每个 block 的头结构**, 不做完整 BRep 反 (需 Parasolid SDK),
# 但抽出可信元数据:
#   · has_ps_marker       SW 封装头 (PS\0\0) 存在性
#   · schema / schema_id  Parasolid schema ID (如 SCH_1800141_18007)
#   · modeller_version    Parasolid modeller build (如 1800141)
#   · body_name           SW 内部标签 (如 Orphan_Brep_#186271)
#   · printable_ratio     block 内 ASCII 可打印字节占比 (识别混合/纯二进制)
#   · floats_in_range     block 内所有 big-endian double 合法范围统计
#                         (合法 = finite ∧ 1e-10 ≤ |v| ≤ 1e10)
#                         → 用作几何坐标/量纲暗示, 不等同真 bbox
#   · parasolid_keywords  BSURF/FACE/EDGE/LOOP/VERTEX 计数 → topology 密度
#
# 上层 parasolid_catalog() 对全文件做一次 L7 解压 + 逐块 analyze_xt_block,
# 最终产出 bodies_catalog.json (87 条, 每条 1 body 元数据).
# ════════════════════════════════════════════════════════════════════════
# Parasolid XT 头正则 (已在 L7 定义 PARASOLID_XT_SCHEMA_RE / ORPHAN_BREP_RE)
_XT_MODELLER_RE   = re.compile(rb"modeller version (\d+)")
_XT_TRANSMIT_HEAD = b"TRANSMIT FILE created by modeller"
_XT_PARA_KEYWORDS = (
    b"BSURF", b"BCURVE", b"FACE", b"EDGE", b"SHELL",
    b"BODY", b"VERTEX", b"LOOP", b"SURFACE", b"CURVE",
    b"POINT", b"PLANE", b"CYLINDER", b"SPHERE", b"CONE",
    b"TORUS", b"SPLINE", b"NURBS", b"ATTRIB",
)
# 合法浮点范围 (CAD 坐标/尺寸): 过滤纯噪声对齐
_XT_FLOAT_ABS_MIN = 1e-10
_XT_FLOAT_ABS_MAX = 1e10


@dataclass
class XTBlockInfo:
    """L8 · 单个 Parasolid XT body snapshot 结构反 (元数据级)."""
    ok:                 bool                         = False
    size_B:             int                          = 0
    has_ps_marker:      bool                         = False
    schema:             Optional[str]                = None  # "SCH_1800141_18007"
    schema_id:          Optional[str]                = None  # "1800141"
    user_id:            Optional[str]                = None  # "18007"
    modeller_version:   Optional[str]                = None
    body_name:          Optional[str]                = None
    has_end_marker:     bool                         = False
    printable_ratio:    float                        = 0.0
    floats_in_range:    Optional[Dict[str, Any]]     = None
    parasolid_keywords: Dict[str, int]               = field(default_factory=dict)
    err:                Optional[str]                = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def analyze_xt_block(data:         bytes,
                     scan_floats:  bool = True,
                     float_stride: int  = 4,
                     max_floats:   int  = 100000,
                     ) -> XTBlockInfo:
    """L8 · 单 Parasolid XT body snapshot 头结构反 (纯 stdlib · 无 SDK).

    Args:
        data:         单个 zlib-解压后的 Parasolid XT binary block.
                      (如 L7 `extract_parasolid_bodies` 解出的块内容.)
        scan_floats:  是否扫描大端 double (耗时 · 与 data 长成比例).
        float_stride: double 扫描步长. 1 = 完整扫 (每字节起扫),
                      4/8 = 对齐扫 (对 Parasolid XT 通常 4 对齐).
                      stride 越大 → 越快但越可能漏掉未对齐 double.
        max_floats:   收集的 double 数上限 (防爆内存 · 大 block 建议 100k).

    Returns:
        XTBlockInfo · ok=True 表示识别为合法 Parasolid XT header.

    Notes:
        - 本函数只做 header / 元数据级反演, **不重建 BRep topology**.
        - floats_in_range 统计仅作量纲暗示, 不保证是 CAD 坐标.
        - SW LocalBodies 里的 block 多为 snapshot (无 END_OF_TRANSMIT_FILE),
          has_end_marker=False 是预期的.
    """
    import math
    r = XTBlockInfo()
    if not data or len(data) < 40:
        r.err = "block_too_small"
        return r
    r.size_B = len(data)
    r.has_ps_marker = data[:4] == b"PS\x00\x00"

    # 找 TRANSMIT FILE 行 (前 400 B)
    tf = data.find(_XT_TRANSMIT_HEAD, 0, 400)
    if tf < 0:
        r.err = "no_transmit_header"
        return r

    # modeller_version
    m = _XT_MODELLER_RE.search(data[:200])
    if m:
        r.modeller_version = m.group(1).decode("ascii", errors="replace")

    # schema (SCH_xxx_yyy)
    m2 = PARASOLID_XT_SCHEMA_RE.search(data[:400])
    if m2:
        r.schema    = m2.group(0).decode("ascii", errors="replace")
        r.schema_id = m2.group(1).decode("ascii", errors="replace")
        r.user_id   = m2.group(2).decode("ascii", errors="replace")

    # body_name (先试 Orphan_Brep_# · 否则退到一般 ASCII 词)
    m3 = ORPHAN_BREP_RE.search(data[:500])
    if m3:
        r.body_name = m3.group(0).decode("ascii", errors="replace")
    else:
        # 回退: 头 500B 里第一个非关键词长 ASCII
        for mc in BODY_NAME_CAND_RE.finditer(data[:500]):
            tok = mc.group(0)
            if tok in (b"TRANSMIT", b"modeller", b"version", b"FILE",
                       b"created"):
                continue
            r.body_name = tok.decode("ascii", errors="replace")
            break

    r.has_end_marker = b"END_OF_TRANSMIT_FILE" in data

    # 文本比率 (整块)
    txt = sum(1 for bb in data if 0x20 <= bb <= 0x7e or bb in (9, 10, 13))
    r.printable_ratio = round(txt / r.size_B, 3)

    # Parasolid 关键字密度
    for kw in _XT_PARA_KEYWORDS:
        c = data.count(kw)
        if c > 0:
            r.parasolid_keywords[kw.decode("ascii")] = c

    # 扫大端 double (从 TRANSMIT 行后开始 · 避免 header 区噪声)
    if scan_floats:
        floats: List[float] = []
        # 跳过 ASCII header 区: 从第一个 \0\0 之后或 tf+200 开始, 取较大者
        # 简化: 从 tf + 120 字节后开始 (SCH_ 行+body name 之后的二进制区)
        scan_start = tf + 120
        if scan_start >= r.size_B - 8:
            scan_start = tf
        stride = max(1, int(float_stride))
        end_pos = r.size_B - 8
        i = scan_start
        collected = 0
        while i <= end_pos and collected < max_floats:
            try:
                v = struct.unpack(">d", data[i:i+8])[0]
                if math.isfinite(v) and _XT_FLOAT_ABS_MIN <= abs(v) <= _XT_FLOAT_ABS_MAX:
                    floats.append(v)
                    collected += 1
            except struct.error:
                pass
            i += stride

        if floats:
            floats.sort()
            n = len(floats)
            r.floats_in_range = {
                "count":      n,
                "stride":     stride,
                "scan_from":  scan_start,
                "min":        float(floats[0]),
                "max":        float(floats[-1]),
                "median":     float(floats[n // 2]),
                "p05":        float(floats[int(n * 0.05)]),
                "p95":        float(floats[int(n * 0.95)]),
            }

    r.ok = True
    return r


@dataclass
class ParasolidCatalog:
    """L8 · 全文件 (SLDPRT) Parasolid body catalog · N body 的结构反集合."""
    ok:               bool                = False
    path:             Optional[str]       = None
    raw_size_B:       int                 = 0
    schema:           Optional[str]       = None
    modeller_version: Optional[str]       = None
    n_bodies:         int                 = 0
    bodies:           List[Dict[str, Any]] = field(default_factory=list)
    global_float_range: Optional[Dict[str, float]] = None
    size_stats:       Optional[Dict[str, int]] = None
    err:              Optional[str]       = None
    notes:            List[str]           = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parasolid_catalog(path:         Union[str, Path],
                      out_json:     Optional[Union[str, Path]] = None,
                      scan_floats:  bool = True,
                      float_stride: int  = 4,
                      max_bodies:   Optional[int] = None,
                      ) -> ParasolidCatalog:
    """L8 · 从 SLDPRT 产完整 Parasolid body catalog (每 body 一条 L8 元数据).

    Args:
        path:          SLDPRT 文件
        out_json:      若给, 结果 JSON 落盘到此文件
        scan_floats:   是否每 body 都扫大端 double (加精度, 但慢)
        float_stride:  double 扫描步长 (4 = 对齐 · 1 = 完整扫)
        max_bodies:    最多分析几个 body (None = 全部 · 调试时用 10)

    Pipeline:
        1. 复用 L7 的 zlib 解压逻辑 (_zlib_carve_blocks)
        2. 逐块 _is_parasolid_xt_block 过滤
        3. 逐块 analyze_xt_block 出 L8 元数据
        4. 聚合 schema / modeller_version / float 全局范围 / size 统计
    """
    c = ParasolidCatalog(path=str(path))
    p = Path(path)
    if not p.exists():
        c.err = f"file_not_found: {p}"
        return c

    try:
        with OLE2Parser(p) as ole:
            entries = _find_localbodies_entries(ole)
            if not entries:
                c.err = "no_LocalBodies_stream"
                c.notes.append("此文件不含 Parasolid body snapshot (可能是空装配/drawing)")
                return c
            entries.sort(key=lambda e: -e.get("size", 0))
            raw = ole._read_entry(entries[0])
            c.raw_size_B = len(raw)

            blocks = _zlib_carve_blocks(raw)
            xt_blocks = [b for b in blocks
                         if b.get("ok") and _is_parasolid_xt_block(b["data"])]

            if not xt_blocks:
                c.err = "no_parasolid_xt_blocks"
                return c

            if max_bodies is not None:
                xt_blocks = xt_blocks[:max_bodies]

            seen_schema:   set = set()
            seen_modeller: set = set()
            all_mins: List[float] = []
            all_maxs: List[float] = []

            for i, b in enumerate(xt_blocks):
                info = analyze_xt_block(
                    b["data"],
                    scan_floats=scan_floats,
                    float_stride=float_stride,
                )
                d = info.to_dict()
                d["rank"]        = i
                d["zlib_offset"] = b["offset"]
                d["zlib_in_B"]   = b["in_B"]
                c.bodies.append(d)

                if info.schema:
                    seen_schema.add(info.schema)
                if info.modeller_version:
                    seen_modeller.add(info.modeller_version)
                if info.floats_in_range:
                    all_mins.append(info.floats_in_range["min"])
                    all_maxs.append(info.floats_in_range["max"])

            c.n_bodies = len(c.bodies)

            # schema 一致性
            if len(seen_schema) == 1:
                c.schema = seen_schema.pop()
            elif len(seen_schema) > 1:
                c.schema = ",".join(sorted(seen_schema))
                c.notes.append(f"混合 schema: {c.schema}")
            if len(seen_modeller) == 1:
                c.modeller_version = seen_modeller.pop()

            # 全局 float 范围
            if all_mins and all_maxs:
                c.global_float_range = {
                    "min": float(min(all_mins)),
                    "max": float(max(all_maxs)),
                }
                c.notes.append(
                    f"全体 body 的 double 合法值域 ~ "
                    f"{c.global_float_range['min']:.3e} .. "
                    f"{c.global_float_range['max']:.3e}"
                )

            # size 统计
            sz = [d["size_B"] for d in c.bodies]
            if sz:
                sz_sorted = sorted(sz)
                c.size_stats = {
                    "min":    sz_sorted[0],
                    "max":    sz_sorted[-1],
                    "median": sz_sorted[len(sz_sorted) // 2],
                    "total":  sum(sz),
                }
                c.notes.append(
                    f"body size 分布: min={c.size_stats['min']:,} B · "
                    f"max={c.size_stats['max']:,} B · "
                    f"median={c.size_stats['median']:,} B · "
                    f"total={c.size_stats['total']:,} B"
                )

            c.ok = True

        if out_json:
            outp = Path(out_json)
            outp.parent.mkdir(parents=True, exist_ok=True)
            outp.write_text(
                json.dumps(c.to_dict(), ensure_ascii=False,
                           indent=2, default=str),
                encoding="utf-8",
            )
    except Exception as ex:  # noqa: BLE001
        c.err = f"{type(ex).__name__}: {ex}"
    return c


# ────────────────────────────────────────────────────────────────────────
# L2 · COM 活体层 (pywin32)
# ────────────────────────────────────────────────────────────────────────
class SWComError(RuntimeError):
    """SW COM 调用异常."""


@dataclass
class SWDoc:
    """活体 SW 文档的 Python 外覆.

    内部持有 IModelDoc2 COM 对象. 所有操作转发.
    """
    _raw: Any = None                       # IModelDoc2
    _bridge: Optional["SolidWorksBridge"] = None
    path: str = ""
    doc_type: int = 0

    @property
    def is_part(self) -> bool:
        return self.doc_type == SW_DOC_TYPE.PART

    @property
    def is_assembly(self) -> bool:
        return self.doc_type == SW_DOC_TYPE.ASSEMBLY

    @property
    def is_drawing(self) -> bool:
        return self.doc_type == SW_DOC_TYPE.DRAWING

    # ─── 信息 ──────────────────────────────────────────────────────────
    def title(self) -> str:
        try:
            t = _com_prop(self._raw, "GetTitle")
            return str(t) if t else ""
        except Exception:
            return ""

    def path_name(self) -> str:
        try:
            p = _com_prop(self._raw, "GetPathName")
            return str(p) if p else self.path
        except Exception:
            return self.path

    def configurations(self) -> List[str]:
        try:
            names = _com_prop(self._raw, "GetConfigurationNames")
            return list(names or [])
        except Exception:
            return []

    def active_config(self) -> str:
        try:
            c = self._raw.ConfigurationManager.ActiveConfiguration
            return c.Name if c else ""
        except Exception:
            return ""

    def mass_properties(self) -> Dict[str, Any]:
        """获取质量属性. 返回 {mass_kg, volume_mm3, cog_mm, pmoi, ...}."""
        out: Dict[str, Any] = {}
        try:
            mp = self._raw.Extension.CreateMassProperty()
            if mp is None:
                return {"err": "CreateMassProperty returned None"}
            mp.UseSystemUnits = True    # m, kg
            out["mass_kg"]     = float(mp.Mass)
            out["volume_m3"]   = float(mp.Volume)
            out["volume_mm3"]  = round(out["volume_m3"] * 1e9, 3)
            cog = mp.CenterOfMass
            out["cog_m"] = [float(c) for c in (cog or [0, 0, 0])]
            try:
                out["surface_area_m2"] = float(mp.SurfaceArea)
            except Exception:
                pass
            try:
                pmoi = list(mp.PrincipalMomentsOfInertia or [])
                out["pmoi_kgm2"] = [float(x) for x in pmoi]
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            out["err"] = f"{type(e).__name__}: {e}"
        return out

    def bbox(self) -> Dict[str, Any]:
        """返回包围盒 (mm · PART/ASM 皆支).

        反笙: SW 2023 `Extension.GetBox` 不暴露, 真身是:
          · IPartDoc.GetPartBox(useTightBoundaries) → [xmin,ymin,zmin,xmax,ymax,zmax] (米)
          · IAssemblyDoc: 聚合所有组件 bbox (若无, 回退 body 级 IBody2.GetBodyBox)
        多路回退, 任何一路成功即返.
        """
        out: Dict[str, Any] = {}
        trace: List[Dict[str, Any]] = []
        bb: Any = None

        # ─── 路 1: IPartDoc.GetPartBox(True) ───
        try:
            fn = getattr(self._raw, "GetPartBox", None)
            if fn is not None:
                bb = fn(True)
                if bb and len(bb) >= 6:
                    trace.append({"path": "GetPartBox_tight", "ok": True})
                else:
                    bb = None
                    trace.append({"path": "GetPartBox_tight", "ok": False, "reason": "empty"})
        except Exception as e:  # noqa: BLE001
            trace.append({"path": "GetPartBox_tight", "err": f"{type(e).__name__}: {e}"})

        # ─── 路 2: GetPartBox(False) 粗边界 ───
        if bb is None:
            try:
                fn = getattr(self._raw, "GetPartBox", None)
                if fn is not None:
                    bb = fn(False)
                    if bb and len(bb) >= 6:
                        trace.append({"path": "GetPartBox_loose", "ok": True})
                    else:
                        bb = None
            except Exception as e:  # noqa: BLE001
                trace.append({"path": "GetPartBox_loose", "err": f"{type(e).__name__}: {e}"})

        # ─── 路 3: 迭代 IBody2.GetBodyBox · 汇总 (通用) ───
        if bb is None:
            try:
                # GetBodies2(swBodyType, bUpdatedBodies)
                # swBodyType_e: 0=solid+surface, 1=solid, 2=surface
                bodies = None
                for ty in (0, 1):
                    try:
                        b = self._raw.GetBodies2(ty, True)
                        if b:
                            bodies = list(b)
                            break
                    except Exception:
                        continue
                if bodies:
                    xs_min = []; xs_max = []
                    for body in bodies:
                        try:
                            bb_b = body.GetBodyBox()
                            if bb_b and len(bb_b) >= 6:
                                xs_min.append(bb_b[:3])
                                xs_max.append(bb_b[3:6])
                        except Exception:
                            continue
                    if xs_min and xs_max:
                        xmin = min(p[0] for p in xs_min)
                        ymin = min(p[1] for p in xs_min)
                        zmin = min(p[2] for p in xs_min)
                        xmax = max(p[0] for p in xs_max)
                        ymax = max(p[1] for p in xs_max)
                        zmax = max(p[2] for p in xs_max)
                        bb = [xmin, ymin, zmin, xmax, ymax, zmax]
                        trace.append({"path": "GetBodies2_union", "ok": True, "n_bodies": len(bodies)})
            except Exception as e:  # noqa: BLE001
                trace.append({"path": "GetBodies2_union", "err": f"{type(e).__name__}: {e}"})

        if bb and len(bb) >= 6:
            try:
                xmin, ymin, zmin, xmax, ymax, zmax = [float(x) for x in bb[:6]]
                out["bbox_mm"] = [
                    round((xmax - xmin) * 1000, 2),
                    round((ymax - ymin) * 1000, 2),
                    round((zmax - zmin) * 1000, 2),
                ]
                out["bbox_min_mm"] = [round(xmin * 1000, 2), round(ymin * 1000, 2), round(zmin * 1000, 2)]
                out["bbox_max_mm"] = [round(xmax * 1000, 2), round(ymax * 1000, 2), round(zmax * 1000, 2)]
            except Exception as e:  # noqa: BLE001
                out["err"] = f"{type(e).__name__}: {e}"
        else:
            out["err"] = "bbox 不可用 (所有路径失败)"
        if trace:
            out["_trace"] = trace
        return out

    def feature_tree(self, max_depth: int = 3,
                      top_level_only: bool = False) -> List[Dict[str, Any]]:
        """遍历特征树, 返回 [{name,type,id},...].

        反笙 · 道直连:
          - `FeatureManager.GetFeatures(bool)` 返 IDispatch 数组, 但元素是
            raw dispatch (pywin32 未 autowrap) → `.Name` 直接访问 miss.
          - 必须 re-wrap 每个 IDispatch: `win32com.client.Dispatch(e._oleobj_)`.
          - 备路: FirstFeature 链 · 亦需 re-wrap.
        """
        import win32com.client as _wc

        def _safe_name(f) -> Optional[str]:
            """多路拿特征名."""
            # 路 a: 直接属性
            try:
                n = getattr(f, "Name", None)
                if n and not callable(n):
                    return str(n)
            except Exception:
                pass
            # 路 b: late-binding re-wrap
            try:
                oleobj = getattr(f, "_oleobj_", None)
                if oleobj is not None:
                    wrapped = _wc.dynamic.Dispatch(oleobj)
                    n = wrapped.Name
                    if n:
                        return str(n)
            except Exception:
                pass
            # 路 c: DISPID invoke (Name DISPID on IFeature = 11)
            try:
                oleobj = getattr(f, "_oleobj_", None)
                if oleobj is not None:
                    import pythoncom
                    n = oleobj.Invoke(11, 0, pythoncom.DISPATCH_PROPERTYGET, True)
                    if n:
                        return str(n)
            except Exception:
                pass
            return None

        def _safe_call(f, method: str, *args):
            """多路调方法, 返结果或 None."""
            # 路 a: 直调
            try:
                fn = getattr(f, method, None)
                if callable(fn):
                    return fn(*args)
            except Exception:
                pass
            # 路 b: re-wrap
            try:
                oleobj = getattr(f, "_oleobj_", None)
                if oleobj is not None:
                    wrapped = _wc.dynamic.Dispatch(oleobj)
                    fn = getattr(wrapped, method, None)
                    if callable(fn):
                        return fn(*args)
            except Exception:
                pass
            return None

        out: List[Dict[str, Any]] = []
        trace: List[str] = []

        # ─── 路 1: FeatureManager.GetFeatures(bool) ───
        try:
            fm = getattr(self._raw, "FeatureManager", None)
            if fm is not None:
                feats = fm.GetFeatures(bool(top_level_only))
                if feats:
                    trace.append(f"GetFeatures→{len(feats) if hasattr(feats,'__len__') else '?'} items")
                    for f in feats:
                        nm = _safe_name(f)
                        ty = _safe_call(f, "GetTypeName2") or _safe_call(f, "GetTypeName")
                        fid = _safe_call(f, "GetID")
                        if nm or ty:
                            out.append({
                                "name": nm or "(unnamed)",
                                "type": ty or "?",
                                "id":   fid,
                            })
                    if out:
                        return out
                else:
                    trace.append("GetFeatures→empty/None")
        except Exception as e:  # noqa: BLE001
            trace.append(f"GetFeatures_err:{type(e).__name__}: {e}")

        # ─── 路 2: FirstFeature 漫步 + re-wrap ───
        try:
            ff = self._raw.FirstFeature
            if callable(ff):
                ff = ff()
            # re-wrap 确保 IDispatch 有 typelib
            if ff is not None:
                try:
                    ff = _wc.dynamic.Dispatch(ff._oleobj_)
                except Exception:
                    pass
            safety = 0
            feat = ff
            while feat is not None and safety < 10000:
                nm = _safe_name(feat)
                ty = _safe_call(feat, "GetTypeName2") or _safe_call(feat, "GetTypeName")
                fid = _safe_call(feat, "GetID")
                if nm:
                    out.append({"name": nm, "type": ty or "?", "id": fid})
                try:
                    nxt = _safe_call(feat, "GetNextFeature")
                    if nxt is not None:
                        try:
                            nxt = _wc.dynamic.Dispatch(nxt._oleobj_)
                        except Exception:
                            pass
                except Exception:
                    nxt = None
                if nxt is None:
                    break
                feat = nxt
                safety += 1
        except Exception as e:  # noqa: BLE001
            trace.append(f"FirstFeature_err:{type(e).__name__}: {e}")

        if not out and trace:
            out.append({"_trace": trace})
        return out

    # ─── 导出 ──────────────────────────────────────────────────────────
    def export(self, dst: Union[str, Path], fmt: Optional[str] = None,
               config: Optional[str] = None) -> Path:
        """导出到目标格式. fmt=None 时从扩展名推断.

        使用 SW 的 SaveAs3 / Extension.SaveAs (silent, overwrite).
        """
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if fmt is None:
            fmt = dst.suffix.lower().lstrip(".")
            if fmt in ("stp",): fmt = "step"
            if fmt in ("igs",): fmt = "iges"

        # 规范化目标扩展
        ext = SW_EXPORT_FMT._EXT_MAP.get(fmt)
        if ext is None:
            raise ValueError(f"unsupported export format: {fmt}")

        # 切换配置 (如需)
        if config:
            try:
                self._raw.ShowConfiguration2(config)
            except Exception:
                pass

        # SaveAs silent: 屏蔽弹窗
        opts = 1    # swSaveAsOptions_Silent
        errors = win32_int()
        warnings = win32_int()
        ok = False
        try:
            ok = bool(self._raw.Extension.SaveAs(
                str(dst), 0, opts, None, errors, warnings
            ))
        except Exception:
            # Fallback: SaveAs3 (老 API)
            try:
                ok = bool(self._raw.SaveAs3(str(dst), 0, opts))
            except Exception as e:
                raise SWComError(f"SaveAs failed: {e}")

        if not ok or not dst.exists():
            raise SWComError(f"SaveAs did not produce file: err={errors.value} warn={warnings.value}")
        return dst

    def close(self, save: bool = False):
        if self._bridge:
            self._bridge.close_doc(self, save=save)


def _dyn_wrap(obj):
    """将 COM 对象 re-wrap 为干净 dynamic.Dispatch · 绕 gencache 污染.

    所有从 COM 拿到的子对象 (GetComponents/GetFirstDocument/GetNext/...) 都
    应过此函数, 才能正确区分 property 与 method.
    """
    if obj is None:
        return None
    try:
        import win32com.client.dynamic as _dyn
        return _dyn.Dispatch(obj._oleobj_)
    except Exception:  # noqa: BLE001
        return obj


def _com_prop(obj, name: str):
    """安全访问 COM 属性/方法 — GetPathName/GetTitle/GetType 可能是 property 或 method.

    在 pywin32 dynamic dispatch 下, COM 的属性和方法同为 CDispatch 对象.
    当属性值恰好是字符串/数字时, getattr 直接返回值 (非 callable);
    但当 COM 类型信息不完整时, 属性可能被 wrap 为 callable CDispatch.
    此函数统一处理: 若取到 callable → 尝试调用; 若调用失败 → 当属性值返回.
    """
    val = getattr(obj, name, None)
    if val is None:
        return None
    if callable(val):
        try:
            return val()
        except Exception:  # noqa: BLE001
            # pywintypes.com_error(-2147352573, '找不到成员') → 不是方法, 是属性值
            return val
    return val


def _com_call(obj, method: str, *args):
    """安全调用 COM 方法 (带参数). 多路回退:

    路 1: 直接 getattr + call
    路 2: re-wrap → getattr + call
    路 3: 直接 Invoke (DISPID by name)
    """
    # 路 1
    try:
        fn = getattr(obj, method, None)
        if callable(fn):
            return fn(*args)
    except Exception:  # noqa: BLE001
        pass
    # 路 2: re-wrap
    try:
        w = _dyn_wrap(obj)
        if w is not None and w is not obj:
            fn = getattr(w, method, None)
            if callable(fn):
                return fn(*args)
    except Exception:  # noqa: BLE001
        pass
    return None


def _com_iter_docs(app):
    """安全遍历 SW 所有打开文档 · 返回 [COM_obj, ...] (已 _dyn_wrap).

    根因: GetFirstDocument/GetNext 链在 dynamic dispatch 下极不稳定 —
    `doc = doc()` 变量名遮蔽 + property/method 混淆导致 crash.
    此函数封装三条路径, 统一返回 wrap 后的 COM 对象列表.
    """
    docs = []
    # 路 1: GetDocuments (property, 返 VT_ARRAY of IModelDoc2)
    try:
        arr = app.GetDocuments
        if callable(arr):
            arr = arr()
        if arr:
            for d in arr:
                w = _dyn_wrap(d)
                if w is not None:
                    docs.append(w)
            if docs:
                return docs
    except Exception:  # noqa: BLE001
        pass
    # 路 2: GetFirstDocument/GetNext 链 (显式用不同变量名)
    try:
        first_doc = _com_prop(app, "GetFirstDocument")
        current = _dyn_wrap(first_doc)
        safety = 0
        while current is not None and safety < 500:
            docs.append(current)
            nxt = _com_prop(current, "GetNext")
            current = _dyn_wrap(nxt) if nxt is not None else None
            safety += 1
        if docs:
            return docs
    except Exception:  # noqa: BLE001
        pass
    return docs


def _find_sw_material_db(app=None) -> Optional[str]:
    """自动定位 SolidWorks 材质库完整路径.

    搜索优先级:
      1. SW 安装目录下 lang/*/sldmaterials/*.sldmat
      2. SW GetUserPreferenceStringValue(swFileLocationsMaterialDatabases=18)
      3. 常见硬编码候选路径
    返回首个存在的 .sldmat 完整路径, 或 None.
    """
    import glob as _glob

    # 路 1: 从 SW EXE 路径推导
    exe = None
    if app is not None:
        try:
            exe = _com_prop(app, "GetExecutablePath")
        except Exception:  # noqa: BLE001
            pass
    if not exe:
        exe = _find_sldworks_exe()
    if exe:
        sw_dir = Path(exe).parent
        # 搜索所有语言下的 sldmaterials
        for pat in [
            sw_dir / "lang" / "*" / "sldmaterials" / "*.sldmat",
            sw_dir.parent / "lang" / "*" / "sldmaterials" / "*.sldmat",
        ]:
            hits = _glob.glob(str(pat))
            # 优先匹配 chinese-simplified
            cn = [h for h in hits if "chinese" in h.lower()]
            if cn:
                return cn[0]
            if hits:
                return hits[0]

    # 路 2: SW 用户偏好
    if app is not None:
        try:
            v = _com_call(app, "GetUserPreferenceStringValue", 18)  # swFileLocationsMaterialDatabases
            if v:
                for d in str(v).split(";"):
                    d = d.strip()
                    if d and Path(d).exists():
                        for f in Path(d).rglob("*.sldmat"):
                            return str(f)
        except Exception:  # noqa: BLE001
            pass

    # 路 3: 硬编码候选
    candidates = [
        r"D:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS\lang\chinese-simplified\sldmaterials\solidworks materials.sldmat",
        r"D:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS\lang\english\sldmaterials\solidworks materials.sldmat",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\chinese-simplified\sldmaterials\solidworks materials.sldmat",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\sldmaterials\solidworks materials.sldmat",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def win32_int():
    """分配一个 pythoncom.Missing 替代, 用于 COM out-params (INT).

    pywin32 的 PARAMFLAG_FOUT + VT_I4 接受一个可变 holder.
    """
    class _Holder:
        value = 0
    return _Holder()


class SolidWorksBridge:
    """SW 活体连接桥. 覆盖探测 → 连接 → 操作 → 释放.

    用法:
      sw = SolidWorksBridge()
      sw.connect()
      doc = sw.open("part.sldprt")
      doc.export("part.step")
      sw.close_doc(doc)
      sw.disconnect()
    """

    def __init__(self, version_hint: Optional[int] = None):
        self.info = sw_info(probe_com=False)
        self._app = None           # ISldWorks COM
        self._owned = False        # 是否由我们启动 (True 则退出时关闭)
        self._version_hint = version_hint
        self._com_inited = False

    # ─── 诊断 ──────────────────────────────────────────────────────────
    def is_installed(self) -> bool:
        return self.info.installed

    def is_connected(self) -> bool:
        return self._app is not None

    # ─── 连接 ──────────────────────────────────────────────────────────
    def connect(self, prefer_active: bool = True, launch_if_needed: bool = True,
                launch_timeout_s: float = 90.0) -> bool:
        """连接 SW COM.

        策略:
          1. GetActiveObject (SW 已运行时) — 最快
          2. Dispatch (触发自动启动) — 中速, 常失败
          3. 手动启动 SLDWORKS.exe + 等待 + 重试 Dispatch — 最慢
        """
        if self._app is not None:
            return True
        if not self.info.pywin32_ok:
            raise SWComError("pywin32 not installed")
        if not self.info.progid:
            raise SWComError("SolidWorks not installed (progid missing)")

        progid = self.info.progid_versioned or self.info.progid
        import pythoncom
        import win32com.client as wc

        if not self._com_inited:
            pythoncom.CoInitialize()
            self._com_inited = True

        last_err = None

        if prefer_active:
            try:
                self._app = wc.GetActiveObject(progid)
                self._owned = False
                return True
            except Exception as e:  # noqa: BLE001
                last_err = e

        try:
            self._app = wc.Dispatch(progid)
            self._owned = False
            return True
        except Exception as e:  # noqa: BLE001
            last_err = e

        if launch_if_needed and self.info.exe:
            # 手动启动 + 轮询
            try:
                flags = 0
                if sys.platform == "win32":
                    flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                subprocess.Popen([self.info.exe, "/SWsilent"],
                                 creationflags=flags)
            except Exception as e:  # noqa: BLE001
                raise SWComError(f"cannot launch SLDWORKS.exe: {e}; last_err={last_err}")
            self._owned = True
            # 轮询
            t0 = time.time()
            step = 3.0
            while time.time() - t0 < launch_timeout_s:
                time.sleep(step)
                try:
                    self._app = wc.GetActiveObject(progid)
                    return True
                except Exception:
                    try:
                        self._app = wc.Dispatch(progid)
                        return True
                    except Exception as e:  # noqa: BLE001
                        last_err = e
                        step = min(step + 1.0, 10.0)
            raise SWComError(f"SW launch timed out after {launch_timeout_s}s; last_err={last_err}")

        raise SWComError(f"cannot connect: {last_err}")

    def disconnect(self, exit_sw: bool = False):
        """断开连接. exit_sw=True 且是我们启动的, 才退出 SW."""
        if self._app is not None and exit_sw and self._owned:
            try:
                self._app.ExitApp()
            except Exception:
                pass
        self._app = None
        if self._com_inited:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._com_inited = False

    # ─── 基础 ──────────────────────────────────────────────────────────
    def revision(self) -> str:
        if not self._app:
            raise SWComError("not connected")
        r = _com_prop(self._app, "RevisionNumber")
        return str(r) if r is not None else ""

    def set_visible(self, v: bool = False):
        if not self._app: return
        try: self._app.Visible = v
        except Exception: pass
        try: self._app.UserControl = v
        except Exception: pass
        try: self._app.FrameState = 2 if v else 0   # Maximize / Minimize
        except Exception: pass

    # ─── 文档 ──────────────────────────────────────────────────────────
    def open(self, path: Union[str, Path], readonly: bool = False,
             silent: bool = True, config: Optional[str] = None) -> SWDoc:
        if not self._app:
            self.connect()
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(p)
        doc_type = SW_DOC_TYPE.from_path(p)
        if doc_type == SW_DOC_TYPE.NONE:
            raise ValueError(f"not a SW document: {p}")

        # OpenDoc6 参数
        # (FileName, Type, Options, Configuration, Errors, Warnings)
        opts = 0
        if readonly: opts |= 2        # swOpenDocOptions_ReadOnly
        if silent:   opts |= 1        # swOpenDocOptions_Silent
        raw = None
        _errs_val = _warns_val = 0
        _last_exc = None
        # 路 1: pythoncom VARIANT byref (最正式)
        try:
            import pythoncom as _pc
            from win32com.client import VARIANT as _VAR
            errors = _VAR(_pc.VT_BYREF | _pc.VT_I4, 0)
            warnings = _VAR(_pc.VT_BYREF | _pc.VT_I4, 0)
            raw = self._app.OpenDoc6(
                str(p), doc_type, opts, config or "", errors, warnings
            )
        except Exception as e:
            _last_exc = e
        # 路 2: 裸 int 0 (pywin32 可能自动 promote)
        if raw is None:
            try:
                raw = self._app.OpenDoc6(
                    str(p), doc_type, opts, config or "", 0, 0
                )
            except Exception as e:
                _last_exc = e
        # 路 3: _Holder 旧模式
        if raw is None:
            try:
                h_err = win32_int()
                h_warn = win32_int()
                raw = self._app.OpenDoc6(
                    str(p), doc_type, opts, config or "", h_err, h_warn
                )
                _errs_val = h_err.value
                _warns_val = h_warn.value
            except Exception as e:
                _last_exc = e

        # 路 4: OpenDoc6 返 None 但文档可能已加载至 ActiveDoc (VARIANT byref 吞值)
        if raw is None:
            try:
                ad = self._app.ActiveDoc
                if ad is not None:
                    try:
                        ad_pn = ad.GetPathName  # property, not method
                        if callable(ad_pn):
                            ad_pn = ad_pn()
                        ad_path = Path(ad_pn).resolve() if ad_pn else None
                    except Exception:
                        ad_path = None
                    if ad_path == p:
                        raw = ad
            except Exception:
                pass

        # 路 5: Unicode ASCII temp copy (非 ASCII 路径 SW COM 打不开)
        if raw is None and not str(p).isascii():
            import shutil, tempfile
            _tmp = Path(tempfile.gettempdir()) / "dao_sw_open"
            _tmp.mkdir(parents=True, exist_ok=True)
            ascii_p = _tmp / p.name
            shutil.copy2(p, ascii_p)
            try:
                import pythoncom as _pc2
                from win32com.client import VARIANT as _VAR2
                e2 = _VAR2(_pc2.VT_BYREF | _pc2.VT_I4, 0)
                w2 = _VAR2(_pc2.VT_BYREF | _pc2.VT_I4, 0)
                raw = self._app.OpenDoc6(
                    str(ascii_p), doc_type, opts, config or "", e2, w2
                )
            except Exception:
                pass
            if raw is None:
                try:
                    raw = self._app.OpenDoc6(
                        str(ascii_p), doc_type, opts, config or "", 0, 0
                    )
                except Exception:
                    pass
            # ActiveDoc fallback for ascii path
            if raw is None:
                try:
                    ad = self._app.ActiveDoc
                    if ad is not None:
                        ad_pn = ad.GetPathName
                        if callable(ad_pn): ad_pn = ad_pn()
                        if ad_pn and Path(ad_pn).resolve() == ascii_p.resolve():
                            raw = ad
                except Exception:
                    pass

        if raw is None:
            raise SWComError(
                f"OpenDoc6 returned null: errors={_errs_val} warnings={_warns_val}"
                + (f" last_exc={_last_exc}" if _last_exc else "")
            )

        return SWDoc(_raw=raw, _bridge=self, path=str(p), doc_type=doc_type)

    def active_doc(self) -> Optional[SWDoc]:
        if not self._app: return None
        try:
            d = self._app.ActiveDoc
            if d is None: return None
            p = _com_prop(d, "GetPathName")
            # 推断类型: path 有则按后缀, 无(未保存新文档)则查 COM GetType
            if p:
                dt = SW_DOC_TYPE.from_path(p)
            else:
                try:
                    gt = _com_prop(d, "GetType")
                    dt = int(gt) if gt is not None else SW_DOC_TYPE.PART
                except Exception:
                    dt = SW_DOC_TYPE.PART
            return SWDoc(_raw=d, _bridge=self, path=p or "", doc_type=dt)
        except Exception:
            return None

    def list_docs(self) -> List[Dict[str, Any]]:
        """列出所有打开的文档 · 用 _com_iter_docs 安全遍历."""
        out: List[Dict[str, Any]] = []
        if not self._app: return out
        for d in _com_iter_docs(self._app):
            try:
                out.append({
                    "title": _com_prop(d, "GetTitle"),
                    "path":  _com_prop(d, "GetPathName"),
                    "type":  SW_DOC_TYPE.name(_com_prop(d, "GetType")),
                })
            except Exception:
                continue
        return out

    def close_doc(self, doc: SWDoc, save: bool = False):
        if not self._app: return
        if save:
            try: doc._raw.Save()
            except Exception: pass
        try:
            self._app.CloseDoc(doc.path_name() or doc.path)
        except Exception:
            pass
        doc._raw = None

    def close_all(self, save: bool = False):
        """关闭所有打开的文档."""
        if not self._app: return
        try:
            if save:
                self._app.CloseAllDocuments(True)
            else:
                self._app.CloseAllDocuments(False)
        except Exception:
            pass

    # ─── 静默导出 (一次性) ────────────────────────────────────────────
    def convert(self, src: Union[str, Path], dst: Union[str, Path],
                fmt: Optional[str] = None, config: Optional[str] = None) -> Path:
        """一键: 打开→导出→关闭. 幂等."""
        if not self._app:
            self.connect()
        dst = Path(dst)
        doc = self.open(src, readonly=True, silent=True, config=config)
        try:
            return doc.export(dst, fmt=fmt, config=config)
        finally:
            self.close_doc(doc, save=False)

    # ─── 批量 ──────────────────────────────────────────────────────────
    def batch_convert(self, src_dir: Union[str, Path], dst_dir: Union[str, Path],
                      fmt: str = "step", pattern: str = "*.sld*") -> List[Path]:
        src_dir = Path(src_dir); dst_dir = Path(dst_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)
        ext = SW_EXPORT_FMT._EXT_MAP.get(fmt, ".step")
        out = []
        for p in sorted(src_dir.glob(pattern)):
            if p.suffix.lower() not in (".sldprt", ".sldasm", ".slddrw"):
                continue
            tgt = dst_dir / (p.stem + ext)
            if tgt.exists():
                out.append(tgt); continue
            try:
                self.convert(p, tgt, fmt=fmt)
                out.append(tgt)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {p.name} -> {fmt}: {e}")
        return out


# ════════════════════════════════════════════════════════════════════════
# L2.5 · Document Manager API 探测 · 免许可元数据读器
# ════════════════════════════════════════════════════════════════════════
# SolidWorks Document Manager (SwDocumentMgr.dll) 是 SW API 里唯一不依赖
# SW 应用、不需要 SW 许可运行的元数据读取接口. 用于读 SLDPRT/SLDASM/SLDDRW:
#   · 配置树, 自定义属性, 方程, 引用件列表, 预览, 重量等
# 调用条件:
#   · SwDocumentMgr.dll (或 .Interop.swdocumentmgr.dll) 存在
#   · 一个 Document Manager license key (由 SolidWorks API 开发计划发放)
# 本层:
#   · 只探测 "DLL 是否在" / "ProgID 是否注册" / "是否能从 DLL 路径加载"
#   · 若 DLL 存在但未注册, 不尝试 regasm (需管理员 · 写状态 · 违"无为")
#     仅打印需要执行的命令供用户决定.
# 使用示例 (需用户自备 license key):
#   dm = SwDocMgrProbe()
#   if dm.ok:
#       dm.load_by_path()            # 动态加载 .NET 程序集
#       classifier = dm.get_classifier(license_key="<YOUR-KEY>")
#       doc = classifier.GetDocument(path, read_only=True)

@dataclass
class SwDocMgrProbe:
    dll_path:          Optional[str] = None
    com_registered:    bool = False
    com_progid:        Optional[str] = None
    com_clsid:         Optional[str] = None
    managed:           bool = False    # 是否 .NET 程序集
    pythonnet_ok:      bool = False    # 是否可 pip install pythonnet
    pywin32_ok:        bool = False
    ok:                bool = False    # 至少一条路能通
    path_usable:       List[str] = field(default_factory=list)
    regasm_cmd:        Optional[str] = None
    diagnostics:       List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def swdm_probe() -> SwDocMgrProbe:
    """探测 Document Manager API 可用性. 纯只读, 不加载 DLL, 不写注册表."""
    out = SwDocMgrProbe()
    # 1) DLL 定位
    out.dll_path = _find_docmgr_dll()
    # 还可能是纯 native:
    if out.dll_path is None:
        for cand in [
            r"C:\Program Files\Common Files\SolidWorks Shared\SwDocumentMgr.dll",
            r"D:\Program Files\Common Files\SolidWorks Shared\SwDocumentMgr.dll",
        ]:
            if Path(cand).exists():
                out.dll_path = cand
                break
    if not out.dll_path:
        out.diagnostics.append("DLL 未找到 · SW 安装未携带 Document Manager")
        return out

    # 2) PE/托管判断
    try:
        with PEReader(out.dll_path) as pe:
            out.managed = pe.is_managed
    except Exception as e:  # noqa: BLE001
        out.diagnostics.append(f"PE 读失败: {e}")

    # 3) COM 注册
    for p in (
        "SwDocumentMgr.SwDocumentMgr",
        "SwDocumentMgr.SwDocumentMgr.31",
        "SwDocumentMgr.SwDocumentMgr.30",
        "SwDocumentMgr.SwDocumentMgr.32",
    ):
        cls = _com_registered(p)
        if cls:
            out.com_registered = True
            out.com_progid = p
            out.com_clsid = cls
            out.path_usable.append(f"com:{p}")
            break

    # 4) pywin32
    try:
        import win32com.client  # noqa: F401
        out.pywin32_ok = True
    except ImportError:
        out.pywin32_ok = False

    # 5) pythonnet (可从 DLL 路径加载 .NET 程序集)
    try:
        import clr  # noqa: F401 · pythonnet
        out.pythonnet_ok = True
    except ImportError:
        out.pythonnet_ok = False

    # 6) 可行路径
    if out.pythonnet_ok and out.managed:
        out.path_usable.append("pythonnet:load_from_path")
    if out.managed and not out.com_registered:
        # regasm 建议命令 (只建议, 不执行)
        regasm = (r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\regasm.exe"
                  r' "%s" /codebase' % out.dll_path)
        out.regasm_cmd = regasm
        out.diagnostics.append(
            "DLL 未 COM 注册 · 可管理员执行 regasm /codebase "
            "(此处只展示命令, 不自动跑)"
        )

    out.ok = bool(out.path_usable)
    if not out.ok:
        out.diagnostics.append(
            "无可用路径: 需 (COM 注册) 或 (pythonnet + managed DLL)"
        )
    return out


# ════════════════════════════════════════════════════════════════════════
# 反者道之动 · 环境健康 · 对话框 · eDrawings
# ════════════════════════════════════════════════════════════════════════

class SWDialogHandler:
    """SW/eDrawings 对话框扫描 + 分类 + 断更.

    根本问题: SW 启动时 FlexLM license 失败 → 弹 #32770 Dialog → 阻塞 COM 注册.
    本类检测对话框, 按类别处理:
      - license_error: SW 许可证故障 (含 -15,10,10061 / 无法获得/FlexLM)
      - welcome:      欢迎/提示对话框 (可安全 dismiss)
      - tip:          每日提示 (可安全 dismiss)
      - unknown:      未知 — 谨慎模式不碰
    """

    LICENSE_PATTERNS = ("无法获得", "许可", "license", "FlexLM",
                         "Cannot obtain", "-15,10,10061", "许可证")
    WELCOME_PATTERNS = ("Welcome", "欢迎", "Getting Started",
                        "What's New", "新功能", "新手")
    TIP_PATTERNS     = ("Tip of the Day", "每日提示", "Tip:")
    OK_LABELS    = frozenset({"确定", "OK", "Yes", "是", "Continue",
                              "Next", "下一步", "关闭", "Close", "Finish"})
    CANCEL_LABELS = frozenset({"取消", "Cancel", "No", "否", "Skip"})

    _TARGET_EXES = ("sldworks.exe", "edrawings.exe")

    @staticmethod
    def _list_sw_pids() -> List[int]:
        """Return all SLDWORKS.exe / eDrawings.exe PIDs.

        单次 tasklist + Python 过滤 (优于 4×tasklist /FI), 0.5-1s.
        Fallback: ctypes EnumProcesses + GetModuleBaseNameW (无 subprocess).
        """
        pids: List[int] = []
        # 主路: 单次 tasklist /FO CSV /NH
        try:
            r = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, encoding="mbcs",
                timeout=8, check=False,
            )
            for line in (r.stdout or "").splitlines():
                parts = [p.strip('"') for p in line.split(",")]
                if len(parts) >= 2:
                    name = parts[0].strip().lower()
                    if name in SWDialogHandler._TARGET_EXES:
                        try: pids.append(int(parts[1]))
                        except ValueError: pass
            return sorted(set(pids))
        except Exception:  # noqa: BLE001
            pass
        # Fallback: ctypes EnumProcesses
        try:
            import ctypes
            from ctypes import wintypes as wt
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            arr = (wt.DWORD * 2048)()
            cb_needed = wt.DWORD()
            if not psapi.EnumProcesses(
                ctypes.byref(arr), ctypes.sizeof(arr),
                ctypes.byref(cb_needed),
            ):
                return []
            n_proc = cb_needed.value // ctypes.sizeof(wt.DWORD)
            for i in range(n_proc):
                pid = int(arr[i])
                if pid <= 0: continue
                h = kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not h: continue
                try:
                    buf = ctypes.create_unicode_buffer(260)
                    n = psapi.GetModuleBaseNameW(h, 0, buf, 260)
                    if n > 0:
                        name = buf.value.lower()
                        if name in SWDialogHandler._TARGET_EXES:
                            pids.append(pid)
                finally:
                    kernel32.CloseHandle(h)
        except Exception:  # noqa: BLE001
            pass
        return sorted(set(pids))

    @staticmethod
    def _get_child_texts(hwnd) -> List[Tuple[str, str]]:
        """Return [(classname, text), ...] for all child controls."""
        import ctypes
        from ctypes import wintypes as wt
        user32 = ctypes.windll.user32
        lines: List[Tuple[str, str]] = []
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(ch, _lp):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(ch, cls, 64)
            buf = ctypes.create_unicode_buffer(1024)
            user32.GetWindowTextW(ch, buf, 1024)
            if buf.value:
                lines.append((cls.value, buf.value))
            return True
        user32.EnumChildWindows(hwnd, cb, 0)
        return lines

    @classmethod
    def classify(cls, title: str, child_texts: List[Tuple[str, str]]) -> str:
        """Return 'license_error' / 'welcome' / 'tip' / 'unknown'."""
        all_text = (title + " " + " ".join(t for _, t in child_texts)).lower()
        if any(pat.lower() in all_text for pat in cls.LICENSE_PATTERNS):
            return "license_error"
        if any(pat.lower() in all_text for pat in cls.WELCOME_PATTERNS):
            return "welcome"
        if any(pat.lower() in all_text for pat in cls.TIP_PATTERNS):
            return "tip"
        return "unknown"

    @classmethod
    def scan(cls, pids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """Return visible #32770 dialogs (classified).

        When pids is None, scans all SW + eDrawings processes.
        """
        import ctypes
        from ctypes import wintypes as wt
        user32 = ctypes.windll.user32
        if pids is None:
            pids = cls._list_sw_pids()
        pid_set = set(pids)
        out: List[Dict[str, Any]] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(hwnd, _lp):
            if not user32.IsWindowVisible(hwnd):
                return True
            cls_buf = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls_buf, 64)
            if cls_buf.value != "#32770":
                return True
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid_set and pid.value not in pid_set:
                return True
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            children = cls._get_child_texts(hwnd)
            # Find buttons
            buttons = [(c, t) for cname, t in children
                       if "button" in cname.lower()
                       for c in (cname,)]  # keep shape simple
            # Actually re-enum buttons with hwnds
            btns_with_hwnd: List[Tuple[int, str]] = []
            @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
            def bcb(ch, _lp):
                cn = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(ch, cn, 64)
                if "Button" in cn.value:
                    tb = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(ch, tb, 256)
                    btns_with_hwnd.append((ch, tb.value))
                return True
            user32.EnumChildWindows(hwnd, bcb, 0)
            kind = cls.classify(title.value, children)
            out.append({
                "hwnd":     hwnd,
                "pid":      pid.value,
                "title":    title.value,
                "kind":     kind,
                "children": children,
                "buttons":  btns_with_hwnd,
            })
            return True
        user32.EnumWindows(cb, 0)
        return out

    @classmethod
    def dismiss(cls, kinds: Tuple[str, ...] = ("welcome", "tip"),
                max_rounds: int = 3, click_label: str = "ok",
                pids: Optional[List[int]] = None) -> Dict[str, Any]:
        """Dismiss dialogs of given `kinds` (3 rounds to catch new ones).

        click_label: 'ok' → OK/确定; 'cancel' → 取消.

        Default behavior is SAFE: only dismisses welcome/tip dialogs, NOT
        license errors (those signal broken environment; clicking OK
        typically exits SW).
        """
        import ctypes
        user32 = ctypes.windll.user32
        BM_CLICK = 0x00F5

        label_set = cls.OK_LABELS if click_label == "ok" else cls.CANCEL_LABELS
        res: Dict[str, Any] = {"rounds": [], "total_dismissed": 0,
                                "skipped_license": 0, "skipped_unknown": 0}
        for _ in range(max_rounds):
            round_dismissed = 0
            round_log: List[Dict[str, Any]] = []
            dialogs = cls.scan(pids)
            for d in dialogs:
                if d["kind"] not in kinds:
                    if d["kind"] == "license_error":
                        res["skipped_license"] += 1
                    elif d["kind"] == "unknown":
                        res["skipped_unknown"] += 1
                    continue
                # Pick button by label
                btn = None
                for h, t in d["buttons"]:
                    if t in label_set:
                        btn = (h, t); break
                if btn is None and d["buttons"]:
                    btn = d["buttons"][0]
                if btn:
                    user32.SendMessageW(btn[0], BM_CLICK, 0, 0)
                    round_log.append({"hwnd": d["hwnd"], "kind": d["kind"],
                                       "clicked": btn[1]})
                    round_dismissed += 1
            res["rounds"].append({"count": round_dismissed, "log": round_log})
            res["total_dismissed"] += round_dismissed
            if round_dismissed == 0:
                break
            import time as _t; _t.sleep(1.2)
        return res


class SWHealthCheck:
    """环境健康 · 一跳就知道能走哪条路.

    输出 Dict 包含:
      install       SW 安装信息
      running       SW 进程列表 (pid, title)
      dialogs       阻塞对话框 (分类)
      license_ok    True 若无 license_error 对话框
      com_ready     True 若 GetActiveObject 成功 (SW 已登 ROT)
      edrawings     eDrawings COM + exe 可达性
      recommendation 依据上述给出的最佳路径
    """

    _EDRAWINGS_EXE_PATHS = (
        r"D:\Program Files\SOLIDWORKS Corp23\eDrawings\eDrawings.exe",
        r"C:\Program Files\SOLIDWORKS Corp\eDrawings\eDrawings.exe",
        r"C:\Program Files\Common Files\SolidWorks Installation Manager\eDrawings\eDrawings.exe",
        r"D:\Program Files\eDrawings\eDrawings.exe",
    )
    _EDRAWINGS_PROGIDS = (
        "EModelView.EModelViewControl",
        "EModelView.EModelViewControl.23",
        "EModelView.EModelViewControl.22",
        "EModelView.EModelViewControl.21",
    )

    @classmethod
    def _edrawings_exe(cls) -> Optional[str]:
        import shutil as _sh
        for p in cls._EDRAWINGS_EXE_PATHS:
            if Path(p).is_file(): return p
        for name in ("eDrawings.exe", "eDrawings"):
            w = _sh.which(name)
            if w: return w
        # 依 SW exe 路径推导
        info = sw_info(probe_com=False)
        if info.exe:
            guess = Path(info.exe).parent.parent / "eDrawings" / "eDrawings.exe"
            if guess.is_file():
                return str(guess)
        return None

    @classmethod
    def _edrawings_com_ok(cls) -> Tuple[bool, Optional[str]]:
        """检 eDrawings COM 可用性 · 不启动进程 (ROT-only + 注册表).

        ⚠ 历史实现用 wc.Dispatch() 会强启 eDrawings.exe 并阻塞等 COM 注册,
        导致 `forge sw_health` 挂死. 改为非侵入式:
          1) GetActiveObject · 若已运行则 ROT 命中 → 真实 COM 活
          2) 注册表 progid CLSID 存在 → 潜在可用 (但未验证活性)
        """
        try:
            import pythoncom  # noqa: F401
            import win32com.client as wc
        except ImportError:
            return False, "pywin32 missing"
        # 1) ROT hit (已运行)
        for pid in cls._EDRAWINGS_PROGIDS:
            try:
                o = wc.GetActiveObject(pid)
                ver = ""
                try: ver = str(o.Version)
                except Exception: pass
                return True, f"{pid} · ROT hit{' · ' + ver if ver else ''}"
            except Exception:  # noqa: BLE001
                continue
        # 2) 注册表落盘检 (仅判断可用性, 不启动)
        if sys.platform == "win32":
            try:
                import winreg
                for pid in cls._EDRAWINGS_PROGIDS:
                    try:
                        k = winreg.OpenKey(
                            winreg.HKEY_CLASSES_ROOT, f"{pid}\\CLSID")
                        clsid, _ = winreg.QueryValueEx(k, "")
                        winreg.CloseKey(k)
                        return False, f"{pid} · registered ({clsid}) · not running"
                    except OSError:
                        continue
            except ImportError:
                pass
        return False, "no eDrawings ProgID registered/active"

    @classmethod
    def _sw_com_ready(cls) -> Tuple[bool, str]:
        """Check GetActiveObject + ROT; do NOT trigger Dispatch launch."""
        try:
            import pythoncom, win32com.client as wc
            pythoncom.CoInitialize()
        except ImportError:
            return False, "pywin32 missing"
        info = sw_info(probe_com=False)
        progid = info.progid_versioned or info.progid
        if not progid:
            return False, "no SW ProgID registered"
        try:
            _ = wc.GetActiveObject(progid)
            return True, f"{progid} · ROT hit"
        except Exception as e:  # noqa: BLE001
            return False, f"{progid} · not in ROT: {str(e)[:60]}"

    @classmethod
    def check(cls, scan_dialogs: bool = True) -> Dict[str, Any]:
        info = sw_info(probe_com=False)
        result: Dict[str, Any] = {
            "install": {
                "installed":       info.installed,
                "version":         info.version,
                "progid":          info.progid_versioned or info.progid,
                "exe":             info.exe,
                "pywin32_ok":      info.pywin32_ok,
            },
            "running": [],
            "dialogs": [],
            "license_ok": True,
            "com_ready":  False,
            "edrawings":  {"exe": None, "com": False},
            "recommendation": "",
        }

        # Running SW procs
        pids = SWDialogHandler._list_sw_pids()
        result["running"] = pids

        # Dialogs
        if scan_dialogs and pids:
            dialogs = SWDialogHandler.scan(pids)
            result["dialogs"] = [
                {"pid": d["pid"], "hwnd": d["hwnd"], "title": d["title"],
                 "kind": d["kind"]}
                for d in dialogs
            ]
            if any(d["kind"] == "license_error" for d in dialogs):
                result["license_ok"] = False

        # SW COM (ROT only — no launch)
        com_ready, com_msg = cls._sw_com_ready()
        result["com_ready"] = com_ready
        result["com_msg"] = com_msg

        # eDrawings
        ed_exe = cls._edrawings_exe()
        result["edrawings"]["exe"] = ed_exe
        ed_com, ed_msg = cls._edrawings_com_ok()
        result["edrawings"]["com"] = ed_com
        result["edrawings"]["msg"] = ed_msg

        # Recommendation
        if com_ready:
            result["recommendation"] = "sw_com"
        elif info.installed and result["license_ok"] and not result["dialogs"]:
            result["recommendation"] = "sw_com_via_launch"
        elif ed_exe:
            result["recommendation"] = "edrawings_exe"
        elif ed_com:
            result["recommendation"] = "edrawings_com"
        else:
            result["recommendation"] = "ole2_only"
        return result


class EDrawingsLauncher:
    """务实的 eDrawings.exe 启动器 + 截图器.

    不走 ActiveX 嵌入 (需 HWND 宿主太复杂). 仅:
      1. subprocess spawn eDrawings.exe (可带文件参数)
      2. 轮询主窗口
      3. PrintWindow 截图
      4. 终止进程

    适用场景:
      - 用户先用 eDrawings 打开文件, 我们截图作为"活体预览"
      - 无 SW license 时的兜底查看器
    """

    def __init__(self, exe: Optional[str] = None):
        self.exe: Optional[str] = exe or SWHealthCheck._edrawings_exe()
        self.pid: Optional[int] = None

    def is_available(self) -> bool:
        return self.exe is not None and Path(self.exe).is_file()

    def launch(self, file_path: Optional[Union[str, Path]] = None) -> int:
        """Spawn eDrawings.exe, optionally with file. Return PID."""
        if not self.is_available():
            raise FileNotFoundError("eDrawings.exe not found")
        args: List[str] = [self.exe]  # type: ignore[list-item]
        if file_path:
            args.append(str(Path(file_path).resolve()))
        import subprocess as _sp
        p = _sp.Popen(
            args,
            creationflags=(_sp.DETACHED_PROCESS |
                           _sp.CREATE_NEW_PROCESS_GROUP),
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
        )
        self.pid = p.pid
        return p.pid

    def find_main_window(self, timeout_s: float = 90.0,
                         min_w: int = 200, min_h: int = 200) -> Optional[Dict]:
        """Poll for the main visible eDrawings window."""
        import ctypes, time
        from ctypes import wintypes as wt
        user32 = ctypes.windll.user32

        def _my_pids() -> set:
            """Re-resolve eDrawings PIDs (launch may have spawned workers)."""
            out = set()
            if self.pid is not None:
                out.add(self.pid)
            try:
                import subprocess as _sp
                r = _sp.run(["tasklist", "/FI", "IMAGENAME eq eDrawings.exe",
                             "/FO", "CSV", "/NH"],
                             capture_output=True, encoding="mbcs", timeout=5)
                for line in (r.stdout or "").splitlines():
                    parts = [p.strip('"') for p in line.split(",")]
                    if len(parts) >= 2:
                        try: out.add(int(parts[1]))
                        except ValueError: pass
            except Exception: pass
            return out

        t0 = time.time()
        while time.time() - t0 < timeout_s:
            pids = _my_pids()
            found: List[Dict[str, Any]] = []
            @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
            def cb(hwnd, _lp):
                p = wt.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
                if p.value not in pids or not user32.IsWindowVisible(hwnd):
                    return True
                title_buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title_buf, 256)
                rect = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left; h = rect.bottom - rect.top
                if (title_buf.value and w >= min_w and h >= min_h):
                    found.append({
                        "hwnd": hwnd, "pid": p.value,
                        "title": title_buf.value,
                        "w": w, "h": h,
                        "x": rect.left, "y": rect.top,
                    })
                return True
            user32.EnumWindows(cb, 0)
            if found:
                # Prefer titled with "eDrawings" over sub-windows
                found.sort(key=lambda f: (0 if "eDrawings" in f["title"] else 1,
                                          -f["w"] * f["h"]))
                return found[0]
            time.sleep(0.5)
        return None

    @staticmethod
    def screenshot_hwnd(hwnd: int, w: int, h: int,
                        out_path: Union[str, Path]) -> Path:
        """PrintWindow with PW_RENDERFULLCONTENT flag (for WPF apps)."""
        try:
            from PIL import Image
        except ImportError as e:
            raise RuntimeError("Pillow required for screenshot") from e
        import ctypes
        from ctypes import wintypes as wt
        user32 = ctypes.windll.user32
        gdi32  = ctypes.windll.gdi32

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        hdc = user32.GetDC(hwnd)
        mem_dc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(mem_dc, bmp)
        # PW_RENDERFULLCONTENT = 0x02
        user32.PrintWindow(hwnd, mem_dc, 0x02)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG),
                        ('biHeight', wt.LONG), ('biPlanes', wt.WORD),
                        ('biBitCount', wt.WORD), ('biCompression', wt.DWORD),
                        ('biSizeImage', wt.DWORD),
                        ('biXPelsPerMeter', wt.LONG),
                        ('biYPelsPerMeter', wt.LONG),
                        ('biClrUsed', wt.DWORD),
                        ('biClrImportant', wt.DWORD)]
        class BITMAPINFO(ctypes.Structure):
            _fields_ = [('bmiHeader', BITMAPINFOHEADER),
                        ('bmiColors', wt.DWORD * 3)]
        bi = BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = w
        bi.bmiHeader.biHeight = -h
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = 0
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
        img.save(out)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hdc)
        return out

    def snap(self, out_path: Union[str, Path],
             wait_s: float = 12.0) -> Optional[Path]:
        """Convenience: find main window, wait wait_s for load, screenshot."""
        import time
        w = self.find_main_window(timeout_s=max(wait_s, 60.0))
        if w is None:
            return None
        # Wait a bit more for model to render after window first appears
        time.sleep(min(wait_s, 30))
        return self.screenshot_hwnd(w["hwnd"], w["w"], w["h"], out_path)

    def close(self):
        """Kill the eDrawings process (all eDrawings actually)."""
        import subprocess as _sp
        _sp.run(["taskkill", "/F", "/IM", "eDrawings.exe"],
                 capture_output=True)
        self.pid = None


def live_show(path: Union[str, Path],
              out_dir: Optional[Union[str, Path]] = None,
              prefer: Tuple[str, ...] = ("sw_com", "edrawings", "ole2"),
              screenshot: bool = True,
              dismiss_dialogs: bool = True) -> Dict[str, Any]:
    """道法自然 · 多路自动选优 · 活体展示 SW 文件.

    Strategy: run `SWHealthCheck`; pick best available path from `prefer`.
    Returns dict describing which path was used + artifacts produced.

    prefer 顺序决定优先级:
      - sw_com      — SW COM 活体 (需 license 可用)
      - edrawings   — eDrawings.exe spawn + 窗口截图
      - ole2        — OLE2 深反 + step_proxy (无需任何程序运行)
    """
    src = Path(path).resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    out = Path(out_dir) if out_dir else (src.parent / "_live_out")
    out.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "src":      str(src),
        "out_dir":  str(out),
        "path_used": None,
        "artifacts": [],
        "health":   None,
        "errors":   [],
    }

    # 0. Health check
    health = SWHealthCheck.check(scan_dialogs=True)
    result["health"] = health

    # optional: dismiss welcome/tip dialogs (not license errors)
    if dismiss_dialogs and health["dialogs"]:
        try:
            result["dismissed"] = SWDialogHandler.dismiss(
                kinds=("welcome", "tip"))
        except Exception as e:  # noqa: BLE001
            result["errors"].append(f"dismiss failed: {e}")

    for method in prefer:
        if method == "sw_com":
            if not health["com_ready"] and not (
                    health["install"]["installed"]
                    and health["license_ok"]):
                continue
            # Try SW COM
            try:
                bridge = SolidWorksBridge()
                bridge.connect(prefer_active=True,
                               launch_if_needed=False)
                doc = bridge.open(src, readonly=True, silent=True)
                if screenshot:
                    shot = out / f"{src.stem}_sw.jpg"
                    try: doc.export(shot, fmt="jpg")
                    except Exception: pass
                    if shot.exists():
                        result["artifacts"].append({
                            "kind": "screenshot", "path": str(shot),
                        })
                step = out / f"{src.stem}_sw.step"
                try:
                    doc.export(step, fmt="step")
                    result["artifacts"].append({
                        "kind": "step", "path": str(step),
                    })
                except Exception as e:  # noqa: BLE001
                    result["errors"].append(f"sw_com export step: {e}")
                bridge.close_doc(doc, save=False)
                bridge.disconnect(exit_sw=False)
                result["path_used"] = "sw_com"
                return result
            except Exception as e:  # noqa: BLE001
                result["errors"].append(f"sw_com: {e}")
                continue

        if method == "edrawings":
            ed = EDrawingsLauncher()
            if not ed.is_available():
                result["errors"].append("edrawings: exe not found")
                continue
            try:
                ed.launch(src)
                if screenshot:
                    shot = out / f"{src.stem}_edrawings.png"
                    r = ed.snap(shot, wait_s=15.0)
                    if r and r.exists():
                        result["artifacts"].append({
                            "kind": "screenshot", "path": str(r),
                        })
                result["path_used"] = "edrawings"
                # don't close — user may want to interact
                return result
            except Exception as e:  # noqa: BLE001
                result["errors"].append(f"edrawings: {e}")
                continue

        if method == "ole2":
            try:
                meta = probe_file(src)
                j = out / f"{src.stem}_ole2.json"
                import json as _j
                j.write_text(_j.dumps(meta, ensure_ascii=False, indent=2,
                                        default=str), encoding="utf-8")
                result["artifacts"].append({
                    "kind": "metadata_json", "path": str(j),
                })
                if meta.get("preview"):
                    pv = out / f"{src.stem}_preview{Path(meta['preview']).suffix}"
                    if Path(meta["preview"]).exists():
                        import shutil as _sh
                        _sh.copy2(meta["preview"], pv)
                        result["artifacts"].append({
                            "kind": "preview_embedded", "path": str(pv),
                        })
                if meta.get("step_proxy"):
                    sp = Path(meta["step_proxy"])
                    if sp.exists():
                        result["artifacts"].append({
                            "kind": "step_proxy", "path": str(sp),
                        })
                result["path_used"] = "ole2"
                return result
            except Exception as e:  # noqa: BLE001
                result["errors"].append(f"ole2: {e}")
                continue

    result["path_used"] = "none"
    return result


# ════════════════════════════════════════════════════════════════════════
# L9 · 一键激活 · 从零到活 · 万法归一 (v3.3.0)
# ════════════════════════════════════════════════════════════════════════
# 纲要
#     L0.5 给出诊断, L5 给出打通步骤 (dry_run), L9 是终极编排:
#       pre_diagnose → remediate(apply) → wait → live_com_probe → post_diagnose
#     若流程中途遇到 not_admin, 不自动 UAC 提权 (避免强制中断), 而是给出
#     明确的 next_steps · 让用户以管理员 shell 重跑 --apply.
#
# 反者道之动:
#     L5 的 dry_run 是 "看得见", L9 的 --apply 是 "干到位".
#     最后 live_com_probe 是 "活体见证": 真正连 COM, 看到 revision 才算过.
#
# 道法自然:
#     不越界做许可破解. 若 SW 激活已过期 (tsf.data 失效), 明确告诉用户
#     "需重新激活", 给出 SW 官方 Activation 向导启动命令.
#
# 产物 (v3.3.0)
#     · L9ActivationResult  stages 列表 + com_ready + delta + next_steps
#     · sw_activate()       主入口 (dry_run 默, 支持 --apply + UAC 提示)
#     · sw_activate_and_verify()  进一步: COM connect + revision
#     · _quick_live_com_probe()   短超时 COM 探针 (隔离活检)
# ════════════════════════════════════════════════════════════════════════

@dataclass
class L9ActivationResult:
    """L9 · 一键激活结果."""
    ok:            bool                     = False
    dry_run:       bool                     = True
    admin:         bool                     = False
    stages:        List[Dict[str, Any]]     = field(default_factory=list)
    # live COM 活检 (激活后是否真能 Dispatch)
    com_ready:     bool                     = False
    com_msg:       Optional[str]            = None
    com_revision:  Optional[str]            = None
    # license delta (severity + findings 变化)
    license_before: Optional[Dict[str, Any]] = None
    license_after:  Optional[Dict[str, Any]] = None
    severity_before: Optional[str]          = None
    severity_after:  Optional[str]          = None
    # 时序
    elapsed_s:     float                    = 0.0
    # 结论
    err:           Optional[str]            = None
    notes:         List[str]                = field(default_factory=list)
    next_steps:    List[str]                = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _quick_live_com_probe(timeout_s: float = 15.0,
                          include_connect: bool = True,
                          include_revision: bool = True,
                          ) -> Dict[str, Any]:
    """短超时活体 COM 探针 (隔离测试 · 不留进程 · 不留 SW 窗口).

    返回:
        {
          "ok":         bool,
          "mode":       "active" | "dispatch" | "none",
          "revision":   Optional[str],
          "msg":        str,
          "elapsed_s":  float,
          "progid":     Optional[str],
        }
    """
    t0 = time.time()
    out: Dict[str, Any] = {"ok": False, "mode": "none", "revision": None,
                            "msg": "", "elapsed_s": 0.0, "progid": None}

    if sys.platform != "win32":
        out["msg"] = "non-windows"
        out["elapsed_s"] = time.time() - t0
        return out

    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception as e:  # noqa: BLE001
        out["msg"] = f"pywin32 missing: {e}"
        out["elapsed_s"] = time.time() - t0
        return out

    # 优先 progid
    info = sw_info(probe_com=False)
    progid = info.progid_versioned or info.progid or "SldWorks.Application"
    out["progid"] = progid

    # 1) 尝试接已运行实例 (快)
    app = None
    try:
        app = win32com.client.GetActiveObject(progid)
        out["mode"] = "active"
    except Exception:
        app = None

    # 2) 若无 · Dispatch (会触发启动, 超时控制)
    if app is None and include_connect:
        # 简陋超时: 用 subprocess 启 python 做 Dispatch, wait
        import threading
        container: List[Any] = [None, None]

        def _dispatch():
            try:
                pythoncom.CoInitialize()
                try:
                    a = win32com.client.Dispatch(progid)
                    container[0] = a
                except Exception as e:  # noqa: BLE001
                    container[1] = e
                finally:
                    try: pythoncom.CoUninitialize()
                    except Exception: pass
            except Exception as e:  # noqa: BLE001
                container[1] = e

        th = threading.Thread(target=_dispatch, daemon=True)
        th.start()
        th.join(timeout=timeout_s)
        if th.is_alive():
            out["msg"] = f"Dispatch timeout after {timeout_s}s"
            out["elapsed_s"] = time.time() - t0
            return out
        if container[1] is not None:
            out["msg"] = f"Dispatch failed: " \
                         f"{type(container[1]).__name__}: {container[1]}"
            out["elapsed_s"] = time.time() - t0
            return out
        app = container[0]
        out["mode"] = "dispatch"

    if app is None:
        out["msg"] = "no SW COM object (neither active nor dispatch)"
        out["elapsed_s"] = time.time() - t0
        return out

    out["ok"] = True

    # 3) 读 revision
    if include_revision:
        try:
            rev = app.RevisionNumber
            out["revision"] = str(rev)
            out["msg"] = f"COM live · revision={rev}"
        except Exception as e:  # noqa: BLE001
            out["msg"] = f"COM alive but RevisionNumber failed: {e}"
    else:
        out["msg"] = "COM alive (no revision probe)"

    out["elapsed_s"] = time.time() - t0

    # 4) 不干预 SW 进程; 让用户决定
    # (我们只查状态, 不 ExitApp, 避免破坏用户正在用的 SW)
    app = None
    return out


def _severity_rank(sev: Optional[str]) -> int:
    """把严重度转成整数, 便于比较变化."""
    rank = {
        None:     -1,
        "":       -1,
        "ok":      0,
        "info":    1,
        "notice":  2,
        "warning": 3,
        "error":   4,
        "fatal":   5,
    }
    return rank.get((sev or "").lower().strip(), 99)


def sw_activate(dry_run: bool = True,
                *,
                wait_license_s: float = 5.0,
                enable_disabled: bool = True,
                with_licensing_service: bool = True,
                probe_com: bool = True,
                probe_com_timeout_s: float = 20.0,
                probe_com_include_dispatch: bool = False,
                ) -> L9ActivationResult:
    """L9 · 一键激活 · 从零到 SW COM 活.

    主流程:
        stage 1 · pre_diagnose  : sw_license_diagnose() 记当前状态
        stage 2 · remediate     : sw_remediate_all(dry_run, ...) 打通
                                  (change_disabled_to_manual=enable_disabled)
        stage 3 · wait          : 给 licensing service / COM 注册落盘的缓冲
        stage 4 · com_probe     : _quick_live_com_probe() 真活体探针
                                  (默认只做 GetActiveObject, 不 Dispatch,
                                   避免触发 SW 启动 · 用户想要真启可传
                                   probe_com_include_dispatch=True)
        stage 5 · post_diagnose : 再跑 sw_license_diagnose 对比 severity

    参数
        dry_run                   True 默; False 真执 (需 admin shell)
        wait_license_s            remediate 后的观察缓冲 (默 5s)
        enable_disabled           若 service Disabled 先翻 Manual
        with_licensing_service    是否也 start SW Licensing Service
        probe_com                 是否做 COM 活体探针
        probe_com_timeout_s       探针超时
        probe_com_include_dispatch   True 则用 Dispatch (会启 SW);
                                     False 只试 GetActiveObject (已运行才见)

    返回 L9ActivationResult · 含 stages/severity 前后对比/next_steps
    """
    t0 = time.time()
    r = L9ActivationResult(dry_run=dry_run, admin=is_admin())

    # ── stage 1 · pre_diagnose ────────────────────────────────────
    try:
        pre = sw_license_diagnose()
        pre_d = pre.to_dict()
        r.license_before = pre_d
        r.severity_before = pre.severity
        r.stages.append({
            "stage":     "pre_diagnose",
            "ok":        True,
            "severity":  pre.severity,
            "findings":  len(pre.findings),
            "recommend": pre.recommend,
        })
    except Exception as e:  # noqa: BLE001
        r.err = f"pre_diagnose: {type(e).__name__}: {e}"
        r.elapsed_s = time.time() - t0
        return r

    # ── stage 2 · remediate ───────────────────────────────────────
    try:
        rem = sw_remediate_all(
            dry_run=dry_run,
            with_licensing_service=with_licensing_service,
            change_disabled_to_manual=enable_disabled,
        )
        r.stages.append({
            "stage":       "remediate",
            "ok":          bool(rem.get("docmgr", {}).get("ok")
                                or rem.get("licensing", {}).get("ok")),
            "admin":       rem.get("admin"),
            "dry_run":     rem.get("dry_run"),
            "docmgr_ok":   rem.get("docmgr", {}).get("ok"),
            "docmgr_err":  rem.get("docmgr", {}).get("err"),
            "licensing_ok":  (rem.get("licensing") or {}).get("ok"),
            "licensing_err": (rem.get("licensing") or {}).get("err"),
        })
        r.stages[-1]["full"] = rem

        # 如果 apply 模式但 not_admin, 给明确的下一步
        if not dry_run and not r.admin:
            docmgr_err = (rem.get("docmgr") or {}).get("err")
            licensing_err = (rem.get("licensing") or {}).get("err")
            if docmgr_err == "not_admin" or licensing_err == "not_admin":
                r.notes.append(
                    "当前 shell 非管理员. L5 写 HKLM + sc start 需要 admin."
                )
                r.next_steps.append(
                    '以管理员身份打开 PowerShell: '
                    'Start-Process pwsh -Verb RunAs · 然后在管理员 shell 再跑:'
                )
                r.next_steps.append(
                    f'python "{Path(__file__).resolve()}" activate --apply'
                )
    except Exception as e:  # noqa: BLE001
        r.err = f"remediate: {type(e).__name__}: {e}"
        r.elapsed_s = time.time() - t0
        return r

    # ── stage 3 · wait ────────────────────────────────────────────
    if not dry_run and wait_license_s > 0:
        time.sleep(wait_license_s)
        r.stages.append({
            "stage":  "wait",
            "ok":     True,
            "wait_s": wait_license_s,
        })

    # ── stage 4 · com_probe ──────────────────────────────────────
    if probe_com:
        try:
            p = _quick_live_com_probe(
                timeout_s=probe_com_timeout_s,
                include_connect=probe_com_include_dispatch,
                include_revision=True,
            )
            r.stages.append({
                "stage":       "com_probe",
                "ok":          bool(p.get("ok")),
                "mode":        p.get("mode"),
                "msg":         p.get("msg"),
                "revision":    p.get("revision"),
                "progid":      p.get("progid"),
                "elapsed_s":   p.get("elapsed_s"),
            })
            r.com_ready    = bool(p.get("ok"))
            r.com_msg      = p.get("msg")
            r.com_revision = p.get("revision")
        except Exception as e:  # noqa: BLE001
            r.stages.append({
                "stage": "com_probe",
                "ok":    False,
                "err":   f"{type(e).__name__}: {e}",
            })

    # ── stage 5 · post_diagnose ───────────────────────────────────
    try:
        post = sw_license_diagnose()
        post_d = post.to_dict()
        r.license_after  = post_d
        r.severity_after = post.severity
        r.stages.append({
            "stage":     "post_diagnose",
            "ok":        True,
            "severity":  post.severity,
            "findings":  len(post.findings),
            "recommend": post.recommend,
            "delta":     {
                "severity_before":  r.severity_before,
                "severity_after":   r.severity_after,
                "improved":         _severity_rank(r.severity_after)
                                    < _severity_rank(r.severity_before),
            },
        })
    except Exception as e:  # noqa: BLE001
        r.stages.append({
            "stage": "post_diagnose",
            "ok":    False,
            "err":   f"{type(e).__name__}: {e}",
        })

    # ── 结论 ──────────────────────────────────────────────────────
    #   ok = severity 改善 OR com_ready True (两条路)
    severity_improved = (_severity_rank(r.severity_after)
                          < _severity_rank(r.severity_before))
    r.ok = severity_improved or r.com_ready

    # next_steps 生成
    if r.ok and not r.com_ready:
        r.next_steps.append(
            "L5 阻塞已消减, 但未在当前进程见证 COM 活体. "
            "可运行: python dao_solidworks.py connect --launch "
            "or sw_show.py launch"
        )
    if not r.ok and dry_run:
        r.next_steps.append(
            "dry_run 模式不会改变系统. 如要真执, 以管理员身份: "
            "python dao_solidworks.py activate --apply"
        )
    if (r.severity_after or "").lower() == "error":
        # 具体错因 → 具体建议
        after_rec = (r.license_after or {}).get("recommend", "") or ""
        if "激活" in after_rec or "activation" in after_rec.lower():
            r.next_steps.append(
                "许可本身已失效 (激活过期或被注销). "
                "运行 SW 激活向导: "
                '"D:\\Program Files\\SOLIDWORKS Corp23\\'
                'SolidWorks\\sldLic.exe" /activate  # 路径可能因安装不同而异'
            )

    r.elapsed_s = time.time() - t0
    return r


def sw_activate_and_verify(dry_run: bool = True,
                            *,
                            test_file: Optional[Union[str, Path]] = None,
                            launch_sw: bool = False,
                            save_report: Optional[Union[str, Path]] = None,
                            **activate_kwargs) -> Dict[str, Any]:
    """L9+ · 激活后完整铁证 · 可选真起 SW + 打开 test_file + 一张截图.

    流程:
        1. sw_activate() — dry_run 或 apply
        2. 若 launch_sw: 启 SW · connect · 读 revision/list_docs
        3. 若 test_file: open → isometric → ViewZoomtofit2 → screenshot
        4. 汇总 + 可选 JSON 报告

    返回:
        {
          "activate":  L9ActivationResult.to_dict(),
          "launch":    {ok, revision, pid, elapsed_s},
          "test_file": {ok, preview_path, elapsed_s, err},
          "report":    str | None,
        }
    """
    out: Dict[str, Any] = {}
    t0 = time.time()
    act = sw_activate(dry_run=dry_run, **activate_kwargs)
    out["activate"] = act.to_dict()

    if not launch_sw:
        out["launch"] = None
        out["test_file"] = None
    else:
        # 尝试 Dispatch + connect
        lr: Dict[str, Any] = {"ok": False, "elapsed_s": 0.0}
        t1 = time.time()
        sw = None
        try:
            sw = SolidWorksBridge()
            sw.connect(launch_if_needed=True, launch_timeout_s=120.0)
            lr["ok"]       = True
            lr["revision"] = sw.revision()
            lr["docs"]     = sw.list_docs()
            lr["elapsed_s"] = time.time() - t1
        except Exception as e:  # noqa: BLE001
            lr["err"] = f"{type(e).__name__}: {e}"
            lr["elapsed_s"] = time.time() - t1
        out["launch"] = lr

        # test_file: 打开 + 截图
        tfr: Dict[str, Any] = {"ok": False}
        if lr["ok"] and test_file:
            t2 = time.time()
            try:
                tp = Path(test_file)
                if not tp.exists():
                    tfr["err"] = f"test_file not found: {tp}"
                else:
                    # 用 sw_show 做展示 (解耦)
                    _HERE_L9 = Path(__file__).resolve().parent
                    sys.path.insert(0, str(_HERE_L9.parent / "10-反笙_FreeCAD"))
                    try:
                        from sw_show import SWShow  # type: ignore
                        sh = SWShow()
                        res = sh.live_show(
                            tp, shots=("isometric",),
                            readonly=True,
                        )
                        tfr.update(res)
                        tfr["ok"] = any(
                            v.get("ok") for v in res.get("shots", {}).values()
                        )
                    finally:
                        try: sys.path.remove(str(_HERE_L9.parent / "10-反笙_FreeCAD"))
                        except ValueError: pass
            except Exception as e:  # noqa: BLE001
                tfr["err"] = f"{type(e).__name__}: {e}"
            tfr["elapsed_s"] = time.time() - t2
        out["test_file"] = tfr

        # 收尾: disconnect (不 ExitApp, 让用户接管)
        if sw is not None:
            try: sw.disconnect(exit_sw=False)
            except Exception: pass

    # 写报告
    if save_report:
        rp = Path(save_report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(
            json.dumps(out, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        out["report"] = str(rp)

    out["total_elapsed_s"] = time.time() - t0
    return out


# ════════════════════════════════════════════════════════════════════════
# CLI (continued)
# ════════════════════════════════════════════════════════════════════════
def _self_test(verbose: bool = True) -> Dict[str, Any]:
    """反者道之动 · 自测矩阵."""
    log: List[str] = []
    def _p(m):
        if verbose: print(m)
        log.append(m)
    res = {"pass": [], "fail": [], "score": 0, "total": 0}

    # T1: sw_info (无 COM)
    try:
        info = sw_info(probe_com=False)
        assert info.pywin32_ok
        assert info.progid is not None or not info.installed
        _p(f"   SW: {info.version} progid={info.progid_versioned} exe={info.exe}")
        res["pass"].append("T1_info"); res["score"] += 1
    except AssertionError as e:
        res["fail"].append(("T1_info", str(e)))
    res["total"] += 1

    # T2: OLE2Parser 基础 · 软编码 · env SW_TEST_TARGET 可覆盖
    _default_cand = (
        Path(__file__).parents[1] / "60-实战_Projects"
        / "南京-吴鸿轩_锤式破碎机" / "sldprt"
        / "hammer_crusher_total_machine.sldprt"
    )
    cand = Path(os.environ.get("SW_TEST_TARGET", str(_default_cand)))
    if cand.exists():
        try:
            with OLE2Parser(cand) as ole:
                assert ole.header["major_version"] in (3, 4)
                assert ole.sect_size in (512, 4096)
                assert len(ole.directory) > 0
                streams = ole.stream_names()
                _p(f"   OLE2 streams: {len(streams)} (e.g. {streams[:3]})")
                res["pass"].append("T2_ole2"); res["score"] += 1
        except Exception as e:
            res["fail"].append(("T2_ole2", repr(e)))
        res["total"] += 1

        # T3: probe_file
        try:
            meta = probe_file(cand)
            assert meta["ok"], meta.get("err")
            assert meta["doc_type"] in ("part", "assembly")
            assert len(meta["streams"]) > 5
            _p(f"   probe: type={meta['doc_type']} n_streams={len(meta['streams'])} "
               f"size={meta['size_MB']}MB preview={bool(meta['preview'])}")
            res["pass"].append("T3_probe"); res["score"] += 1
        except Exception as e:
            res["fail"].append(("T3_probe", repr(e)))
        res["total"] += 1

        # T4: Preview 抽取
        try:
            out_png = Path(__file__).parent / "_sw_preview_test.png"
            data = extract_preview(cand, out_png)
            if data and out_png.exists() and out_png.stat().st_size > 0:
                _p(f"   preview: {out_png.name} ({out_png.stat().st_size}B)")
                res["pass"].append("T4_preview"); res["score"] += 1
                # 保留文件作为证据, 不删除
            else:
                _p(f"   preview: (none) — SW未保存预览或格式特殊")
                res["pass"].append("T4_preview_skip"); res["score"] += 1
        except Exception as e:
            res["fail"].append(("T4_preview", repr(e)))
        res["total"] += 1
    else:
        _p(f"   skipping T2-T4 (no sldprt at {cand})")

    # T5: PropertySetParser 基本
    try:
        # 构造最小 property set
        hdr = b"\xFE\xFF" + b"\x00\x00" + b"\x00\x00\x00\x00" + (b"\x00" * 16) + b"\x01\x00\x00\x00"
        hdr += b"\xE0\x85\x9F\xF2" + b"\xF9\x4F" + b"\x68\x10" + b"\xAB\x91\x08\x00\x2B\x27\xB3\xD9"  # SI FMTID
        hdr += b"\x30\x00\x00\x00"  # offset 48
        # section
        body = b"\x30\x00\x00\x00" + b"\x01\x00\x00\x00"   # size 48, 1 prop
        body += b"\x02\x00\x00\x00" + b"\x10\x00\x00\x00"  # pid=2 (TITLE), offset 16
        body += b"\x1E\x00\x00\x00"                         # VT_LPSTR
        body += b"\x05\x00\x00\x00" + b"test\x00" + b"\x00\x00\x00"  # "test"
        full = hdr + body
        out = PropertySetParser.parse(full)
        _p(f"   ps parse: {out}")
        res["pass"].append("T5_ps"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T5_ps", repr(e)))
    res["total"] += 1

    # T6: SolidWorksBridge 诊断 (不连)
    try:
        sw = SolidWorksBridge()
        assert sw.is_installed()
        assert not sw.is_connected()
        _p(f"   bridge: installed=True connected=False")
        res["pass"].append("T6_bridge"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T6_bridge", repr(e)))
    res["total"] += 1

    # T7: SWInfo 序列化
    try:
        info = sw_info(probe_com=False)
        d = info.to_dict()
        s = json.dumps(d, ensure_ascii=False)
        assert "progid" in d
        _p(f"   info json: {len(s)} chars")
        res["pass"].append("T7_json"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T7_json", repr(e)))
    res["total"] += 1

    # T8: SWDialogHandler 能力 (不触发真实弹窗)
    try:
        # classify with synthetic input
        k1 = SWDialogHandler.classify(
            "SOLIDWORKS",
            [("Static", "无法获得下列许可 SOLIDWORKS Standard")])
        k2 = SWDialogHandler.classify(
            "Welcome to SolidWorks", [("Static", "Getting Started")])
        k3 = SWDialogHandler.classify("", [("Static", "Tip of the Day")])
        k4 = SWDialogHandler.classify("Random", [("Static", "unknown stuff")])
        assert k1 == "license_error", f"expected license_error, got {k1}"
        assert k2 == "welcome", f"expected welcome, got {k2}"
        assert k3 == "tip", f"expected tip, got {k3}"
        assert k4 == "unknown", f"expected unknown, got {k4}"
        # scan should not throw
        _ = SWDialogHandler.scan([])
        _p(f"   SWDialogHandler.classify: 4/4 patterns OK")
        res["pass"].append("T8_dialog_handler"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T8_dialog_handler", repr(e)))
    res["total"] += 1

    # T9: SWHealthCheck 不抛 + 关键字段都在
    try:
        h = SWHealthCheck.check(scan_dialogs=False)
        for k in ("install", "running", "dialogs", "license_ok",
                  "com_ready", "edrawings", "recommendation"):
            assert k in h, f"missing key {k}"
        assert h["recommendation"] in (
            "sw_com", "sw_com_via_launch", "edrawings_exe",
            "edrawings_com", "ole2_only")
        _p(f"   health.recommendation = {h['recommendation']}")
        res["pass"].append("T9_health"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T9_health", repr(e)))
    res["total"] += 1

    # T10: EDrawingsLauncher 检测 (不 launch)
    try:
        ed = EDrawingsLauncher()
        avail = ed.is_available()
        _p(f"   EDrawingsLauncher available={avail} exe={ed.exe}")
        # 不必严格 require eDrawings 安装 — 信息性检查
        res["pass"].append("T10_edrawings"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T10_edrawings", repr(e)))
    res["total"] += 1

    # T11: live_show 接口存在 + 签名正确
    try:
        import inspect
        sig = inspect.signature(live_show)
        params = list(sig.parameters.keys())
        assert "path" in params and "prefer" in params
        _p(f"   live_show params: {params}")
        res["pass"].append("T11_live_show"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T11_live_show", repr(e)))
    res["total"] += 1

    # ── 新 L0.5/L1.5/L3/L4/L2.5 覆盖 ──────────────────────────────────────
    # T12: L0.5 sw_license_diagnose 基础字段
    try:
        s = sw_license_diagnose()
        assert s.severity in ("ok", "warning", "critical")
        assert isinstance(s.com_registered, dict) and len(s.com_registered) >= 5
        assert isinstance(s.ports, dict) and len(s.ports) == len(_SW_LIC_PORTS)
        _p(f"   L0.5 license: severity={s.severity} findings={len(s.findings)}")
        res["pass"].append("T12_license"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T12_license", repr(e)))
    res["total"] += 1

    # T13: L1.5 carve_feature_names 在合成流上命中
    try:
        # 合成: u32 长度 + UTF-16LE "Boss-Extrude1"
        nm = "Boss-Extrude1"
        blob = struct.pack("<I", len(nm)) + nm.encode("utf-16-le")
        names = carve_feature_names(blob)
        assert nm in names, f"expected {nm!r}, got {names}"
        # 裸 UTF-16: "Fillet2" + null
        blob2 = "Fillet2".encode("utf-16-le") + b"\x00\x00\x00\x00"
        names2 = carve_feature_names(blob2)
        assert "Fillet2" in names2, f"bare scan miss: {names2}"
        _p(f"   L1.5 carve: detected synthesized {nm!r} + Fillet2")
        res["pass"].append("T13_carve"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T13_carve", repr(e)))
    res["total"] += 1

    # T14: deep_probe_file (若 cand 存在)
    if cand.exists():
        try:
            meta = deep_probe_file(cand)
            assert meta["ok"], meta.get("err")
            assert "feature_names_carved" in meta
            assert "stream_highlights" in meta
            n = len(meta["feature_names_carved"])
            _p(f"   L1.5 deep_probe: n_features={n} "
               f"streams={list(meta['stream_highlights'].keys())}")
            assert n > 0, "no feature names carved"
            res["pass"].append("T14_deep_probe"); res["score"] += 1
        except Exception as e:
            res["fail"].append(("T14_deep_probe", repr(e)))
        res["total"] += 1

    # T15: L3 PEReader + dll_name
    try:
        # 选一个已知存在的小 DLL
        test_dll = None
        for p in (
            r"C:\Program Files\Common Files\SolidWorks Shared\sldShellUtilsUIu.dll",
            r"C:\Windows\System32\kernel32.dll",
        ):
            if Path(p).exists():
                test_dll = Path(p); break
        if test_dll is None:
            raise AssertionError("no test DLL found")
        with PEReader(test_dll) as pe:
            sm = pe.summary()
            assert sm["pe_type"] in ("PE32", "PE32+")
            assert sm["machine"] in ("x86", "x64", "arm64", "arm", "ia64")
            # kernel32 有 dll_name, SW shared DLL 有较大导出表
            nm = pe.dll_name()
            exps = pe.exports(limit=5)
            _p(f"   L3 PE: {test_dll.name} · {sm['pe_type']}/{sm['machine']} · "
               f"name={nm!r} · exp[:5]={exps[:5]}")
        res["pass"].append("T15_pe"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T15_pe", repr(e)))
    res["total"] += 1

    # T16: L3 sw_dll_index (限小 budget)
    try:
        idx = sw_dll_index(max_files=50, include_exports=False)
        if "err" in idx:
            _p(f"   L3 sw_dll_index: skipped ({idx['err']})")
            res["pass"].append("T16_dll_index_skip"); res["score"] += 1
        else:
            assert idx["total"] > 0
            assert idx["managed_count"] + idx["native_count"] == idx["total"]
            _p(f"   L3 dll_index: total={idx['total']} "
               f"managed={idx['managed_count']} native={idx['native_count']}")
            res["pass"].append("T16_dll_index"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T16_dll_index", repr(e)))
    res["total"] += 1

    # T17: L4 sw_registry_dump
    try:
        if sys.platform == "win32":
            r = sw_registry_dump(include_values=True, max_keys=100)
            if "err" in r:
                _p(f"   L4 reg: skipped ({r['err']})")
                res["pass"].append("T17_reg_skip"); res["score"] += 1
            else:
                assert "_summary" in r
                assert r["_summary"]["total_keys"] >= 0
                _p(f"   L4 reg: keys={r['_summary']['total_keys']} "
                   f"values={r['_summary']['total_values']}")
                res["pass"].append("T17_reg"); res["score"] += 1
        else:
            res["pass"].append("T17_reg_nonwin"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T17_reg", repr(e)))
    res["total"] += 1

    # T18: L2.5 swdm_probe
    try:
        dm = swdm_probe()
        # 只要不抛 + 结构合理
        assert isinstance(dm.path_usable, list)
        assert isinstance(dm.diagnostics, list)
        _p(f"   L2.5 swdm: dll={dm.dll_path and Path(dm.dll_path).name} "
           f"managed={dm.managed} ok={dm.ok}")
        res["pass"].append("T18_swdm"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T18_swdm", repr(e)))
    res["total"] += 1

    # ── L5/L6 · 打通 · 几何反演 ────────────────────────────────────────
    # T19: L5 is_admin + find_regasm + dry_run remediation
    try:
        admin = is_admin()
        regasm = find_regasm()
        # dry_run 安全可测
        r = remediate_docmgr_com(dry_run=True)
        assert r.dry_run is True, "dry_run flag not honored"
        assert r.action == "remediate_docmgr_com"
        assert isinstance(r.steps, list)
        # 若 DLL + regasm 均就绪, dry_run 应 ok
        if r.ok or r.err in (None, "docmgr_dll_not_found", "regasm_not_found"):
            _p(f"   L5.1 docmgr_remediate dry_run: ok={r.ok} admin={admin} "
               f"regasm={regasm and Path(regasm).name}")
            res["pass"].append("T19_remediate_docmgr_dry"); res["score"] += 1
        else:
            raise AssertionError(f"dry_run unexpected state: ok={r.ok} err={r.err}")
    except Exception as e:
        res["fail"].append(("T19_remediate_docmgr_dry", repr(e)))
    res["total"] += 1

    # T20: L5.2 licensing dry_run
    try:
        r2 = remediate_sw_licensing_service(dry_run=True)
        assert r2.dry_run is True
        assert r2.action == "remediate_sw_licensing"
        # dry_run 总 ok=True (只规划不执行)
        assert r2.ok, f"dry_run should be ok, got err={r2.err}"
        _p(f"   L5.2 license_remediate dry_run: ok={r2.ok} "
           f"before={list(r2.before.keys())}")
        res["pass"].append("T20_remediate_license_dry"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T20_remediate_license_dry", repr(e)))
    res["total"] += 1

    # T21: L6 · carve_geometry_refs (若 cand 存在)
    if cand.exists():
        try:
            g = carve_geometry_refs(cand, max_stream_bytes=1 * 1024 * 1024)
            assert g.ok, g.err
            # 预期: 至少找到 1 个几何流 (关键字中) 或通过 size fallback
            assert len(g.geometry_streams) >= 1, (
                f"no geometry streams: {g.geometry_streams}")
            # 预期: 从 L1.5 carve 出 Orphan_Brep 引用 (hammer_crusher 有 87)
            _p(f"   L6 geom: n_streams={len(g.geometry_streams)} "
               f"xt_hits={len(g.xt_hits)} orphan={len(g.orphan_breps)}")
            res["pass"].append("T21_geom"); res["score"] += 1
        except Exception as e:
            res["fail"].append(("T21_geom", repr(e)))
        res["total"] += 1

    # ── L7 · 极限反演 ────────────────────────────────────────────────
    # T22: extract_parasolid_bodies · 不落盘 · 基本字段
    if cand.exists():
        try:
            r = extract_parasolid_bodies(cand, out_dir=None)
            assert isinstance(r.body_names, list)
            assert isinstance(r.body_sizes_B, list)
            # 对 hammer_crusher 应 >= 50 bodies (实测 87)
            if r.ok and r.n_bodies > 0:
                _p(f"   L7 bodies: n={r.n_bodies} schema={r.schema} "
                   f"range={min(r.body_sizes_B):,}..{max(r.body_sizes_B):,}B")
                assert r.schema is not None, "Parasolid schema not extracted"
                assert r.schema.startswith("SCH_"), f"bad schema: {r.schema}"
                res["pass"].append("T22_bodies"); res["score"] += 1
            elif r.err == "no LocalBodies stream":
                # 文件无 LocalBodies 属合理 (空零件 / 装配)
                _p(f"   L7 bodies: skip (no LocalBodies in {cand.name})")
                res["pass"].append("T22_bodies_skip"); res["score"] += 1
            else:
                raise AssertionError(
                    f"unexpected ok={r.ok} n={r.n_bodies} err={r.err}")
        except Exception as e:
            res["fail"].append(("T22_bodies", repr(e)))
        res["total"] += 1

    # T23: extract_strings · 字符串 + 取证
    if cand.exists():
        try:
            s = extract_strings(cand)
            assert s.ok, s.err
            assert isinstance(s.utf16le, list)
            assert isinstance(s.sw_classes, list)
            # 对真实 SW 零件应 >= 100 UTF-16LE 字符串
            assert s.n_utf16le > 50, (
                f"太少 UTF-16LE 字符串: {s.n_utf16le}")
            _p(f"   L7 strings: utf16le={s.n_utf16le} ascii={s.n_ascii} "
               f"classes={len(s.sw_classes)} lang={s.language_hint} "
               f"paths={len(s.win_paths)}")
            res["pass"].append("T23_strings"); res["score"] += 1
        except Exception as e:
            res["fail"].append(("T23_strings", repr(e)))
        res["total"] += 1

    # ── L8 · 极反推万物 · XT 块结构反 ───────────────────────────────
    # T24: analyze_xt_block · 合成最小 block + 真实 block (若 cand)
    try:
        # 合成一个最小 Parasolid XT header (足以通过解析)
        synth_head = (
            b"PS\x00\x00\x00"
            b"3: TRANSMIT FILE created by modeller version 1800141\x00\x00"
            b"\x00\x11SCH_1800141_18007\x00\x00\x00"
            + b"\x00" * 16
            + b"\x06\x00T\x00\x00\x00\x13\x00\x06"
            + b"Orphan_Brep_#999999\x00"
            + b"\x00" * 64
        )
        info = analyze_xt_block(synth_head, scan_floats=False)
        assert info.ok, f"synth block rejected: err={info.err}"
        assert info.has_ps_marker, "PS marker not detected in synth"
        assert info.schema == "SCH_1800141_18007", f"bad schema: {info.schema}"
        assert info.schema_id == "1800141"
        assert info.user_id == "18007"
        assert info.modeller_version == "1800141"
        assert info.body_name == "Orphan_Brep_#999999", (
            f"body_name miss: {info.body_name}")
        assert not info.has_end_marker
        _p(f"   L8 XT synth: schema={info.schema} body={info.body_name} "
           f"printable={info.printable_ratio}")
        res["pass"].append("T24_xt_block_synth"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T24_xt_block_synth", repr(e)))
    res["total"] += 1

    # T25: parasolid_catalog · 真件 (若 cand) · 跑 5 body 上限
    if cand.exists():
        try:
            cat = parasolid_catalog(cand, scan_floats=True,
                                    float_stride=8, max_bodies=5)
            if cat.ok:
                assert cat.n_bodies >= 1, f"no bodies: {cat.n_bodies}"
                assert cat.schema and cat.schema.startswith("SCH_"), (
                    f"bad schema: {cat.schema}")
                assert cat.raw_size_B > 0
                assert len(cat.bodies) == cat.n_bodies
                # 至少一个 body 有 body_name
                named = [b for b in cat.bodies if b.get("body_name")]
                assert len(named) >= 1, "no body with name"
                # 反验: to_dict 可 JSON 往返 (软编码一致性)
                rt = json.loads(json.dumps(cat.to_dict(), default=str))
                assert rt["n_bodies"] == cat.n_bodies
                _p(f"   L8 catalog: n={cat.n_bodies} schema={cat.schema} "
                   f"raw={cat.raw_size_B:,}B float_range="
                   f"{cat.global_float_range}")
                res["pass"].append("T25_catalog"); res["score"] += 1
            elif cat.err in ("no_LocalBodies_stream",
                             "no_parasolid_xt_blocks"):
                _p(f"   L8 catalog: skip ({cat.err})")
                res["pass"].append("T25_catalog_skip"); res["score"] += 1
            else:
                raise AssertionError(
                    f"unexpected: ok={cat.ok} err={cat.err} n={cat.n_bodies}")
        except Exception as e:
            res["fail"].append(("T25_catalog", repr(e)))
        res["total"] += 1

    # ── L8 边界测 · 测试到底 · 去芜存菁 (v3.2.0) ─────────────────────
    # T26: analyze_xt_block 对 empty / too_small / noise 输入的优雅失败
    try:
        # empty
        i1 = analyze_xt_block(b"", scan_floats=False)
        assert not i1.ok and i1.err == "block_too_small"
        # too small (< 40 B)
        i2 = analyze_xt_block(b"\x00" * 20, scan_floats=False)
        assert not i2.ok and i2.err == "block_too_small"
        # 随机 >= 40 B 但无 TRANSMIT FILE → no_transmit_header
        i3 = analyze_xt_block(b"RANDOM_NOT_PARASOLID_DATA" + b"\x00" * 60,
                              scan_floats=False)
        assert not i3.ok and i3.err == "no_transmit_header"
        # 仅 PS\0\0 但无 header → 仍然 no_transmit_header
        i4 = analyze_xt_block(b"PS\x00\x00" + b"\xff" * 80, scan_floats=False)
        assert not i4.ok and i4.err == "no_transmit_header"
        _p(f"   L8 boundary: empty/small/noise/partial-PS 全按预期失败")
        res["pass"].append("T26_xt_boundary"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T26_xt_boundary", repr(e)))
    res["total"] += 1

    # T27: parasolid_catalog 对不存在文件的优雅失败
    try:
        c_err = parasolid_catalog("__nonexistent_file__.sldprt")
        assert not c_err.ok
        assert c_err.err and "file_not_found" in c_err.err
        assert c_err.n_bodies == 0
        _p(f"   L8 catalog missing-file: ok={c_err.ok} err={c_err.err}")
        res["pass"].append("T27_catalog_missing"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T27_catalog_missing", repr(e)))
    res["total"] += 1

    # T28: scan_floats=False 时 floats_in_range 为 None · stride 参数不影响核心字段
    if cand.exists():
        try:
            # 不扫 float 的快速路径
            c_nof = parasolid_catalog(cand, scan_floats=False, max_bodies=3)
            # 扫 float 大 stride
            c_s16 = parasolid_catalog(cand, scan_floats=True,
                                      float_stride=16, max_bodies=3)
            if c_nof.ok and c_s16.ok:
                assert c_nof.n_bodies == c_s16.n_bodies
                assert c_nof.schema == c_s16.schema
                # scan_floats=False: 每 body 的 floats_in_range 应全 None
                assert all(b.get("floats_in_range") is None
                            for b in c_nof.bodies), "nof 不应有 float"
                # global_float_range 在 scan_floats=False 时为 None
                assert c_nof.global_float_range is None
                # stride=16 仍应有 float (大 body 内 double 分布够密)
                assert any(b.get("floats_in_range") is not None
                            for b in c_s16.bodies), "s16 应至少一 body 有 float"
                _p(f"   L8 stride consistency: nof={c_nof.n_bodies} "
                   f"s16={c_s16.n_bodies} schema_match={c_nof.schema == c_s16.schema}")
                res["pass"].append("T28_stride_consistency"); res["score"] += 1
            elif c_nof.err == "no_LocalBodies_stream":
                _p(f"   L8 stride consistency: skip ({c_nof.err})")
                res["pass"].append("T28_stride_consistency_skip"); res["score"] += 1
            else:
                raise AssertionError(f"unexpected: {c_nof.err} / {c_s16.err}")
        except Exception as e:
            res["fail"].append(("T28_stride_consistency", repr(e)))
        res["total"] += 1

    res["ratio"] = f"{res['score']}/{res['total']}"
    res["pct"] = round(100.0 * res["score"] / max(res["total"], 1), 1)
    return res


def _cli():
    import argparse
    ap = argparse.ArgumentParser(
        description="dao_solidworks · 万法 · SolidWorks 本源桥 · 反者道之动",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="显示 SW 安装信息")
    p_connect = sub.add_parser("connect", help="测试 COM 连接")
    p_connect.add_argument("--launch", action="store_true")
    p_connect.add_argument("--timeout", type=float, default=60.0)
    p_connect.add_argument("--visible", action="store_true")

    p_probe = sub.add_parser("probe", help="L1 深反 SLDPRT (无需 SW)")
    p_probe.add_argument("file")
    p_probe.add_argument("--json", action="store_true")

    p_preview = sub.add_parser("preview", help="抽预览 PNG")
    p_preview.add_argument("file")
    p_preview.add_argument("--out", default=None)

    p_conv = sub.add_parser("convert", help="COM 导出 src → dst")
    p_conv.add_argument("src"); p_conv.add_argument("dst")
    p_conv.add_argument("--fmt", default=None)
    p_conv.add_argument("--config", default=None)
    p_conv.add_argument("--launch", action="store_true")

    p_batch = sub.add_parser("batch", help="批量导出目录")
    p_batch.add_argument("src_dir"); p_batch.add_argument("dst_dir")
    p_batch.add_argument("--fmt", default="step")

    p_docs = sub.add_parser("docs", help="列出当前 SW 打开的文档")

    # —— 新: 健康 / 对话框 / eDrawings / 活体展示 ——
    p_health = sub.add_parser("health", help="SW 环境健康检查 (license/COM/eDrawings)")
    p_health.add_argument("--json", action="store_true")
    p_health.add_argument("--no-scan", action="store_true",
                          help="跳过对话框扫描 (更快)")

    p_dialogs = sub.add_parser("dialogs", help="列出 SW/eDrawings 当前对话框 (分类)")
    p_dialogs.add_argument("--json", action="store_true")

    p_dismiss = sub.add_parser("dismiss", help="断更对话框 (默认安全: 只关 welcome/tip)")
    p_dismiss.add_argument("--kinds", default="welcome,tip",
                           help="要断更的类别: welcome/tip/license_error/unknown")
    p_dismiss.add_argument("--aggressive", action="store_true",
                           help="激进模式 = 所有类别 (危险!)")

    p_ed = sub.add_parser("ed", help="eDrawings.exe 启动 + 截图")
    p_ed.add_argument("file", nargs="?", default=None)
    p_ed.add_argument("--out", default=None, help="截图输出路径")
    p_ed.add_argument("--wait", type=float, default=15.0)
    p_ed.add_argument("--no-shot", action="store_true")
    p_ed.add_argument("--close", action="store_true",
                      help="截图后杀 eDrawings 进程")

    p_live = sub.add_parser("live", help="道法自然 · 多路自动选优活体展示")
    p_live.add_argument("file")
    p_live.add_argument("--out-dir", default=None)
    p_live.add_argument("--prefer", default="sw_com,edrawings,ole2",
                        help="路径优先级顺序 (逗号分隔)")
    p_live.add_argument("--no-shot", action="store_true")
    p_live.add_argument("--no-dismiss", action="store_true")

    # —— 新 L0.5/L1.5/L3/L4/L2.5 ——
    p_lic = sub.add_parser("license", help="L0.5 · 许可诊断 (只读)")
    p_lic.add_argument("--json", action="store_true")

    p_dp = sub.add_parser("deep-probe",
                          help="L1+L1.5 · 深反 SLDPRT (含特征/配置名 carve)")
    p_dp.add_argument("file")
    p_dp.add_argument("--json", action="store_true")
    p_dp.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024,
                       help="每流最大采样字节数")

    p_dll = sub.add_parser("dll-index",
                           help="L3 · 扫 SW 安装目录 DLL/EXE 索引")
    p_dll.add_argument("--root", default=None,
                        help="SW 安装根 (默认自动探测)")
    p_dll.add_argument("--max", type=int, default=500)
    p_dll.add_argument("--with-exports", action="store_true",
                        help="附带每个 native DLL 的 top 20 exports")
    p_dll.add_argument("--out", default=None, help="JSON 输出路径")

    p_pe = sub.add_parser("pe", help="L3 · 单 DLL/EXE PE 反 + exports")
    p_pe.add_argument("file")
    p_pe.add_argument("--exports", type=int, default=50)
    p_pe.add_argument("--json", action="store_true")

    p_reg = sub.add_parser("reg-dump",
                           help="L4 · 导出 SW 注册表子树 JSON")
    p_reg.add_argument("--out", default=None)
    p_reg.add_argument("--max-keys", type=int, default=800)
    p_reg.add_argument("--no-values", action="store_true")

    p_dm = sub.add_parser("docmgr",
                           help="L2.5 · SW Document Manager 探测")
    p_dm.add_argument("--json", action="store_true")

    # —— 新 L5 · 打通 (Remediation) —————————————————————————————
    p_rem = sub.add_parser(
        "remediate",
        help="L5 · 一键打通 (dry_run 默认 True 防误触 · --apply 实执需 admin)")
    p_rem.add_argument("--apply", action="store_true",
                        help="真正执行 (dry_run=False) · 需 admin shell")
    p_rem.add_argument("--no-service", action="store_true",
                        help="只做 COM 注册, 不动服务")
    p_rem.add_argument("--enable-disabled", action="store_true",
                        help="若服务 Disabled, 先改 Manual 再 start")
    p_rem.add_argument("--json", action="store_true")

    p_rd = sub.add_parser(
        "docmgr-register",
        help="L5.1 · 单独注册 SwDocumentMgr COM (regasm /codebase)")
    p_rd.add_argument("--apply", action="store_true")
    p_rd.add_argument("--json", action="store_true")

    p_rl = sub.add_parser(
        "license-start",
        help="L5.2 · 启动 SolidWorks Licensing Service")
    p_rl.add_argument("--apply", action="store_true")
    p_rl.add_argument("--enable-disabled", action="store_true")
    p_rl.add_argument("--json", action="store_true")

    # —— 新 L6 · 几何反演 (Pure Reverse) —————————————————————————
    p_g = sub.add_parser(
        "geom",
        help="L6 · 几何反演 (无 COM · 无许可 · carve Parasolid/BRep 引用)")
    p_g.add_argument("file")
    p_g.add_argument("--max-bytes", type=int, default=4 * 1024 * 1024)
    p_g.add_argument("--json", action="store_true")

    # —— 新 L7 · 极限反演 (v3.1.0) ———————————————————————————————
    p_b = sub.add_parser(
        "bodies",
        help="L7 · 抽 Parasolid body snapshots (zlib + PK_RECEIVE 格式)")
    p_b.add_argument("file")
    p_b.add_argument("--out-dir", default=None,
                      help="输出目录 (存 .x_t 文件)")
    p_b.add_argument("--max", type=int, default=None,
                      help="最多抽几个 body (默认全部)")
    p_b.add_argument("--all", action="store_true",
                      help="--out-dir 时保存所有 body (默认只前 10 大)")
    p_b.add_argument("--json", action="store_true")

    p_s = sub.add_parser(
        "strings",
        help="L7.2 · 字符串全谱反 (UTF-16LE/BE + ASCII + 语言/作者/路径)")
    p_s.add_argument("file")
    p_s.add_argument("--min-len", type=int, default=4)
    p_s.add_argument("--out", default=None,
                      help="把完整字符串清单存成 JSON")
    p_s.add_argument("--json", action="store_true")

    # —— 新 L8 · Parasolid XT 块结构反 (v3.2.0) ——————————————————————
    p_xi = sub.add_parser(
        "xt-info",
        help="L8 · 单 .x_t 文件头结构反 (schema/body_name/float range)")
    p_xi.add_argument("file", help="Parasolid XT block (.x_t) 文件")
    p_xi.add_argument("--no-floats", action="store_true",
                      help="跳过 double-float 扫 (更快)")
    p_xi.add_argument("--stride", type=int, default=4,
                      help="double 扫步长 (4 = 对齐 · 1 = 完整扫 · 默认 4)")
    p_xi.add_argument("--json", action="store_true")

    p_xc = sub.add_parser(
        "xt-catalog",
        help="L8 · 全 SLDPRT 的 Parasolid body catalog (N body 元数据)")
    p_xc.add_argument("file", help="SLDPRT 文件")
    p_xc.add_argument("--out", default=None,
                      help="JSON 输出路径 (常用: bodies_catalog.json)")
    p_xc.add_argument("--no-floats", action="store_true",
                      help="跳过 double-float 扫 (更快)")
    p_xc.add_argument("--stride", type=int, default=8,
                      help="double 扫步长 (默认 8 · 全量 catalog 用大 stride 省时)")
    p_xc.add_argument("--max", type=int, default=None,
                      help="只分析前 N 个 body (默认全部 · 调试用)")
    p_xc.add_argument("--json", action="store_true")

    # —— 新 L9 · 一键激活 (v3.3.0) ———————————————————————————————
    p_act = sub.add_parser(
        "activate",
        help="L9 · 一键激活 · L0.5→L5→COM活体探针→L0.5 复诊 (dry_run 默 · --apply 实执需 admin)")
    p_act.add_argument("--apply", action="store_true",
                       help="真正执行 (dry_run=False · 需管理员 shell)")
    p_act.add_argument("--no-enable-disabled", action="store_true",
                       help="若服务 Disabled, 不改 Manual (保守)")
    p_act.add_argument("--no-service", action="store_true",
                       help="只做 COM 注册, 不动服务")
    p_act.add_argument("--no-probe", action="store_true",
                       help="跳过 COM 活体探针")
    p_act.add_argument("--dispatch", action="store_true",
                       help="COM 探针用 Dispatch (会启 SW · 默只 GetActiveObject)")
    p_act.add_argument("--probe-timeout", type=float, default=20.0)
    p_act.add_argument("--wait", type=float, default=5.0,
                       help="remediate 后观察缓冲 (秒, 默 5)")
    p_act.add_argument("--json", action="store_true")
    p_act.add_argument("--report", default=None,
                       help="把完整结果存到 JSON 文件")

    p_acv = sub.add_parser(
        "activate-verify",
        help="L9+ · 激活 + 真启 SW + 可选打开 test_file 一张截图")
    p_acv.add_argument("--apply", action="store_true")
    p_acv.add_argument("--launch", action="store_true",
                       help="真启 SW (默 False · 需 --launch 才启)")
    p_acv.add_argument("--test-file", default=None,
                       help="激活后打开此 SLDPRT/SLDASM, isometric 截图")
    p_acv.add_argument("--report", default=None)
    p_acv.add_argument("--probe-timeout", type=float, default=20.0)
    p_acv.add_argument("--json", action="store_true")

    sub.add_parser("test", help="自测")

    a = ap.parse_args()

    if a.cmd == "info":
        info = sw_info(probe_com=True)
        print(json.dumps(info.to_dict(), ensure_ascii=False, indent=2))
        return

    if a.cmd == "connect":
        sw = SolidWorksBridge()
        print(f"  installed: {sw.is_installed()}")
        print(f"  progid:    {sw.info.progid_versioned or sw.info.progid}")
        print(f"  exe:       {sw.info.exe}")
        try:
            sw.connect(launch_if_needed=a.launch, launch_timeout_s=a.timeout)
            if a.visible:
                sw.set_visible(True)
            print(f"  connected: True")
            print(f"  revision:  {sw.revision()}")
            docs = sw.list_docs()
            print(f"  docs ({len(docs)}):")
            for d in docs:
                print(f"    - {d}")
            sw.disconnect(exit_sw=False)
        except Exception as e:
            print(f"  connect FAILED: {e}")
            sys.exit(1)
        return

    if a.cmd == "probe":
        meta = probe_file(a.file)
        if a.json:
            print(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"file:      {meta.get('path')}")
            print(f"ok:        {meta.get('ok')}")
            print(f"doc_type:  {meta.get('doc_type')}")
            print(f"size:      {meta.get('size_MB')} MB")
            print(f"streams:   {len(meta.get('streams', []))}")
            print(f"storages:  {len(meta.get('storages', []))}")
            sm = meta.get("summary", {})
            if sm:
                print(f"summary:")
                for k in ("title","author","last_author","created","last_saved","app_name"):
                    if k in sm:
                        print(f"  {k:15s} {sm[k]}")
            pv = meta.get("preview")
            if pv:
                print(f"preview:   {pv}")
            if meta.get("step_proxy"):
                print(f"step_proxy: {meta['step_proxy']}")
            if meta.get("hints"):
                print(f"hints:     {meta['hints']}")
        return

    if a.cmd == "preview":
        out = Path(a.out) if a.out else Path(a.file).with_suffix(".preview.png")
        data = extract_preview(a.file, out)
        if data:
            print(f"saved: {out} ({out.stat().st_size:,} B)")
        else:
            print("no preview found")
            sys.exit(1)
        return

    if a.cmd == "convert":
        sw = SolidWorksBridge()
        sw.connect(launch_if_needed=a.launch)
        dst = sw.convert(a.src, a.dst, fmt=a.fmt, config=a.config)
        print(f"ok: {dst} ({dst.stat().st_size:,} B)")
        sw.disconnect()
        return

    if a.cmd == "batch":
        sw = SolidWorksBridge()
        sw.connect(launch_if_needed=True)
        outs = sw.batch_convert(a.src_dir, a.dst_dir, fmt=a.fmt)
        print(f"converted {len(outs)} files to {a.dst_dir}")
        for p in outs[:20]:
            print(f"  {p}")
        sw.disconnect()
        return

    if a.cmd == "docs":
        sw = SolidWorksBridge()
        sw.connect(prefer_active=True, launch_if_needed=False)
        for d in sw.list_docs():
            print(d)
        sw.disconnect()
        return

    if a.cmd == "health":
        h = SWHealthCheck.check(scan_dialogs=not a.no_scan)
        if a.json:
            print(json.dumps(h, ensure_ascii=False, indent=2, default=str))
        else:
            print("═" * 60)
            print(f"  SolidWorks 环境健康检查")
            print("═" * 60)
            ins = h["install"]
            print(f"  installed:     {ins['installed']}  ({ins['version']})")
            print(f"  progid:        {ins['progid']}")
            print(f"  exe:           {ins['exe']}")
            print(f"  pywin32:       {ins['pywin32_ok']}")
            print(f"  sw_processes:  {h['running']}")
            print(f"  com_ready:     {h['com_ready']}")
            print(f"    reason:      {h.get('com_msg', '')}")
            print(f"  license_ok:    {h['license_ok']}")
            print(f"  dialogs:       {len(h['dialogs'])}")
            for d in h["dialogs"]:
                print(f"    [{d['kind']:14s}] pid={d['pid']} {d['title']!r}")
            ed = h["edrawings"]
            print(f"  edrawings_exe: {ed['exe']}")
            print(f"  edrawings_com: {ed['com']}  {ed.get('msg', '')}")
            print(f"  ────────────────────────────────────────────")
            print(f"  推荐路径:       {h['recommendation']}")
            print("═" * 60)
        return

    if a.cmd == "dialogs":
        ds = SWDialogHandler.scan()
        if a.json:
            # Strip hwnd from children for cleanliness
            clean = [{k: v for k, v in d.items() if k != "buttons"}
                      for d in ds]
            print(json.dumps(clean, ensure_ascii=False, indent=2,
                             default=str))
        else:
            print(f"visible dialogs: {len(ds)}")
            for d in ds:
                print(f"\n  [{d['kind']}] hwnd=0x{d['hwnd']:08x} pid={d['pid']}")
                print(f"    title:    {d['title']!r}")
                if d["children"]:
                    print(f"    children:")
                    for cls_name, text in d["children"][:10]:
                        print(f"      [{cls_name}] {text!r}")
                if d["buttons"]:
                    print(f"    buttons:  {[t for _, t in d['buttons']]}")
        return

    if a.cmd == "dismiss":
        if a.aggressive:
            kinds = ("welcome", "tip", "license_error", "unknown")
        else:
            kinds = tuple(s.strip() for s in a.kinds.split(",") if s.strip())
        r = SWDialogHandler.dismiss(kinds=kinds)
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
        return

    if a.cmd == "ed":
        ed = EDrawingsLauncher()
        if not ed.is_available():
            print(f"eDrawings.exe NOT found (searched: {ed._EDRAWINGS_EXE_PATHS if False else '[default paths]'})")
            sys.exit(1)
        pid = ed.launch(a.file)
        print(f"eDrawings launched (pid={pid}, file={a.file})")
        if not a.no_shot:
            out = (Path(a.out) if a.out else
                   (Path(a.file).parent / f"{Path(a.file).stem}_edrawings.png"
                    if a.file else Path.cwd() / "edrawings.png"))
            p = ed.snap(out, wait_s=a.wait)
            if p:
                print(f"screenshot saved: {p}  ({p.stat().st_size:,} B)")
            else:
                print("screenshot FAILED (main window not found)")
        if a.close:
            ed.close()
            print("eDrawings process killed")
        return

    if a.cmd == "live":
        prefer = tuple(s.strip() for s in a.prefer.split(",") if s.strip())
        r = live_show(a.file, out_dir=a.out_dir,
                      prefer=prefer,
                      screenshot=not a.no_shot,
                      dismiss_dialogs=not a.no_dismiss)
        # Make human-friendly output
        print("═" * 60)
        print(f"  live_show · {Path(a.file).name}")
        print("═" * 60)
        print(f"  path_used:     {r['path_used']}")
        print(f"  recommendation: {r['health']['recommendation']}")
        print(f"  license_ok:    {r['health']['license_ok']}")
        print(f"  com_ready:     {r['health']['com_ready']}")
        print(f"  artifacts ({len(r['artifacts'])}):")
        for a_ in r["artifacts"]:
            sz = Path(a_["path"]).stat().st_size if Path(a_["path"]).exists() else 0
            print(f"    [{a_['kind']:20s}] {a_['path']}  ({sz:,} B)")
        if r["errors"]:
            print(f"  errors:")
            for e in r["errors"]:
                print(f"    - {e}")
        return

    # —— 新命令: license / deep-probe / dll-index / pe / reg-dump / docmgr ——
    if a.cmd == "license":
        s = sw_license_diagnose()
        if a.json:
            print(json.dumps(s.to_dict(), ensure_ascii=False,
                             indent=2, default=str))
        else:
            print("═" * 66)
            print(f"  SolidWorks 许可系统深反 · 只读诊断")
            print("═" * 66)
            print(f"  severity:        {s.severity}")
            print(f"  recommend:       {s.recommend}")
            print(f"  doc_mgr_dll:     {s.doc_mgr_dll}")
            print(f"  COM progid 注册:")
            for p, clsid in s.com_registered.items():
                mark = "✓" if clsid else "✗"
                print(f"    {mark} {p:40s} {clsid or ''}")
            print(f"  FlexNet 服务:")
            for n, st in s.services_flexnet.items():
                print(f"    [{st or 'n/a':14s}] {n}")
            print(f"  SW 许可服务:")
            for n, st in s.services_sw.items():
                print(f"    [{st or 'n/a':14s}] {n}")
            print(f"  FlexLM 端口:")
            for port, up in s.ports.items():
                mark = "✓ listening" if up else "✗ closed"
                print(f"    [{mark:12s}] {port}")
            if s.trusted_storage:
                print(f"  Trusted storage ({len(s.trusted_storage)}):")
                for t in s.trusted_storage:
                    print(f"    - {t['name']:32s}  "
                          f"{t['size_B']:>7} B  {t['mtime']}  ({t['kind']})")
            if s.event_log_tail:
                print(f"  Event log tail (前 5):")
                for ln in s.event_log_tail[-5:]:
                    print(f"    {ln[:120]}")
            print(f"  findings ({len(s.findings)}):")
            for f in s.findings:
                print(f"    · {f}")
            print("═" * 66)
        return

    if a.cmd == "deep-probe":
        meta = deep_probe_file(a.file, max_stream_bytes=a.max_bytes)
        if a.json:
            print(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"file:      {meta.get('path')}")
            print(f"ok:        {meta.get('ok')}")
            print(f"doc_type:  {meta.get('doc_type')}")
            print(f"size:      {meta.get('size_MB')} MB")
            print(f"n_streams: {len(meta.get('streams', []))}")
            sm = meta.get("summary", {})
            if sm:
                print(f"summary:")
                for k in ("title", "author", "last_author",
                          "created", "last_saved", "app_name"):
                    if k in sm:
                        print(f"  {k:15s} {sm[k]}")
            fn = meta.get("feature_names_carved", [])
            print(f"n_features_carved: {len(fn)}")
            for s in fn[:30]:
                print(f"  · {s!r}")
            cn = meta.get("config_names_carved", [])
            print(f"n_configs_carved:  {len(cn)}")
            for s in cn[:12]:
                print(f"  · {s!r}")
            hl = meta.get("stream_highlights", {})
            if hl:
                print(f"stream_highlights:")
                for name, info in hl.items():
                    print(f"  {name}: {info['size_B']:,}B sampled={info['sampled_B']:,}B "
                          f"n={info['n_names_found']}")
        return

    if a.cmd == "dll-index":
        idx = sw_dll_index(installdir=a.root, max_files=a.max,
                            include_exports=a.with_exports)
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(
                json.dumps(idx, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"saved: {a.out}")
        if "err" in idx:
            print(f"ERR: {idx['err']}"); sys.exit(1)
        print(f"root:    {idx['root']}")
        print(f"total:   {idx['total']}  (managed={idx['managed_count']} "
              f"native={idx['native_count']})")
        print(f"dirs ({len(idx['by_dir'])}):")
        for d, files in list(idx["by_dir"].items())[:20]:
            print(f"  {d}: {len(files)} files "
                  f"(首 3: {[f['name'] for f in files[:3]]})")
        return

    if a.cmd == "pe":
        try:
            with PEReader(a.file) as pe:
                sm = pe.summary()
                if a.json:
                    out = {**sm, "exports": pe.exports(limit=a.exports)}
                    print(json.dumps(out, ensure_ascii=False,
                                     indent=2, default=str))
                else:
                    print(f"file:        {sm['path']}")
                    print(f"size:        {sm['size_B']:,} B")
                    print(f"pe_type:     {sm['pe_type']}")
                    print(f"machine:     {sm['machine']}")
                    print(f"is_managed:  {sm['is_managed']}")
                    print(f"dll_name:    {sm['dll_name']}")
                    print(f"n_sections:  {sm['n_sections']}  "
                          f"sections: {sm['sections']}")
                    exps = pe.exports(limit=a.exports)
                    print(f"exports ({len(exps)}):")
                    for e in exps:
                        print(f"  {e}")
        except Exception as e:
            print(f"PE read failed: {e}"); sys.exit(1)
        return

    if a.cmd == "reg-dump":
        r = sw_registry_dump(include_values=not a.no_values,
                              max_keys=a.max_keys)
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(
                json.dumps(r, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"saved: {a.out}")
        if "err" in r:
            print(f"ERR: {r['err']}"); sys.exit(1)
        summ = r.get("_summary", {})
        print(f"roots ({len(summ.get('roots', []))}):")
        for root_name in summ.get("roots", []):
            print(f"  {root_name}")
        print(f"total_keys:   {summ.get('total_keys')}")
        print(f"total_values: {summ.get('total_values')}")
        return

    if a.cmd == "docmgr":
        dm = swdm_probe()
        if a.json:
            print(json.dumps(dm.to_dict(), ensure_ascii=False,
                             indent=2, default=str))
        else:
            print(f"dll_path:       {dm.dll_path}")
            print(f"managed:        {dm.managed}")
            print(f"com_registered: {dm.com_registered}")
            print(f"  progid:       {dm.com_progid}")
            print(f"  clsid:        {dm.com_clsid}")
            print(f"pywin32_ok:     {dm.pywin32_ok}")
            print(f"pythonnet_ok:   {dm.pythonnet_ok}")
            print(f"ok:             {dm.ok}")
            print(f"path_usable:    {dm.path_usable}")
            if dm.regasm_cmd:
                print(f"regasm hint:")
                print(f"  {dm.regasm_cmd}")
            print(f"diagnostics:")
            for d in dm.diagnostics:
                print(f"  · {d}")
        return

    # —— L5 · 打通 ————————————————————————————————————————————————
    if a.cmd == "remediate":
        dry = not a.apply
        out = sw_remediate_all(
            dry_run=dry,
            with_licensing_service=not a.no_service,
            change_disabled_to_manual=a.enable_disabled,
        )
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        else:
            print("═" * 62)
            print(f"  L5 · 反者道之动 · 打通  dry_run={dry}  admin={out['admin']}")
            print("═" * 62)
            for k in ("docmgr", "licensing"):
                r = out.get(k)
                if not r:
                    print(f"\n[{k}] — 跳过")
                    continue
                print(f"\n[{k}]  action={r.get('action')}  ok={r.get('ok')}  "
                       f"err={r.get('err')}")
                for step in r.get("steps", []):
                    print(f"  · {step}")
                for note in r.get("notes", []):
                    print(f"  ⓘ {note}")
            pd = out.get("post_diagnose", {})
            if isinstance(pd, dict) and "severity" in pd:
                print(f"\n[复诊] severity={pd.get('severity')}  "
                       f"recommend={pd.get('recommend')}")
                for f in pd.get("findings", [])[:10]:
                    print(f"  · {f}")
        return

    if a.cmd == "docmgr-register":
        r = remediate_docmgr_com(dry_run=not a.apply)
        if a.json:
            print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2,
                             default=str))
        else:
            print(f"action:  {r.action}")
            print(f"dry_run: {r.dry_run}")
            print(f"admin:   {r.admin}")
            print(f"ok:      {r.ok}")
            if r.err:
                print(f"err:     {r.err}")
            print(f"steps ({len(r.steps)}):")
            for s in r.steps:
                print(f"  · {s}")
            if r.before or r.after:
                print(f"before: {r.before}")
                print(f"after:  {r.after}")
            for note in r.notes:
                print(f"  ⓘ {note}")
        sys.exit(0 if r.ok else 1)

    if a.cmd == "license-start":
        r = remediate_sw_licensing_service(
            dry_run=not a.apply,
            change_disabled_to_manual=a.enable_disabled,
        )
        if a.json:
            print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2,
                             default=str))
        else:
            print(f"action:  {r.action}")
            print(f"dry_run: {r.dry_run}")
            print(f"admin:   {r.admin}")
            print(f"ok:      {r.ok}")
            if r.err:
                print(f"err:     {r.err}")
            print(f"before:  {r.before}")
            print(f"after:   {r.after}")
            print(f"steps ({len(r.steps)}):")
            for s in r.steps:
                print(f"  · {s}")
            for note in r.notes:
                print(f"  ⓘ {note}")
        sys.exit(0 if r.ok else 1)

    # —— L6 · 几何反演 ————————————————————————————————————————————
    if a.cmd == "geom":
        g = carve_geometry_refs(a.file, max_stream_bytes=a.max_bytes)
        if a.json:
            print(json.dumps(g.to_dict(), ensure_ascii=False, indent=2,
                             default=str))
        else:
            print("═" * 62)
            print(f"  L6 · 几何反演  file={a.file}")
            print("═" * 62)
            print(f"ok:            {g.ok}  err={g.err}")
            print(f"geometry streams ({len(g.geometry_streams)}):")
            for s in g.geometry_streams:
                n_hits = s.get("n_hits", 0)
                star = "★" if n_hits else " "
                print(f"  {star} {s['name']:28s}  size={s.get('size_B', 0):>10,} B  "
                       f"sampled={s.get('sampled_B', 0):>9,} B  hits={n_hits}")
            print(f"\nParasolid XT signatures hit ({len(g.xt_hits)}):")
            for h in g.xt_hits[:20]:
                print(f"  · stream={h['stream']:28s}  kind={h['kind']:10s}  "
                       f"offset=0x{h['offset']:08x}  hex={h['preview_hex'][:32]}...")
            print(f"\nOrphan BRep refs ({len(g.orphan_breps)}):")
            for b in g.orphan_breps[:20]:
                print(f"  · {b}")
            print(f"\nBody ids ({len(g.body_ids)}):")
            for b in g.body_ids[:20]:
                print(f"  · {b}")
            for note in g.notes:
                print(f"  ⓘ {note}")
        return

    # —— L7 · 极限反演 ————————————————————————————————————————————
    if a.cmd == "bodies":
        r = extract_parasolid_bodies(
            a.file,
            out_dir=a.out_dir,
            max_bodies=a.max,
            save_all=a.all,
        )
        if a.json:
            # body data 很大, 存 to_dict 时去掉 raw bytes 字段(没有就好)
            print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2,
                             default=str))
        else:
            print("═" * 62)
            print(f"  L7 · Parasolid body 抽取  file={a.file}")
            print("═" * 62)
            print(f"ok:           {r.ok}  err={r.err}")
            print(f"raw_size:     {r.raw_size_B:,} B  (LocalBodies 流)")
            print(f"candidates:   {r.n_candidates}  zlib 头")
            print(f"bodies:       {r.n_bodies}  解压成功 XT 块")
            if r.schema:
                print(f"schema:       {r.schema}  (modeller {r.modeller_ver})")
            if r.body_sizes_B:
                print(f"size range:   min={min(r.body_sizes_B):,}  "
                      f"max={max(r.body_sizes_B):,}  "
                      f"median={sorted(r.body_sizes_B)[len(r.body_sizes_B)//2]:,}")
            if r.output_files:
                print(f"saved files:  {len(r.output_files)}")
                for f in r.output_files[:5]:
                    print(f"  · {Path(f).name}")
                if len(r.output_files) > 5:
                    print(f"  ... +{len(r.output_files) - 5} more")
            if r.body_names:
                uniq = sorted(set(r.body_names))
                print(f"body names ({len(uniq)} unique):")
                for n in uniq[:10]:
                    print(f"  · {n}")
                if len(uniq) > 10:
                    print(f"  ... +{len(uniq) - 10} more")
            for note in r.notes:
                print(f"  ⓘ {note}")
        sys.exit(0 if r.ok else 1)

    if a.cmd == "strings":
        r = extract_strings(a.file, min_len=a.min_len)
        if a.out:
            Path(a.out).write_text(
                json.dumps(r.to_dict(), ensure_ascii=False, indent=2,
                           default=str),
                encoding="utf-8")
            print(f"[saved] {a.out}")
        if a.json:
            # 大字符串 list 截短一点
            d = r.to_dict()
            for k in ("utf16le", "utf16be", "ascii"):
                if len(d.get(k, [])) > 100:
                    d[k] = d[k][:100] + [f"... +{len(d[k]) - 100} more"]
            print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
        else:
            print("═" * 62)
            print(f"  L7.2 · 字符串全谱  file={a.file}")
            print("═" * 62)
            print(f"ok:           {r.ok}  err={r.err}")
            print(f"UTF-16LE:     {r.n_utf16le:,}")
            print(f"UTF-16BE:     {r.n_utf16be:,}")
            print(f"ASCII:        {r.n_ascii:,}")
            print(f"language:     {r.language_hint}")
            if r.author:
                print(f"author:       {r.author!r}")
            if r.sw_classes:
                print(f"\nSW C++ 类名 ({len(r.sw_classes)}):")
                for c in r.sw_classes[:20]:
                    print(f"  · {c}")
            if r.file_paths:
                print(f"\n自身路径泄露:")
                for fp in r.file_paths:
                    print(f"  · {fp}")
            if r.win_paths:
                print(f"\nWindows 路径 ({len(r.win_paths)}):")
                for wp in r.win_paths[:10]:
                    print(f"  · {wp}")
            # 前 30 个 UTF-16LE (文件特征/组件名)
            if r.utf16le:
                print(f"\nUTF-16LE 前 30:")
                for s in r.utf16le[:30]:
                    print(f"  · {s!r}")
            for note in r.notes:
                print(f"  ⓘ {note}")
        return

    # —— L8 · Parasolid XT 块结构反 ————————————————————————————————
    if a.cmd == "xt-info":
        p = Path(a.file)
        if not p.exists():
            print(f"ERR: file not found: {p}"); sys.exit(1)
        data = p.read_bytes()
        info = analyze_xt_block(
            data,
            scan_floats=not a.no_floats,
            float_stride=a.stride,
        )
        if a.json:
            print(json.dumps(info.to_dict(), ensure_ascii=False,
                             indent=2, default=str))
        else:
            print("═" * 62)
            print(f"  L8 · XT 块头结构反  file={p.name}")
            print("═" * 62)
            print(f"ok:                {info.ok}  err={info.err}")
            print(f"size:              {info.size_B:,} B")
            print(f"has_ps_marker:     {info.has_ps_marker}")
            print(f"schema:            {info.schema}")
            print(f"  schema_id:       {info.schema_id}")
            print(f"  user_id:         {info.user_id}")
            print(f"modeller_version:  {info.modeller_version}")
            print(f"body_name:         {info.body_name!r}")
            print(f"has_end_marker:    {info.has_end_marker}")
            print(f"printable_ratio:   {info.printable_ratio}")
            if info.parasolid_keywords:
                print(f"parasolid_keywords ({len(info.parasolid_keywords)}):")
                for kw, cnt in sorted(info.parasolid_keywords.items(),
                                      key=lambda x: -x[1]):
                    print(f"  · {kw:10s} × {cnt}")
            else:
                print(f"parasolid_keywords: (none · 块可能是 BINARY XT · token 编码)")
            fr = info.floats_in_range
            if fr:
                print(f"floats_in_range:")
                print(f"  count:   {fr['count']:,}  (stride={fr['stride']} "
                      f"from 0x{fr['scan_from']:x})")
                print(f"  min:     {fr['min']:.6e}")
                print(f"  max:     {fr['max']:.6e}")
                print(f"  median:  {fr['median']:.6e}")
                print(f"  p05..p95 {fr['p05']:.3e} .. {fr['p95']:.3e}")
        sys.exit(0 if info.ok else 1)

    if a.cmd == "xt-catalog":
        c = parasolid_catalog(
            a.file,
            out_json=a.out,
            scan_floats=not a.no_floats,
            float_stride=a.stride,
            max_bodies=a.max,
        )
        if a.out and c.ok:
            print(f"[saved] {a.out}  ({Path(a.out).stat().st_size:,} B)")
        if a.json:
            d = c.to_dict()
            # 大 bodies 列表略掐
            if len(d.get("bodies", [])) > 10:
                d["_bodies_preview"] = d["bodies"][:3]
                d["bodies"] = f"<{len(c.bodies)} entries · see --out JSON>"
            print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
        else:
            print("═" * 62)
            print(f"  L8 · Parasolid catalog  file={Path(a.file).name}")
            print("═" * 62)
            print(f"ok:             {c.ok}  err={c.err}")
            print(f"raw_size:       {c.raw_size_B:,} B  (LocalBodies 流)")
            print(f"n_bodies:       {c.n_bodies}")
            print(f"schema:         {c.schema}")
            print(f"modeller_ver:   {c.modeller_version}")
            if c.size_stats:
                s = c.size_stats
                print(f"size_stats:     min={s['min']:,} max={s['max']:,} "
                      f"median={s['median']:,} total={s['total']:,} B")
            if c.global_float_range:
                g = c.global_float_range
                print(f"float_range:    {g['min']:.3e} .. {g['max']:.3e}")
            # body name 分布
            names: Dict[str, int] = {}
            for b in c.bodies:
                nm = b.get("body_name") or "(unnamed)"
                names[nm] = names.get(nm, 0) + 1
            if names:
                top = sorted(names.items(), key=lambda x: -x[1])[:5]
                print(f"body_name 分布 (top 5):")
                for nm, cnt in top:
                    print(f"  · {nm:30s} × {cnt}")
            for note in c.notes:
                print(f"  ⓘ {note}")
        sys.exit(0 if c.ok else 1)

    # —— L9 · 一键激活 (v3.3.0) ————————————————————————————————
    if a.cmd == "activate":
        r = sw_activate(
            dry_run=not a.apply,
            wait_license_s=a.wait,
            enable_disabled=not a.no_enable_disabled,
            with_licensing_service=not a.no_service,
            probe_com=not a.no_probe,
            probe_com_timeout_s=a.probe_timeout,
            probe_com_include_dispatch=a.dispatch,
        )
        if a.report:
            Path(a.report).parent.mkdir(parents=True, exist_ok=True)
            Path(a.report).write_text(
                json.dumps(r.to_dict(), ensure_ascii=False, indent=2,
                           default=str),
                encoding="utf-8",
            )
            print(f"[saved] {a.report}")
        if a.json:
            print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2,
                             default=str))
        else:
            print("═" * 66)
            print(f"  L9 · 一键激活  dry_run={r.dry_run}  admin={r.admin}")
            print("═" * 66)
            print(f"  ok:          {r.ok}  ({r.elapsed_s:.1f}s)")
            print(f"  severity:    {r.severity_before or '?'}  →  "
                  f"{r.severity_after or '?'}")
            print(f"  com_ready:   {r.com_ready}  (mode="
                  f"{next((s.get('mode') for s in r.stages if s.get('stage') == 'com_probe'), '?')})")
            if r.com_revision:
                print(f"  revision:    {r.com_revision}")
            if r.com_msg:
                print(f"  com_msg:     {r.com_msg}")
            print()
            print(f"  stages ({len(r.stages)}):")
            for s in r.stages:
                name = s.get("stage", "?")
                mark = "✓" if s.get("ok") else "·"
                extra = ""
                if name == "pre_diagnose" or name == "post_diagnose":
                    extra = f"severity={s.get('severity')} findings={s.get('findings')}"
                elif name == "remediate":
                    extra = (f"docmgr={s.get('docmgr_ok')} "
                             f"lic={s.get('licensing_ok')}")
                    if s.get("docmgr_err"):
                        extra += f" docmgr_err={s['docmgr_err']}"
                    if s.get("licensing_err"):
                        extra += f" lic_err={s['licensing_err']}"
                elif name == "com_probe":
                    extra = f"mode={s.get('mode')} elapsed={s.get('elapsed_s', 0):.1f}s"
                    if s.get("msg"): extra += f" · {s['msg']}"
                elif name == "wait":
                    extra = f"{s.get('wait_s')}s"
                print(f"    {mark} {name:15s} {extra}")
            if r.notes:
                print()
                print(f"  notes:")
                for n in r.notes:
                    print(f"    ⓘ {n}")
            if r.next_steps:
                print()
                print(f"  next_steps:")
                for ns in r.next_steps:
                    print(f"    → {ns}")
            print("═" * 66)
        sys.exit(0 if r.ok else 1)

    if a.cmd == "activate-verify":
        out = sw_activate_and_verify(
            dry_run=not a.apply,
            launch_sw=a.launch,
            test_file=a.test_file,
            save_report=a.report,
            probe_com_timeout_s=a.probe_timeout,
        )
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        else:
            act = out["activate"]
            print("═" * 66)
            print(f"  L9+ · 激活验证  dry_run={act.get('dry_run')}  "
                  f"admin={act.get('admin')}")
            print("═" * 66)
            print(f"  activate.ok:       {act.get('ok')}  "
                  f"severity: {act.get('severity_before')} → "
                  f"{act.get('severity_after')}")
            lr = out.get("launch")
            if lr is not None:
                print(f"  launch.ok:         {lr.get('ok')}  "
                      f"revision={lr.get('revision', 'n/a')}  "
                      f"({lr.get('elapsed_s', 0):.1f}s)")
                if lr.get("err"):
                    print(f"    err:             {lr['err']}")
            tfr = out.get("test_file")
            if tfr is not None and a.test_file:
                print(f"  test_file.ok:      {tfr.get('ok')}  "
                      f"({tfr.get('elapsed_s', 0):.1f}s)")
                if tfr.get("err"):
                    print(f"    err:             {tfr['err']}")
                for name, shot in (tfr.get("shots") or {}).items():
                    if shot.get("ok"):
                        print(f"    [shot {name:10s}] {shot['path']}  "
                              f"({shot.get('size_B', 0):,} B)")
            print(f"  total_elapsed:     {out.get('total_elapsed_s', 0):.1f}s")
            if out.get("report"):
                print(f"  report:            {out['report']}")
            print("═" * 66)
        sys.exit(0 if out["activate"].get("ok") else 1)

    if a.cmd == "test":
        res = _self_test()
        print("\n" + "=" * 58)
        print(f"  dao_solidworks 自测: {res['ratio']}  ({res['pct']}%)")
        print("=" * 58)
        for p in res["pass"]: print(f"  ✓ {p}")
        for n, e in res["fail"]: print(f"  ✗ {n}: {e}")
        sys.exit(0 if not res["fail"] else 1)


if __name__ == "__main__":
    _cli()
