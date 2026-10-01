# -*- coding: utf-8 -*-
"""2-6-7 × gather_solve：聚拢求解器能否拿下？计时+回放验证。"""
import json
import sys
import os
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import build_game  # noqa: E402
from solver.ml.gather_solver import gather_solve  # noqa: E402

path = os.path.join(_ROOT, 'save', '2-6-7-20261001-161826.json')
with open(path, encoding='utf-8') as f:
    doc = json.load(f)
m, n = doc['puzzle']['m'], doc['puzzle']['n']
step = doc['puzzle']['step']
snap = doc['history']['snapshots'][0]
b = snap['bounds']
coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                   for i, row in enumerate(snap['matrix'])
                   for j, v in enumerate(row) if v)

g = build_game(coords, m, n)
t0 = time.time()
res = gather_solve(g, step=step)
dt = time.time() - t0
print('gather_solve: %.1fs' % dt)
if isinstance(res, dict):
    print('keys:', sorted(res.keys()))
    acts = res.get('actions')
    print('solved=%s reason=%s actions=%s'
          % (res.get('solved'), res.get('reason'),
             len(acts) if acts else acts))
    if acts:
        g2 = build_game(coords, m, n)
        for a in acts:
            ok = False
            try:
                gap, line, side, d = a[0], a[1], a[2], a[3]
                rep = a[4] if len(a) > 4 else None
                tgt = None
                for blk in g2.blocks:
                    if rep is not None and tuple(blk.location) == tuple(rep):
                        tgt = blk
                        break
                if tgt is None:
                    st_above = (lambda q: q[0] <= line) if side == 'above' \
                        else (lambda q: q[0] > line) if gap == 'h' else None
                    for blk in g2.blocks:
                        r, c = blk.location
                        if gap == 'h':
                            hit = (r <= line) if side == 'above' else (r > line)
                        else:
                            hit = (c <= line) if side == 'left' else (c > line)
                        if hit:
                            tgt = blk
                            break
                g2.opt(gap, line, tgt)
                final = g2.try_move(d, step)
                if final:
                    g2.commit_move(final)
                    ok = True
                else:
                    for blk in g2.blocks:
                        blk.be_opted = False
            except Exception as e:
                print('  回放异常: %s' % e)
            if not ok:
                print('  第 %d 步回放失败: %s' % (acts.index(a), a))
                break
        print('整链回放 is_solved =', g2.is_solved())
else:
    print('返回类型:', type(res), res if not isinstance(res, list) else len(res))
