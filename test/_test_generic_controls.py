# -*- coding: utf-8 -*-
"""回归：几何引擎板型的操作方式（用户 2026-10-24 定，2026-10-25 修正）。

原始规则：**只支持「箭头 + 两次触控」**。键鼠方向键、单次触控（拖拽角度猜缝）、
虚拟键盘（键位按形状排布）都与形状强相关，新板型一律不支持。

2026-10-25 修正：模型板型的方向字母表是从几何**派生**的（compat.direction_table
第二级来源，大写 A/B/C…），盘与盘不同，没有「上/下/左/右」语义可映射；但键盘
移动与虚拟键盘都直接吃这张派生表，于是两者对通用通道**重新开放**：
  · 键盘移动：按派生字母键（如 A/B）沿该方向推一步；
  · F1 虚拟键盘：按派生字母表渲染，照常开/关。
两者与「箭头 + 两次触控」并存，不再有「GUI 能开、快捷键开不了」的缺口。

本测试钉住：
  A. 建局后控制开关的状态（两次触控开，其余关）；
  B. 两次触控：先选缝，再拖块——**缝必须保持不变**（旧实现会按拖拽方向改判）；
  C. 没有预选缝时拖拽 → 拒绝并提示（不再自动猜缝）；
  D. 箭头按键可点，走的还是那条缝、方向正确；
  E. 键盘字母键（派生字母表）能推动滑块；
  F. F1 虚拟键盘对通用通道可正常开/关。
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

    # E. 键盘字母键（派生字母表）能推动滑块
    t_keyboard_letters_move()

    # F. F1 虚拟键盘对通用通道可正常开/关（2026-10-25 修）
    t_virtual_keyboard_opens_for_generic()

    print(f'\n通过 {_ok[0]} 项，失败 {len(_fail)} 项')
    if _fail:
        for m in _fail:
            print('  ✗', m)
        print('FAILED')
        sys.exit(1)
    print('ALL PASS')




def _first_movable(gui):
    """返回第一个引擎层面真能推动的 (缝族, line, 块, 字母)。"""
    from engine.compat import direction_table
    g = gui.game
    tbl = direction_table(g.spec)
    for (gf, line) in list(g.all_gaps()):
        fam = next(f for f in g.spec.seam_families if f.name == gf)
        for letter, d in sorted(tbl.items()):
            if d not in fam.parallel:
                continue
            for b in g.blocks:
                g.opt(gf, line, b)
                pos, reason = g.try_move_ex(letter, 1)
                if reason == '':
                    return (gf, line, b, letter)
    return None


def t_keyboard_letters_move():
    """通用通道的键盘方向：按派生字母键能推一步（2026-10-25 修）。

    修之前，事件链只有 mi / triangle / WASD 三支，**通用通道一支都没有**；
    而 WASD 那支又被 new_model_puzzle 强制关掉（control_mouse_kb=False），
    于是自定义谜题载入后键盘完全推不动滑块，只有 GUI 的箭头按键 /
    两次触控能用。这里钉住「字母键 = 该盘派生的方向字母」这条新路。
    """
    gui = make(5160)
    g = gui.game

    from engine.compat import direction_table
    tbl = direction_table(g.spec)
    check(bool(tbl), f'模型板型应派得出方向字母表（实得 {sorted(tbl)}）')

    found = _first_movable(gui)
    check(found is not None, '应至少有一个能推动的方向')
    if found is None:
        return
    gf, line, blk, letter = found

    g.opt(gf, line, blk)
    gui.selected_gap = (gf, line)
    gui.selected_block = blk
    before = [tuple(b.location) for b in g.blocks]
    step0 = gui.step_count

    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {
        'key': getattr(pygame, 'K_' + letter.lower()), 'mod': 0, 'unicode': letter}))
    gui.handle_events()

    check([tuple(b.location) for b in g.blocks] != before,
          f'按字母键 {letter!r} 应真的推动滑块')
    check(gui.step_count == step0 + 1,
          f'步数应 +1（{step0} → {gui.step_count}）')

    # 方向必须平行于选中的缝：换个不相干的字母不应生效
    other = next((L for L in sorted(tbl)
                  if L not in (gui._gap_dir_letters(gf) or ())), None)
    if other is not None:
        g.opt(gf, line, blk)
        gui.selected_gap = (gf, line)
        gui.selected_block = blk
        before = [tuple(b.location) for b in g.blocks]
        step0 = gui.step_count
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {
            'key': getattr(pygame, 'K_' + other.lower()), 'mod': 0, 'unicode': other}))
        gui.handle_events()
        check([tuple(b.location) for b in g.blocks] == before
              and gui.step_count == step0,
              f'字母 {other!r} 不平行于缝隙 {gf}，不应生效')


def t_virtual_keyboard_opens_for_generic():
    """F1 虚拟键盘在模型板型下应正常开/关（2026-10-25 修）。

    修之前 _generic_controls_locked() 把虚拟键盘一并拦了，于是自定义谜题里
    F1 这个快捷键失效（面板其实渲染得动，按派生字母表走，与新增的键盘移动
    同源）。现在通用通道的虚拟键盘照常切换。
    """
    gui = make(5160)
    check(getattr(gui, 'show_virtual_keyboard', False) is False, '初始虚拟键盘关')

    kb = gui.keybindings['virtual_keyboard']
    k = kb['key']
    # 与 events._is_action_triggered 同款映射（'f1' → K_F1 等）
    _keymap = {
        'space': pygame.K_SPACE, 'up': pygame.K_UP, 'down': pygame.K_DOWN,
        'left': pygame.K_LEFT, 'right': pygame.K_RIGHT,
        'return': pygame.K_RETURN, 'escape': pygame.K_ESCAPE,
        'tab': pygame.K_TAB, 'backspace': pygame.K_BACKSPACE,
        'delete': pygame.K_DELETE, 'home': pygame.K_HOME, 'end': pygame.K_END,
        'pageup': pygame.K_PAGEUP, 'pagedown': pygame.K_PAGEDOWN,
        'insert': pygame.K_INSERT,
        'f1': pygame.K_F1, 'f2': pygame.K_F2, 'f3': pygame.K_F3, 'f4': pygame.K_F4,
        'f5': pygame.K_F5, 'f6': pygame.K_F6, 'f7': pygame.K_F7, 'f8': pygame.K_F8,
        'f9': pygame.K_F9, 'f10': pygame.K_F10, 'f11': pygame.K_F11, 'f12': pygame.K_F12,
    }
    key = getattr(pygame, 'K_' + k) if len(k) == 1 else _keymap.get(k)
    check(key is not None, f'虚拟键盘快捷键 {k!r} 可映射到 pygame 键')

    # F1 打开
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN,
        {'key': key, 'mod': 0, 'unicode': k}))
    gui.handle_events()
    check(getattr(gui, 'show_virtual_keyboard', False) is True, 'F1 打开虚拟键盘')

    # 面板按派生字母表渲染，不崩（选定缝隙 + 块后 draw_board 触发）
    fam, line, blk = pick_gap(gui)
    if fam is not None:
        gui.selected_gap = (fam, line)
        gui.selected_block = blk
        gui.game.opt(fam, line, blk)
        try:
            gui.draw_board()
            check(True, '虚拟键盘（派生字母表）渲染不崩溃')
        except Exception as e:  # noqa: BLE001
            check(False, f'虚拟键盘渲染异常：{e}')
    else:
        check(True, '无可拾取缝，跳过渲染（不影响开关）')

    # F1 再关
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN,
        {'key': key, 'mod': 0, 'unicode': k}))
    gui.handle_events()
    check(getattr(gui, 'show_virtual_keyboard', False) is False, 'F1 再次关闭虚拟键盘')


if __name__ == '__main__':
    main()
