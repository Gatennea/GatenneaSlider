# -*- coding: utf-8 -*-
"""把 S1 的方向标注在三种谜题上的样子截出来，供人工验收。

要看的三件事：
  1. 标注**在滑块之上**（不再被压掉一半）；
  2. 两端位于**选中切片**沿推行方向的外沿附近——换一个锚点块，端点要跟着移；
  3. 能走→绿底箭头+格数，不能走→灰底灰叉。

执行：``D:/python/python.exe test/_shot_gap_annot.py``
导出到 ``experiments/out/``：gap_annot_{square,tri,mi}.png
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_triangle import gap_index_range  # noqa: E402

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'experiments', 'out')
os.makedirs(_OUT, exist_ok=True)


def render(gui, name):
    gui.screen.fill((0, 0, 0))
    gui.draw_board()
    pygame.display.flip()
    path = os.path.join(_OUT, name)
    pygame.image.save(gui.screen, path)
    print(f'saved: {path}')


def select(gui, gap_type, line, block):
    gui.game.opt(gap_type, line, block)
    gui.selected_gap = (gap_type, line)
    annot = gui._get_gap_direction_annotation()
    n = len([b for b in gui.game.blocks if b.be_opted])
    if annot:
        ends = [(d, round(ax), round(ay), ms)
                for d, (ax, ay), ms, _uv in annot['ends']]
        print(f'  gap=({gap_type}, {line}) 带走 {n} 块 → 端点 {ends}')
    else:
        print(f'  gap=({gap_type}, {line}) 带走 {n} 块 → 无标注')


gui = SliderGUI(m=5, n=5, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False
gui.ui_mode = 'enhanced'

# ------------------------------------------------------------------ 方形
gui.new_puzzle(5, 5, 1)
gui.center_map()
select(gui, 'h', 2, gui.game.blocks[-1])
render(gui, 'gap_annot_square.png')

# ------------------------------------------------------------------ 三角
gui.new_triangle_puzzle(3, 1)
gui._center_triangle()
rng = gap_index_range('n', gui.game.positions())
select(gui, 'n', rng[len(rng) // 2], gui.game.blocks[len(gui.game.blocks) // 2])
render(gui, 'gap_annot_tri.png')

# ------------------------------------------------------------------ 米字
gui.new_mi_puzzle(3, 3, 1)
gui._fit_mi_zoom()
gui._center_mi()
mb = gui.game.blocks
select(gui, 'd1', 0, mb[len(mb) // 2])
render(gui, 'gap_annot_mi.png')

print('done.')
