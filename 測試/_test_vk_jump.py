# -*- coding: utf-8 -*-
r"""
虚拟键盘跳到某步（1c）headless 冒烟测试（dummy video，不开窗口）

验证点：
    1. 布局：面板含步数输入框与“跳到”按钮矩形
    2. jump_to_history_index：跳到指定历史索引，棋盘恢复、step_count 同步、版本+1
    3. 输入框：仅接受数字、最多4位、退格删除
    4. 回车跳转：跳到对应步、清空缓冲、失焦
    5. 未聚焦时按键不消费
    6. 超出范围：跳到最后一档，并提示
    7. Esc：清空缓冲并失焦
    8. 点“跳到”按钮：按当前缓冲跳转

运行：
    D:\python\python.exe 測試\_test_vk_jump.py
"""

import os
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

import pygame
from game import Block

ok_all = True


def _check(name, cond, detail=''):
    global ok_all
    ok_all = ok_all and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def _state(gui, rows, cols):
    """按指定行列集合重建滑块组（用于构造互不相同的状态）"""
    coords = {(r, c) for r in rows for c in cols}
    gui.game.blocks = [Block(list(p)) for p in sorted(coords)]
    gui.game.update_matrix()


def main():
    from GUI import SliderGUI
    gui = SliderGUI(m=5, n=5, step=2)
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    gui.show_virtual_keyboard = True   # 恢复配置可能隐藏面板，测试中强制显示

    # ---- 构造三段历史：A(顶缝 1-4行) → B(0-3行) → C(0-3行右移) ----
    gui.game_history.reset()
    _state(gui, range(1, 5), range(5))
    gui.game_history.save_snapshot(gui.game)        # index 0
    _state(gui, range(0, 4), range(5))
    gui.game_history.save_snapshot(gui.game)        # index 1
    _state(gui, range(0, 4), range(1, 5))
    gui.game_history.save_snapshot(gui.game)        # index 2
    gui.game_history.history_index = 2
    _check('历史构造为3段', len(gui.game_history.history) == 3,
           f'n={len(gui.game_history.history)}')

    # ---- 1. 布局矩形 ----
    gui._vk_build_layout()
    _check('输入框矩形存在', gui.vk_jump_input_rect is not None, str(gui.vk_jump_input_rect))
    _check('按钮矩形存在', gui.vk_jump_btn_rect is not None, str(gui.vk_jump_btn_rect))
    _check('输入框在面板内', gui.vk_panel_rect.contains(gui.vk_jump_input_rect), '')
    _check('按钮在面板内', gui.vk_panel_rect.contains(gui.vk_jump_btn_rect), '')

    # ---- 2. jump_to_history_index ----
    ver_before = gui._board_version
    gui.jump_to_history_index(0)
    _check('跳到历史0', gui.game_history.history_index == 0,
           f'idx={gui.game_history.history_index}')
    _check('棋盘恢复为状态A', gui.game.blocks[0].location == [1, 0],
           str(gui.game.blocks[0].location))
    _check('step_count 同步', gui.step_count == 0, f'step_count={gui.step_count}')
    _check('跳转标记版本+1', gui._board_version == ver_before + 1,
           f'{ver_before}->{gui._board_version}')
    gui.jump_to_history_index(2)
    _check('跳到历史2', gui.game_history.history_index == 2,
           f'idx={gui.game_history.history_index}')

    # ---- 3. 输入框：数字过滤 / 退格 ----
    gui.vk_jump_focus = True
    for key in (pygame.K_1, pygame.K_0):
        gui.handle_virtual_keyboard_event(
            pygame.event.Event(pygame.KEYDOWN, {'key': key, 'mod': 0}))
    _check('缓冲含10', gui.vk_jump_buffer == '10', gui.vk_jump_buffer)
    gui.handle_virtual_keyboard_event(
        pygame.event.Event(pygame.KEYDOWN, {'key': pygame.K_BACKSPACE, 'mod': 0}))
    _check('退格删末位', gui.vk_jump_buffer == '1', gui.vk_jump_buffer)
    for key in (pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
        gui.handle_virtual_keyboard_event(
            pygame.event.Event(pygame.KEYDOWN, {'key': key, 'mod': 0}))
    _check('最多4位', gui.vk_jump_buffer == '1234', gui.vk_jump_buffer)

    # ---- 5. 未聚焦不消费 ----
    gui.vk_jump_focus = False
    gui.vk_jump_buffer = ''
    consumed = gui.handle_virtual_keyboard_event(
        pygame.event.Event(pygame.KEYDOWN, {'key': pygame.K_9, 'mod': 0}))
    _check('未聚焦时按键放行', consumed is False and gui.vk_jump_buffer == '', '')

    # ---- 4. 回车跳转 ----
    gui.vk_jump_focus = True
    gui.vk_jump_buffer = '1'
    gui.handle_virtual_keyboard_event(
        pygame.event.Event(pygame.KEYDOWN, {'key': pygame.K_RETURN, 'mod': 0}))
    _check('回车跳到第1步', gui.game_history.history_index == 1,
           f'idx={gui.game_history.history_index}')
    _check('跳转后清空缓冲', gui.vk_jump_buffer == '', gui.vk_jump_buffer)
    _check('跳转后失焦', not gui.vk_jump_focus, '')

    # ---- 6. 超出范围 ----
    gui.vk_jump_focus = True
    gui.vk_jump_buffer = '99'
    gui.handle_virtual_keyboard_event(
        pygame.event.Event(pygame.KEYDOWN, {'key': pygame.K_RETURN, 'mod': 0}))
    _check('超范围跳到末档', gui.game_history.history_index == 2,
           f'idx={gui.game_history.history_index}')
    _check('超范围有提示', '超出范围' in gui.macro_notify_msg, gui.macro_notify_msg)

    # ---- 7. Esc ----
    gui.vk_jump_focus = True
    gui.vk_jump_buffer = '7'
    consumed = gui.handle_virtual_keyboard_event(
        pygame.event.Event(pygame.KEYDOWN, {'key': pygame.K_ESCAPE, 'mod': 0}))
    _check('Esc 消费并清空', consumed and gui.vk_jump_buffer == '' and not gui.vk_jump_focus, '')

    # ---- 8. 点“跳到”按钮 ----
    gui.vk_jump_buffer = '0'
    gui.vk_jump_focus = True
    btn_center = gui.vk_jump_btn_rect.center
    consumed = gui.handle_virtual_keyboard_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                           {'button': 1, 'pos': btn_center}))
    _check('点按钮消费事件', consumed, '')
    _check('点按钮跳到第0步', gui.game_history.history_index == 0,
           f'idx={gui.game_history.history_index}')

    print('\n' + ('ALL PASS' if ok_all else 'SOME FAILED'))
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()