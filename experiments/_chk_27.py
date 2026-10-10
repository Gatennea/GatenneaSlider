# -*- coding: utf-8 -*-
import sys, time, json
sys.path.insert(0, ".")
from solver.ml.fill_macro import build_game, _replay_apply
from solver.auto_solver import auto_solve

def load(path, sid=0):
    doc = json.load(open(path, encoding='utf-8'))
    snap = doc['history']['snapshots'][sid]
    b = snap['bounds']
    coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                       for i, row in enumerate(snap['matrix'])
                       for j, v in enumerate(row) if v)
    pz = doc['puzzle']
    return coords, pz['m'], pz['n'], pz['step']

coords, m, n, step = load('archives/2-7-8-20261001-185331.json')
print('2-7-8 m=%d n=%d step=%d' % (m, n, step), flush=True)
g0 = build_game(coords, m, n)
t0 = time.time()
res = auto_solve(g0, step, time_budget=60)
dt = time.time() - t0
print('auto_solve done %.2fs' % dt, flush=True)
acts = res[0]
reps = res[1] if len(res) > 1 else []
g2 = build_game(coords, m, n)
a5 = [tuple(a) + ((tuple(reps[i]),) if (reps and reps[i]) else (None,))
      for i, a in enumerate(acts)]
ok = _replay_apply(g2, a5, m, n, step) and g2.is_solved()
print('2-7-8 SOLVED' if ok else '2-7-8 PARTIAL/FAIL', 'steps=%d' % len(acts), flush=True)
