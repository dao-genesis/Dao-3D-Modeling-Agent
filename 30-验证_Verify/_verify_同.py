#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_verify_同.py — 第十五妙门「同」之验
═══════════════════════════════════════════════════════════════
玄同接入桥之最小验证 · 不依赖外部, 不修改 graph.db.
"""
import sys
from pathlib import Path

# 路径引导
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), None)
if _DAO_ROOT:
    sys.path.insert(0, str(_DAO_ROOT))


def main():
    n_pass = 0
    n_fail = 0
    print('=' * 64)
    print(' 第十五妙门「同」 · 自验')
    print('=' * 64)

    # 1. 万法 import
    print('\n[1] 万法 import')
    try:
        from 万法 import 道, Res
        print(f'  ✓ ok · {道!r}')
        n_pass += 1
    except Exception as e:
        print(f'  ✗ {e}')
        n_fail += 1
        return n_pass, n_fail

    # 2. dao_xuantong import
    print('\n[2] dao_xuantong import')
    try:
        from dao_xuantong import XuanTongPeer, DEFAULT_INTENT
        print(f'  ✓ ok · DEFAULT_INTENT={DEFAULT_INTENT}')
        n_pass += 1
    except Exception as e:
        print(f'  ✗ {e}')
        n_fail += 1

    # 3. 道.同 facet 可访问
    print('\n[3] 道.同 facet')
    try:
        f = 道.同
        assert f is not None
        print(f'  ✓ ok · {type(f).__name__}')
        n_pass += 1
    except Exception as e:
        print(f'  ✗ {e}')
        n_fail += 1

    # 4. 道.同.status 可调
    print('\n[4] 道.同.status (只读)')
    try:
        r = 道.同.status()
        if r.ok:
            d = r.data
            print(f'  ✓ ok · open={d["leaves_open"]} '
                  f'claimed={d["leaves_claimed"]} done={d["leaves_done"]}')
            print(f'      findings={d["total_findings"]} '
                  f'witnesses={d["total_witnesses"]}')
            n_pass += 1
        else:
            print(f'  ✗ {r.error}')
            n_fail += 1
    except Exception as e:
        print(f'  ✗ {e}')
        n_fail += 1

    # 5. 道.同.next_leaf 可调
    print('\n[5] 道.同.next_leaf (只读)')
    try:
        r = 道.同.next_leaf()
        if r.ok:
            if r.data:
                print(f'  ✓ ok · 下一只 leaf: [{r.data["id"][:8]}] {r.data["title"]}')
            else:
                print('  ✓ ok · 无 open leaf (此 intent 已尽)')
            n_pass += 1
        else:
            print(f'  ✗ {r.error}')
            n_fail += 1
    except Exception as e:
        print(f'  ✗ {e}')
        n_fail += 1

    # 6. 道 别名链 (xuantong / peer)
    print('\n[6] 道.xuantong / 道.peer 别名链')
    try:
        assert 道.同 is 道.xuantong
        assert 道.同 is 道.peer
        print('  ✓ ok · 道.同 ≡ 道.xuantong ≡ 道.peer')
        n_pass += 1
    except Exception as e:
        print(f'  ✗ {e}')
        n_fail += 1

    # 7. 道.summary 包含 xuantong
    print('\n[7] 道.summary() 含 xuantong 节')
    try:
        s = 道.summary()
        assert 'xuantong' in s
        x = s['xuantong']
        if 'error' in x:
            print(f'  ✗ summary 中 xuantong 报错: {x["error"]}')
            n_fail += 1
        else:
            print(f'  ✓ ok · summary[xuantong] keys: {list(x.keys())[:6]}...')
            n_pass += 1
    except Exception as e:
        print(f'  ✗ {e}')
        n_fail += 1

    # 8. SolidWorks 真 finding 存在
    print('\n[8] SolidWorks 真 finding 在 graph.db 中')
    try:
        import sys as _s
        from dao_xuantong import _xt_peer_mod
        with _xt_peer_mod._db(readonly=True) as conn:
            row = conn.execute("""
                SELECT f.id, f.peer_id, f.phase, l.title
                FROM finding f
                JOIN leaf l ON f.leaf_id = l.id
                WHERE l.title='SolidWorks'
                  AND l.intent_id='逆向所有3d建模软件'
                ORDER BY f.created_at DESC LIMIT 1
            """).fetchone()
        if row:
            print(f'  ✓ ok · finding {row[0][:8]} from {row[1]} phase={row[2]}')
            n_pass += 1
        else:
            print('  ✗ 无 SolidWorks 真 finding')
            n_fail += 1
    except Exception as e:
        print(f'  ✗ {e}')
        n_fail += 1

    print()
    print('=' * 64)
    total = n_pass + n_fail
    print(f' {n_pass}/{total} PASS · {n_fail} FAIL')
    print('=' * 64)
    return n_pass, n_fail


if __name__ == '__main__':
    p, f = main()
    sys.exit(0 if f == 0 else 1)
