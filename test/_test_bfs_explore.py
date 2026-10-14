# -*- coding: utf-8 -*-
"""探测中等尺寸的状态数、不可逆性、性能。"""
import sys, os, time, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solver import table_core as tc


def explore(m, n, step):
    total = m * n
    goal = tc.goal_state(m, n)
    gH = tc.canonicalize(goal)
    dist = {gH: 0}
    frontier = [gH]
    d = 0
    t0 = time.time()
    states_processed = 0
    while frontier:
        d += 1
        nxt = []
        for h in frontier:
            B = set(tc.int_to_coords(h, total))
            t1 = time.time()
            for pH in tc.predecessors(B, m, n, step):
                if pH not in dist:
                    dist[pH] = d
                    nxt.append(pH)
            states_processed += 1
        frontier = nxt
        elapsed = time.time() - t0
        print(f"  层{d}: +{len(nxt)} 状态 (总{len(dist)})  累计{elapsed:.1f}s  速率{states_processed/elapsed:.0f}状态/秒", flush=True)
        if elapsed > 90:
            print("  超时停止", flush=True)
            break
    # 不可逆性：正向可达但反向未覆盖
    fwd_count = None
    only_fwd = None
    if len(dist) < 200000:
        gH2 = tc.canonicalize(goal)
        fdist = {gH2: 0}
        ffront = [gH2]
        while ffront:
            fnxt = []
            for h in ffront:
                B = set(tc.int_to_coords(h, total))
                for nb in tc.forward_neighbors(B, step, total):
                    if nb not in fdist:
                        fdist[nb] = 0
                        fnxt.append(nb)
            ffront = fnxt
        fwd_count = len(fdist)
        only_fwd = len(set(fdist) - set(dist))
    print(f"[{m}x{n} step={step}] 反向状态数={len(dist)} max_dist={d-1} 用时{time.time()-t0:.1f}s")
    if fwd_count is not None:
        print(f"   正向可达总数={fwd_count} 仅正向可达(不可解)={only_fwd}")
    return dist


if __name__ == '__main__':
    explore(3, 4, 2)
    explore(4, 4, 2)
