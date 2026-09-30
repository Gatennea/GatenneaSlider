# -*- coding: utf-8 -*-
"""实验9：5x5 step2 免表共轭链求解（gather → A搜索 → 填洞 → 逆向）。

与 4x4 完全同一套代码，无距离表；验证「局部宏不随棋盘尺寸爆炸」。
"""
import time

from experiments import harness as H
from experiments.exp_conj_search import (conj_chain, structurally_fillable,
                                         replay_all)
from solver.table_core import canonicalize


def main():
    seeds = [int(x) for x in
             '1000,1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,'
             '1011,1012,1013,1014,1015'.split(',')]
    m = n = 5
    step = 2
    goal_key = canonicalize(frozenset((r, c) for r in range(m)
                                      for c in range(n)))
    from solver.ml.gather_solver import gradient_gather

    n_solved = 0
    for seed in seeds:
        snap = H.gen_state(m, n, step, seed)
        g = H.load_game(snap)
        gfn = gradient_gather
        t0 = time.perf_counter()
        r = gfn(g, step)
        t_gather = time.perf_counter() - t0
        if g.is_solved():
            n_solved += 1
            print(f'  seed{seed} gather直接解 {t_gather:.1f}s')
            continue
        rc = H.coords_of(g)
        t0 = time.perf_counter()
        res = conj_chain(rc, m, n, step, goal_key)
        dt = time.perf_counter() - t0
        if res[0] is None:
            print(f'  seed{seed} FAIL:{res[1]["mode"]} '
                  f'(gather {t_gather:.1f}s + chain {dt:.1f}s)')
            continue
        acts, info = res
        n_solved += 1
        info_extra = f"A{info.get('A',0)}/f{info['fill']}/u{info.get('undo',0)}"
        print(f'  seed{seed} {info["mode"]:11s} {info_extra} '
              f'链长={len(acts):3d} (gather {t_gather:.1f}s + chain {dt:.1f}s)')
    print(f'\n5x5 step2 免表共轭链: {n_solved}/{len(seeds)}')


if __name__ == '__main__':
    main()
