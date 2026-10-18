# -*- coding: utf-8 -*-
"""三形态枚举器（第一版）：前向 BFS + 不可逆定理逐边核验。

只依赖前向 BFS（从还原态出发，天然有限且完备），故本版给出：
    |cone|、正向深度、边数、单步不可逆边数、粘连核验。

定理核验：对每条「两端都在 cone 内的单步不可逆边」(x→y)，检查落位分量在 y 中
是否还能被某条「平行于该步方向」的缝单独框住（is_selectable）。不可逆 ⟺ 粘连，
两个计数应逐边相等——即定理在三角形/米字格上的数值验证。

板型见 board_types.py。
注意：三角还原态有 120°/240° 旋转等价，本版只取一个代表姿态作种子，|cone| 是
「能到达该姿态」的子集（完整 cone 需多源种子＝异形方案 §4.2 待办）。
"""
from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import board_types as bt  # noqa: E402


def parse(spec: str):
    kind, _, rest = spec.partition(':')
    parts = [int(x) for x in rest.split(',') if x != '']
    if kind == 'square':
        return bt.SquareBoard(parts[0], parts[1]), (parts[2] if len(parts) > 2 else 1)
    if kind == 'triangle':
        return bt.TriangleBoard(parts[0]), (parts[1] if len(parts) > 1 else 1)
    if kind == 'mi':
        return bt.MiBoard(parts[0], parts[1]), (parts[2] if len(parts) > 2 else 1)
    raise ValueError(spec)


def analyze(board, step, cross_check_square=False):
    goal = board.goal_cells()
    gkey = board.canonical(goal)
    rep = {gkey: frozenset(goal)}
    depth = {gkey: 0}
    queue = deque([gkey])
    edges = {}                      # key -> [(ykey, moved, dvec)]
    while queue:
        x = queue.popleft()
        es, seen = [], set()
        for y_cells, moved, dvec in board.forward_moves(rep[x], step):
            yk = board.canonical(y_cells)
            sig = (moved, dvec)
            if sig in seen:
                continue
            seen.add(sig)
            if yk not in rep:
                rep[yk] = frozenset(y_cells)
                depth[yk] = depth[x] + 1
                queue.append(yk)
            es.append((yk, frozenset(moved), dvec))
        edges[x] = es

    n_cone = len(rep)
    fwd_god = max(depth.values()) if depth else 0
    n_edges = sum(len(v) for v in edges.values())

    n_irr = n_sticky = 0
    for x, es in edges.items():
        for yk, moved, dvec in es:
            # 可逆 ⟺ y 的出边里有一条回到 x
            if any(a == x for a, _, _ in edges.get(yk, [])):
                continue              # 可逆
            n_irr += 1
            # 定理的 C' = 落位后的分量（平移前 comp 平移 dvec*step）
            C = board.shift(moved, dvec, step)
            if not board.is_selectable(rep[yk], C, dvec):
                n_sticky += 1

    print('=' * 66)
    print(f'[{board.kind}] step={step}  K={board.K}')
    print(f'  |cone|             = {n_cone:,}')
    print(f'  forward god depth  = {fwd_god}')
    print(f'  #edges (in cone)   = {n_edges:,}')
    print(f'  one-step irrevers. = {n_irr:,}')
    print(f'  sticky (not select)= {n_sticky:,}')
    print(f'  THEOREM irr==sticky: {"OK" if n_irr == n_sticky else "MISMATCH"}')
    return n_cone, fwd_god, n_edges, n_irr, n_sticky


def cross_check_square(m, n, step):
    """把 SquareBoard.forward_moves 与历史 forward_closure.forward_edges 对拍。"""
    from forward_closure import forward_edges
    from solver import table_core as tc
    board = bt.SquareBoard(m, n)
    goal = board.goal_cells()
    bad = 0
    # 抽查 goal 及若干邻居
    states = [set(goal)]
    for cells, _, _ in board.forward_moves(goal, step):
        states.append(set(cells))
        if len(states) >= 12:
            break
    for cells in states:
        mine = {board.canonical(y) for y, _, _ in board.forward_moves(cells, step)}
        ref = {y for y, _, _ in forward_edges(cells, step, m * n)}
        if mine != ref:
            bad += 1
    print(f'  [square cross-check] {len(states)} states, mismatch={bad}')
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('specs', nargs='+')
    ap.add_argument('--cross-check', action='store_true')
    args = ap.parse_args()
    if args.cross_check:
        cross_check_square(2, 3, 1)
    for spec in args.specs:
        board, step = parse(spec)
        analyze(board, step)


if __name__ == '__main__':
    main()
