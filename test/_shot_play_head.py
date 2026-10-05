# -*- coding: utf-8 -*-
"""S2-1：把「求解演示正在动的那一组」的光边在三种谜题上各截一张图。

执行：``D:/python/python.exe -u test/_shot_play_head.py``
输出 experiments/out/play_head_{square,tri,mi}.png

构造的是「求解播放到某一步、动画进度 35%」的瞬间：整片 be_opted 提亮
（原始特色）+ 该组边框走青绿光边。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'experiments', 'out')


def arm(gui, blocks, progress=0.35):
    """摆成求解播放中、这一步正在动的状态（含渲染插值要用到的字段）。"""
    gui.macro_executing = True
    gui.animating = True
    gui.anim_blocks = list(blocks)
    gui.anim_start_pos = [list(b.location) for b in blocks]
    gui.anim_end_pos = [list(b.location) for b in blocks]
    gui._anim_dr = 0.0
    gui._anim_dc = 0.0
    gui.anim_progress = progress


def shot(gui, name, draw, note):
    gui.screen.fill((30, 30, 30))
    draw()
    ph = gui._play_head_border()
    print(f'   {name}: 光边 {ph}，动画组 {len(gui.anim_blocks)} 块')
    pygame.image.save(gui.screen, os.path.join(OUT, f'play_head_{name}.png'))
    print('   →', f'play_head_{name}.png', note)
    gui.macro_executing = False
    gui.animating = False
    gui.anim_blocks = []


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.ui_mode = 'enhanced'
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()

print('方形 6×6 横缝 h=3：')
gui.new_puzzle(6, 6, 1)
b = gui.game.blocks[len(gui.game.blocks) // 2]
gui.game.opt('h', 3, b)
grp = [x for x in gui.game.blocks if x.be_opted]
arm(gui, grp)
shot(gui, 'square', gui.draw_board, '整片提亮 + 青绿光边标出正在动的组')

print('三角 k=3：')
gui.new_triangle_puzzle(3, 1)
if hasattr(gui, '_fit_triangle_zoom'):
    gui._fit_triangle_zoom()
gui._center_triangle()
from game_triangle import gap_index_range  # noqa: E402
rng = gap_index_range('n', gui.game.positions())
line = rng[len(rng) // 2]
tb = gui.game.blocks[len(gui.game.blocks) // 2]
gui.game.opt('n', line, tb)
arm(gui, [x for x in gui.game.blocks if x.be_opted])
shot(gui, 'tri', gui.draw_triangle_board, '三角多边形描边同样上光边')

print('米字 3×3：')
gui.new_mi_puzzle(3, 3, 1)
gui._fit_mi_zoom()
gui._center_mi()
mb = gui.game.blocks[len(gui.game.blocks) // 2]
gui.game.opt('d1', 0, mb)
arm(gui, [x for x in gui.game.blocks if x.be_opted])
shot(gui, 'mi', gui.draw_mi_board, '米字带晶格档 q 的键也能命中')
