# -*- coding: utf-8 -*-
"""回归：无限打乱接入三维（2026-11-18）。

用户报「無限打亂也接入三維」：二维无限打乱一直是逐格随机游走，但三维里
``_ann_dirs_for_gap`` 落到方形 h/v 表，c/d 族拿到空元组，第一步就误判
「无可逆走法」并自动停机。这里钉住修好后的行为：

  A. 三维 r/c/d 三族都能拿到平行于缝的四个方向字母。
  B. 从「打乱」入口（shuffle_puzzle）能启动三维无限游走，不是直接调
     _start_infinite_shuffle 的旁路。
  C. 连续提交 12 格：模式仍活着、步数递增、每一格都真的动了块。
  D. 再点一次「打乱」= 停止：模式关闭、步数归零、历史以当前态为根
     （不可撤回）。

跑法：D:/python/python.exe test/_test_cubic_infinite.py
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

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


print('=' * 60)
print('A. 三维缝族方向表')
from GUI import SliderGUI  # noqa: E402

pygame.init()
gui = SliderGUI(m=4, n=4, step=2)
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_infinite_')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
gui.config_path = os.path.join(gui.config_dir, 'config.json')
gui._readonly = False
gui.save_readonly_flag = False
gui.animation_enabled = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui._cubic_camera_prefs = {}
gui.new_cubic_puzzle(4, 4, 4, 2)

want = {
    'r': {'C', 'D', 'c', 'd'},
    'c': {'D', 'R', 'd', 'r'},
    'd': {'C', 'R', 'c', 'r'},
}
for fam, letters in want.items():
    got = set(gui._ann_dirs_for_gap(fam))
    check(got == letters, f'{fam} 族方向 = 平行四向', extra=str(got))
    check(len(got) == 4, f'{fam} 族不沿用方形 h/v 的两向表')

print('B. 从打乱入口启动三维无限游走')
gui.infinite_shuffle = True
gui.confirm_before_shuffle = False
gui.selection_animation_enabled = True
gui.shuffle_puzzle(confirm=False)
check(getattr(gui, '_infinite_shuffle_active', False),
      '打乱入口启动了三维连续游走')
check(gui.step_count == 1, f'第一步已计步（{gui.step_count}）')
check(gui.animating, '第一步动画已启动')
check(any(tuple(p) != tuple(b.location)
          for p, b in zip(gui.anim_end_pos, gui.anim_blocks)),
      '第一步动画终点真的离开了起点')
check('无可逆走法' not in gui.macro_notify_msg,
      f'不再误报无可逆走法（{gui.macro_notify_msg}）')
check(gui.selected_gap and gui.selected_gap[0] in ('r', 'c', 'd'),
      f'选中动画的缝来自三维族（{gui.selected_gap}）')

print('C. 连续 12 格：不停机、每格都动')
for i in range(12):
    if not getattr(gui, '_infinite_shuffle_active', False):
        break
    if not getattr(gui, 'animating', False):
        break
    prev = [tuple(b.location) for b in gui.game.blocks]
    gui.commit_animation()
    check(any(a != tuple(b.location) for a, b in zip(prev, gui.game.blocks))
          or not getattr(gui, 'animating', False),
          f'第 {i + 2} 格提交后块位置有变化')
check(getattr(gui, '_infinite_shuffle_active', False),
      f'连走 12 格后仍在游走（步数 {gui.step_count}）')
check(gui.step_count >= 12, f'步数持续增长（{gui.step_count}）')

print('D. 再点打乱 = 停止，历史以当前态为根')
gui.shuffle_puzzle(confirm=False)
check(not getattr(gui, '_infinite_shuffle_active', False), '无限游走已停止')
check(gui.step_count == 0, f'停止后步数归零（{gui.step_count}）')
check(not gui.game_history.can_undo(), '停止后不可撤回（当前态即历史根）')
check(gui.macro_notify_msg == '已停止无限打乱',
      f'停止提示正确（{gui.macro_notify_msg}）')

print('=' * 60)
if _fail:
    print(f'结果：{_ok[0]} 通过，{len(_fail)} 失败')
    for msg in _fail:
        print('  -', msg)
    sys.exit(1)
print(f'结果：全部通过（{_ok[0]} 项）')
