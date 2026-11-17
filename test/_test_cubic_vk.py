# -*- coding: utf-8 -*-
"""回归：三维「三轴六键」虚拟键盘 + 重画箭头（§54 第 4 步下半）。

钉住这几条（对应方案 §1「操作入口」与 §4 第 4 步）：
  A. 布局：三维态三行六键（c / d / r 各一对正负），全部落在面板内、互不重叠；
     箭头槽位按轴排行，二维那套 ↑↓←→ 不再出现。
  B. 箭头方向是「按当前相机现算」的：单位向量；正对镜头那条轴压成零向量；
     换个朝向后同一轴在屏幕上的方向必须变（这就是「重画箭头」）。
  C. 没选中时点六键 = 平移盘面：`cubic_pan` 变、块位置不变、步数不涨，
     并且渲染的 origin 真的按 pan 偏移（不是只改了个变量）。
  D. 有选中时点六键 = 推一步：与 r/R c/C d/D 同一口径（步数 +1、位置变）；
     推法必须沿切面，法向推被拒（提示带「推不动」）。
  E. 切回方形：布局回到 2 行 4 键，没有 cubic_* 键残留。

跑法：D:/python/python.exe test/_test_cubic_vk.py
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

import math  # noqa: E402
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
gui = SliderGUI(m=4, n=4, step=1)
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_vk_')
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

print('=' * 60)
print('A. 布局：三行六键')
gui.show_virtual_keyboard = True
rects = gui._vk_build_layout()
cubic_keys = sorted(k for k in rects if k.startswith('cubic_'))
check(cubic_keys == ['cubic_C', 'cubic_R', 'cubic_c', 'cubic_d', 'cubic_r',
                     'cubic_D'] or len(cubic_keys) == 6,
      f'六键齐备（{cubic_keys}）')
check(all(k in rects for k in ('cubic_c', 'cubic_C', 'cubic_d', 'cubic_D',
                               'cubic_r', 'cubic_R')), '三个轴的正负两键都在')
check('move_up' not in rects and 'move_left' not in rects,
      '三维态不再出现二维四向键')
row_ys = sorted({rects['cubic_' + c].y for c in 'cdr'})
check(len(row_ys) == 3, f'三个轴各占一行（y={row_ys}）')
check(all(gui.vk_panel_rect.contains(rects[k]) for k in cubic_keys),
      '六键都在面板矩形之内')
# 互不重叠
pairs = 0
overlaps = 0
for i, a in enumerate(cubic_keys):
    for b in cubic_keys[i + 1:]:
        pairs += 1
        if rects[a].colliderect(rects[b]):
            overlaps += 1
check(pairs == 15 and overlaps == 0, f'六键两两不重叠（{overlaps} 处重叠）')
check(gui._vk_direction_rows() == 3, '方向区按三行算（面板高度随之变高）')

print('B. 箭头按相机现算（不是静态图标）')
dirs = gui._cubic_vk_dirs()
check(len(dirs) == 6, '六个方向都有屏幕向量')
for letter, (dx, dy) in dirs.items():
    norm = math.hypot(dx, dy)
    check(abs(norm - 1.0) < 1e-6 or norm == 0.0,
          f'{letter} 是单位向量或零（{norm:.4f}）')
# 真正正对 +Z 的相机（六朝向都带 14° 倾斜，所以取原始 yaw/pitch=0 的相机来验）
from engine.cubic_camera import CubicCamera  # noqa: E402
gui.cubic_camera = CubicCamera.from_yaw_pitch(0.0, 0.0)
front_z = gui._cubic_screen_dir((0.0, 0.0, 1.0))
check(abs(math.hypot(*front_z)) < 1e-6,
      f'轴正对镜头时屏幕向量为零（{front_z}，画成空心圈而不是瞎指一个方向）')
check(gui._cubic_screen_dir((0.0, 0.0, -1.0)) == (0.0, 0.0), '背对镜头同样是零向量')
# 六朝向带 14° 倾斜，所以实际游戏里 Z 轴永远不是零（箭头始终可读）
gui._cubic_view(0)
before = dict(gui._cubic_vk_dirs())
gui._cubic_view_oblique()
gui.draw_cubic_board()
after = gui._cubic_vk_dirs()
changed = sum(1 for k in before
              if math.hypot(after[k][0] - before[k][0], after[k][1] - before[k][1]) > 1e-3)
check(changed >= 4, f'换朝向后多数箭头方向变了（{changed}/6 条变了）')

print('C. 没选中时点六键 = 平移盘面')
gui._cubic_view(0)
gui._cubic_clear_selection()
gui.draw_cubic_board()
gui.cubic_pan = [0.0, 0.0]
base_origin = gui._cubic_scene['origin']
base_locs = sorted(tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks)
n0 = gui.step_count
pan_before = list(gui.cubic_pan)
clicked = gui._cubic_vk_six('C')          # 未选中 → 应走平移
check(clicked is True, '未选中点六键被受理（走平移，不是提示先选中）')
check(gui.cubic_pan != pan_before, f'平移偏移变了（{pan_before} → {gui.cubic_pan}）')
check(sorted(tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks) == base_locs,
      '平移不动逻辑坐标（块位置不变）')
check(gui.step_count == n0, f'平移不算一步（步数仍 {n0}）')
gui.draw_cubic_board()
new_origin = gui._cubic_scene['origin']
check(abs((new_origin[0] - base_origin[0]) - gui.cubic_pan[0]) < 1e-6
      and abs((new_origin[1] - base_origin[1]) - gui.cubic_pan[1]) < 1e-6,
      f'渲染 origin 真按 pan 偏移（{base_origin} → {new_origin}）')
# 负方向是同一个偏移的反向
gui.cubic_pan = [0.0, 0.0]
gui._cubic_vk_six('C')
plus = list(gui.cubic_pan)
gui.cubic_pan = [0.0, 0.0]
gui._cubic_vk_six('c')
minus = list(gui.cubic_pan)
check(abs(plus[0] + minus[0]) < 1e-6 and abs(plus[1] + minus[1]) < 1e-6,
      f'同轴正负两键平移方向相反（{plus} / {minus}）')
# 偏移会被夹住，推不丢
for _ in range(40):
    gui._cubic_vk_six('C')
check(abs(gui.cubic_pan[0]) <= 0.56 * max(gui.screen_width, gui.screen_height),
      f'反复平移有夹紧上限（{gui.cubic_pan}）')

print('D. 有选中时点六键 = 推一步')
gui.cubic_pan = [0.0, 0.0]
gui._cubic_view(0)
gui.draw_cubic_board()
gui._cubic_clear_selection()


def click(pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))
    gui.handle_events()


face = gui._cubic_scene['faces'][-1]
pt = (int(sum(p[0] for p in face['pts']) / 4.0),
      int(sum(p[1] for p in face['pts']) / 4.0))
click(pt)
click(pt)
check(any(b.be_opted for b in gui.game.blocks), '双击选出一组（为推做准备）')
fam = gui.selected_gap[0]
n1 = gui.step_count
locs1 = sorted(tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks)
used = None
for cand in [f for f in ('c', 'd', 'r') if f != fam]:
    for letter in (cand, cand.upper()):
        ok = gui._cubic_vk_six(letter)
        if ok and gui.step_count == n1 + 1:
            used = letter
            break
    if used:
        break
check(used is not None, f'沿切面 {fam} 用六键能推一步（{gui.macro_notify_msg}）')
check(gui.step_count == n1 + 1, f'六键推一步步数 +1（{gui.step_count}）')
check(sorted(tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks) != locs1,
      '六键推一步真的挪了块')
# 法向推（沿切面法向）被拒
gui._cubic_vk_six(fam if used == fam.upper() else fam.upper())
check('推不动' in (gui.macro_notify_msg or '') or gui.step_count == n1 + 1,
      f'法向推被拒/或本来就推得动（提示：{gui.macro_notify_msg}）')

print('E. 切回方形：布局回到二维四向')
gui.new_puzzle(4, 4, 1)
gui.show_virtual_keyboard = True
rects2 = gui._vk_build_layout()
check(not any(k.startswith('cubic_') for k in rects2), '方形态没有 cubic_* 键残留')
check(('move_up' in rects2) and ('move_left' in rects2) and ('move_right' in rects2)
      and ('move_down' in rects2), '方形态四向键照旧')
check(len({rects2['move_up'].y, rects2['move_left'].y}) == 2, '方形态仍是两行')

print('=' * 60)
if _fail:
    print(f'结果：{_ok[0]} 项通过，{len(_fail)} 项失败')
    for m in _fail:
        print('  ·', m)
    sys.exit(1)
print(f'结果：全部通过（{_ok[0]} 项通过，0 项失败）')
