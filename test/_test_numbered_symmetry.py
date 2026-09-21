# -*- coding: utf-8 -*-
"""带序号判胜：编号排列须按行主序，但允许整体旋转/镜像（矩形 D4 群，8 种）"""
import os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pygame
pygame.init()
from GUI import SliderGUI

ROWS, COLS = 4, 3   # 非正方：旋转/转置会改变朝向，便于区分 8 种变换

gui = SliderGUI()
gui.save_readonly_flag = False
gui.new_puzzle(ROWS, COLS, 1, numbered=True)

bounds = gui.game.matrix_bounds
min_row, min_col = bounds['min_row'], bounds['min_col']


def assign_numbers(fn, rows2, cols2):
    """按变换 fn 重排编号：(i,j) 处的号 = fn(i,j) 在 rows2×cols2 网格里的行主序序号"""
    for b in gui.game.blocks:
        i = b.location[0] - min_row
        j = b.location[1] - min_col
        a, c = fn(i, j)
        b.number = a * cols2 + c + 1
    gui.game.update_matrix()


def numbers_on_board():
    return {tuple(b.location): b.number for b in gui.game.blocks}


# 初始（恒等）排列 → 已复原
assert gui.is_solved() is True
print('PASS: 恒等排列判胜')

# 8 种对称变换逐一验证
transforms = (
    ('恒等',       lambda i, j: (i, j), ROWS, COLS),
    ('旋转180°',   lambda i, j: (ROWS - 1 - i, COLS - 1 - j), ROWS, COLS),
    ('上下镜像',   lambda i, j: (ROWS - 1 - i, j), ROWS, COLS),
    ('左右镜像',   lambda i, j: (i, COLS - 1 - j), ROWS, COLS),
    ('主对角线翻转', lambda i, j: (j, i), COLS, ROWS),
    ('副对角线翻转', lambda i, j: (COLS - 1 - j, ROWS - 1 - i), COLS, ROWS),
    ('旋转90°',    lambda i, j: (j, ROWS - 1 - i), COLS, ROWS),
    ('旋转270°',   lambda i, j: (COLS - 1 - j, i), COLS, ROWS),
)
for name, fn, rows2, cols2 in transforms:
    assign_numbers(fn, rows2, cols2)
    assert gui.is_solved() is True, f'{name} 应判胜'
    print(f'PASS: {name} 判胜（编号仍按序）')

# 物理旋转实测：把整个排列旋转 180°（块移动、编号跟随），应判胜
gui.new_puzzle(ROWS, COLS, 1, numbered=True)
for b in gui.game.blocks:
    i, j = b.location[0] - min_row, b.location[1] - min_col
    b.location = [min_row + (ROWS - 1 - i), min_col + (COLS - 1 - j)]
gui.game.update_matrix()
assert gui.is_solved() is True, '物理旋转 180° 后应判胜'
print('PASS: 物理旋转 180°（编号随块移动）判胜')

# 打乱两个编号 → 任何对称下都不按序 → 不判胜
gui.new_puzzle(ROWS, COLS, 1, numbered=True)
b0, b1 = gui.game.blocks[0], gui.game.blocks[1]
b0.number, b1.number = b1.number, b0.number
assert gui.is_solved() is False, '编号错位不应判胜'
print('PASS: 编号错位不判胜')

# 编号集合错误（缺号/重号）→ 不判胜
gui.new_puzzle(ROWS, COLS, 1, numbered=True)
gui.game.blocks[0].number = 999
assert gui.is_solved() is False
print('PASS: 编号集合错误不判胜')

# 形状非矩形（挖一块）→ 不判胜（即使剩下的编号恰好按序）
gui.new_puzzle(ROWS, COLS, 1, numbered=True)
victim = gui.game.blocks[-1]
gui.game.blocks.remove(victim)
gui.game.update_matrix()
assert gui.is_solved() is False, '非矩形不应判胜'
print('PASS: 形状非矩形不判胜')

# 正方 3x3：转置即旋转，同样接受
gui.new_puzzle(3, 3, 1, numbered=True)
bd = gui.game.matrix_bounds
for b in gui.game.blocks:
    i, j = b.location[0] - bd['min_row'], b.location[1] - bd['min_col']
    b.number = j * 3 + i + 1          # 转置后的行主序
gui.game.update_matrix()
assert gui.is_solved() is True
print('PASS: 正方 3x3 转置判胜')

# 普通方形不受影响
gui.new_puzzle(4, 4, 2)
assert gui.numbered is False
gui.shuffle_puzzle()
assert gui.is_solved() is False
gui.reset_puzzle()
assert gui.is_solved() is True
print('PASS: 普通方形判胜逻辑不变')

print('numbered symmetry PASS')
pygame.quit()
