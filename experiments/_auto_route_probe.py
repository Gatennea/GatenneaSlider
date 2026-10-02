# -*- coding: utf-8 -*-
"""自动规划路由探针：逐案例测「局面特征 × 各求解器单独耗时」。

为 auto_solve 的路由规则提供事实依据：
  - 什么特征下补缺宏快（06/07 型：多空位）？
  - 什么特征下混合流水线快（5.1 型：单空位？）？
  - 特征能否在秒级内算出来用于分流？

运行：D:/python/python.exe -u experiments/_auto_route_probe.py
"""
import os
import sys
import json
import time
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'experiments'))

from solver.ml.fill_macro import build_game, window_of           # noqa: E402
from solver.ml.gather_solver import gather_metrics               # noqa: E402
from solver.ml.gap_solver import solve_gap_macro                 # noqa: E402
from solver.hybrid_solver import hybrid_solve                    # noqa: E402


def load_archive(kind, name):
    path = os.path.join(ROOT, 'beginner_archive' if kind == 'archive' else 'save', name)
    doc = json.load(open(path, encoding='utf-8'))
    s0 = doc['history']['snapshots'][0]
    b = s0['bounds']
    pz = doc['puzzle']
    coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                       for i, row in enumerate(s0['matrix'])
                       for j, v in enumerate(row) if v)
    return coords, pz['m'], pz['n'], pz['step']


def timed_run(fn, coords, m, n, step, budget_s):
    box = {}

    def worker():
        g = build_game(coords, m, n)
        t0 = time.time()
        try:
            res = fn(g, step)
        except Exception as e:
            res = {'type': 'fill_fail', 'reason': '异常: %s' % e}
        box['res'] = res
        box['dt'] = time.time() - t0

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join(budget_s)
    if th.is_alive():
        return budget_s, 'TIMEOUT'
    dt = box.get('dt', -1)
    res = box.get('res')
    if isinstance(res, tuple):
        return dt, 'solved %d 步' % len(res[0])
    if isinstance(res, dict):
        t = res.get('type', '?')
        if t == 'fill_partial':
            return dt, 'partial %d 步' % len(res.get('actions', []))
        return dt, '%s:%s' % (t, str(res.get('reason', ''))[:30])
    return dt, str(res)


CASES = [
    ('5.1(刚体)', load_archive('archive', '5.1.json'), 60),
    ('失败06', load_archive('save', '失败06.json'), 60),
    ('失败07', load_archive('save', '失败07.json'), 60),
    ('失败04', load_archive('save', '失败04.json'), 150),
]

for name, (coords, m, n, step), budget in CASES:
    _reg, ov, holes, outside = window_of(coords, m, n, step)
    sc = gather_metrics(coords, m, n)['score']
    print('%s  尺寸=%dx%d step=%d | 洞%d 凸%d 聚拢度%.3f'
          % (name, m, n, step, len(holes), len(outside), sc), flush=True)
    dt, desc = timed_run(solve_gap_macro, coords, m, n, step, budget)
    print('    补缺宏   %6.1fs  %s' % (dt, desc), flush=True)
    dt, desc = timed_run(hybrid_solve, coords, m, n, step, budget)
    print('    混合流水 %6.1fs  %s' % (dt, desc), flush=True)
print('探针完成。', flush=True)
