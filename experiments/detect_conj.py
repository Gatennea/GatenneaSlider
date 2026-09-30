# -*- coding: utf-8 -*-
"""自动检测第4关各子关解的共轭结构 A + B + inverse_reverse(A)，
并对比外层模板如何随缺口位置变化。
"""
import os

from experiments import harness as H
from experiments.analyze_notch import (load_save, initial_coords, build_actions)

OPP = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


def inv_action(a):
    gt, gl, side, d = a
    return (gt, gl, side, OPP[d])


def detect_conjugation(actions):
    """找最大 k 使 actions 末 k 个 == 前 k 个逆序取逆（允许 gap_line 平移）。"""
    n = len(actions)
    best = 0
    for k in range(1, n // 2 + 1):
        head = actions[:k]
        tail = actions[n - k:]
        expect = [inv_action(x) for x in reversed(head)]
        # 严格匹配
        if tail == expect:
            best = k
            continue
        # 允许整体平移：gap_type/side/dir 相同，gap_line 差值恒定
        ok = True
        deltas = []
        for e, t in zip(expect, tail):
            if e[0] != t[0] or e[2] != t[2] or e[3] != t[3]:
                ok = False
                break
            deltas.append(t[1] - e[1])
        if ok and len(set(deltas)) <= 1:
            best = k
    return best


def main():
    for k in range(1, 7):
        sub = f'4.{k}'
        save = load_save(sub)
        steps = build_actions(save)
        actions = [a for a, _, _ in steps]
        c = detect_conjugation(actions)
        A = actions[:c]
        B = actions[c:len(actions) - c]
        Ap = actions[len(actions) - c:]
        # 验证重放（rep 感知，按每步实际 step）
        m, n, step = (save['puzzle']['m'], save['puzzle']['n'],
                      save['puzzle']['step'])
        g = H.load_game({'m': m, 'n': n, 'step': step,
                         'coords': sorted(initial_coords(save))})
        from experiments.exp9_rep import _apply_with_rep
        for a, rep, mstep in steps:
            _apply_with_rep(g, a, mstep, rep)
        print(f"{sub}  {len(actions)}步  k={c} solved={g.is_solved()}")
        print(f"      A  = {A}")
        print(f"      B  = {B}")
        print(f"      A' = {Ap}")


if __name__ == '__main__':
    main()
