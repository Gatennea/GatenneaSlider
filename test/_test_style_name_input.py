# -*- coding: utf-8 -*-
r"""§58 A 组护栏：样式名 / 模型名两框的中文输入（2026-11-21）。

判据全部走真实事件入口（handle_annotation_event / _med_handle_event）与
运行时注册表行为，不用「源码里有没有 TEXTINPUT 分支」这类静态假绿。

运行：D:\python\python.exe test\_test_style_name_input.py
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from gui.events import _IME_TEXT_INPUT_CONTEXTS  # noqa: E402

FAILED = []
PASSED = [0]


def check(ok, label, extra=None):
    if ok:
        PASSED[0] += 1
        print(f'  ok: {label}')
    else:
        FAILED.append(label)
        print(f'  FAIL: {label}' + (f'  <- {extra}' if extra is not None else ''))


def _ti(text):
    return pygame.event.Event(pygame.TEXTINPUT, {'text': text})


def _kd(key, unicode=''):
    return pygame.event.Event(pygame.KEYDOWN, {
        'key': key, 'unicode': unicode, 'mod': 0, 'scancode': 0})


def _new_gui(create=False):
    g = SliderGUI()
    g.config_dir = tempfile.mkdtemp(prefix='style_input_')
    if create:
        g.set_game_mode('create')
    return g


def t1_design_style_name():
    print('== 1. 设计样式名框：中文 + ASCII + 不双插 ==')
    g = _new_gui(create=True)
    g._ann_sub_dialog = 'design'
    g._ann_view = 'design'
    g._ann_design_name_active = True
    g._ann_design_style_name = ''
    check(g.handle_annotation_event(_ti('捆绑样式')), 'TEXTINPUT 被设计画布消费')
    check(g._ann_design_style_name == '捆绑样式', '中文整串进样式名框',
          g._ann_design_style_name)
    g.handle_annotation_event(_ti('ABC'))
    check(g._ann_design_style_name == '捆绑样式ABC', '同框续接 ASCII',
          g._ann_design_style_name)
    g.handle_annotation_event(_kd(pygame.K_a, 'a'))
    check(g._ann_design_style_name == '捆绑样式ABC', 'KEYDOWN.unicode 不再插字（防双插）',
          g._ann_design_style_name)
    g.handle_annotation_event(_kd(pygame.K_BACKSPACE))
    check(g._ann_design_style_name == '捆绑样式AB', '退格仍由 KEYDOWN 处理',
          g._ann_design_style_name)
    g._ann_design_name_active = False
    check(not g.handle_annotation_event(_ti('x')), '未聚焦时 TEXTINPUT 放行不吞')


def t2_model_name():
    print('== 2. 模型名框：中文 + ASCII + 不双插 + 保存门 ==')
    g = _new_gui()
    g._med_open()
    check(g.med_active, '搭积木编辑会话已打开', g.macro_notify_msg)
    med = g._med
    med['name_active'] = True
    med['name'] = ''
    med['name_rect'] = pygame.Rect(10, 50, 120, 24)
    check(g._med_handle_event(_ti('我的模型')), 'TEXTINPUT 被模型编辑器消费')
    check(med['name'] == '我的模型', '中文整串进模型名框', med['name'])
    g._med_handle_event(_ti('2'))
    check(med['name'] == '我的模型2', '同框续接 ASCII', med['name'])
    g._med_handle_event(_kd(pygame.K_a, 'a'))
    check(med['name'] == '我的模型2', 'KEYDOWN.unicode 不再插字（防双插）',
          med['name'])
    g._med_handle_event(_kd(pygame.K_BACKSPACE))
    check(med['name'] == '我的模型', '退格仍由 KEYDOWN 处理', med['name'])
    # 真入口走到保存门：空盘会被 gate 拒，但中文名必须先过名字过滤这关。
    g._med_save()
    msg = g.macro_notify_msg or ''
    check('名字只能含' not in msg, '中文名通过保存侧名字过滤', msg)
    check('保存被拒' in msg, '流程确实到达保存门（非名字过滤提前返回）', msg)
    g._med_close()


def t3_ime_registry():
    print('== 3. IME 注册表：两框登记 + 锚点 ==')
    g = _new_gui()
    names = [n for n, _, _ in _IME_TEXT_INPUT_CONTEXTS]
    check('design_name' in names, 'design_name 已登记')
    check('model_name' in names, 'model_name 新登记')
    active = [n for n, is_open, _ in _IME_TEXT_INPUT_CONTEXTS if is_open(g)]
    check('model_name' not in active, '编辑器未开时 model_name 不激活')
    g._med_open()
    g._med['name_active'] = True
    g._med['name_rect'] = pygame.Rect(7, 8, 90, 24)
    active = [n for n, is_open, _ in _IME_TEXT_INPUT_CONTEXTS if is_open(g)]
    check('model_name' in active, '名字框聚焦时 model_name 激活')
    rect_of = next(rect for n, _, rect in _IME_TEXT_INPUT_CONTEXTS
                   if n == 'model_name')
    check(rect_of(g) is g._med['name_rect'], 'IME 候选框锚点指向名字框')
    g._med['name_active'] = False
    active = [n for n, is_open, _ in _IME_TEXT_INPUT_CONTEXTS if is_open(g)]
    check('model_name' not in active, '失焦即停（生命周期闭合）')
    g._med_close()


def main():
    t1_design_style_name()
    t2_model_name()
    t3_ime_registry()
    print(f'\n{PASSED[0]} passed, {len(FAILED)} failed')
    if FAILED:
        print('FAILED: ' + '; '.join(FAILED))
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
