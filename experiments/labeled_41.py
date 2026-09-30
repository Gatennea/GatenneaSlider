# -*- coding: utf-8 -*-
"""带标签重放 4.1：直接持有凸起块对象，追踪其位置与缺口填充时刻。"""
from experiments import harness as H
from experiments.analyze_notch import load_save, initial_coords, build_actions
from experiments.exp9_rep import _apply_with_rep


def main():
    save = load_save('4.1')
    m, n, step = save['puzzle']['m'], save['puzzle']['n'], save['puzzle']['step']
    coords0 = set(initial_coords(save))
    P, notch = (3, -1), (7, 1)

    g = H.load_game({'m': m, 'n': n, 'step': step,
                     'coords': sorted(coords0)})
    pblock = next(b for b in g.blocks if tuple(b.location) == P)
    print(f"初始: P在{P} 缺口{notch} (缺口当前空={notch not in coords0})")
    for i, (a, rep, mstep) in enumerate(build_actions(save)):
        _apply_with_rep(g, a, mstep, rep)
        cur = set(H.coords_of(g))
        print(f"步{i+1} {a} step{mstep}: P在{tuple(pblock.location)} "
              f"缺口已填={notch in cur}")


if __name__ == '__main__':
    main()
