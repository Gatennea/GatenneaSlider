# -*- coding: utf-8 -*-
"""并行限深反向建表器。

产出与 build_table 相同的 solver/data/{m}_{n}_{step}/table.pkl
（dict: 规范key -> 距还原最短步数），但只建到 max_depth，且多进程并行、
逐层写检查点可续建。用于"最后一公里"局部表，而非全状态空间。
"""
import argparse
import json
import os
import pickle
import time
from multiprocessing import Pool

from solver import table_core as TC


def _pred_worker(args):
    key, m, n, step = args
    coords = frozenset(TC.int_to_coords(key, m * n))
    return list(TC.predecessors(coords, m, n, step))


def data_paths(m, n, step):
    d = os.path.join(os.path.dirname(os.path.abspath(TC.__file__)),
                     'data', f'{m}_{n}_{step}')
    return d, os.path.join(d, 'table.pkl'), os.path.join(d, 'meta.json'), \
        os.path.join(d, 'checkpoint.pkl')


def build(m, n, step, max_depth, procs):
    data_dir, table_path, meta_path, ckpt_path = data_paths(m, n, step)
    os.makedirs(data_dir, exist_ok=True)

    goal_key = TC.canonicalize(TC.goal_state(m, n))
    dist = {goal_key: 0}
    frontier = [goal_key]
    start_depth = 1

    if os.path.exists(ckpt_path):
        with open(ckpt_path, 'rb') as f:
            ck = pickle.load(f)
        dist, frontier, start_depth = ck['dist'], ck['frontier'], ck['depth']
        print(f"从检查点续建：深度 {start_depth}，已 {len(dist)} 状态")

    t0 = time.time()
    pool = Pool(processes=procs)
    try:
        for d in range(start_depth, max_depth + 1):
            work = [(k, m, n, step) for k in frontier]
            results = pool.map(_pred_worker, work, chunksize=4)
            new = set()
            for r in results:
                new.update(r)
            new = [k for k in new if k not in dist]
            for k in new:
                dist[k] = d
            frontier = new
            dt = time.time() - t0
            print(f"  深度{d}: 新增{len(new):>8} 累计{len(dist):>9} "
                  f"{dt:>8.1f}s", flush=True)
            with open(ckpt_path, 'wb') as f:
                pickle.dump({'dist': dist, 'frontier': frontier,
                             'depth': d + 1}, f)
            if not new:
                print("  （已穷尽）")
                break
    finally:
        pool.close()
        pool.join()

    with open(table_path, 'wb') as f:
        pickle.dump(dist, f)
    distrib = {}
    for v in dist.values():
        distrib[v] = distrib.get(v, 0) + 1
    meta = {'m': m, 'n': n, 'step': step, 'max_distance': max(dist.values()),
            'capped_depth': max_depth, 'total_states': len(dist),
            'distance_distribution': {str(k): v for k, v in distrib.items()},
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S')}
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"\n已写出 {table_path}（{len(dist)} 状态）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('m', type=int)
    ap.add_argument('n', type=int)
    ap.add_argument('step', type=int)
    ap.add_argument('--depth', type=int, default=7)
    ap.add_argument('--procs', type=int, default=16)
    args = ap.parse_args()
    build(args.m, args.n, args.step, args.depth, args.procs)


if __name__ == '__main__':
    main()
