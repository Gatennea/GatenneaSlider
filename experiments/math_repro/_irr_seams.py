# -*- coding: utf-8 -*-
"""异形盘面满盘入口成本：逐缝逐向试探，打印合法首发与选中块数。

用法（cwd 必须是主仓根，脚本要 import GUI）：
    D:\\python\\python.exe <this> tri 4 2
    D:\\python\\python.exe <this> tri 4 1
    D:\\python\\python.exe <this> mi 2 2 1

输出每个合法 (族, line, 方向) 以及该步移动的块数，并汇总每族出现过哪些块数。
门槛（k-step>=2 等）由 GUI.new_*_puzzle 自己拦，被拒返回 False 不抛异常。
"""
import os
import sys
import queue

sys.path.insert(0, os.path.abspath('.'))
# 无头：必须在 import pygame 之前设，否则会开窗口（GUI.py:727 同款判定）。
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame
from GUI import SliderGUI

FAM = {
    'tri': [('h', ('a', 'd')), ('p', ('e', 'z')), ('n', ('w', 'x'))],
    'mi': [('h', ('a', 'd')), ('v', ('w', 's')), ('d1', ('q', 'x')), ('d2', ('e', 'z'))],
    'cubic': [('r', ('a', 'd')), ('c', ('w', 's')), ('d', ('q', 'e'))],
}


def build(kind, args):
    q = queue.Queue()
    gui = SliderGUI(6, 6, 2, q)
    if kind == 'tri':
        ok = gui.new_triangle_puzzle(*args)
    elif kind == 'mi':
        ok = gui.new_mi_puzzle(*args)
    elif kind == 'cubic':
        ok = gui.new_cubic_puzzle(*args)
    else:
        ok = False
    gui.animation_enabled = False
    gui.game_history.reset()
    return gui if ok else None


def probe(kind, args):
    g = build(kind, args)
    if g is None:
        print(f"--- {kind} {args}: REJECTED by guard")
        return
    print(f"--- {kind} {args}: blocks={len(g.game.blocks)}")
    res = []
    for gt, dirs in FAM[kind]:
        for line in range(-4, 11):
            for dr in dirs:
                gui = build(kind, args)
                if gui is None:
                    continue
                anchor = gui.game.blocks[0]
                try:
                    gui.selected_gap = (gt, line)
                    gui.selected_block = anchor
                    gui.game.opt(gt, line, anchor)
                    sel = [b for b in gui.game.blocks if b.be_opted]
                    if not sel:
                        continue
                    ok = gui.move_selected_blocks(dr)
                except Exception:
                    continue
                if ok:
                    res.append((gt, line, dr, len(sel)))
    print(f"    legal first moves: {len(res)}")
    for t in res:
        print("     ", t)
    fam = {}
    for gt, line, dr, n in res:
        fam.setdefault(gt, []).append(n)
    print("    per-family block counts:", {k: sorted(set(v)) for k, v in fam.items()})


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    kind = sys.argv[1]
    args = tuple(int(x) for x in sys.argv[2:])
    pygame.init()
    probe(kind, args)
