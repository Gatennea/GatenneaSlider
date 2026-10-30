# -*- coding: utf-8 -*-
"""验证完整表下降求解：随机全局面 + 硬残局，检查可解、最优、重放。"""
from experiments import harness as H
from experiments.exp_actions import apply_exp_action
from experiments.exp_table_solve import load_table, table_descent


def verify_path(coords, m, n, step, path):
    g = H.load_game({'m': m, 'n': n, 'step': step,
                     'coords': sorted(coords)})
    for a in path:
        assert apply_exp_action(g, a, step), f'动作 {a} 重放失败'
    return g.is_solved()


def main():
    m = n = 4
    step = 2
    table = load_table()
    n_ok = 0
    N = 30
    for seed in range(1000, 1000 + N):
        snap = H.gen_state(m, n, step, seed)
        coords = frozenset(snap['coords'])
        path, final, d0 = table_descent(coords, m, n, step, table)
        solved = verify_path(coords, m, n, step, path)
        optimal = (len(path) == d0)
        n_ok += solved and optimal
        if not (solved and optimal):
            print(f'  seed{seed} solved={solved} optimal={optimal} d={d0} len={len(path)}')
    print(f'随机全局面: {n_ok}/{N} 可解且最优')

    # 硬残局（距离 7）
    hard = 26960769438285125908113663559289765120336278697045450582562818884355
    from solver.table_core import int_to_coords
    coords = frozenset(int_to_coords(hard, m * n))
    path, final, d0 = table_descent(coords, m, n, step, table)
    solved = verify_path(coords, m, n, step, path)
    print(f'硬残局: 距离={d0} 路径长度={len(path)} 解出={solved} 最优={len(path)==d0}')


if __name__ == '__main__':
    main()
