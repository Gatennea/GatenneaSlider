# -*- coding: utf-8 -*-
"""实验11：5x5 快速管线 = plain gather → 多洞驱动 → 缺口共轭兜底。

目标：在保持 100% 成功率的前提下把单局耗时从 ~40s 压到 ~10s 内。
"""
import time

from experiments import harness as H
from experiments.exp_conj_search import conj_chain, replay_all, apply_step
from solver.table_core import canonicalize
from solver.ml.fill_macro import solve_multi_void


def main():
    seeds = list(range(1000, 1016))
    m = n = 5
    step = 2
    goal_key = canonicalize(frozenset((r, c) for r in range(m)
                                      for c in range(n)))
    from solver.ml.gather_solver import gather_solve

    n_solved = 0
    for seed in seeds:
        snap = H.gen_state(m, n, step, seed)
        g = H.load_game(snap)
        t0 = time.perf_counter()
        gather_solve(g, step)
        t_g = time.perf_counter() - t0
        if g.is_solved():
            n_solved += 1
            print(f'  seed{seed} gather直解 {t_g:.1f}s')
            continue

        # 多洞驱动
        rc = H.coords_of(g)
        t0 = time.perf_counter()
        acts, stats = solve_multi_void(rc, m, n, step)
        t_m = time.perf_counter() - t0
        applied = 0
        if acts:
            for a in acts:
                if apply_step(g, a, step):
                    applied += 1
        if g.is_solved():
            n_solved += 1
            print(f'  seed{seed} 多洞直解 {t_g:.1f}s+{t_m:.1f}s '
                  f'({len(acts)}步) solved')
            continue

        # 共轭兜底
        rc2 = H.coords_of(g)
        t0 = time.perf_counter()
        res = conj_chain(rc2, m, n, step, goal_key)
        t_c = time.perf_counter() - t0
        if res[0] is None:
            # gradient 重新聚拢后再试（不同残局可能可填）
            from solver.ml.gather_solver import gradient_gather
            g2 = H.load_game(snap)
            t0 = time.perf_counter()
            gradient_gather(g2, step)
            t_gr = time.perf_counter() - t0
            if g2.is_solved():
                n_solved += 1
                print(f'  seed{seed} gradient兜底直解 '
                      f'gather={t_g:.1f}s grad={t_gr:.1f}s')
                continue
            rc3 = H.coords_of(g2)
            t0 = time.perf_counter()
            res = conj_chain(rc3, m, n, step, goal_key)
            t_c2 = time.perf_counter() - t0
            if res[0] is None:
                print(f'  seed{seed} FAIL:{res[1]["mode"]} '
                      f'gather={t_g:.1f}s multi={t_m:.1f}s '
                      f'conj={t_c:.1f}s grad={t_gr:.1f}s conj2={t_c2:.1f}s')
                continue
            n_solved += 1
            info = res[1]
            print(f'  seed{seed} gradient+共轭兜底 A{info.get("A",0)}/f{info["fill"]} '
                  f'gather={t_g:.1f}s grad={t_gr:.1f}s conj={t_c2:.1f}s')
            continue
        n_solved += 1
        info = res[1]
        print(f'  seed{seed} 共轭兜底 A{info.get("A",0)}/f{info["fill"]} '
              f'gather={t_g:.1f}s multi={t_m:.1f}s conj={t_c:.1f}s')
    print(f'\n5x5 快速管线: {n_solved}/{len(seeds)}')


if __name__ == '__main__':
    main()
