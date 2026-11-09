# -*- coding: utf-8 -*-
"""D2 第二輪護欄：終止判據接縫 + 機制型打分（2026-11-10）。

三件事要釘死：

  A. 靜態接線：stop_fn 從 auto_solve → hybrid_solve →
     guided_reduce_one 整條都在；玩家側（gui/auto_solve）完全不傳；
     出堆判據真的呼叫 stop_fn，且**起點不呼叫**。
  B. 等價性：stop_fn=None（無論有沒有 scorer）與舊版逐位一致；
     stop_fn 注入後確實接管終止（強制 True / False 兩端都要能看出差別）；
     起點不被誤判（強制 True 時回傳段長 1、不是 0）。
  C. 機制型打分不看錶：`experiments/script_bench_progress_scorer.py`
     的四個 scorer 函數體不得出現查表／canonicalize／load_table，
     且在表外座標、查表被禁用的情況下仍能算出有限整數。

真刀反向驗證（撤接線必須轉紅）見當日 archive 裡的
_reverse_stop_fn.py。執行：
D:/python/python.exe -u test/_test_solver_progress_scorer.py
"""
import ast
import importlib.util
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

BENCH = os.path.join(ROOT, 'experiments',
                     'script_bench_progress_scorer.py')
SEEDS = (1, 7, 42, 100, 2026)
BUDGET = 3000
FAILURES = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + (f'  {detail}' if detail else ''))
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


def load_bench():
    spec = importlib.util.spec_from_file_location('bench_progress', BENCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------- A. 靜態接線 ----------------
def static_checks():
    gsrc = inspect.getsource(sc.guided_reduce_one)
    hsrc = inspect.getsource(hs.hybrid_solve)
    asrc = inspect.getsource(auto.auto_solve)
    gui_src = open(os.path.join(ROOT, 'gui', 'auto_solve.py'),
                   encoding='utf-8').read()

    for label, fn in (('guided_reduce_one', sc.guided_reduce_one),
                       ('hybrid_solve', hs.hybrid_solve),
                       ('auto_solve', auto.auto_solve)):
        p = inspect.signature(fn).parameters.get('stop_fn')
        check('A1 %s 有 stop_fn 且預設 None' % label,
              p is not None and p.default is None)
    check('A2 出堆判據真的呼叫 stop_fn 且起點除外',
          'stop_fn(_f, holes)' in gsrc and 'cid == 0' in gsrc
          and 'holes < h0' in gsrc)
    check('A3 hybrid_solve 把 stop_fn 傳進 GBFS',
          'stop_fn=stop_fn' in hsrc)
    check('A4 auto_solve 把 stop_fn 傳進 hybrid_solve',
          'stop_fn=stop_fn' in asrc)
    check('A5 玩家側 GUI 不傳 stop_fn', 'stop_fn=' not in gui_src)
    check('A6 舊呼叫仍由 **_kwargs 相容', '**_kwargs' in asrc)


# ---------------- B. 等價性與接管 ----------------
def always_true(v, holes):
    return True


def always_false(v, holes):
    return False


def equivalence_checks(board_cases):
    same, true_ok, false_ok, spy_ok = 0, 0, 0, 0
    for coords in board_cases:
        p0, e0 = sc.guided_reduce_one(coords, 4, 4, 2, budget=BUDGET)
        p1, e1 = sc.guided_reduce_one(coords, 4, 4, 2, budget=BUDGET,
                                      stop_fn=None)
        same += ((p1, e1) == (p0, e0))
        # D1 的「同值打分」與 stop_fn=None 併用也必須逐位一致
        p2, e2 = sc.guided_reduce_one(
            coords, 4, 4, 2, budget=BUDGET,
            scorer=lambda c, m, n, s: sc.heuristic_parts(c, m, n, s),
            stop_fn=None)
        same += ((p2, e2) == (p0, e0))

        pt, et = sc.guided_reduce_one(coords, 4, 4, 2, budget=BUDGET,
                                      stop_fn=always_true)
        # 起點跳過 ⇒ 第一個展開節點才停，段長 1；起點本身也算 expanded
        true_ok += (pt is not None and len(pt) == 1 and et == 1)
        pf, ef = sc.guided_reduce_one(coords, 4, 4, 2, budget=BUDGET,
                                      stop_fn=always_false)
        false_ok += (pf is None and ef > 0)

        calls = []

        def spy(v, holes):
            calls.append((v, holes))
            return False

        sc.guided_reduce_one(coords, 4, 4, 2, budget=BUDGET, stop_fn=spy)
        spy_ok += (len(calls) > 1)

    check('B1 stop_fn=None 與預設逐位一致（含 scorer 併用）',
          same == 2 * len(board_cases), f'{same}/{2 * len(board_cases)}')
    check('B2 stop_fn=True 時第一個展開節點即停、段長 1',
          true_ok == len(board_cases), f'{true_ok}/{len(board_cases)}')
    check('B3 stop_fn=False 時找不到路徑、節點照樣展開',
          false_ok == len(board_cases), f'{false_ok}/{len(board_cases)}')
    check('B4 stop_fn 對每個出堆節點都被呼叫（不只起點）',
          spy_ok == len(board_cases), f'{spy_ok}/{len(board_cases)}')


def progress_stop_checks(board_cases, bench):
    """打分 + 終止判據一起換：終態打分必須真的小於起點，路徑可重放。"""
    ok = 0
    for coords in board_cases:
        fn = bench.scorer_pair
        base = fn(coords, 4, 4, 2)[0]
        path, _ex = sc.guided_reduce_one(
            coords, 4, 4, 2, budget=BUDGET,
            scorer=fn, stop_fn=lambda v, h, b=base: v < b)
        if path is None:
            continue
        cur = frozenset(coords)
        good = True
        for act, rep in path:
            nxt = next((nb for nb, a, r in sc.expand(cur, 2)
                        if a == act and r == rep), None)
            if nxt is None:
                good = False
                break
            cur = nxt
        ok += (good and fn(cur, 4, 4, 2)[0] < base)
    check('B5 打分變小終止：路徑合法且終態打分確實變小',
          ok == len(board_cases), f'{ok}/{len(board_cases)}')


def e2e_checks():
    seen = {}

    def hybrid(*a, **k):
        seen.update(k)
        return False

    random.seed(3)
    g = SliderMatrix(4, 4)
    g.shuffle(4 * 4 * 10, 2)
    with mock.patch.object(auto, 'table_solve', return_value=None), \
            mock.patch.object(auto, 'solve_gap_macro', return_value=False), \
            mock.patch.object(auto, 'hybrid_solve', side_effect=hybrid):
        auto.auto_solve(g, 2, stop_fn=always_false)
    check('C1 stop_fn 真的透傳到 hybrid_solve',
          seen.get('stop_fn') is always_false)


# ---------------- C. 機制型打分不看錶 ----------------
FORBIDDEN = ('load_table', 'canonicalize', 'table[', 'table.get',
             'table_solver', 'checkpoint')


def scorer_purity_checks(bench):
    tree = ast.parse(open(BENCH, encoding='utf-8').read())
    fnodes = {n.name: n for n in tree.body
              if isinstance(n, ast.FunctionDef)}
    bad = []
    for name, fn in bench.SCORERS.items():
        node = fnodes.get(fn.__name__)
        body = ast.get_source_segment(
            open(BENCH, encoding='utf-8').read(), node) if node else ''
        if body is None or any(tok in body for tok in FORBIDDEN):
            bad.append(name)
    check('D1 四個 scorer 函數體都沒有查表／canonicalize',
          not bad, f'髒：{bad}')

    # 表外座標（隨便一個 5×5 盤）也要算得出有限整數，且不碰查表
    outside = frozenset((r, c) for r in range(5) for c in range(5))
    vals = {}
    with mock.patch.object(bench, 'load_table',
                           side_effect=AssertionError('不該查表')):
        for name, fn in bench.SCORERS.items():
            v, holes = fn(outside, 4, 4, 2)
            vals[name] = (v, holes)
    check('D2 查表被禁用時四個打分仍能算出有限整數',
          all(isinstance(v, (int, float)) and isinstance(h, int)
              for v, h in vals.values()),
          str({k: v for k, v in vals.items()}))

    # 一對一配對不能比基線更低估（同盤配對成本 ≥ 各自取最近洞之和）
    rng = random.Random(9)
    pool = [(r, c) for r in range(-3, 8) for c in range(-3, 8)]
    ok = 0
    # 固定恰好 16 格（與 m*n 相同），否則 window 的 holes/protr
    # 數量不相等，打分就失去可比性（初版用 random()<0.35 抽，
    # 20 次裡一次都沒抽到 16 格，護欄假紅 0/20）。
    for _ in range(20):
        coords = frozenset(rng.sample(pool, 16))
        base = bench.scorer_default(coords, 4, 4, 2)[0]
        pair = bench.scorer_pair(coords, 4, 4, 2)[0]
        ok += (pair >= base)
    check('D3 一對一配對不低於基線（消除搶洞低估、不引入新低估）',
          ok == 20, f'{ok}/20 隨機盤')


def main():
    bench = load_bench()
    static_checks()
    board_cases = cases()
    equivalence_checks(board_cases)
    progress_stop_checks(board_cases, bench)
    e2e_checks()
    scorer_purity_checks(bench)
    print('==== %s（%d 項失敗）' % (
        '全部通過' if not FAILURES else '有失敗', len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
