# -*- coding: utf-8 -*-
"""回归：对话框输入框可正常打字 + 自定义框回车导航。

历史 bug（2026-11-11）：
- 保存文件对话框的 PygameFileDialog.handle_event 没有转发 TEXTINPUT 事件。
  保存框打开时 events._sync_ime_text_input 会把 TextInput._text_input_mode
  置 True，打字只经 TEXTINPUT 投递，而对话框没转发给 TextInput，于是出现
  「能删字不能打字」（删除走 KEYDOWN，不受模式影响）。
- 自定义谜题对话框的回车原本总是直接确定；需求改为「非末字段→进下一字段，
  末字段→视为确定」。

反向验证：临时撤掉 PygameFileDialog 的 TEXTINPUT 分支（修复点），本测试的
TEXTINPUT 打字断言必然 FAIL——护栏能转红。

运行方式：conftest 子进程脚本（需 __main__ 守卫），或：
  SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python test/_test_dialog_input.py
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
from gui.dialogs import PygameFileDialog  # noqa: E402
from gui.text_input import TextInput  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print('  ok: ' + msg)
    else:
        _fail.append(msg)
        print('  FAIL: ' + msg + ' ' + extra)
    return cond


def make_fake_event(etype, **kw):
    return pygame.event.Event(etype, **kw)


# ----------------------------------------------------------------------
# A. 保存文件对话框：TEXTINPUT 必须被转发（_text_input_mode = True 时）
# ----------------------------------------------------------------------
def run_file_dialog():
    print('\n== 保存框打字（TEXTINPUT 转发）==')
    screen = pygame.Surface((800, 600))
    dlg = PygameFileDialog(screen, None, None, None, {})
    dlg.show(mode='save', title='保存', initial_file='')
    dlg.active = True
    # 模拟真实状态：保存框打开时 _sync_ime_text_input 会把模式置 True
    TextInput._text_input_mode = True

    # KEYDOWN 的可打印字符在模式为 True 时不应插入（这是设计，避免与 TEXTINPUT 重复）
    dlg.handle_event(make_fake_event(pygame.KEYDOWN, key=pygame.K_a,
                                    unicode='a', mod=0))
    check(dlg.text_input.text == '',
          '模式=True 时 KEYDOWN 不插入（避免重复）',
          'text=%r' % dlg.text_input.text)

    # TEXTINPUT 必须被转发并插入
    dlg.handle_event(make_fake_event(pygame.TEXTINPUT, text='a'))
    check(dlg.text_input.text == 'a',
          'TEXTINPUT 被转发并插入字符',
          'text=%r' % dlg.text_input.text)

    # 连续输入
    dlg.handle_event(make_fake_event(pygame.TEXTINPUT, text='bc'))
    check(dlg.text_input.text == 'abc',
          'TEXTINPUT 连续组字插入',
          'text=%r' % dlg.text_input.text)

    # 删除键走 KEYDOWN，仍可用
    dlg.handle_event(make_fake_event(pygame.KEYDOWN, key=pygame.K_BACKSPACE,
                                    unicode='', mod=0))
    check(dlg.text_input.text == 'ab',
          '删除（BACKSPACE 走 KEYDOWN）仍可用',
          'text=%r' % dlg.text_input.text)

    # 还原模式，避免影响其它用例
    TextInput._text_input_mode = False


# ----------------------------------------------------------------------
# B. 自定义谜题对话框：回车导航
# ----------------------------------------------------------------------
def setup_custom(gui, kind):
    gui.show_custom_dialog = True
    gui.custom_kind = kind
    if kind == 'triangle':
        gui.custom_fields = {'m': '', 'step': ''}
    else:
        gui.custom_fields = {'m': '', 'n': '', 'step': ''}
    gui.custom_active_field = 'm'
    gui.custom_error = ''
    gui.custom_ok_btn = pygame.Rect(0, 0, 10, 10)
    gui.custom_cancel_btn = pygame.Rect(200, 200, 10, 10)
    gui.custom_field_rects = {}
    return gui


def press_enter(gui):
    return gui.handle_custom_dialog_events(
        make_fake_event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode='\r', mod=0))


def run_custom_nav():
    print('\n== 自定义框回车导航（矩形）==')
    gui = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 7182})
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()

    setup_custom(gui, 'rect')  # 字段顺序 m -> n -> step
    check(gui.custom_active_field == 'm', '初始焦点在 m')

    press_enter(gui)
    check(gui.custom_active_field == 'n',
          '回车从 m 进入下一字段 n', 'field=%r' % gui.custom_active_field)
    check(gui.show_custom_dialog, '非末字段回车不触发确定（对话框仍开）')

    press_enter(gui)
    check(gui.custom_active_field == 'step',
          '回车从 n 进入末字段 step', 'field=%r' % gui.custom_active_field)

    # 末字段填入合法值后，回车视为确定
    gui.custom_fields = {'m': '6', 'n': '6', 'step': '2'}
    press_enter(gui)
    check(not gui.show_custom_dialog,
          '末字段回车视为确定（对话框关闭）',
          'show_custom_dialog=%r' % gui.show_custom_dialog)

    # 三角形态：字段 m -> step（无 n），末字段回车确定
    print('\n== 自定义框回车导航（三角形）==')
    setup_custom(gui, 'triangle')  # m -> step
    press_enter(gui)
    check(gui.custom_active_field == 'step',
          '三角形：回车从 m 进入 step', 'field=%r' % gui.custom_active_field)
    gui.custom_fields = {'m': '5', 'step': '2'}
    press_enter(gui)
    check(not gui.show_custom_dialog,
          '三角形：末字段（step）回车确定',
          'show_custom_dialog=%r' % gui.show_custom_dialog)


# ----------------------------------------------------------------------
# C. §五十七：一次按键只插一次（KEYDOWN + TEXTINPUT 双投）+ 注册表随开关增减
# ----------------------------------------------------------------------
def run_double_insert():
    print('\n== 双插回归（§五十七 注册表）==')
    gui = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 7183})
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()

    # 启动即同步：无上下文时必须把 SDL 默认开着的文本输入关掉（否则退回双插）
    gui._sync_ime_text_input()
    check(TextInput._text_input_mode is False,
          '启动无上下文：_text_input_mode=False')

    # 打开自定义谜题框 → 登记进注册表
    setup_custom(gui, 'rect')
    gui._sync_ime_text_input()
    active, _ = gui._ime_contexts_active()
    check('custom' in active, '自定义框打开即登记进注册表', active)
    check(TextInput._text_input_mode is True,
          '自定义框打开：_text_input_mode=True（KEYDOWN 插入路关闭）')

    # 一次按键 = SDL 同时投 KEYDOWN.unicode + TEXTINPUT 各一次
    gui.handle_custom_dialog_events(
        make_fake_event(pygame.KEYDOWN, key=pygame.K_5, unicode='5', mod=0))
    gui.handle_custom_dialog_events(make_fake_event(pygame.TEXTINPUT, text='5'))
    check(gui.custom_fields['m'] == '5',
          '同一按键双投只插入一次（ASCII）', repr(gui.custom_fields))

    # 中文输入法组字：KEYDOWN(全角) + TEXTINPUT 各一投，仍只一次
    gui.handle_custom_dialog_events(
        make_fake_event(pygame.KEYDOWN, key=pygame.K_5, unicode='５', mod=0))
    gui.handle_custom_dialog_events(make_fake_event(pygame.TEXTINPUT, text='５'))
    check(gui.custom_fields['m'] == '5５',
          '同一按键双投只插入一次（中文/全角）', repr(gui.custom_fields))

    # 关闭 → 注销出注册表，模式退回 KEYDOWN 路
    gui.show_custom_dialog = False
    gui._sync_ime_text_input()
    active, _ = gui._ime_contexts_active()
    check('custom' not in active, '自定义框关闭即注销出注册表', active)
    check(TextInput._text_input_mode is False,
          '自定义框关闭：_text_input_mode=False')

    # 三维创造命名框（_ann_design_name_active）同样登记
    gui._ann_design_name_active = True
    gui._sync_ime_text_input()
    active, _ = gui._ime_contexts_active()
    check('design_name' in active, '样式名框激活即登记进注册表', active)
    check(TextInput._text_input_mode is True,
          '样式名框激活：_text_input_mode=True')
    gui._ann_design_name_active = False
    gui._sync_ime_text_input()
    active, _ = gui._ime_contexts_active()
    check('design_name' not in active, '样式名框失焦即注销出注册表', active)

    # 原有四个框不回归：帮助检索框
    gui.show_help = True
    gui._sync_ime_text_input()
    active, _ = gui._ime_contexts_active()
    check('help' in active and TextInput._text_input_mode is True,
          '帮助框照旧登记（原白名单四项不回归）', active)
    gui.show_help = False
    gui._sync_ime_text_input()
    check(TextInput._text_input_mode is False, '帮助框关闭后模式退回')


if __name__ == '__main__':
    pygame.init()
    try:
        run_file_dialog()
        run_custom_nav()
        run_double_insert()
    finally:
        pygame.quit()
    print('\n通过 %d 项，失败 %d 项' % (_ok[0], len(_fail)))
    if _fail:
        for m in _fail:
            print('  ✗', m)
        print('FAILED')
        sys.exit(1)
    print('ALL PASS')
