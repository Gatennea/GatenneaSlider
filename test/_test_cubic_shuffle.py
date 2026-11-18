# -*- coding: utf-8 -*-
"""回归：三维打乱（方案第 5 阶段「真的能玩」的入口）。

2026-11-18 实测过一个致命问题：三维按「打乱」**盘面纹丝不动**（changed=0，
is_solved=True），提示还停在换局那句。根因不是引擎——`EngineGame.shuffle`
在 (r,c,d) 上本身是通的（裸调 40 次尝试能改 26 块）——而是 GUI 包装层把记录
交给了「打乱演示」：演示按 (行,列) 两坐标重放，三维记录是 (r,c,d) 三步位移，
重放失败就把盘面先退回**打乱前**的还原态，看起来像什么都没发生。

本测试钉住：
  A. 关动画：打乱真的改了盘面、落在未复原态、历史只剩一条终态、步数归零。
  B. 开动画：同样立刻落到终态（三维不走二维演示，不退回还原态）。
  C. 二维开动画仍然走演示（不因为三维的改动把二维演示关掉）。
  D. 打乱后的局面还能继续玩：随便选中一侧推一步仍然合法。

跑法：D:/python/python.exe test/_test_cubic_shuffle.py
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


def make_gui(anim=False):
    gui = SliderGUI(m=4, n=4, step=1)
    gui.animation_enabled = anim
    gui.animation_duration = 60 if anim else 0
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    d = tempfile.mkdtemp(prefix='gs_cubic_shuffle_')
    gui.config_dir = d
    gui.config_path = os.path.join(d, 'config.json')
    gui.temp_history_path = os.path.join(d, 'temp_history.json')
    gui._readonly = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui._cubic_camera_prefs = {}
    gui.new_cubic_puzzle(3, 3, 3, 1)
    return gui


def _changed(gui, before):
    return sum(1 for a, b in zip(before, [tuple(x.location) for x in gui.game.blocks])
               if a != b)


print('=' * 60)
print('A. 关动画：打乱真的生效')
g = make_gui(anim=False)
before = [tuple(b.location) for b in g.game.blocks]
check(g.game.is_solved(), '开局是还原态（未打乱前）')
g.shuffle_puzzle(confirm=False)
check(_changed(g, before) > 10, '打乱后多数块位置变了', _changed(g, before))
check(not g.game.is_solved(), '打乱后不再是还原态')
check(len(g.game_history.history) == 1, '历史被重置成一条（打乱态为基准）',
      len(g.game_history.history))
check(g.step_count == 0, '步数归零', g.step_count)
check('已打乱' in (g.macro_notify_msg or ''), '提示写明已打乱', g.macro_notify_msg)

print('=' * 60)
print('B. 开动画：同样立刻落到终态（不走二维演示）')
g2 = make_gui(anim=True)
before2 = [tuple(b.location) for b in g2.game.blocks]
g2.shuffle_puzzle(confirm=False)
check(_changed(g2, before2) > 10, '开动画时盘面也真的变了（不退回还原态）',
      _changed(g2, before2))
check(not g2.game.is_solved(), '开动画时仍落在未复原态')
check(not g2.animating, '三维不打乱演示（不进入 animating 锁盘）', g2.animating)

print('=' * 60)
print('C. 二维开动画仍走演示（别把二维演示误关）')
g3 = SliderGUI(m=4, n=4, step=1)
g3.animation_enabled = True
g3.animation_duration = 60
g3.tut_show_prompt = False
g3.tutorial_active = False
d3 = tempfile.mkdtemp(prefix='gs_square_shuffle_')
g3.config_dir = d3
g3.config_path = os.path.join(d3, 'config.json')
g3.temp_history_path = os.path.join(d3, 'temp_history.json')
g3._readonly = False
pygame.display.set_mode((g3.screen_width, g3.screen_height))
g3.screen = pygame.display.get_surface()
g3.new_puzzle(4, 4, 2)
b3 = [tuple(x.location) for x in g3.game.blocks]
g3.shuffle_puzzle(confirm=False)
# 二维演示会把盘面先退回打乱前、再逐步重放（所以「此刻位置没变」是正常的）；
# 判据看演示确实启动了，说明演示分支没被三维的改动误关。
check(getattr(g3, '_shuffle_demo_active', False) or g3.animating,
      '二维开动画仍然进入打乱演示', (getattr(g3, '_shuffle_demo_active', None),
                                    g3.animating))

print('=' * 60)
print('D. 打乱后还能继续推')
g4 = make_gui(anim=False)
g4.shuffle_puzzle(confirm=False)
block = g4.game.blocks[0]
seam = None
from engine import cubic_pick
for fam, line in (('r', 0), ('r', 1), ('c', 0), ('c', 1), ('d', 0), ('d', 1)):
    if g4.game.is_valid_gap(fam, line):
        seam = (fam, line)
        break
check(seam is not None, '打乱后仍有合法缝可选')
if seam:
    g4.game.opt(seam[0], seam[1], block)
    ok = g4.move_selected_blocks('r') or g4.move_selected_blocks('c') \
        or g4.move_selected_blocks('d')
    check(ok, '打乱后推得动（选一侧 + 沿某轴）', ok)

print('=' * 60)
total = _ok[0] + len(_fail)
print(f'结果：{"全部通过" if not _fail else "有失败"}（{_ok[0]} 项通过，{len(_fail)} 项失败）／共 {total} 项')
if _fail:
    for f in _fail:
        print('  -', f)
sys.exit(1 if _fail else 0)
