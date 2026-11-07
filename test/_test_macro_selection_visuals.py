# -*- coding: utf-8 -*-
"""护栏：关掉「选中动画」后，求解器/宏播放不许再显示选中态提示。

用户 2026-11-07 报（待办 §二十三）：「求解器播放動畫時關閉選中動畫
實際無效」。根因不是开关没读，而是这个开关原来只管撤销/重做与打乱演示
两条高亮分支；宏队列播放走 ``_execute_next_macro_step()``，每步直接写
``selected_gap`` 与 ``be_opted``（``game.opt`` 的执行状态），渲染据此画
红缝 + 整片选中色，另有求解演示的白色光边，三样都不看开关。

正解（本护栏钉住）：**不动功能状态，只收视觉**。
``game.opt`` / ``try_move`` / ``commit_move`` 照旧用 be_opted 选组、把
final_positions 配对回块；这一步用完之后，
``events._clear_macro_selection_if_disabled()`` 在开关关闭时把红缝与选中色
清掉（必须排在 commit_move 之后）。白光边与撤销/重做边框则由
``renderer._selection_visuals_enabled()`` 这个共用判据直接关掉。
开关开着、手玩选中、撤销/重做全部保持原样。

覆盖：无动画回放 / 动画播放 / 提交收尾 / 像素级渲染 / 四形态 / 反向验证。

执行：``python test/_test_macro_selection_visuals.py``
"""
import inspect
import os
import queue
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import numpy as np  # noqa: E402
import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

_failed = []

# 方形 4×4 上实测能真正走一步的宏 op（探针枚举出来的最小样本）。
OP = {'gap_type': 'h', 'gap_line': 0, 'side': 'above',
      'direction': 'd', 'step': 1}


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failed.append(name)
    return bool(cond)


def boot(sel_on, *, anim=False, kind='sq'):
    g = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                  ext_state={'enabled': False, 'token': None})
    g.game_mode = 'practice'
    g.tutorial_active = False
    g.tut_show_prompt = False
    g.save_readonly_flag = False
    if kind == 'sq':
        g.new_puzzle(4, 4, 2)
    elif kind == 'tri':
        g.new_triangle_puzzle(4, 2)
    elif kind == 'mi':
        g.new_mi_puzzle(4, 4, 2)
    elif kind == 'generic':
        g.new_model_puzzle('shatter', 1)
    g.selection_animation_enabled = sel_on
    g.animation_enabled = anim
    if anim:
        g.animation_duration = 2000
    g.ui_mode = 'enhanced'
    pygame.display.set_mode((g.screen_width, g.screen_height))
    g.screen = pygame.display.get_surface()
    return g


def positions(g):
    return sorted(tuple(b.location) for b in g.game.blocks)


def opted_count(g):
    return sum(1 for b in g.game.blocks if getattr(b, 'be_opted', False))


def start_macro(g):
    g.macro_executing = True
    g.macro_exec_name = '护栏'
    g.macro_exec_ops = [dict(OP)]
    g.macro_exec_index = 0
    g.macro_exec_factor = 1
    g.macro_error_msg = ''
    g._gather_info = None
    g._stream_active = False
    g._stream_queue = None


def pixels(g):
    """离屏画一帧，数红缝色与选中色像素（两种色在这个盘上没有别的用途）。"""
    g.draw_board()
    arr = pygame.surfarray.array3d(g.screen).astype(np.int16)
    red = np.array(g.colors['line'][:3], dtype=np.int16)
    sel = np.array(g.colors['block_selected'][:3], dtype=np.int16)
    n_red = int((np.abs(arr - red).sum(axis=2) == 0).sum())
    n_sel = int((np.abs(arr - sel).sum(axis=2) == 0).sum())
    return n_red, n_sel


# ---- A 无动画回放：清视觉，但不能碰功能 ---------------------------------
res = {}
for on in (True, False):
    g = boot(on)
    before = positions(g)
    start_macro(g)
    g._execute_next_macro_step()
    res[on] = {
        'gap': g.selected_gap,
        'opted': opted_count(g),
        'err': g.macro_error_msg,
        'after': positions(g),
        'steps': g.step_count,
        'before': before,
    }

check('A1 开关开着：原有高亮行为保留',
      res[True]['gap'] == ('h', 0) and res[True]['opted'] > 0,
      f"gap={res[True]['gap']} opted={res[True]['opted']}")
check('A2 开关关着：播放完不残留红缝与选中色',
      res[False]['gap'] is None and res[False]['opted'] == 0,
      f"gap={res[False]['gap']} opted={res[False]['opted']}")
check('A3 关闭开关不破坏移动（两态落点、步数一致且真走了）',
      res[False]['err'] == '' and res[True]['err'] == ''
      and res[False]['after'] != res[False]['before']
      and res[False]['after'] == res[True]['after']
      and res[False]['steps'] == res[True]['steps'],
      f"steps={res[False]['steps']} err={res[False]['err']!r}")

# ---- B 动画播放中：三样提示一起关，动画照样能提交 ------------------------
anim = {}
for on in (True, False):
    g = boot(on, anim=True)
    start_macro(g)
    g._execute_next_macro_step()
    g.anim_progress = 0.35
    red, sel = pixels(g)
    anim[on] = {
        'g': g,
        'animating': g.animating,
        'gap': g.selected_gap,
        'opted': opted_count(g),
        'head': g._play_head_border(),
        'red': red,
        'sel': sel,
    }

check('B1 开关开着：动画帧有红缝、选中色与白色光边',
      anim[True]['animating'] and anim[True]['gap'] is not None
      and anim[True]['opted'] > 0 and anim[True]['head'] is not None)
check('B2 开关关着：动画帧三样提示全无',
      anim[False]['animating'] and anim[False]['gap'] is None
      and anim[False]['opted'] == 0 and anim[False]['head'] is None,
      f"head={anim[False]['head']}")
check('B3 像素级：开着画得出红缝/选中色，关着一像素都没有',
      anim[True]['red'] > 1000 and anim[True]['sel'] > 1000
      and anim[False]['red'] == 0 and anim[False]['sel'] == 0,
      f"on=({anim[True]['red']},{anim[True]['sel']}) "
      f"off=({anim[False]['red']},{anim[False]['sel']})")

g_off = anim[False]['g']
g_off.commit_animation()
check('B4 动画提交后仍干净、回放正常收尾',
      g_off.macro_error_msg == '' and not g_off.macro_executing
      and g_off.selected_gap is None and opted_count(g_off) == 0,
      f"err={g_off.macro_error_msg!r} gap={g_off.selected_gap}")

# ---- C 手玩选中不受影响（开关只管自动播放，不该把手玩也关掉） ------------
g = boot(False)
g.selected_gap = ('h', 1)
g.game.blocks[0].be_opted = True
hand_red, hand_sel = pixels(g)
check('C1 手玩选中照常高亮',
      g.selected_gap == ('h', 1) and opted_count(g) == 1
      and hand_red > 0 and hand_sel > 0,
      f"red={hand_red} sel={hand_sel}")

# ---- D 四形态：清理 helper 形态中立 --------------------------------------
for kind in ('sq', 'tri', 'mi', 'generic'):
    h = boot(False, kind=kind)
    h.selected_gap = ('h', 1)
    h.game.blocks[0].be_opted = True
    h._clear_macro_selection_if_disabled()
    check(f'D-{kind} 关闭时清掉红缝与选中色',
          h.selected_gap is None and opted_count(h) == 0)
    k = boot(True, kind=kind)
    k.selected_gap = ('h', 1)
    k.game.blocks[0].be_opted = True
    k._clear_macro_selection_if_disabled()
    check(f'D-{kind} 开着时一个字节都不碰',
          k.selected_gap == ('h', 1) and opted_count(k) == 1)

# ---- E 静态接线：所有退出分支都接了清理、光边共用开关判据 ----------------
macro_src = inspect.getsource(SliderGUI._execute_next_macro_step)
head_src = inspect.getsource(SliderGUI._play_head_border)
undo_src = inspect.getsource(SliderGUI._sel_anim_border)
clean_src = inspect.getsource(SliderGUI._clear_macro_selection_if_disabled)
check('E1 宏播放每个退出分支都接了清理（防漏接、防回流）',
      macro_src.count('_clear_macro_selection_if_disabled()') >= 8,
      f"count={macro_src.count('_clear_macro_selection_if_disabled()')}")
check('E2 白光边与撤销/重做高亮共用同一开关判据',
      '_selection_visuals_enabled' in head_src
      and '_selection_visuals_enabled' in undo_src)
check('E3 清理只收视觉态，不碰 game.opt / try_move / commit_move',
      'game.opt(' not in clean_src and 'try_move(' not in clean_src
      and 'commit_move(' not in clean_src)
check('E4 无动画路径的清理排在 commit_move 之后',
      macro_src.find('self.game.commit_move(final_positions)')
      < macro_src.find('self._clear_macro_selection_if_disabled()',
                       macro_src.find('self.game.commit_move(final_positions)')))

# ---- F 反向验证：撤掉清理，断言必须转红 ----------------------------------
_orig = SliderGUI._clear_macro_selection_if_disabled
SliderGUI._clear_macro_selection_if_disabled = lambda self: None
try:
    r = boot(False, anim=True)
    start_macro(r)
    r._execute_next_macro_step()
    r.anim_progress = 0.35
    r_red, r_sel = pixels(r)
finally:
    SliderGUI._clear_macro_selection_if_disabled = _orig
check('F1 撤掉清理后红缝与选中色回流（护栏确实抓得住）',
      r.selected_gap is not None and opted_count(r) > 0
      and r_red > 1000 and r_sel > 1000,
      f"gap={r.selected_gap} opted={opted_count(r)} "
      f"red={r_red} sel={r_sel}")

print()
if _failed:
    print(f'FAILED {len(_failed)}: ' + '; '.join(_failed))
    sys.exit(1)
print('ALL PASS')
