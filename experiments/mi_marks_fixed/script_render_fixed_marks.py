# -*- coding: utf-8 -*-
"""渲染「片级锚点修复版」的 mi 标记，供人工回看（归档用，非测试）。

背景（2026-10-05）：
    早前 mi 标记画在**格心**，一格 4 片（N/E/S/W）的标记全叠在同一点 → 糊成一团。
    修复（commit ``a868f3a``）改为画在**每一片自己的内心**，四片分落格的四方。
    用户看过之后觉得「还是比较乱」，最终决定 mi 干脆不标、只留目标框
    （feat 分支 commit ``13e7184`` 已移除 mi 标记）。

    本脚本把**修复版的样子**留成图片，避免以后「修复到底长啥样」失传。

⚠️ 本脚本只在**含修复的版本**（``a868f3a`` 及其祖先）上有效。
    在已移除 mi 标记的 feat 分支上跑，会得到「只有绿框、无任何标记」的画面。

执行：
    git checkout a868f3a
    D:/python/python.exe experiments/mi_marks_fixed/script_script_render_fixed_marks.py
    git checkout feat/ui-animation

导出到本目录：
    mi_marks_one_hole.png   还原本 + 挖掉正中一格 → 该格 4 片标记，应清晰分开
    mi_marks_shuffled.png   打乱態（多洞）→ 标记落满缺片，就是当时的「乱」场面
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402


def render(gui):
    """画一帧完整画面：棋盘（含目标框与标记）+ 调试面板。"""
    gui.screen.fill((0, 0, 0))
    gui._fit_mi_zoom()
    gui._center_mi()
    gui.draw_mi_board()
    gui.draw_metrics_panel()


def shoot(gui, name):
    path = os.path.join(_HERE, name)
    pygame.image.save(gui.screen, path)
    print(f'saved: {path}')


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False
gui.show_metrics_panel = True

# ---------------------------------------------------- 干净样例：1 格洞 → 4 片标记
gui.new_mi_puzzle(4, 4, 2)
g = gui.game
removed = [b for b in list(g.blocks)
           if b.location[0] == 1 and b.location[1] == 1]
for b in removed:
    g.blocks.remove(b)
g.update_matrix()
gui._compute_target_region()
gui.mp_pos = [gui.screen_width - 200, 8]
render(gui)
shoot(gui, 'mi_marks_one_hole.png')
print(f'干净样例：挖掉 (1,1) 共 {len(removed)} 片 → 应画 {len(removed)} 个分开的标记')

# ---------------------------------------------------- 打乱态：多洞多标记（当时的「乱」）
import random  # noqa: E402
random.seed(7)
gui.game.shuffle(40, 2)
gui._compute_target_region()
gui.mp_pos = [gui.screen_width - 200, 8]
render(gui)
shoot(gui, 'mi_marks_shuffled.png')
print('打乱态：已导出（多洞多标记）')

print('done.')
