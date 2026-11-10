# -*- coding: utf-8 -*-
"""护栏：求解时间预算语义 + 可复现随机源（2026-11-09）。

⚠️ 2026-11-11 口径更新：GUI 的「最大等待秒数」按用户拍板改成
「连续无进展停机」（idle_budget 滑动窗口），不再传 total_budget 硬上限；
total_budget 参数与 C 组整轮语义护栏全部保留给 HTTP / 实验基线对照。
A2 随之改盯新接线，「不许退回 stage_budget（每候选各一份）」这条原意不变。

坐实过的两个真问题：
1. stage_budget 是「每候选各一份」：补缺宏 T 秒 + 混合 T 秒 = 2T，
   与设置页「求解时间上限」文案不符（T=3 实测墙钟 6.01s）。
   新增 total_budget（整轮共享单调 deadline，首候选最多占一半、余额让渡续算）。
2. 求解内部 `rng = rng or random.Random()` 无参播种 + gather_solve 吃全局
   random，同局面连跑两次可能「解出 / 只回部分成果」翻转，A/B 基准不可比。
   新增 rng_seed 并沿链透传到补缺宏与聚拢轮。

顺带钉住 test/conftest.py 的清理只能用 os.replace（安全删除钩子按本轮
累计删除计数，第 50 次起会在 finally 抛异常，全套级联 105 条假红）。

执行：D:/python/python.exe -u test/_test_solver_budget_seed.py
"""
import inspect
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game import SliderMatrix                                    # noqa: E402
from solver import auto_solver as A                               # noqa: E402
from solver.auto_solver import auto_solve                         # noqa: E402
from solver.ml.fill_macro import build_game, _replay_apply       # noqa: E402
from solver.ml.invariants import is_solved_by_profile             # noqa: E402
import solver.ml.gap_solver as gs                                 # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, extra))
    if not cond:
        _failures.append(name)
    return bool(cond)


def src(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def make_coords(m, n, seed, attempts=150):
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=2)
    return frozenset(tuple(b.location) for b in g.blocks)


def fp(r):
    if isinstance(r, tuple):
        return repr((tuple(map(tuple, r[0])),
                     tuple(tuple(x) if x else None for x in (r[1] or []))))
    if isinstance(r, dict):
        return repr((r.get('type'),
                     tuple(map(tuple, r.get('actions') or []))))
    return repr(r)


def a5_of(acts, reps):
    reps = list(reps or [])
    return [tuple(a) + ((tuple(reps[i]),) if i < len(reps) and reps[i]
                        else (None,))
            for i, a in enumerate(acts)]


# ---------------------------------------------------------------- A 静态接线
_sig = inspect.signature(auto_solve).parameters
check('A1 auto_solve 同时保留 stage_budget 与新增 total_budget / rng_seed',
      all(k in _sig for k in ('stage_budget', 'total_budget', 'rng_seed')),
      str(list(_sig)))
_gui_src = src('gui/auto_solve.py')
check('A2 GUI 传 idle_budget（连续无进展停机）且不再用每候选/硬上限',
      "budget_kw['idle_budget']" in _gui_src
      and "budget_kw['stage_budget']" not in _gui_src
      and "budget_kw['total_budget']" not in _gui_src)
_gather_src = src('solver/ml/gather_solver.py')
check('A3 gather_solve 显式 seed 时改用局部 Random（不再吃全局状态）',
      'if stochastic or seed is not None:' in _gather_src
      and 'rng = random.Random(seed)' in _gather_src)
_hs_src = src('solver/hybrid_solver.py')
check('A4 hybrid_solve 有 gather_seed 且透传给 gather_solve',
      'gather_seed=None' in _hs_src and 'seed=gather_seed' in _hs_src)
_gs_src = src('solver/ml/gap_solver.py')
check('A5 补缺宏链透传 rng 到多空位驱动与填洞宏兜底',
      'rng=rng' in _gs_src
      and 'solve_multi_vacancy(coords, m, n, step, mode=' in _gs_src
      and 'segment_cb=segment_cb, rng=rng' in _gs_src)
_fm_src = src('solver/ml/fill_macro.py')
check('A6 填洞宏把 rng 从外层一路交给 solve_multi_void（不是半截接线）',
      "segment_cb, rng=kwargs.get('rng'))" in _fm_src
      and 'rng=rng,' in _fm_src
      and 'rng=None' in _fm_src
      and 'def _solve_fill_macro_inner(' in _fm_src)
_cf_src = src('test/conftest.py')
check('A7 conftest 运行态清理只用 os.replace、不含 os.remove',
      'os.replace(path,' in _cf_src and 'os.remove(path)' not in _cf_src)
check('A8 整轮预算的首候选让出比例仍存在',
      hasattr(A, '_TOTAL_SHARE_FIRST')
      and 0 < A._TOTAL_SHARE_FIRST < 1,
      str(getattr(A, '_TOTAL_SHARE_FIRST', None)))

# ---------------------------------------------------------------- B 可复现
_captured = []
_orig_vac = gs.solve_multi_vacancy


def _spy_vac(*a, **kw):
    _captured.append(kw.get('rng'))
    return _orig_vac(*a, **kw)


_c66 = make_coords(6, 6, 3)
gs.solve_multi_vacancy = _spy_vac
try:
    _r1 = auto_solve(build_game(_c66, 6, 6), 2,
                     stage_budget=3, rng_seed=42)
    _r2 = auto_solve(build_game(_c66, 6, 6), 2,
                     stage_budget=3, rng_seed=42)
finally:
    gs.solve_multi_vacancy = _orig_vac
check('B1 rng_seed=42 同局面两次解链逐位一致（6×6）',
      fp(_r1) == fp(_r2), '%s / %s' % (type(_r1).__name__,
                                       len((_r1[0] if isinstance(_r1, tuple)
                                            else _r1.get('actions') or []))))
check('B2 rng 确实注入到多空位驱动（不是被 **kwargs 吞掉的摆设）',
      len(_captured) >= 2
      and all(isinstance(r, random.Random) for r in _captured[:2]),
      'captured=%d' % len(_captured))
_c55 = make_coords(5, 5, 1001)
_r3 = auto_solve(build_game(_c55, 5, 5), 2, rng_seed=7)
_r4 = auto_solve(build_game(_c55, 5, 5), 2, rng_seed=7)
check('B3 另一个种子 / 另一尺寸同样可复现', fp(_r3) == fp(_r4))
_r5 = auto_solve(build_game(_c55, 5, 5), 2)   # 不传种子：旧行为仍可用
check('B4 不传 rng_seed 时保持旧行为且能正常返回',
      isinstance(_r5, (tuple, dict)), type(_r5).__name__)
# ⚠️ 填洞宏兜底路径原先半截接线：内部函数用了不存在的 kwargs，且外层
# 没把 rng 传下来 → 只有补缺宏多空位分支先走时看不出来，真走到就 NameError。
from solver.ml.fill_macro import solve_fill_macro              # noqa: E402
try:
    _rf = solve_fill_macro(build_game(_c55, 5, 5), 2,
                           rng=random.Random(1), time_budget=1.0)
    _fill_ok = isinstance(_rf, (tuple, dict))
except NameError as e:
    _fill_ok = False
    print('   [填洞宏兜底 NameError] %s' % e)
check('B5 填洞宏兜底路径接受 rng 且不抛 NameError', _fill_ok)

# ---------------------------------------------------------------- C 时间语义
_T = 1.5
_c77 = make_coords(7, 7, 3)


def timed(coords, m, n, kw):
    stages, marks = [], []

    def pcb(info):
        st = info.get('stage')
        if not marks or marks[-1][0] != st:
            marks.append((st, time.time()))

    def scb(s):
        stages.append(dict(s))
    t0 = time.time()
    r = auto_solve(build_game(coords, m, n), 2,
                   progress_callback=pcb, stage_cb=scb,
                   rng_seed=42, **kw)
    return r, time.time() - t0, stages, marks


def _replay_segments(coords0, m, n, stages):
    cur = coords0
    for s in stages:
        gg = build_game(cur, m, n)
        if not _replay_apply(gg, a5_of(s['actions'], s['reps']), m, n, 2):
            return False
        cur = frozenset(tuple(b.location) for b in gg.blocks)
        if cur != frozenset(s['end']):
            return False
    return bool(stages)


_old, _old_dt, _old_stages, _old_marks = timed(
    _c77, 7, 7, {'stage_budget': _T})
_new, _new_dt, _new_stages, _new_marks = timed(
    _c77, 7, 7, {'total_budget': _T})
check('C1 旧语义：每候选各吃一份，墙钟明显超过 1.6T',
      _old_dt > _T * 1.6, 'dt=%.2fs T=%.1fs' % (_old_dt, _T))
check('C2 新语义：整轮收在 1.5T 内（且不提前空转）',
      _new_dt < _T * 1.5 and _new_dt > _T * 0.5,
      'dt=%.2fs T=%.1fs' % (_new_dt, _T))
check('C3 新语义下第二候选仍启动（首候选没吃满整轮）',
      any('混合流水线' in s for s, _ in _new_marks),
      str([s for s, _ in _new_marks][-3:]))
check('C4 新语义下已播段逐段重放 end 与落点一致',
      _replay_segments(_c77, 7, 7, _new_stages),
      'segments=%d' % len(_new_stages))

if isinstance(_new, tuple):
    _end = build_game(_c77, 7, 7)
    _ok = _replay_apply(_end, a5_of(_new[0], _new[1]), 7, 7, 2)
    check('C5 若返回全解，整链确实复原',
          _ok and is_solved_by_profile(
              frozenset(tuple(b.location) for b in _end.blocks), 7, 7))
else:
    check('C5 未谎报全解（返回部分成果且段非空）',
          isinstance(_new, dict) and _new.get('type') in
          ('fill_partial', 'fill_fail') and len(_new_stages) > 0,
          str(_new.get('type')))

_r0 = auto_solve(build_game(_c55, 5, 5), 2, total_budget=0, rng_seed=42)
check('C6 total_budget=0 表示不限时、仍能正常求解',
      isinstance(_r0, (tuple, dict)), type(_r0).__name__)

print('==== %s（%d 项失败）' % ('全部通过' if not _failures else '有失败',
                            len(_failures)))
sys.exit(1 if _failures else 0)
