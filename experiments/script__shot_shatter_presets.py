# -*- coding: utf-8 -*-
"""碎三角圆角/缝宽预设对照：从板型定义直接改 seam_width / corner_radius 渲染。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
from GUI import SliderGUI

TMP = 'C:/Users/guo/AppData/Local/Temp'

PRESETS = [
    (4, 2),     # 细缝小圆角
    (6, 3),     # 当前默认（修正几何后 ≈ 方形 8.3% 的圆角量）
    (8, 4),     # 更明显
    (10, 5),    # 再明显
]


def shot(g, name):
    g.zoom = 1.0
    g.center_map()
    g.draw_board()
    pygame.image.save(g.screen, os.path.join(TMP, name))
    print('wrote', name)


g = SliderGUI()
g.animation_enabled = False
g.new_model_puzzle('shatter', 1)
spec = g.game.board.spec

for sw, cr in PRESETS:
    object.__setattr__(spec, 'seam_width', sw)
    object.__setattr__(spec, 'corner_radius', cr)
    shot(g, f'_sp_{sw}_{cr}.png')

# 放大看顶点：细看节点与圆角
for sw, cr in ((6, 3), (8, 4), (10, 5)):
    object.__setattr__(spec, 'seam_width', sw)
    object.__setattr__(spec, 'corner_radius', cr)
    g.zoom = 2.0
    g.center_map()
    g.draw_board()
    pygame.image.save(g.screen, os.path.join(TMP, f'_sp_z2_{sw}_{cr}.png'))
    print('wrote', f'_sp_z2_{sw}_{cr}.png')
