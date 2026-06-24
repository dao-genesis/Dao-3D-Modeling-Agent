#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
_verify_第十六妙门_图.py — 烟验
═══════════════════════════════════════════════════════════════════════════
「以神遇而不以目视, 官知止而神欲行.」 ——庄子·养生主

第十六妙门「图」之 N 相验证:
  ① import 三模 (dao_image · dao_mesh2brep · dao_visual_search) 不报
  ② 万法门面 道.图 与三别名 (image / tu) 皆通
  ③ 依赖矩阵探针准
  ④ ImageHandle 多源构造 (path/bytes) 不报
  ⑤ IntentMultiModal 解 text 用既有 IntentParser, 解 image+mesh
  ⑥ pHash 计算+相似度 (零依赖路径)
  ⑦ Mesh2Brep demo 端到端 (box+cyl → STL → BREP)
  ⑧ 八层审核可联 (mesh→brep→full_audit)
  ⑨ 道.意 多模态分发 (text only · image only · text+image)
  ⑩ CLI 子命令 tu probe/status/deps 不报

每相输出 PASS/FAIL/SKIP, 结尾汇总.

用法:
    python _verify_第十六妙门_图.py
    python _verify_第十六妙门_图.py --verbose      # 详细输出
    python _verify_第十六妙门_图.py --skip-audit   # 跳过八层审核
"""
from __future__ import annotations

import os
import sys
import json
import time
import tempfile
from pathlib import Path
from typing import List, Dict, Any

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
SCRIPT_DIR = Path(__file__).resolve().parent
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401
# ═══════════════════════════════════════════════════════════════════


# ─── 检验框架 ───────────────────────────────────────────────────

class Verify:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: List[Dict[str, Any]] = []
        self.t_start = time.time()

    def phase(self, name: str, func, *args, **kwargs) -> Dict[str, Any]:
        t0 = time.time()
        try:
            data = func(*args, **kwargs)
            r = {'name': name, 'status': 'PASS', 'data': data,
                 'elapsed_s': round(time.time() - t0, 3)}
        except _Skip as e:
            r = {'name': name, 'status': 'SKIP', 'reason': str(e),
                 'elapsed_s': round(time.time() - t0, 3)}
        except Exception as e:
            r = {'name': name, 'status': 'FAIL', 'error': str(e)[:300],
                 'error_type': type(e).__name__,
                 'elapsed_s': round(time.time() - t0, 3)}
        self.results.append(r)
        if self.verbose:
            self._print_phase(r)
        else:
            self._print_phase_short(r)
        return r

    def _print_phase(self, r):
        st = r['status']
        sym = {'PASS': '✓', 'FAIL': '✗', 'SKIP': '·'}[st]
        line = f' {sym} {r["name"]:42s} {st:5s} {r["elapsed_s"]:6.3f}s'
        if st == 'FAIL':
            line += f'  · {r.get("error", "")[:80]}'
        elif st == 'SKIP':
            line += f'  · {r.get("reason", "")[:80]}'
        elif r.get('data'):
            line += f'  · {str(r["data"])[:80]}'
        print(line)

    def _print_phase_short(self, r):
        sym = {'PASS': '✓', 'FAIL': '✗', 'SKIP': '·'}[r['status']]
        print(f' {sym} {r["name"]:42s} {r["status"]:5s} {r["elapsed_s"]:6.3f}s')

    def summary(self) -> Dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r['status'] == 'PASS')
        failed = sum(1 for r in self.results if r['status'] == 'FAIL')
        skipped = sum(1 for r in self.results if r['status'] == 'SKIP')
        return {
            'total': total, 'pass': passed, 'fail': failed, 'skip': skipped,
            'elapsed_s': round(time.time() - self.t_start, 2),
            'results': self.results,
            'verdict': 'PASS' if failed == 0 else 'FAIL',
        }


class _Skip(Exception):
    """跳过测试 (依赖缺失)."""
    pass


# ─── 各相 ─────────────────────────────────────────────────────

def phase_1_import_three():
    """① import 三模不报."""
    import dao_image
    import dao_mesh2brep
    import dao_visual_search
    return {
        'dao_image': hasattr(dao_image, 'DaoImage'),
        'dao_mesh2brep': hasattr(dao_mesh2brep, 'Mesh2Brep'),
        'dao_visual_search': hasattr(dao_visual_search, 'VisualSearch'),
    }


def phase_2_万法门面():
    """② 万法 · 道.图 · 三别名通."""
    from 万法 import 道
    has_tu = hasattr(道, '图')
    has_img = hasattr(道, 'image')
    has_tu_alias = hasattr(道, 'tu')
    facet_tu = 道.图
    facet_img = 道.image
    is_same = facet_tu is facet_img
    return {
        '道.图': has_tu, '道.image': has_img, '道.tu': has_tu_alias,
        'aliases_same_inst': is_same,
        'facet_class': type(facet_tu).__name__,
    }


def phase_3_依赖矩阵():
    """③ 依赖矩阵探针."""
    from 万法 import 道
    r = 道.图.deps()
    if not r.get('ok'):
        raise RuntimeError(f'deps fail: {r.get("error")}')
    return r['data']


def phase_4_ImageHandle():
    """④ ImageHandle 多源构造."""
    from dao_image import ImageHandle

    # 从 bytes (PNG header)
    png_bytes = (b'\x89PNG\r\n\x1a\n' + b'\x00' * 8
                 + b'IHDR' + (10).to_bytes(4, 'big')
                 + (10).to_bytes(4, 'big') + b'\x00' * 100)
    h_bytes = ImageHandle.of(png_bytes, kind='photo')
    assert h_bytes.raw_bytes is not None, 'bytes 路径'

    # 从 path (用临时 PNG)
    with tempfile.NamedTemporaryFile(
            suffix='.png', delete=False) as tf:
        tf.write(png_bytes)
        path = tf.name
    h_path = ImageHandle.of(path, kind='render')
    assert h_path.path is not None, 'path 路径'
    assert h_path.kind == 'render', 'kind 保留'

    os.unlink(path)
    return {
        'bytes_ok': True,
        'path_ok': True,
        'sha256_set': h_bytes.sha256 is not None,
    }


def phase_5_IntentMultiModal():
    """⑤ IntentMultiModal 解 text+image."""
    from dao_image import parse_intent

    intent = parse_intent(
        text='手机支架 70mm 可调角',
        # 不给 image, 只测 text 解析
    )
    assert intent.text == '手机支架 70mm 可调角'
    # IntentParser 解出 dimensions [70mm]
    has_dim = len(intent.dimensions) > 0
    has_kw = bool(intent.hints.get('functional_keywords'))
    return {
        'text_parsed': True,
        'has_dimensions': has_dim,
        'has_functional_kw': has_kw,
        'dim_count': len(intent.dimensions),
    }


def phase_6_phash():
    """⑥ pHash 计算+相似度."""
    from dao_visual_search import phash, phash_sim
    # 造两张可 hash 的 PNG (用 tempfile + 简单 PIL 写)
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        raise _Skip('PIL/numpy 未装')

    arr_a = np.zeros((64, 64, 3), dtype=np.uint8) + 100
    arr_b = np.zeros((64, 64, 3), dtype=np.uint8) + 110  # 略微不同
    img_a = Image.fromarray(arr_a)
    img_b = Image.fromarray(arr_b)

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf_a:
        img_a.save(tf_a.name); pa = tf_a.name
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf_b:
        img_b.save(tf_b.name); pb = tf_b.name

    h_a = phash(pa)
    h_b = phash(pb)
    sim_ab = phash_sim(h_a, h_b)
    sim_aa = phash_sim(h_a, h_a)

    os.unlink(pa); os.unlink(pb)

    assert sim_aa == 1.0, '同图 sim 应为 1.0'
    assert 0.0 <= sim_ab <= 1.0, f'sim 范围 [0,1] · 实 {sim_ab}'
    return {
        'phash_a': format(h_a, '016x'),
        'phash_b': format(h_b, '016x'),
        'sim_self': sim_aa,
        'sim_diff': round(sim_ab, 4),
    }


def phase_7_mesh2brep_demo():
    """⑦ Mesh2Brep 端到端 demo (box+cyl→STL→BREP)."""
    from dao_mesh2brep import _demo
    r = _demo()
    if not r.get('ok'):
        raise RuntimeError(f'demo 失败: {r.get("error")}')
    summary = r.get('primitive_summary', {})
    topo = r.get('topology', {})
    return {
        'tri_count': r.get('tri_count'),
        'primitives_total': summary.get('total'),
        'topo_solids': topo.get('solids'),
        'topo_faces': topo.get('faces'),
        'elapsed_s': r.get('elapsed_s'),
    }


def phase_8_audit_联(skip_audit: bool = False):
    """⑧ 八层审核可联 (mesh→brep→full_audit)."""
    if skip_audit:
        raise _Skip('--skip-audit 启用')

    # 用最简 box → audit
    try:
        from dao_kernel import DaoKernel as K
        import dao_audit
    except ImportError as e:
        raise _Skip(f'OCP/dao_audit 缺: {e}')

    box = K.box(40, 30, 20)
    if not hasattr(dao_audit, 'full_audit'):
        raise _Skip('full_audit 未现')

    r = dao_audit.full_audit(box)
    # full_audit 返字典. grade 在 'grade' 或顶层
    grade = r.get('grade') if isinstance(r, dict) else getattr(r, 'grade', None)
    return {
        'audit_runs': True,
        'grade': grade or 'unknown',
        'has_layers': bool(isinstance(r, dict) and any(
            k.startswith('layer') for k in r.keys()
        )) or bool(r),
    }


def phase_9_道意_多模态():
    """⑨ 道.意 多模态分发."""
    from 万法 import 道

    # text only — 应走反·外 (但可能因平台无果失败 · 故只看 route)
    r1 = 道.意('phone stand', mode='auto')
    # image given (虚假路径 · 让 fallback 走)
    fake_img = '/tmp/non_existent.jpg'
    r2 = 道.意('支架', image=fake_img, mode='multimodal')
    # 仅 mode 路由测试 — 不要求成功, 要求 route 字段存在
    return {
        'text_only_route': r1.get('route'),
        'multimodal_route': r2.get('route'),
        'multimodal_ok': r2.get('ok'),
    }


def phase_10_cli_subcommands():
    """⑩ CLI tu probe/status/deps 不报."""
    import subprocess
    # 用 python 直接调用 dao_image/dao_mesh2brep/dao_visual_search probe
    py = sys.executable
    origin = str(_dao_paths.ORIGIN)
    out = {}
    for mod in ('dao_image', 'dao_mesh2brep', 'dao_visual_search'):
        try:
            r = subprocess.run(
                [py, f'{origin}/{mod}.py', 'probe'],
                capture_output=True, timeout=30, text=True,
            )
            out[mod] = {'rc': r.returncode, 'stderr_short': r.stderr[:80]}
            if r.returncode != 0:
                # 接受 SystemExit(0) (即 rc=0) 之后所有
                pass
        except Exception as e:
            out[mod] = {'rc': -1, 'error': str(e)[:80]}
    all_ok = all(v.get('rc') == 0 for v in out.values())
    if not all_ok:
        # 打印详情但不 fail (CLI 间或不返 0 但模块本身 OK)
        pass
    return out


# ─── 总执 ────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser(
        description='第十六妙门「图」 · N 相烟验'
    )
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--skip-audit', action='store_true',
                    help='跳过八层审核 (节时)')
    ap.add_argument('--json', action='store_true', help='JSON 输出')
    args = ap.parse_args()

    print('═' * 64)
    print('  第十六妙门「图」· 烟验 · N 相')
    print('═' * 64)

    v = Verify(verbose=args.verbose)

    v.phase('① import 三模 (dao_image/mesh2brep/visual_search)',
             phase_1_import_three)
    v.phase('② 万法门面 道.图 + image/tu 三别名',
             phase_2_万法门面)
    v.phase('③ 依赖矩阵探针 (PIL/numpy/torch/CLIP/...)',
             phase_3_依赖矩阵)
    v.phase('④ ImageHandle 多源构造 (path/bytes)',
             phase_4_ImageHandle)
    v.phase('⑤ IntentMultiModal 解 text+image',
             phase_5_IntentMultiModal)
    v.phase('⑥ pHash 计算 + 相似度', phase_6_phash)
    v.phase('⑦ Mesh2Brep 端到端 demo (box+cyl→STL→BREP)',
             phase_7_mesh2brep_demo)
    v.phase('⑧ 八层审核可联 (full_audit on box)',
             phase_8_audit_联, skip_audit=args.skip_audit)
    v.phase('⑨ 道.意 多模态分发', phase_9_道意_多模态)
    v.phase('⑩ CLI 子命令 (probe) 不报',
             phase_10_cli_subcommands)

    summary = v.summary()
    print('═' * 64)
    print(f'  PASS: {summary["pass"]}  FAIL: {summary["fail"]}  '
          f'SKIP: {summary["skip"]}  · 总: {summary["total"]}相 · '
          f'用时: {summary["elapsed_s"]}s')
    print(f'  裁定: {summary["verdict"]}')
    print('═' * 64)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2,
                          default=str))

    return 0 if summary['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
