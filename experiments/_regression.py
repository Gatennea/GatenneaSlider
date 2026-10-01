# -*- coding: utf-8 -*-
"""回归测试：cancel/流式改动后，各存档求解结果不退化。"""
import json
import sys
import os
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import build_game, _replay_apply  # noqa: E402
from solver.ml.gap_solver import solve_gap_macro  # noqa: E402

CASES = [
    # (路径, 期望: 'solved'/'partial'/'fail'/'any')
    ('beginner_archive/5.1.json', 'solved'),
    ('beginner_archive/5.5.json', 'solved'),
    ('beginner_archive/4.4.json', 'fail'),      # 固有缺陷标本，仍应失败
    ('beginner_archive/4.1.json', 'solved'),
    ('beginner_archive/4.2.json', 'any'),
    ('beginner_archive/4.3.json', 'solved'),
    ('beginner_archive/4.5.json', 'solved'),
    ('beginner_archive/4.6.json', 'solved'),
    ('save/2-4-4-20261001-103250.json', 'solved'),
    ('save/2-4-4-20261001-103347.json', 'solved'),
    ('save/2-4-4-20261001-103418.json', 'solved'),
    ('save/失败01.json', 'any'),
    ('save/失败02.json', 'any'),
    ('save/失败03.json', 'solved'),
    ('save/失败04.json', 'any'),
    ('save/失败05.json', 'any'),
    ('save/失败06.json', 'any'),
    ('save/失败07.json', 'any'),
    ('save/失败08.json', 'any'),
    ('save/失败09.json', 'any'),
    ('save/2-6-6-20260930-181940.json', 'any'),
]


def load(path):
    with open(path, encoding='utf-8') as f:
        doc = json.load(f)
    snap = doc['history']['snapshots'][0]
    b = snap['bounds']
    coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                       for i, row in enumerate(snap['matrix'])
                       for j, v in enumerate(row) if v)
    pz = doc['puzzle']
    return coords, pz['m'], pz['n'], pz['step']


fails = 0
for rel, expect in CASES:
    path = os.path.join(_ROOT, rel)
    if not os.path.exists(path):
        print('%-42s 缺文件' % rel)
        continue
    coords, m, n, step = load(path)
    g = build_game(coords, m, n)
    t0 = time.time()
    res = solve_gap_macro(g, step)
    dt = time.time() - t0
    if isinstance(res, dict):
        tag = 'partial' if res.get('type') == 'fill_partial' else 'fail'
        n_steps = len(res.get('actions', []) or [])
    else:
        tag = 'solved'
        n_steps = len(res[0])
        g2 = build_game(coords, m, n)
        a5 = [tuple(a) + ((tuple(res[1][i]),) if res[1][i] else (None,))
              for i, a in enumerate(res[0])]
        if not (_replay_apply(g2, a5, m, n, step) and g2.is_solved()):
            tag = 'REPLAY-FAIL'
    verdict = 'OK'
    if expect == 'solved' and tag != 'solved':
        verdict = '!! 退化（期望全解）'
        fails += 1
    elif expect == 'fail' and tag == 'solved':
        verdict = '?? 意外全解（信息）'
    print('%-42s %-12s %3d 步 %6.1fs  %s' % (rel, tag, n_steps, dt, verdict))
print('=' * 70)
print('退化数: %d' % fails)
