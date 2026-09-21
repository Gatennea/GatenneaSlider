# -*- coding: utf-8 -*-
"""A6：带序号谜题的 P2 体验项冒烟（免费获得的功能不应回归）"""
import os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pygame
pygame.init()
from GUI import SliderGUI

gui = SliderGUI()
gui.new_puzzle(4, 4, 2, numbered=True)


def draw_frame():
    """按 run() 主循环的顺序绘制一帧"""
    gui.draw_board()
    gui.draw_right_panel()
    gui.draw_menu_bar()
    gui.draw_status_bar()


# 1. 渲染整帧（含序号文字）不崩
draw_frame()
print('PASS: 带序号渲染整帧')

# 2. 虚拟键盘绘制
gui.show_virtual_keyboard = True
gui.draw_virtual_keyboard()
gui.show_virtual_keyboard = False
print('PASS: 虚拟键盘渲染')

# 3. 连锁提示
cells = gui._chain_hint_cells()
assert isinstance(cells, (list, set, tuple)) or cells is None
print('PASS: 连锁提示计算')

# 4. 相机缩放/居中（免费项）
gui.zoom = 1.5
gui.center_map()
gui.ensure_blocks_visible()
draw_frame()
print('PASS: 相机缩放/居中 + 缩放后渲染')

# 5. 拖拽跟随意象：初始化 → 滑动 → 清理
block = gui.game.blocks[0]
gui._init_drag_follow(block, 0, 0)
gui._drag_slide(block, 10, 0)
draw_frame()
gui.clear_drag_follow()
draw_frame()
print('PASS: 拖拽跟随意象 + 预览渲染')

# 6. 三段式操作：选缝 → 选块 → 移动（核心操作在序号模式下不变）
gui.new_puzzle(4, 4, 2, numbered=True)
gui.shuffle_puzzle()
before = {tuple(b.location): b.number for b in gui.game.blocks}
moved = False
bounds = gui.game.matrix_bounds
for gap_type in ('h', 'v'):
    axis = 0 if gap_type == 'h' else 1
    for line in range(bounds['min_row'] if gap_type == 'h' else bounds['min_col'],
                      (bounds['max_row'] if gap_type == 'h' else bounds['max_col']) + 1):
        gui.selected_gap = (gap_type, line)
        for b in gui.game.blocks:
            gui.game.opt(gap_type, line, b)
            if not any(x.be_opted for x in gui.game.blocks):
                continue
            gui.selected_block = b
            for d in ('w', 's', 'a', 'd'):
                if gui.move_selected_blocks(d):
                    moved = True
                    break
            if moved:
                break
        if moved:
            break
    if moved:
        break
if moved:
    after = {tuple(b.location): b.number for b in gui.game.blocks}
    assert set(after.values()) == set(before.values()), '移动后编号集合应不变'
    assert len(after) == len(before), '滑块数量不应变'
    gui.game_history.save_snapshot(gui.game, session_key=None, move_info=None)
    gui.undo()
    restored = {tuple(b.location): b.number for b in gui.game.blocks}
    assert restored == before, '撤销后编号-位置映射应完全恢复'
    print('PASS: 三段式移动 + 撤销，编号-位置映射完全恢复')
else:
    print('SKIP: 未找到合法移动组合')

print('A6 numbered P2 smoke PASS')
pygame.quit()
