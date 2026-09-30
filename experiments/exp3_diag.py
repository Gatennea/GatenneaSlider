# -*- coding: utf-8 -*-
"""诊断：残局真实深度。

对梯度聚拢后未解的残局，用大预算 IDDFS 探测：
- 能否解出、解要多深、探索了多少节点；
- 同时跑现有 ida_star（含 G2 阶段）对照。
"""
import argparse
import time

from experiments import harness as H
from experiments.last_mile import last_mile_solve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='1000,1003')
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--depth', type=int, default=60)
    ap.add_argument('--nodes', type=int, default=1500000)
    ap.add_argument('--time', type=float, default=120.0)
    args = ap.parse_args()

    m, n, st = args.configs.split('x')
    spec = (int(m), int(n), int(st))
    seeds = [int(x) for x in args.seeds.split(',')]
    snaps = [H.gen_state(spec[0], spec[1], spec[2], s) for s in seeds]

    from solver.ml.gather_solver import gradient_gather
    from solver.state import snapshot, restore

    for snap in snaps:
        g = H.load_game(snap)
        r = gradient_gather(g, snap['step'])
        print(f"\nseed={snap['seed']} 聚拢后 score="
              f"{H.gather_metrics(H.coords_of(g), g.m, g.n)['score']:.3f} "
              f"reason={r['reason']} solved={g.is_solved()}")
        if g.is_solved():
            continue
        pre = snapshot(g)

        # LMS 大预算
        t0 = time.perf_counter()
        lm = last_mile_solve(g, snap['step'], max_depth=args.depth,
                             max_nodes=args.nodes, time_limit=args.time)
        dt = time.perf_counter() - t0
        if lm:
            restore(g, pre)
            for a in lm:
                H.apply_action(g, a, snap['step'])
            print(f"  LMS: 解出 {len(lm)} 步 {dt:.1f}s "
                  f"verified={g.is_solved()}")
        else:
            print(f"  LMS: 失败（{args.depth}层/{args.nodes}节点/{args.time}s "
                  f"{dt:.1f}s）")

        # 对照：现有 ida_star（自带 G2）
        restore(g, pre)
        from solver import solve
        t0 = time.perf_counter()
        try:
            res = solve(g, snap['step'])
            dt = time.perf_counter() - t0
            if res:
                restore(g, pre)
                for a in res:
                    H.apply_action(g, a, snap['step'])
                print(f"  ida_star: 解出 {len(res)} 步 {dt:.1f}s "
                      f"verified={g.is_solved()}")
            else:
                print(f"  ida_star: 无解 {dt:.1f}s")
        except Exception as e:
            print(f"  ida_star: 异常 {e!r}")


if __name__ == '__main__':
    main()
