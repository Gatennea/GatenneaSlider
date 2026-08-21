# -*- coding: utf-8 -*-
"""profile predecessors() 在 4x4 step2 上的耗时分布。"""
import sys, os, time, cProfile, pstats, io, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solver import table_core as tc


def get_states(m, n, step, count):
    total = m * n
    goal = tc.goal_state(m, n)
    gH = tc.canonicalize(goal)
    dist = {gH: 0}
    frontier = [gH]
    states = [goal]
    while frontier and len(states) < count:
        nxt = []
        for h in frontier:
            B = set(tc.int_to_coords(h, total))
            for pH in tc.predecessors(B, m, n, step):
                if pH not in dist:
                    dist[pH] = 0
                    nxt.append(pH)
                    states.append(set(tc.int_to_coords(pH, total)))
        frontier = nxt
    return states


def main():
    m, n, step = 4, 4, 2
    total = m * n
    print("采集状态中...", flush=True)
    states = get_states(m, n, step, 300)
    print(f"采集到 {len(states)} 个状态", flush=True)

    # 计时
    t0 = time.time()
    n_preds = 0
    for s in states:
        n_preds += len(tc.predecessors(s, m, n, step))
    dt = time.time() - t0
    print(f"总耗时 {dt:.2f}s  状态数={len(states)}  每状态={dt/len(states)*1000:.1f}ms  前驱总数={n_preds}", flush=True)

    # profile
    pr = cProfile.Profile()
    pr.enable()
    for s in states[:100]:
        tc.predecessors(s, m, n, step)
    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('tottime')
    ps.print_stats(15)
    print(s.getvalue())


if __name__ == '__main__':
    main()
