# -*- coding: utf-8 -*-
"""分析 gather 残局：真实残局距离分布 + 全链相对最优的差距。

用完整 4x4 step2 距离表作标准答案。
"""
import collections

from experiments import harness as H
from solver.table_core import canonicalize
from experiments.exp_table_solve import load_table


def run(which_gather, seeds, table):
    residual_dist = collections.Counter()
    gather_solved = 0
    rows = []
    for seed in seeds:
        snap = H.gen_state(4, 4, 2, seed)
        g = H.load_game(snap)
        d_opt_start = table[canonicalize(H.coords_of(g))]

        r = which_gather(g, 2)
        n_gather = len(r['actions'])
        coords = H.coords_of(g)
        if g.is_solved():
            gather_solved += 1
            d_res = 0
        else:
            d_res = table[canonicalize(coords)]
        residual_dist[d_res] += 1
        rows.append((seed, d_opt_start, n_gather, d_res))
    return residual_dist, gather_solved, rows


def main():
    table = load_table()
    seeds = list(range(1000, 1040))
    from solver.ml.gather_solver import gather_solve, gradient_gather

    for name, fn in (('普通gather', gather_solve),
                     ('gradient', gradient_gather)):
        dist, solved, rows = run(fn, seeds, table)
        print(f'=== {name} (n={len(seeds)}) ===')
        print(f'  gather 直接解出: {solved}')
        print(f'  残局真实距离分布: {dict(sorted(dist.items()))}')
        # 全链步数 = gather步数 + 残局距离；与初始最优比较
        excess = [(n_g + d_res - d_opt) for _, d_opt, n_g, d_res in rows]
        print(f'  全链超出最优步数: 中位={sorted(excess)[len(excess)//2]} '
              f'最大={max(excess)} 平均={sum(excess)/len(excess):.1f}')


if __name__ == '__main__':
    main()
