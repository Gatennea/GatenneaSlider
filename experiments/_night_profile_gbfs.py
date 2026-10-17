# -*- coding: utf-8 -*-
"""深夜优化·第 2 步：profile guided_reduce_one（GBFS 段），确认热点。

用法：
    D:/python/python.exe -u experiments/_night_profile_gbfs.py
"""
import cProfile
import io
import os
import pstats
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from experiments import harness as H  # noqa: E402
from solver.search_core import guided_reduce_one  # noqa: E402

SEED = 20261018


def main():
    # 6×6 中局：先聚拢若干步造一个「有缺口」的局面，再对 GBFS 段做 profile
    snap = H.gen_state(6, 6, 2, SEED)
    g = H.load_game(snap)
    from solver.ml.gather_solver import gather_solve
    r = gather_solve(g, 2, max_steps=25)
    coords = frozenset((b.location[0], b.location[1]) for b in g.blocks)
    print('聚拢 25 步后局面：%d 块' % len(coords))

    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    path, used = guided_reduce_one(coords, 6, 6, 2, budget=3000)
    pr.disable()
    dt = time.perf_counter() - t0
    print('guided_reduce_one budget=3000：%.2fs，展开 %d 节点，path=%s'
          % (dt, used, '有' if path else '无'))
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s)
    ps.sort_stats('tottime')
    ps.print_stats(16)
    print(s.getvalue())


if __name__ == '__main__':
    main()
