# -*- coding: utf-8 -*-
"""自动规划混合求解器（solver/auto_solver.py）测试。

覆盖路径：
1. 注册表 'hybrid' 指向 auto_solve；
2. 有表 → ①查表全解（亚秒级、整链回放合法）；
3. 无表 + 空位主线 → ②补缺宏全解（archives/失败07.json 实例）；
4. 部分成果链接：fake 补缺宏 partial（真解前缀）+ fake 混合后缀
   → 前缀拼接、整链重放验证后采纳；
5. 全败 → fill_fail dict；
6. ②有成果但③失败 → fill_partial 断点协议（GUI 播到断点）。

运行：D:/python/python.exe test/_test_auto_planner.py（项目根目录）
"""
import os
import sys
import json
import time

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'experiments'))

import harness                                        # noqa: E402
from game import SliderMatrix                         # noqa: E402
from solver import SOLVER_ALGORITHMS                  # noqa: E402
import solver.auto_solver as A                        # noqa: E402
from solver.ml.fill_macro import build_game, replay_and_verify  # noqa: E402

PASS = []


def check(name, cond, note=''):
    PASS.append(bool(cond))
    print('%s %s%s' % ('PASS' if cond else 'FAIL', name,
                       ('（%s）' % note) if note else ''))


def a5zip(acts, reps):
    """(actions4, reps) → 5 元组列表（reps 补 None）。"""
    out = []
    for i, a in enumerate(acts):
        rep = reps[i] if (reps and i < len(reps) and reps[i]) else None
        out.append(tuple(a) + ((tuple(rep),) if rep else (None,)))
    return out


def shuffled_game(m, n, step, seed, attempts=140):
    """与实验 harness 同源的打乱局面（正向随机游走，必然可解）。"""
    import random
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=step)
    return g


# ---- 1. 注册表指向 ----
check('注册表 hybrid → auto_solve', SOLVER_ALGORITHMS['hybrid'][1] is A.auto_solve)

# ---- 2. 有表：①查表全解 ----
g4 = shuffled_game(4, 4, 2, 1000)
coords4 = frozenset(tuple(b.location) for b in g4.blocks)
stages = []
t0 = time.time()
res = A.auto_solve(build_game(coords4, 4, 4), 2,
                   progress_callback=lambda i: stages.append(str(i.get('stage', ''))))
dt_table = time.time() - t0
ok2 = (isinstance(res, tuple) and len(res) == 2
       and replay_and_verify(coords4, 4, 4, 2, a5zip(*res))
       and any('查表' in s for s in stages))
check('有表走①查表全解', ok2, '%d 步 %.2fs' % (len(res[0]) if isinstance(res, tuple) else -1, dt_table))

# 真解留作 4/6 的拼接素材（表路径，快）
sol_acts, sol_reps = res

# ---- 3. 无表 + 空位主线：②补缺宏全解（失败07） ----
doc = json.load(open(os.path.join(PROJECT, 'archives', '失败07.json'), encoding='utf-8'))
s0 = doc['history']['snapshots'][0]
b0 = s0['bounds']
coords07 = frozenset((b0['min_row'] + i, b0['min_col'] + j)
                     for i, row in enumerate(s0['matrix'])
                     for j, v in enumerate(row) if v)
pz = doc['puzzle']
g07 = build_game(coords07, pz['m'], pz['n'])
stages3 = []
t0 = time.time()
res3 = A.auto_solve(g07, pz['step'],
                    progress_callback=lambda i: stages3.append(str(i.get('stage', ''))))
dt07 = time.time() - t0
ok3 = (isinstance(res3, tuple)
       and replay_and_verify(coords07, pz['m'], pz['n'], pz['step'], a5zip(*res3))
       and any('补缺宏' in s for s in stages3))
check('失败07 走②补缺宏全解', ok3,
      '%s %.2fs' % (('%d 步' % len(res3[0])) if isinstance(res3, tuple) else res3, dt07))

# ---- 4. 部分成果链接：②partial(真解前缀) + ③后缀 → 拼接全解 ----
k = len(sol_acts) - 1
P_acts, P_reps = sol_acts[:k], sol_reps[:k]
orig = (A.table_solve, A.solve_gap_macro, A.hybrid_solve)
try:
    A.table_solve = lambda *a, **kw: None
    A.solve_gap_macro = lambda *a, **kw: {
        'type': 'fill_partial', 'actions': P_acts, 'rep_cells': P_reps,
        'reason': 'fake partial'}
    A.hybrid_solve = lambda gm, stp, **kw: (sol_acts[k:], sol_reps[k:])
    res4 = A.auto_solve(build_game(coords4, 4, 4), 2)
finally:
    A.table_solve, A.solve_gap_macro, A.hybrid_solve = orig
ok4 = (isinstance(res4, tuple) and len(res4[0]) == len(sol_acts)
       and replay_and_verify(coords4, 4, 4, 2, a5zip(*res4)))
check('②partial+③后缀拼接全解', ok4,
      '%s（前缀%d+后缀%d）' % ('%d 步' % len(res4[0]) if isinstance(res4, tuple) else res4,
                              k, len(sol_acts) - k))

# ---- 5. 全败 → fill_fail ----
try:
    A.table_solve = lambda *a, **kw: None
    A.solve_gap_macro = lambda *a, **kw: {'type': 'fill_fail', 'reason': 'fake'}
    A.hybrid_solve = lambda *a, **kw: False
    res5 = A.auto_solve(build_game(coords4, 4, 4), 2)
finally:
    A.table_solve, A.solve_gap_macro, A.hybrid_solve = orig
check('全败返回 fill_fail', isinstance(res5, dict) and res5.get('type') == 'fill_fail')

# ---- 6. ②有成果 ③失败 → fill_partial 断点 ----
try:
    A.table_solve = lambda *a, **kw: None
    A.solve_gap_macro = lambda *a, **kw: {
        'type': 'fill_partial', 'actions': P_acts, 'rep_cells': P_reps,
        'reason': 'fake partial'}
    A.hybrid_solve = lambda *a, **kw: False
    res6 = A.auto_solve(build_game(coords4, 4, 4), 2)
finally:
    A.table_solve, A.solve_gap_macro, A.hybrid_solve = orig
ok6 = (isinstance(res6, dict) and res6.get('type') == 'fill_partial'
       and len(res6.get('actions', [])) == k)
check('②成果③失败 → fill_partial 断点', ok6,
      '保留前缀 %d 步' % (len(res6.get('actions', [])) if isinstance(res6, dict) else -1))

print('=' * 40)
print('%d/%d PASS' % (sum(PASS), len(PASS)))
sys.exit(0 if all(PASS) else 1)
