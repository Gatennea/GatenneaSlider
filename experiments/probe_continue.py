# -*- coding: utf-8 -*-
"""探针：找出走「补缺宏·部分 → 混合流水线·续算」续算路径且最终解出的 seed。

续算路径 = ① gap_first（洞≥3）且补缺宏返回 partial（best 有效）且混合流水线从
best['end'] 续算成功。这种用例才会触发 auto_solver 续算分支的 end 坐标计算，
是验证刚修复 bug 的关键。
"""
import sys
sys.path.insert(0, '.')

import random
import time
from game import SliderMatrix
from solver.auto_solver import auto_solve
from solver.ml.fill_macro import build_game, window_of


def probe(sz, seed, step, budget):
    random.seed(seed)
    g = SliderMatrix(*sz)
    g.shuffle(attempts=150, step=step)
    coords0 = frozenset(tuple(b.location) for b in g.blocks)
    _reg, _ov, holes, _out = window_of(coords0, g.m, g.n, step)
    if len(holes) < 3:
        return None  # 非 gap_first，不走续算主路径
    stages = []
    t0 = time.time()
    def cc():
        return (time.time() - t0) >= budget
    r = auto_solve(g, step, stage_cb=lambda s: stages.append(s['label']),
                   time_budget=budget, cancel_check=cc)
    labels = stages
    has_partial = '补缺宏·部分' in labels
    has_cont = '混合流水线·续算' in labels
    solved = isinstance(r, tuple)
    return {'seed': seed, 'holes': len(holes), 'labels': labels,
            'has_partial': has_partial, 'has_cont': has_cont,
            'solved': solved}


if __name__ == '__main__':
    found = []
    for seed in range(1, 31):
        res = probe((5, 5), seed, 2, 120)
        if res is None:
            continue
        if res['has_cont'] and res['solved']:
            found.append(res)
            print('CONTINUE-SOLVED seed=%d holes=%d labels=%s'
                  % (res['seed'], res['holes'], res['labels']))
        else:
            print('seed=%d holes=%d labels=%s solved=%s'
                  % (res['seed'], res['holes'], res['labels'], res['solved']))
    print('=== found continue-solved:', [f['seed'] for f in found])
