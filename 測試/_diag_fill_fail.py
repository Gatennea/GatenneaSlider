# -*- coding: utf-8 -*-
"""批量诊断 save/填洞失敗案例 下的存档：状态 / 中断点 / 原因分类。"""
import glob
import json
import os
import sys

sys.path.insert(0, '.')
from solver.ml.fill_macro import solve_single_void, window_of

D = os.path.join('save', '填洞失敗案例')


def load(fn):
    d = json.load(open(fn, encoding='utf-8'))
    pz = d['puzzle']
    st = d['history']['snapshots'][0]
    b = st['bounds']
    co = frozenset((i + b['min_row'], j + b['min_col'])
                   for i, row in enumerate(st['matrix'])
                   for j, v in enumerate(row) if v)
    return co, pz['m'], pz['n'], pz['step']


for fn in sorted(glob.glob(os.path.join(D, '*.json'))):
    co, m, n, step = load(fn)
    (r0, c0, _), ov, holes, outside = window_of(co, m, n, step)
    a, s = solve_single_void(co, m, n, step, keep_partial=True)
    rel = []
    if len(outside) == 1:
        p = next(iter(outside))
        rh = r0 + (m if True else 0)
        # p 相对窗口四边
        inside_r = range(r0, r0 + m)  # 窗口(近似 m×n)
        inside_c = range(c0, c0 + n)
        pr, pc = p
        if pr < r0:
            rel = ['上方']
        elif pr >= r0 + m:
            rel = ['下方']
        elif pc < c0:
            rel = ['左侧']
        elif pc >= c0 + n:
            rel = ['右侧']
    print(os.path.basename(fn))
    print('   m,n=%d,%d 窗口r0=%d c0=%d ov=%d 洞=%s 凸=%s 凸在窗口%s'
          % (m, n, r0, c0, ov, sorted(holes), sorted(outside), rel))
    if a is None:
        print('   FAIL  %s' % s)
    elif s.get('partial'):
        print('   PARTIAL %s 步=%d' % (s.get('reason'), len(a)))
        for x in a:
            print('      ', x)
    else:
        print('   OK 步=%d' % len(a))
