# -*- coding: utf-8 -*-
"""探测某存档某过渡：枚举到的动作 vs 期望动作。"""
import json
import sys

from experiments import harness as H
from experiments.exp_actions import (enumerate_exp_actions, apply_exp_action,
                                     _side_cells, _components)
from experiments.analyze_conjugation import snap_coords
from solver.state import snapshot, restore


def main(path, idx):
    arc = json.load(open(path, encoding='utf-8'))
    m, n, step = arc['puzzle']['m'], arc['puzzle']['n'], arc['puzzle']['step']
    snaps = arc['history']['snapshots']
    coord_list = [snap_coords(s) for s in snaps]

    # 累积走到 idx
    g = H.load_game({'m': m, 'n': n, 'step': step,
                     'coords': sorted(coord_list[0])})
    for i in range(idx):
        target = frozenset(coord_list[i + 1])
        for a in enumerate_exp_actions(g, step):
            s = snapshot(g)
            if apply_exp_action(g, a, step) and H.coords_of(g) == target:
                break
            restore(g, s)

    target = frozenset(coord_list[idx + 1])
    mi = snaps[idx + 1]['move_info']
    print(f"期望 gap={mi['gap_type']} line={mi['gap_line']} dir={mi['direction']}")

    # 该 gap line 两侧分量
    side_a, side_b = _side_cells(g, mi['gap_type'], mi['gap_line'])
    for name, cells in (('A侧', side_a), ('B侧', side_b)):
        for comp in _components(cells):
            print(f"  {name} 分量 大小={len(comp)} rep={min(comp)}")

    # 暴力：枚举所有动作，看是否有命中
    hits = []
    for a in enumerate_exp_actions(g, step):
        s = snapshot(g)
        if apply_exp_action(g, a, step) and H.coords_of(g) == target:
            hits.append(a)
        restore(g, s)
    print(f"命中动作数={len(hits)} {hits[:5]}")

    # 手动对每个分量试期望方向，报告 try_move 失败原因
    for name, cells in (('A侧', side_a), ('B侧', side_b)):
        for comp in _components(cells):
            rep = min(comp)
            s = snapshot(g)
            rb = next(b for b in g.blocks if tuple(b.location) == rep)
            g.opt(mi['gap_type'], mi['gap_line'], rb)
            final = g.try_move(mi['direction'], step)
            if not final:
                # 逐单位步定位失败原因
                import copy
                gg = copy.deepcopy(g)
                reason = None
                for k in range(1, step + 1):
                    f2 = gg.try_move(mi['direction'], 1)
                    if not f2:
                        reason = f'第{k}单位步失败'
                        break
                    gg.commit_move(f2)
                print(f"  {name} rep={rep} 期望方向失败: {reason}")
            restore(g, s)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
