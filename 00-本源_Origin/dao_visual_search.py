#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dao_visual_search.py — 视觉相似度反·外·图
═══════════════════════════════════════════════════════════════════════════
「天网恢恢, 疏而不失.」 ——帛书七十三章
「不出于户, 以知天下; 不窥于牖, 以知天道.」 ——帛书四十七章

立此之缘:
  现 dao_reverse.WorldSearch 仅按文本关键词搜 8 平台 (printables/sketchfab/cults3d/
  yeggi/...). 用户最自然之意表达是 **拍一张照片**. 本模块即立"图入"之栏:

  ┌───────────────────────────────────────────────────────────┐
  │  query_image  →  embed (pHash / CLIP / hist)              │
  │     ↓                                                      │
  │  既有反·外搜 (text_hint 或 通用查询)                       │
  │     ↓                                                      │
  │  对每候选: fetch 缩略图 → embed → 与 query 比较相似度       │
  │     ↓                                                      │
  │  按相似度排序 → 取 top-N → 走既有反·外·内适配链路          │
  └───────────────────────────────────────────────────────────┘

「弱者道之用」: 三档优雅降级
  ① pHash (零依赖)        — 64-bit DCT-based, 颜色失真鲁棒, 适缩略图
  ② numpy + PIL 颜色直方图 — 中等准, 比 pHash 更细
  ③ torch + open_clip      — 最准, 跨域 (照片 ↔ 渲染图) 强

「为而不争」:
  - 不重写 资源探针.py 的平台层 — 借既有 `WorldSearch.search_all_platforms`
  - 不强制下载原模型 — 只拉缩略图 (KB级) 算相似度
  - 优先利用 `result['thumbnail']` 字段 (大多平台已返此)

用法:

    from dao_visual_search import VisualSearch

    vs = VisualSearch()

    # 主路: 视觉相似度搜
    r = vs.search('photo.jpg', limit=10, text_hint='phone stand')
    # → {'method': 'phash', 'candidates': [{'platform','id','sim',...}], ...}

    # pHash 单算 (供其他场景)
    h1 = vs.phash('a.jpg')
    h2 = vs.phash('b.jpg')
    sim = vs.phash_sim(h1, h2)   # ∈ [0, 1] · 1=同图 · 0=最远
"""
from __future__ import annotations

import os
import sys
import json
import math
import time
import hashlib
import urllib.request
import urllib.error
import ssl
from io import BytesIO
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
SCRIPT_DIR = Path(__file__).resolve().parent
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
try:
    import _paths as _dao_paths  # noqa: F401
except Exception:
    _dao_paths = None
# ═══════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# § 0 · 依赖探针
# ═══════════════════════════════════════════════════════════════

def _probe(name: str) -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


_HAS_PIL    = _probe('PIL')
_HAS_NUMPY  = _probe('numpy')
_HAS_TORCH  = _probe('torch')
_HAS_CLIP   = _probe('open_clip_torch') or _probe('open_clip')


def deps() -> Dict[str, bool]:
    return {
        'PIL': _HAS_PIL,
        'numpy': _HAS_NUMPY,
        'torch': _HAS_TORCH,
        'open_clip': _HAS_CLIP,
    }


# ═══════════════════════════════════════════════════════════════
# § 1 · pHash · 零依赖感知 hash · 64-bit DCT
# ═══════════════════════════════════════════════════════════════

def _gray_8bit(pixels: List[List[Tuple[int, int, int]]]) -> List[List[int]]:
    """RGB → 8-bit gray · 纯 Python."""
    return [[int(0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2])
             for p in row] for row in pixels]


def _resize_nearest_pure(pixels: List[List[Tuple[int, int, int]]],
                          new_w: int, new_h: int) -> List[List[Tuple[int, int, int]]]:
    """纯 Python 最近邻缩放 · 仅 fallback 用."""
    h = len(pixels); w = len(pixels[0]) if h else 0
    if w == 0 or h == 0:
        return [[(0, 0, 0)] * new_w for _ in range(new_h)]
    out = []
    for y in range(new_h):
        sy = min(int(y * h / new_h), h - 1)
        row = []
        for x in range(new_w):
            sx = min(int(x * w / new_w), w - 1)
            row.append(pixels[sy][sx])
        out.append(row)
    return out


def _dct_1d(v: List[float]) -> List[float]:
    """一维 DCT-II · 纯 Python (短向量)."""
    N = len(v)
    out = []
    for k in range(N):
        s = 0.0
        for n in range(N):
            s += v[n] * math.cos(math.pi * (2 * n + 1) * k / (2 * N))
        out.append(s)
    return out


def _dct_2d(matrix: List[List[float]]) -> List[List[float]]:
    """二维 DCT (先行后列)."""
    rows = [_dct_1d(r) for r in matrix]
    if not rows:
        return rows
    cols = len(rows[0])
    transposed = [[rows[r][c] for r in range(len(rows))] for c in range(cols)]
    transposed = [_dct_1d(r) for r in transposed]
    return [[transposed[c][r] for c in range(cols)] for r in range(len(rows))]


def phash(image_path_or_bytes: Union[str, Path, bytes],
           hash_size: int = 8) -> int:
    """64-bit perceptual hash (DCT-based).

    优先 PIL+numpy 走 fast path (毫秒级).
    无依赖时纯 Python (慢, 但一图 < 100ms 仍可用).

    Returns: int (64-bit if hash_size=8)
    """
    # 加载 + 灰度 + resize 32×32
    if _HAS_PIL:
        from PIL import Image  # type: ignore
        if isinstance(image_path_or_bytes, (bytes, bytearray)):
            img = Image.open(BytesIO(bytes(image_path_or_bytes)))
        else:
            img = Image.open(str(image_path_or_bytes))
        img = img.convert('L').resize((hash_size * 4, hash_size * 4),
                                       Image.LANCZOS)
        if _HAS_NUMPY:
            import numpy as np
            arr = np.asarray(img, dtype=np.float64)
            # DCT (借 scipy 若有, 否则纯 numpy 实现一维 DCT)
            dct = _np_dct2d(arr)
            low = dct[:hash_size, :hash_size]
            mean = (low.sum() - low[0, 0]) / (hash_size * hash_size - 1)
            bits = (low > mean).flatten()[:64]
            h = 0
            for b in bits:
                h = (h << 1) | int(bool(b))
            return int(h)
        else:
            # PIL no-numpy
            pixels = list(img.getdata())
            w, h = img.size
            mat = [pixels[i * w:(i + 1) * w] for i in range(h)]
            mat_f = [[float(p) for p in row] for row in mat]
            dct = _dct_2d(mat_f)
            low = [row[:hash_size] for row in dct[:hash_size]]
            tot = sum(sum(row) for row in low) - low[0][0]
            mean = tot / (hash_size * hash_size - 1)
            h_val = 0
            for r, row in enumerate(low):
                for c, v in enumerate(row):
                    h_val = (h_val << 1) | (1 if v > mean else 0)
            return int(h_val)

    # 全无 PIL: 仅支持 PNG/BMP via stdlib + 纯 Python (有限)
    # 退化: 用文件 sha256 头 8 字节作"hash" - 非感知, 但有标识价值
    return _fallback_file_hash(image_path_or_bytes, hash_size=hash_size)


def _np_dct2d(arr):
    """numpy 实现 2D DCT-II · 借 scipy.fft 若有."""
    try:
        from scipy.fft import dct  # type: ignore
        return dct(dct(arr, axis=0, norm='ortho'), axis=1, norm='ortho')
    except Exception:
        # 纯 numpy 实现 (慢但通)
        import numpy as np
        N = arr.shape[0]; M = arr.shape[1]
        # 行 DCT
        ys = np.arange(N); xs = np.arange(M)
        c1 = np.cos(np.pi * (2 * ys[None, :] + 1) * ys[:, None] / (2 * N))
        c2 = np.cos(np.pi * (2 * xs[None, :] + 1) * xs[:, None] / (2 * M))
        return c1 @ arr @ c2.T


def _fallback_file_hash(src: Union[str, Path, bytes],
                         hash_size: int = 8) -> int:
    """无 PIL 时之兜底 — 取文件 sha256 截 64-bit. 非感知但有唯一性."""
    if isinstance(src, (bytes, bytearray)):
        h = hashlib.sha256(bytes(src)).digest()
    else:
        with open(src, 'rb') as f:
            h = hashlib.sha256(f.read(65536)).digest()
    return int.from_bytes(h[:8], 'big', signed=False)


def phash_sim(h1: int, h2: int) -> float:
    """两 hash 之相似度 ∈ [0, 1]. 1=同图. 走 hamming distance."""
    diff = h1 ^ h2
    # popcount 64-bit
    bits = bin(diff).count('1')
    return 1.0 - bits / 64.0


# ═══════════════════════════════════════════════════════════════
# § 2 · 颜色直方图 (中阶) · 跨色调更稳
# ═══════════════════════════════════════════════════════════════

def color_histogram(image_path_or_bytes: Union[str, Path, bytes],
                     bins: int = 8) -> Optional[List[float]]:
    """RGB 色直方图 · bins×bins×bins 维向量, 归一化."""
    if not _HAS_PIL:
        return None
    from PIL import Image  # type: ignore
    if isinstance(image_path_or_bytes, (bytes, bytearray)):
        img = Image.open(BytesIO(bytes(image_path_or_bytes)))
    else:
        img = Image.open(str(image_path_or_bytes))
    img = img.convert('RGB').resize((128, 128))

    if _HAS_NUMPY:
        import numpy as np
        arr = np.asarray(img)
        # 分桶
        idx = (arr // (256 // bins)).astype(np.int64)
        flat = idx[:, :, 0] * bins * bins + idx[:, :, 1] * bins + idx[:, :, 2]
        hist = np.bincount(flat.flatten(), minlength=bins ** 3).astype(np.float64)
        s = hist.sum()
        if s > 0:
            hist = hist / s
        return hist.tolist()

    # 纯 Python
    pixels = list(img.getdata())
    hist = [0.0] * (bins * bins * bins)
    step = 256 // bins
    for r, g, b in pixels:
        ri = min(r // step, bins - 1)
        gi = min(g // step, bins - 1)
        bi = min(b // step, bins - 1)
        hist[ri * bins * bins + gi * bins + bi] += 1
    s = sum(hist)
    if s > 0:
        hist = [x / s for x in hist]
    return hist


def hist_sim(h1: List[float], h2: List[float]) -> float:
    """直方图相似度 (intersection · ∈ [0,1])."""
    if not h1 or not h2 or len(h1) != len(h2):
        return 0.0
    return sum(min(a, b) for a, b in zip(h1, h2))


# ═══════════════════════════════════════════════════════════════
# § 3 · CLIP 嵌入 (高阶 · 可选)
# ═══════════════════════════════════════════════════════════════

class _ClipBackend:
    """open_clip 包装 · 懒加载 · 单例.

    仅在 deps['torch'] and deps['open_clip'] 时启用.
    模型默 ViT-B-32 (开源 LAION-2B-s34B-b79K), 占显存 ~600MB.
    """

    _model = None
    _preprocess = None
    _device = None
    _model_name = 'ViT-B-32'
    _pretrained = 'laion2b_s34b_b79k'

    @classmethod
    def available(cls) -> bool:
        return _HAS_TORCH and _HAS_CLIP

    @classmethod
    def load(cls, model_name: Optional[str] = None,
             pretrained: Optional[str] = None,
             device: Optional[str] = None):
        if cls._model is not None:
            return
        if not cls.available():
            raise RuntimeError('torch / open_clip 未装. CLIP 路不可用.')
        try:
            import open_clip  # type: ignore
        except Exception:
            try:
                import open_clip_torch as open_clip  # type: ignore
            except Exception as e:
                raise RuntimeError(f'open_clip 加载失败: {e}')
        import torch
        cls._device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        if model_name:
            cls._model_name = model_name
        if pretrained:
            cls._pretrained = pretrained
        m, _, p = open_clip.create_model_and_transforms(
            cls._model_name, pretrained=cls._pretrained)
        cls._model = m.to(cls._device).eval()
        cls._preprocess = p

    @classmethod
    def embed_image(cls, image_path_or_bytes: Union[str, Path, bytes]):
        cls.load()
        from PIL import Image  # type: ignore
        import torch
        if isinstance(image_path_or_bytes, (bytes, bytearray)):
            img = Image.open(BytesIO(bytes(image_path_or_bytes)))
        else:
            img = Image.open(str(image_path_or_bytes))
        img = img.convert('RGB')
        x = cls._preprocess(img).unsqueeze(0).to(cls._device)
        with torch.no_grad():
            feat = cls._model.encode_image(x)
            feat = feat / feat.norm(dim=-1, keepdim=True)
        return feat.cpu().numpy()[0]

    @classmethod
    def cos_sim(cls, a, b) -> float:
        import numpy as np
        return float(np.dot(a, b))


# ═══════════════════════════════════════════════════════════════
# § 4 · 缩略图获取 · 借 stdlib · 失败静默
# ═══════════════════════════════════════════════════════════════

_SSL_CTX = ssl.create_default_context()
_SSL_CTX_NOVERIFY = ssl.create_default_context()
_SSL_CTX_NOVERIFY.check_hostname = False
_SSL_CTX_NOVERIFY.verify_mode = ssl.CERT_NONE

_THUMB_CACHE: Dict[str, bytes] = {}
_THUMB_CACHE_MAX = 256
_UA = 'DaoVisualSearch/1.0 (3D Modeling Agent)'


def fetch_thumbnail(url: str, timeout: int = 8,
                     max_bytes: int = 4 * 1024 * 1024) -> Optional[bytes]:
    """拉缩略图 · 内存缓存 · 大小封顶 4MB."""
    if not url:
        return None
    if url in _THUMB_CACHE:
        return _THUMB_CACHE[url]
    req = urllib.request.Request(url, headers={'User-Agent': _UA})
    for ctx in (_SSL_CTX, _SSL_CTX_NOVERIFY):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = resp.read(max_bytes)
                if len(_THUMB_CACHE) >= _THUMB_CACHE_MAX:
                    # 简单 LRU: 删最早一项
                    try:
                        first_key = next(iter(_THUMB_CACHE))
                        del _THUMB_CACHE[first_key]
                    except Exception:
                        _THUMB_CACHE.clear()
                _THUMB_CACHE[url] = data
                return data
        except Exception:
            continue
    return None


# ═══════════════════════════════════════════════════════════════
# § 5 · VisualSearch · 主类 · 三档自适应
# ═══════════════════════════════════════════════════════════════

class VisualSearch:
    """视觉相似度搜索 · 接 既有 dao_reverse.WorldSearch."""

    def __init__(self, method: str = 'auto',
                 thumbnail_timeout: int = 6):
        """method ∈ {'auto', 'phash', 'hist', 'clip'}.

        auto: clip if available else phash (hist 仅作辅证).
        """
        self.method = method
        self.thumbnail_timeout = thumbnail_timeout
        self._world = None  # WorldSearch 懒加载

    def _load_world(self):
        if self._world is None:
            try:
                from dao_reverse import WorldSearch
                self._world = WorldSearch
            except Exception as e:
                raise RuntimeError(f'WorldSearch 不可用: {e}')
        return self._world

    def _pick_method(self) -> str:
        if self.method != 'auto':
            return self.method
        if _ClipBackend.available():
            return 'clip'
        if _HAS_PIL:
            return 'phash'
        return 'phash'  # 仍走, 但走 fallback file hash

    # ─── 公接口 ─────────────────────────────────────────

    def search(self,
               image: Any,
               limit: int = 10,
               platforms: Optional[List[str]] = None,
               text_hint: Optional[str] = None,
               candidate_pool: int = 30) -> Dict[str, Any]:
        """主入口 · 视觉相似度搜.

        流程:
          1) embed query image (phash 或 clip embedding)
          2) 借 既有 WorldSearch.search_all_platforms 取候选池
             (text_hint 若给, 用之做关键词搜索; 不给则用 '*' 通用查询)
          3) 对每候选: 拉缩略图 → embed → 比较相似度
          4) 按相似度排序 · 取 top limit
        """
        t0 = time.time()
        warns: List[str] = []
        method = self._pick_method()

        # 取 image bytes / path
        from dao_image import ImageHandle  # type: ignore
        img = ImageHandle.of(image, kind='photo') \
            if not isinstance(image, ImageHandle) else image

        # 1) 编码 query
        try:
            if method == 'clip':
                _ClipBackend.load()
                q_path = img.path or _bytes_to_temp(img.raw_bytes)
                q_emb = _ClipBackend.embed_image(q_path)
                q_kind = 'clip-embed'
            else:
                # phash
                if img.path is not None:
                    q_emb = phash(img.path)
                elif img.raw_bytes is not None:
                    q_emb = phash(img.raw_bytes)
                else:
                    raise RuntimeError('image has no source')
                q_kind = 'phash'
        except Exception as e:
            warns.append(f'query embed: {e}')
            return {
                'method': method,
                'candidates': [],
                'warnings': warns,
                'error': str(e),
                'elapsed_s': round(time.time() - t0, 3),
            }

        # 2) 取候选池 · 借既有 WorldSearch
        candidates: List[Dict[str, Any]] = []
        try:
            World = self._load_world()
            query_terms = [text_hint or '*']
            results = World.search_multi_terms(
                query_terms,
                limit_per_term=candidate_pool,
                platforms=platforms,
            )
            candidates = list(results)
        except Exception as e:
            warns.append(f'world search: {e}')

        if not candidates:
            return {
                'method': method,
                'candidates': [],
                'warnings': warns + ['无候选 (text_hint/platforms 可能受限)'],
                'elapsed_s': round(time.time() - t0, 3),
            }

        # 3) 评分
        scored = []
        for cand in candidates:
            thumb_url = (cand.get('thumbnail') or cand.get('preview')
                          or cand.get('image') or cand.get('icon'))
            if not thumb_url:
                cand['_sim'] = 0.0
                cand['_sim_method'] = 'no-thumbnail'
                scored.append(cand)
                continue
            thumb_bytes = fetch_thumbnail(
                thumb_url, timeout=self.thumbnail_timeout)
            if not thumb_bytes:
                cand['_sim'] = 0.0
                cand['_sim_method'] = 'thumb-fetch-fail'
                scored.append(cand)
                continue
            try:
                if method == 'clip':
                    tmp = _bytes_to_temp(thumb_bytes)
                    t_emb = _ClipBackend.embed_image(tmp)
                    sim = _ClipBackend.cos_sim(q_emb, t_emb)
                else:
                    t_h = phash(thumb_bytes)
                    sim = phash_sim(q_emb, t_h)
                cand['_sim'] = float(sim)
                cand['_sim_method'] = q_kind
            except Exception as e:
                cand['_sim'] = 0.0
                cand['_sim_method'] = f'embed-error: {str(e)[:80]}'
            scored.append(cand)

        # 4) 排序
        scored.sort(key=lambda c: c.get('_sim', 0.0), reverse=True)
        top = scored[:limit]

        return {
            'method': method,
            'q_kind': q_kind,
            'candidate_count': len(scored),
            'returned': len(top),
            'candidates': top,
            'warnings': warns,
            'elapsed_s': round(time.time() - t0, 3),
        }

    # 单点工具 · 暴露给外
    @staticmethod
    def phash(src) -> int:
        return phash(src)

    @staticmethod
    def phash_sim(h1: int, h2: int) -> float:
        return phash_sim(h1, h2)

    @staticmethod
    def hist(src) -> Optional[List[float]]:
        return color_histogram(src)

    @staticmethod
    def hist_sim(h1, h2) -> float:
        return hist_sim(h1, h2)


# ═══════════════════════════════════════════════════════════════
# § 6 · 工具
# ═══════════════════════════════════════════════════════════════

def _bytes_to_temp(b: bytes) -> str:
    import tempfile
    suffix = '.png' if b[:8] == b'\x89PNG\r\n\x1a\n' else '.jpg'
    tf = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tf.write(b); tf.close()
    return tf.name


# ═══════════════════════════════════════════════════════════════
# § 7 · CLI
# ═══════════════════════════════════════════════════════════════

def _print_json(o):
    print(json.dumps(o, ensure_ascii=False, indent=2, default=str))


def _cli():
    import argparse
    ap = argparse.ArgumentParser(
        prog='dao_visual_search',
        description='视觉相似度反·外·图'
    )
    sub = ap.add_subparsers(dest='cmd')

    p_s = sub.add_parser('search', help='视觉相似度搜')
    p_s.add_argument('image', help='查询图路径')
    p_s.add_argument('--limit', type=int, default=10)
    p_s.add_argument('--text-hint', default=None)
    p_s.add_argument('--platforms', nargs='*', default=None)
    p_s.add_argument('--method', default='auto',
                     choices=['auto', 'phash', 'hist', 'clip'])
    p_s.add_argument('--pool', type=int, default=30)

    p_h = sub.add_parser('phash', help='单图 phash')
    p_h.add_argument('image')

    p_c = sub.add_parser('compare', help='两图相似度')
    p_c.add_argument('a')
    p_c.add_argument('b')
    p_c.add_argument('--method', default='phash',
                     choices=['phash', 'hist', 'clip'])

    sub.add_parser('probe', help='依赖探针')

    args = ap.parse_args()

    if not args.cmd:
        ap.print_help()
        return 0

    if args.cmd == 'probe':
        _print_json({
            'deps': deps(),
            'recommended_method': (
                'clip' if _ClipBackend.available()
                else ('phash' if _HAS_PIL else 'fallback-file-hash')
            ),
        })
        return 0

    if args.cmd == 'phash':
        h = phash(args.image)
        _print_json({'image': args.image, 'phash': format(h, '016x'),
                      'phash_int': h})
        return 0

    if args.cmd == 'compare':
        if args.method == 'phash':
            h1 = phash(args.a); h2 = phash(args.b)
            sim = phash_sim(h1, h2)
            _print_json({
                'method': 'phash',
                'a': args.a, 'b': args.b,
                'phash_a': format(h1, '016x'),
                'phash_b': format(h2, '016x'),
                'sim': sim,
            })
        elif args.method == 'hist':
            h1 = color_histogram(args.a); h2 = color_histogram(args.b)
            if not h1 or not h2:
                print('hist 不可用 (需 PIL)')
                return 2
            _print_json({'method': 'hist', 'sim': hist_sim(h1, h2)})
        elif args.method == 'clip':
            if not _ClipBackend.available():
                print('clip 不可用 (需 torch + open_clip)')
                return 2
            _ClipBackend.load()
            a = _ClipBackend.embed_image(args.a)
            b = _ClipBackend.embed_image(args.b)
            _print_json({'method': 'clip', 'sim': _ClipBackend.cos_sim(a, b)})
        return 0

    if args.cmd == 'search':
        vs = VisualSearch(method=args.method)
        r = vs.search(args.image, limit=args.limit,
                       platforms=args.platforms,
                       text_hint=args.text_hint,
                       candidate_pool=args.pool)
        _print_json(r)
        return 0 if r.get('candidates') else 1

    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(_cli())
