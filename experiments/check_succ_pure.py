# -*- coding: utf-8 -*-
"""校验 succ_pure 与 Game 版枚举（enumerate_exp_actions+apply）后继一致。"""
from experiments import harness as H
from experiments.exp_actions import (enumerate_exp_actions, apply_exp_action,
                                     succ_pure)
from solver.state import snapshot, restore
from solver.table_core import canonicalize


def main():
    bad = 0
    for seed in range(1000, 1050):
        snap = H.gen_state(4, 4, 2, seed)
        g = H.load_game(snap)
        coords = frozenset(H.coords_of(g))

        # Game 版
        gset = set()
        for a in enumerate_exp_actions(g, 2):
            s = snapshot(g)
            if apply_exp_action(g, a, 2):
                gset.add(canonicalize(H.coords_of(g)))
            restore(g, s)

        # 纯集合版
        pset = set()
        for _a, nxt in succ_pure(coords, 4, 4, 2):
            pset.add(canonicalize(nxt))

        if gset != pset:
            bad += 1
            print(f'  seed{seed} 不一致: game={len(gset)} pure={len(pset)} '
                  f'差={sorted(gset ^ pset)[:4]}')
            if bad > 5:
                break
    print(f'等价校验: {50 - bad}/50 通过')


if __name__ == '__main__':
    main()
