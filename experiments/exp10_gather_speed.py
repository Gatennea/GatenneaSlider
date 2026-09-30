# -*- coding: utf-8 -*-
"""测 5x5 上普通 gather 与 gradient gather 的耗时与残局形态。"""
import time

from experiments import harness as H
from solver.ml.fill_macro import window_of


def run(which, seeds):
    from solver.ml.gather_solver import gather_solve, gradient_gather
    fn = gather_solve if which == 'plain' else gradient_gather
    t_total = 0.0
    holes_stat = {}
    solved = 0
    for s in seeds:
        snap = H.gen_state(5, 5, 2, s)
        g = H.load_game(snap)
        t0 = time.perf_counter()
        fn(g, 2)
        dt = time.perf_counter() - t0
        t_total += dt
        if g.is_solved():
            solved += 1
            continue
        _w, _o, holes, outside = window_of(H.coords_of(g), 5, 5, 2)
        key = (len(holes), len(outside))
        holes_stat[key] = holes_stat.get(key, 0) + 1
    print(f'  {which}: 解出 {solved}/{len(seeds)} 平均 {t_total/len(seeds):.1f}s '
          f'残局形态(洞,凸起) {dict(sorted(holes_stat.items()))}')


def main():
    seeds = list(range(1000, 1016))
    run('plain', seeds)
    run('gradient', seeds)


if __name__ == '__main__':
    main()
