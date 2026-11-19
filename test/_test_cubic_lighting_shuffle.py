# -*- coding: utf-8 -*-
"""三维打光与打乱相机冻结的护栏（2026-11-19）。

A. 打光：任意朝向的三个可见面都必须有可读亮度（不再「一半纯暗」），
   同时保留顶 / 前 / 侧的层次；旧 SHADE 的 0.5 背光面是本次回归的对象。
B. 打乱：三维打乱会话期间取景中心必须冻结；不能跟随质心逐帧追，
   否则 AnchorPlanner 的亚格残余会被放大成持续抖动。
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from engine import cubic_view  # noqa: E402
from engine.cubic_camera import CubicCamera  # noqa: E402

FAILED = []
PASSED = [0]


def check(ok, label, extra=None):
    if ok:
        PASSED[0] += 1
        print(f"  ok: {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL: {label}" + (f"  <- {extra}" if extra is not None else ''))


def make_gui():
    cfg = tempfile.mkdtemp(prefix='cubic_light_')
    g = SliderGUI(m=3, n=3, step=1)
    g.config_dir = cfg
    g.config_path = os.path.join(cfg, 'config.json')
    g.temp_history_path = os.path.join(cfg, 'temp_history.json')
    g.tutorial_active = False
    pygame.display.set_mode((g.screen_width, g.screen_height))
    g.screen = pygame.display.get_surface()
    g._cubic_camera_prefs = {}
    return g


def visible_shades(cam):
    faces = cubic_view.collect_faces(
        [(0, 0, 0)], cam, scale=30.0, origin=(200.0, 200.0))
    return [f['shade'] for f in faces]


print('=' * 60)
print('A. 打光：三个可见面都亮，且保留层次')
cam = CubicCamera.oblique_default()
s = visible_shades(cam)
check(len(s) == 3, '默认斜视恰好三个可见面', s)
check(min(s) >= 0.66, '最暗可见面不低于环境光底线（不再纯暗）', min(s))
check(max(s) - min(s) >= 0.12, '三个可见面仍有可读层次（不是糊成一片）',
      max(s) - min(s))
check(len({round(v, 4) for v in s}) == 3, '三面是三级明暗', s)

for i in range(6):
    cam_i = CubicCamera.from_view_angles(i)
    vals = visible_shades(cam_i)
    check(len(vals) == 3, f'朝向 {i}：三个可见面', vals)
    check(min(vals) >= 0.66, f'朝向 {i}：最暗面仍可读', round(min(vals), 3))
    check(max(vals) - min(vals) >= 0.12,
          f'朝向 {i}：三面仍有层次', round(max(vals) - min(vals), 3))

print('=' * 60)
print('B. 三维打乱：相机取景中心冻结')
g = make_gui()
g.cubic_mode = True
g.cubic_follow_centroid = True
g.cubic_gap = 0.12
g.new_cubic_puzzle(3, 3, 3, 1)
g._cubic_view_oblique()
g.draw_board()
_origin0 = g._cubic_scene['origin']

# 模拟「打乱会话已开始、第一步已把盘面推到新位置」：先捕获中心，再挪块。
g._shuffle_demo_active = True
g._cubic_capture_shuffle_center()
for b in g.game.blocks[:9]:
    b.location[0] += 1
g.draw_board()
_origin1 = g._cubic_scene['origin']
check(abs(_origin1[0] - _origin0[0]) <= 1.0
      and abs(_origin1[1] - _origin0[1]) <= 1.0,
      '打乱期间挪块后取景 origin 不跟着跳',
      (_origin0, _origin1))

g._shuffle_demo_active = False
g.draw_board()
_origin2 = g._cubic_scene['origin']
check(abs(_origin2[0] - _origin1[0]) > 1.0
      or abs(_origin2[1] - _origin1[1]) > 1.0,
      '打乱结束后跟随质心恢复（origin 会重新对准新质心）',
      (_origin1, _origin2))

print('=' * 60)
print('B2. 打乱缩放：右下角数值跟 cubic_zoom，收尾不再二次改变块大小')
g2 = make_gui()
g2.cubic_mode = True
g2.cubic_follow_centroid = True
g2.new_cubic_puzzle(3, 3, 3, 1)
g2.draw_board()
g2.draw_status_bar()
_base = float(g2._cubic_scene['scale'])
check(abs(_base - float(g2._cubic_base_scale)) < 1e-9,
      '首帧记下整局固定比例', (g2._cubic_base_scale, _base))
check(g2._status_zoom_text == '缩放：100%',
      '三维右下角显示 cubic_zoom（100%）', g2._status_zoom_text)

# 正常态把一块挪远：如果每帧按包围盒重算，scale 会变小；现在必须固定。
g2.game.blocks[0].location[0] += 4
g2.draw_board()
check(abs(float(g2._cubic_scene['scale']) - _base) < 1e-9,
      '正常态块移动不再改变块大小', g2._cubic_scene['scale'])

g2.cubic_zoom = 1.25
g2.draw_board()
g2.draw_status_bar()
check(g2._status_zoom_text == '缩放：125%',
      '拖三维缩放后右下角数值跟着变', g2._status_zoom_text)
check(abs(float(g2._cubic_scene['scale']) - _base * 1.25) < 1e-9,
      '缩放只乘固定比例（125%）', g2._cubic_scene['scale'])

# 打乱开始 + 中途缩放 + 结束，三个时刻的块大小必须一致。
g2._shuffle_demo_active = True
g2._cubic_capture_shuffle_center()
g2.draw_board()
_shuffle_scale = float(g2._cubic_scene['scale'])
check(abs(_shuffle_scale - _base * 1.25) < 1e-9,
      '打乱开始时沿用同一比例', _shuffle_scale)
g2.game.blocks[1].location[1] += 3
g2.draw_board()
check(abs(float(g2._cubic_scene['scale']) - _shuffle_scale) < 1e-9,
      '打乱中途盘面胀大也不缩放', g2._cubic_scene['scale'])
g2.cubic_zoom = 1.5
g2.draw_board()
g2.draw_status_bar()
check(abs(float(g2._cubic_scene['scale']) - _base * 1.5) < 1e-9,
      '打乱中缩放按同一固定比例生效', g2._cubic_scene['scale'])
check(g2._status_zoom_text == '缩放：150%',
      '打乱中右下角数值同步', g2._status_zoom_text)
g2._shuffle_demo_active = False
g2.draw_board()
check(abs(float(g2._cubic_scene['scale']) - _base * 1.5) < 1e-9,
      '打乱结束后块大小不再改变', g2._cubic_scene['scale'])

print('=' * 60)
print('C. 三维打乱：AnchorPlanner 防偏移真的接上了')
g = make_gui()
g.cubic_mode = True
g.cubic_gap = 0.12
g.new_cubic_puzzle(3, 3, 3, 1)

def _centroid(blocks):
    cs = [cubic_view.block_center(tuple(int(v) for v in b.location[:3]), 0.0)
          for b in blocks]
    return tuple(sum(c[i] for c in cs) / len(cs) for i in range(3))

def _vlen(v):
    return sum(x * x for x in v) ** 0.5

for trial in range(3):
    _before = _centroid(g.game.blocks)
    g.game.shuffle(40, 1, bias=0.0, min_score=None, record=[])
    _after = _centroid(g.game.blocks)
    drift = _vlen(tuple(_after[i] - _before[i] for i in range(3)))
    check(drift <= 1.01, f'第 {trial + 1} 次打乱重心漂移 ≤ 1 格',
          round(drift, 3))

print('=' * 60)
if FAILED:
    print('结果：FAIL ' + str(FAILED))
    sys.exit(1)
print(f'结果：全部通过（{PASSED[0]} 项）')
