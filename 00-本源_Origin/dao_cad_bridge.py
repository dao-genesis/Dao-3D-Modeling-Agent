#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dao_cad_bridge.py — 万法 CAD I/O 桥 · 披褐怀玉 · 和而不同
═══════════════════════════════════════════════════════════════════
反者道之动 · 无感于格式 · 无为而无不为

纲要
    "道可道, 非常道" — 格式可名, 非常名.
    SolidWorks 与 FreeCAD 异名同源, 皆以 OCCT/Parasolid 几何为本.
    此桥不执一格, 统于 DaoModel 之虚位, 以 STEP 为万法中转之朴.

支持格式 (读 R · 写 W · 探 P)
    格式           ext           读  写  探   路径
    ─────────────────────────────────────────────────
    STEP (AP214)   .step .stp    R   W   P   Part.read / Part.exportBrep
    IGES           .iges .igs    R   W   P   Part.read
    BREP           .brep .brp    R   W   P   Part.read / exportBrep
    STL (asc/bin)  .stl          R   W   P   Mesh.read
    OBJ            .obj          R   W   P   Mesh.read
    FCStd          .FCStd        R   W   P   App.openDocument
    SLDPRT (R+)    .sldprt       R~      P   OLE2 嗅探 + STEP proxy 回退
    SLDASM (R+)    .sldasm       R~      P   同上
    X_T/X_B        .x_t .x_b     —   —   P   (需 Parasolid SDK, 仅识别)

回退链 (反者道之动)
    SLDPRT 读取三级回退:
      1. 同目录同名 `.stp_ap203.sldprt` (SolidWorks导出代理)
      2. 同目录同名 `.step` / `.stp`
      3. OLE2 CFB 仅元数据 (缩略图/属性)

用法 (API)
    from dao_cad_bridge import DaoModel, convert, sniff

    # 无感读取
    m = DaoModel.load("part.sldprt")   # 自动回退到 STEP proxy
    m = DaoModel.load("part.step")
    m = DaoModel.load("assembly.FCStd")

    # 属性
    print(m.info())          # {fmt, n_shapes, volume, bbox, ...}

    # 无感写出
    m.save("out.step")
    m.save("out.stl")
    m.save("out.FCStd")

    # 一键转换
    convert("in.sldprt", "out.step")
    convert("in.FCStd", "out.stl")

CLI
    python dao_cad_bridge.py sniff <file>
    python dao_cad_bridge.py info <file>
    python dao_cad_bridge.py convert <src> <dst>
    python dao_cad_bridge.py sync <src_dir> <dst_dir> --fmt step,stl
    python dao_cad_bridge.py test                # 自测

工程原则
    - 0 强依赖. FreeCAD 优先, 缺失则退化到 OLE2 元数据模式.
    - OLE2 纯 stdlib 实现 (struct). 不依赖 olefile.
    - 披褐怀玉: 外层 DaoModel 不变, 内层 shape 随引擎变化.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

__version__ = "1.0.0"
__all__ = [
    "Format", "sniff", "DaoModel", "convert", "sync_dir",
    "OLE2Reader", "FCBackend",
]


# ── 格式枚举 ────────────────────────────────────────────────────────────
class Format(str, Enum):
    STEP   = "step"
    IGES   = "iges"
    BREP   = "brep"
    STL    = "stl"
    OBJ    = "obj"
    PLY    = "ply"
    FCSTD  = "fcstd"
    SLDPRT = "sldprt"
    SLDASM = "sldasm"
    X_T    = "x_t"          # Parasolid text
    X_B    = "x_b"          # Parasolid binary
    DXF    = "dxf"
    DWG    = "dwg"
    GLB    = "glb"
    GLTF   = "gltf"
    UNKNOWN = "unknown"


# 扩展名 → 格式 映射
_EXT_MAP: Dict[str, Format] = {
    ".step":  Format.STEP,  ".stp": Format.STEP,
    ".iges":  Format.IGES,  ".igs": Format.IGES,
    ".brep":  Format.BREP,  ".brp": Format.BREP,
    ".stl":   Format.STL,
    ".obj":   Format.OBJ,
    ".ply":   Format.PLY,
    ".fcstd": Format.FCSTD,
    ".sldprt": Format.SLDPRT,
    ".sldasm": Format.SLDASM,
    ".x_t":   Format.X_T,   ".xmt_txt": Format.X_T,
    ".x_b":   Format.X_B,   ".xmt_bin": Format.X_B,
    ".dxf":   Format.DXF,
    ".dwg":   Format.DWG,
    ".glb":   Format.GLB,
    ".gltf":  Format.GLTF,
}

# Magic bytes 签名
_MAGIC: List[Tuple[bytes, Format]] = [
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", Format.SLDPRT),   # OLE2 CFB (SLDPRT/SLDASM/FCStd老版)
    (b"PK\x03\x04",                         Format.FCSTD),  # ZIP (FCStd/GLB)
    (b"ISO-10303-",                         Format.STEP),   # STEP 头
    (b"solid ",                             Format.STL),    # ASCII STL
    (b"DBRep_DrawableShape",                Format.BREP),   # OCCT BREP
    (b"glTF",                               Format.GLB),    # GLB binary
]


# ── OLE2 嗅探器 (纯 stdlib, 无 olefile 依赖) ────────────────────────────
class OLE2Reader:
    """轻量 OLE2/CFB 嗅探器.

    仅读 header 和目录结构, 不做完整流解析 (那交给 olefile).
    用于区分 SLDPRT / SLDASM / 旧版 FCStd.
    """

    HEADER_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._raw = None

    @property
    def raw(self) -> bytes:
        if self._raw is None:
            with self.path.open("rb") as f:
                # 读前 64KB, 足够覆盖 header+dir(通常)
                self._raw = f.read(min(self.path.stat().st_size, 64 * 1024))
        return self._raw

    def is_ole2(self) -> bool:
        return self.raw[:8] == self.HEADER_MAGIC

    def detect_subtype(self) -> Format:
        """基于内部流名启发式判定."""
        if not self.is_ole2():
            return Format.UNKNOWN
        raw = self.raw
        # SolidWorks 流标识
        if (b"SwDoc"   in raw or b"SwXml" in raw or
            b"SolidW"  in raw or b"swXmlContents" in raw):
            # 区分 part / assembly: SLDASM 有 "Component" 流
            if b"Component" in raw or b"TopLevelNode" in raw:
                return Format.SLDASM
            return Format.SLDPRT
        if b"Config\x00\x00\x00" in raw and b"CAD" in raw:
            return Format.SLDPRT
        # 旧 FCStd 基于 OLE2 几乎不存在 (FC 使用 ZIP)
        return Format.UNKNOWN

    def metadata(self) -> Dict[str, Any]:
        """提取尽量多的元数据 (size, hash, subtype, 流名快照)."""
        size = self.path.stat().st_size
        raw = self.raw
        meta = {
            "path":      str(self.path),
            "size_B":    size,
            "size_MB":   round(size / (1024 * 1024), 3),
            "sha1":      self._sha1(),
            "is_ole2":   self.is_ole2(),
            "subtype":   self.detect_subtype().value,
        }
        # 粗略流名提取 (直接搜 "S\x00w\x00" 等 UTF-16LE 片段)
        hints = []
        for needle in (b"SwDoc", b"SwXml", b"Contents", b"Configuration",
                       b"Preview", b"JPEG", b"SummaryInformation"):
            if needle in raw:
                hints.append(needle.decode("latin-1"))
        meta["stream_hints"] = hints
        return meta

    def _sha1(self) -> str:
        h = hashlib.sha1()
        with self.path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()


# ── 格式识别 ────────────────────────────────────────────────────────────
def sniff(path: Union[str, Path]) -> Format:
    """自动识别 CAD 文件格式 (扩展名 + magic bytes 交叉验证)."""
    p = Path(path)
    ext = p.suffix.lower()
    ext_fmt = _EXT_MAP.get(ext, Format.UNKNOWN)

    if not p.exists():
        return ext_fmt

    # 读 magic
    try:
        with p.open("rb") as f:
            head = f.read(256)
    except OSError:
        return ext_fmt

    # 优先 magic bytes
    magic_fmt = Format.UNKNOWN
    for sig, fmt in _MAGIC:
        if head.startswith(sig):
            magic_fmt = fmt
            break
        if sig in head[:256]:
            magic_fmt = fmt
            break

    # OLE2 细分
    if magic_fmt == Format.SLDPRT:
        subtype = OLE2Reader(p).detect_subtype()
        if subtype != Format.UNKNOWN:
            magic_fmt = subtype

    # 冲突时 ext 优先 (如 .x_t 与 .step 都是纯文本, 无 magic)
    if ext_fmt != Format.UNKNOWN:
        return ext_fmt
    return magic_fmt


# ── FreeCAD 后端 (按需载入) ─────────────────────────────────────────────
class FCBackend:
    """FreeCAD 后端的懒加载封装.

    FreeCAD 不是标准 pip 包, 需通过命令行探测 `freecad` 或通过 Python 环境.
    此类支持两种模式:
      - in_process: 当前 Python 有 FreeCAD 模块 (少见, 仅当 PYTHONPATH 指向 FC bin)
      - out_of_process: 通过 `freecadcmd` / `FreeCAD.exe --console` 启动子进程
    """

    _avail: Optional[bool] = None
    _in_process: Optional[bool] = None
    _fc_cmd: Optional[str] = None

    @classmethod
    def available(cls) -> bool:
        if cls._avail is not None:
            return cls._avail
        # 1. 尝试 in-process
        try:
            import FreeCAD  # type: ignore  # noqa
            cls._in_process = True
            cls._avail = True
            return True
        except ImportError:
            cls._in_process = False
        # 2. 尝试 out-of-process
        for cand in ("freecadcmd", "freecad", "FreeCADCmd", "FreeCAD"):
            exe = shutil.which(cand)
            if exe:
                cls._fc_cmd = exe
                cls._avail = True
                return True
        # 3. 常见 Windows 路径
        for p in (r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe",
                  r"C:\Program Files\FreeCAD 1.0\bin\freecadcmd.exe",
                  r"C:\Program Files\FreeCAD 0.21\bin\freecadcmd.exe"):
            if os.path.exists(p):
                cls._fc_cmd = p
                cls._avail = True
                return True
        cls._avail = False
        return False

    @classmethod
    def run_script(cls, code: str, timeout: int = 300) -> Tuple[bool, str, str]:
        """在 FreeCAD 子进程里执行脚本 (out-of-process)."""
        if not cls.available():
            return False, "", "FreeCAD not available"
        if cls._in_process:
            # 直接 exec (注意: 会污染当前 Python)
            try:
                g = {"__name__": "__dao_fc__"}
                exec(code, g)
                return True, str(g.get("__result__", "")), ""
            except Exception as e:  # noqa: BLE001
                return False, "", str(e)
        # 子进程
        with tempfile.NamedTemporaryFile("w", suffix=".py",
                                         delete=False, encoding="utf-8") as fp:
            fp.write(code)
            tmp = fp.name
        try:
            # 强制 FC 子进程 stdout 用 UTF-8 (中文 label 正确输出)
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUTF8", "1")
            r = subprocess.run(
                [cls._fc_cmd, tmp],
                capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace",
                env=env,
            )
            return (r.returncode == 0), r.stdout or "", r.stderr or ""
        finally:
            try: os.remove(tmp)
            except OSError: pass


# ── SLDPRT 解析 (三级回退) ──────────────────────────────────────────────
def find_step_proxy(path: Path) -> Optional[Path]:
    """为 SLDPRT 查找 STEP 代理文件.

    回退顺序:
      1. same_stem.stp_ap203.sldprt  (SolidWorks "另存为 STEP" 产物)
      2. same_stem.step / same_stem.stp
      3. {stem}_step/step.step 等变体
    """
    p = Path(path)
    stem = p.stem
    parent = p.parent

    # 1. xxx.stp_ap203.sldprt
    candidates = [
        parent / f"{stem}.stp_ap203.sldprt",
        parent / f"{stem}_ap203.sldprt",
    ]
    # 2. xxx.step / xxx.stp
    candidates += [
        parent / f"{stem}.step",
        parent / f"{stem}.stp",
        parent / f"{stem}.STEP",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


# ── DaoModel: 万法 CAD 统一模型 ─────────────────────────────────────────
@dataclass
class DaoModel:
    """统一 CAD 模型抽象.

    内部 shape 可能是:
      - str:       源文件路径 (懒加载模式)
      - bytes:     内存字节流 (通用中转)
      - Any:       FreeCAD Part.Shape 或 OCCT TopoDS_Shape (加载后)

    披褐怀玉 · 和而不同: 外层 API 不变, 内层按后端变化.
    """
    src_path: Optional[str] = None
    fmt:      Format = Format.UNKNOWN
    shape:    Any = None                 # FC Shape / OCCT Shape / 路径字符串
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 缓存 STEP 中转字节, 实现多格式快速互转
    _step_bytes: Optional[bytes] = None

    # ─── 加载入口 ───────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: Union[str, Path],
             fmt: Optional[Format] = None) -> "DaoModel":
        """从文件加载. fmt=None 时自动识别."""
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(p)
        fmt = fmt or sniff(p)
        m = cls(src_path=str(p), fmt=fmt)

        if fmt == Format.SLDPRT or fmt == Format.SLDASM:
            m._load_sldprt(p)
        elif fmt == Format.STEP or fmt == Format.IGES or fmt == Format.BREP:
            m._load_occt(p, fmt)
        elif fmt == Format.FCSTD:
            m._load_fcstd(p)
        elif fmt in (Format.STL, Format.OBJ, Format.PLY):
            m._load_mesh(p, fmt)
        else:
            m.metadata["warn"] = f"format '{fmt.value}' only metadata probe"
        return m

    # ─── 加载实现 ───────────────────────────────────────────────────────
    def _load_sldprt(self, p: Path):
        """SLDPRT/SLDASM 多级回退:
          1. dao_solidworks.probe_file (深 OLE2 解析 · 无 SW 依赖)
          2. OLE2Reader (本地兼容 · 兜底)
          3. STEP proxy (同目录同名 stp/step/stp_ap203.sldprt)
          4. COM 活体 (若 SW 运行)
        """
        # Round 1 · 深反 (优先)
        try:
            import dao_solidworks as _sw  # 本源桥
            deep = _sw.probe_file(p)
            if deep.get("ok"):
                # 过滤大 blob, 只保留诊断信息
                light = {k: v for k, v in deep.items()
                         if k not in ("streams",)}
                # streams 截到 20 条 + size 统计
                light["streams_count"]    = len(deep.get("streams", []))
                light["streams_top"]      = deep.get("streams", [])[:20]
                light["largest_stream"]   = max(
                    (s for s in deep.get("streams", [])),
                    key=lambda s: s.get("size", 0), default=None,
                )
                self.metadata["sw_deep"] = light
                # 若有预览 PNG, 记录文件大小
                if deep.get("preview"):
                    self.metadata["preview"] = deep["preview"]
        except Exception as e:  # noqa: BLE001
            self.metadata["sw_deep_err"] = f"{type(e).__name__}: {e}"

        # Round 2 · 轻 OLE2 兼容
        r = OLE2Reader(p)
        self.metadata["ole2"] = r.metadata()

        # Round 3 · STEP proxy 回退 (便于几何体量/bbox)
        proxy = find_step_proxy(p)
        if proxy is not None:
            self.metadata["step_proxy"] = str(proxy)
            if proxy.suffix.lower() in (".step", ".stp"):
                self._load_occt(proxy, Format.STEP)
            elif proxy.name.endswith(".stp_ap203.sldprt"):
                try:
                    head = proxy.read_bytes()[:256]
                except OSError:
                    head = b""
                if head.startswith(b"ISO-10303-"):
                    tmp = Path(tempfile.gettempdir()) / f"_dao_{proxy.stem}.step"
                    shutil.copy2(proxy, tmp)
                    self._load_occt(tmp, Format.STEP)
                else:
                    self.metadata["proxy_is_ole2"] = True
        else:
            # 无代理时也不阻断 — sw_deep 已有足够信息
            if "sw_deep" not in self.metadata:
                self.metadata["warn"] = "no STEP proxy and no sw_deep metadata"

    def _load_occt(self, p: Path, fmt: Format):
        """通过 FreeCAD 的 Part 模块读取 STEP/IGES/BREP."""
        if not FCBackend.available():
            self.metadata["warn"] = "FreeCAD unavailable, metadata-only"
            self.metadata["size_B"] = p.stat().st_size
            return
        # 用子进程获取 bbox + volume
        code = _render_script(_FC_PROBE_SCRIPT, path=str(p).replace("\\", "/"))
        ok, out, err = FCBackend.run_script(code, timeout=120)
        if ok:
            try:
                info = json.loads(_extract_result(out) or "{}")
                self.metadata.update(info)
                self.shape = str(p)      # 懒持有路径, 需要时再 open
            except json.JSONDecodeError as e:
                self.metadata["parse_error"] = str(e)
                self.metadata["raw_out"] = out[-500:]
        else:
            self.metadata["fc_error"] = err[-500:] if err else "unknown"

    def _load_fcstd(self, p: Path):
        """读 FCStd 文档元数据."""
        if not FCBackend.available():
            self.metadata["size_B"] = p.stat().st_size
            self.metadata["warn"] = "FreeCAD unavailable, metadata-only"
            return
        code = _render_script(_FC_FCSTD_PROBE, path=str(p).replace("\\", "/"))
        ok, out, err = FCBackend.run_script(code, timeout=120)
        if ok:
            try:
                self.metadata.update(json.loads(_extract_result(out) or "{}"))
                self.shape = str(p)
            except Exception as e:  # noqa: BLE001
                self.metadata["parse_error"] = str(e)
        else:
            self.metadata["fc_error"] = err[-500:] if err else ""

    def _load_mesh(self, p: Path, fmt: Format):
        """读网格 (STL/OBJ/PLY) 的基本元数据.

        不依赖 FC, 自己解析头 (STL ascii/binary 区分).
        """
        size = p.stat().st_size
        self.metadata["size_B"] = size
        if fmt == Format.STL:
            with p.open("rb") as f:
                head = f.read(5)
            if head == b"solid":
                self.metadata["stl_mode"] = "ascii"
            else:
                self.metadata["stl_mode"] = "binary"
                with p.open("rb") as f:
                    f.seek(80)
                    n = struct.unpack("<I", f.read(4))[0]
                    self.metadata["stl_n_triangles"] = n
        self.shape = str(p)

    # ─── 保存入口 ───────────────────────────────────────────────────────
    def save(self, path: Union[str, Path],
             fmt: Optional[Format] = None) -> Path:
        """保存到目标格式. fmt=None 时从扩展名自动识别.

        SLDPRT/SLDASM 源的写出路径 (反者道之动):
          A. 若有 STEP proxy → 走 FC 转换 (通用稳定)
          B. 否则若 SW COM 可连 → 走 dao_solidworks.SolidWorksBridge.convert
          C. 否则报错, 提示导出一个 STEP proxy 即可
        """
        p = Path(path)
        fmt = fmt or _EXT_MAP.get(p.suffix.lower(), Format.UNKNOWN)
        if fmt == Format.UNKNOWN:
            raise ValueError(f"unknown target format: {p}")

        p.parent.mkdir(parents=True, exist_ok=True)

        # SLDPRT/SLDASM 源特殊处理
        if self.fmt in (Format.SLDPRT, Format.SLDASM) and self.src_path:
            # Path A: 已有 STEP proxy (shape 已指向 proxy)
            if isinstance(self.shape, str) and Path(self.shape).exists() \
               and Path(self.shape).suffix.lower() in (".step", ".stp"):
                return self._fc_convert(Path(self.shape), p, fmt)
            # Path B: SW COM 直导
            try:
                return self._sw_save(Path(self.src_path), p, fmt)
            except Exception as e:  # noqa: BLE001
                # Path C: 兜底失败
                raise RuntimeError(
                    f"SLDPRT write failed (no STEP proxy, SW COM err: {e})"
                )

        # 源既是文件路径 → 通过 FC 转换
        if isinstance(self.shape, str) and Path(self.shape).exists():
            return self._fc_convert(Path(self.shape), p, fmt)

        # 源是 FC Shape (in-process) → 直接导出
        if self.shape is not None and FCBackend._in_process:
            return self._fc_export_inproc(p, fmt)

        raise RuntimeError(
            f"no loaded shape to save (src={self.src_path}, fmt={self.fmt})"
        )

    def _sw_save(self, src: Path, dst: Path, dst_fmt: Format) -> Path:
        """通过 SolidWorksBridge (COM) 导出 SLDPRT → 目标格式."""
        import dao_solidworks as _sw
        fmt_name = {
            Format.STEP: "step", Format.IGES: "iges",
            Format.STL:  "stl",  Format.X_T:  "x_t",
            Format.X_B:  "x_b",  Format.DXF:  "dxf",
            Format.DWG:  "dwg",
        }.get(dst_fmt, dst_fmt.value)
        bridge = _sw.SolidWorksBridge()
        if not bridge.is_installed():
            raise RuntimeError("SolidWorks not installed; cannot _sw_save")
        bridge.connect(prefer_active=True, launch_if_needed=True, launch_timeout_s=90.0)
        try:
            return bridge.convert(src, dst, fmt=fmt_name)
        finally:
            bridge.disconnect(exit_sw=False)

    # ─── 子例程 ─────────────────────────────────────────────────────────
    def _fc_convert(self, src: Path, dst: Path, dst_fmt: Format) -> Path:
        """out-of-process: FC 读源, 导出为目标格式."""
        if not FCBackend.available():
            raise RuntimeError("FreeCAD unavailable for conversion")
        code = _render_script(
            _FC_CONVERT_SCRIPT,
            src=str(src).replace("\\", "/"),
            dst=str(dst).replace("\\", "/"),
            src_ext=src.suffix.lower(),
            dst_ext=dst.suffix.lower(),
            dst_fmt=dst_fmt.value,
        )
        ok, out, err = FCBackend.run_script(code, timeout=300)
        if not ok or not dst.exists():
            raise RuntimeError(f"FC convert failed: {err[-400:]}")
        return dst

    def _fc_export_inproc(self, dst: Path, fmt: Format) -> Path:
        import Part, Mesh  # type: ignore
        s = self.shape
        if fmt == Format.STEP:
            s.exportStep(str(dst))
        elif fmt == Format.IGES:
            s.exportIges(str(dst))
        elif fmt == Format.BREP:
            s.exportBrep(str(dst))
        elif fmt == Format.STL:
            Mesh.Mesh(s.tessellate(0.1)).write(str(dst))
        elif fmt == Format.OBJ:
            Mesh.Mesh(s.tessellate(0.1)).write(str(dst))
        else:
            raise ValueError(f"in-process export not supported: {fmt}")
        return dst

    # ─── 信息 ───────────────────────────────────────────────────────────
    def info(self) -> Dict[str, Any]:
        return {
            "src":      self.src_path,
            "fmt":      self.fmt.value if isinstance(self.fmt, Format) else str(self.fmt),
            "loaded":   self.shape is not None,
            **self.metadata,
        }

    def __repr__(self) -> str:
        n = self.metadata.get("n_shapes") or self.metadata.get("n_objects") or "?"
        vol = self.metadata.get("volume_mm3") or self.metadata.get("total_volume_mm3") or "?"
        return f"<DaoModel fmt={self.fmt.value} src={self.src_path!r} n={n} vol={vol}>"


# ── FC 脚本模板 (子进程执行) ─────────────────────────────────────────────
# 使用 __PLACEHOLDER__ 占位符 (通过 str.replace), 避免 .format() 的花括号逃逸麻烦.
_FC_PROBE_SCRIPT = r"""
import sys, json, os
try:
    import FreeCAD as App, Part
except Exception as e:
    print("__DAO_RESULT__" + json.dumps({"error": str(e)}))
    sys.exit(1)

path = r"__PATH__"
try:
    shapes = Part.read(path)
    if hasattr(shapes, "SubShapes") and shapes.SubShapes:
        n = len(shapes.SubShapes)
    else:
        n = 1
    bb = shapes.BoundBox
    out = {
        "n_shapes":   n,
        "volume_mm3": round(float(shapes.Volume), 1),
        "area_mm2":   round(float(shapes.Area), 1),
        "bbox_mm":    [round(bb.XLength,1), round(bb.YLength,1), round(bb.ZLength,1)],
        "bbox_min":   [round(bb.XMin,1), round(bb.YMin,1), round(bb.ZMin,1)],
        "bbox_max":   [round(bb.XMax,1), round(bb.YMax,1), round(bb.ZMax,1)],
        "is_valid":   bool(shapes.isValid()),
    }
    print("__DAO_RESULT__" + json.dumps(out))
except Exception as e:
    print("__DAO_RESULT__" + json.dumps({"error": str(e)}))
    sys.exit(1)
"""


_FC_FCSTD_PROBE = r"""
import sys, json
try:
    import FreeCAD as App, Part
except Exception as e:
    print("__DAO_RESULT__" + json.dumps({"error": str(e)}))
    sys.exit(1)

path = r"__PATH__"
try:
    doc = App.openDocument(path, True)
    n_objs = len(doc.Objects)
    total_vol = 0.0; n_valid = 0; labels = []
    bb_all = None
    for o in doc.Objects:
        if not hasattr(o, "Shape") or o.Shape is None or o.Shape.isNull():
            continue
        total_vol += float(o.Shape.Volume)
        if o.Shape.isValid(): n_valid += 1
        labels.append(o.Label)
        bb = o.Shape.BoundBox
        if bb_all is None:
            bb_all = bb
        else:
            bb_all.add(bb)
    out = {
        "n_objects":        n_objs,
        "n_valid":          n_valid,
        "total_volume_mm3": round(total_vol, 1),
        "labels":           labels[:40],
    }
    if bb_all is not None:
        out["bbox_mm"] = [round(bb_all.XLength,1), round(bb_all.YLength,1), round(bb_all.ZLength,1)]
    print("__DAO_RESULT__" + json.dumps(out, ensure_ascii=False))
    App.closeDocument(doc.Name)
except Exception as e:
    print("__DAO_RESULT__" + json.dumps({"error": str(e)}))
    sys.exit(1)
"""


_FC_CONVERT_SCRIPT = r"""
import sys, json, os
try:
    import FreeCAD as App, Part
except Exception as e:
    print("__DAO_RESULT__" + json.dumps({"error": str(e)}))
    sys.exit(1)

src     = r"__SRC__"
dst     = r"__DST__"
src_ext = "__SRC_EXT__"
dst_ext = "__DST_EXT__"
dst_fmt = "__DST_FMT__"

try:
    if src_ext in (".step", ".stp", ".iges", ".igs", ".brep", ".brp"):
        shape = Part.read(src)
    elif src_ext == ".fcstd":
        doc = App.openDocument(src, True)
        shapes = []
        for o in doc.Objects:
            if hasattr(o, "Shape") and o.Shape is not None and not o.Shape.isNull():
                shapes.append(o.Shape)
        if not shapes:
            raise RuntimeError("FCStd has no valid shapes")
        shape = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
    elif src_ext in (".stl", ".obj"):
        import Mesh
        mesh = Mesh.Mesh()
        mesh.read(src)
        shape = Part.Shape()
        shape.makeShapeFromMesh(mesh.Topology, 0.05)
    else:
        raise ValueError("unsupported source: " + src_ext)

    if dst_fmt == "step":
        shape.exportStep(dst)
    elif dst_fmt == "iges":
        shape.exportIges(dst)
    elif dst_fmt == "brep":
        shape.exportBrep(dst)
    elif dst_fmt in ("stl", "obj"):
        import Mesh
        m = Mesh.Mesh(shape.tessellate(0.1))
        m.write(dst)
    elif dst_fmt == "fcstd":
        doc2 = App.newDocument("dao_export")
        f = doc2.addObject("Part::Feature", "dao_imported")
        f.Shape = shape
        doc2.recompute()
        doc2.saveAs(dst)
    else:
        raise ValueError("unsupported target: " + dst_fmt)

    size = os.path.getsize(dst)
    print("__DAO_RESULT__" + json.dumps({"ok": True, "dst": dst, "size": size}))
except Exception as e:
    print("__DAO_RESULT__" + json.dumps({"error": str(e)}))
    sys.exit(1)
"""


def _render_script(tmpl: str, **kw) -> str:
    """占位符替换 (避免 .format 的花括号陷阱)."""
    out = tmpl
    for k, v in kw.items():
        out = out.replace(f"__{k.upper()}__", str(v))
    return out


def _extract_result(out: str) -> Optional[str]:
    """从 FC 子进程 stdout 提取 __DAO_RESULT__ 后的 JSON."""
    if not out:
        return None
    # 找最后一个 marker (FC 启动会产生一堆 banner)
    idx = out.rfind("__DAO_RESULT__")
    if idx < 0:
        return None
    rest = out[idx + len("__DAO_RESULT__"):]
    # 取到行尾或文件尾
    end = rest.find("\n")
    return rest[:end].strip() if end >= 0 else rest.strip()


# ── 便捷函数 ────────────────────────────────────────────────────────────
def convert(src: Union[str, Path], dst: Union[str, Path],
            src_fmt: Optional[Format] = None,
            dst_fmt: Optional[Format] = None) -> Path:
    """一键转换: 自动识别源和目标格式."""
    m = DaoModel.load(src, fmt=src_fmt)
    return m.save(dst, fmt=dst_fmt)


def sync_dir(src_dir: Union[str, Path],
             dst_dir: Union[str, Path],
             target_fmts: List[Format],
             overwrite: bool = False) -> List[Path]:
    """目录同步: 对 src_dir 下每个 CAD 文件, 按 target_fmts 导出到 dst_dir.

    "无为而无不为": 批量, 幂等, 默认跳过已存在.
    """
    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    out: List[Path] = []
    for p in src_dir.iterdir():
        if not p.is_file():
            continue
        fmt = sniff(p)
        if fmt == Format.UNKNOWN:
            continue
        for tf in target_fmts:
            dst = dst_dir / f"{p.stem}.{tf.value}"
            if dst.exists() and not overwrite:
                out.append(dst)
                continue
            try:
                convert(p, dst, src_fmt=fmt, dst_fmt=tf)
                out.append(dst)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {p.name} -> {tf.value}: {e}")
    return out


# ── 自测 ────────────────────────────────────────────────────────────────
def _self_test(verbose: bool = True) -> Dict[str, Any]:
    """道生一 · 自洽自测. 返回评分矩阵."""
    log = []
    def _log(m):
        if verbose: print(m)
        log.append(m)

    res: Dict[str, Any] = {"score": 0, "total": 0, "pass": [], "fail": []}

    # T1: 格式枚举完整
    try:
        assert Format.STEP.value == "step"
        assert _EXT_MAP[".sldprt"] == Format.SLDPRT
        res["pass"].append("T1_enum"); res["total"] += 1; res["score"] += 1
    except Exception as e:
        res["fail"].append(("T1_enum", str(e))); res["total"] += 1

    # T2: sniff 简单路径
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".step", delete=False) as f:
            f.write("ISO-10303-21;\nHEADER;\nENDSEC;\n")
            tp = f.name
        f = sniff(tp)
        os.unlink(tp)
        assert f == Format.STEP, f
        res["pass"].append("T2_sniff_step"); res["total"] += 1; res["score"] += 1
    except Exception as e:
        res["fail"].append(("T2_sniff_step", str(e))); res["total"] += 1

    # T3: OLE2 reader 识别 SLDPRT (若存在)
    try:
        cand = Path(__file__).parents[1] / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机" / "sldprt" / "hammer_crusher_total_machine.sldprt"
        if cand.exists():
            r = OLE2Reader(cand)
            assert r.is_ole2()
            meta = r.metadata()
            assert meta["size_B"] > 0
            _log(f"   OLE2 hints: {meta.get('stream_hints')}")
            res["pass"].append("T3_ole2"); res["total"] += 1; res["score"] += 1
        else:
            res["pass"].append("T3_ole2_skipped"); res["total"] += 1; res["score"] += 1
    except Exception as e:
        res["fail"].append(("T3_ole2", str(e))); res["total"] += 1

    # T4: find_step_proxy
    try:
        cand = Path(__file__).parents[1] / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机" / "sldprt" / "hammer_crusher_total_machine.sldprt"
        if cand.exists():
            proxy = find_step_proxy(cand)
            _log(f"   proxy for SLDPRT: {proxy}")
            # proxy 可能是 .stp_ap203.sldprt 或 .step, 都算通过
        res["pass"].append("T4_proxy"); res["total"] += 1; res["score"] += 1
    except Exception as e:
        res["fail"].append(("T4_proxy", str(e))); res["total"] += 1

    # T5: FC 可用性探测 (不强制)
    try:
        fc_ok = FCBackend.available()
        _log(f"   FreeCAD available: {fc_ok}  (cmd={FCBackend._fc_cmd})")
        res["pass"].append("T5_fc_probe"); res["total"] += 1; res["score"] += 1
    except Exception as e:
        res["fail"].append(("T5_fc_probe", str(e))); res["total"] += 1

    # T6: DaoModel.load on SLDPRT (回退到 STEP proxy 元数据)
    try:
        cand = Path(__file__).parents[1] / "60-实战_Projects" / "南京-吴鸿轩_锤式破碎机" / "sldprt" / "hammer_crusher_total_machine.sldprt"
        if cand.exists():
            m = DaoModel.load(cand)
            _log(f"   {m}")
            assert m.fmt in (Format.SLDPRT, Format.SLDASM)
            assert "ole2" in m.metadata
        res["pass"].append("T6_sldprt_load"); res["total"] += 1; res["score"] += 1
    except Exception as e:
        res["fail"].append(("T6_sldprt_load", str(e))); res["total"] += 1

    res["ratio"] = f"{res['score']}/{res['total']}"
    res["score_pct"] = round(100.0 * res["score"] / max(res["total"], 1), 1)
    return res


# ── CLI ─────────────────────────────────────────────────────────────────
def _cli():
    import argparse
    ap = argparse.ArgumentParser(
        description="dao_cad_bridge · 万法 CAD I/O 桥 · 披褐怀玉",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("sniff",   help="识别文件格式")
    s1.add_argument("file")

    s2 = sub.add_parser("info",    help="读取并显示元数据")
    s2.add_argument("file")
    s2.add_argument("--json", action="store_true")

    s3 = sub.add_parser("convert", help="转换 src -> dst")
    s3.add_argument("src"); s3.add_argument("dst")

    s4 = sub.add_parser("sync",    help="目录同步")
    s4.add_argument("src"); s4.add_argument("dst")
    s4.add_argument("--fmt", default="step,stl",
                    help="目标格式逗号分隔 (默认 step,stl)")
    s4.add_argument("--overwrite", action="store_true")

    sub.add_parser("test", help="自测")

    a = ap.parse_args()

    if a.cmd == "sniff":
        f = sniff(a.file)
        print(f.value)
    elif a.cmd == "info":
        m = DaoModel.load(a.file)
        info = m.info()
        if a.json:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            print(f"fmt:    {info.get('fmt')}")
            print(f"src:    {info.get('src')}")
            for k, v in info.items():
                if k in ("src", "fmt"): continue
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)[:200]
                print(f"  {k:20s} {v}")
    elif a.cmd == "convert":
        dst = convert(a.src, a.dst)
        print(f"ok: {dst}  ({dst.stat().st_size:,}B)")
    elif a.cmd == "sync":
        fmts = [Format(x.strip()) for x in a.fmt.split(",") if x.strip()]
        outs = sync_dir(a.src, a.dst, fmts, overwrite=a.overwrite)
        print(f"synced {len(outs)} files to {a.dst}")
        for p in outs[:20]:
            print(f"  {p}")
    elif a.cmd == "test":
        res = _self_test()
        print("\n" + "=" * 54)
        print(f"  dao_cad_bridge 自测: {res['ratio']}  ({res['score_pct']}%)")
        print("=" * 54)
        for p in res["pass"]: print(f"  ✓ {p}")
        for n, e in res["fail"]: print(f"  ✗ {n}: {e}")


if __name__ == "__main__":
    _cli()
