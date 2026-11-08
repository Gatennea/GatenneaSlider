# -*- coding: utf-8 -*-
"""音频设置页护栏：跨页签误触 + 「全部静音」。

2026-11-09 实测事故：音频页画过一次之后，切到 control 页点 (534,445)
会把音效音量从 70 **静默**改成 2，并置上 _settings_sfx_vol_dragging。
根因：音量滑条的 track/knob rect 是实例属性（画过一次就常驻），而按下 /
拖动两处判定漏了 `settings_active_tab == 'audio'` 闸门；同一个对话框里
其它所有控件（含动画时长、缩放滑条）都带闸门，只有这一处没有。

同轮补齐：`sound_muted` 此前只能改 config.json / HTTP，设置页没有鼠标入口
（违反「只用鼠标也要能完成一切」）；且静音只挡新播放，正在响的一声音效
会拖到播完。现在音频页有第三个总开关，静音会立刻停掉一次性音效声道。

⚠️ 反向验证（每次改这块都要做）：临时把 `gui/events.py` 两处
`if self.settings_active_tab == 'audio':` 闸门去掉、把下一层缩进还原，
本脚本 A3/A4/A5/A8/C1 必须转红；恢复源码后逐字节核对并重跑全绿。

执行：``D:/python/python.exe -u test/_test_audio_settings_scope.py``
"""
import os
import sys
import queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


gui = SliderGUI(m=4, n=4, step=2, cmd_queue=queue.Queue())
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.sfx_volume = 70
gui.music_volume = 50
gui.sound_muted = False
gui._sync_audio_settings()


def open_settings(tab):
    gui.show_settings_dialog = True
    gui.settings_active_tab = tab
    gui.settings_editing_action = None
    gui.settings_editing_value = None
    gui._settings_backup_keybindings = dict(gui.keybindings)
    gui.draw_settings_dialog()


def click_at(pos):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    gui.handle_events()


def motion_at(pos):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION, pos=pos, buttons=(1, 0, 0)))
    gui.handle_events()


# ================================================================ A 跨页签
print("\n--- A 音量滑条只在音频页生效 ---")
open_settings('audio')
gui.draw_settings_dialog()
gui.settings_scrollbar.set_scroll(10 ** 6)
gui.draw_settings_dialog()
sfx_track = pygame.Rect(gui._settings_sfx_vol_track_rect)
music_track = pygame.Rect(gui._settings_music_vol_track_rect)
check('A1 音频页画出两条音量滑条 rect',
      sfx_track.width > 0 and music_track.width > 0,
      f'{sfx_track} / {music_track}')

sfx_pos = (sfx_track.x + 3, sfx_track.centery)
music_pos = (music_track.x + 3, music_track.centery)

for tab in ('control', 'animation', 'solver'):
    gui.sfx_volume = 70
    gui.music_volume = 50
    gui._settings_sfx_vol_dragging = False
    gui._settings_music_vol_dragging = False
    gui._sync_audio_settings()
    open_settings(tab)
    check(f'A2 切到 {tab} 页后旧 rect 仍在（事故前提成立）',
          gui._settings_sfx_vol_track_rect == sfx_track,
          str(gui._settings_sfx_vol_track_rect))
    before = (gui.sfx_volume, gui.music_volume)
    click_at(sfx_pos)
    click_at(music_pos)
    check(f'A3 在 {tab} 页点旧滑条坐标不改音量',
          (gui.sfx_volume, gui.music_volume) == before,
          f'{before} -> {(gui.sfx_volume, gui.music_volume)}')
    check(f'A4 在 {tab} 页点旧滑条坐标不置拖拽旗标',
          not getattr(gui, '_settings_sfx_vol_dragging', False)
          and not getattr(gui, '_settings_music_vol_dragging', False))

# 就算旗标被别处置上，切页后拖动鼠标也不能接着改音量
gui.sfx_volume = 70
gui._sync_audio_settings()
open_settings('control')
gui._settings_sfx_vol_dragging = True
motion_at((sfx_track.right - 2, sfx_track.centery))
check('A5 非音频页的 MOUSEMOTION 不改音量',
      gui.sfx_volume == 70, str(gui.sfx_volume))
gui._settings_sfx_vol_dragging = False

# 闸门不能误伤本页正常使用
open_settings('audio')
gui.draw_settings_dialog()
gui.settings_scrollbar.set_scroll(10 ** 6)
gui.draw_settings_dialog()
_live = pygame.Rect(gui._settings_sfx_vol_track_rect)
click_at((_live.right - 1, _live.centery))
check('A6 回到音频页仍能拖满音量（闸门没误伤）',
      gui.sfx_volume >= 99 and abs(gui.audio.sfx_volume - gui.sfx_volume / 100.0) < 1e-6,
      f'gui={gui.sfx_volume} audio={gui.audio.sfx_volume}')
gui.sfx_volume = 70
gui._settings_sfx_vol_dragging = False
gui._sync_audio_settings()

# ================================================================ B 全部静音
print("\n--- B 全部静音：鼠标可达 + 立刻安静 + 状态不串 ---")
open_settings('audio')
gui.settings_scrollbar.set_scroll(0)
gui.draw_settings_dialog()
check('B1 音频页有「全部静音」开关 rect',
      hasattr(gui, '_settings_mute_toggle_rect')
      and gui._settings_mute_toggle_rect.width > 0,
      str(getattr(gui, '_settings_mute_toggle_rect', None)))

_snapshot = (gui.sfx_enabled, gui.music_enabled,
             tuple(gui.audio.slot_enabled.get(k) for k in ('slide', 'fail', 'solved',
                                                           'click', 'keyboard')))
_mute_before = gui.sound_muted
click_at(gui._settings_mute_toggle_rect.center)
check('B2 点「全部静音」→ sound_muted 翻转且推送到 AudioManager',
      gui.sound_muted != _mute_before and gui.audio.muted == gui.sound_muted,
      f'gui={gui.sound_muted} audio={gui.audio.muted}')
check('B3 有明确的操作反馈（不是静默生效）',
      '全部静音' in (gui.macro_notify_msg or ''), repr(gui.macro_notify_msg))
check('B4 静音时所有一次性音效都不再触发',
      not gui.audio._can_play_sfx())
check('B4b 「试听」仍不受静音影响（故意能听，用来决定开不开）',
      'if not self.available:' in open(os.path.join('gui', 'audio.py'),
                                       encoding='utf-8').read())
check('B5 静音不改音效/音乐总开关与五项逐项开关',
      (gui.sfx_enabled, gui.music_enabled,
       tuple(gui.audio.slot_enabled.get(k) for k in ('slide', 'fail', 'solved',
                                                     'click', 'keyboard'))) == _snapshot)

# 立刻安静：set_muted(True) 要真的调用 mixer.stop() 停掉正在响的声道
_stop_calls = []
_orig_stop = pygame.mixer.stop
pygame.mixer.stop = lambda: _stop_calls.append(1)
try:
    gui.audio.set_muted(False)
    gui.audio.set_muted(True)
finally:
    pygame.mixer.stop = _orig_stop
check('B6 静音时停掉正在播的一次性音效（mixer.stop 被调用一次）',
      not gui.audio.available or _stop_calls == [1],
      f'calls={_stop_calls} available={gui.audio.available}')

click_at(gui._settings_mute_toggle_rect.center)   # 再点一次 = 关掉静音
check('B7 再点恢复：静音关闭、音效恢复可用、各开关仍是原值',
      not gui.sound_muted and not gui.audio.muted
      and gui.audio._can_play_sfx()
      and (gui.sfx_enabled, gui.music_enabled,
           tuple(gui.audio.slot_enabled.get(k) for k in ('slide', 'fail', 'solved',
                                                         'click', 'keyboard'))) == _snapshot,
      f'muted={gui.sound_muted} can_play={bool(gui.audio._can_play_sfx())}')

# ================================================================ C 静态接线
print("\n--- C 静态接线（防删闸门 / 防漏三处同步）---")
_ev = open(os.path.join('gui', 'events.py'), encoding='utf-8').read()
_rd = open(os.path.join('gui', 'renderer.py'), encoding='utf-8').read()
check('C1 按下与拖动两处音量判定都带音频页闸门',
      "if self.settings_active_tab == 'audio':\n                for _key in ('sfx', 'music'):" in _ev
      and "if self.settings_active_tab == 'audio':\n                if getattr(self, '_settings_sfx_vol_dragging', False):" in _ev)
check('C2 renderer 给静音开关记录 rect',
      'self._settings_mute_toggle_rect = _rect_mute' in _rd)
check('C3 点击静音开关走 _sync_audio_settings（不是只改属性）',
      "self.sound_muted = not getattr(self, 'sound_muted', False)" in _ev
      and '_settings_mute_toggle_rect' in _ev)
_http = open(os.path.join('http_server.py'), encoding='utf-8').read()
_fo = open(os.path.join('gui', 'file_ops.py'), encoding='utf-8').read()
check('C4 sound_muted 三处同步（设置白名单 / HTTP / config 存读）',
      "'sound_muted'" in _ev and "'sound_muted'" in _http
      and "'sound_muted'" in _fo)
from gui import feature_index as fi  # noqa: E402
check('C5 功能索引有「全部静音」且一键跳音频页',
      any(f['id'] == 'sound_muted' for f in fi.FEATURES)
      and fi._ACTIONS.get('sound_muted', {}).get('tab') == 'audio')
check('C6 「静音」这个口语检索词指向全部静音，不是音效总开关',
      any(f['id'] == 'sound_muted' for f in fi.FEATURES
          if '静音' in f['aliases'])
      and all('静音' not in f['aliases'] for f in fi.FEATURES
              if f['id'] == 'sfx_enabled'))

# 收尾：别把运行态留给后面的脚本
gui.sound_muted = False
gui.sfx_volume = 70
gui.music_volume = 50
gui._sync_audio_settings()

print(f"\n=== 结果：{'PASS' if not _failures else 'FAIL ' + str(_failures)} ===")
sys.exit(1 if _failures else 0)
