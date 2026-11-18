# -*- coding: utf-8 -*-
"""三维：配置持久化（局尺寸/平移）+ 切面整块矩形 + 平移手势。

对应 2026-11-18 用户报的三条：
  1. 缝隙应该是一张矩形平面（之前按格拼，形状被改坏了）
  2. config.json 没存三维滑块的信息（重启后三维局丢了）
  3. 没法移动视角（只能转）

判据
  A. seam_plane_rect 是**一张矩形**：四角共面、跨度=整盘、面积=(m-gap)*(n-gap)，
     且盘面被打散（有格子没有块）时它仍然是完整的矩形（不缩水、不缺口）。
  B. save_config 落盘 cubic_puzzle（m/n/d/step）与 cubic_pan。
  C. 只有 config、没有 temp_history 时，load_last_state 仍能按 config 重建三维局，
     且分榜键带层数（不再报「缺 depth」）。
  D. 平移：拖动改变 cubic_pan、夹紧在半屏内；_cubic_pan_center 归零。

跑法：D:/python/python.exe test/_test_cubic_config_state.py
"""
import json
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame                                       # noqa: E402
from GUI import SliderGUI                           # noqa: E402
from engine import cubic_pick as cp                 # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=None):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg}' + (f'  {extra}' if extra else ''))


def make_gui(m=4, n=4, step=1):
    gui = SliderGUI(m=m, n=n, step=step)
    d = tempfile.mkdtemp(prefix='gs_cubic_state_')
    gui.config_dir = d
    gui.config_path = os.path.join(d, 'config.json')
    gui.temp_history_path = os.path.join(d, 'temp_history.json')
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui._cubic_camera_prefs = {}
    gui._cubic_puzzle_prefs = None
    gui._cubic_pan_prefs = None
    return gui


print('=' * 60)
print('A. 切面是一张整块矩形')
g = make_gui()
g.new_cubic_puzzle(3, 3, 3, 1)
rect = cp.seam_plane_rect('r', 1, g.game.blocks, gap=0.18)
check(len(rect) == 4, '返回四角', len(rect))
axis = cp.FAMILY_TO_WORLD_AXIS['r']
a, b = [i for i in range(3) if i != axis]
check(all(abs(p[axis] - 2.0) < 1e-9 for p in rect), '四角都在同一张平面上')
span_a = max(p[a] for p in rect) - min(p[a] for p in rect)
span_b = max(p[b] for p in rect) - min(p[b] for p in rect)
expect = 3.0 + 0.18       # 铺满包围盒横截面（两侧各多半格 gap）
check(abs(span_a - expect) < 1e-9 and abs(span_b - expect) < 1e-9,
      f'跨度覆盖整盘（{span_a:.2f}×{span_b:.2f}，应 {expect:.2f}）')
# 面积（平面内两轴叉积）
area = 0.0
for i in range(4):
    p0, p1 = rect[i], rect[(i + 1) % 4]
    area += p0[a] * p1[b] - p1[a] * p0[b]
check(abs(abs(area) / 2.0 - expect ** 2) < 1e-9, f'面积 = 切面整片（{abs(area) / 2:.4f}）')

# 打散后仍是一整块：只留一个块（占据角落），矩形范围不该跟着缩
blk = g.game.blocks[0]
cp_bak = g.game.blocks
try:
    g.game.blocks = [blk]
    rect_loose = cp.seam_plane_rect('r', 1, g.game.blocks, gap=0.18)
    check(rect_loose and len(rect_loose) == 4, '只剩一块时仍给出完整的矩形（不缺格）')
finally:
    g.game.blocks = cp_bak

print('=' * 60)
print('B. save_config 落盘三维局信息与平移')
g.new_cubic_puzzle(3, 3, 3, 1)
g.cubic_pan = [12.0, -8.0]
g.cubic_follow_centroid = False          # 手动平移过 → 跟随已暂停，要能原样存回
g.save_config()
with open(g.config_path, 'r', encoding='utf-8') as f:
    cfg = json.load(f)
cpz = cfg.get('cubic_puzzle') or {}
check(cpz.get('m') == 3 and cpz.get('n') == 3 and cpz.get('d') == 3
      and cpz.get('step') == 1, 'cubic_puzzle 写下 m/n/d/step', cpz)
check(cfg.get('cubic_pan') == [12.0, -8.0], 'cubic_pan 写下手动平移', cfg.get('cubic_pan'))
check(cfg.get('cubic_follow_centroid') is False, '跟随质心的暂停状态也写盘',
      cfg.get('cubic_follow_centroid'))
check(isinstance(cfg.get('cubic_camera'), dict), 'cubic_camera 仍在（相机组没被挤掉）')

print('=' * 60)
print('C. 只有 config：按配置重建三维局（不再「缺 depth」崩）')
g2 = make_gui()
g2.config_dir = g.config_dir
g2.config_path = g.config_path
g2.temp_history_path = os.path.join(g.config_dir, 'nope_history.json')
g2._cubic_camera_prefs = {}
g2.load_last_state()
check(getattr(g2, 'cubic_mode', False), '重建后是三维局')
check(int(getattr(g2, 'current_depth', 0)) == 3, '层数回来了（3）', getattr(g2, 'current_depth', None))
key = g2._current_puzzle_key()
check('cubic3*3*3' in key, f'分榜键带层数（{key}）')
check(list(map(float, g2.cubic_pan)) == [12.0, -8.0], '平移从 config 恢复', g2.cubic_pan)
check(g2.cubic_follow_centroid is False, '跟随暂停状态也从 config 恢复',
      g2.cubic_follow_centroid)

print('=' * 60)
print('D. 平移与居中（方案 §2.2：六键平移，手动平移暂停跟随，居中恢复）')
g3 = make_gui()
g3.new_cubic_puzzle(3, 3, 3, 1)
g3.cubic_pan = [0.0, 0.0]
g3.cubic_follow_centroid = True
panned = False
for letter in ('r', 'R', 'c', 'C', 'd', 'D'):
    if g3._cubic_pan_by(letter, notify=False):
        panned = True
        break
check(panned, '没选中时六键能平移（至少一条不与镜头正对的轴）')
check(g3.cubic_pan != [0.0, 0.0], f'平移真的改了偏移（{g3.cubic_pan}）')
check(g3.cubic_follow_centroid is False, '手动平移后暂停「跟随质心」')
g3.cubic_pan = [10 ** 9, -10 ** 9]      # 越界：验证夹紧逻辑不靠外部绕过
g3._cubic_pan_by('r', notify=False)
lim = 0.55 * max(g3.screen_width, g3.screen_height)
check(abs(g3.cubic_pan[0]) <= lim + 1e-6 and abs(g3.cubic_pan[1]) <= lim + 1e-6,
      '平移被夹在半屏内', (g3.cubic_pan, lim))
g3.center_map()      # 菜单「编辑 → 居中」的入口
check(g3.cubic_pan == [0.0, 0.0], '居中把平移归零', g3.cubic_pan)
check(g3.cubic_follow_centroid is True, '居中恢复「跟随质心」')

print('E. 跟随质心：质心确实投影到屏幕中心')
g4 = make_gui()
g4.new_cubic_puzzle(3, 3, 3, 1)
from engine import cubic_view as cv            # noqa: E402
locs = [tuple(int(v) for v in b.location[:3]) for b in g4.game.blocks]
cen = (sum(p[1] for p in locs) / len(locs) + 0.5,
       sum(p[2] for p in locs) / len(locs) + 0.5,
       sum(p[0] for p in locs) / len(locs) + 0.5)
scene = cv.build_scene(g4.game.blocks, g4.cubic_camera,
                       g4.screen_width, g4.screen_height,
                       margin=64, zoom=1.0, gap=g4.cubic_gap, center=cen)
sx, sy, _ = cv.project_point(cen, g4.cubic_camera, scene['scale'], scene['origin'])
check(abs(sx - g4.screen_width / 2.0) < 1e-6 and abs(sy - g4.screen_height / 2.0) < 1e-6,
      f'质心落在屏幕中心（{sx:.1f},{sy:.1f}）',
      (sx, sy, g4.screen_width / 2.0, g4.screen_height / 2.0))

print('=' * 60)
total = _ok[0] + len(_fail)
print(f'结果：{"全部通过" if not _fail else "有失败"}（{_ok[0]} 项通过，{len(_fail)} 项失败）／共 {total} 项')
if _fail:
    for f in _fail:
        print('  -', f)
sys.exit(1 if _fail else 0)
