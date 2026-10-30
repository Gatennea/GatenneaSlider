# -*- coding: utf-8 -*-
"""探针：方形棋盘上「画得出、点得到、选不动」的缝隙到底有哪些。

背景：米字格对错位态锁死缝会弹「这条缝选不动（错位态切在块里）：…」，
方形点外沿缝却一声不响。本探针把方形每种「候选缝被 is_valid_*_line 否
决」的位置找出来，并模拟点击看有没有提示，用来确认要补的是哪一类。
"""
import os
import sys
import queue

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
from GUI import SliderGUI


def boot(cells, m=4, n=4):
    gui = SliderGUI(m=m, n=n, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui.new_puzzle(m, n, 2)
    gui._update_in_progress = False
    gui.game.apply_pattern(cells, {})
    gui.center_map()
    return gui


def probe(tag, cells, m=4, n=4):
    gui = boot(cells, m, n)
    bounds = gui.game.get_boundaries()
    print(f"\n=== {tag} cells={len(cells)} bounds={bounds}")
    W, H = gui.screen.get_width(), gui.screen.get_height()
    seen = {}
    for y in range(0, H, 3):
        for x in range(0, W, 3):
            wx, wy = gui.screen_to_world(x, y)
            cands = list(gui.board_view.candidate_gaps(wx, wy, bounds))
            if not cands:
                continue
            bad = []
            for kind, idx in cands:
                ok = (gui.game.is_valid_h_line(idx) if kind == 'h'
                      else gui.game.is_valid_v_line(idx))
                if not ok:
                    bad.append((kind, idx))
            if not bad:
                continue
            gap = gui.get_gap_at_pos(x, y)
            blk = gui.get_block_at_pos(x, y)
            if gap is None and blk is None:
                for b in bad:
                    seen.setdefault(b, [0, (x, y)])
                    seen[b][0] += 1
    for k, v in sorted(seen.items()):
        print(f"  静默拒绝 {k}: {v[0]} 个采样点 (例 {v[1]})")
    if not seen:
        print("  没有静默拒绝的候选缝")

    # 直接点一条外沿缝，看有没有提示
    for (kind, idx), _ in sorted(seen.items())[:1]:
        x, y = seen[(kind, idx)][1]
        gui.macro_notify_msg = None
        gui.macro_notify_timer = 0
        pygame.event.post(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=(int(x), int(y))))
        gui.handle_events()
        print(f"  点击 {kind}{idx} @({x},{y}) → notify={gui.macro_notify_msg!r} "
              f"selected_gap={gui.selected_gap}")


full = {(r, c) for r in range(4) for c in range(4)}
probe('满盘 4x4', full)
probe('缺一块 (1,1)', full - {(1, 1)})
probe('缺整列 c=3', {(r, c) for r in range(4) for c in range(3)})
probe('L 形 8 颗', {(r, c) for r in range(3) for c in range(3)})
