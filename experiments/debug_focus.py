# -*- coding: utf-8 -*-
"""聚焦：打印某存档匹配到的动作，并逐步重放报告首个失败点。"""
import json
import sys

from experiments import harness as H
from experiments.analyze_conjugation import extract_actions


def main(path):
    arc = json.load(open(path, encoding='utf-8'))
    actions, snaps, coord_list = extract_actions(arc)
    step = arc['puzzle']['step']
    for i, a in enumerate(actions):
        print(f"  {i}: {a}")

    g = H.load_game({'m': arc['puzzle']['m'], 'n': arc['puzzle']['n'],
                     'step': step, 'coords': sorted(coord_list[0])})
    for i, a in enumerate(actions):
        before = H.coords_of(g)
        ok = H.apply_action(g, a, step) if a else False
        want = frozenset(coord_list[i + 1])
        got = H.coords_of(g)
        flag = '' if (ok and got == want) else '  <== 异常'
        print(f"  replay {i}: apply={ok} match={got == want}{flag}")
        if not ok or got != want:
            print(f"    want 新增={sorted(want - before)}")
            print(f"    got  新增={sorted(got - before)}")
            break
    print("solved:", g.is_solved())


if __name__ == '__main__':
    main(sys.argv[1])
