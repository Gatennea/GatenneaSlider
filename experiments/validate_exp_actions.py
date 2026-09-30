# -*- coding: utf-8 -*-
"""用改进动作（按分量）重放全部 beginner_archive，验证动作模型。"""
import json
import os

from experiments import harness as H
from experiments.exp_actions import (apply_exp_n, _side_cells, _components)
from experiments.analyze_conjugation import snap_coords
from solver.state import snapshot, restore

ARCH = 'beginner_archive'


def validate(path):
    arc = json.load(open(path, encoding='utf-8'))
    m, n, step = arc['puzzle']['m'], arc['puzzle']['n'], arc['puzzle']['step']
    snaps = arc['history']['snapshots']
    coord_list = [snap_coords(s) for s in snaps]

    g = H.load_game({'m': m, 'n': n, 'step': step,
                     'coords': sorted(coord_list[0])})
    first_fail = None
    n_unit = 0
    for i in range(len(snaps) - 1):
        target = frozenset(coord_list[i + 1])
        mi = snaps[i + 1]['move_info']
        gap, line, d, total = (mi['gap_type'], mi['gap_line'],
                               mi['direction'], mi['step'])
        found = False
        for side_cells in _side_cells(g, gap, line):
            for comp in _components(side_cells):
                rep = min(comp)
                s = snapshot(g)
                if apply_exp_n(g, gap, line, rep, d, total, step) \
                        and H.coords_of(g) == target:
                    found = True
                    n_unit += total // step
                    break
                restore(g, s)
            if found:
                break
        if not found:
            first_fail = i
            break
    return first_fail is None, first_fail, n_unit


def main():
    files = sorted(f for f in os.listdir(ARCH) if f.endswith('.json'))
    n_ok = 0
    for f in files:
        ok, idx, total = validate(os.path.join(ARCH, f))
        n_ok += ok
        print(f"  {f:10s} {'通过' if ok else f'失败于过渡{idx}'} ({total}步)")
    print(f"\n动作模型重放: {n_ok}/{len(files)}")


if __name__ == '__main__':
    main()
