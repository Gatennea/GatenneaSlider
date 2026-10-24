# -*- coding: utf-8 -*-
"""通用板型（几何引擎）的自由捆绑契约。

背景（2026-10-24 实测定位）：捆绑的语义在引擎里**本来就有**——
块自带组号、``Board.legal_moves`` 走 ``_group_closure`` 且 ``_slide_ok``
逐步校验、存档快照存 groups、通用渲染通道已调 ``_draw_bandaged_groups_poly``。
唯一坏掉的是「批量建局入口按位置索引组号」：带朝向板型同一位置可有多块
（朝向不同），位置不足以标识块 → 传位置永远抛「未知朝向 ''」，
等于**造不出带捆绑的盘**。修法：组的键支持「坐标 + 朝向」，位置口径保留
但歧义时明确报错（不猜）。

跑法：``PYTHONPATH=. python -u test/_test_generic_bandage.py``
"""
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from engine.adapter import create_adapter_puzzle
from engine.compat import _keys_to_positions
from engine.registry import make_board
from engine.shatter_geometry import _polygon_at

_FAILS = []


def check(cond, label, extra=''):
    tag = 'OK  ' if cond else 'FAIL'
    print(f'[{tag}] {label}' + (f'  （{extra}）' if extra else ''))
    if not cond:
        _FAILS.append(label)


def _shared_edge(k1, k2):
    """两块是否共享一条边（≥2 个公共顶点）。"""
    s1 = {tuple(round(c, 6) for c in v) for v in _polygon_at(*k1)}
    s2 = {tuple(round(c, 6) for c in v) for v in _polygon_at(*k2)}
    return len(s1 & s2) >= 2


def _shape_of(key):
    """朝向标签 → 形状（'1'..'6' 为正三角，其余为 30-30-120 等腰）。"""
    from engine.shatter_geometry import _ROLES  # noqa: F401  (存在性即契约)
    o = key[1].lstrip('r')
    return 'eq' if o in ('1', '2', '3', '4', '5', '6') else 'iso'


def _adjacent_same_shape_pairs(spec, keys):
    kl = sorted(keys)
    return [(kl[i], kl[j]) for i in range(len(kl)) for j in range(i + 1, len(kl))
            if _shared_edge(kl[i], kl[j])
            and _shape_of(kl[i]) == _shape_of(kl[j])]


def _live_gaps(adapter, spec):
    return [(f.name, line) for f in spec.seam_families
            for line in range(-60, 61)
            if adapter.is_valid_gap(f.name, line)
            and adapter.is_live_gap(f.name, line)]


def test_build_and_group_closure():
    print('\n== T1 带捆绑的通用盘：能建、能选中整组 ==')
    board = make_board('shatter')
    spec = board.spec
    keys = board.keys
    pairs = _adjacent_same_shape_pairs(spec, keys)
    check(bool(pairs), '碎三角盘面存在同形状相邻对（可拼 60° 菱形）',
          f'{len(pairs)} 对')
    if not pairs:
        return
    k1, k2 = pairs[0]
    flat = _keys_to_positions(frozenset(keys), spec)
    fk1 = (k1[0][0], k1[0][1], k1[1])
    fk2 = (k2[0][0], k2[0][1], k2[1])

    plain = create_adapter_puzzle('shatter', 4, 4, 2)
    baseline = len(plain._board.legal_moves(1))

    g = create_adapter_puzzle('shatter', 4, 4, 2)
    g.apply_pattern(flat, groups={fk1: 1, fk2: 1})
    grouped = sum(1 for b in g.blocks if b.group)
    check(grouped == 2, '按键（坐标 + 朝向）建出 2 块一组的捆绑盘', f'组内 {grouped} 块')

    live = _live_gaps(g, spec)
    check(bool(live), '带捆绑盘上仍有活缝', f'{len(live)} 条')
    if not live:
        return

    blk = next(b for b in g.blocks
               if (b.location[0], b.location[1], b.location[2]) == fk1)
    g.opt(live[0][0], live[0][1], blk)
    opted = {(b.location[0], b.location[1], b.location[2])
             for b in g.blocks if b.be_opted}
    check(fk1 in opted and fk2 in opted,
          '点组内一块 → 两块组员一起被选中（组是刚体）',
          f'选中 {len(opted)} 块')

    after = len(g._board.legal_moves(1))
    check(after != baseline,
          '组闭包已进入合法移动判定（不是只改选中）',
          f'无组 {baseline} → 有组 {after}')


def test_positional_backward_compat():
    print('\n== T2 位置口径向后兼容（方形/三角/米字老调用）==')
    g = create_adapter_puzzle('square', 4, 4, 2)
    g.apply_pattern([[0, 0], [0, 1], [1, 0], [1, 1]],
                    groups={(0, 0): 1, (0, 1): 1})
    check(sum(1 for b in g.blocks if b.group) == 2,
          '方形用位置索引组号仍然生效')


def test_ambiguous_position_rejected():
    print('\n== T3 位置歧义时明确报错（不猜）==')
    board = make_board('shatter')
    spec = board.spec
    keys = board.keys
    flat = _keys_to_positions(frozenset(keys), spec)
    by_point = {}
    for p, o in keys:
        by_point.setdefault(p, []).append(o)
    multi = [(p, o) for p, o in by_point.items() if len(o) > 1]
    g = create_adapter_puzzle('shatter', 4, 4, 2)
    if not multi:
        check(True, '本盘面无同位置多朝向块，歧义分支不适用（跳过）')
    else:
        p = multi[0][0]
        try:
            g.apply_pattern(flat, groups={p: 1})
            check(False, '同位置多块时应拒绝位置口径')
        except ValueError as e:
            check('朝向' in str(e), '同位置多块时给出「请用坐标+朝向」的明确错误',
                  str(e)[:40])
    try:
        g.apply_pattern(flat, groups={(999, 999, '1'): 1})
        check(False, '不存在的块键应被拒绝')
    except ValueError as e:
        check('不在本局面' in str(e), '不存在的块键被拒绝', str(e)[:30])


def test_groups_survive_roundtrip():
    print('\n== T4 组信息可原样取出（存档落盘用同一口径）==')
    board = make_board('shatter')
    spec = board.spec
    pairs = _adjacent_same_shape_pairs(spec, board.keys)
    if not pairs:
        check(False, '缺少同形状相邻对，无法测组往返')
        return
    k1, k2 = pairs[0]
    flat = _keys_to_positions(frozenset(board.keys), spec)
    fk1 = (k1[0][0], k1[0][1], k1[1])
    fk2 = (k2[0][0], k2[0][1], k2[1])
    g = create_adapter_puzzle('shatter', 4, 4, 2)
    g.apply_pattern(flat, groups={fk1: 1, fk2: 1})
    got = g.groups_as_positions() or {}
    check(len(got) == 2, 'groups_as_positions 取回 2 个组员', str(sorted(got)[:2]))
    check(sorted(got.values()) == [1, 1], '组号原样保留')


if __name__ == '__main__':
    test_build_and_group_closure()
    test_positional_backward_compat()
    test_ambiguous_position_rejected()
    test_groups_survive_roundtrip()
    print()
    if _FAILS:
        print(f'FAILED ({len(_FAILS)}): ' + '; '.join(_FAILS))
        sys.exit(1)
    print('ALL PASS')
