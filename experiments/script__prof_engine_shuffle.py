"""定位 EngineGame.shuffle 的性能热点（老引擎同参数对照）。"""
import cProfile
import io
import pstats
import sys
import time

sys.path.insert(0, '.')

import engine.config as ecfg
from puzzle_types import create_puzzle


def bench(kind, m, n, step, enabled, attempts, rounds=5):
    ecfg.set_enabled(enabled)
    g = create_puzzle(m, n, step, kind)
    # 预热
    g.shuffle(attempts, step, 0.0, None)
    t0 = time.perf_counter()
    for _ in range(rounds):
        g.shuffle(attempts, step, 0.0, None)
    dt = (time.perf_counter() - t0) / rounds * 1000
    print(f"{'ENGINE' if enabled else 'OLD   '} {kind} {m}x{n} s{step} "
          f"attempts={attempts}: {dt:.1f} ms/shuffle  ({type(g).__name__})")
    return g


def prof(kind, m, n, step, attempts, rounds=3):
    ecfg.set_enabled(True)
    g = create_puzzle(m, n, step, kind)
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(rounds):
        g.shuffle(attempts, step, 0.0, None)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(18)
    print(s.getvalue())


if __name__ == '__main__':
    for (m, n, att) in ((4, 4, 30), (6, 6, 60)):
        bench('square', m, n, 2, False, att)
        bench('square', m, n, 2, True, att)
    print('=' * 70)
    prof('square', 6, 6, 2, 60)
