# -*- coding: utf-8 -*-
r"""异形板的最短非恒等回路：按层枚举，遇到「回原形但非恒等」就停。

用法（cwd 必须是主仓根）：
    D:\python\python.exe <this> tri 4 2 14
    D:\python\python.exe <this> mi 2 2 4

判据：把块坐标平移到最小角之后与初态比较 —— 形状相同即「回原形」；
再要求位置不是初态本身，才计一条回路。
"""
import os
import queue
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

sys.path.insert(0, os.path.abspath('.'))

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402

FAM = {
    'tri': [('h', ('a', 'd')), ('p', ('e', 'z')), ('n', ('w', 'x'))],
    'mi': [('h', ('a', 'd')), ('v', ('w', 's')), ('d1', ('q', 'x')), ('d2', ('e', 'z'))],
    'square': [('h', ('w', 's')), ('v', ('a', 'd'))],
}


def build(kind, args):
    gui = SliderGUI(6, 6, 2, queue.Queue())
    gui.animation_enabled = False
    if kind == 'tri':
        ok = gui.new_triangle_puzzle(*args)
    elif kind == 'mi':
        ok = gui.new_mi_puzzle(*args)
    else:
        ok = gui.new_puzzle(*args, numbered=True)
    gui.game_history.reset()
    return gui if ok else None


def snap(gui):
    return tuple(tuple(b.location) for b in gui.game.blocks)


def restore(gui, pos):
    for b, p in zip(gui.game.blocks, pos):
        b.location = list(p)
        b.be_opted = False
    try:
        gui.game.update_matrix()
    except Exception:
        pass


def norm(pos):
    mr = min(p[0] for p in pos)
    mc = min(p[1] for p in pos)
    return tuple((p[0] - mr, p[1] - mc) for p in pos)


def occ(pos):
    """占据集（绝对坐标）。

    判「真的回到原形状」必须用绝对占据集，不能用 norm：norm 会把**整盘平移**
    当成回原形，于是「推出去再推回来、整体错位」被误记成回路。
    """
    return frozenset(pos)


def enum(gui, kind):
    """枚举当前局面所有不同移动。

    必须对**每一个**块当锚点试一遍：`SliderMatrix.opt` 的选中集是
    「锚点所在侧 + 与之连通」的分量，只固定用一个锚点会漏掉另一侧的整片。
    三角 k=4 s=2 满盘用单锚点只能拿到 6 个移动，全锚点是 12 个。
    """
    local = snap(gui)
    out = {}
    n = len(gui.game.blocks)
    for gt, dirs in FAM[kind]:
        for line in range(-4, 11):
            for dr in dirs:
                for ai in range(n):
                    restore(gui, local)
                    try:
                        gui.selected_gap = (gt, line)
                        gui.selected_block = gui.game.blocks[ai]
                        gui.game.opt(gt, line, gui.game.blocks[ai])
                        sel = [b for b in gui.game.blocks if b.be_opted]
                    except Exception:
                        continue
                    if not sel:
                        continue
                    ok = False
                    try:
                        ok = gui.move_selected_blocks(dr)
                    except Exception:
                        ok = False
                    if ok:
                        key = (gt, line, dr,
                               tuple(sorted(tuple(x.location) for x in sel)))
                        out[key] = snap(gui)
    restore(gui, local)
    return list(out.values())


def run(kind, args, depth, cap=200000):
    gui = build(kind, args)
    if gui is None:
        print(f"{kind} {args}: REJECTED")
        return
    base = snap(gui)
    bk = norm(base)
    bocc = occ(base)
    print(f"{kind} {args}: blocks={len(gui.game.blocks)} d0_moves={len(enum(gui, kind))}")
    seen = {bk}
    frontier = [base]
    hits = []
    wins = []
    for d in range(1, depth + 1):
        nxt = []
        for pos in frontier:
            restore(gui, pos)
            for np_ in enum(gui, kind):
                if np_ == base:
                    continue
                if occ(np_) == bocc:
                    # 绝对占据集回到原样、但块的位置排列不同 = 真回路
                    hits.append(d)
                    continue
                restore(gui, np_)
                if gui.is_solved():
                    wins.append(d)
                key = norm(np_)
                if key not in seen:
                    seen.add(key)
                    nxt.append(np_)
            if len(seen) > cap:
                break
        print(f"  d{d}: new={len(nxt)} total={len(seen)} loops={len(hits)} wins={len(wins)}")
        if wins and min(wins) == d:
            print(f"    first solved at {d} steps")
        if hits:
            print(f"    first loop at {min(hits)} steps")
            break
        if len(seen) > cap:
            print("  CAP reached, stop")
            break
        frontier = nxt
        if not frontier:
            print("  frontier empty")
            break
    restore(gui, base)
    return hits


if __name__ == '__main__':
    kind = sys.argv[1]
    nums = [int(x) for x in sys.argv[2:]]
    run(kind, tuple(nums[:-1]), nums[-1])
