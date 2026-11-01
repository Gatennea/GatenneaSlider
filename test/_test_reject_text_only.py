# -*- coding: utf-8 -*-
"""回归：选不中的缝只给文字提示，绝无白线/叉号图形（2026-11-02 设计回退）。

历史脉络：2026-11-01~02 曾在「选不中缝」上叠加过白线+叉号图形反馈（现完整保留在
archive/reject-seam-graphics 分支），但用户判定这类缝太多（尤其自造模型），图形
高亮太吵，决定回退到「只文字、无图形」——点到了选不中的缝，弹一句文字提示即可，
代价是看不出具体挡在哪。本测试锁死这条设计，防未来误加重加图形：

  A. 渲染器不得存在任何被拒缝图形绘制方法（硬护栏：重加即红）；
  B. 点到选不中的缝（死缝 / 错位接缝）必须给 macro_notify_msg 文字提示；
  C. 同一点击绝不得设置 rejected_gap（图形高亮的载体）——确保无图形。

执行：``D:/python/python.exe -u test/_test_reject_text_only.py``
"""
import os
import queue
import sys
import random

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from engine.compat import direction_table  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def boot(which, *args):
    gui = SliderGUI(cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui.animation_enabled = False
    getattr(gui, which)(*args)
    gui._update_in_progress = False
    return gui


# ---- A. 硬护栏：渲染器不得存在被拒缝图形绘制方法 ----
check('A1 无 _draw_gap_reject_marks', not hasattr(SliderGUI, '_draw_gap_reject_marks'))
check('A2 无 _draw_rejected_gap_preview',
      not hasattr(SliderGUI, '_draw_rejected_gap_preview'))
check('A3 无 _gap_reject_mark_points',
      not hasattr(SliderGUI, '_gap_reject_mark_points'))


def _all_moves(g, tbl):
    out = []
    for (_gf, _line) in list(g.all_gaps()):
        _fam = next(f for f in g.spec.seam_families if f.name == _gf)
        for _letter, _d in sorted(tbl.items()):
            if _d not in _fam.parallel:
                continue
            for _b in g.blocks:
                g.opt(_gf, _line, _b)
                _pos, _reason = g.try_move_ex(_letter, 1)
                if _reason == '':
                    out.append((_gf, _line, _b, _letter))
    return out


_found = 0
_bad = 0
_sample = None
for _seed in (7, 1, 2, 3):
    gui = boot('new_shatter_puzzle', _seed)
    g = gui.game
    _tbl = direction_table(g.spec)
    random.seed(_seed)
    for _i in range(25):
        _moves = _all_moves(g, _tbl)
        if not _moves:
            break
        _gf, _line, _blk, _letter = random.choice(_moves)
        gui.selected_gap = (_gf, _line)
        gui.selected_block = _blk
        g.opt(_gf, _line, _blk)
        pygame.event.post(pygame.event.Event(
            pygame.KEYDOWN, {'key': getattr(pygame, 'K_' + _letter.lower()),
                             'mod': 0, 'unicode': _letter}))
        gui.handle_events()
        gui._update_in_progress = False
    W = gui.screen_width
    H = gui.screen_height
    for _sx in range(20, W - 20, 7):
        for _sy in range(20, H - 20, 7):
            pygame.mouse.set_pos((_sx, _sy))
            gui.selected_gap = None
            gui.selected_block = None
            gui.macro_notify_msg = None
            gui.macro_notify_timer = 0
            if getattr(gui, 'rejected_gap', None) is not None:
                gui.rejected_gap = None
            gui._sq_click_query(_sx, _sy)
            _msg = gui.macro_notify_msg
            if not _msg:
                continue
            _found += 1
            # B/C：有文字提示，且绝无图形载体
            _has_graphics = getattr(gui, 'rejected_gap', None) is not None
            if _has_graphics:
                _bad += 1
                if _sample is None:
                    _sample = (_seed, _sx, _sy, _msg, 'rejected_gap set')
            elif _sample is None:
                _sample = (_seed, _sx, _sy, _msg)
    if _found:
        break  # 一个种子找到足够证明设计，省时间

check('B 扫到至少一个「点选不中缝给文字提示」的点', _found >= 1, f'found={_found}')
check('C 文字提示点击绝无图形载体(rejected_gap)',
      _bad == 0, f'bad={_bad} sample={_sample}')

print('\n===', 'ALL PASS' if not _failures else f'{len(_failures)} FAILURES', '===')
sys.exit(1 if _failures else 0)
