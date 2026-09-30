# -*- coding: utf-8 -*-
"""逐帧核对：把 rep 重放结果与每个 snapshot 的真实矩阵坐标对比。"""
import argparse

from experiments import harness as H
from experiments.analyze_notch import load_save, initial_coords, build_actions
from experiments.exp9_rep import _apply_with_rep


def snap_coords(s):
    b = s['bounds']
    out = set()
    for r, row in enumerate(s['matrix']):
        for c, v in enumerate(row):
            if v:
                out.add((r + b['min_row'], c + b['min_col']))
    return frozenset(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sub', default='4.3')
    args = ap.parse_args()
    save = load_save(args.sub)
    m, n, step = save['puzzle']['m'], save['puzzle']['n'], save['puzzle']['step']
    snaps = save['history']['snapshots']
    steps = build_actions(save)

    g = H.load_game({'m': m, 'n': n, 'step': step,
                     'coords': sorted(initial_coords(save))})
    for i, (a, rep, mstep) in enumerate(steps):
        ok = _apply_with_rep(g, a, mstep, rep)
        got = H.coords_of(g)
        truth = snap_coords(snaps[i + 1])
        mark = 'OK' if got == truth else 'XX'
        print(f"步{i+1} apply={ok} match={mark} {a}")
        if got != truth:
            only_g = sorted(set(got) - set(truth))
            only_t = sorted(set(truth) - set(got))
            print(f"    重放多出: {only_g[:8]}")
            print(f"    应有却无: {only_t[:8]}")
            break


if __name__ == '__main__':
    main()
