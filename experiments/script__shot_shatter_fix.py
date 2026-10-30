# -*- coding: utf-8 -*-
"""验证通用通道去顶点星刺后的碎三角渲染。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
from GUI import SliderGUI

TMP = 'C:/Users/guo/AppData/Local/Temp'

g = SliderGUI()
g.animation_enabled = False
g.new_model_puzzle('shatter', 1)

# 全景 zoom=1
g.zoom = 1.0
g.center_map()
g.draw_board()
pygame.image.save(g.screen, os.path.join(TMP, '_sf_full.png'))
print('wrote _sf_full.png')

# 顶点特写 zoom=3
g.zoom = 3.0
g.center_map()
g.draw_board()
pygame.image.save(g.screen, os.path.join(TMP, '_sf_zoom3.png'))
print('wrote _sf_zoom3.png')

# 选中一块，验证特殊态描边仍在
g.zoom = 3.0
g.center_map()
blk = g.game.blocks[10]
blk.be_opted = True
g.draw_board()
pygame.image.save(g.screen, os.path.join(TMP, '_sf_selected.png'))
print('wrote _sf_selected.png')
