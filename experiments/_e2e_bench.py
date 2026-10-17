# -*- coding: utf-8 -*-
"""端到端基准：同一批局面，测 gather 段 / GBFS 段 / 混合整链墙钟。

本脚本在基线 worktree（HEAD）与优化后工作区各跑一遍，比较同种子同局面的
耗时。用法：D:/python/python.exe -u _e2e_bench.py <tag>
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(ROOT))  # 兼容腳本位於 experiments/ 子目錄

from experiments import harness as H
from solver.ml.gather_solver import gather_solve
from solver.search_core import guided_reduce_one

SEED = 20261018
TAG = sys.argv[1] if len(sys.argv) > 1 else '?'


def gen(m, n, s, i):
    return H.gen_state(m, n, s, SEED + i)


def bench_gather(m, n, s, i, steps=40):
    snap = gen(m, n, s, i)
    g = H.load_game(snap)
    t0 = time.perf_counter()
    r = gather_solve(g, s, max_steps=steps)
    dt = time.perf_counter() - t0
    coords = frozenset((b.location[0], b.location[1]) for b in g.blocks)
    return dt, len(coords), r.get('reason')


def bench_gbfs(m, n, s, i, gather_steps=25, budget=2000):
    snap = gen(m, n, s, i)
    g = H.load_game(snap)
    gather_solve(g, s, max_steps=gather_steps)
    coords = frozenset((b.location[0], b.location[1]) for b in g.blocks)
    t0 = time.perf_counter()
    path, used = guided_reduce_one(coords, m, n, s, budget=budget)
    return time.perf_counter() - t0, used, bool(path)


def bench_hybrid(m, n, s, i):
    from solver.hybrid_solver import hybrid_solve
    snap = gen(m, n, s, i)
    g = H.load_game(snap)
    t0 = time.perf_counter()
    r = hybrid_solve(g, s)
    return time.perf_counter() - t0, (len(r[0]) if isinstance(r, tuple) else -1)


def best_of(fn, reps, *a, **kw):
    """跑 reps 次取最小值（CPU 绑定，min 对漂移稳健）。"""
    best = None
    out = None
    for _ in range(reps):
        out = fn(*a, **kw)
        if best is None or out[0] < best:
            best = out[0]
    return best, out


def main():
    print('==== %s ====' % TAG)
    for (m, n, s) in [(6, 6, 2), (8, 8, 2)]:
        for i in range(2):
            t, (_, nblocks, reason) = best_of(bench_gather, 5, m, n, s, i)
            print('  gather  %dx%d s=%d #%d：%.3fs（%d 块，%s）'
                  % (m, n, s, i, t, nblocks, reason))
            sys.stdout.flush()
    for (m, n, s) in [(6, 6, 2), (8, 8, 2)]:
        t, (_, used, got) = best_of(bench_gbfs, 2, m, n, s, 0)
        print('  gbfs    %dx%d s=%d #0：%.3fs（展開 %d 節點，path=%s）'
              % (m, n, s, t, used, got))
        sys.stdout.flush()
    for i in range(2):
        t, (_, steps) = best_of(bench_hybrid, 1, 5, 5, 2, i)
        print('  hybrid  5x5 s=2 #%d：%.2fs（%d 步）' % (i, t, steps))
        sys.stdout.flush()


if __name__ == '__main__':
    main()
