# -*- coding: utf-8 -*-
"""护栏：求解「最大等待秒数」改为连续无进展停机（2026-11-11，待办 §三十四 第 3 条）。

用户实测：hybrid 有时停在「离复原很近」的地方，再启动一次几秒就复原 ——
根因是 total_budget 的**绝对** deadline（开机到停机最多 T 秒），把快解出的
下一段砍掉了。修法：`idle_budget` 滑动窗口，自上次采纳一段定稿动作起、
连续 T 秒没新进展才停；首个候选窗口取半让给第二候选。

判据（确定性，不靠求解器运气）：把两个真候选求解器换成**按固定间隔产出
定稿段**的假求解器，段数 / 是否被提前砍停就是确定性的观测值。
  T1 有进展 → 滑动窗口让 8 段全跑完、总耗时超过 T（旧的硬上限必砍）
  T2 对照：total_budget=T 仍按点砍（旧语义保留给 HTTP/实验）
  T3 无进展 → 约 T 秒即停，不空等
  T4 首个候选无进展时第二候选仍被启动（idle 到期不能整轮 break）
  T5/T6 静态接线：GUI 传 idle_budget、advance 采纳段时 touch_progress
  T7 idle_budget=0 不启用（不限时）

执行：D:/python/python.exe -u test/_test_solver_idle_budget.py
反向验证：archive/scratch_2026-11-11/reverse_idle_budget.py
"""
import os
import sys
import time
import inspect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import solver.auto_solver as A          # noqa: E402
from game import SliderMatrix            # noqa: E402
from solver.ml.fill_macro import build_game  # noqa: E402

FAILS = []


def check(name, cond, extra=''):
    print(('  PASS ' if cond else '  FAIL ') + name + '  ' + extra)
    if not cond:
        FAILS.append(name)


def scattered_coords(m=5, n=5, step=2, seed=7):
    """非解局面（auto_solve 对已解局面会直接返回空解）。"""
    import random
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=60, step=step)
    return frozenset(tuple(b.location) for b in g.blocks)


class FakeCandidates:
    """替换 gap/hybrid 两个真求解器 + _end_state，让 auto_solve 只测预算语义。

    _end_state 被换成「恒验证成功、终态沿用起点」，避免为了造合法动作去
    真回放；advance 的记账 / touch_progress / stage_cb 全部照常走。
    """

    def __init__(self, seg_interval, nsegs, produce=True, tail=0.0):
        self.seg_interval = seg_interval
        self.nsegs = nsegs
        self.produce = produce
        self.tail = tail
        self.segs = 0
        self.calls = {'gap': 0, 'hybrid': 0}
        self.orig = {}

    def __enter__(self):
        self.orig = dict(gap=A.solve_gap_macro, hybrid=A.hybrid_solve,
                         end=A._end_state)
        outer = self

        def fake_gap(game, step, cancel_check=None, progress_callback=None,
                     segment_cb=None, time_budget=None, **kw):
            outer.calls['gap'] += 1
            for i in range(outer.nsegs):
                t_end = time.time() + outer.seg_interval
                while time.time() < t_end:
                    if cancel_check is not None and cancel_check():
                        return {'type': 'fill_fail', 'reason': 'stopped'}
                    time.sleep(0.004)
                if outer.produce and segment_cb is not None:
                    # gseg(label, acts5) —— 两个位置参数，别合成一个元组
                    segment_cb('假段%d' % i, [('h', 1, 'above', 'd', None)])
                    outer.segs += 1
            if outer.tail:
                t_end = time.time() + outer.tail
                while time.time() < t_end:
                    if cancel_check is not None and cancel_check():
                        return {'type': 'fill_fail', 'reason': 'stopped-tail'}
                    time.sleep(0.004)
            return {'type': 'fill_fail', 'reason': 'done'}

        def fake_hybrid(game, step, cancel_check=None, progress_callback=None,
                        segment_cb=None, **kw):
            outer.calls['hybrid'] += 1
            return False

        A.solve_gap_macro = fake_gap
        A.hybrid_solve = fake_hybrid
        A._end_state = lambda coords0, acts, reps, m, n, step: (coords0, True)
        return self

    def __exit__(self, *a):
        A.solve_gap_macro = self.orig['gap']
        A.hybrid_solve = self.orig['hybrid']
        A._end_state = self.orig['end']


def run(coords, m, n, step, **kw):
    return A.auto_solve(build_game(coords, m, n), step, **kw)


def main():
    coords = scattered_coords()
    m = n = 5
    step = 2
    T = 0.3
    SEG = 0.05
    N = 8

    # T1 有进展：8 段（约 0.4s）应全部跑完，虽已远超 T=0.3s
    with FakeCandidates(SEG, N) as f:
        t0 = time.time()
        run(coords, m, n, step, idle_budget=T)
        dt = time.time() - t0
        check('T1 持续进步时不被 0.3s 砍停', f.segs == N,
              'segs=%d dt=%.2fs' % (f.segs, dt))
        check('T1 总耗时确实越过旧硬上限', dt > T,
              'dt=%.2fs > %.2fs' % (dt, T))

    # T2 对照：total_budget 旧语义仍按点砍
    with FakeCandidates(SEG, N) as f:
        run(coords, m, n, step, total_budget=T)
        check('T2 旧绝对上限仍按点停', f.segs < N,
              'segs=%d' % f.segs)

    # T3 无进展：约 T/2（首候选窗口取半）即停，不空等 0.8s 尾巴
    with FakeCandidates(SEG, N, produce=False, tail=0.8) as f:
        t0 = time.time()
        run(coords, m, n, step, idle_budget=T)
        dt = time.time() - t0
        check('T3 连续无进展即停、不空等', dt < 0.5 and f.segs == 0,
              'dt=%.2fs segs=%d' % (dt, f.segs))
        # T4 同一局：第二候选仍被启动（idle 到期没有整轮 break）
        check('T4 第二候选仍分到窗口', f.calls['hybrid'] >= 1,
              'calls=%r' % f.calls)

    # T7 0 = 不限时（不启用 idle）
    with FakeCandidates(SEG, N) as f:
        run(coords, m, n, step, idle_budget=0)
        check('T7 idle_budget=0 不启用', f.segs == N,
              'segs=%d' % f.segs)

    # T5/T6 静态接线（防「只改求解器没接 GUI」/「采纳段忘了滑动窗口」）
    gsrc = open(os.path.join(ROOT, 'gui', 'auto_solve.py'),
                encoding='utf-8').read()
    check('T5 GUI 走 idle_budget',
          "budget_kw['idle_budget']" in gsrc)
    check('T5 GUI 不再传 total_budget',
          "budget_kw['total_budget']" not in gsrc)
    asrc = inspect.getsource(A.auto_solve)
    # ⚠️ 别用 'touch_progress()' in asrc 当判据：函数定义行
    # `def touch_progress():` 本身就含这个子串，撤掉调用仍恒绿（假护栏）。
    # 只看 advance 函数体里那一次真正的调用。
    advance_body = asrc.split('def advance(')[1].split('def advance_from(')[0]
    check('T6 采纳段时滑动停机窗口',
          'touch_progress()' in advance_body)
    check('T6 idle 到期不整轮 break',
          'idle_expired()' not in asrc.split('def out_of_time()')[1].split('def score_of')[0])

    print('\nFAILS=%d %r' % (len(FAILS), FAILS))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
