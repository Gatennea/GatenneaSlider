# -*- coding: utf-8 -*-
r"""use_fill 消融开关测试（2026-10-16）。

锁定三件事：
  ① use_fill=False 能跑完且返回协议合法（tuple / False / None 之一）；
  ② use_fill=True 与不传参数（缺省）行为一致——求解器确定性 + 缺省未被改；
  ③ auto_solve(hybrid_use_fill=...) 正确透传到 hybrid_solve(use_fill=...)；
     hybrid_solve_with_table 经 **kwargs 自然透传（monkeypatch 捕获实参）。

注意：on/off 的**行为差异**（耗时/成功率）由 experiments/script_fillin_ablation.py
的消融数据回答，不在本单测范围——本测试只锁「开关本身没坏、默认没变」。

不依赖 pygame。运行：
  D:\python\python.exe experiments/script_test_use_fill_flag.py
"""
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FIXTURE = os.path.join(_ROOT, 'experiments', 'fixtures', '死局-4_4_2-1.json')


def _load_fixture_game():
    d = json.load(open(FIXTURE, encoding='utf-8'))
    snap = d['history']['snapshots'][d['history']['history_index']]
    b = snap['bounds']
    coords = frozenset((r + b['min_row'], c + b['min_col'])
                       for r, row in enumerate(snap['matrix'])
                       for c, v in enumerate(row) if v)
    from solver.ml.fill_macro import build_game
    return build_game(coords, d['puzzle']['m'], d['puzzle']['n']), d['puzzle']['step']


def test_flag_runs_and_default_unchanged(budget=20.0):
    """① 三态协议合法；② on == 缺省（确定性 + 默认未变）。"""
    from solver.hybrid_solver import hybrid_solve

    def run(**kw):
        g, step = _load_fixture_game()
        t0 = time.perf_counter()
        cc = lambda: time.perf_counter() - t0 >= budget
        return hybrid_solve(g, step, cancel_check=cc, **kw)

    r_off = run(use_fill=False)
    r_default = run()
    r_on = run(use_fill=True)
    for tag, r in (('off', r_off), ('default', r_default), ('on', r_on)):
        assert r is None or isinstance(r, (tuple, bool)), \
            'use_fill 测试：%s 返回协议非法 %r' % (tag, type(r).__name__)
    assert r_on == r_default, \
        'use_fill=True 与缺省行为不一致（默认被改动？）'
    print('[flag] ① use_fill off/default/on 协议合法；'
          '② on == default（确定性，默认未变）')


def test_passthrough():
    """③ auto_solve / hybrid_solve_with_table 的 use_fill 透传。"""
    import solver.auto_solver as A
    import solver as S
    from solver import hybrid_solve_with_table
    from experiments import harness as H

    snap = H.gen_state(5, 5, 2, 4242)   # 5×5 无表，必落到路由/混合
    g = H.load_game(snap)

    captured = {}
    orig = (A.hybrid_solve, A.solve_gap_macro, A.table_solve, S.hybrid_solve)
    A.hybrid_solve = lambda gm, stp, **kw: captured.update(kw) or False
    A.solve_gap_macro = lambda *a, **kw: {'type': 'fill_fail', 'reason': 'test'}
    A.table_solve = lambda *a, **kw: None
    S.hybrid_solve = A.hybrid_solve
    try:
        A.auto_solve(g, 2, hybrid_use_fill=False)
        assert captured.get('use_fill') is False, \
            'auto_solve 未透传 use_fill=False'
        captured.clear()
        A.auto_solve(g, 2)
        assert captured.get('use_fill') is True, \
            'auto_solve 缺省未传 use_fill=True'
        captured.clear()
        hybrid_solve_with_table(g, 2, use_fill=False)
        assert captured.get('use_fill') is False, \
            'hybrid_solve_with_table 未透传 use_fill'
    finally:
        (A.hybrid_solve, A.solve_gap_macro, A.table_solve,
         S.hybrid_solve) = orig
    print('[flag] ③ auto_solve / with_table 透传正确（缺省 True）')


if __name__ == '__main__':
    test_flag_runs_and_default_unchanged()
    test_passthrough()
    print('PASS')
