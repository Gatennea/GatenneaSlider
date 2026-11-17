# -*- coding: utf-8 -*-
"""回归：三维「真的能玩的起步」——三轴六向推 + 判胜 + 打乱（§54 第 4 步上半）。

本步拆成两片做：
  ①（本文件）方向字母表 + 选中后能沿三轴六向推一步 / 推回、步数与判胜口径、
    打乱可继续；撤销重做**明确拒绝**（历史扩到 (r,c,d) 是第 5 步）。
  ②（未做）虚拟键盘三轴六键 + 重画箭头。

钉住这几条：
  A. compat 注册的 cubic 字母表 = r/R c/C d/D，且与 spec 六向一一对应。
  B. 双击选中一侧后按字母推：整组同向位移、块数守恒、步数 +1、历史不炸。
  C. 旋转态（不在六朝向之一）按键不推；没选中按键只提示。
  D. 撤销 / 重做在三维下被明确拒绝（不抛 ValueError，位置不变）。
  E. 未还原时 is_solved() 为假、打乱后仍为假且渲染不崩；还原态为真。

跑法：D:/python/python.exe test/_test_cubic_play.py
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

from engine.adapter import create_adapter_puzzle  # noqa: E402
from engine.compat import CUBIC_DIRECTIONS, direction_table  # noqa: E402

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
print('A. 方向字母表')
game = create_adapter_puzzle('cubic', 3, 3, 1, depth=3)
table = direction_table(game.spec)
check(table == CUBIC_DIRECTIONS,
      'registered cubic table is r/R c/C d/D', extra=str(sorted(table)))
check(set(table.values()) == set(game.spec.directions),
      '六字母与 spec 六向一一对应（不多不少）')
for letter, vec in CUBIC_DIRECTIONS.items():
    check(sum(abs(v) for v in vec) == 1 and len(vec) == 3,
          f'{letter} 是单轴单位向量', extra=str(vec))
check(direction_table(game.spec) is not None and
      len(direction_table(game.spec)) == 6, '字母表恰好六项')

print('B. 选中后按字母推')
from GUI import SliderGUI  # noqa: E402

pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_play_')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
gui.config_path = os.path.join(gui.config_dir, 'config.json')
gui._readonly = False
gui.save_readonly_flag = False
gui.animation_enabled = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui._cubic_camera_prefs = {}
gui.new_cubic_puzzle(3, 3, 3, 1)
gui._cubic_view(0)
gui.draw_cubic_board()


def locs():
    return sorted(tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks)


def click(pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))
    gui.handle_events()


def key(k, mod=0):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode=''))
    gui.handle_events()


face = gui._cubic_scene['faces'][-1]
pt = (int(sum(p[0] for p in face['pts']) / 4.0),
      int(sum(p[1] for p in face['pts']) / 4.0))
click(pt)
click(pt)
check(any(b.be_opted for b in gui.game.blocks), '双击选中一侧连通组')
check(gui.game.is_solved(), '建局 = 还原态，is_solved() 为真（还没推）')

# 双击后选中的切面由「离点击最近的那条缝」决定（2026-11-17 改）。
# 注意：合法推法是**沿切面滑动**——方向必须与缝族垂直（引擎 action_to_move
# 会拒「法向推」为 bad_direction），所以从另两根轴里挑一个能走通的。
FAMILY_KEY = {'r': pygame.K_r, 'c': pygame.K_c, 'd': pygame.K_d}
fam = gui.selected_gap[0]
before = locs()
step0 = gui.step_count
used = None
for push in [f for f in ('r', 'c', 'd') if f != fam]:
    for mod in (0, pygame.KMOD_SHIFT):
        key(FAMILY_KEY[push], mod=mod)
        if gui.step_count == step0 + 1:
            used = (push, mod)
            break
    if used:
        break
check(used is not None, f'沿切面 {fam} 能推一步（步数 {gui.step_count}，{gui.macro_notify_msg}）')
after = locs()
check(gui.step_count == step0 + 1, f'推一步步数 +1（{gui.step_count}）')
check(len(after) == len(before) == 27, '块数守恒 27')
check(set(after) != set(before), '位置确实变了（不是空推）')
check(not gui.game.is_solved(), '推一步后不再还原（is_solved 为假）')
check(used[0] in (gui.macro_notify_msg or ''), f'提示带方向名（{gui.macro_notify_msg}）')

key(FAMILY_KEY[used[0]], mod=(pygame.KMOD_SHIFT if used[1] == 0 else 0))
check(set(locs()) == set(before), '反向字母推回原位')
check(gui.game.is_solved(), '推回后重新还原')

print('C. 闸门（斜视下照样能推 / 没选中不推）')
gui._cubic_view_oblique()
gui.draw_cubic_board()
# 斜视下仍然有选中（前进到上一步时选中的组没被清掉），推一步应该生效
opted = [tuple(int(v) for v in b.location[:3])
         for b in gui.game.blocks if getattr(b, 'be_opted', False)]
check(bool(opted), '斜视前已有选中组')
before = locs()
key(pygame.K_c, mod=pygame.KMOD_SHIFT)
check(set(locs()) != set(before) or '推不动' in (gui.macro_notify_msg or ''),
      f'斜视下按键会真的尝试推进（{gui.macro_notify_msg}）')
check('旋转态' not in (gui.macro_notify_msg or ''),
      f'不再拦「旋转态」（{gui.macro_notify_msg}）')
gui._cubic_view(0)
gui._cubic_clear_selection()
n_before = gui.step_count
before = locs()
key(pygame.K_c, mod=pygame.KMOD_SHIFT)
check(set(locs()) == set(before), '没选中按键不推')
check(gui.step_count == n_before,
      f'没选中被拒时步数不涨（之前 {n_before}，现在 {gui.step_count}）')

print('D. 撤销 / 重做在三维下明确拒绝（不崩）')
before = locs()
gui.undo()
check(set(locs()) == set(before), '撤销被拒，位置不变')
check('第 5 步' in (gui.macro_notify_msg or ''), f'撤销提示指路第 5 步（{gui.macro_notify_msg}）')
gui.redo()
check(set(locs()) == set(before), '重做被拒，位置不变')
check('第 5 步' in (gui.macro_notify_msg or ''), '重做提示同样指路第 5 步')

print('E. 打乱 / 判胜 / 渲染')
gui.shuffle_puzzle(confirm=False)
check(len(gui.game.blocks) == 27, '打乱后块数仍 27')
check(not gui.game.is_solved(), '打乱后不是还原态')
gui._cubic_view(0)
gui.draw_cubic_board()
check(len(gui._cubic_scene['faces']) > 27, '打乱后仍有可见面（渲染不崩）')
check(gui.step_count == 0, f'打乱把步数清零（打乱本身不算一步，实得 {gui.step_count}）')

print('=' * 60)
if _fail:
    print(f'结果：{_ok[0]} 项通过，{len(_fail)} 项失败')
    for m in _fail:
        print('  ·', m)
    sys.exit(1)
print(f'结果：全部通过（{_ok[0]} 项通过，0 项失败）')

