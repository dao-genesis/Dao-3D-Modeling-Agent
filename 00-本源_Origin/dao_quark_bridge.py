#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dao_quark_bridge.py — 万法 · 夸克网盘 × 3D建模Agent · 道法自然桥
═══════════════════════════════════════════════════════════════════════

纲要
    "道法自然 · 无之以为用" — 不重建认证, 借夸克客户端自身 CDP + 登录态.
    此桥是 3D建模Agent 向夸克网盘伸出的一只手, 目的单一:
      把夸克网盘里的 SW 安装包 / SLDPRT 件 / 许可工具 等拉到本机,
      交给 dao_solidworks.py 就地反演 / 活体展示.

两层并行
    L0 · 探测 (不依赖 CDP)      — 夸克 App 进程? CDP :19222 存活?
                                  夸克网盘 (兄弟项目) 代码在哪?
    L1 · 驱动 (依赖 CDP + 登录) — 解析分享链接 / 遍历自己的 drive /
                                  取下载 URL / 流式下载到本机

用户五感归夸克 (不画浮层)
    本模块只在终端打印 `_stamp()` 进度, 不注入任何 UI.
    用户看到的文件仍在夸克客户端原生 UI.

架构 (与 10-反笙_FreeCAD/sw_show.py 并列)
    3D建模Agent/00-本源_Origin/dao_quark_bridge.py    ← 本文件
         │  (soft-import, sys.path.insert)
         ▼
    夸克网盘/dao_http.py  (126+ REST · 纯 stdlib · 无外部依赖)
         │  (Runtime.evaluate)
         ▼
    CDP :19222 → 夸克客户端 → drive-pc.quark.cn REST

核心 API · DaoQuarkBridge
    status()                        → 全景: App/CDP/dao_http 三态
    connect(verbose=False)           尝试绑定一个活 quark target
    ls(pdir_fid="0")                 列目录
    ls_path("/SolidWorks软件安装包") 路径式列目录 (自动逐段解析)
    find(substr, [cat])              全局搜索 (可按类过滤)
    info(fid)                        单 fid 元信息
    path_of(fid)                     反查 fid → /a/b/c 路径
    get_url(fid)                     取短期签名下载 URL
    download(fid, dst, *, sha=, chunk=, progress=, max_retries=)
                                     流式下载, 断点续传, 校验 SHA (可选)
    pull(name_or_path, dst, ...)     find + download 一气呵成
    pull_folder(fid_or_path, dst_dir, filter=..., progress=...)
                                     文件夹递归下载 (按 include 正则过滤)
    share_resolve(url_or_id, passcode="") → ShareInfo (含 pwd_id, stoken, files)
    share_pull(url, passcode, dst, filter=..., save_first=True)
                                     分享链接 → 本机文件 (含可选"先转存")

SolidWorks 快捷路径
    sw_installer_locate(prefer="pan")  → 在夸克 drive 找 SolidWorks 安装包
    sw_installer_pull(dst_dir, ...)    → 把主安装包拉到 70-天下_World/sw/

CLI
    python dao_quark_bridge.py status
    python dao_quark_bridge.py ls [pdir_fid]
    python dao_quark_bridge.py ls-path /SolidWorks软件安装包
    python dao_quark_bridge.py find SolidWorks
    python dao_quark_bridge.py info <fid>
    python dao_quark_bridge.py url <fid>
    python dao_quark_bridge.py get <fid> [out_path]
    python dao_quark_bridge.py pull <name|path> [dst]
    python dao_quark_bridge.py pull-folder <fid|path> <dst_dir> [--filter regex]
    python dao_quark_bridge.py share <url> [--passcode <pwd>] [--save]
    python dao_quark_bridge.py share-pull <url> [--passcode <pwd>] <dst>
    python dao_quark_bridge.py sw-locate
    python dao_quark_bridge.py sw-pull [--dst <dir>] [--what installer|license|docx|all]
    python dao_quark_bridge.py test

依赖
    · 无新三方包 (纯 stdlib + websocket-client, 已由夸克网盘 requirements 提供)
    · Windows 下需要夸克客户端以 CDP :19222 启动 (见 夸克网盘/启动夸克CDP.cmd)

工程原则
    - 失败时报具体错因, 提示下一步 (启 CDP / 登录 / 确认 Quark 进程)
    - 下载: 大文件流式 · 支持 Range 断点续传 · SHA256 校验 (可选)
    - 不保存 cookie 到本机磁盘 (只在内存里短暂传给 urllib 请求头)
    - 幂等: 同一 dst 已存在且大小/SHA 正确则跳过
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# ─── 路径引导 · 五层 sys.path 自动注入 ──────────────────────────────────
_HERE = Path(__file__).resolve().parent
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / "_paths.py").is_file()), _HERE.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
try:
    import _paths as _dao_paths  # noqa: F401
except Exception:
    _dao_paths = None  # type: ignore


# ─── 探测夸克网盘兄弟项目位置 ──────────────────────────────────────────
def _find_quark_project() -> Optional[Path]:
    """按 convention 查找 "夸克网盘/dao_http.py" 所在目录.

    查找顺序:
        1. 环境变量 DAO_QUARK_PROJECT
        2. 3D建模Agent 同级: ../夸克网盘/
        3. 3D建模Agent 根级: ./夸克网盘/
        4. 用户根: e:/道/道生一/一生二/夸克网盘/
    """
    env = os.environ.get("DAO_QUARK_PROJECT")
    if env and (Path(env) / "dao_http.py").is_file():
        return Path(env).resolve()

    if _dao_paths is not None:
        root = _dao_paths.ROOT  # type: ignore[attr-defined]
        cands = [
            root.parent / "夸克网盘",
            root / "夸克网盘",
        ]
    else:
        cands = [_HERE.parent.parent / "夸克网盘"]

    # 也试一下 e:\道\道生一\一生二\夸克网盘
    cands.append(Path(r"E:\道\道生一\一生二\夸克网盘"))
    cands.append(Path(r"e:\道\道生一\一生二\夸克网盘"))

    for c in cands:
        try:
            if (c / "dao_http.py").is_file():
                return c.resolve()
        except Exception:
            continue
    return None


QUARK_PROJECT: Optional[Path] = _find_quark_project()
if QUARK_PROJECT is not None and str(QUARK_PROJECT) not in sys.path:
    sys.path.insert(0, str(QUARK_PROJECT))


__version__ = "1.0.0"
__all__ = [
    "DaoQuarkBridge", "QuarkBridgeError", "QuarkStatus",
    "QuarkFile", "ShareInfo", "DownloadResult",
    "share_url_to_pwd_id", "parse_share_url",
]


# ────────────────────────────────────────────────────────────────────────
# 终端 stamp (与夸克网盘风格保持一致 · 道法自然)
# ────────────────────────────────────────────────────────────────────────
_NOW = lambda: time.strftime("%H:%M:%S")  # noqa: E731

def _stamp(kind: str, msg: str) -> None:
    """终端带级别的进度戳. kind: OK|WARN|ERR|STEP|INFO|DL"""
    tag = {
        "OK":   "✓",
        "WARN": "!",
        "ERR":  "✗",
        "STEP": "·",
        "INFO": " ",
        "DL":   "↓",
        "Q":    "Q",
    }.get(kind.upper(), kind)
    print(f"[{_NOW()}] {tag} {msg}", flush=True)


def _human_size(n: Optional[int]) -> str:
    if n is None: return "?"
    n = int(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if isinstance(n, float) else f"{n}{unit}"
        n = n / 1024 if unit != "B" else n // 1024 if isinstance(n, int) else n / 1024
    return f"{n:.1f}PB"


# ────────────────────────────────────────────────────────────────────────
# 错误
# ────────────────────────────────────────────────────────────────────────
class QuarkBridgeError(RuntimeError):
    """所有本模块的语义异常."""


# ────────────────────────────────────────────────────────────────────────
# 数据结构
# ────────────────────────────────────────────────────────────────────────
@dataclass
class QuarkStatus:
    quark_app_running: bool = False                 # quark.exe 进程存在
    quark_app_count:   int = 0
    cdp_up:            bool = False                 # :19222/json/version 可达
    cdp_targets:       int = 0                      # CDP target 总数
    quark_target_alive: bool = False                # 可登录, fetch() 成功
    dao_http_importable: bool = False               # 兄弟项目可导入
    dao_http_version:  Optional[str] = None
    quark_project_dir: Optional[str] = None
    ws_origin:         Optional[str] = None         # 活 target 的 origin
    ws_title:          Optional[str] = None
    advice:            List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuarkFile:
    fid:       str
    name:      str
    size:      Optional[int] = None
    file_type: Optional[int] = None    # 0=dir, 1=file
    category:  Optional[int] = None    # 1=video, 2=audio, 3=image, 4=doc, 5=compress
    pdir_fid:  Optional[str] = None
    path:      Optional[str] = None    # /a/b/c.ext (full path, 若 API 提供)
    updated_at: Optional[int] = None

    @property
    def is_dir(self) -> bool:
        return self.file_type == 0

    @classmethod
    def from_api(cls, d: Dict[str, Any]) -> "QuarkFile":
        return cls(
            fid       = d.get("fid") or d.get("file_id") or "",
            name      = d.get("file_name") or d.get("name") or "",
            size      = d.get("size"),
            file_type = d.get("file_type"),
            category  = d.get("category"),
            pdir_fid  = d.get("pdir_fid"),
            path      = d.get("file_path") or d.get("full_path"),
            updated_at= d.get("updated_at"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ShareInfo:
    pwd_id:    str
    url:       str
    passcode:  str = ""
    stoken:    Optional[str] = None
    title:     Optional[str] = None
    files:     List[QuarkFile] = field(default_factory=list)
    err:       Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["files"] = [f.to_dict() if isinstance(f, QuarkFile) else f for f in self.files]
        return d


@dataclass
class DownloadResult:
    ok:        bool = False
    path:      Optional[str] = None
    bytes:     int = 0
    sha256:    Optional[str] = None
    elapsed_s: float = 0.0
    http_status: Optional[int] = None
    err:       Optional[str] = None
    skipped_cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ────────────────────────────────────────────────────────────────────────
# 分享链接解析 · 纯 stdlib
# ────────────────────────────────────────────────────────────────────────
_SHARE_PAT = re.compile(r"pan\.quark\.cn/s/([A-Za-z0-9_\-]+)")

def parse_share_url(url_or_id: str) -> str:
    """从任意形式的分享链接提取 pwd_id.

    支持:
        https://pan.quark.cn/s/abc123def456
        http://pan.quark.cn/s/abc123def456
        pan.quark.cn/s/abc123def456
        abc123def456                          (已是 pwd_id)
    """
    s = (url_or_id or "").strip()
    if not s:
        raise QuarkBridgeError("empty share url/id")
    m = _SHARE_PAT.search(s)
    if m:
        return m.group(1)
    # 无域 → 认为是纯 pwd_id (纯字母数字下划线横线)
    if re.fullmatch(r"[A-Za-z0-9_\-]{4,}", s):
        return s
    raise QuarkBridgeError(f"cannot parse share id from: {s!r}")


# 兼容旧名
share_url_to_pwd_id = parse_share_url


# ────────────────────────────────────────────────────────────────────────
# 核心桥
# ────────────────────────────────────────────────────────────────────────
class DaoQuarkBridge:
    """3D建模Agent 用的夸克网盘客户端桥.

    持有一个 `DaoHttpBridge` 实例 (来自兄弟项目 `夸克网盘/dao_http.py`),
    向外暴露贴合 3D 建模使用的 API 层 (QuarkFile/ShareInfo/DownloadResult).
    """

    def __init__(self, port: int = 19222):
        self.port = port
        self._http = None  # 延迟创建

    # ── 生命周期 ──────────────────────────────────────────────────
    def status(self) -> QuarkStatus:
        """三态诊断. 不抛异常."""
        st = QuarkStatus(
            quark_project_dir=str(QUARK_PROJECT) if QUARK_PROJECT else None,
        )

        # L0a · 夸克 App 进程
        try:
            import subprocess
            p = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq quark.exe", "/FO", "CSV", "/NH"],
                capture_output=True, encoding="mbcs", errors="replace", timeout=6,
            )
            lines = [l for l in (p.stdout or "").splitlines() if l.strip()]
            st.quark_app_count = sum(1 for l in lines if l.startswith('"quark.exe"'))
            st.quark_app_running = st.quark_app_count > 0
        except Exception:
            pass

        # L0b · CDP 可达?
        try:
            r = urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json/version", timeout=2.0)
            data = json.loads(r.read())
            st.cdp_up = True
        except Exception:
            st.cdp_up = False

        try:
            r = urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json", timeout=2.5)
            lst = json.loads(r.read())
            st.cdp_targets = len(lst) if isinstance(lst, list) else 0
        except Exception:
            pass

        # L0c · dao_http 可导入?
        try:
            import dao_http  # type: ignore
            st.dao_http_importable = True
            st.dao_http_version = getattr(dao_http, "__version__", None) or "n/a"
        except Exception as e:
            st.dao_http_importable = False
            st.advice.append(
                f"无法导入 夸克网盘/dao_http.py ({type(e).__name__}: {e}); "
                f"设置环境变量 DAO_QUARK_PROJECT 或把兄弟项目放到 ../夸克网盘/"
            )

        # L1 · 活 target?  (只在 CDP 起时才探)
        if st.cdp_up and st.dao_http_importable:
            try:
                self._ensure_http()
                if self._http is not None and self._http.connect(verbose=False, retries=1):
                    st.quark_target_alive = True
                    t = self._http.target or {}
                    st.ws_origin = t.get("origin")
                    st.ws_title  = t.get("title")
            except Exception as e:
                st.advice.append(f"connect_http: {type(e).__name__}: {e}")

        # 建议
        if not st.quark_app_running:
            st.advice.append("夸克客户端未运行 · 双击 夸克网盘/启动夸克CDP.cmd")
        elif not st.cdp_up:
            st.advice.append("CDP 端口 19222 未开 · 需以 --remote-debugging-port=19222 启动夸克")
        elif not st.quark_target_alive:
            st.advice.append("未找到已登录的 quark 渲染 target · 请先在夸克客户端扫码登录")
        return st

    def _ensure_http(self):
        """延迟引入 dao_http (避免无夸克环境时 import 失败)."""
        if self._http is not None:
            return
        try:
            from dao_http import DaoHttpBridge  # type: ignore
        except ImportError as e:
            raise QuarkBridgeError(
                f"cannot import dao_http: {e}; "
                f"set env DAO_QUARK_PROJECT or place 夸克网盘/ as sibling dir"
            ) from e
        self._http = DaoHttpBridge(port=self.port)

    def connect(self, verbose: bool = False, retries: int = 3) -> bool:
        """绑定一个活 quark 登录 target."""
        self._ensure_http()
        assert self._http is not None
        return self._http.connect(verbose=verbose, retries=retries)

    @property
    def http(self):
        """返回底层 DaoHttpBridge (若需直调 126 个 REST 方法)."""
        self._ensure_http()
        return self._http

    # ── 目录读 ────────────────────────────────────────────────────
    def ls(self, pdir_fid: str = "0", *,
           page: int = 1, size: int = 100) -> List[QuarkFile]:
        """列目录. pdir_fid='0' 为根."""
        self._ensure_http()
        assert self._http is not None
        r = self._http.file_sort(pdir_fid=pdir_fid, page=page, size=size)
        if not r.get("ok"):
            raise QuarkBridgeError(
                f"file_sort failed: code={r.get('code')} msg={r.get('message')}"
            )
        data = r.get("data") or {}
        # data may itself be the list, or {list: [...]}
        items = data.get("list") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        return [QuarkFile.from_api(d) for d in items if isinstance(d, dict)]

    def ls_path(self, slash_path: str) -> List[QuarkFile]:
        """按 '/夹A/夹B/...' 路径列目录 (忽略最末文件, 返其内容)."""
        fid = self.get_by_path(slash_path, is_dir=True)
        if fid is None:
            raise QuarkBridgeError(f"path not found: {slash_path}")
        return self.ls(fid)

    def get_by_path(self, slash_path: str, is_dir: Optional[bool] = None) -> Optional[str]:
        """路径 → fid. is_dir=True 要求末节是目录; None 不限.

        '/'  or '' → '0' (根)
        """
        p = (slash_path or "").strip()
        if p in ("", "/"):
            return "0"
        parts = [x for x in p.replace("\\", "/").split("/") if x]
        cur = "0"
        for i, part in enumerate(parts):
            items = self.ls(cur, size=500)
            hit = next((f for f in items if f.name == part), None)
            if hit is None:
                # 试全局 search 做宽容匹配 (路径末端允许)
                return None
            if i < len(parts) - 1 and not hit.is_dir:
                return None  # 中间节点必须是目录
            cur = hit.fid
        if is_dir is not None:
            # 最后再 ls 一下判目录
            try:
                _ = self.ls(cur, size=1)
                actual_is_dir = True
            except Exception:
                actual_is_dir = False
            if is_dir and not actual_is_dir:
                return None
        return cur

    def find(self, substr: str, *,
             limit: int = 50, category: Optional[str] = None) -> List[QuarkFile]:
        """全局搜索 (云端)."""
        self._ensure_http()
        assert self._http is not None
        r = self._http.file_search(substr, size=limit)
        if not r.get("ok"):
            raise QuarkBridgeError(
                f"file_search failed: code={r.get('code')} msg={r.get('message')}"
            )
        data = r.get("data") or {}
        items = data.get("list") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        out = [QuarkFile.from_api(d) for d in items if isinstance(d, dict)]
        if category:
            # category is a human name; require user-side filtering
            out = [f for f in out if f.category is not None]
        return out[:limit]

    def info(self, fid: str) -> QuarkFile:
        self._ensure_http()
        assert self._http is not None
        r = self._http.file_info(fid)
        if not r.get("ok"):
            raise QuarkBridgeError(f"file_info: {r.get('message')}")
        d = (r.get("data") or {})
        # data: {file: {...}} or direct
        f = d.get("file") if isinstance(d, dict) else None
        return QuarkFile.from_api(f if isinstance(f, dict) else d)

    def path_of(self, fid: str) -> Optional[str]:
        """反查 fid 的完整路径. 返回 '/a/b/c.ext' 或 None."""
        self._ensure_http()
        assert self._http is not None
        r = self._http.file_path_list(fid)
        if not r.get("ok"): return None
        data = r.get("data") or {}
        lst = data.get("list") if isinstance(data, dict) else data
        if not isinstance(lst, list):
            return None
        names = [x.get("file_name") or x.get("name")
                 for x in lst if isinstance(x, dict)]
        names = [n for n in names if n]
        return "/" + "/".join(names) if names else None

    # ── 下载 URL + 流式 download ───────────────────────────────────
    def get_url(self, fid: str) -> Dict[str, Any]:
        """取单文件的签名下载 URL (及同文件元数据).

        返回 shape: {
            "download_url": "https://...aliyuncs.com/...",
            "file_name":    "...",
            "size":         12345,
            ... (原生 quark 字段)
        }
        """
        self._ensure_http()
        assert self._http is not None
        r = self._http.file_download([fid])
        if not r.get("ok"):
            raise QuarkBridgeError(
                f"file_download(get_url): code={r.get('code')} msg={r.get('message')}"
            )
        data = r.get("data")
        # data: list[{download_url, file_name, size, ...}] or dict
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            lst = data.get("list") or data.get("files") or []
            if isinstance(lst, list) and lst:
                return lst[0]
            if "download_url" in data:
                return data
        raise QuarkBridgeError(f"unexpected file_download shape: {type(data)}")

    def _extract_cdp_cookies(self) -> Dict[str, str]:
        """从 CDP 活 target 里读 document.cookie (内存瞬时, 不落盘).

        这一步是必要的: aliyuncs 签名 URL 可能附加了 host-only cookie 校验
        (e.g. __puus, x-region). 绝大多数情形下其实不需, 但保留做兜底.
        """
        try:
            from dao_http import cdp_once  # type: ignore
        except Exception:
            return {}
        self._ensure_http()
        assert self._http is not None
        ws = self._http.ws_url
        if not ws: return {}
        r = cdp_once(ws, "document.cookie", timeout=2.5)
        if not r.get("ok"): return {}
        raw = r.get("result") or ""
        out: Dict[str, str] = {}
        for seg in str(raw).split(";"):
            seg = seg.strip()
            if "=" in seg:
                k, _, v = seg.partition("=")
                k = k.strip(); v = v.strip()
                if k and v:
                    out[k] = v
        return out

    def download(self, fid: str, dst: Union[str, Path], *,
                 expected_size: Optional[int] = None,
                 expected_sha256: Optional[str] = None,
                 chunk: int = 1024 * 1024,
                 progress: Optional[Callable[[int, Optional[int]], None]] = None,
                 max_retries: int = 3,
                 resume: bool = True,
                 timeout: float = 60.0,
                 ) -> DownloadResult:
        """流式下载单文件到 `dst`. 返回 DownloadResult.

        幂等: dst 已存在且大小 (+SHA 若给) 匹配, 直接返回 skipped_cached=True.
        断点续传: resume=True 则用 Range 请求补剩余字节.
        """
        dst = Path(dst)
        t0 = time.time()
        res = DownloadResult(path=str(dst))

        meta = self.get_url(fid)
        url = meta.get("download_url")
        if not url:
            res.err = "no download_url in response"
            return res

        server_size = meta.get("size")
        if server_size is None: server_size = expected_size
        file_name = meta.get("file_name") or meta.get("name") or dst.name

        dst.parent.mkdir(parents=True, exist_ok=True)

        # 幂等短路
        if dst.is_file():
            size_ok = (server_size is None or dst.stat().st_size == int(server_size))
            if size_ok:
                if expected_sha256:
                    got = _sha256_file(dst)
                    if got.lower() == expected_sha256.lower():
                        res.ok = True
                        res.bytes = dst.stat().st_size
                        res.sha256 = got
                        res.skipped_cached = True
                        res.elapsed_s = time.time() - t0
                        _stamp("OK", f"cached (sha matched) {file_name} {_human_size(res.bytes)}")
                        return res
                else:
                    res.ok = True
                    res.bytes = dst.stat().st_size
                    res.skipped_cached = True
                    res.elapsed_s = time.time() - t0
                    _stamp("OK", f"cached (size matched) {file_name} {_human_size(res.bytes)}")
                    return res

        # Cookie 头 (尽量空, 需要再补)
        cookie_hdr: Optional[str] = None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/"
                          "537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 quark-cloud-drive/3.14.6",
            "Referer":   "https://pan.quark.cn/",
            "Origin":    "https://pan.quark.cn",
            "Accept":    "*/*",
        }

        attempt = 0
        tmp = dst.with_suffix(dst.suffix + ".partial")
        while attempt <= max_retries:
            try:
                start_offset = 0
                mode = "wb"
                if resume and tmp.is_file() and tmp.stat().st_size > 0:
                    start_offset = tmp.stat().st_size
                    mode = "ab"
                    headers_once = dict(headers)
                    headers_once["Range"] = f"bytes={start_offset}-"
                    if cookie_hdr:
                        headers_once["Cookie"] = cookie_hdr
                    req = urllib.request.Request(url, headers=headers_once)
                else:
                    if cookie_hdr:
                        headers["Cookie"] = cookie_hdr
                    req = urllib.request.Request(url, headers=headers)

                _stamp("DL",
                       f"{file_name} ← fid={fid[:8]}... (size≈{_human_size(server_size)}"
                       f"{f', resume from {_human_size(start_offset)}' if start_offset else ''})")

                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    res.http_status = resp.status if hasattr(resp, "status") else resp.getcode()
                    # Content-Length or total from Content-Range
                    total = server_size
                    cl = resp.headers.get("Content-Length")
                    if cl is not None and total is None:
                        try: total = int(cl) + start_offset
                        except Exception: pass

                    got = start_offset
                    last_report = time.time()
                    with open(tmp, mode) as f:
                        while True:
                            buf = resp.read(chunk)
                            if not buf:
                                break
                            f.write(buf)
                            got += len(buf)
                            if progress is not None:
                                try: progress(got, total)
                                except Exception: pass
                            if time.time() - last_report > 2.0:
                                pct = (got / total * 100) if total else 0
                                rate = got / max(time.time() - t0, 0.001) / 1e6
                                _stamp("DL",
                                       f"  {_human_size(got)}/{_human_size(total)} "
                                       f"({pct:.1f}%)  {rate:.2f} MB/s")
                                last_report = time.time()

                # 完成
                final_bytes = tmp.stat().st_size
                if server_size is not None and final_bytes != int(server_size):
                    # 部分/ range 失败 — 重试
                    raise IOError(
                        f"incomplete: got {final_bytes} / {server_size} bytes"
                    )
                tmp.replace(dst)
                res.bytes = dst.stat().st_size
                if expected_sha256:
                    got_sha = _sha256_file(dst)
                    res.sha256 = got_sha
                    if got_sha.lower() != expected_sha256.lower():
                        raise IOError(f"sha256 mismatch: got {got_sha}, "
                                      f"expected {expected_sha256}")
                else:
                    # 仍算一个 (加速后续幂等)
                    try: res.sha256 = _sha256_file(dst)
                    except Exception: pass
                res.ok = True
                res.elapsed_s = time.time() - t0
                _stamp("OK", f"saved {dst} · {_human_size(res.bytes)} "
                              f"in {res.elapsed_s:.1f}s")
                return res

            except urllib.error.HTTPError as e:
                # 401/403: 可能需要 Cookie
                if e.code in (401, 403) and cookie_hdr is None:
                    try:
                        cks = self._extract_cdp_cookies()
                        if cks:
                            cookie_hdr = "; ".join(f"{k}={v}" for k, v in cks.items())
                            _stamp("WARN",
                                   f"HTTP {e.code} · 注入 {len(cks)} 个 CDP cookie 重试")
                            attempt += 1
                            continue
                    except Exception:
                        pass
                res.err = f"HTTP {e.code}: {e.reason}"
                _stamp("ERR", res.err)
                # 4xx 不重试
                if 400 <= e.code < 500:
                    return res
                attempt += 1
            except Exception as e:  # socket / transient
                res.err = f"{type(e).__name__}: {e}"
                _stamp("WARN", f"retry {attempt + 1}/{max_retries}: {res.err}")
                attempt += 1
                time.sleep(min(2 ** attempt, 8))

        res.elapsed_s = time.time() - t0
        return res

    # ── pull (find-then-download 组合) ─────────────────────────────
    def pull(self, name_or_path: str, dst: Union[str, Path],
             **download_kwargs) -> DownloadResult:
        """按 name/path 找到 fid 再下载. dst 若为目录则用原名."""
        dst = Path(dst)
        fid: Optional[str] = None
        name: Optional[str] = None
        # 1) 路径
        if name_or_path.startswith("/"):
            fid = self.get_by_path(name_or_path)
            if not fid or fid == "0":
                raise QuarkBridgeError(f"path not found / root not downloadable: {name_or_path}")
            try: name = Path(name_or_path).name
            except Exception: pass
        else:
            hits = self.find(name_or_path, limit=20)
            # 精确匹配优先
            exact = [h for h in hits if h.name == name_or_path]
            pool = exact or hits
            # 只要文件 (file_type=1)
            files_only = [h for h in pool if not h.is_dir]
            if files_only:
                pool = files_only
            if not pool:
                raise QuarkBridgeError(f"no match for query: {name_or_path}")
            if len(pool) > 1 and not exact:
                _stamp("WARN",
                       f"多条匹配, 默认用首条 · 其余 {len(pool) - 1}: "
                       f"{[h.name for h in pool[1:4]]}")
            hit = pool[0]
            fid = hit.fid
            name = hit.name

        if dst.is_dir() or (not dst.exists() and dst.name == "" ) \
                or (not dst.exists() and name and not dst.suffix):
            dst = dst / (name or "downloaded.bin")
        return self.download(fid, dst, **download_kwargs)

    def pull_folder(self, folder: Union[str, 'QuarkFile'],
                    dst_dir: Union[str, Path], *,
                    include: Optional[Union[str, re.Pattern]] = None,
                    exclude: Optional[Union[str, re.Pattern]] = None,
                    recursive: bool = True,
                    max_files: int = 10000,
                    progress: Optional[Callable[[int, Optional[int]], None]] = None,
                    **download_kwargs) -> Dict[str, Any]:
        """递归下载一个目录. folder 可是 fid/path/QuarkFile."""
        # 解析 folder → fid
        if isinstance(folder, QuarkFile):
            fid = folder.fid
            root_name = folder.name
        elif isinstance(folder, str) and folder.startswith("/"):
            fid = self.get_by_path(folder, is_dir=True)
            if not fid:
                raise QuarkBridgeError(f"folder path not found: {folder}")
            root_name = folder.rstrip("/").split("/")[-1] or ""
        else:
            fid = str(folder)
            root_name = ""

        inc = re.compile(include) if isinstance(include, str) else include
        exc = re.compile(exclude) if isinstance(exclude, str) else exclude

        dst_dir = Path(dst_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)

        results: List[DownloadResult] = []
        skipped: List[str] = []
        errors:  List[Tuple[str, str]] = []

        def _recur(cur_fid: str, cur_local: Path):
            if len(results) >= max_files:
                return
            page = 1
            while True:
                items = self.ls(cur_fid, page=page, size=200)
                if not items: break
                for f in items:
                    if len(results) >= max_files: return
                    if f.is_dir:
                        if recursive:
                            sub = cur_local / _safe_filename(f.name)
                            sub.mkdir(parents=True, exist_ok=True)
                            _recur(f.fid, sub)
                        continue
                    # 文件: 过滤
                    if inc and not inc.search(f.name):
                        skipped.append(f.name); continue
                    if exc and exc.search(f.name):
                        skipped.append(f.name); continue
                    local = cur_local / _safe_filename(f.name)
                    try:
                        r = self.download(f.fid, local,
                                          expected_size=f.size,
                                          progress=progress,
                                          **download_kwargs)
                        results.append(r)
                        if not r.ok:
                            errors.append((f.name, r.err or "unknown"))
                    except Exception as e:
                        errors.append((f.name, f"{type(e).__name__}: {e}"))
                if len(items) < 200:
                    break
                page += 1

        top_local = dst_dir / _safe_filename(root_name) if root_name else dst_dir
        top_local.mkdir(parents=True, exist_ok=True)
        _recur(fid, top_local)

        total_bytes = sum(r.bytes for r in results if r.ok)
        return {
            "ok":          all(r.ok for r in results) and not errors,
            "dst_dir":     str(top_local),
            "n_files":     len(results),
            "n_ok":        sum(1 for r in results if r.ok),
            "n_skipped":   len(skipped),
            "n_errors":    len(errors),
            "total_bytes": total_bytes,
            "errors":      errors,
            "results":     [r.to_dict() for r in results],
        }

    # ── 分享 ──────────────────────────────────────────────────────
    def share_resolve(self, url_or_id: str, passcode: str = "") -> ShareInfo:
        """解析分享链接: pwd_id → stoken → files.

        若 passcode 错或过期, 返回 info.err, files 为空.
        """
        self._ensure_http()
        assert self._http is not None
        pwd_id = parse_share_url(url_or_id)
        info = ShareInfo(pwd_id=pwd_id, url=url_or_id, passcode=passcode)

        # 1) token
        r = self._http.share_sharepage_token(pwd_id, passcode)
        if not r.get("ok"):
            info.err = f"sharepage_token: code={r.get('code')} msg={r.get('message')}"
            return info
        data = r.get("data") or {}
        info.stoken = data.get("stoken") if isinstance(data, dict) else None
        info.title  = data.get("title") if isinstance(data, dict) else None

        # 2) detail
        r = self._http.share_sharepage_detail(pwd_id, info.stoken or "")
        if not r.get("ok"):
            info.err = f"sharepage_detail: code={r.get('code')} msg={r.get('message')}"
            return info
        data = r.get("data") or {}
        items = data.get("list") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return info
        info.files = [QuarkFile.from_api(d) for d in items if isinstance(d, dict)]
        return info

    def share_pull(self, url_or_id: str, passcode: str,
                   dst_dir: Union[str, Path], *,
                   include: Optional[Union[str, re.Pattern]] = None,
                   save_first: bool = True,
                   save_to_pdir_fid: str = "0",
                   **download_kwargs) -> Dict[str, Any]:
        """分享链接 → 本机.

        save_first=True 时, 先把分享条目转存到自己的 drive (根), 再用 file_download 拉链接.
        save_first=False 走共享页直读 (部分文件不支持)
        """
        self._ensure_http()
        assert self._http is not None
        info = self.share_resolve(url_or_id, passcode)
        if info.err or not info.files:
            raise QuarkBridgeError(
                f"share_resolve failed: {info.err or 'no files'}"
            )
        _stamp("Q", f"解析分享 pwd_id={info.pwd_id[:10]}... 得 {len(info.files)} 项")

        inc = re.compile(include) if isinstance(include, str) else include
        pick = [f for f in info.files if (not inc or inc.search(f.name))]
        if not pick:
            raise QuarkBridgeError("no files matched include filter")

        dst_dir = Path(dst_dir); dst_dir.mkdir(parents=True, exist_ok=True)

        if save_first:
            # 转存到自己 drive · 再下载
            fids = [f.fid for f in pick]
            r = self._http.share_sharepage_save(
                info.pwd_id, info.stoken or "", fids, save_to_pdir_fid
            )
            if not r.get("ok"):
                raise QuarkBridgeError(
                    f"sharepage_save failed: code={r.get('code')} msg={r.get('message')}"
                )
            _stamp("Q", f"已转存 {len(fids)} 项到自己 drive (pdir={save_to_pdir_fid})")
            # 转存成功后, 文件可能在根下, 用 find 按名回找新 fid
            # 等待 quark 服务端索引
            time.sleep(2.0)
            resolved: List[QuarkFile] = []
            for f in pick:
                hits = self.find(f.name, limit=5)
                match = next((h for h in hits if h.name == f.name and not h.is_dir), None)
                if match: resolved.append(match)
                elif hits: resolved.append(hits[0])
            pick = resolved or pick

        # 下载
        results: List[DownloadResult] = []
        for f in pick:
            if f.is_dir:
                # 文件夹: 走 pull_folder
                sub = self.pull_folder(f, dst_dir,
                                       include=include, **download_kwargs)
                results.append(DownloadResult(
                    ok=sub["ok"], path=sub["dst_dir"],
                    bytes=sub["total_bytes"], skipped_cached=False,
                ))
                continue
            try:
                r = self.download(f.fid, dst_dir / _safe_filename(f.name),
                                  expected_size=f.size, **download_kwargs)
                results.append(r)
            except Exception as e:
                results.append(DownloadResult(ok=False,
                                              path=str(dst_dir / f.name),
                                              err=f"{type(e).__name__}: {e}"))

        return {
            "ok":        all(r.ok for r in results),
            "share":     info.to_dict(),
            "n_files":   len(results),
            "n_ok":      sum(1 for r in results if r.ok),
            "results":   [r.to_dict() for r in results],
            "dst_dir":   str(dst_dir),
        }

    # ── SolidWorks 快捷路径 ───────────────────────────────────────
    def sw_installer_locate(self) -> Dict[str, Any]:
        """在夸克 drive 中定位 SolidWorks 相关资源.

        先按 "SolidWorks" 关键字搜索, 然后按扩展名归类:
          · exe / setup  → 安装包
          · iso          → 光盘镜像
          · docx / pdf   → 许可激活指南
          · zip / rar    → 压缩包
        """
        hits = self.find("SolidWorks", limit=200)
        out = {
            "n_hits":     len(hits),
            "folders":    [],
            "installers": [],
            "isos":       [],
            "archives":   [],
            "docs":       [],
            "others":     [],
        }
        for h in hits:
            d = h.to_dict()
            if h.is_dir:
                out["folders"].append(d); continue
            ext = Path(h.name).suffix.lower()
            if ext in (".exe", ".msi"):        out["installers"].append(d)
            elif ext == ".iso":                 out["isos"].append(d)
            elif ext in (".zip", ".rar", ".7z"): out["archives"].append(d)
            elif ext in (".docx", ".doc", ".pdf", ".txt", ".md"):
                                                out["docs"].append(d)
            else:                               out["others"].append(d)
        # 也扫分享-下文件夹
        try:
            root = self.ls("0", size=500)
            root_folders = [f.to_dict() for f in root
                            if f.is_dir and "solidworks" in f.name.lower()]
            out["root_folders"] = root_folders
        except Exception:
            pass
        return out

    def sw_installer_pull(self, dst_dir: Union[str, Path],
                          what: str = "installer",
                          **download_kwargs) -> Dict[str, Any]:
        """一键拉取 SolidWorks 资源.

        what:
            installer  → 安装包 (exe/msi/iso)
            license    → 许可激活相关 (docx/pdf/zip)
            docx       → 仅文档
            all        → 全部 (慎用, 可能数 GB)
        """
        loc = self.sw_installer_locate()
        dst_dir = Path(dst_dir); dst_dir.mkdir(parents=True, exist_ok=True)

        picks: List[Dict[str, Any]] = []
        if what in ("installer", "all"):
            picks += loc["installers"] + loc["isos"] + loc["archives"]
        if what in ("license", "all"):
            picks += [d for d in loc["docs"]
                      if any(k in d["name"] for k in ("续", "激活", "license", "crack", "授权"))]
        if what in ("docx", "all"):
            picks += loc["docs"]
        # 若仅有 folders 且 what=='all', 则下整个文件夹
        if what == "all" and not picks and loc["root_folders"]:
            picks = loc["root_folders"]

        # 去重
        seen: set = set()
        picks = [p for p in picks if not (p["fid"] in seen or seen.add(p["fid"]))]

        if not picks:
            return {"ok": False, "n_picked": 0, "advice":
                    "未匹配到 SolidWorks 相关文件; 请先转存分享链接到自己的 drive"}

        _stamp("Q", f"将下载 {len(picks)} 项 SolidWorks {what}")

        results = []
        for p in picks:
            name = p["name"]; fid = p["fid"]
            file_type = p.get("file_type")
            local = dst_dir / _safe_filename(name)
            try:
                if file_type == 0:
                    sub = self.pull_folder(fid, dst_dir, **download_kwargs)
                    results.append({"name": name, "kind": "folder", **{
                        k: v for k, v in sub.items() if k != "results"
                    }})
                else:
                    r = self.download(fid, local,
                                      expected_size=p.get("size"),
                                      **download_kwargs)
                    results.append({"name": name, "kind": "file", **r.to_dict()})
            except Exception as e:
                results.append({"name": name, "ok": False,
                                "err": f"{type(e).__name__}: {e}"})

        ok_count = sum(1 for r in results if r.get("ok"))
        return {
            "ok":        ok_count > 0,
            "what":      what,
            "n_picked":  len(picks),
            "n_ok":      ok_count,
            "dst_dir":   str(dst_dir),
            "results":   results,
        }


# ────────────────────────────────────────────────────────────────────────
# 工具
# ────────────────────────────────────────────────────────────────────────
_INVALID_FILE_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')

def _safe_filename(name: str) -> str:
    """Windows 安全文件名: 清除控制字符与 <>:"|?*."""
    if not name: return "unnamed"
    s = _INVALID_FILE_CHARS.sub("_", name).strip(" .")
    return s or "unnamed"


def _sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(chunk), b""):
            h.update(buf)
    return h.hexdigest()


# ────────────────────────────────────────────────────────────────────────
# 自测
# ────────────────────────────────────────────────────────────────────────
def _self_test() -> Dict[str, Any]:
    """桥自测 (不强连 CDP · 可离线跑).

    覆盖:
        T1   parse_share_url 四种形式
        T2   _safe_filename Windows 兼容
        T3   _human_size 格式
        T4   DaoQuarkBridge 可实例化
        T5   status() 不抛 (即便无 CDP)
        T6   QuarkFile.from_api / to_dict 往返
        T7   QUARK_PROJECT 探测到有效路径
        T8   dao_http 可 import (若 QUARK_PROJECT 有效)
    """
    res: Dict[str, Any] = {"pass": [], "fail": [], "score": 0, "total": 0}

    # T1 parse_share_url
    try:
        assert parse_share_url("https://pan.quark.cn/s/296776c49460") == "296776c49460"
        assert parse_share_url("http://pan.quark.cn/s/abc123_def") == "abc123_def"
        assert parse_share_url("pan.quark.cn/s/xy-zw") == "xy-zw"
        assert parse_share_url("296776c49460") == "296776c49460"
        try:
            parse_share_url("")
            assert False, "empty should raise"
        except QuarkBridgeError: pass
        res["pass"].append("T1_parse_share_url"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T1_parse_share_url", repr(e)))
    res["total"] += 1

    # T2 _safe_filename
    try:
        assert _safe_filename("a<b>c:d\"e|f?g*h") == "a_b_c_d_e_f_g_h"
        assert _safe_filename("") == "unnamed"
        assert _safe_filename("normal.exe") == "normal.exe"
        res["pass"].append("T2_safe_filename"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T2_safe_filename", repr(e)))
    res["total"] += 1

    # T3 _human_size
    try:
        assert "B" in _human_size(500)
        assert "KB" in _human_size(5000)
        assert "MB" in _human_size(5_000_000)
        assert _human_size(None) == "?"
        res["pass"].append("T3_human_size"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T3_human_size", repr(e)))
    res["total"] += 1

    # T4 bridge init
    try:
        br = DaoQuarkBridge()
        assert br.port == 19222
        assert br._http is None
        res["pass"].append("T4_bridge_init"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T4_bridge_init", repr(e)))
    res["total"] += 1

    # T5 status 不抛
    try:
        br = DaoQuarkBridge()
        st = br.status()
        assert isinstance(st, QuarkStatus)
        d = st.to_dict()
        assert "cdp_up" in d and "quark_app_running" in d
        res["pass"].append("T5_status"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T5_status", repr(e)))
    res["total"] += 1

    # T6 QuarkFile roundtrip
    try:
        api_data = {"fid": "abc", "file_name": "x.sldprt",
                    "size": 12345, "file_type": 1}
        qf = QuarkFile.from_api(api_data)
        d = qf.to_dict()
        assert d["fid"] == "abc"
        assert d["name"] == "x.sldprt"
        assert d["size"] == 12345
        assert not qf.is_dir
        # dir case
        df = QuarkFile.from_api({"fid": "D", "file_name": "dir", "file_type": 0})
        assert df.is_dir
        res["pass"].append("T6_quarkfile"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T6_quarkfile", repr(e)))
    res["total"] += 1

    # T7 QUARK_PROJECT
    try:
        qp = QUARK_PROJECT
        assert qp is not None, "QUARK_PROJECT not auto-detected"
        assert (qp / "dao_http.py").is_file()
        res["pass"].append("T7_quark_project"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T7_quark_project", repr(e)))
    res["total"] += 1

    # T8 dao_http importable
    try:
        import dao_http  # type: ignore
        assert hasattr(dao_http, "DaoHttpBridge")
        assert hasattr(dao_http, "cdp_once")
        res["pass"].append("T8_import_dao_http"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T8_import_dao_http", repr(e)))
    res["total"] += 1

    res["ratio"] = f"{res['score']}/{res['total']}"
    res["pct"]   = round(100.0 * res["score"] / max(res["total"], 1), 1)
    return res


# ────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────
def _pp(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _progress_bar(got: int, total: Optional[int]):
    if not total:
        sys.stdout.write(f"\r  {_human_size(got)}"); sys.stdout.flush()
        return
    pct = got / total * 100
    bar_w = 30
    filled = int(bar_w * got / total)
    bar = "█" * filled + "░" * (bar_w - filled)
    sys.stdout.write(
        f"\r  [{bar}] {pct:5.1f}% {_human_size(got)}/{_human_size(total)}"
    )
    sys.stdout.flush()


def _default_sw_dst() -> Path:
    """默认 SW 下载目标: 3D建模Agent/70-天下_World/sw/"""
    if _dao_paths is not None:
        return _dao_paths.WORLD / "sw"  # type: ignore[attr-defined]
    return _HERE.parent / "70-天下_World" / "sw"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="dao_quark_bridge · 3D建模Agent × 夸克网盘 · 道法自然桥"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="三态诊断")
    sub.add_parser("test", help="自测 (无需 CDP)")

    p_ls = sub.add_parser("ls", help="列目录")
    p_ls.add_argument("pdir_fid", nargs="?", default="0")
    p_ls.add_argument("--size", type=int, default=100)

    p_lsp = sub.add_parser("ls-path", help="按路径列目录")
    p_lsp.add_argument("path")

    p_find = sub.add_parser("find", help="全局搜索")
    p_find.add_argument("q")
    p_find.add_argument("--limit", type=int, default=50)

    p_info = sub.add_parser("info", help="文件 fid 详情")
    p_info.add_argument("fid")

    p_url = sub.add_parser("url", help="取下载 URL")
    p_url.add_argument("fid")

    p_get = sub.add_parser("get", help="下载 fid 到本地")
    p_get.add_argument("fid")
    p_get.add_argument("dst", nargs="?", default=".")
    p_get.add_argument("--sha256", default=None)
    p_get.add_argument("--no-resume", action="store_true")

    p_pull = sub.add_parser("pull", help="按名/路径下载")
    p_pull.add_argument("name_or_path")
    p_pull.add_argument("dst", nargs="?", default=".")

    p_pullf = sub.add_parser("pull-folder", help="递归下整个文件夹")
    p_pullf.add_argument("fid_or_path")
    p_pullf.add_argument("dst_dir")
    p_pullf.add_argument("--include", default=None, help="文件名正则过滤")
    p_pullf.add_argument("--exclude", default=None)
    p_pullf.add_argument("--max", type=int, default=1000)

    p_share = sub.add_parser("share", help="解析分享链接")
    p_share.add_argument("url")
    p_share.add_argument("--passcode", default="")

    p_share_pull = sub.add_parser("share-pull", help="分享链接 → 本机")
    p_share_pull.add_argument("url")
    p_share_pull.add_argument("--passcode", default="")
    p_share_pull.add_argument("--dst", default=None)
    p_share_pull.add_argument("--include", default=None)
    p_share_pull.add_argument("--no-save-first", action="store_true",
                              help="跳过转存自己 drive 的步骤, 直接走分享页下载")

    sub.add_parser("sw-locate", help="在夸克 drive 定位 SolidWorks 资源")

    p_swp = sub.add_parser("sw-pull",
                           help="拉取 SolidWorks 资源到 70-天下_World/sw/")
    p_swp.add_argument("--dst", default=None)
    p_swp.add_argument("--what", choices=("installer", "license", "docx", "all"),
                       default="installer")

    a = ap.parse_args(argv)

    # 无需连接的命令
    if a.cmd == "test":
        r = _self_test()
        print("\n" + "=" * 56)
        print(f"  dao_quark_bridge 自测: {r['ratio']}  ({r['pct']}%)")
        print("=" * 56)
        for p in r["pass"]: print(f"  ✓ {p}")
        for n, e in r["fail"]: print(f"  ✗ {n}: {e}")
        return 0 if not r["fail"] else 1

    br = DaoQuarkBridge()
    if a.cmd == "status":
        st = br.status()
        _pp(st.to_dict())
        return 0 if st.cdp_up and st.quark_target_alive else 2

    # 以下命令需要 CDP 活 target
    if not br.connect(verbose=True):
        st = br.status()
        _stamp("ERR", "CDP/夸克 target 连接失败")
        for hint in st.advice:
            _stamp("WARN", hint)
        return 3

    try:
        if a.cmd == "ls":
            items = br.ls(a.pdir_fid, size=a.size)
            _pp([f.to_dict() for f in items]); return 0

        if a.cmd == "ls-path":
            items = br.ls_path(a.path)
            _pp([f.to_dict() for f in items]); return 0

        if a.cmd == "find":
            items = br.find(a.q, limit=a.limit)
            _pp([f.to_dict() for f in items]); return 0

        if a.cmd == "info":
            _pp(br.info(a.fid).to_dict()); return 0

        if a.cmd == "url":
            meta = br.get_url(a.fid)
            _pp(meta); return 0

        if a.cmd == "get":
            dst = Path(a.dst)
            if dst.is_dir() or a.dst.endswith(("/", "\\")):
                meta = br.get_url(a.fid)
                dst = dst / _safe_filename(
                    meta.get("file_name") or "downloaded.bin"
                )
            r = br.download(a.fid, dst,
                            expected_sha256=a.sha256,
                            resume=not a.no_resume,
                            progress=_progress_bar)
            print()
            _pp(r.to_dict())
            return 0 if r.ok else 4

        if a.cmd == "pull":
            r = br.pull(a.name_or_path, a.dst, progress=_progress_bar)
            print()
            _pp(r.to_dict())
            return 0 if r.ok else 4

        if a.cmd == "pull-folder":
            r = br.pull_folder(a.fid_or_path, a.dst_dir,
                               include=a.include, exclude=a.exclude,
                               max_files=a.max,
                               progress=_progress_bar)
            print()
            _pp({k: v for k, v in r.items() if k != "results"})
            return 0 if r["ok"] else 4

        if a.cmd == "share":
            info = br.share_resolve(a.url, a.passcode)
            _pp(info.to_dict())
            return 0 if not info.err else 5

        if a.cmd == "share-pull":
            dst = Path(a.dst) if a.dst else _default_sw_dst() / "from_share"
            r = br.share_pull(a.url, a.passcode, dst,
                              include=a.include,
                              save_first=not a.no_save_first,
                              progress=_progress_bar)
            print()
            _pp({k: v for k, v in r.items() if k != "results"})
            return 0 if r["ok"] else 5

        if a.cmd == "sw-locate":
            loc = br.sw_installer_locate()
            _pp(loc); return 0

        if a.cmd == "sw-pull":
            dst = Path(a.dst) if a.dst else _default_sw_dst()
            r = br.sw_installer_pull(dst, what=a.what, progress=_progress_bar)
            print()
            _pp({k: v for k, v in r.items() if k != "results"})
            return 0 if r["ok"] else 4

    except QuarkBridgeError as e:
        _stamp("ERR", str(e)); return 6
    except KeyboardInterrupt:
        _stamp("WARN", "用户中断"); return 130
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
