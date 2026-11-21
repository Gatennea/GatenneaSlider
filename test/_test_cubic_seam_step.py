# -*- coding: utf-8 -*-
"""回归：三维法线轴「上/下一个切面」步进。

钉住用户 2026-11-21 的口径：
  A. 只沿当前切面的法线轴走；大写 = 正方向 +1，小写 = 负方向 -1。
  B. 跳过中间无效缝，找到下一条 `is_valid_gap` 为真的切面。
  C. 切换切面后仍用同一个参考块 `game.opt(fam, new_line, ref)` 重选，
     `selected_block` 不变、步数不涨、不写历史。
  D. 虚拟键盘法线轴两端与盘面两枚方键走同一套动作；两端不可用时变灰。
  E. 没有参考块时只切切面，不误选隔壁组。

跑法：D:/python/python.exe test/_test_cubic_seam_step.py
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


from GUI import SliderGUI  # noqa: E402

pygame.init()
gui = SliderGUI(m=3, n=3, step=1)
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_seam_step_')
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


def arm_gap(fam='c', line=1):
    """把切面设到 line，并用一块参考块选同侧连通组（不走屏幕点击）。"""
    gui._cubic_clear_selection()
    gui.selected_gap = (fam, line)
    ref = gui.game.blocks[0]
    gui.game.opt(fam, line, ref)
    gui.selected_block = ref
    return ref


def click(x, y):
    pos = (x, y)
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {'pos': pos, 'button': 1}))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, {'pos': pos, 'button': 1}))
    gui.handle_events()


print('=' * 60)
print('A. 正负方向与有效性扫描')
ref = arm_gap('c', 0)
valid = [ln for ln in range(-1, 3) if gui.game.is_valid_gap('c', ln)]
check(valid == [0, 1], f'3×3×3 实心 c 轴两条内部缝都有效（{valid}）')
check(gui._cubic_seam_step_target('C') == 1, '大写 C 找到正方向下一条 c1')
check(gui._cubic_seam_step_target('c') is None, 'c0 负方向没有上一条')
check(gui._cubic_seam_step_target('R') is None, '非当前法线轴不响应')

print('A2. 跳过中间无效缝，找下一条有效切面')
gui.new_cubic_puzzle(4, 4, 4, 1)
arm_gap('c', 0)
_true_valid = gui.game.is_valid_gap
gui.game.is_valid_gap = lambda fam, line: fam == 'c' and line in (0, 2)
check(gui._cubic_seam_step_target('C') == 2,
      'c0 正方向跳过无效 c1，直接落到 c2')
gui.game.is_valid_gap = lambda fam, line: fam == 'c' and line in (0, 1)
check(gui._cubic_seam_step_target('C') == 1,
      '只有紧邻一条有效时落在紧邻那条')
gui.game.is_valid_gap = _true_valid
gui.new_cubic_puzzle(3, 3, 3, 1)
ref = arm_gap('c', 0)

print('B. 虚拟键盘法线轴：切面走、步数不走')
n0 = gui.step_count
h0 = len(gui.game_history.history)
locs0 = sorted(tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks)
check(gui._cubic_vk_six('C'), '虚拟键盘大写 C 受理切面步进')
check(gui.selected_gap == ('c', 1), f'切面切到 c1（{gui.selected_gap}）')
check(gui.step_count == n0, f'切面步进不算一步（{gui.step_count}）')
check(len(gui.game_history.history) == h0, '切面步进不写历史')
check(gui.selected_block is ref, '参考块对象保持不变')
check(any(b is ref and b.be_opted for b in gui.game.blocks),
      '新切面仍按同一参考块重选同侧组')
check(sorted(tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks) == locs0,
      '切面步进不移动任何块')
check(gui._cubic_vk_six('c'), '虚拟键盘小写 c 反向切回')
check(gui.selected_gap == ('c', 0), f'反向切回 c0（{gui.selected_gap}）')
check(gui.step_count == n0, '反向切面同样不算一步')
check(gui.selected_block is ref, '反向切面也保留同一参考块')

print('C. 虚拟键盘法线轴两端画成切面键，且不可用端变灰')
rects = gui._vk_build_layout()
check('cubic_C' in rects and 'cubic_c' in rects, '法线轴两键仍在坐标轴布局里')
gfx = pygame.Surface((gui.screen_width, gui.screen_height), pygame.SRCALPHA)
old = gui.screen
gui.screen = gfx
gui._vk_draw_cubic_buttons(rects, (-100, -100))
gui.screen = old
check(gui._cubic_seam_step_target('C') == 1, '正端当前可用')
check(gui._cubic_seam_step_target('c') is None, '负端当前不可用')

print('D. 盘面只画可用的切面键：同位置、同动作')
gui.draw_cubic_board()
steps = list(getattr(gui, '_cubic_seam_step_buttons', ()))
check(len(steps) == 1, f'c0 只有正方向有下一条，盘面只出一枚键（{len(steps)}）')
check(steps[0][0] == 'C', '留下的是正方向键')
check(steps[0][3] is True, '留下的键是可用态')
pos_rect = steps[0][1]
click(*pos_rect.center)
check(gui.selected_gap == ('c', 1), f'点盘面正端切到 c1（{gui.selected_gap}）')
check(gui.step_count == n0, '点盘面切面键不推块、不涨步数')
check(gui.selected_block is ref, '点盘面切面键仍保留参考块')

print('E. 没有下一条：该方向的键整枚隐藏')
gui.draw_cubic_board()
steps2 = list(getattr(gui, '_cubic_seam_step_buttons', ()))
check(len(steps2) == 1 and steps2[0][0] == 'c',
      f'c1 只保留负方向键，正端不显示（{[s[0] for s in steps2]}）')
check(not any(s[0] == 'C' for s in steps2), '无下一条的正端键已隐藏')
neg_rect = steps2[0][1]
click(*neg_rect.center)
check(gui.selected_gap == ('c', 0), '点盘面负端切回 c0（target 为 0 也不能被当成不可用）')

print('F. 没有参考块：只切切面，不误选隔壁组')
gui._cubic_clear_selection()
gui.selected_gap = ('c', 0)
check(gui._cubic_seam_step_target('C') == 1, '无参考块也能找到下一条缝')
check(gui._cubic_vk_six('C'), '无参考块仍可切面')
check(gui.selected_gap == ('c', 1), '切面照常前进')
check(not any(getattr(b, 'be_opted', False) for b in gui.game.blocks),
      '没有参考块时不自动选隔壁组')
check('请左键选要滑的滑块' in (gui.macro_notify_msg or ''),
      f'提示玩家重新选块（{gui.macro_notify_msg}）')

print('=' * 60)
print(f'结果：{"全部通过" if not _fail else "有失败"}'
      f'（{_ok[0]} 项通过，{len(_fail)} 项失败）')
if _fail:
    for f in _fail:
        print('  ·', f)
pygame.quit()
sys.exit(1 if _fail else 0)
