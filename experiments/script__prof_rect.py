# -*- coding: utf-8 -*-
"""矩形求解器性能剖析：auto_solve 在代表性局面上的热点分布。

目的：回答「必然可优化的地方在哪」——用 tottime（自身耗时）找真热点，
而不是靠猜。tottime 才是「这段代码自己烧掉的时间」，cumtime 会被调用链放大。

用法：
    D:/python/python.exe -u experiments/script__prof_rect.py > experiments/_prof_rect_out.txt 2>&1
"""
import cProfile
import io
import json
import os
import pstats
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import build_game          # noqa: E402
from solver.auto_solver import auto_solve            # noqa: E402

CASES = [
    ('archives/失败06.json', 0, 60, '06 死局(带移链后秒解)'),
    ('archives/失败07.json', 0, 60, '07 死局(带移链后秒解)'),
    ('archives/2-7-8-20261001-185331.json', 31, 60, '2-7-8 停机局面'),
    ('archives/失败04.json', 0, 120, '04 死局(撞DFS预算)'),
]


def load(path, snap_idx=0):
    with open(os.path.join(_ROOT, path), encoding='utf-8') as f:
        doc = json.load(f)
    snap = doc['history']['snapshots'][snap_idx]
    b = snap['bounds']
    coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                       for i, row in enumerate(snap['matrix'])
                       for j, v in enumerate(row) if v)
    pz = doc['puzzle']
    return coords, pz['m'], pz['n'], pz['step']


def run_case(path, snap_idx, budget, label):
    print('=' * 78)
    print('CASE %s  (%s)' % (label, path))
    print('=' * 78)
    coords, m, n, step = load(path, snap_idx)
    game = build_game(coords, m, n)
    print('  size=%dx%d step=%d cells=%d budget=%ss'
          % (m, n, step, len(coords), budget))

    pr = cProfile.Profile()
    t0 = time.time()
    pr.enable()
    res = auto_solve(build_game(coords, m, n), step, time_budget=budget)
    pr.disable()
    el = time.time() - t0

    if isinstance(res, tuple):
        verdict = 'SOLVED %d steps' % len(res[0])
    elif isinstance(res, dict):
        verdict = 'PARTIAL (%s)' % res.get('type')
    else:
        verdict = 'FAIL/False'
    print('  => %s   wall=%.2fs' % (verdict, el))

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('tottime')
    ps.print_stats(22)
    print(s.getvalue())
    return verdict, el


def main():
    total = 0.0
    for path, idx, budget, label in CASES:
        if not os.path.exists(os.path.join(_ROOT, path)):
            print('SKIP missing %s' % path)
            continue
        try:
            _v, el = run_case(path, idx, budget, label)
            total += el
        except Exception as e:
            import traceback
            print('  ERROR: %s' % e)
            traceback.print_exc()
    print('TOTAL wall = %.1fs' % total)


if __name__ == '__main__':
    main()
