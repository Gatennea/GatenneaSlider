# -*- coding: utf-8 -*-
"""实验5：残局真实剩余步数（并行反向 BFS + 目标命中）。

对指定种子：梯度聚拢 → 取残局规范 key 作为目标；
多进程反向 BFS，报告每个目标在第几层被命中（=真实最短剩余步数）。
"""
import argparse
import os
import time
from multiprocessing import Pool

from experiments import harness as H
from solver import table_core as TC


def _pred_worker(args):
    key, m, n, step = args
    coords = frozenset(TC.int_to_coords(key, m * n))
    return list(TC.predecessors(coords, m, n, step))


def gather_targets(seeds, m, n, step):
    from solver.ml.gather_solver import gradient_gather
    targets = {}
    for s in seeds:
        snap = H.gen_state(m, n, step, s)
        g = H.load_game(snap)
        r = gradient_gather(g, step)
        key = TC.canonicalize(H.coords_of(g))
        targets[key] = s
        print(f"  目标 seed={s} key={key} solved={g.is_solved()} "
              f"reason={r['reason']}")
    return targets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='1000,1003')
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--depth', type=int, default=9)
    ap.add_argument('--procs', type=int, default=min(8, os.cpu_count() or 4))
    ap.add_argument('--time', type=float, default=900.0)
    args = ap.parse_args()

    m, n, st = args.configs.split('x')
    m, n, st = int(m), int(n), int(st)
    seeds = [int(x) for x in args.seeds.split(',')]

    print('计算聚拢残局目标：')
    targets = gather_targets(seeds, m, n, st)

    goal_key = TC.canonicalize(TC.goal_state(m, n))
    visited = {goal_key}
    frontier = [goal_key]
    found = {}
    t0 = time.time()
    pool = Pool(processes=args.procs)
    try:
        for d in range(1, args.depth + 1):
            work = [(k, m, n, st) for k in frontier]
            results = pool.map(_pred_worker, work, chunksize=4)
            new = set()
            for r in results:
                new.update(r)
            new -= visited
            visited |= new
            frontier = list(new)
            dt = time.time() - t0
            for tk, seed in targets.items():
                if tk in visited and tk not in found:
                    found[tk] = d
            print(f"  深度{d}: 新增{len(new):>8} 累计{len(visited):>9} "
                  f"{dt:>7.1f}s 命中={ {s: found[k] for k,s in targets.items() if k in found} }")
            if len(found) == len(targets):
                break
            if not new or dt > args.time:
                break
    finally:
        pool.close()
        pool.join()

    print('\n== 结果 ==')
    for tk, seed in targets.items():
        print(f"  seed={seed}: 真实最短剩余步数 = {found.get(tk, '>%d（未命中）' % args.depth)}")


if __name__ == '__main__':
    main()
