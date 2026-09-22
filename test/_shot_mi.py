# -*- coding: utf-8 -*-
"""把米字格建局態（實心矩形）截圖存成 test/_shot_mi*.png 供人工查看形狀。

執行：python test/_shot_mi.py
導出：
    test/_shot_mi_6x6.png   6×6 等級2（菜單預設同款）
    test/_shot_mi_4x4.png   4×4 等級1（格數少，容易數清一塊 = 四分之一格）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))

gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False

for (m, n, step, name) in ((6, 6, 2, '_shot_mi_6x6.png'),
                           (4, 4, 1, '_shot_mi_4x4.png')):
    gui.new_mi_puzzle(m, n, step)
    gui.draw_board()
    out = os.path.join(_HERE, name)
    pygame.image.save(gui.screen, out)
    print(f"saved: {out}  ({m}×{n} 等級{step}, "
          f"{len(gui.game.blocks)} 塊, is_solved={gui.is_solved()}, "
          f"zoom={gui.zoom:.3f})")
