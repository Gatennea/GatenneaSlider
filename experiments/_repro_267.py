# -*- coding: utf-8 -*-
"""复现 2-6-7 求解失败：从存档快照 0（打乱态）构造局面跑 solve_gap_macro。"""
import json
import sys
import os
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import build_game, gcoords  # noqa: E402
from solver.ml.gap_solver import solve_gap_macro  # noqa: E402

path = os.path.join(_ROOT, 'save', '2-6-7-20261001-161826.json')
with open(path, encoding='utf-8') as f:
    doc = json.load(f)

m, n = doc['puzzle']['m'], doc['puzzle']['n']
step = doc['puzzle']['step']
snaps = doc['history']['snapshots']
hi = doc['history']['history_index']

# 快照 → 世界坐标格集
def snap_coords(snap):
    b = snap['bounds']
    mr, mc = b['min_row'], b['min_col']
    return frozenset((mr + i, mc + j)
                     for i, row in enumerate(snap['matrix'])
                     for j, v in enumerate(row) if v == 1)

print('puzzle %dx%d step=%d, snapshots=%d, history_index=%d' %
      (m, n, step, len(snaps), hi))

# 校验：最后快照应为满盘已还原
g_last = build_game(snap_coords(snaps[-1]), m, n)
print('last snapshot solved?', g_last.is_solved(), '(expect True)')

# 打乱起点 = 快照 0
coords0 = snap_coords(snaps[0])
g0 = build_game(coords0, m, n)
print('start snapshot: %d blocks, solved=%s' % (len(coords0), g0.is_solved()))

t0 = time.time()
res = solve_gap_macro(g0, step, verbose=True)
dt = time.time() - t0
print('--- solve_gap_macro: %.1fs ---' % dt)
if isinstance(res, dict):
    print('FAIL dict:', res)
else:
    print('OK actions=%d reps=%d' % (len(res[0]), len(res[1])))
