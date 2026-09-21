# -*- coding: utf-8 -*-
"""回归：带序号模式下，形状复原但编号无序时不得显示/判定为已复原

复现用户验收发现的问题：6×6 实心矩形 + 编号乱序，左下角状态栏却显示「复原」。
根因是 draw_status_bar 调 game.is_solved()（只看形状），绕过 GUI 层的编号检查。
"""
import os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pygame
pygame.init()
from GUI import SliderGUI

# 用户存档里的真实 numbers 矩阵（6×6，1..36 各一次，但完全无序）
SCRAMBLED = [
    [5, 6, 3, 4, 17, 18],
    [11, 12, 9, 10, 23, 24],
    [1, 2, 15, 16, 29, 30],
    [7, 8, 21, 22, 35, 36],
    [13, 14, 25, 26, 27, 28],
    [19, 20, 31, 32, 33, 34],
]

gui = SliderGUI()
gui.save_readonly_flag = False
gui.new_puzzle(6, 6, 2, numbered=True)

# 把编号按用户矩阵写进棋盘（位置与矩阵一一对应）
bounds = gui.game.matrix_bounds
min_row, min_col = bounds['min_row'], bounds['min_col']
for b in gui.game.blocks:
    r, c = b.location[0] - min_row, b.location[1] - min_col
    b.number = SCRAMBLED[r][c]
gui.game.update_matrix()

# 1. 形状确实是实心 6×6
assert gui.game.is_solved() is True, '形状应为实心矩形'
# 2. 但带序号判定必须为 False
assert gui.is_solved() is False, '编号无序时不得判胜'
print('PASS: 形状复原+编号无序 → is_solved() = False')

# 3. 状态栏文字必须走 GUI 层判定（而非 game.is_solved()）
#    方法：临时让两层判定互相矛盾，采样状态栏文字像素颜色
def status_has_color(target):
    gui.draw_status_bar()
    text_y = gui.screen_height - gui.status_bar_height + (gui.status_bar_height - 14) // 2
    region = gui.screen.subsurface(pygame.Rect(8, text_y - 4, 150, 24)).copy()
    for x in range(region.get_width()):
        for y in range(region.get_height()):
            px = region.get_at((x, y))[:3]
            if all(abs(px[i] - target[i]) <= 12 for i in range(3)):
                return True
    return False


solved_color, unsolved_color = gui.colors['solved'], gui.colors['unsolved']
game_cls = type(gui.game)
orig_game_is_solved = game_cls.is_solved
orig_gui_is_solved = SliderGUI.is_solved
try:
    # 矛盾场景 A：GUI 层说未复原、game 层说复原 → 状态栏应显示「未复原」
    SliderGUI.is_solved = lambda self: False
    game_cls.is_solved = lambda self: True
    assert not status_has_color(solved_color), '状态栏不得用 game.is_solved() 判复原'
    assert status_has_color(unsolved_color), '状态栏应显示未复原色'
    print('PASS: 状态栏用 GUI 层判定（矛盾场景显示未复原）')

    # 矛盾场景 B：GUI 层说复原、game 层说未复原 → 状态栏应显示「复原」
    SliderGUI.is_solved = lambda self: True
    game_cls.is_solved = lambda self: False
    assert status_has_color(solved_color), '状态栏应显示复原色'
    print('PASS: 状态栏跟随 GUI 层判定显示复原')
finally:
    SliderGUI.is_solved = orig_gui_is_solved
    game_cls.is_solved = orig_game_is_solved

# 5. 对照组：编号正确时必须判胜
gui.new_puzzle(6, 6, 2, numbered=True)
assert gui.is_solved() is True
print('PASS: 编号正确的 6×6 判胜')

print('numbered status-bar regression PASS')
pygame.quit()
