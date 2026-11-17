# -*- coding: utf-8 -*-
"""S1 渲染冒烟：三种谜题各真画一帧，确认改动没引入运行时异常。

针对的场景是「只做 audit 了 `_draw_gap_direction_annotation` 的几何，没验证它在
真实 draw 链路里跑不跑得起来」。这里连同选缝 + 选中切片一起走完。
（2026-11-17 界面模式已删，不再分 enhanced / plain 各画一遍。）

执行：``D:/python/python.exe test/_test_s1_render.py``
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402


def draw_one(gui, mode):
    gui.screen.fill((0, 0, 0))
    gui.draw_board()
    pygame.display.flip()
    print(f'  [{mode}] 描画 OK')


gui = SliderGUI(m=5, n=5, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False

# ------------------------------------------------------------------ 方形
gui.new_puzzle(5, 5, 1)
gui.game.opt('h', 2, gui.game.blocks[0])
gui.selected_gap = ('h', 2)
gui._sel_anim_timer = 30
gui._sel_anim_is_undo = True
draw_one(gui, '方形 5×5')

# ------------------------------------------------------------------ 三角
gui.new_triangle_puzzle(3, 1)
gui._center_triangle()
from game_triangle import gap_index_range  # noqa: E402

cells = gui.game.positions()
rng = gap_index_range('n', cells)
line = rng[len(rng) // 2]
gui.game.opt('n', line, gui.game.blocks[len(gui.game.blocks) // 2])
gui.selected_gap = ('n', line)
draw_one(gui, f'三角 k=3 n={line}')

# ------------------------------------------------------------------ 米字
gui.new_mi_puzzle(3, 3, 1)
gui._fit_mi_zoom()
gui._center_mi()
mi_blocks = gui.game.blocks
gui.game.opt('d1', 0, mi_blocks[len(mi_blocks) // 2])
gui.selected_gap = ('d1', 0)
draw_one(gui, '米字 3×3 d1=0')

print('\nS1 渲染冒烟：三形态全部通过。')
