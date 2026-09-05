# -*- coding: utf-8 -*-
"""对比 0011 solve 内部轨迹 与 replay 轨迹，找首次分叉。"""
import sys
sys.path.insert(0, '.')

from solver.ml.fill_macro import (sample_states, solve_single_void,
                                  build_game, replay_and_verify)


def dump(g):
    return sorted(tuple(b.location) for b in g.blocks)


st = [s for s in sample_states() if '0011' in s[0]][0]
coords, m, n, step = st[4], st[1], st[2], st[3]
acts, stats = solve_single_void(coords, m, n, step)
print('acts=', acts, stats)
print('replay=', replay_and_verify(coords, m, n, step, acts))

# replay 逐步
g = build_game(coords, m, n)
from game import Block
from solver.ml.fill_macro import _Runner
r = _Runner.__new__(_Runner)
r.g, r.m, r.n, r.step = g, m, n, step
r.p = None
steps_log = []
for i, a in enumerate(acts):
    gap, line, side, d, rep = a
    tgt = r._block_at(rep) or r._side_first_block(gap, line, side)
    g.opt(gap, line, tgt)
    pre = [tuple(b.location) for b in g.blocks if b.be_opted]
    fin = g.try_move(d, step)
    print('step%d %s rep=%s tgt=%s comp=%d ok=%s' %
          (i, (gap, line, side, d), rep, tuple(tgt.location), len(pre),
           bool(fin)))
    if not fin:
        break
    g.commit_move(fin)
    steps_log.append(dump(g))
    print('   solved=', g.is_solved())
