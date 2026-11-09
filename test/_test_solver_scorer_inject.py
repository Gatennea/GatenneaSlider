# -*- coding: utf-8 -*-
"""D1 护栏：打分 / 路由可注入接縫（2026-11-10）。

接縫本身不讓求解器變強，只把「換一個打分、換一個路由」從改搜索核心
降成換一個參數。所以本護欄釘死三件事：

  A. 靜態接線：scorer 從 auto_solve → hybrid_solve → guided_reduce_one
     整條鏈都在，route_fn 真的接上 gap_first，玩家側（gui/auto_solve）
     完全不傳這兩個參數。
  B. 等價性：預設 / 顯式 None / 注入「與 heuristic_parts 同值」的打分，
     GBFS 的 (path, expanded) 逐位一致；注入反向打分則確實改變行為
     （證明接縫不是裝飾）。
  C. 端到端：route_fn 真的改變兩候選先後，scorer 真的傳進
     hybrid_solve；查表命中時兩個參數都不影響結果。

真刀反向驗證（撤掉接線必須轉紅）見當日 archive 裡的
_reverse_scorer.py。執行：D:/python/python.exe -u test/_test_solver_scorer_inject.py
"""
import inspect
import os
import random
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import solver.auto_solver as auto  # noqa: E402
import solver.hybrid_solver as hs  # noqa: E402
import solver.search_core as sc  # noqa: E402
from game import SliderMatrix  # noqa: E402

SEEDS = (1, 7, 42, 100, 2026)
BUDGET = 3000
FAILURES = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        FAILURES.append(name)
    return ok


def cases():
    out = []
    for seed in SEEDS:
        random.seed(seed)
        g = SliderMatrix(4, 4)
        g.shuffle(4 * 4 * 10, 2)
        out.append(frozenset(tuple(b.location) for b in g.blocks))
    return out


def same_score(coords, m, n, step):
    return sc.heuristic_parts(coords, m, n, step)


def neg_score(coords, m, n, step):
    h, holes = sc.heuristic_parts(coords, m, n, step)
    return -h, holes


# ---------------- A. 靜態接線 ----------------
def static_checks():
    gsrc = inspect.getsource(sc.guided_reduce_one)
    hsrc = inspect.getsource(hs.hybrid_solve)
    asrc = inspect.getsource(auto.auto_solve)
    gui_src = open(os.path.join(ROOT, 'gui', 'auto_solve.py'),
                   encoding='utf-8').read()

    check('A1 guided_reduce_one 有 scorer 且預設 None',
          'scorer' in inspect.signature(sc.guided_reduce_one).parameters
          and inspect.signature(sc.guided_reduce_one)
          .parameters['scorer'].default is None)
    check('A2 預設分支沿用原 heuristic_parts / 起點只取洞數',
          'if scorer is None:' in gsrc
          and 'score = heuristic_parts' in gsrc
          and 'h0 = len(fast_window(start, m, n)[1])' in gsrc
          and 'score(new, m, n, step)' in gsrc)
    check('A3 hybrid_solve 接上 scorer 並傳給 GBFS',
          'scorer' in inspect.signature(hs.hybrid_solve).parameters
          and 'scorer=scorer' in hsrc)
    check('A4 auto_solve 接上 scorer 與 route_fn',
          all(k in inspect.signature(auto.auto_solve).parameters
              for k in ('scorer', 'route_fn'))
          and 'route_fn(len(holes)' in asrc
          and 'scorer=scorer' in asrc)
    check('A5 玩家側 GUI 完全不傳這兩個參數',
          'scorer=' not in gui_src and 'route_fn=' not in gui_src)
    check('A6 舊呼叫仍由 **_kwargs 相容', '**_kwargs' in asrc)


# ---------------- B. 等價性與可替換性 ----------------
def equivalence_checks(board_cases):
    same_ok, neg_diff, spy_used = 0, 0, 0
    for coords in board_cases:
        p0, e0 = sc.guided_reduce_one(coords, 4, 4, 2, budget=BUDGET)
        p1, e1 = sc.guided_reduce_one(coords, 4, 4, 2, budget=BUDGET,
                                      scorer=same_score)
        p2, e2 = sc.guided_reduce_one(coords, 4, 4, 2, budget=BUDGET,
                                      scorer=neg_score)
        same_ok += ((p1, e1) == (p0, e0))
        neg_diff += ((p2, e2) != (p0, e0))

        calls = []

        def spy(c, m, n, s):
            calls.append(c)
            return sc.heuristic_parts(c, m, n, s)

        p3, e3 = sc.guided_reduce_one(coords, 4, 4, 2, budget=BUDGET,
                                      scorer=spy)
        # >1 而非 >0：起點取值本來就會呼叫一次，必須證明每個新節點
        # 的入堆排序也吃了注入打分（撤掉 score(new,...) 這條就會轉紅）
        spy_used += (len(calls) > 1 and (p3, e3) == (p0, e0))

    check('B1 注入打分對每個新節點生效（不只起點）',
          spy_used == len(board_cases), f'{spy_used}/{len(board_cases)}')
    check('B2 顯式注入同值打分與預設逐位一致',
          same_ok == len(board_cases), f'{same_ok}/{len(board_cases)}')
    check('B3 注入反向打分確實改變搜索行為',
          neg_diff >= len(board_cases) - 1,
          f'{neg_diff}/{len(board_cases)} 局不同')


# ---------------- C. 端到端 ----------------
def puzzle():
    random.seed(3)
    g = SliderMatrix(4, 4)
    g.shuffle(4 * 4 * 10, 2)
    return g


def order_with(route_fn, extra=None):
    calls = []
    kw = {'route_fn': route_fn}
    if extra:
        kw.update(extra)

    def gap(*a, **k):
        calls.append('gap')
        return False

    seen = {}

    def hybrid(*a, **k):
        calls.append('hybrid')
        seen.update(k)
        return False

    with mock.patch.object(auto, 'table_solve', return_value=None), \
            mock.patch.object(auto, 'solve_gap_macro', side_effect=gap), \
            mock.patch.object(auto, 'hybrid_solve', side_effect=hybrid):
        auto.auto_solve(puzzle(), 2, **kw)
    return calls, seen


def e2e_checks():
    o_true, _ = order_with(lambda holes, *a: True)
    o_false, _ = order_with(lambda holes, *a: False)
    check('C1 route_fn 真的改變兩候選先後',
          o_true == ['gap', 'hybrid'] and o_false == ['hybrid', 'gap'],
          f'{o_true} vs {o_false}')

    marker = object()
    _o, seen = order_with(lambda holes, *a: False, extra={'scorer': marker})
    check('C2 scorer 真的透傳到 hybrid_solve',
          seen.get('scorer') is marker)

    # 用打樁的查表命中確保兩次都秒回、結果確定，不摻入求解隨機漂移
    with mock.patch.object(auto, 'table_solve', return_value=([], [])):
        r0 = auto.auto_solve(puzzle(), 2)
        r1 = auto.auto_solve(puzzle(), 2, scorer=neg_score,
                             route_fn=lambda holes, *a: True)
    check('C3 查表命中時注入參數不影響結果', r0 == r1,
          f'{type(r0).__name__}')


def main():
    static_checks()
    equivalence_checks(cases())
    e2e_checks()
    print('==== %s（%d 項失敗）' % (
        '全部通過' if not FAILURES else '有失敗', len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
