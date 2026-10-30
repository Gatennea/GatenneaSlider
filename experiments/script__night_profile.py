# -*- coding: utf-8 -*-
"""深夜优化·第 1 步（精准版）：定位当前求解链真热点。

两段：
  A. 墙钟基线：hybrid_solve 整局计时（6×6 / 5×5，无表尺寸），逐局打印——
     同时回答「玩家按求解要等多久」。
  B. cProfile：gather_solve 封 40 步（热路径采样足够，不必等全程收敛），
     6×6 / 5×5 / 8×8 各一局。

用法：
    D:/python/python.exe -u experiments/script__night_profile.py > experiments/_night_profile_out.txt 2>&1
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
from solver.hybrid_solver import hybrid_solve  # noqa: E402
from solver.ml.gather_solver import gather_solve  # noqa: E402

SEED = 20261018


def phase_a():
    print('==== A. 墙钟基线：hybrid_solve 整局 ====')
    for (m, n, s) in [(6, 6, 2), (5, 5, 2)]:
        for i in range(2):
            snap = H.gen_state(m, n, s, SEED + i)
            g = H.load_game(snap)
            t0 = time.perf_counter()
            r = hybrid_solve(g, s)
            dt = time.perf_counter() - t0
            acts = r[0] if isinstance(r, tuple) else (r or [])
            print('  %dx%d s=%d #%d：%.1fs，%d 步，reason=%s'
                  % (m, n, s, i, dt, len(acts) if acts else -1,
                     (r[1] if isinstance(r, tuple) and len(r) > 1 else '?')))
            sys.stdout.flush()


def phase_b():
    print('\n==== B. cProfile：gather_solve 封 40 步 ====')
    for (m, n, s) in [(6, 6, 2), (5, 5, 2), (8, 8, 2)]:
        snap = H.gen_state(m, n, s, SEED)
        g = H.load_game(snap)
        pr = cProfile.Profile()
        t0 = time.perf_counter()
        pr.enable()
        r = gather_solve(g, s, max_steps=40)
        pr.disable()
        dt = time.perf_counter() - t0
        print('  %dx%d s=%d：40 步耗时 %.2fs（含 profile 开销），reason=%s'
              % (m, n, s, dt, r.get('reason')))
        sys.stdout.flush()
        s_io = io.StringIO()
        ps = pstats.Stats(pr, stream=s_io)
        ps.sort_stats('tottime')
        ps.print_stats(18)
        print(s_io.getvalue())
        sys.stdout.flush()


if __name__ == '__main__':
    phase_a()
    phase_b()
