# -*- coding: utf-8 -*-
"""回归：三维画面大小只由缩放决定，旋转不许改比例（用户 2026-11-17 实测「忽大忽小」）。

钉住：
  A. 转一圈（0/20/40/60/80/100°）scale 一模一样——投影包围盒会变，比例不许变。
  B. build_scene 走 stable_frame（包围球定比例），不是 fit_view。
  C. zoom 线性决定 scale：2 倍 zoom = 2 倍 scale。
  D. 右侧「缩放」滑条在三维态改的是 cubic_zoom，二维 zoom 一根毫毛不动；
     滑条矩形与滑钮位置跟 cubic_zoom 走。

跑法：D:/python/python.exe test/_test_cubic_framing.py
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

from engine import cubic_view as cv  # noqa: E402
from engine.cubic_camera import CubicCamera  # noqa: E402

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


CUBE3 = {(r, c, d) for r in range(3) for c in range(3) for d in range(3)}

print('=' * 60)
print('A. 旋转不改比例')
cam = CubicCamera.oblique_default()
scales = []
spans = []
for deg in (0, 20, 40, 60, 80, 100):
    scene = cv.build_scene(CUBE3, cam.spin((0.0, 1.0, 0.0), deg), 1000, 600,
                           margin=64, zoom=1.0, gap=0.12)
    xs = [p[0] for f in scene['faces'] for p in f['pts']]
    ys = [p[1] for f in scene['faces'] for p in f['pts']]
    scales.append(round(scene['scale'], 6))
    spans.append((round(max(xs) - min(xs)), round(max(ys) - min(ys))))
check(len(set(scales)) == 1, f'六个朝向 scale 完全相同（{set(scales)}）')
check(len(set(spans)) > 1,
      f'屏幕跨度确实随朝向变（说明变的是投影而不是比例）：{spans}')

print('B. 装画面走 stable_frame')
frame = cv.stable_frame(CUBE3, cam, 1000, 600, margin=64, zoom=1.0, gap=0.12)
scene = cv.build_scene(CUBE3, cam, 1000, 600, margin=64, zoom=1.0, gap=0.12)
check(abs(frame[0] - scene['scale']) < 1e-9, 'build_scene 的 scale = stable_frame 的 scale')
check(abs(frame[1][0] - scene['origin'][0]) < 1e-9 and
      abs(frame[1][1] - scene['origin'][1]) < 1e-9, 'origin 也同源')

print('C. zoom 线性决定大小')
for z, expect in ((0.5, 0.5), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0)):
    s = cv.build_scene(CUBE3, cam, 1000, 600, margin=64, zoom=z, gap=0.12)['scale']
    check(abs(s / frame[0] - expect) < 1e-9, f'zoom {z} → scale ×{expect}', extra=f'{s}')

print('D. 右侧缩放滑条改的是三维缩放')
from GUI import SliderGUI  # noqa: E402

pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_frame_')
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
gui.draw_right_panel()
check(gui.zoom_slider_rect is not None, '右侧面板给了缩放滑条矩形')
zoom2d0 = gui.zoom
gui._update_zoom_slider_from_mouse(gui.zoom_slider_rect.top)
check(abs(gui.cubic_zoom - gui.CUBIC_ZOOM_RANGE[1]) < 1e-9,
      f'拖到顶 = 最大缩放（{gui.cubic_zoom}）')
check(gui.zoom == zoom2d0, '二维 zoom 不动')
gui._update_zoom_slider_from_mouse(gui.zoom_slider_rect.bottom)
check(abs(gui.cubic_zoom - gui.CUBIC_ZOOM_RANGE[0]) < 1e-9,
      f'拖到底 = 最小缩放（{gui.cubic_zoom}）')
check(gui.zoom == zoom2d0, '二维 zoom 仍然不动')

gui._update_zoom_slider_from_mouse(gui.zoom_slider_rect.top)
gui.draw_cubic_board()
gui.draw_right_panel()
check(abs(gui.cubic_zoom - gui.CUBIC_ZOOM_RANGE[1]) < 1e-9, '再拖回顶仍是最大')
big = cv.build_scene(gui.game.blocks, gui.cubic_camera, gui.screen_width,
                     gui.screen_height, margin=64, zoom=gui.cubic_zoom,
                     gap=gui.cubic_gap)['scale']
gui._update_zoom_slider_from_mouse(gui.zoom_slider_rect.bottom)
gui.draw_cubic_board()
small = cv.build_scene(gui.game.blocks, gui.cubic_camera, gui.screen_width,
                       gui.screen_height, margin=64, zoom=gui.cubic_zoom,
                       gap=gui.cubic_gap)['scale']
check(big > small * 5, f'滑条从顶到底，scale 明显变小（{big:.1f} → {small:.1f}）')

print('=' * 60)
if _fail:
    print(f'结果：{_ok[0]} 项通过，{len(_fail)} 项失败')
    for m in _fail:
        print('  ·', m)
    sys.exit(1)
print(f'结果：全部通过（{_ok[0]} 项通过，0 项失败）')
