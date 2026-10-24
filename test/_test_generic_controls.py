# -*- coding: utf-8 -*-
"""回归：几何引擎板型的操作方式（用户 2026-10-24 定）。

规则：**只支持「箭头 + 两次触控」**。键鼠方向键、单次触控（拖拽角度猜缝）、
虚拟键盘（键位按形状排布）都与形状强相关，新板型一律不支持。

本测试钉住四件事：
  A. 建局后控制开关的状态（两次触控开，其余关）；
  B. 两次触控：先选缝，再拖块——**缝必须保持不变**（旧实现会按拖拽方向改判）；
  C. 没有预选缝时拖拽 → 拒绝并提示（不再自动猜缝）；
  D. 箭头按键可点，走的还是那条缝、方向正确。
"""
import os
import queue
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return cond


def make(port):
    gui = SliderGUI(m=4, n=4, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': port})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.animation_enabled = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui.new_shatter_puzzle(1)
    gui.center_map()
    return gui


def pick_gap(gui, side=0):
    g = gui.game
    for fam in g.spec.seam_families:
        for line in range(-60, 61):
            if not (g.is_valid_gap(fam.name, line)
                    and g.is_live_gap(fam.name, line)):
                continue
            blk = gui._find_block_on_side(fam.name, line, side)
            if blk is not None:
                return fam.name, line, blk
    return None, None, None


def main():
    gui = make(5160)
    g = gui.game

    # A. 控制开关
    check(gui.control_two_touch is True, '两次触控：开')
    check(gui.control_single_touch is False, '单次触控：关（几何引擎板型不支持）')
    check(gui.control_mouse_kb is False, '鼠标键盘方向键：关')
    check(getattr(gui, 'show_virtual_keyboard', False) is False, '虚拟键盘：关')
    check(gui._generic_controls_locked() is True, '通用板型判定为「操作入口锁定」')

    fam, line, blk = pick_gap(gui)
    check(fam is not None, f'找到可用缝 {fam} {line}')

    # B. 两次触控：缝保持
    gui.selected_gap = (fam, line)
    g._clear_selection()
    key = tuple(blk.location)
    letters = gui._gap_dir_letters(fam) or ()
    letter = letters[-1]
    vx, vy = gui._letter_screen_vec(letter, key)
    ok = gui._init_generic_drag_follow(blk, vx * 2.0, vy * 2.0)
    check(ok is True, '沿缝方向拖 → 起跟随')
    check(gui.selected_gap == (fam, line), '缝保持不变（沿缝拖）',
          f'{gui.selected_gap} vs {(fam, line)}')
    check(gui.drag_follow_direction in letters,
          '锁定方向属于该缝的平行方向')
    check(gui.drag_follow_auto_deselect is False,
          '两次触控松手后保留选中（auto_deselect=False）')
    gui.drag_following = False

    # 垂直拖：旧实现会因此把缝改判成另一族
    gui.selected_gap = (fam, line)
    g._clear_selection()
    before = gui.selected_gap
    gui._init_generic_drag_follow(blk, -vy * 2.0, vx * 2.0)
    check(gui.selected_gap == before, '垂直拖拽不会改判缝',
          f'{before} -> {gui.selected_gap}')
    gui.drag_following = False

    # C. 无预选缝：拒绝
    gui.selected_gap = None
    g._clear_selection()
    ok = gui._init_generic_drag_follow(blk, vx * 2.0, vy * 2.0)
    check(ok is False, '无预选缝时拖拽被拒绝（不猜缝）')
    check('先点选缝隙' in (gui.macro_notify_msg or ''), '并给出两次触控提示',
          f'msg={gui.macro_notify_msg!r}')

    # D. 箭头可点
    gui.selected_gap = (fam, line)
    gui.selected_block = blk
    g.opt(fam, line, blk)
    gui.draw_board()
    btns = list(getattr(gui, '_arrow_buttons', []))
    check(bool(btns), f'箭头命中矩形已生成（{len(btns)} 个）')
    if btns:
        d, rect = btns[0]
        step0 = gui.step_count
        pygame.event.post(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {'pos': rect.center, 'button': 1}))
        pygame.event.post(pygame.event.Event(
            pygame.MOUSEBUTTONUP, {'pos': rect.center, 'button': 1}))
        gui.handle_events()
        check(gui.step_count == step0 + 1,
              f'点箭头 {d!r} 走了一步（{step0} → {gui.step_count}）')
        check(gui.selected_gap == (fam, line), '点箭头后缝仍在（可继续点）',
              f'{gui.selected_gap}')

    print(f'\n通过 {_ok[0]} 项，失败 {len(_fail)} 项')
    if _fail:
        for m in _fail:
            print('  ✗', m)
        print('FAILED')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
