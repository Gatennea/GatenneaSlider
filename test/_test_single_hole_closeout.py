# -*- coding: utf-8 -*-
"""护栏：流式续算到「恰好 1 洞」时，本轮内补跑补缺宏收口（2026-11-11）。

用户实测「hybrid 停在离复原很近的地方，再启动一次几秒就复原」。
诊断（archive/scratch_2026-11-11/diag_restart_route.py）坐实：
6×6 s2 seed 2000/2001/2005 第一遍都跑满 20s 停在 fill_partial，
**终态都恰好剩 1 洞**；从终态再跑一次 auto_solve 3/3 都是 0.01s 复原。
根因不是预算（改 idle_budget 后 A/B 解出率仍 3/6），是候选顺序按初始
局面算死、续算态的单洞没被重新识别。修法＝两候选跑完、未全解时，用
flow['end'] 重测；命中单洞就补跑一次补缺宏，把「再点一次」搬进本轮。

判据（确定性，盯「被绕开的求解器有没有启动」）：spy 计 solve_gap_macro
调用次数。修复态应为 2（首次流式 + 单洞收口）且返回全解 tuple；
撤掉收口则只有 1 次、返回 fill_partial dict。

执行：D:/python/python.exe -u test/_test_single_hole_closeout.py
反向验证：archive/scratch_2026-11-11/reverse_closeout.py
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


def coords_fixtures(m=5, n=5, step=2):
    """解态 / 恰好 1 洞 / 非解的散盘初始态。"""
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


def main():
    m = n = 5
    step = 2
    solved, single, scattered = coords_fixtures(m, n, step)

    _reg, _ov, holes, _out = window_of(single, m, n, step)
    check('F0 夹具真的是 1 洞', len(holes) == 1, 'holes=%d' % len(holes))
    if len(holes) != 1:
        return 1

    orig = dict(gap=A.solve_gap_macro, hybrid=A.hybrid_solve, end=A._end_state)
    state = {'gap_calls': 0, 'end_calls': 0}

    def fake_gap(game, step, cancel_check=None, progress_callback=None,
                 segment_cb=None, time_budget=None, **kw):
        state['gap_calls'] += 1
        if state['gap_calls'] == 1:
            # 首次流式：上报一段，让 flow['end'] 推进到「恰好 1 洞」
            if segment_cb is not None:
                segment_cb('假流式段', [('h', 1, 'above', 'd', None)])
            return {'type': 'fill_partial', 'actions': [], 'rep_cells': []}
        # 第 2 次＝单洞收口：确定性直解
        return [('h', 1, 'above', 'd')], [None]

    def fake_hybrid(game, step, cancel_check=None, progress_callback=None,
                    segment_cb=None, **kw):
        return False

    def fake_end(coords0, acts, reps, m, n, step):
        state['end_calls'] += 1
        return ((single if state['end_calls'] == 1 else solved), True)

    A.solve_gap_macro = fake_gap
    A.hybrid_solve = fake_hybrid
    A._end_state = fake_end
    try:
        res = A.auto_solve(build_game(scattered, m, n), step,
                           idle_budget=0.3)
    finally:
        A.solve_gap_macro = orig['gap']
        A.hybrid_solve = orig['hybrid']
        A._end_state = orig['end']

    check('F1 单洞收口真的补跑了补缺宏', state['gap_calls'] == 2,
          'gap_calls=%d' % state['gap_calls'])
    check('F2 本轮内直接返回全解', isinstance(res, tuple),
          'res=%s' % (type(res).__name__))
    if isinstance(res, tuple):
        check('F3 整链含流式段 + 收口段', len(res[0]) == 2,
              'steps=%d' % len(res[0]))

    # 静态接线：收口必须按 flow['end'] 重测洞数，不能沿用初始 coords0
    asrc = inspect.getsource(A.auto_solve)
    check('F4 按续算态重测洞数',
          "window_of(flow['end'], m, n, step)" in asrc)
    check('F5 收口有独立短帽（不吃 idle 窗口）',
          '_SINGLE_HOLE_CAP' in asrc)

    print('\nFAILS=%d %r' % (len(FAILS), FAILS))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
