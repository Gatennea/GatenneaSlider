# -*- coding: utf-8 -*-
"""打乱动画不再自动调整动画速度（待办 §三十四 第 1 条，脚本型）。

诉求：打亂動畫（演示 + 無限打亂）播放「前後」都不應自動改變玩家的動畫速度。
舊實現在進入時存原值、播放每步把 animation_duration 壓低（演示 min 150ms /
無限打亂 min 200ms，動畫關閉時退化 60ms）、退出時還原——這套「自動調整」
正是待辦要去掉的。

盯的是：animation_duration 在被打亂動畫碰過一遍後，仍等於玩家進入前設的值，
且每一格 start_animation 調用當下的步長就是玩家設定值（沒被夾低）。

反向自檢：用 monkeypatch 把「舊壓低邏輯」裝回 _play_next_shuffle_record /
_infinite_shuffle_step，斷言同樣的檢查會轉紅——證明本護欄非恆真。

執行：``D:/python/python.exe -u test/_test_shuffle_demo_speed.py``
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

FAILS = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        FAILS.append(name)
    return bool(cond)


def positions(game):
    return [tuple(b.location) for b in game.blocks]


def make_gui(m=4, n=4, step=2):
    gui = SliderGUI(m=m, n=n, step=step)
    gui.save_readonly_flag = False
    return gui


def with_truncated_records(gui, keep, fn):
    """把 gui.game 所屬類的 shuffle 包裝成「記錄截斷」版（見 _test_shuffle_demo）。"""
    cls = type(gui.game)
    orig = cls.shuffle

    def wrapped(self, attempts, step, bias=0.0, min_score=0.75, record=None):
        orig(self, attempts, step, bias=bias, min_score=min_score, record=record)
        if record is not None and len(record) > keep:
            del record[keep:]

    cls.shuffle = wrapped
    try:
        fn()
    finally:
        cls.shuffle = orig


def ff_anim(gui):
    """把當前滑動動畫快進到結尾（下一幀 update_animation 即提交）。"""
    gui.anim_start_time = pygame.time.get_ticks() - gui.animation_duration - 5


def run_demo_until_done(gui, max_frames=3000):
    frames = 0
    while getattr(gui, '_shuffle_demo_active', False) and frames < max_frames:
        if gui.animating:
            ff_anim(gui)
        if getattr(gui, '_shuffle_demo_phase', None) in ('fade_out', 'fade_in'):
            gui._shuffle_fade_last_ms -= 20
        gui.update_animation()
        gui._update_shuffle_demo()
        frames += 1
    return frames


def spy_start_capture(gui, captured):
    """包裝 start_animation：記錄每次調用當下的 animation_duration。"""
    orig = gui.start_animation

    def spy(selected, target):
        captured.append(gui.animation_duration)
        return orig(selected, target)

    gui.start_animation = spy
    return orig


# ============================================================ 主測試：打亂演示
print('=' * 60)
print('打乱演示：进入前/播放期/退出后 animation_duration 保持玩家设置')
print('=' * 60)

gui = make_gui()
gui.animation_duration = 500          # 玩家设置的动画速度
gui.SHUFFLE_FADE_MS = 2
gui.SHUFFLE_DEMO_STEPS = 2
captured = []
spy_start_capture(gui, captured)

import random
random.seed(20261111)
with_truncated_records(gui, 3, gui.shuffle_puzzle)   # 3 > 2 → 截断 + 淡出

check('演示进入后 animation_duration 未变（无保存改写）',
      gui.animation_duration == 500, f'got={gui.animation_duration}')
check('演示第一格 start 时步长=玩家设置（未被夹低）',
      captured and captured[0] == 500, f'captured={captured[:3]}')

frames = run_demo_until_done(gui)
check('演示能自行收尾', not gui._shuffle_demo_active, f'{frames} 帧')
check('演示播放期间每格 start 步长均=500（未被夹低）',
      all(c == 500 for c in captured), f'captured={captured}')
check('演示退出后 animation_duration 未变（无还原改写）',
      gui.animation_duration == 500, f'got={gui.animation_duration}')


# ============================================================ 主測試：無限打亂
print()
print('=' * 60)
print('无限打乱：进入前/游走期/退出后 animation_duration 保持玩家设置')
print('=' * 60)

gui2 = make_gui()
gui2.animation_duration = 500
gui2.infinite_shuffle = True          # 开关打开才会真正游走
captured2 = []
spy_start_capture(gui2, captured2)

gui2._start_infinite_shuffle()
check('无限打乱进入后 animation_duration 未变',
      gui2.animation_duration == 500, f'got={gui2.animation_duration}')
check('无限打乱第一格 start 时步长=玩家设置',
      captured2 and captured2[0] == 500, f'captured={captured2[:3]}')

# 驱动若干格：每格 ff+update 提交后由 commit_animation 续下一格
for i in range(8):
    ff_anim(gui2)
    gui2.update_animation()
    if not getattr(gui2, '_infinite_shuffle_active', False):
        break
    check(f'无限打乱第 {i+1} 格后 animation_duration 仍=500',
          gui2.animation_duration == 500, f'got={gui2.animation_duration}')
    check(f'无限打乱第 {i+1} 格 start 步长=500',
          captured2[-1] == 500, f'last={captured2[-1]}')

gui2._stop_infinite_shuffle()
check('无限打乱退出后 animation_duration 未变',
      gui2.animation_duration == 500, f'got={gui2.animation_duration}')


# ============================================================ 反向自檢：舊壓低路徑會轉紅
print()
print('=' * 60)
print('反向自检：若恢复旧「压低」逻辑，护栏必须转红（非恒真）')
print('=' * 60)


gui_r = make_gui()
gui_r.animation_duration = 500
gui_r.SHUFFLE_FADE_MS = 2
gui_r.SHUFFLE_DEMO_STEPS = 2
captured_r = []
spy_start_capture(gui_r, captured_r)

# 实例级 monkeypatch：模拟「旧演示压低」——每步把 animation_duration 夹到 150ms
_orig_play = gui_r._play_next_shuffle_record
def _patched_play(self):
    self.animation_duration = min(self.animation_duration, 150)
    return _orig_play()
gui_r._play_next_shuffle_record = types.MethodType(_patched_play, gui_r)

random.seed(99)
with_truncated_records(gui_r, 3, gui_r.shuffle_puzzle)
check('反向：旧压低逻辑存在时，第一格 start 步长≠500（护栏能检出）',
      bool(captured_r) and captured_r[0] != 500, f'captured={captured_r[:3]}')

print('\nFAILS=%d %r' % (len(FAILS), FAILS))
sys.exit(1 if FAILS else 0)
