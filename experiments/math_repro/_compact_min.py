# -*- coding: utf-8 -*-
r"""紧凑盘的最小可选分量随深度变化。

问题：能不能在盘内直接选出 1*s 段（s 块）来互换？满盘时方形 6x6 s=2 只能整行
6 块；打散一步后能选到 1 块，但那块已经在棋盘外。这里量「盘内」的那一支。

用法（cwd 必须是主仓根，脚本要 import GUI）：
    D:\python\python.exe <this> 6 6 2 3
    D:\python\python.exe <this> 4 4 2 2

参数：(m, n, s, max_depth)

判据：一次移动后，36 块（或 m*n 块）的相对坐标仍全部落在 0..m-1 / 0..n-1
── 也就是盘面没走出原来的矩形轮廓。这样的选择才算「盘内」。

输出每一层的最少选中块数；99 表示该层没有盘内可达的选择。
"""
import os
import queue
import sys

# 无头：必须在 import pygame 之前设，否则会开窗口。
# GUI.py:727 也按这两个变量判定 headless（成绩写 records_test.dat）。
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

sys.path.insert(0, os.path.abspath('.'))

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402


def build(m, n, s):
    gui = SliderGUI(m, n, s, queue.Queue())
    gui.animation_enabled = False
    ok = gui.new_puzzle(m, n, s, numbered=True)
    gui.game_history.reset()
    return gui if ok else None


def snap(gui):
    return tuple(b.location for b in gui.game.blocks)


def restore(gui, pos):
    for b, p in zip(gui.game.blocks, pos):
        b.location = p
        b.be_opted = False
    try:
        gui.game.update_matrix()
    except Exception:
        pass


def norm(pos):
    mr = min(p[0] for p in pos)
    mc = min(p[1] for p in pos)
    return tuple((p[0] - mr, p[1] - mc) for p in pos)


def enum(gui):
    """枚举当前局面所有合法移动，返回 [(gt, line, dir, nblocks, new_pos)]。"""
    local = snap(gui)
    out = []
    for gt in ('h', 'v'):
        for line in range(-4, 12):
            for dr in ('w', 's', 'a', 'd'):
                restore(gui, local)
                try:
                    gui.selected_gap = (gt, line)
                    gui.selected_block = gui.game.blocks[0]
                    gui.game.opt(gt, line, gui.game.blocks[0])
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
                    out.append((gt, line, dr, len(sel), snap(gui)))
    restore(gui, local)
    return out


def main():
    m = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    s = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    depth = int(sys.argv[4]) if len(sys.argv) > 4 else 3

    gui = build(m, n, s)
    if gui is None:
        print(f"{m}x{n} s={s}: REJECTED by constructor guard")
        return
    base = snap(gui)
    print(f"{m}x{n} s={s}: blocks={len(gui.game.blocks)}")

    moves = enum(gui)
    print(f"  d0 legal={len(moves)} min_sel={min(x[3] for x in moves)}")

    seen = {norm(base)}
    frontier = [base]
    for d in range(1, depth + 1):
        nxt = []
        best = 99
        info = None
        for pos in frontier:
            restore(gui, pos)
            for mv in enum(gui):
                key = norm(mv[4])
                inside = all(0 <= x < m and 0 <= y < n for x, y in key)
                if inside and mv[3] < best:
                    best = mv[3]
                    info = mv[:3]
                if key not in seen:
                    seen.add(key)
                    nxt.append(mv[4])
        print(f"  d{d}: new={len(nxt)} total={len(seen)} inboard_min_sel={best}"
              + (f" via {info}" if info else ""))
        frontier = nxt
        if not frontier:
            break

    restore(gui, base)


if __name__ == '__main__':
    main()
