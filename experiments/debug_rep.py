# -*- coding: utf-8 -*-
"""验证：缝隙一侧多分量时，代表块选择决定成败。"""
import json
import sys

from experiments import harness as H
from experiments.analyze_conjugation import extract_actions, snap_coords


def main(path, fail_idx):
    arc = json.load(open(path, encoding='utf-8'))
    actions, snaps, coord_list = extract_actions(arc)
    step = arc['puzzle']['step']

    # 用“累积”方式走到 fail_idx
    g = H.load_game({'m': arc['puzzle']['m'], 'n': arc['puzzle']['n'],
                     'step': step, 'coords': sorted(coord_list[0])})
    for i in range(fail_idx):
        H.apply_action(g, actions[i], step)

    gd, gl, side, md = actions[fail_idx]
    from solver.actions import _get_side_blocks
    side_blocks = _get_side_blocks(g, gd, gl, side)
    print(f"动作 {actions[fail_idx]}；该侧块数={len(side_blocks)}")

    # 该侧按“不跨越缝隙”的连通分量分组
    def comp_of(rep):
        from collections import deque
        seed = tuple(rep.location)
        cells = {tuple(b.location) for b in side_blocks}
        seen = {seed}
        q = deque([seed])
        while q:
            r, c = q.popleft()
            for d in [(1,0),(-1,0),(0,1),(0,-1)]:
                n = (r+d[0], c+d[1])
                if n in cells and n not in seen:
                    seen.add(n); q.append(n)
        return seen

    comps = []
    used = set()
    for b in side_blocks:
        key = tuple(b.location)
        if key in used:
            continue
        comp = comp_of(b)
        used |= comp
        comps.append((key, comp))
    print(f"该侧连通分量数={len(comps)}")
    for key, comp in comps:
        print(f"  分量 rep={key} 大小={len(comp)}")

    # 逐个代表块尝试该动作
    from solver.state import snapshot, restore
    target = frozenset(coord_list[fail_idx + 1])
    for key, comp in comps:
        s = snapshot(g)
        g.opt(gd, gl, next(b for b in g.blocks if tuple(b.location) == key))
        pos = g.try_move(md, step)
        hit = False
        if pos:
            g.commit_move(pos)
            hit = (H.coords_of(g) == target)
        restore(g, s)
        print(f"  rep={key}: try_move={'成功' if pos else '失败'} 命中目标={hit}")


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
