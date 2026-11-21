# -*- coding: utf-8 -*-
"""回归：滑动被拒的视觉反馈（2026-11-13 定案 · 配色 A）。

锁定六件事，防止「又只剩文字 + 声音」或配色被改回旧暗橙：

  A. 边框 helper 只认 disconnected / collision 两色，未知一律中性色（不静默归类）；
  B. 四条绘制路径（square / tri / mi / 通用 polygon 通道）各接一次 helper，
     且渲染器里旧的暗橙 (220,80,40) 与「填充 × 0.45」已彻底消失；
  C. 键盘 / 虚拟键盘 / 箭头被拒 → 12 帧闪现、带原因、只闪不位移；
  D. 时机错 / 操作前提没满足的拒绝（visual=False）不闪；
  E. 視覺與音效解耦：連按（音效被節流）仍要立刻續閃，不准有冷卻；
  F. 倒计时归零与八个退出分支的共同清理点都清掉原因，不残留到下一局；
  G. 真实离屏渲染一帧并查像素：断开是冷紫、重叠是暖珊瑚、无闪现时两色都不出现。

执行：``D:/python/python.exe -u test/_test_reject_visual.py``
"""
import os
import queue
import sys
import tempfile

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from gui.renderer import (  # noqa: E402
    REJECT_BORDER_COLLISION, REJECT_BORDER_DISCONNECTED,
    REJECT_BORDER_UNKNOWN, reject_border_style,
)

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def boot():
    gui = SliderGUI(cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui.animation_enabled = False
    gui.new_puzzle(5, 5, 1)
    gui._update_in_progress = False
    return gui


class FakeAudio:
    """只回传节流判定：第一次通过，之后一律视为连按被节流。"""

    def __init__(self):
        self.calls = 0

    def play_fail(self):
        self.calls += 1
        return self.calls == 1


# ---- A. 配色 helper ----
check('A1 断开 = 冷紫',
      reject_border_style('disconnected', 1)[0] == REJECT_BORDER_DISCONNECTED)
check('A2 重叠 = 暖珊瑚',
      reject_border_style('collision', 1)[0] == REJECT_BORDER_COLLISION)
for _r in (None, 'no_move', 'bad_direction', 'all_selected', 'timer_blocked', ''):
    check(f'A3 原因 {_r!r} 走中性色、不静默归类',
          reject_border_style(_r, 1)[0] == REJECT_BORDER_UNKNOWN)
check('A4 线宽随 zoom 加粗', reject_border_style('collision', 2)[1] == 6)

# ---- B. 四条绘制路径 + 旧样式清除 ----
_src = open('gui/renderer.py', encoding='utf-8').read()
_marks = [
    ('tri', '    def draw_triangle_board(self):'),
    ('mi', '    def draw_mi_board(self):'),
    ('polygon', '    def _draw_polygon_board(self, view):'),
    ('square', '    def draw_board(self):'),
]
_starts = [(name, _src.index(mark)) for name, mark in _marks]
_menu = _src.index('    def draw_menu_bar(self):')
for _k, (_name, _start) in enumerate(_starts):
    _end = min([p for _, p in _starts if p > _start] or [_menu])
    _seg = _src[_start:_end]
    check(f'B1 {_name} 绘制接了 helper',
          _seg.count('reject_border_style(') >= 2,
          f'calls={_seg.count("reject_border_style(")}')
check('B2 旧暗橙 (220,80,40) 已从渲染器消失', '(220, 80, 40)' not in _src)
check('B3 填充变暗 ×0.45 已从拒绝路径消失', 'ch * 0.45' not in _src)
check('B4 helper 定义在模块级（三形态共用一处）',
      _src.index('def reject_border_style(') < _starts[0][1])

# ---- C/D/E/F. 状态机 ----
gui = boot()
for _b in gui.game.blocks[:3]:
    _b.be_opted = True
gui.audio = FakeAudio()
check('C0 拒绝返回 False', gui._reject_move(reason='collision') is False)
check('C1 键盘被拒不位移（无越界方向可回弹）',
      gui._shake_dr == 0 and gui._shake_dc == 0)
check('C2 12 帧闪现', getattr(gui, '_shake_t', 0) == 12)
check('C3 原因带到底层', getattr(gui, '_reject_reason', None) == 'collision')
check('C4 被选组被点亮', len(getattr(gui, '_shake_blocks', set())) == 3,
      f'n={len(getattr(gui, "_shake_blocks", set()))}')

gui._shake_t = 3
gui._reject_reason = None
check('E 连按音效被节流，但视觉照样续闪（无冷卻）',
      gui._reject_move(reason='disconnected') is False
      and getattr(gui, '_shake_t', 0) == 12
      and getattr(gui, '_reject_reason', None) == 'disconnected',
      f't={getattr(gui, "_shake_t", 0)} reason={getattr(gui, "_reject_reason", None)}')
check('E2 音效仍只响一次（节流没被拆掉）', gui.audio.calls == 2)

gui.audio = FakeAudio()
gui._shake_t = 0
gui._reject_reason = None
gui._reject_move(visual=False)
check('D 时机错/前提没满足不闪', getattr(gui, '_shake_t', 0) == 0)

gui._reject_reason = 'disconnected'
gui._shake_t = 1
gui.update_animation()
check('F1 倒计时归零清原因', getattr(gui, '_reject_reason', None) is None)
gui._reject_reason = 'collision'
gui._shake_t = 12
gui._clear_sel_anim()
check('F2 八个退出分支的共同清理点也清掉闪现',
      getattr(gui, '_shake_t', 0) == 0
      and getattr(gui, '_reject_reason', None) is None)

# ---- G. 真实离屏渲染 + 像素色检查 ----
try:
    import numpy as np

    def has_color(rgb, tol=10):
        arr = pygame.surfarray.array3d(gui.screen).astype(int)
        return bool((np.abs(arr - np.array(rgb)).max(axis=2) <= tol).any())

    def render(reason):
        gui._shake_t = 12
        gui._shake_dr = 0
        gui._shake_dc = 0
        gui._shake_blocks = set(id(b) for b in gui.game.blocks if b.be_opted)
        gui._reject_reason = reason
        gui.draw_board()
        return gui.screen.copy()

    _tmp = tempfile.gettempdir()
    _plain = render(None)
    gui._shake_t = 0
    gui._shake_blocks = set()
    gui._reject_reason = None
    gui.draw_board()
    _plain = gui.screen.copy()
    check('G0 无闪现时不出现冷紫/珊瑚',
          not has_color(REJECT_BORDER_DISCONNECTED)
          and not has_color(REJECT_BORDER_COLLISION))
    pygame.image.save(_plain, os.path.join(_tmp, 'gatsli_reject_plain.png'))

    _disc = render('disconnected')
    check('G1 断开渲染出冷紫边框',
          has_color(REJECT_BORDER_DISCONNECTED)
          and not has_color(REJECT_BORDER_COLLISION))
    pygame.image.save(_disc, os.path.join(_tmp, 'gatsli_reject_disconnected.png'))

    _coll = render('collision')
    check('G2 重叠渲染出暖珊瑚边框',
          has_color(REJECT_BORDER_COLLISION)
          and not has_color(REJECT_BORDER_DISCONNECTED))
    pygame.image.save(_coll, os.path.join(_tmp, 'gatsli_reject_collision.png'))
    print(f'  screenshots -> {_tmp}/gatsli_reject_*.png')

    # ---- H. §70 捆绑组组级边框反馈（整组重绘不再盖掉反馈色） ----
    def has_color_on(scr, rgb, tol=10):
        arr = pygame.surfarray.array3d(scr).astype(int)
        return bool((np.abs(arr - np.array(rgb)).max(axis=2) <= tol).any())

    def boot_bandaged():
        g = SliderGUI(cmd_queue=queue.Queue(),
                      ext_state={'enabled': False, 'token': None})
        g.game_mode = 'practice'
        g.tutorial_active = False
        g.tut_show_prompt = False
        g.animation_enabled = False
        g.new_puzzle(5, 5, 1)
        g._update_in_progress = False
        pos = {tuple(b.location): b for b in g.game.blocks}
        for c in ((0, 0), (0, 1), (1, 0), (1, 1)):
            pos[c].group = 1      # 2x2 捆绑组
        return g

    gb = boot_bandaged()
    _bb_calls = []
    _orig_bb = SliderGUI._bandaged_border

    def _spy_bb(self, *a, **k):
        r = _orig_bb(self, *a, **k)
        _bb_calls.append((a, r))
        return r

    SliderGUI._bandaged_border = _spy_bb

    def render_band(reason=None, anim=None):
        """清态 → 组成员设反馈 → 清屏画一帧 → (屏幕, spy 捕获的返回值)。"""
        gb._shake_t = 0
        gb._shake_blocks = set()
        gb._reject_reason = None
        gb._sel_anim_timer = 0
        gb._sel_anim_is_undo = None
        gb.drag_following = False
        gb.drag_follow_invalid = False
        for b in gb.game.blocks:
            b.be_opted = False
        members = [b for b in gb.game.blocks if getattr(b, 'group', 0) == 1]
        if reason:
            for b in members:
                b.be_opted = True
            gb._shake_blocks = set(id(b) for b in members)
            gb._shake_t = 12
            gb._reject_reason = reason
        elif anim is not None:
            for b in members:
                b.be_opted = True
            gb._sel_anim_timer = 12
            gb._sel_anim_is_undo = anim
        _bb_calls.clear()
        gb.screen.fill((0, 0, 0))
        gb.draw_board()
        return gb.screen.copy(), [r for _a, r in _bb_calls]

    try:
        _scr, _rets = render_band(reason='disconnected')
        _cols = [r[0] for r in _rets]
        check('H1 捆绑组拒绝闪现走组级反馈 = 冷紫（不再被盖成死灰）',
              REJECT_BORDER_DISCONNECTED in _cols, str(set(_cols)))
        check('H1b 冷紫真实出现在画面像素里',
              has_color_on(_scr, REJECT_BORDER_DISCONNECTED))
        _scr, _rets = render_band(reason='collision')
        check('H2 捆绑组拒绝 = 暖珊瑚',
              REJECT_BORDER_COLLISION in [r[0] for r in _rets],
              str(set(r[0] for r in _rets)))
        _scr, _rets = render_band(anim=True)
        check('H3 捆绑组撤销 = UNDO 蓝',
              SliderGUI.SEL_ANIM_BORDER_UNDO in [r[0] for r in _rets],
              str(set(r[0] for r in _rets)))
        check('H3b UNDO 蓝真实出现在画面像素里',
              has_color_on(_scr, SliderGUI.SEL_ANIM_BORDER_UNDO))
        _scr, _rets = render_band(anim=False)
        check('H4 捆绑组重做 = REDO 橙',
              SliderGUI.SEL_ANIM_BORDER_REDO in [r[0] for r in _rets],
              str(set(r[0] for r in _rets)))
        _scr, _rets = render_band()
        check('H5 计时器归零后回默认灰',
              _rets and all(r[0] == gb.colors['border'] for r in _rets),
              str(set(r[0] for r in _rets)))
    finally:
        SliderGUI._bandaged_border = _orig_bb
except Exception as e:
    import traceback
    traceback.print_exc()
    check('H 捆绑组反馈', False, str(e))

print('\n===', 'ALL PASS' if not _failures else f'{len(_failures)} FAILURES', '===')
sys.exit(1 if _failures else 0)
