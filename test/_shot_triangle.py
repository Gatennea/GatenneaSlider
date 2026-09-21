# -*- coding: utf-8 -*-
"""把三角形建局態（實心大三角）截圖存成 test/_shot_triangle.png 供人工查看。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

gui = SliderGUI()
gui.animation_enabled = False
gui.new_triangle_puzzle(6, 2)
gui.draw_board()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_shot_triangle.png')
pygame.image.save(gui.screen, out)
print("saved:", out)
print("is_solved =", gui.is_solved(), " blocks =", len(gui.game.blocks))
