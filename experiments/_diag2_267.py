# -*- coding: utf-8 -*-
"""2-6-7 深挖：OK couple 的 9 步产物回放后 ov 变化 / 带移产物 ov 变化。"""
import json
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import build_game, gcoords, _replay_apply  # noqa: E402
from solver.ml.gap_solver import window_of, _vacancy_couple_hook  # noqa: E402
from solver.ml.fill_macro import _overlap_raised  # noqa: E402
from solver.ml.fill_macro import _belt_shift_fill  # noqa: E402

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


def show_state(cur, tag):
    reg, ov, holes, outside = window_of(cur, m, n, step)
    print('%s: ov=%d 洞%s 凸%s 窗口%s' % (tag, ov, sorted(holes),
                                         sorted(outside), reg))
    return ov


hook = _vacancy_couple_hook(False)
show_state(coords, '初始')

for h, p in [((0, 5), (6, 3)), ((4, 0), (6, 6)), ((5, 5), (-1, 1))]:
    acts, st = hook(coords, m, n, step, h, p)
    if acts is None:
        print('\ncouple 洞%s←凸%s: 无产物 (%s)' % (h, p, st))
        continue
    raised = _overlap_raised(coords, m, n, step, acts)
    g2 = build_game(coords, m, n)
    ok = _replay_apply(g2, acts, m, n, step)
    print('\ncouple 洞%s←凸%s: %d 步 回放=%s 闸门提升=%s'
          % (h, p, len(acts), ok, raised))
    if ok:
        cur2 = frozenset(gcoords(g2))
        show_state(cur2, '  回放后')

# 带移产物
for h in [(0, 5), (4, 0), (5, 5)]:
    acts = _belt_shift_fill(coords, m, n, step, h)
    if not acts:
        continue
    g2 = build_game(coords, m, n)
    ok = _replay_apply(g2, acts, m, n, step)
    raised = _overlap_raised(coords, m, n, step, acts) if ok else None
    print('\n带移 洞%s: %d 步 回放=%s 闸门提升=%s' % (h, len(acts), ok, raised))
    if ok:
        cur2 = frozenset(gcoords(g2))
        show_state(cur2, '  回放后')
