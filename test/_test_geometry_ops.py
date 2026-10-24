# -*- coding: utf-8 -*-
"""通用几何原语与生产实现（碎三角）的差分测试。

S1 的做法：先把共用件 `engine/geometry_ops.py` 抽出来，用**差分**证明它与
碎三角现有的实现逐项等价，再让加载器去用共用件——不先动生产代码，避免
"重构顺手改坏可玩的盘"。

覆盖：重叠判定（含相切必须算不重叠）、边占用表、共边连通分量、整盘连通。
跑法：``PYTHONPATH=. python -u test/_test_geometry_ops.py``
"""
import os
import random
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from engine import geometry_ops as gops
from engine.analysis import safe_scramble
from engine.registry import make_board
from engine.shatter_geometry import (_block_vertices, _components,
                                     _edge_owner_map, _polygon_at,
                                     _tri_overlap)

_FAILS = []


def check(cond, label, extra=''):
    tag = 'OK  ' if cond else 'FAIL'
    print(f'[{tag}] {label}' + (f'  （{extra}）' if extra else ''))
    if not cond:
        _FAILS.append(label)


def _plane_polys(board):
    return {k: tuple(_polygon_at(*k)) for k in board.keys}


def test_overlap_equivalence():
    print('\n== T1 重叠判定：共用件 ≡ 生产实现 ==')
    b = make_board('shatter')
    polys = _plane_polys(b)
    keys = sorted(polys)
    diff = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, c = polys[keys[i]], polys[keys[j]]
            if gops.convex_overlap(a, c) != _tri_overlap(a, c):
                diff += 1
    check(diff == 0, '还原态 1128 对多边形判定完全一致', f'不一致 {diff} 对')

    # 相切（共边）必须算不重叠——这是"相邻滑块不能判碰撞"的硬约束
    k1 = keys[0]
    adj = [k for k in keys[1:]
           if len(set(_block_vertices(k1)) & set(_block_vertices(k))) >= 2]
    check(bool(adj), '找到与首块共边的邻块', f'{len(adj)} 个')
    if adj:
        a, c = polys[k1], polys[adj[0]]
        check(not gops.convex_overlap(a, c), '共边的两块判为不重叠（相切不算碰撞）')

    # 正面积重叠必须被检出（位移要小于块自身宽度，否则是分离而非重叠）
    moved = tuple((x + 0.05, y + 0.02) for (x, y) in polys[k1])
    check(gops.convex_overlap(polys[k1], moved)
          and _tri_overlap(polys[k1], moved), '微小平移后的自身判为重叠')
    # 平移到完全分离的位置，两边都必须判不重叠（口径一致）
    far = tuple((x + 100.0, y) for (x, y) in polys[k1])
    check(not gops.convex_overlap(polys[k1], far)
          and not _tri_overlap(polys[k1], far), '远距平移判为不重叠')


def test_edge_map_equivalence():
    print('\n== T2 边占用表：共用件 ≡ 生产实现 ==')
    b = make_board('shatter')
    keys = b.keys
    ours = gops.edge_map({k: _block_vertices(k) for k in keys})
    theirs = _edge_owner_map(keys)
    norm = lambda d: {e: sorted(v) for e, v in d.items()}
    check(norm(ours) == norm(theirs), '边表逐边一致', f'{len(ours)} 条边')
    inner = gops.shared_edge_owners({k: _block_vertices(k) for k in keys})
    check(len(inner) == 66, '内部接触边 66 条（78 - 12 条外轮廓）', f'{len(inner)} 条')


def test_components_equivalence():
    print('\n== T3 共边连通：共用件 ≡ 生产实现 ==')
    b = make_board('shatter')
    ours = gops.components(b.keys, _block_vertices)
    theirs = _components(b.keys)
    check(set(ours) == set(theirs), '还原态分量分解一致',
          f'{len(ours)} 个分量')
    check(gops.is_connected(b.keys, _block_vertices), '还原态单一连通')

    board, _p, _u = safe_scramble(b, 1, 5, random.Random(11))
    ours2 = gops.components(board.keys, _block_vertices)
    theirs2 = _components(board.keys)
    check(set(ours2) == set(theirs2), '打乱 5 步后分量分解一致',
          f'{len(ours2)} 个分量')

    # 取两块互不相邻的子集，必须分成两个分量
    keys = sorted(board.keys)
    k0 = keys[0]
    far = next(k for k in keys
               if len(set(_block_vertices(k0)) & set(_block_vertices(k))) < 2)
    two = gops.components({k0, far}, _block_vertices)
    check(len(two) == 2, '两块不相邻 → 两个分量')


if __name__ == '__main__':
    test_overlap_equivalence()
    test_edge_map_equivalence()
    test_components_equivalence()
    print()
    if _FAILS:
        print(f'FAILED ({len(_FAILS)}): ' + '; '.join(_FAILS))
        sys.exit(1)
    print('ALL PASS')
