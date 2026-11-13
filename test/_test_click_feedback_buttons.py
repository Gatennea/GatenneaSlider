# -*- coding: utf-8 -*-
"""无头验证：点击反馈左右分形态（左键外扩环 / 右键内收环 / 右键弱脉冲）。

背景（用户 2026-11-13）：「点击反馈只对左键有效，包括 GUI 和音效两方面，
接下来给右键也加反馈」。

设计口径（本文件守的就是这几条）
================================
  1. 左键：全局事件回显，外扩蓝环 + click 声（原有形态，**不得改变**）。
  2. 右键语义是「取消选中」。真走到取消那一步 → 升级成内收暖环 + 更轻的
     click 声；被模态（设置框等）吞掉 → 只留一颗弱脉冲，**不冒充取消了东西**。
  3. 左右共用 click 槽（不新增开关），右鍵音量 0.65、独立节流时间戳。
  4. 这一层是整屏覆盖绘制，三形态共用，**不需要**按 §3 在 square/tri/mi
     各接一次（理由见 docs/ui/UI实现铁律.md §1 的豁免条）。

護欄
====
  S1~S3  静态：全局挂接点 / 升级调用 / 三形态分支都在，且只有一处 spawn 调用点
  S4     编辑器会话里的右键（自己吞事件）也接了升级
  L1/L2  左键仍是 kind='left' + click('left')
  R1~R3  右键棋盘：通知成立、升级为 'right'、出声 kind='right'
  R4     右键确实把选中清掉
  R5     设置对话框里右键：仍是 'right_weak'、不出声、提示不变
  R6     右键在菜单栏同样升级（全局口径）
  D1~D3  三种形态都能画、过期项会被清、上限不超
  A1/A2  右键音量系数生效；左右节流时间戳各自独立

执行：D:/python/python.exe -u test/_test_click_feedback_buttons.py
"""
import inspect
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

import gui.audio as A  # noqa: E402
from GUI import SliderGUI  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


# ================================================================ S：静态挂接点
_ev_src = inspect.getsource(SliderGUI.handle_events)
_draw_src = inspect.getsource(SliderGUI.draw_click_feedback)
_med_src = inspect.getsource(SliderGUI._med_mouse_down)

check('S1 右键在全局最早挂接（记弱脉冲，先于所有分支）',
      "kind='right_weak'" in _ev_src, '')
check('S2 取消选中分支里升级 + 出右键声',
      'promote_click_feedback()' in _ev_src and "_play_click_sound('right')" in _ev_src, '')
check('S3 反馈绘制含左键/右键/弱脉冲三条分支，仍是全局一层',
      ('right_weak' in _draw_src and 'RIGHT_FEEDBACK_MS' in _draw_src
       and 'CLICK_FEEDBACK_MS' in _draw_src), '')
_sites = _ev_src.count('spawn_click_feedback(')
_quit_at = _ev_src.find("event.type == pygame.QUIT")
_last_site = _ev_src.rfind('spawn_click_feedback(')
check('S3b 左/右各一处，且两处都在所有分支之前（全局一层，非每形态各接）',
      _sites == 2 and 0 < _last_site < _quit_at,
      f'sites={_sites} last={_last_site} quit={_quit_at}')
check('S4 模型编辑器自己吞右键，也接了升级（不只剩弱脉冲）',
      'promote_click_feedback' in _med_src, '')


# ================================================================ L/R：GUI 行为
def build():
    gui = SliderGUI(m=4, n=4, step=2)
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui.save_readonly_flag = False
    gui.new_puzzle(4, 4, 2)
    gui._click_feedback = []
    gui._click_calls = []
    if getattr(gui, 'audio', None) is not None:
        gui.audio.play_click = lambda kind='left': gui._click_calls.append(kind)
    return gui


def fire(gui, button, pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                        button=button, pos=pos))
    gui.handle_events()


g = build()
_center = (g.screen_width // 2, g.screen_height // 2)

# 左键：形态与声音都不该变
fire(g, 1, _center)
check('L1 左键仍是 kind=left', g._click_feedback[-1]['kind'] == 'left',
      f"kind={g._click_feedback[-1]['kind']}")
check('L2 左键 click 声没被改动', g._click_calls[-1:] == ['left'],
      f'calls={g._click_calls}')

# 右键：棋盘上确实取消 + 升级成完整反馈
g.selected_gap = ('v', 1) if hasattr(g, 'selected_gap') else None
g._click_calls.clear()
g._click_feedback = []
fire(g, 3, _center)
check('R1 右键取消选中的提示成立', g.macro_notify_msg == '已取消选中',
      f"notify={g.macro_notify_msg!r}")
check('R2 右键弱脉冲升级为完整内收环', g._click_feedback[-1]['kind'] == 'right',
      f"kind={g._click_feedback[-1]['kind']}")
check('R3 右键出声（kind=right）', g._click_calls == ['right'],
      f'calls={g._click_calls}')
check('R4 右键清掉选中（selected_gap / be_opted）',
      g.selected_gap is None and g.selected_block is None
      and not any(b.be_opted for b in g.game.blocks), '')

# 设置对话框：右键被模态吞掉 → 只剩弱脉冲，不出声、不弹提示
g._click_calls.clear()
g._click_feedback = []
g.show_settings_dialog = True
g.settings_active_tab = 'keyboard'
g.macro_notify_msg = '<未变>'
fire(g, 3, _center)
check('R5 模态里右键只剩弱脉冲（不冒充取消）',
      g._click_feedback[-1]['kind'] == 'right_weak',
      f"kind={g._click_feedback[-1]['kind']}")
check('R5b 模态里右键不出声', g._click_calls == [], f'calls={g._click_calls}')
check('R5c 模态里右键不改提示', g.macro_notify_msg == '<未变>',
      f"notify={g.macro_notify_msg!r}")
g.show_settings_dialog = False

# 菜单栏：与棋盘同口径（全局回显）
g._click_calls.clear()
g._click_feedback = []
fire(g, 3, (10, 10))
check('R6 菜单栏右键同样升级为完整反馈',
      g._click_feedback[-1]['kind'] == 'right' and g._click_calls == ['right'],
      f"kind={g._click_feedback[-1]['kind']} calls={g._click_calls}")


# ================================================================ D：绘制
def draw_ok(kind, age_ms):
    g._click_feedback = [{'x': _center[0], 'y': _center[1],
                          't0': pygame.time.get_ticks() - age_ms, 'kind': kind}]
    try:
        g.draw_click_feedback()
        return True, list(g._click_feedback)
    except Exception as e:      # 绘制不许把主循环带崩
        print(f'   [draw error] {kind} age={age_ms}: {e}')
        return False, []


for _k in ('left', 'right', 'right_weak'):
    ok, alive = draw_ok(_k, 10)
    check(f'D1 {_k} 能画且仍在存活列表', ok and len(alive) == 1, f'ok={ok}')

ok, alive = draw_ok('right', 10_000)
check('D2 过期反馈会被清出列表（不积压）', ok and alive == [], f'ok={ok} alive={len(alive)}')

g._click_feedback = []
for _i in range(20):
    g.spawn_click_feedback((_i, _i), kind='left')
check('D3 连点上限仍是 12 条', len(g._click_feedback) == g.CLICK_FEEDBACK_MAX,
      f'len={len(g._click_feedback)}')


# ================================================================ A：音效
mgr = A.AudioManager()
mgr.load_all()


class _FakeSound:
    def __init__(self):
        self.volumes = []

    def set_volume(self, v):
        self.volumes.append(v)

    def play(self):
        self.volumes.append('play')


if not mgr.available:
    print('   [skip] A1/A2：无 mixer（dummy 驱动也未起来）')
else:
    _snd = _FakeSound()
    mgr._sounds['click'] = _snd
    mgr.set_sfx_volume(70)
    mgr.set_slot_enabled('click', True)

    _snd.volumes.clear()
    mgr.play('click', volume_scale=A._CLICK_RIGHT_VOLUME)
    check('A1 右键音量 = sfx_volume × 0.65',
          abs(_snd.volumes[0] - 0.7 * A._CLICK_RIGHT_VOLUME) < 1e-6,
          f'vol={_snd.volumes[0]:.3f}')

    mgr._last_click_ms = -10 ** 9
    mgr._last_click_right_ms = -10 ** 9
    _snd.volumes.clear()
    mgr.play_click()
    mgr.play_click('right')
    _played = sum(1 for v in _snd.volumes if v == 'play')
    check('A2 左右各用独立节流时间戳，紧挨着连点两声都出',
          _played == 2 and mgr._last_click_ms > -10 ** 9
          and mgr._last_click_right_ms > -10 ** 9,
          f'played={_played}')


print()
if _failures:
    print(f'FAILED {len(_failures)}: ' + '; '.join(_failures))
    sys.exit(1)
print('ALL PASS')
