# -*- coding: utf-8 -*-
"""回归：三維內部宏 op 執行器（P1）。

不做 GUI 玩家宏，只鎖求解器依賴的內部契約：
  A. 40 個連續 op（動畫開）逐步 `opt()` + `move_selected_blocks()`，最終盤面
     與規劃器一致；
  B. 同一串 op 把 `side` 抹成 None，執行器從 `rep_cell` 反推側別，結果仍一致；
  C. `rep_cell` 指向已不在的格時，退回「同側找塊」仍能執行；
  D. 壞 gap（線號 -1）明確失敗、留 `macro_error_msg`、清隊列；
  E. 三維 GUI 宏入口真的被 gate：錄製 / 執行都回「三維暫未開放宏功能」。

跑法：D:/python/python.exe test/_test_cubic_macro_exec.py
"""
import copy
import os
import random
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return bool(cond)


_AXIS = {'r': 0, 'c': 1, 'd': 2}


def find_op(game):
    """在當前盤面找一條合法三維滑動，返回 (op, final_positions)。"""
    for gap_type, axis in _AXIS.items():
        for line in range(1, int(game.depth)):
            for side in ('above', 'below'):
                if not game.side_has_blocks(gap_type, line, side):
                    continue
                for b in game.blocks:
                    b.be_opted = False
                cand = None
                for b in game.blocks:
                    rank = b.location[axis]
                    if (side == 'above' and rank <= line) or (
                            side == 'below' and rank > line):
                        cand = b
                        break
                if cand is None:
                    continue
                game.opt(gap_type, line, cand)
                selected = [b for b in game.blocks if b.be_opted]
                # 整盤平移無意義；也不接受空組。
                if not selected or len(selected) == len(game.blocks):
                    continue
                for direction in ('r', 'R', 'c', 'C', 'd', 'D'):
                    final_positions, _reason = game.try_move_ex(direction, 1)
                    if final_positions:
                        return ({
                            'kind': 'cubic',
                            'gap_type': gap_type,
                            'gap_line': line,
                            'side': side,
                            'direction': direction,
                            'step': 1,
                            'rep_cell': list(cand.location[:3]),
                        }, final_positions)
    return None, None


def build_ops(gui, n_ops=40):
    planner = copy.deepcopy(gui.game)
    ops = []
    final_positions = None
    for _ in range(n_ops):
        op, fp = find_op(planner)
        if op is None:
            break
        ops.append(op)
        planner.commit_move(fp)
        final_positions = sorted(tuple(b.location[:3]) for b in planner.blocks)
    return ops, final_positions


def run_ops(gui, ops):
    gui.macro_exec_ops = copy.deepcopy(ops)
    gui.macro_exec_index = 0
    gui.macro_executing = True
    gui.macro_error_msg = ''
    gui._solved_popup_shown = True
    for i in range(len(ops)):
        ok = gui._execute_cubic_macro_op(gui.macro_exec_ops[i])
        if not ok:
            return False, i
    return True, len(ops)


print('=' * 60)
print('A. 連續 40 個 op（動畫開）')
pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_macro_exec_')
gui.config_path = os.path.join(gui.config_dir, 'config.json')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
gui.tutorial_active = False
gui.tut_show_prompt = False
gui._cubic_camera_prefs = {}
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui.new_cubic_puzzle(4, 4, 4, 1)
gui.cubic_gap = 0.12
random.seed(7)
gui.shuffle_puzzle(confirm=False)
gui.animation_enabled = True

_initial = gui.game.snapshot_state()
_ops, _expected = build_ops(gui, 40)
check(len(_ops) >= 20, f'規劃出足夠的連續 op（{len(_ops)} 條）', len(_ops))
check(_expected is not None, '規劃器留下最終盤面')
gui.game.restore_state(_initial)

_success, _n = run_ops(gui, _ops)
_actual = sorted(tuple(b.location[:3]) for b in gui.game.blocks)
check(_success, f'動畫開：{_n} 條 op 全部成功', _n)
check(_actual == _expected, '動畫開：最終盤面與規劃器一致',
      (_actual[:3], _expected[:3] if _expected else None))
check(gui.macro_exec_index == len(_ops), '每步都推進 macro_exec_index',
      gui.macro_exec_index)

print('=' * 60)
print('B. side=None 由 rep_cell 反推側別')
_ops_side_none = copy.deepcopy(_ops)
for op in _ops_side_none:
    op['side'] = None
gui.game.restore_state(_initial)
gui.animation_enabled = False
_success2, _n2 = run_ops(gui, _ops_side_none)
_actual2 = sorted(tuple(b.location[:3]) for b in gui.game.blocks)
check(_success2, f'動畫關：{_n2} 條 op 全部成功', _n2)
check(_actual2 == _expected, 'side=None 仍與規劃器一致',
      (_actual2[:3], _expected[:3] if _expected else None))

print('=' * 60)
print('C. rep_cell 失效 → 同側找塊')
gui.game.restore_state(_initial)
_fallback = copy.deepcopy(_ops[0])
_fallback['rep_cell'] = [-999, -999, -999]
_success3 = gui._execute_cubic_macro_op(_fallback)
check(_success3, 'rep_cell 不在盤上時退回同側找塊並執行成功', gui.macro_error_msg)

print('=' * 60)
print('D. 壞 gap 明確失敗')
gui.game.restore_state(_initial)
gui.macro_exec_ops = [{'kind': 'cubic', 'gap_type': 'r', 'gap_line': -1,
                       'side': 'above', 'direction': 'c', 'step': 1}]
gui.macro_exec_index = 0
gui.macro_executing = True
gui.macro_error_msg = ''
_ok4 = gui._execute_cubic_macro_op(gui.macro_exec_ops[0])
check(_ok4 is False, 'gap_line=-1 返回 False')
check('第 1 步失败' in (gui.macro_error_msg or ''),
      '錯誤訊息帶步號與原因', gui.macro_error_msg)
check(gui.macro_exec_ops == [] and gui.macro_executing is False,
      '失敗後清隊列並退出執行態', (gui.macro_exec_ops, gui.macro_executing))

print('=' * 60)
print('E. 三維 GUI 宏入口 gate')
gui.macro_recording = False
gui.macro_executing = False
gui._start_macro_recording()
check(gui.macro_recording is False, '點錄製宏：沒有真的進入錄製')
check(gui.macro_notify_msg == '三维暂未开放宏功能',
      '錄製入口提示暫未開放', gui.macro_notify_msg)
gui._start_macro_execute('任意宏')
check(gui.macro_executing is False and gui.macro_selecting_base is False,
      '點執行宏：沒有真的進入等待基準')
check(gui.macro_notify_msg == '三维暂未开放宏功能',
      '執行入口提示暫未開放', gui.macro_notify_msg)

print('=' * 60)
print(f'{_ok[0]} ok, {len(_fail)} failed')
if _fail:
    for msg in _fail:
        print('FAIL:', msg)
    raise SystemExit(1)
