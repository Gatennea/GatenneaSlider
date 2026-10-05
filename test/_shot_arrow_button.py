# -*- coding: utf-8 -*-
"""把「贴图版箭头按键」在三种谜题上各截一张图，人工看样子。

执行：``D:/python/python.exe -u test/_shot_arrow_button.py``
输出 experiments/out/arrow_btn_{square,tri,mi}.png
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


def shot(gui, name, note):
    gui.screen.fill((30, 30, 30))
    gui.draw_board()
    btns = gui._get_gap_direction_annotation()
    if btns:
        for d, (ax, ay), ang, mv in btns['buttons']:
            print(f'   {name} 端 {d}: 中心({ax:.0f},{ay:.0f}) 旋转{ang:.0f}° '
                  f'{"可走" if mv else "禁用(不画)"}')
    pygame.image.save(gui.screen, os.path.join(OUT, f'arrow_btn_{name}.png'))
    print('   →', f'arrow_btn_{name}.png', note)


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.ui_mode = 'enhanced'
# 画布必须按 GUI 自己的 screen_width/height 建：按键的「出屏收缩」是按
# 这两个值算的，窗口小了会把按键推到可视区外（几何没错，只是截不到）
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()

print('方形 6×6 横缝：')
gui.new_puzzle(6, 6, 1)
b = gui.game.blocks[len(gui.game.blocks) // 2]
gui.game.opt('h', 3, b)
gui.selected_gap = ('h', 3)
gui.selected_block = b
# 模拟「选中滑块那一下的鼠标点」：取该块的屏幕位置
_bx, _by = gui._key_center(tuple(b.location))
gui._gap_anchor_world = gui.screen_to_world(_bx, _by)
shot(gui, 'square', '两键摆在选中滑块那一点两侧')

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
gui.selected_gap = ('n', line)
gui.selected_block = tb
_tx, _ty = gui._key_center(tuple(tb.location))
gui._gap_anchor_world = gui.screen_to_world(_tx, _ty)
shot(gui, 'tri', '斜向按键（箭头随屏幕向量旋转）')

print('米字 3×3 对角缝：')
gui.new_mi_puzzle(3, 3, 1)
gui._fit_mi_zoom()
gui._center_mi()
mb = gui.game.blocks[len(gui.game.blocks) // 2]
gui.game.opt('d1', 0, mb)
gui.selected_gap = ('d1', 0)
gui.selected_block = mb
_mx, _my = gui._key_center(tuple(mb.location))
gui._gap_anchor_world = gui.screen_to_world(_mx, _my)
shot(gui, 'mi', '对角族按键')
