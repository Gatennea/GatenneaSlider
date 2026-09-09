# -*- coding: utf-8 -*-
r"""
复原成功悬浮窗（1a）headless 冒烟测试（dummy video，不开窗口）

验证点：
    1. 撤销回到复原 → 弹出（_solved_popup_active=True, 计时归零）
    2. 重做到达复原 → 不弹（via_redo 抑制）
    3. 语义：达成时才弹、不重复弹、离开复原后再达成可再弹
    4. 绘制：各阶段 t 值不抛异常、超时自动淡出关闭
    5. 事件：Esc 关闭 / Enter 调用 save_to_file 并关闭 / 点悬浮窗关闭 / 点窗外不关闭

运行：
    D:\python\python.exe 測試\_test_solved_popup.py
"""

import os
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

import pygame
from game import Block


def _place_blocks(gui, coords):
    """仅摆放滑块与更新矩阵，不动历史记录。"""
    gui.game.blocks = [Block(list(p)) for p in sorted(coords)]
    gui.game.update_matrix()
    gui.center_map()
    gui.selected_gap = None
    gui.selected_block = None
    for b in gui.game.blocks:
        b.be_opted = False


def _set_board(gui, coords):
    """把 gui.game 替换为给定坐标集，并重置历史（快照仅含当前态）。"""
    _place_blocks(gui, coords)
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)


def main():
    from GUI import SliderGUI
    gui = SliderGUI(m=3, n=3, step=2)
    gui.animation_enabled = False
    gui.new_puzzle(3, 3, 2)
    ok_all = True

    solved = set((r, c) for r in range(3) for c in range(3))
    # 非复原：窗内挖掉 (1,1)，窗外补一块 (2,3) → 3×4 非矩形
    not_solved = set(solved)
    not_solved.discard((1, 1))
    not_solved.add((2, 3))

    def reset_popup():
        gui._solved_popup_active = False
        gui._solved_popup_t = 0
        gui._prev_solved = False

    # ---- 1. 撤销路径：非复原 → 撤销 → 复原 → 不弹（suppress 抑制） ----
    print('1 撤销达成复原→不弹：')
    reset_popup()
    gui._solved_popup_t = 77            # 残余计时：不应被撤销重置
    # 快照0=复原, 快照1=非复原, 索引=1
    _set_board(gui, solved)
    _place_blocks(gui, not_solved)
    gui.game_history.save_snapshot(gui.game)
    assert gui.game_history.history_index == 1
    gui.undo()  # 回到复原
    assert gui.game.is_solved(), 'undo 后应为复原'
    assert not gui._solved_popup_active, 'undo 回到复原不应弹窗'
    assert gui._solved_popup_t == 77, '撤销不应触碰悬浮窗计时'
    assert gui._prev_solved is True
    print('  OK')

    # ---- 2. 重做路径：非复原 → 重做 → 复原 → 不弹 ----
    print('2 重做达成复原→不弹：')
    # 快照0=非复原, 快照1=复原；先 undo 到 0，再 redo 到 1
    reset_popup()
    _set_board(gui, not_solved)
    _place_blocks(gui, solved)
    gui.game_history.save_snapshot(gui.game)
    assert gui.game_history.history_index == 1
    gui.undo()   # → 非复原（不应弹）
    assert not gui._solved_popup_active
    gui.redo()   # → 复原（via_redo 抑制，不应弹）
    assert gui.game.is_solved(), 'redo 后应为复原'
    assert not gui._solved_popup_active, 'redo 达成复原不应弹窗'
    assert gui._prev_solved is True
    print('  OK')

    # ---- 3. 语义：达成才弹 / 不重复弹 / 离开再达成可再弹 ----
    print('3 达成/防重复/再达成：')
    reset_popup()
    _set_board(gui, solved)
    gui._maybe_show_solved_popup()
    assert gui._solved_popup_active and gui._solved_popup_t == 0
    gui._solved_popup_t = 7
    gui._maybe_show_solved_popup()          # 仍复原 → 不重置计时
    assert gui._solved_popup_t == 7, '重复调用不应重置计时'
    _set_board(gui, not_solved)
    gui._maybe_show_solved_popup()          # 离开复原 → 仅同步 _prev_solved
    assert gui._prev_solved is False and gui._solved_popup_active
    _set_board(gui, solved)
    gui._maybe_show_solved_popup()          # 再达成 → 重新弹
    assert gui._solved_popup_active and gui._solved_popup_t == 0
    print('  OK')

    # ---- 4. via_redo 直接抑制 ----
    print('4 via_redo 抑制：')
    reset_popup()
    _set_board(gui, solved)
    gui._solved_popup_t = 77
    gui._maybe_show_solved_popup(via_redo=True)
    assert not gui._solved_popup_active, 'via_redo 不应弹'
    assert gui._prev_solved is True
    assert gui._solved_popup_t == 77
    print('  OK')

    # ---- 5. 绘制各阶段 ----
    print('5 绘制冒烟：')
    _set_board(gui, solved)
    gui._solved_popup_active = True
    for t in (0, 3, 6, 12, 100, 359, 360, 370, 374):
        gui._solved_popup_t = t
        gui.draw_solved_popup()
    assert gui._solved_popup_rect, '未记录悬浮窗点击区域'
    assert gui._solved_popup_active, '374 帧时仍应显示'
    gui._solved_popup_t = 376          # 超过 360+15 → 自动关闭
    gui.draw_solved_popup()
    assert not gui._solved_popup_active, '超时应自动关闭'
    print('  OK')

    # ---- 6. 事件 ----
    print('6 事件：')
    # 6a Esc 关闭
    reset_popup()
    gui._solved_popup_active = True
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    gui.handle_events()
    assert not gui._solved_popup_active, 'Esc 未关闭'
    # 6b Enter 保存并关闭
    calls = []
    gui.save_to_file = lambda: calls.append(1)
    reset_popup()
    gui._solved_popup_active = True
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    gui.handle_events()
    assert not gui._solved_popup_active, 'Enter 未关闭'
    assert calls == [1], 'Enter 未触发保存'
    # 6c 点击悬浮窗内部关闭
    reset_popup()
    gui._solved_popup_active = True
    gui._solved_popup_rect = pygame.Rect(100, 100, 400, 180)
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, pos=(300, 190), button=1))
    gui.handle_events()
    assert not gui._solved_popup_active, '点击悬浮窗未关闭'
    # 6d 点击窗外不关闭（事件放行到游戏）
    reset_popup()
    gui._solved_popup_active = True
    gui._solved_popup_rect = pygame.Rect(100, 100, 400, 180)
    pygame.event.clear()
    bottom_y = gui.screen_height - gui.status_bar_height + 2
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, pos=(60, bottom_y), button=1))
    gui.handle_events()
    assert gui._solved_popup_active, '点击窗外不应关闭悬浮窗'
    print('  OK')

    print('\n全部通过' if ok_all else '\n存在失败')
    return 0 if ok_all else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)