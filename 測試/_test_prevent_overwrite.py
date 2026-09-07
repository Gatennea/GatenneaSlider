# -*- coding: utf-8 -*-
r"""
防止存档覆盖（2b）headless 冒烟测试（dummy video，不开窗口）

验证点：
    1. 开关默认关：已有路径时 Ctrl+S(save_to_file) 直接写原文件
    2. 开关开：已有路径时 save_to_file 进入另存为（save_as），原文件不被改写
    3. 开关开且无路径：仍进入另存为
    4. 配置持久化：save_config 写回开关值，load_last_state 还原
    5. 设置 file Tab 点开关 → prevent_overwrite_flag 翻转

运行：
    D:\python\python.exe 測試\_test_prevent_overwrite.py
"""

import json
import os
import sys
import tempfile
import time

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

import pygame

ok_all = True


def _check(name, cond, detail=''):
    global ok_all
    ok_all = ok_all and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def main():
    from GUI import SliderGUI
    gui = SliderGUI(m=5, n=5, step=2)
    gui.animation_enabled = False
    gui._readonly = False          # 屏蔽 temp_history 可能残留的只读标记
    gui.save_readonly_flag = False

    tmpdir = tempfile.mkdtemp(prefix='slider_overwrite_')
    save_path = os.path.join(tmpdir, 't.json')

    # ---- 0. 先建立存档路径 ----
    gui._save_to_path(save_path)
    _check('建立存档路径', gui.current_file_path == save_path, gui.current_file_path)

    # ---- 1. 开关关：直存原文件 ----
    calls = []
    gui.save_as = lambda: calls.append('save_as')
    gui.prevent_overwrite_flag = False
    gui._mark_file_dirty()
    gui.save_to_file()
    _check('开关关时直存(不进另存为)', len(calls) == 0, f'calls={calls}')
    _check('直存后星号消失', '*' not in gui._window_title, gui._window_title)

    # ---- 2. 开关开：进入另存为且原文件不被改写 ----
    gui.prevent_overwrite_flag = True
    gui._mark_file_dirty()
    mtime_before = os.path.getmtime(save_path)
    time.sleep(0.02)
    gui.save_to_file()
    _check('开关开时进入另存为', len(calls) == 1, f'calls={calls}')
    _check('原文件未被改写', os.path.getmtime(save_path) == mtime_before, '')
    _check('仍未保存(保持星号)', '*' in gui._window_title, gui._window_title)

    # ---- 3. 开关开且无路径：仍进入另存为 ----
    gui.current_file_path = None
    gui.save_to_file()
    _check('开关开且无路径仍另存为', len(calls) == 2, f'calls={calls}')

    # ---- 4. 配置持久化（重定向到临时 config 路径，不污染工作区） ----
    gui.config_dir = os.path.join(tmpdir, 'config')
    gui.config_path = os.path.join(gui.config_dir, 'config.json')
    gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
    gui.prevent_overwrite_flag = True
    gui.save_config()
    with open(gui.config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    _check('save_config 写回开关', cfg.get('prevent_overwrite_flag') is True,
           f"cfg={cfg.get('prevent_overwrite_flag')}")

    gui.prevent_overwrite_flag = False
    gui.load_last_state()
    _check('load_last_state 还原开关', gui.prevent_overwrite_flag is True,
           f'flag={gui.prevent_overwrite_flag}')

    # ---- 5. 设置 file Tab 点“防止覆盖”开关（走真实事件处理器） ----
    gui.prevent_overwrite_flag = False
    gui.settings_active_tab = 'file'
    # 把可能为 None 的 tab 矩形换成本体不可触碰的矩形，避免 hasattr 命中 None
    for attr in ('_settings_tab_kb_rect', '_settings_tab_anim_rect',
                 '_settings_tab_solver_rect', '_settings_tab_gather_rect',
                 '_settings_tab_file_rect', '_settings_readonly_toggle_rect'):
        setattr(gui, attr, pygame.Rect(0, 0, 1, 1))
    gui._settings_prevent_overwrite_rect = pygame.Rect(100, 100, 60, 28)
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button': 1, 'pos': (120, 110)})
    gui._handle_settings_dialog_event(ev)
    _check('点开关翻转为开', gui.prevent_overwrite_flag is True,
           f'flag={gui.prevent_overwrite_flag}')
    _check('点开关有通知', '防止覆盖' in getattr(gui, 'macro_notify_msg', ''),
           getattr(gui, 'macro_notify_msg', ''))

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    print('\n' + ('ALL PASS' if ok_all else 'SOME FAILED'))
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()