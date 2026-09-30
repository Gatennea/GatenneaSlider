# -*- coding: utf-8 -*-
"""实验7：5x5 step2 gather 残局距离。

先用半成品 checkpoint 的 dist 查询；未覆盖的 key 留待反向 BFS。
"""
import collections
import pickle

from experiments import harness as H
from solver import table_core as TC


def collect(seeds, which):
    from solver.ml.gather_solver import gather_solve, gradient_gather
    fn = gather_solve if which == 'plain' else gradient_gather
    residual = {}
    solved_n = 0
    for s in seeds:
        snap = H.gen_state(5, 5, 2, s)
        g = H.load_game(snap)
        fn(g, 2)
        if g.is_solved():
            solved_n += 1
        key = TC.canonicalize(H.coords_of(g))
        residual.setdefault(key, []).append(s)
    return residual, solved_n


def main():
    seeds = list(range(1000, 1016))
    ck = pickle.load(open(r'solver\data\5_5_2\checkpoint.pkl', 'rb'))
    dist = ck['dist']

    for which in ('plain', 'gradient'):
        residual, solved_n = collect(seeds, which)
        covered, missing = {}, []
        for key, ss in residual.items():
            if key in dist:
                covered[dist[key]] = covered.get(dist[key], 0) + 1
            else:
                missing.append((key, ss))
        print(f'=== {which} (残局去重 {len(residual)}，gather直接解出 {solved_n}) ===')
        print(f'  checkpoint 覆盖的残局距离分布: {dict(sorted(covered.items()))}')
        print(f'  未覆盖 key 数: {len(missing)}')
        for key, ss in missing[:8]:
            print(f'    seeds={ss} key={key}')


if __name__ == '__main__':
    main()
