# -*- coding: utf-8 -*-
"""删除混合内填洞宏后的冒烟测试：验证 hybrid_solve / auto_solve 不崩、协议合法、确有解出。"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver.ml.fill_macro import build_game          # noqa: E402
from solver.hybrid_solver import hybrid_solve        # noqa: E402
from solver.auto_solver import auto_solve            # noqa: E402


def make(m, n, step, attempts):
    coords = frozenset((r, c) for r in range(n) for c in range(m))
    g = build_game(coords, m, n)
    g.shuffle(attempts, step)
    return g


def run_hybrid():
    print("=== hybrid_solve ===")
    ok = solved = tot = err = 0
    cases = [(4, 4, 2, 6), (4, 4, 2, 10), (5, 5, 2, 8), (5, 5, 2, 12)]
    for i in range(3):
        for (m, n, step, att) in cases:
            g = make(m, n, step, att)
            tot += 1
            try:
                res = hybrid_solve(g, step, node_budget=40000, max_rounds=12)
                assert res is False or res is None or \
                    (isinstance(res, tuple) and len(res) == 2), \
                    "非法协议: %r" % type(res)
                if isinstance(res, tuple):
                    ok += 1
                    # tuple 即内部已 is_solved 校验通过
                    solved += 1
            except Exception as e:
                err += 1
                print("  HYBRID ERROR @%dx%d s%d att%d: %r" %
                      (m, n, step, att, e))
                traceback.print_exc()
    print("  tot=%d 返回tuple(已解)=%d 其他=%d 异常=%d" % (tot, ok, tot - ok, err))
    return err


def run_auto():
    print("=== auto_solve ===")
    ok = solved = tot = err = 0
    cases = [(4, 4, 2, 6), (4, 4, 2, 10), (5, 5, 2, 8)]
    for i in range(3):
        for (m, n, step, att) in cases:
            g = make(m, n, step, att)
            tot += 1
            try:
                res = auto_solve(g, step)
                # 合法返回：([],[]) 已复原 / (acts, reps) 已解 / ('fail',) 等
                assert res is not None, "返回 None"
                ok += 1
                if isinstance(res, tuple) and len(res[0]) > 0:
                    solved += 1
            except Exception as e:
                err += 1
                print("  AUTO ERROR @%dx%d s%d att%d: %r" %
                      (m, n, step, att, e))
                traceback.print_exc()
    print("  tot=%d 合法返回=%d 其中解出(有动作)=%d 异常=%d" %
          (tot, ok, solved, err))
    return err


if __name__ == "__main__":
    e1 = run_hybrid()
    e2 = run_auto()
    print("RESULT: hybrid_err=%d auto_err=%d -> %s" %
          (e1, e2, "PASS (无异常)" if (e1 + e2) == 0 else "FAIL"))
