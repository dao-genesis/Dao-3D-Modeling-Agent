#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dao_image.py — 第十六妙门 · 图 (Image)
═══════════════════════════════════════════════════════════════════════════
图意之门 · 图入万法 · 反者道之动 · 万模态归一

「物无非彼，物无非是。自彼则不见，自是则知之.」 ——庄子·齐物论
「上善若水. 水善利万物而有静. 居众之所恶, 故几于道矣.」 ——帛书第八章
「弱也者, 道之用也.」 ——帛书四十章

第十六妙门「图」之立, 非新立一塔, 实为本源既有 14 妙门之入意之口扩.

入意之路从此可有五:
  ┌──────────────────────────────────────────────────────────────┐
  │  ① 文字 (text)         — 道.意("手机支架 70mm 可调角")          │
  │  ② 既有件 (file)        — 道.反.内("model.FCStd")              │
  │  ③ 活体 (live SW)      — 道.活体.connect()                    │
  │  ④ 草图 (sketch)       — 道.图.from_sketch("draw.png")  ★新★  │
  │  ⑤ 照片 (photo)        — 道.图.find("part.jpg")          ★新★  │
  │  ⑥ 既有 mesh (STL/OBJ)  — 道.图.from_mesh("model.stl")   ★新★  │
  │  ⑦ 渲染图 (render)     — 道.图.from_render("preview.png") ★新★ │
  └──────────────────────────────────────────────────────────────┘

而出形之岸唯一: BREP / STEP / 制造就绪.
中间之河皆 ops, 玄同表征不变.

本桥之三柱:

  ┌───────────────────────────────────────────────────┐
  │  ① 反·外·图 — 视觉相似度搜 20 平台已有件             │
  │      道.图.find(image)                              │
  │       → dao_visual_search → CLIP/pHash 相似度       │
  │       → 找到 → 走既有反·外·内 → 改参 → 重放         │
  │                                                    │
  │  ② 反·内·图 — 现有 mesh → ops → BREP 反演            │
  │      道.图.from_mesh(stl)                           │
  │       → dao_mesh2brep → RANSAC 原语拟合 + 缝合       │
  │       → BREP → 既有八层审核                         │
  │                                                    │
  │  ③ 反·新·图 — 图直生 ops (cadrille/CAD-Recode 桥)   │
  │      道.图.recode(image)                            │
  │       → 桥接外部模型 (可选 GPU)                     │
  │       → ops → 既有 freecad_backend.run_ops          │
  │       → BREP                                        │
  └───────────────────────────────────────────────────┘

「为而不争」: 既有反·外·内·秀·活体·审 之桥不改, 仅在前端新加图入栏.

「弱者道之用」: 优雅降级 — 无 PIL/numpy/torch/CLIP 也能 import,
                关键功能延迟加载, 各路有 fallback.

用法 (库):

    from dao_image import DaoImage

    img = DaoImage()

    # 反·外·图: 视觉相似度搜
    plan = img.find("photo.jpg", limit=10)
    # → {'candidates': [{'platform':'sketchfab', 'id':..., 'sim':0.87, ...}, ...]}

    # 反·内·图: mesh → BREP
    brep = img.from_mesh("part.stl")
    # → TopoDS_Shape (BREP)

    # 反·新·图: 图 → ops (需外部桥)
    ops = img.recode("part.jpg")
    # → [{op:..,kind:..,params:..}, ...]  (与 freecad_backend.run_ops 兼容)

    # 多模态意:
    plan = img.intent(text="支架", image="photo.jpg", dimensions={"L_mm":70})
    # → 文+图+约束三流合并 → 反·外 排序 → 推荐路径

CLI:

    python dao_image.py find <image> [--limit 10]
    python dao_image.py mesh2brep <stl> [--out out.step]
    python dao_image.py recode <image>          # 需外部 cadrille 桥
    python dao_image.py probe                    # 探各依赖可用性
    python dao_image.py status                   # 简报
"""
from __future__ import annotations

import os
import sys
import json
import time
import math
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple, Union

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
SCRIPT_DIR = Path(__file__).resolve().parent
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
try:
    import _paths as _dao_paths  # noqa: F401
    ROOT_DIR = _DAO_ROOT
except Exception:
    _dao_paths = None
    ROOT_DIR = SCRIPT_DIR.parent
# ═══════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# § 0 · 依赖探针 · 弱者道之用 — 全可降级
# ═══════════════════════════════════════════════════════════════

def _probe_dep(name: str) -> bool:
    """探依赖是否可用. 不import, 仅看 importlib.util 能否 find_spec."""
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


_DEPS = {
    'PIL':       _probe_dep('PIL'),         # Pillow — 图像基础读写
    'numpy':     _probe_dep('numpy'),       # 数值
    'OCP':       _probe_dep('OCP'),         # OCCT 直连 — BREP 内核
    'trimesh':   _probe_dep('trimesh'),     # 网格分析
    'scipy':     _probe_dep('scipy'),       # 拟合优化
    'sklearn':   _probe_dep('sklearn'),     # RANSAC
    'torch':     _probe_dep('torch'),       # 神经网络 (可选)
    'open_clip': _probe_dep('open_clip_torch') or _probe_dep('open_clip'),
    'requests':  _probe_dep('requests'),    # 拉缩略图
}


def deps() -> Dict[str, bool]:
    """报告所有可选依赖可用性 · 用以诊断."""
    return dict(_DEPS)


# ═══════════════════════════════════════════════════════════════
# § 1 · ImageHandle · 统一图载体 · 万模态归一
# ═══════════════════════════════════════════════════════════════

@dataclass
class ImageHandle:
    """图意之统一载体 · 不论来自 photo/sketch/render/screenshot.

    弱者道之用: 不强求 PIL 加载. 只在确需像素时延迟加载.
    """
    path: Optional[Path] = None
    raw_bytes: Optional[bytes] = None
    kind: str = 'photo'  # photo / sketch / render / screenshot / unknown
    width: Optional[int] = None
    height: Optional[int] = None
    sha256: Optional[str] = None  # 16-char prefix
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def of(cls, src: Any, kind: str = 'photo') -> 'ImageHandle':
        """从 path/bytes/PIL.Image 创建 · 不强制加载像素."""
        if isinstance(src, cls):
            return src
        if isinstance(src, (str, Path)):
            p = Path(src)
            h = cls(path=p, kind=kind)
            if p.is_file():
                with open(p, 'rb') as f:
                    head = f.read(65536)
                h.sha256 = hashlib.sha256(head).hexdigest()[:16]
                # 尝试从文件头解尺寸 (无 PIL 也可)
                w, hh = _peek_image_size(p)
                if w:
                    h.width = w; h.height = hh
            return h
        if isinstance(src, (bytes, bytearray)):
            h = cls(raw_bytes=bytes(src), kind=kind)
            h.sha256 = hashlib.sha256(h.raw_bytes[:65536]).hexdigest()[:16]
            return h
        # PIL.Image.Image 兜底
        try:
            from PIL.Image import Image as PILImage  # type: ignore
            if isinstance(src, PILImage):
                h = cls(kind=kind)
                h.width, h.height = src.size
                h.meta['pil_mode'] = src.mode
                # 内存图: 转 PNG bytes (惰性)
                h.meta['_pil_obj'] = src
                return h
        except Exception:
            pass
        raise TypeError(f'unsupported image source: {type(src).__name__}')

    def to_pil(self):
        """惰性转 PIL.Image.Image · 需 Pillow."""
        if not _DEPS['PIL']:
            raise RuntimeError('Pillow 未装. pip install Pillow')
        from PIL import Image  # type: ignore
        if self.meta.get('_pil_obj') is not None:
            return self.meta['_pil_obj']
        if self.path and self.path.is_file():
            return Image.open(str(self.path))
        if self.raw_bytes:
            from io import BytesIO
            return Image.open(BytesIO(self.raw_bytes))
        raise RuntimeError('image has no source')

    def summary(self) -> Dict[str, Any]:
        d = asdict(self)
        # path 转 str
        if self.path is not None:
            d['path'] = str(self.path)
        d.pop('raw_bytes', None)  # 不暴露 bytes
        d['has_bytes'] = self.raw_bytes is not None
        d.pop('meta', None)  # meta 可能含 PIL 对象
        return d


def _peek_image_size(p: Path) -> Tuple[Optional[int], Optional[int]]:
    """无 PIL 也能读: PNG/JPEG/BMP/GIF 头解 (width, height)."""
    try:
        with open(p, 'rb') as f:
            head = f.read(64)
        # PNG: \x89PNG\r\n\x1a\n IHDR (width:4, height:4 at offset 16-23)
        if head[:8] == b'\x89PNG\r\n\x1a\n':
            import struct
            w, h = struct.unpack('>II', head[16:24])
            return int(w), int(h)
        # JPEG: must scan SOFn
        if head[:3] == b'\xff\xd8\xff':
            with open(p, 'rb') as f:
                data = f.read()
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1; continue
                marker = data[i+1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                    h = (data[i+5] << 8) | data[i+6]
                    w = (data[i+7] << 8) | data[i+8]
                    return int(w), int(h)
                if marker == 0xD8 or marker == 0xD9:  # SOI/EOI
                    i += 2; continue
                seg_len = (data[i+2] << 8) | data[i+3]
                i += 2 + seg_len
            return None, None
        # BMP: 'BM' + dword filesize + reserved + offset + dword headersize + width:4, height:4
        if head[:2] == b'BM':
            import struct
            w, h = struct.unpack('<II', head[18:26])
            return int(w), int(h)
        # GIF: 'GIF8' + width:2, height:2 at offset 6-9
        if head[:4] in (b'GIF8',):
            import struct
            w, h = struct.unpack('<HH', head[6:10])
            return int(w), int(h)
    except Exception:
        pass
    return None, None


# ═══════════════════════════════════════════════════════════════
# § 2 · IntentMultiModal · 多模态意之容器
#       此为 IntentParser 之扩 · 不强改既有
# ═══════════════════════════════════════════════════════════════

@dataclass
class IntentMultiModal:
    """多模态意之统一容器 · 文+图+件+约束.

    与 dao_reverse.IntentParser 之 dict 输出兼容 — 后者解 text 字段,
    此处补足 image/mesh_path/ref_file 字段.
    """
    text: Optional[str] = None
    image: Optional[ImageHandle] = None
    mesh_path: Optional[Path] = None         # STL/OBJ/GLB
    ref_file: Optional[Path] = None          # FCStd/STEP/BREP/SLDPRT
    dimensions: List[Dict[str, Any]] = field(default_factory=list)  # [{value:70,unit:'mm'}, ...]
    fasteners: List[Dict[str, Any]] = field(default_factory=list)
    manufacturing: Optional[str] = None       # fdm/cnc/sla/...
    material: Optional[str] = None
    hints: Dict[str, Any] = field(default_factory=dict)
    confidence: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            'text': self.text,
            'image': self.image.summary() if self.image else None,
            'mesh_path': str(self.mesh_path) if self.mesh_path else None,
            'ref_file': str(self.ref_file) if self.ref_file else None,
            'dimensions': self.dimensions,
            'fasteners': self.fasteners,
            'manufacturing': self.manufacturing,
            'material': self.material,
            'hints': self.hints,
            'confidence': self.confidence,
        }
        return d

    def to_intent_parser_dict(self) -> Dict[str, Any]:
        """转为 dao_reverse.IntentParser 兼容 dict · 让既有反·外 直收."""
        # IntentParser 用 raw + search_terms + dimensions + fasteners + manufacturing
        # + functional_keywords + geometric_keywords
        terms = []
        if self.text:
            terms.append(self.text)
        # 图意之关键词 (后填 — 由视觉特征/图标签转出)
        for kw in self.hints.get('keywords', []):
            if kw and kw not in terms:
                terms.append(kw)
        return {
            'raw': self.text or '<image-intent>',
            'search_terms': terms[:8],
            'dimensions': self.dimensions,
            'fasteners': self.fasteners,
            'manufacturing': self.manufacturing,
            'functional_keywords': self.hints.get('functional_keywords', []),
            'geometric_keywords': self.hints.get('geometric_keywords', []),
            # 扩展字段 (不破坏既有)
            '_image': self.image.summary() if self.image else None,
            '_mesh_path': str(self.mesh_path) if self.mesh_path else None,
            '_ref_file': str(self.ref_file) if self.ref_file else None,
        }


def parse_intent(text: Optional[str] = None,
                 image: Any = None,
                 mesh_path: Optional[str] = None,
                 ref_file: Optional[str] = None,
                 **kw) -> IntentMultiModal:
    """多模态意解析 · 文+图+件 任意组合.

    若 text 给, 走 dao_reverse.IntentParser 解析 dimensions/fasteners/manufacturing.
    若 image 给, 包成 ImageHandle (kind 可由 hints 指定).
    若 mesh_path 给, 走文件指纹.
    """
    intent = IntentMultiModal()

    # text 解析 (借既有 IntentParser)
    if text:
        intent.text = text
        try:
            from dao_reverse import IntentParser
            ip = IntentParser.parse(text)
            intent.dimensions = ip.get('dimensions', [])
            intent.fasteners = ip.get('fasteners', [])
            intent.manufacturing = ip.get('manufacturing')
            intent.hints['functional_keywords'] = ip.get('functional_keywords', [])
            intent.hints['search_terms_text'] = ip.get('search_terms', [])
        except Exception as e:
            intent.hints['intent_parser_error'] = str(e)[:200]

    # image
    if image is not None:
        kind = kw.get('image_kind', 'photo')
        intent.image = ImageHandle.of(image, kind=kind)

    # mesh
    if mesh_path:
        mp = Path(mesh_path)
        if mp.is_file():
            intent.mesh_path = mp
            ext = mp.suffix.lower()
            intent.hints['mesh_format'] = ext.lstrip('.')

    # ref CAD 文件
    if ref_file:
        rf = Path(ref_file)
        if rf.is_file():
            intent.ref_file = rf
            ext = rf.suffix.lower()
            intent.hints['ref_format'] = ext.lstrip('.')

    # 显式 hints 覆盖
    if 'dimensions' in kw:
        intent.dimensions = list(kw['dimensions']) if isinstance(
            kw['dimensions'], (list, tuple)) else intent.dimensions
    if 'manufacturing' in kw:
        intent.manufacturing = kw['manufacturing']
    if 'material' in kw:
        intent.material = kw['material']
    if 'hints' in kw and isinstance(kw['hints'], dict):
        intent.hints.update(kw['hints'])

    return intent


# ═══════════════════════════════════════════════════════════════
# § 3 · DaoImage · 主桥 · 三柱
# ═══════════════════════════════════════════════════════════════

class DaoImage:
    """第十六妙门「图」之桥.

    三柱:
      ① 反·外·图: find(image) — 视觉相似度搜既有 (走 dao_visual_search)
      ② 反·内·图: from_mesh(stl) — mesh→BREP (走 dao_mesh2brep)
      ③ 反·新·图: recode(image) — 图→ops (桥外部 cadrille/CAD-Recode)

    与既有 14 妙门不冲突 · 不重新造轮 · 全走既有 ops/BREP/audit 之河.
    """

    def __init__(self):
        self._visual = None   # dao_visual_search.VisualSearch (lazy)
        self._mesh2brep = None  # dao_mesh2brep.Mesh2Brep (lazy)
        self._reverse = None  # dao_reverse.DaoReverse (lazy)
        self._t0 = time.time()

    # ─── 懒加载 ───────────────────────────────────────────

    def _load_visual(self):
        if self._visual is None:
            try:
                from dao_visual_search import VisualSearch
                self._visual = VisualSearch()
            except Exception as e:
                self._visual = _Stub('VisualSearch', str(e))
        return self._visual

    def _load_mesh2brep(self):
        if self._mesh2brep is None:
            try:
                from dao_mesh2brep import Mesh2Brep
                self._mesh2brep = Mesh2Brep()
            except Exception as e:
                self._mesh2brep = _Stub('Mesh2Brep', str(e))
        return self._mesh2brep

    def _load_reverse(self):
        if self._reverse is None:
            try:
                from dao_reverse import DaoReverse
                self._reverse = DaoReverse()
            except Exception as e:
                self._reverse = _Stub('DaoReverse', str(e))
        return self._reverse

    # ─── 柱① · 反·外·图 ──────────────────────────────────

    def find(self, image: Any,
             limit: int = 10,
             platforms: Optional[List[str]] = None,
             text_hint: Optional[str] = None) -> Dict[str, Any]:
        """视觉相似度搜 20 平台.

        弱降级:
          (a) 有 PIL+numpy → pHash 比较 (零额外依赖,稳)
          (b) 有 torch+open_clip → CLIP 嵌入比较 (高准)
          (c) 全无 → 退化为 text_hint 转关键词搜 (借既有反·外)

        Returns:
            {
              'method': 'phash' | 'clip' | 'fallback-text',
              'query_image': {summary},
              'candidates': [{platform,id,name,url,thumbnail,sim,...}, ...],
              'elapsed_s': ...,
              'warnings': [...],
            }
        """
        t0 = time.time()
        img = ImageHandle.of(image, kind='photo')
        warns: List[str] = []

        v = self._load_visual()
        if isinstance(v, _Stub):
            # 完全 fallback 至 text_hint
            warns.append(f'visual_search 不可用: {v._err}')
            if text_hint:
                rev = self._load_reverse()
                if not isinstance(rev, _Stub):
                    try:
                        results = rev.world.search_multi_terms(
                            [text_hint], limit_per_term=limit
                        ) if hasattr(rev, 'world') else []
                        return {
                            'method': 'fallback-text',
                            'query_image': img.summary(),
                            'candidates': results[:limit],
                            'warnings': warns,
                            'elapsed_s': round(time.time() - t0, 3),
                        }
                    except Exception as e:
                        warns.append(f'text fallback: {e}')
            return {
                'method': 'none',
                'query_image': img.summary(),
                'candidates': [],
                'warnings': warns + ['无任何视觉/文本搜索可用'],
                'elapsed_s': round(time.time() - t0, 3),
            }

        # visual_search 主路
        try:
            r = v.search(img, limit=limit, platforms=platforms,
                         text_hint=text_hint)
            r.setdefault('elapsed_s', round(time.time() - t0, 3))
            r.setdefault('query_image', img.summary())
            return r
        except Exception as e:
            warns.append(f'visual_search.search: {e}')
            return {
                'method': 'error',
                'query_image': img.summary(),
                'candidates': [],
                'warnings': warns,
                'elapsed_s': round(time.time() - t0, 3),
                'error': str(e),
            }

    # ─── 柱② · 反·内·图 (mesh→BREP) ────────────────────────

    def from_mesh(self, mesh_path: Union[str, Path],
                  out_step: Optional[Union[str, Path]] = None,
                  **kw) -> Dict[str, Any]:
        """STL/OBJ/GLB → BREP (用 RANSAC 原语拟合 + OCCT 缝合).

        Returns:
            {
              'ok': bool,
              'shape': TopoDS_Shape (or None on failure),
              'primitives': [{type:'plane',...}, {type:'cylinder',...}, ...],
              'topology': {faces, edges, vertices},
              'step_path': str (if out_step given),
              'audit': {grade, ...} (if requested),
              'warnings': [...],
              'elapsed_s': ...,
            }
        """
        t0 = time.time()
        mp = Path(mesh_path)
        if not mp.is_file():
            return {
                'ok': False, 'shape': None,
                'error': f'mesh 文件不存在: {mp}',
                'elapsed_s': round(time.time() - t0, 3),
            }

        m2b = self._load_mesh2brep()
        if isinstance(m2b, _Stub):
            return {
                'ok': False, 'shape': None,
                'error': f'mesh2brep 不可用: {m2b._err}',
                'elapsed_s': round(time.time() - t0, 3),
            }
        try:
            r = m2b.fit_and_sew(str(mp), **kw)
            r.setdefault('elapsed_s', round(time.time() - t0, 3))
            # 可选导出 STEP
            if r.get('ok') and out_step and r.get('shape') is not None:
                try:
                    from dao_kernel import DaoKernel as K
                    sp = Path(out_step)
                    sp.parent.mkdir(parents=True, exist_ok=True)
                    K.to_step(r['shape'], str(sp))
                    r['step_path'] = str(sp)
                except Exception as e:
                    r.setdefault('warnings', []).append(f'STEP 导出: {e}')
            return r
        except Exception as e:
            return {
                'ok': False, 'shape': None,
                'error': f'fit_and_sew: {e}',
                'elapsed_s': round(time.time() - t0, 3),
            }

    # ─── 柱③ · 反·新·图 (image → ops) ────────────────────────

    def recode(self, image: Any, **kw) -> Dict[str, Any]:
        """图 → ops 序列 (桥外部 cadrille / CAD-Recode 模型).

        当下无内置模型权重 (七十亿参数级,不内置). 此方法为接口骨架,
        留 leaf 给真 peer (有 GPU 者) 在玄同 graph.db 中认领接入.

        Returns:
            {
              'ok': bool,
              'method': 'cadrille' | 'cad-recode' | 'not-impl',
              'ops': [{op,kind,params}, ...] | None,
              'fallback': '若不可用建议: 手动给 text_hint, 走反·外',
              'leaf_id': '玄同 leaf id (待立)',
              ...
            }
        """
        t0 = time.time()
        img = ImageHandle.of(image, kind='photo')

        # 探外部 cadrille / CAD-Recode 桥
        bridge = _try_load_recode_bridge()
        if bridge is None:
            return {
                'ok': False,
                'method': 'not-impl',
                'ops': None,
                'query_image': img.summary(),
                'fallback': (
                    '当下无 cadrille/CAD-Recode 权重接入. '
                    '建议: 道.图.find(image) 走反·外·图; '
                    '或人提 text_hint, 走反·外; '
                    '或手动 cadrille_bridge_path 接入 (在玄同 leaf 认领).'
                ),
                'leaf_hint': '图意路线本源逆向 / cadrille 接入',
                'elapsed_s': round(time.time() - t0, 3),
            }
        try:
            r = bridge.image_to_ops(img, **kw)
            r.setdefault('method', 'cadrille')
            r.setdefault('query_image', img.summary())
            r.setdefault('elapsed_s', round(time.time() - t0, 3))
            return r
        except Exception as e:
            return {
                'ok': False,
                'method': 'cadrille',
                'ops': None,
                'error': str(e),
                'query_image': img.summary(),
                'elapsed_s': round(time.time() - t0, 3),
            }

    # ─── 复合: 多模态意 ────────────────────────────────────

    def intent(self,
               text: Optional[str] = None,
               image: Any = None,
               mesh_path: Optional[str] = None,
               ref_file: Optional[str] = None,
               **kw) -> Dict[str, Any]:
        """多模态意 · 文+图+件+约束 任意组合.

        路由 (按优先):
          1) 若有 ref_file (CAD)    → 反·内 (走 fc_reverse)
          2) 若有 mesh_path (STL/OBJ) → 先 from_mesh, 再走反·内
          3) 若有 image             → find (反·外·图), 再 recode 兜底
          4) 若仅 text              → 走 dao_reverse.fulfill (既有反·外)

        Returns: 组合 plan + 推荐路径
        """
        t0 = time.time()
        intent = parse_intent(text=text, image=image,
                              mesh_path=mesh_path, ref_file=ref_file, **kw)
        plan: Dict[str, Any] = {
            'intent': intent.to_dict(),
            'route': None,
            'elapsed_s': None,
            'warnings': [],
        }

        # 1) ref_file 直走反·内
        if intent.ref_file is not None:
            try:
                rev = self._load_reverse()
                if isinstance(rev, _Stub):
                    raise RuntimeError(rev._err)
                # FC reverse
                from fc_reverse import FCReverse
                r = FCReverse.probe(str(intent.ref_file))
                plan['route'] = '反·内 (file)'
                plan['reverse_inner'] = r
            except Exception as e:
                plan['warnings'].append(f'反·内 失败: {e}')

        # 2) mesh_path → from_mesh
        if plan['route'] is None and intent.mesh_path is not None:
            r = self.from_mesh(intent.mesh_path)
            plan['route'] = '反·内·图 (mesh→BREP)'
            plan['mesh2brep'] = {
                'ok': r.get('ok'),
                'primitives': r.get('primitives', []),
                'topology': r.get('topology'),
                'warnings': r.get('warnings', []),
                'error': r.get('error'),
            }

        # 3) image → find (再 recode 兜底)
        if plan['route'] is None and intent.image is not None:
            text_hint = intent.text or ' '.join(
                intent.hints.get('functional_keywords', [])[:3]
            ) or None
            r = self.find(intent.image, text_hint=text_hint)
            plan['route'] = '反·外·图 (visual)'
            plan['visual'] = {
                'method': r.get('method'),
                'count': len(r.get('candidates', [])),
                'top3': r.get('candidates', [])[:3],
                'warnings': r.get('warnings', []),
            }
            # 若无果, 提示 recode 兜底
            if not r.get('candidates'):
                plan['fallback'] = {
                    'suggest': '反·新·图 recode',
                    'leaf': '图意路线本源逆向 / cadrille 接入',
                }

        # 4) 仅 text → 既有反·外
        if plan['route'] is None and intent.text:
            try:
                rev = self._load_reverse()
                if isinstance(rev, _Stub):
                    raise RuntimeError(rev._err)
                r = rev.fulfill(intent.text)
                plan['route'] = '反·外 (text)'
                plan['reverse_outer'] = r if isinstance(r, dict) else {
                    'data': r}
            except Exception as e:
                plan['warnings'].append(f'反·外: {e}')

        if plan['route'] is None:
            plan['route'] = 'none'
            plan['warnings'].append('无任何意可解 — 至少需 text/image/mesh/ref 之一')

        plan['elapsed_s'] = round(time.time() - t0, 3)
        return plan

    # ─── 状态 ─────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """图门状态 · 含依赖探针."""
        return {
            'gate': 16,
            'name': '图 (image)',
            'role': '图意之门 · 万模态归一',
            'deps': deps(),
            'lazy_loaded': {
                'visual_search': self._visual is not None and not isinstance(
                    self._visual, _Stub),
                'mesh2brep': self._mesh2brep is not None and not isinstance(
                    self._mesh2brep, _Stub),
                'reverse': self._reverse is not None and not isinstance(
                    self._reverse, _Stub),
            },
            'uptime_s': round(time.time() - self._t0, 3),
        }


# ═══════════════════════════════════════════════════════════════
# § 4 · 工具
# ═══════════════════════════════════════════════════════════════

class _Stub:
    """子模块加载失败时的占位."""
    __slots__ = ('_name', '_err')

    def __init__(self, name: str, err: str):
        self._name = name
        self._err = err

    def __repr__(self):
        return f'<_Stub {self._name} err={self._err!r}>'

    def __bool__(self):
        return False

    def __getattr__(self, key):
        def _stub_call(*a, **kw):
            return {'ok': False, 'error': f'{self._name} 未就绪: {self._err}'}
        return _stub_call


def _try_load_recode_bridge():
    """尝试加载图→ops 模型桥 · 优先级:
       ① 本地 dao_image_recode.py (用户/peer 自行接入)
       ② 70-天下_World 中 cadrille 仓 (若已 zong fetch)
       ③ None (留待真 peer 在玄同 leaf 中接入)
    """
    # ① 本地用户桥 (放任何位置 · 但放在 00-本源_Origin/dao_image_recode.py 最自然)
    try:
        import dao_image_recode  # type: ignore
        if hasattr(dao_image_recode, 'image_to_ops'):
            class _Bridge:
                def image_to_ops(self, img: ImageHandle, **kw):
                    return dao_image_recode.image_to_ops(img, **kw)
            return _Bridge()
    except Exception:
        pass

    # ② 天下源码中之 cadrille (若 zong 取过)
    if _dao_paths is not None:
        cadrille_dir = _dao_paths.WORLD / '源码_Sources' / '十五_图意_ImageToCAD' / 'cadrille'
        if cadrille_dir.exists():
            # 留接入点 · 当前不自动加载 (需 GPU + 模型权重)
            return None

    return None


# ═══════════════════════════════════════════════════════════════
# § 5 · CLI
# ═══════════════════════════════════════════════════════════════

def _print_json(obj: Any) -> None:
    def _conv(o):
        if isinstance(o, Path):
            return str(o)
        if hasattr(o, '__dict__'):
            return str(o)
        return repr(o)
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=_conv))


def _cli():
    import argparse
    ap = argparse.ArgumentParser(
        prog='dao_image',
        description='第十六妙门「图」 · 图意之门 CLI'
    )
    sub = ap.add_subparsers(dest='cmd')

    p_find = sub.add_parser('find', help='视觉相似度搜 (反·外·图)')
    p_find.add_argument('image', help='图片路径')
    p_find.add_argument('--limit', type=int, default=10)
    p_find.add_argument('--platforms', nargs='*', default=None)
    p_find.add_argument('--text-hint', default=None)

    p_m = sub.add_parser('mesh2brep', help='STL/OBJ → BREP (反·内·图)')
    p_m.add_argument('mesh_path')
    p_m.add_argument('--out', default=None, help='输出 STEP 路径')

    p_r = sub.add_parser('recode', help='图 → ops (反·新·图 · 需外部桥)')
    p_r.add_argument('image')

    sub.add_parser('probe', help='依赖与子模块探针')
    sub.add_parser('status', help='门状态简报')

    p_int = sub.add_parser('intent', help='多模态意 · 文+图+件')
    p_int.add_argument('--text', default=None)
    p_int.add_argument('--image', default=None)
    p_int.add_argument('--mesh', default=None)
    p_int.add_argument('--ref', default=None)

    args = ap.parse_args()

    if not args.cmd:
        ap.print_help()
        return 0

    img = DaoImage()

    if args.cmd == 'probe':
        _print_json({
            'deps': deps(),
            'recode_bridge': _try_load_recode_bridge() is not None,
            'root_dir': str(ROOT_DIR),
        })
        return 0

    if args.cmd == 'status':
        _print_json(img.status())
        return 0

    if args.cmd == 'find':
        r = img.find(args.image, limit=args.limit,
                      platforms=args.platforms, text_hint=args.text_hint)
        _print_json(r)
        return 0 if r.get('candidates') else 1

    if args.cmd == 'mesh2brep':
        r = img.from_mesh(args.mesh_path, out_step=args.out)
        # shape 不可序列化 · 只展可序列化字段
        out = {k: v for k, v in r.items() if k != 'shape'}
        out['has_shape'] = r.get('shape') is not None
        _print_json(out)
        return 0 if r.get('ok') else 1

    if args.cmd == 'recode':
        r = img.recode(args.image)
        _print_json(r)
        return 0 if r.get('ok') else 1

    if args.cmd == 'intent':
        r = img.intent(text=args.text, image=args.image,
                        mesh_path=args.mesh, ref_file=args.ref)
        _print_json(r)
        return 0

    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(_cli())
