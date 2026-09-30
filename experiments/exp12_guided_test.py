# -*- coding: utf-8 -*-
"""测 find_A（BFS）vs find_A_guided（best-first）在难残局上的速度。"""
import time

from experiments import harness as H
from experiments.exp_conj_search import find_A, find_A_guided
from solver.ml.gather_solver import gather_solve


def main():
    for seed in (1006, 1008, 1015):
        snap = H.gen_state(5, 5, 2, seed)
        g = H.load_game(snap)
        gather_solve(g, 2)
        if g.is_solved():
            print(f'  seed{seed}: gather直解')
            continue
        rc = frozenset(H.coords_of(g))
        for name, fn, kw in (('BFS', find_A, dict(max_depth=6,
                                                  node_cap=250000)),
                             ('guided', find_A_guided,
                              dict(max_depth=8, node_cap=200000))):
            t0 = time.perf_counter()
            res = fn(rc, 5, 5, 2, **kw)
            dt = time.perf_counter() - t0
            if res is None:
                print(f'  seed{seed} {name:7s} 未找到 {dt:.1f}s')
            else:
                A, s1 = res
                print(f'  seed{seed} {name:7s} A={len(A)}步 {dt:.1f}s')


if __name__ == '__main__':
    main()
