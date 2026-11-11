# -*- coding: utf-8 -*-
"""护栏：混合求解跑到「恰好 1 洞」时必须立刻让位给确定性补缺宏。

用户 2026-11-11 报：「最後階段經常直接調用填洞補就能完成，硬是靠 GBFS
搜了一會才發現能用填洞補缺，直接浪費好幾秒。」

诊断：路由（gap_first）只按**初始局面**的洞数算一次；混合候选内部每轮
GBFS 前不重测。当流式续算态推进到「恰好 1 洞」时，`guided_reduce_one`
仍会在 1 洞态上跑一整轮搜索，而 `solve_gap_macro` 对单洞是确定性直解
（0.0s）。修法＝`advance()` 每次采纳段后记录 `flow['single_hole']`；
`run_hybrid` 的 `stage_cancel` 一见单洞就中止混合；候选开跑前 / 全部
跑完时用 `try_single_hole_closeout()` 直接补缺宏收口。

判据（行为，盯「被绕开的 GBFS 有没有启动」）：fake hybrid 上报一段
把 flow 推到 1 洞后，在循环里数 cancel_check 通过次数（gbfs_ran）。
  · 修复态：single_hole 标记生效 → 立刻 cancel → gbfs_ran == 0，返回全解。
  · 反向态：把 window_of 打桩成「2 洞」→ single_hole 不置位 → hybrid
    不被中止 → gbfs_ran > 0（证明计数器真的能抓到 GBFS 启动）。

执行：D:/python/python.exe -u test/_test_single_hole_preempt.py
"""
import os
import sys
import inspect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import solver.auto_solver as A          # noqa: E402
from game import SliderMatrix            # noqa: E402
from solver.ml.fill_macro import build_game, window_of  # noqa: E402

FAILS = []


def check(name, cond, extra=''):
    print(('  PASS ' if cond else '  FAIL ') + name + '  ' + extra)
    if not cond:
        FAILS.append(name)


def fixtures(m=5, n=5, step=2):
    solved = frozenset((b.location[0], b.location[1])
                       for b in SliderMatrix(m, n).blocks)
    maxr = max(c[0] for c in solved)
    one = next(c for c in solved if c[0] == maxr)
    single = frozenset((solved - {one}) | {(one[0] + 1, one[1])})
    import random
    random.seed(11)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=60, step=step)
    scattered = frozenset(tuple(b.location) for b in g.blocks)
    return solved, single, scattered


def run_scenario(single, scattered, force_two_holes=False):
    """跑一次 auto_solve，fake hybrid 上报单洞段后数「GBFS 继续跑了多少下」。

    force_two_holes=True 时把 window_of 打桩成恒返回 2 洞（反向验证：
    单洞标记不置位 → 混合不该被中止）。
    """
    m = n = 5
    step = 2
    state = {'gbfs_ran': 0, 'gap_calls': 0}

    orig = dict(gap=A.solve_gap_macro, hybrid=A.hybrid_solve,
                end=A._end_state, win=A.window_of,
                route=None)

    def fake_hybrid(game, step, cancel_check=None, progress_callback=None,
                    segment_cb=None, **kw):
        # 先上报一段，把 flow['end'] 推到「恰好 1 洞」
        if segment_cb is not None:
            segment_cb({'label': '假搜索段',
                        'actions': [('h', 1, 'above', 'd')],
                        'reps': [None], 'end': single})
        # 模拟 GBFS：不断 check cancel；修复态应立刻被 cancel 掉
        for _ in range(100):
            if cancel_check is not None and cancel_check():
                break
            state['gbfs_ran'] += 1
        return False

    def fake_gap(game, step, cancel_check=None, progress_callback=None,
                 segment_cb=None, time_budget=None, **kw):
        state['gap_calls'] += 1
        return [('h', 1, 'above', 'd')], [None]

    def fake_end(coords0, acts, reps, m, n, step):
        return (single, True)   # 只被单洞收口调用；恒判为通过

    A.solve_gap_macro = fake_gap
    A.hybrid_solve = fake_hybrid
    A._end_state = fake_end
    if force_two_holes:
        A.window_of = lambda coords, m, n, step: (None, None, [1, 2], None)
    try:
        res = A.auto_solve(build_game(scattered, m, n), step,
                           idle_budget=0.3,
                           route_fn=(lambda *a: False))  # 强制混合先跑
    finally:
        A.solve_gap_macro = orig['gap']
        A.hybrid_solve = orig['hybrid']
        A._end_state = orig['end']
        A.window_of = orig['win']
    return state, res


def main():
    solved, single, scattered = fixtures()
    _r, _o, holes, _u = window_of(single, 5, 5, 2)
    check('F0 夹具真的是 1 洞', len(holes) == 1, 'holes=%d' % len(holes))
    if len(holes) != 1:
        return 1

    # ---- 修复态：1 洞 → 立刻中止混合，走确定性收口 ----
    state, res = run_scenario(single, scattered)
    check('P1 单洞一出现就中止混合（GBFS 未再启动）',
          state['gbfs_ran'] == 0, 'gbfs_ran=%d' % state['gbfs_ran'])
    check('P2 单洞收口直接补跑补缺宏', state['gap_calls'] >= 1,
          'gap_calls=%d' % state['gap_calls'])
    check('P3 本轮内返回全解 tuple', isinstance(res, tuple),
          'res=%s' % type(res).__name__)

    # ---- 反向：state 不被识别成单洞 → 混合不应被中止（GBFS 真启动了）----
    state2, _res2 = run_scenario(single, scattered, force_two_holes=True)
    check('P4 反向验证：非单洞时 GBFS 确实会跑（计数器有效）',
          state2['gbfs_ran'] > 0, 'gbfs_ran=%d' % state2['gbfs_ran'])

    # ---- 静态接线：两处都必须挂上 single_hole 判据 ----
    asrc = inspect.getsource(A.auto_solve)
    check('P5 advance 记录 flow[single_hole]',
          "flow['single_hole']" in asrc)
    check('P6 候选开跑前有单洞收口',
          'try_single_hole_closeout()' in asrc)

    print('\nFAILS=%d %r' % (len(FAILS), FAILS))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
