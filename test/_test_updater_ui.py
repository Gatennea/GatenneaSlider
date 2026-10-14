# -*- coding: utf-8 -*-
"""更新器 UI 集成冒烟测试（headless，SDL dummy）。"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from GUI import SliderGUI
import pygame

gui = SliderGUI(m=6, n=6, step=2)
gui.animation_enabled = False
gui.screen = pygame.Surface((1000, 700))

# 1) 开发模式：检查更新只给提示、不启线程、不抛
gui._start_update_check()
assert gui.macro_notify_msg, 'dev 模式检查更新应有提示'
assert gui._update_check_in_progress is False
print('[PASS] dev _start_update_check 只提示不启线程')

# 2) 开发模式：自动轮询直接 no-op
gui._auto_update_poll()
print('[PASS] dev _auto_update_poll no-op')

# 3) 发现新版本 → 画左上角「更新」按钮
gui.update_available = True
gui._update_manifest = {'version': 'v999-20261014'}
gui.draw_update_banner()
assert gui._update_btn_rect is not None, '应画出更新按钮矩形'
print('[PASS] draw_update_banner 画出按钮 rect=%s' % gui._update_btn_rect)

# 4) 未更新时按钮矩形清空
gui.update_available = False
gui.draw_update_banner()
assert gui._update_btn_rect is None
print('[PASS] draw_update_banner 未更新时清空 rect')

# 5) 进度框：下载中不抛
gui._update_in_progress = True
gui.update_progress = 0.42
gui.update_status_msg = '下载中 1234KB / 3000KB'
gui.draw_update_progress()
print('[PASS] draw_update_progress 不抛')

# 6) 开发模式：立即更新只提示、不启线程、不退出
gui.update_available = False
gui._update_in_progress = False
gui._start_update_now()
assert gui._update_in_progress is False
print('[PASS] dev _start_update_now 只提示不启线程')

# 7) 已有版本 + 立即更新：启后台线程（dev 模式 is_frozen=False 会提前返回，
#    这里只验证方法存在且能走到启线程分支前的守卫）
gui.update_available = True
gui._update_manifest = {'version': 'v999-20261014'}
gui._update_in_progress = False
# 开发模式会在 guards 处返回（is_frozen False），仍是只提示
gui._start_update_now()
assert gui._update_in_progress is False
print('[PASS] _start_update_now 开发模式守卫生效')

print('SMOKE PASS')
