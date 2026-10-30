# -*- coding: utf-8 -*-
"""圆角几何修正后，检查方形/三角/米字三形态是否被影响（回归对照）。"""
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


def shot(kind, name, zoom=1.0):
    g.new_puzzle(kind, 1)
    g.zoom = zoom
    g.center_map()
    g.draw_board()
    pygame.image.save(g.screen, os.path.join(TMP, name))
    print('wrote', name)


g.new_puzzle(6, 6, 1)
for nm, z in (('_chk_square.png', 1.0),):
    g.zoom = z
    g.center_map()
    g.draw_board()
    pygame.image.save(g.screen, os.path.join(TMP, nm))
    print('wrote', nm)

g.new_triangle_puzzle(6, 1)
for nm, z in (('_chk_tri.png', 1.0), ('_chk_tri_z2.png', 2.0)):
    g.zoom = z
    g.center_map()
    g.draw_board()
    pygame.image.save(g.screen, os.path.join(TMP, nm))
    print('wrote', nm)

g.new_mi_puzzle(6, 6, 1)
for nm, z in (('_chk_mi.png', 1.0), ('_chk_mi_z2.png', 2.0)):
    g.zoom = z
    g.center_map()
    g.draw_board()
    pygame.image.save(g.screen, os.path.join(TMP, nm))
    print('wrote', nm)
