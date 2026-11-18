# -*- coding: utf-8 -*-
"""回归：三维六朝向 + 拖动旋转 + 缩放 + 相机分组存 config（§54 第 2 步）。

用户口径（2026-11-17）：**六个朝向都不该正对**。正对时实心 3×3×3 在屏幕上
就是一张二维 3×3，深度全靠猜；每面都带一点倾斜，该面仍是主体、邻面留细边。
另一条是「规整、朝向一致」：主面边缘必须仍沿屏幕横/竖，六张图同一套风格。

钉住这几条：
  A. 六朝向都倾斜（不正对），倾斜量一致，主面边沿与屏幕横竖对齐。
  B. 六张图彼此不同、每张都三面可见（深度读得出来），主面确实是它名下那一面。
  C. 拖动 = 旋转（内容跟手），极点有保护；旋转期间什么都不选中、不入历史。
  D. Ctrl+滚轮只动 cubic_zoom，二维 zoom / camera_x/y 一根毫毛都不动。
  E. 相机姿态（四元数）+ 缩放 + 拆分 + 视角序号进 config，重建三维局能套回来。

跑法：D:/python/python.exe test/_test_cubic_view_nav.py
"""
import hashlib
import json
import math
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

from engine.cubic_camera import (  # noqa: E402
    FACE_BASIS, FACE_VIEW_LABELS, CubicCamera, face_view_rotation)
from engine import cubic_view as cv  # noqa: E402

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


def solid(m, n, d):
    return {(r, c, dep) for r in range(m) for c in range(n) for dep in range(d)}


def angle_between(a, b):
    dot = min(1.0, max(-1.0, sum(x * y for x, y in zip(a, b))))
    return math.degrees(math.acos(dot))


def same_pose(a, b, tol=1e-9):
    """同一姿态（四元数 q 与 −q 等价）。"""
    d1 = max(abs(x - y) for x, y in zip(a.q, b.q))
    d2 = max(abs(x + y) for x, y in zip(a.q, b.q))
    return min(d1, d2) < tol


CUBE3 = solid(3, 3, 3)
_NORMAL_NAME = {(1, 0, 0): 'x+', (-1, 0, 0): 'x-',
                (0, 1, 0): 'y+', (0, -1, 0): 'y-',
                (0, 0, 1): 'z+', (0, 0, -1): 'z-'}
_EXPECT = ('z+', 'z-', 'x+', 'x-', 'y+', 'y-')


print('=' * 60)
print('A. 六朝向都不正对，且各自规整（主面边沿贴屏幕横竖）')
views = []
tilts = []
for i in range(6):
    cam = face_view_rotation(i)
    views.append(cam)
    check(not cam.is_axis_aligned(), f'{FACE_VIEW_LABELS[i]} 带倾斜（不正对）')
    tilts.append(angle_between(cam.view_axis(), FACE_BASIS[i][2]))
    # 主面所在平面的两条世界轴，投影到相机空间后必须**几乎**落在某条屏幕轴
    # 上（横/竖）。两轴偏角是复合旋转，边缘会有约 1–2° 的轻微斜度，这是斜视的
    # 正常代价；只要远小于「斜成 30° 的等轴测」，画面就读作规整。
    n = FACE_BASIS[i][2]
    in_plane = [k for k in range(3) if abs(n[k]) < 1e-9]
    ok = True
    worst = 0.0
    for k in in_plane:
        axis = tuple(1.0 if j == k else 0.0 for j in range(3))
        px, py, _ = cam.to_camera(axis)
        off = min(abs(px), abs(py))
        worst = max(worst, off)
        ok = ok and off <= 0.06
    check(ok, f'{FACE_VIEW_LABELS[i]} 主面边沿≈屏幕横竖（偏斜 {math.degrees(math.asin(min(1, worst))):.1f}°）',
          worst)
    near = cam.nearest_face_view()
    check(sum(a * b for a, b in zip(near.view_axis(), n)) > 0.9,
          f'{FACE_VIEW_LABELS[i]} 就近正对方向认的就是这一面')
check(all(abs(t - tilts[0]) < 3.0 for t in tilts),
      '六张图的倾斜量一致（同一套风格，不忽正忽斜）',
      [round(t, 2) for t in tilts])
check(0.0 < tilts[0] < 30.0, '倾斜量在合理的斜视档位内', tilts[0])

print('=' * 60)
print('B. 六张图：彼此不同、都三面可见、主面正确')


def _poly_area(pts):
    s = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


fps = {}
for i, cam in enumerate(views):
    faces = cv.collect_faces(CUBE3, cam, scale=26.0, origin=(180.0, 180.0),
                             gap=cv.DEFAULT_GAP)
    check(len(faces) == 81, f'{FACE_VIEW_LABELS[i]} 每块 3 面可见（共 81 面）',
          len(faces))
    areas = {}
    for f in faces:
        key = _NORMAL_NAME[tuple(int(round(v)) for v in f['normal'])]
        areas[key] = areas.get(key, 0.0) + _poly_area(f['pts'])
    best = max(areas, key=areas.get)
    check(best == _EXPECT[i], f'{FACE_VIEW_LABELS[i]} 主面正对着它（{best}）', best)
    sig = hashlib.sha1(repr([(f['axis'], f['sign'], round(f['depth'], 3))
                             for f in faces]).encode()).hexdigest()[:10]
    check(sig not in fps.values(), f'{FACE_VIEW_LABELS[i]} 投影与其它朝向不同')
    fps[i] = sig

print('=' * 60)
print('C. 拖动旋转（事件队列，真走 handle_events）')
from GUI import SliderGUI  # noqa: E402

pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_nav_')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
gui.config_path = os.path.join(gui.config_dir, 'config.json')
gui._readonly = False
gui.save_readonly_flag = False
gui.animation_enabled = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui.new_cubic_puzzle(3, 3, 3, 1)
gui.cubic_zoom = 1.0            # 清掉配置里带进来的缩放，单看「旋转不碰缩放」

board = (gui.screen_width // 2, gui.screen_height // 2)
cam0 = gui.cubic_camera
hist0 = len(getattr(gui.game_history, 'undo_stack', []) or [])

pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=board))
gui.handle_events()
check(getattr(gui, 'cubic_dragging', False), '棋盘上按下左键 = 开始旋转')
check(gui.selected_block is None and gui.selected_gap is None,
      '按下不选任何东西（旋转与选中互斥）')

pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION,
                                     pos=(board[0] + 100, board[1]), rel=(100, 0)))
gui.handle_events()
from engine.cubic_camera import arcball_axis_angle  # noqa: E402
_ax, _ang = arcball_axis_angle(board, (board[0] + 100, board[1]),
                               gui.screen_width, gui.screen_height)
_axis_world = tuple(_ax[0] * cam0.right_axis()[i] + _ax[1] * cam0.up_axis()[i]
                    + _ax[2] * cam0.view_axis()[i] for i in range(3))
want = cam0.spin(_axis_world, -_ang * gui.CUBIC_DRAG_SENSITIVITY)
check(same_pose(gui.cubic_camera, want),
      '右拖 100px → arcball（球面夹角，抓住的点跟手）')
check(angle_between(gui.cubic_camera.view_axis(), cam0.view_axis()) > 10,
      '视角确实转开了（不是没反应）', angle_between(gui.cubic_camera.view_axis(), cam0.view_axis()))

pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION,
                                     pos=(board[0] + 100, board[1] + 900),
                                     rel=(0, 900)))
gui.handle_events()
check(abs(gui.cubic_camera.view_axis()[1]) <= math.cos(
    math.radians(90.0 - gui.CUBIC_PITCH_LIMIT)) + 1e-9,
      '大幅下拖被极点保护挡住（不翻跟头）', gui.cubic_camera.view_axis())
check(gui.cubic_camera.view_axis()[1] != 0.0, '竖直拖动确实起效（不是完全没动）')

pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                                     pos=(board[0] + 100, board[1] + 900)))
gui.handle_events()
check(not gui.cubic_dragging, '松手结束旋转')
check(gui.selected_block is None and gui.selected_gap is None,
      '整段拖完什么都没选中')
check(gui.step_count == 0 and len(getattr(gui.game_history, 'undo_stack', []) or []) == hist0,
      '旋转不产生步数、不入历史', (gui.step_count, hist0))
check(gui.cubic_zoom == 1.0, '旋转不碰缩放')

print('=' * 60)
print('D. Ctrl+滚轮缩放（只动 cubic_zoom）')
_orig_mods = pygame.key.get_mods
pygame.key.get_mods = lambda: pygame.KMOD_CTRL
try:
    z0 = gui.cubic_zoom
    pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
    gui.handle_events()
    check(abs(gui.cubic_zoom - round(z0 * 1.1, 3)) < 1e-9,
          'Ctrl+滚轮上 → 三维缩放放大 10%', gui.cubic_zoom)
    check(gui.zoom == 1.0, '二维 zoom 一点没动')
    for _ in range(40):
        pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
    gui.handle_events()
    check(abs(gui.cubic_zoom - gui.CUBIC_ZOOM_RANGE[1]) < 1e-9,
          '缩放夹在上限', gui.cubic_zoom)
    for _ in range(40):
        pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    gui.handle_events()
    check(abs(gui.cubic_zoom - gui.CUBIC_ZOOM_RANGE[0]) < 1e-9,
          '缩放夹在下限', gui.cubic_zoom)
finally:
    pygame.key.get_mods = _orig_mods
gui.cubic_zoom = 1.0

print('=' * 60)
print('E. 1–6 / 0 键：切朝向与回斜视')
for i in range(6):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN,
                                         key=getattr(pygame, f'K_{i + 1}'),
                                         mod=0, unicode=str(i + 1), scancode=0))
    gui.handle_events()
    check(gui.cubic_view_index == i, f'按 {i + 1} → {FACE_VIEW_LABELS[i]}', gui.cubic_view_index)
    check(same_pose(gui.cubic_camera, face_view_rotation(i)),
          f'{FACE_VIEW_LABELS[i]} 到的姿态与六朝向定义一致（不跳变）')
pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_0,
                                    mod=0, unicode='0', scancode=0))
gui.handle_events()
check(gui.cubic_view_index is None and gui.cubic_view_label == '斜视',
      '按 0 回默认斜视', gui.cubic_view_label)
check(same_pose(gui.cubic_camera, CubicCamera.oblique_default()),
      '斜视姿态回到第 1 步那一档')

print('=' * 60)
print('F. 自由旋转不成为默认视角；1–6 选过的朝向才恢复')
gui.cubic_gap = 0.18
gui.cubic_camera = CubicCamera.oblique_default().spin((1.0, 0.0, 0.0), 12.0)
gui.cubic_view_label = '自由旋转'
gui.cubic_view_index = None
gui.save_config()
with open(os.path.join(gui.config_dir, 'config.json'), encoding='utf-8') as fh:
    cfg = json.load(fh)
cc = cfg.get('cubic_camera') or {}
check(set(('quat', 'zoom', 'gap')) <= set(cc), 'config 里有三维相机组', cc)
check(abs(cc.get('gap', -1) - 0.18) < 1e-9, '拆分值一起存')
check('zoom' in cfg and abs(cfg['zoom'] - 1.0) < 1e-9, '二维 zoom 仍按二维口径存')

gui.cubic_camera = CubicCamera.oblique_default()
gui.cubic_zoom = 1.0
gui.cubic_gap = 0.12
gui.load_last_state()
gui.new_cubic_puzzle(3, 3, 3, 1)
check(same_pose(gui.cubic_camera, CubicCamera.oblique_default(), tol=1e-6),
      '自由旋转不恢复，默认回到斜视参考姿态', gui.cubic_camera)
check(gui.cubic_view_label == '斜视', '标签也回到斜视', gui.cubic_view_label)
check(gui.cubic_view_index is None, '没有假装恢复某个朝向', gui.cubic_view_index)
check(abs(gui.cubic_gap - 0.18) < 1e-9, '拆分仍套回', gui.cubic_gap)

print('=' * 60)
print('F2. 明确选过朝向（1–6）才按朝向恢复')
gui.cubic_view_index = 2
gui.cubic_camera = face_view_rotation(2)
gui.cubic_view_label = FACE_VIEW_LABELS[2]
gui.save_config()
gui.load_last_state()
gui.new_cubic_puzzle(3, 3, 3, 1)
check(same_pose(gui.cubic_camera, face_view_rotation(2), tol=1e-6),
      '恢复选过的「右 +X」朝向', gui.cubic_camera)
check(gui.cubic_view_index == 2, '视角序号恢复', gui.cubic_view_index)

print('=' * 60)
print('G. 整帧：六朝向都画得出来')
gui.cubic_zoom = 1.0
sigs = set()
for i in range(6):
    gui._cubic_view(i)
    gui.draw_board()
    sig = hashlib.sha1(pygame.image.tostring(gui.screen, 'RGB')).hexdigest()[:10]
    check(True, f'{FACE_VIEW_LABELS[i]} 整帧绘制不抛异常')
    check(sig not in sigs, f'{FACE_VIEW_LABELS[i]} 整帧与其它朝向不同')
    sigs.add(sig)

print('=' * 60)
print(f'结果：{"全部通过" if not _fail else "有失败"}（{_ok[0]} 项通过，'
      f'{len(_fail)} 项失败）')
if _fail:
    for msg in _fail:
        print('  - ' + msg)
sys.exit(1 if _fail else 0)
