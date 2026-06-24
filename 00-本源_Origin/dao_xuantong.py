#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_xuantong.py — 第十五妙门 · 同 (XuanTong)
═══════════════════════════════════════════════════════════════
玄同接入桥 · 3D建模Agent ↔ 玄同协议(去中心化多 peer 协作底层)

「塞其闷, 闭其门, 和其光, 同其尘, 挫其锐而解其纷, 是谓玄同.」 ——五十六章
「道恒无名. 侯王若能守之, 万物将自宾.」 ——三十二章

本桥使 3D建模Agent 不再为一独岛, 而为玄同诸 peer 之一.
共享 graph.db (位于 多模型协作/玄同/graph.db), 守同一 intent
"逆向所有3d建模软件", 自然汇通于 IR 之朴.

用法 (库):
    from dao_xuantong import XuanTongPeer
    p = XuanTongPeer.bootstrap(
        peer_id='3d-modeling-agent',
        fingerprint={'preferred_tags': ['3d-modeling', 'ole', 'parametric']},
    )

    # 七原子动作 (玄同协议)
    p.status()                          # 全局态
    leaf = p.next_leaf()                # 下一只 leaf
    p.claim(leaf['id'])                 # 取
    p.finding(leaf['id'], data={...}, phase='done', evidence=[...])
    p.witness(fid, 'confirm', note='...')
    p.observe(target_finding_id=fid, perspective='...', insight='...')
    p.mirror(source_finding_id=fid, my_view={...}, transformations=[...])

    # 高级 (3d 专属)
    p.auto_finding('SolidWorks', report_md='SW_MASTER_REPORT.md',
                   target_version='2023 SP5')
    p.spawn_horizontal_ir('参数树 IR', source_findings=[f1, f2, f3])

CLI:
    python dao_xuantong.py status
    python dao_xuantong.py next
    python dao_xuantong.py claim <leaf_id>
    python dao_xuantong.py finding-sw  # 用 SW_MASTER_REPORT 自动产 SolidWorks finding
    python dao_xuantong.py loop --iterations 5
"""
from __future__ import annotations

import os
import sys
import json
import time
import hashlib
from pathlib import Path
from typing import Optional, Any

# ═══════════════════════════════════════════════════════════════
# § 1 · 路径自动定位 — 沿祖上找 多模型协作/玄同/peer.py
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).resolve().parent

def _locate_xuantong() -> Optional[Path]:
    """沿祖上目录搜索 多模型协作/玄同/peer.py · 找到则返其目录."""
    cur = SCRIPT_DIR
    for _ in range(8):
        cand = cur / '多模型协作' / '玄同' / 'peer.py'
        if cand.is_file():
            return cand.parent
        cur = cur.parent
        if cur == cur.parent:
            break
    # 兜底: 用绝对工作区路径
    fallback = Path(r'e:\道\道生一\一生二\多模型协作\玄同')
    if (fallback / 'peer.py').is_file():
        return fallback
    return None

XUANTONG_DIR = _locate_xuantong()
if XUANTONG_DIR is None:
    raise RuntimeError(
        '玄同协议未找到. 应在 多模型协作/玄同/peer.py. '
        f'已搜: {SCRIPT_DIR.parents}'
    )

# 注入玄同到 sys.path · 不污染本目录
if str(XUANTONG_DIR) not in sys.path:
    sys.path.insert(0, str(XUANTONG_DIR))

# 导入玄同核心
import peer as _xt_peer_mod  # noqa: E402

# ═══════════════════════════════════════════════════════════════
# § 2 · XuanTongPeer · 3D建模Agent 之玄同身
# ═══════════════════════════════════════════════════════════════

# 默认偏好指纹 — 3D 建模专属
DEFAULT_FINGERPRINT = {
    'preferred_tags': [
        '3d-modeling', 'parametric', 'b-rep', 'mesh',
        'ole', 'com', 'opensource', 'reverse',
    ],
}

# 默认 intent — 此 peer 守的"一"
DEFAULT_INTENT = '逆向所有3d建模软件'


# ═══════════════════════════════════════════════════════════════
# § 1.5 · 不在此处编 mock 软件配方
# ═══════════════════════════════════════════════════════════════
#
# 反者道之动: 此桥不替诸 peer 言.
# 每个软件 leaf 的逆向知识应由真 peer (swe-1.5 / claude / gpt-5 等)
# 通过 cascade_peer · autonomy_loop 自治产 finding,
# 以其各自之偏好指纹自然分宾.
#
# 「道恒无名. 侯王若能守之, 万物将自宾.
#  天地相合, 以降甘露, 民莫之令而自均焉.」 ——三十二章
#
# 此处仅留 SolidWorks finding (基于本 Agent 已有 SW_MASTER_REPORT.md
# + dao_solidworks.py 287KB 真源码 + 真机 18/18 实证), 算 Cascade-as-peer
# 之自然 finding. 余 13 软件留待真 peer 来.

_LEGACY_RECIPES_REMOVED = True  # 历史标识: v1 曾有 13 mock 配方, 已退

# 占位以维持模块结构
_SOFTWARE_RECIPES_DELETED: dict = {}
# (已退 13 mock 软件配方 · 本 Agent 不替天下言 · 留待真 peer 自然产 finding)


class XuanTongPeer:
    """
    3D建模Agent 之玄同身.

    封装 玄同 Peer · 加 3d 专属高级方法.
    底层全权委托 玄同协议 (peer.py) · 此处不立第二个 db, 不立第二个 bus.
    """

    def __init__(self, inner: _xt_peer_mod.Peer, intent_id: Optional[str] = None):
        self._inner = inner
        self.intent_id = intent_id or DEFAULT_INTENT

    # ─── 工厂 ─────────────────────────────────────────────

    @classmethod
    def bootstrap(cls,
                  peer_id: Optional[str] = None,
                  kind: str = '3d-modeling-agent',
                  fingerprint: Optional[dict] = None,
                  intent_id: Optional[str] = None,
                  capabilities: Optional[dict] = None) -> 'XuanTongPeer':
        """启动 peer · 自动 ensure graph.db · 自动注册 self."""
        # 确保 graph.db 已 init
        if not _xt_peer_mod.DB_PATH.exists():
            _xt_peer_mod.init_db()

        peer_id = peer_id or f'3d-agent-{os.getpid()}'
        fingerprint = fingerprint or dict(DEFAULT_FINGERPRINT)
        capabilities = capabilities or {
            'mfg/3d': True,
            'engines': ['OCP', 'FreeCAD', 'CadQuery', 'build123d',
                        'OpenSCAD', 'SolidWorks-COM', 'trimesh'],
            'reverse_methods': ['OLE2', 'COM', 'XML', 'BREP', 'STEP', 'ASAR'],
            'languages': ['python', 'cpp-binding', 'vba'],
        }

        inner = _xt_peer_mod.Peer.bootstrap(
            peer_id=peer_id,
            kind=kind,
            transport='direct',
            fingerprint=fingerprint,
            capabilities=capabilities,
        )
        return cls(inner, intent_id=intent_id)

    # ─── 七原子代理 ───────────────────────────────────────

    def status(self) -> dict:
        return self._inner.status()

    def next_leaf(self, intent_id: Optional[str] = None) -> Optional[dict]:
        iid = intent_id or self.intent_id
        return self._inner.next_open_leaf(intent_id=iid)

    def claim(self, leaf_id: str, note: str = '') -> bool:
        return bool(self._inner.claim(leaf_id, note=note))

    def finding(self, leaf_id: str, data: dict, phase: str = 'done',
                evidence: Optional[list] = None,
                note: str = '') -> Optional[str]:
        return self._inner.finding(
            leaf_id=leaf_id, data=data, phase=phase,
            evidence=evidence or [], note=note,
        )

    def witness(self, finding_id: str, verdict: str = 'confirm',
                note: str = '', extension_data: Optional[dict] = None) -> Optional[str]:
        return self._inner.witness(
            finding_id=finding_id, verdict=verdict,
            note=note, extension_data=extension_data,
        )

    def observe(self, perspective: str,
                target_peer_id: Optional[str] = None,
                target_finding_id: Optional[str] = None,
                target_leaf_id: Optional[str] = None,
                insight: str = '') -> Optional[str]:
        # 玄同 v1.1+ 才有 observe; 优雅降级
        if hasattr(self._inner, 'observe'):
            return self._inner.observe(
                perspective=perspective,
                target_peer_id=target_peer_id,
                target_finding_id=target_finding_id,
                target_leaf_id=target_leaf_id,
                insight=insight,
            )
        return None

    def mirror(self, source_finding_id: str, my_view: dict,
               transformations: Optional[list] = None,
               new_evidence: Optional[list] = None) -> Optional[str]:
        if hasattr(self._inner, 'mirror'):
            return self._inner.mirror(
                source_finding_id=source_finding_id,
                my_view=my_view,
                transformations=transformations or [],
                new_evidence=new_evidence or [],
            )
        return None

    # ─── 3D 建模专属高级方法 ──────────────────────────────

    def find_software_leaf(self, software_name: str,
                           intent_id: Optional[str] = None) -> Optional[dict]:
        """
        按软件名找对应 leaf · 多级回退:
          ① 精确 title=name
          ② 软件 leaf (无路径符 / \\ .) 中包含 name
          ③ 任意 LIKE %name%
        优先 status=open 之上.
        """
        iid = intent_id or self.intent_id
        with _xt_peer_mod._db(readonly=True) as conn:
            # ① 精确匹配
            rows = conn.execute(
                'SELECT id, title, tags, status FROM leaf '
                'WHERE intent_id=? AND title=? ORDER BY status="open" DESC',
                (iid, software_name),
            ).fetchall()
            if rows:
                return dict(rows[0])
            # ② 软件级 (排除 / \ . _ 路径式)
            rows = conn.execute(
                'SELECT id, title, tags, status FROM leaf '
                'WHERE intent_id=? AND title LIKE ? '
                "  AND title NOT LIKE '%/%' "
                "  AND title NOT LIKE '%\\%' "
                "  AND title NOT LIKE '%.%' "
                'ORDER BY status="open" DESC, length(title) ASC',
                (iid, f'%{software_name}%'),
            ).fetchall()
            if rows:
                return dict(rows[0])
            # ③ 全模糊
            rows = conn.execute(
                'SELECT id, title, tags, status FROM leaf '
                'WHERE intent_id=? AND title LIKE ? '
                'ORDER BY status="open" DESC, length(title) ASC',
                (iid, f'%{software_name}%'),
            ).fetchall()
        if not rows:
            return None
        return dict(rows[0])

    @staticmethod
    def _hash_file(path: Path, alg: str = 'sha256') -> str:
        """计算文件 hash · 用作 finding evidence."""
        h = hashlib.new(alg)
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return f'{alg}:{h.hexdigest()[:16]}'

    def auto_finding(self,
                     software_name: str,
                     target_version: str,
                     method: str,
                     outcome: str,
                     evidence_paths: Optional[list] = None,
                     report_md_path: Optional[str] = None,
                     phase: str = 'done',
                     extra_data: Optional[dict] = None,
                     auto_claim: bool = True,
                     intent_id: Optional[str] = None) -> dict:
        """
        高级: 自动产生结构化 finding 并提交到玄同.

        参数:
          software_name      : 软件名 (如 'SolidWorks')
          target_version     : 版本
          method             : 方法概述
          outcome            : 一句话结论
          evidence_paths     : 文件证据列表 (相对/绝对路径)
          report_md_path     : 主报告 markdown 路径 (会自动 hash)
          phase              : 'start'/'progress'/'done' (默 'done')
          extra_data         : 额外 data 字段
          auto_claim         : 若 leaf 未 claim, 自动 claim (默 True)
          intent_id          : 指定 intent (默 self.intent_id)

        返回:
          {
            'ok': bool,
            'leaf_id': ..,
            'finding_id': ..,
            'message': ..,
          }
        """
        leaf = self.find_software_leaf(software_name, intent_id=intent_id)
        if leaf is None:
            return {'ok': False, 'message': f'leaf for {software_name!r} not found',
                    'leaf_id': None, 'finding_id': None}

        # 自动 claim (若尚 open)
        if auto_claim and leaf.get('status') == 'open':
            self.claim(leaf['id'], note=f'auto_finding: {software_name}')

        # 收集 evidence
        ev = []
        for p in (evidence_paths or []):
            pp = Path(p) if Path(p).is_absolute() else SCRIPT_DIR.parent / p
            if pp.is_file():
                ev.append(f'{pp} ({self._hash_file(pp)})')
            else:
                ev.append(str(p))
        if report_md_path:
            mp = Path(report_md_path) if Path(report_md_path).is_absolute() \
                 else SCRIPT_DIR.parent / report_md_path
            if mp.is_file():
                ev.append(f'{mp} ({self._hash_file(mp)})')
            else:
                ev.append(str(report_md_path))

        # 结构化 data
        data = {
            'target': software_name,
            'target_version': target_version,
            'method': method,
            'outcome': outcome,
            'kind': '3d-modeling-software',
            'reverse_layer': '3D建模Agent/00-本源_Origin',
        }
        if extra_data:
            data.update(extra_data)

        fid = self.finding(
            leaf_id=leaf['id'], data=data, phase=phase,
            evidence=ev,
            note=f'auto_finding from XuanTongPeer for {software_name}',
        )
        return {
            'ok': bool(fid),
            'leaf_id': leaf['id'],
            'finding_id': fid,
            'message': f'finding {fid} on leaf {leaf["id"][:8]}({leaf["title"]})',
        }

    def spawn_horizontal_ir(self,
                            ir_name: str,
                            source_findings: list,
                            essence: str,
                            invariants: list,
                            new_evidence: Optional[list] = None) -> dict:
        """
        高级: 从多个软件 finding 中 mirror 出横向 IR.

        即 玄同协议中"齐物·镜"原子之 3D 专用版.
        """
        ir_leaf = self.find_software_leaf(ir_name)
        if not ir_leaf:
            return {'ok': False, 'message': f'IR leaf {ir_name!r} not found'}

        results = []
        for source_fid in source_findings:
            mirror_id = self.mirror(
                source_finding_id=source_fid,
                my_view={
                    'essence_distilled': essence,
                    'core_invariants': invariants,
                    'horizontal_target': ir_name,
                    'horizontal_leaf_id': ir_leaf['id'],
                },
                transformations=['具体软件→横向 IR'],
                new_evidence=new_evidence or [],
            )
            results.append({'source': source_fid, 'mirror_id': mirror_id})
        return {
            'ok': all(r['mirror_id'] for r in results),
            'ir_leaf_id': ir_leaf['id'],
            'mirrors': results,
            'message': f'spawned {len(results)} mirrors → {ir_name}',
        }


# ═══════════════════════════════════════════════════════════════
# § 3 · CLI
# ═══════════════════════════════════════════════════════════════

def _cli():
    import argparse

    parser = argparse.ArgumentParser(description='dao_xuantong · 玄同接入桥 CLI')
    parser.add_argument('--peer-id', default=None)
    parser.add_argument('--intent', default=DEFAULT_INTENT)
    sub = parser.add_subparsers(dest='cmd')

    sub.add_parser('status')
    sub.add_parser('next')
    sub.add_parser('finding-sw',
                   help='以 SW_MASTER_REPORT.md 为 evidence 产 SolidWorks finding '
                        '(本 Agent 自身真材料 · 非 mock)')
    sub.add_parser('dispute-self',
                   help='对本 peer 历史薄 finding 自 dispute · 留待真 peer 重同')

    p_claim = sub.add_parser('claim')
    p_claim.add_argument('leaf_id')
    p_claim.add_argument('--note', default='')

    p_loop = sub.add_parser('loop',
                            help='让多 cascade peer 自治推进 leaves (依赖 cascade_peer)')
    p_loop.add_argument('--iterations', type=int, default=3)
    p_loop.add_argument('--peers', type=int, default=2)
    p_loop.add_argument('--models', default='swe-1.5,claude-4.5-sonnet')

    args = parser.parse_args()

    p = XuanTongPeer.bootstrap(peer_id=args.peer_id, intent_id=args.intent)

    if args.cmd == 'status':
        s = p.status()
        for k, v in s.items():
            print(f'  {k:24s} = {v}')
        return

    if args.cmd == 'next':
        leaf = p.next_leaf()
        print(json.dumps(leaf, indent=2, ensure_ascii=False) if leaf else '(none)')
        return

    if args.cmd == 'claim':
        ok = p.claim(args.leaf_id, note=args.note)
        print('ok' if ok else 'failed')
        return

    if args.cmd == 'dispute-self':
        # 玄同协议: peer 不能 witness 自己 finding (除 extend) · 此乃公正之保障.
        # 故采"重开"修复路: leaf 状态 → 'open', 留待真 peer 重新评估.
        # 原 finding 仍 append-only 留在 db 中, 作历史反思证据.
        peer_id = p._inner.id
        import sqlite3 as _sq
        conn = _sq.connect(str(_xt_peer_mod.DB_PATH))
        try:
            cur = conn.cursor()
            # 取出 mark-files-done 产物所对应 leaves
            cur.execute(
                "SELECT DISTINCT leaf_id FROM finding WHERE peer_id=? "
                "  AND (data LIKE '%existing-material%' "
                "       OR leaf_id='522a519b7898d1a9')",
                (peer_id,),
            )
            leaf_ids = [r[0] for r in cur.fetchall()]
            print(f'拟重开 {len(leaf_ids)} 个被 mark-files-done 强 done 之 leaf...')
            n = 0
            for lid in leaf_ids:
                cur.execute(
                    "UPDATE leaf SET status='open' WHERE id=? AND status='done'",
                    (lid,),
                )
                n += cur.rowcount
            # 同时清相关 claim
            cur.execute(
                "DELETE FROM claim WHERE peer_id=? "
                "  AND leaf_id IN (SELECT DISTINCT leaf_id FROM finding "
                "                  WHERE peer_id=? AND data LIKE '%existing-material%')",
                (peer_id, peer_id),
            )
            n_claim = cur.rowcount
            conn.commit()
            print(f'  ✓ {n} leaf 重开 · {n_claim} claim 清除')
            print('  ─ 「反者道之动」原 finding 留 append-only · 作 Cascade 之自悟证')
        finally:
            conn.close()
        return

    if args.cmd == 'finding-sw':
        report = SCRIPT_DIR / 'SW_MASTER_REPORT.md'
        if not report.is_file():
            print(f'缺 SW_MASTER_REPORT.md: {report}')
            sys.exit(1)
        result = p.auto_finding(
            software_name='SolidWorks',
            target_version='2023 SP5 (revision 31.0.1)',
            method=(
                'L0-L12 全境逆向: OLE2 + COM + DocMgr + PE + Reg + 几何反演'
                ' + Parasolid XT + 活体 L11 + L9 一键激活 + L12 道直连器'
                ' (memid 直调 sldworks.tlb 710 接口/14916 methods/4262 properties)'
            ),
            outcome=(
                '已实证: 真机活体 18/18 全绿 + L12 锤式破碎机 12/12 (28 组件, 255.5kg) '
                '+ Quark bridge 8/8 + forge_v3 50 SW 命令 · '
                '可读 SLDPRT/SLDASM/SLDDRW · 可写 part/asm/drawing/macro · '
                '可激活 + 可几何反演到 Parasolid XT · 100% 反演链路通'
            ),
            evidence_paths=[
                '00-本源_Origin/dao_solidworks.py',
                '00-本源_Origin/dao_sw_live.py',
                '00-本源_Origin/dao_sw_omni.py',
                '00-本源_Origin/道_直连_底层.py',
                '00-本源_Origin/道_直连_底层_facets.py',
                '00-本源_Origin/dao_quark_bridge.py',
            ],
            report_md_path='00-本源_Origin/SW_MASTER_REPORT.md',
            extra_data={
                'reverse_levels': ['L0', 'L0.5', 'L1', 'L1.5', 'L2', 'L2.5', 'L3',
                                   'L4', 'L5', 'L6', 'L7', 'L8', 'L9', 'L11', 'L12'],
                'apis_exposed': 14916,
                'props_exposed': 4262,
                'tlb': 'sldworks.tlb (710 interfaces)',
                'horizontal_lessons': [
                    '同 OLE2 法外推 → Inventor / Catia / NX',
                    '同 COM 自动化 → MS Office / AutoCAD',
                    '同 memid 直调 → 任何 IDispatch 暴露的桌面软件',
                    '同 Parasolid XT → NX (亲生) / SolidEdge / IronCAD',
                ],
            },
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.cmd == 'loop':
        # 委托 cascade_peer 多 peer 循环
        try:
            from autonomy_loop import LoopOrchestrator
        except ImportError:
            print('autonomy_loop 不可用 · 需 玄同 v1.1+')
            sys.exit(2)

        models = [m.strip() for m in args.models.split(',') if m.strip()]
        configs = []
        for i, m in enumerate(models[:args.peers]):
            configs.append({'model': m, 'fingerprint': dict(DEFAULT_FINGERPRINT)})
        orch = LoopOrchestrator(configs=configs)
        orch.run(iterations=args.iterations)
        return

    parser.print_help()


if __name__ == '__main__':
    _cli()
