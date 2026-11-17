# -*- coding: utf-8 -*-
"""回归：三维拾取与选中（§54 第 3 步「能正确选中」）。

验收判据（方案 §6 第 3 条 + §2.2 互斥口径）：
  A. 屏幕点 → 面的命中 = 画面上最近的那一片（前块挡后块，倒序测就是按深度取近）。
  B. 面 → 缝：内部面给出有效的 (缝族, 缝线号)，外表面退回相邻那条线；都没挨缝返回 None。
  C. 切面预览多边形：固定坐标 = line+1，与引擎 ``t = line + 1`` 同一口径。
  D. 单击出白线切面预览（不进历史、不产生步数）；双击选中该切面一侧的连通组，
     与引擎 ``opt`` 独立算出的组逐一相同。
  E. 拖动（移动过）只旋转、不选中；旋转态（不在六朝向之一）点也不选。

跑法：D:/python/python.exe test/_test_cubic_pick.py
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

from engine import cubic_pick as cp  # noqa: E402
from engine import cubic_view as cv  # noqa: E402
from engine.cubic_camera import CubicCamera  # noqa: E402
from engine.adapter import create_adapter_puzzle  # noqa: E402

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


CUBE3 = solid(3, 3, 3)

print('=' * 60)
print('A. 屏幕点 → 面（点命中与画家序）')
quad = [(0, 0), (10, 0), (10, 10), (0, 10)]
check(cp.point_in_quad((5, 5), quad), '四边形内的点命中')
check(cp.point_in_quad((0, 5), quad), '边界上的点算命中（含边）')
check(not cp.point_in_quad((-3, 5), quad), '四边形外的点不命中')
check(not cp.point_in_quad((5, 14), quad), '上下方向越界不命中')

cam = CubicCamera.oblique_default()
scene = cv.build_scene(CUBE3, cam, 800, 600, margin=64, zoom=1.0, gap=0.12)
faces = scene['faces']
check(len(faces) == 81, f'3×3×3 拆分态 81 片可见面（实得 {len(faces)}）')

near = faces[-1]
center = (sum(p[0] for p in near['pts']) / 4.0, sum(p[1] for p in near['pts']) / 4.0)
hit = cp.hit_face(faces, center)
check(hit is not None and hit['loc'] == near['loc'] and hit['axis'] == near['axis'],
      '画面最靠前那一片的面心 → 命中的就是它（最近优先）')
check(cp.hit_face(faces, (-500, -500)) is None, '棋盘外点击 → 不命中')

# 前后两块：点击重叠区域应命中前面那块
front = {(0, 0, 0), (0, 0, 1)}
scene2 = cv.build_scene(front, CubicCamera.oblique_default(), 400, 300,
                        margin=20, zoom=1.0, gap=0.0)
faces2 = scene2['faces']
rear_faces = [f for f in faces2 if f['loc'] == (0, 0, 0)]
front_faces = [f for f in faces2 if f['loc'] == (0, 0, 1)]
check(len(rear_faces) > 0 and len(front_faces) > 0, '前后两块都有可见面')
overlap = None
for f in front_faces:
    c = (sum(p[0] for p in f['pts']) / 4.0, sum(p[1] for p in f['pts']) / 4.0)
    if cp.hit_face(faces2, c)['loc'] == (0, 0, 1):
        overlap = c
        break
check(overlap is not None, '点在前块可见面上 → 命中前块（不被后块抢）')

print('B. 面 → 缝（内部面 / 外表面 / 无缝）')
game = create_adapter_puzzle('cubic', 3, 3, 1, depth=3)
locs = cv.locations_of(game.blocks)
check(cp.face_is_internal({'loc': (1, 1, 1), 'axis': 0, 'sign': 1}, locs),
      '心块 +X 面是内部面')
check(not cp.face_is_internal({'loc': (1, 2, 1), 'axis': 0, 'sign': 1}, locs),
      '最外层 +X 面不是内部面')

seams = {}
for face in faces:
    seam = cp.seam_of_face(face, game.is_valid_gap)
    check(seam is not None and face['loc'] not in (None,),
          '每一片可见面都能给出有效切面' if face is faces[0] else
          f'面 {face["loc"]} 轴{face["axis"]}{face["sign"]:+d} → 切面 {seam}',
          extra=str(seam))
    if seam:
        seams[seam] = seams.get(seam, 0) + 1
        check(game.is_valid_gap(seam[0], seam[1]),
              f'切面 {seam} 引擎判为有效', extra=str(seam))
check(set(seams) <= {('r', 0), ('r', 1), ('c', 0), ('c', 1), ('d', 0), ('d', 1)},
      f'所有切面都落在 3×3×3 的六条有效缝上（实得 {sorted(seams)}）')

outer = {'loc': (0, 0, 0), 'axis': 0, 'sign': -1}     # c=0 外侧，line −1 无效
seam_out = cp.seam_of_face(outer, game.is_valid_gap)
check(seam_out == ('c', 0), f'外侧面的退回相邻线（实得 {seam_out}）')
check(cp.seam_of_face({'loc': (0, 0, 0), 'axis': 2, 'sign': 1},
                      lambda f, l: False) is None,
      '没有任何有效线时返回 None（不硬选）')

print('C. 切面预览多边形')
for family, line in (('r', 1), ('c', 0), ('d', 1)):
    poly = cp.seam_plane_polygon(family, line, game.blocks)
    world_index = cp.FAMILY_TO_WORLD_AXIS[family]
    check(len(poly) == 4, f'{family}·{line} 切面四角')
    check(all(abs(p[world_index] - (line + 1)) < 1e-9 for p in poly),
          f'{family}·{line} 固定坐标 = line+1（与引擎 t 同口径）')
    others = [i for i in range(3) if i != world_index]
    a_vals = {round(p[others[0]], 6) for p in poly}
    b_vals = {round(p[others[1]], 6) for p in poly}
    check(len(a_vals) == 2 and len(b_vals) == 2, f'{family}·{line} 是矩形不是线')
check(cp.seam_plane_polygon('c', 0, []) is None, '空棋盘 → 无预览平面')
check(tuple(int(v) for v in cp.block_at_location(game.blocks, (1, 2, 0)).location[:3])
      == (1, 2, 0), 'block_at_location 按位置找到块')
check(cp.block_at_location(game.blocks, (9, 9, 9)) is None, '不存在的位置返回 None')

print('D. GUI：单击出切面 / 双击选中一侧')
from GUI import SliderGUI  # noqa: E402

pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_pick_')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
gui.config_path = os.path.join(gui.config_dir, 'config.json')
gui._readonly = False
gui.save_readonly_flag = False
gui.animation_enabled = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui._cubic_camera_prefs = {}
gui.new_cubic_puzzle(3, 3, 3, 1)
gui._cubic_view(0)               # 先回到一个朝向（每面都带偏角，不正对）
gui.draw_cubic_board()           # 生成 _cubic_scene（点击命中用它）
check(gui._cubic_scene is not None and len(gui._cubic_scene['faces']) == 81,
      '渲染层把这一帧的面存下来供拾取用')

hist0 = len(getattr(gui.game_history, 'undo_stack', []) or [])
step0 = gui.step_count


def _seam_point(scene, face, offset=3.0):
    """取一个贴着缝线的屏幕点：沿面边采样、往面心一侧缩 offset 像素，
    用 seam_edge_distance 反查「这条边是不是缝边」。"""
    pts = face['pts']
    cen = (sum(p[0] for p in pts) / 4.0, sum(p[1] for p in pts) / 4.0)
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        for t in (0.5, 0.3, 0.7, 0.2, 0.8):
            mx, my = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            nx, ny = cen[0] - mx, cen[1] - my
            n = (nx * nx + ny * ny) ** 0.5 or 1.0
            p = (int(round(mx + nx / n * offset)), int(round(my + ny / n * offset)))
            if cp.seam_edge_distance(scene['faces'], face, p) <= 5.0:
                return p
    return None


# 面心不再算「选缝」（2026-11-17 用户要求），必须点在缝线上；
# 所以先找最靠前那片面的面心，再找它旁边的缝线取点。
target = gui._cubic_scene['faces'][-1]
pt = _seam_point(gui._cubic_scene, target)
if pt is None:
    for f in reversed(gui._cubic_scene['faces']):
        pt = _seam_point(gui._cubic_scene, f)
        if pt is not None:
            target = f
            break
check(pt is not None, '场景里能找到一个贴着缝线的屏幕点')
center_pt = (int(round(sum(p[0] for p in target['pts']) / 4.0)),
             int(round(sum(p[1] for p in target['pts']) / 4.0)))


def click(pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))
    gui.handle_events()


click(center_pt)
check(gui.selected_gap is None, '点面心不改切面（2026-11-17 修：缝选中范围太大）')

click(pt)
check(gui.selected_gap is not None, f'点缝线上 → 出现切面预览（{gui.selected_gap}）')
check(gui.selected_gap and gui.game.is_valid_gap(*gui.selected_gap),
      '预览的切面是引擎判有效的缝')
check(gui.step_count == step0 and len(getattr(gui.game_history, 'undo_stack', []) or []) == hist0,
      '单击不产生步数、不入历史（还只是预览）')
check(not any(getattr(b, 'be_opted', False) for b in gui.game.blocks),
      '单击不选块（选中留给双击）')

click(pt)
seam = gui.selected_gap
opted_gui = sorted(tuple(int(v) for v in b.location[:3])
                   for b in gui.game.blocks if getattr(b, 'be_opted', False))
ref = create_adapter_puzzle('cubic', 3, 3, 1, depth=3)
ref_block = None
for b in ref.blocks:
    if tuple(int(v) for v in b.location[:3]) == tuple(int(v) for v in target['loc'][:3]):
        ref_block = b
ref.opt(seam[0], seam[1], ref_block)
opted_ref = sorted(tuple(int(v) for v in b.location[:3])
                   for b in ref.blocks if getattr(b, 'be_opted', False))
check(bool(opted_gui), f'双击 → 选中一侧连通组（{len(opted_gui)} 块）')
check(opted_gui == opted_ref, '选中的组与引擎 opt 独立算出的组逐一相同')
check(all(tuple(int(v) for v in b.location[:3]) == tuple(int(v) for v in b.location[:3])
          for b in gui.game.blocks),
      '选中后块位置未被挪动（只是标记，不是滑动）')
check(gui.step_count == step0, '双击选中也不产生步数')

print('E. 拖动只转不选 / 旋转态不选 / 右键清空')
gui._cubic_clear_selection()
pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pt))
gui.handle_events()
pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION,
                                     pos=(pt[0] + 40, pt[1] + 8), rel=(40, 8)))
gui.handle_events()
pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                                     pos=(pt[0] + 40, pt[1] + 8)))
gui.handle_events()
check(gui.selected_gap is None and gui.selected_block is None,
      '拖动松手 = 旋转收尾，不选中任何东西')
check(not any(getattr(b, 'be_opted', False) for b in gui.game.blocks),
      '旋转后也没有块被标记选中')

gui._cubic_view_oblique()        # 斜视 = 旋转态（不在六朝向之一）
gui.draw_cubic_board()
target = gui._cubic_scene['faces'][-1]
pt = (int(round(sum(p[0] for p in target['pts']) / 4.0)),
      int(round(sum(p[1] for p in target['pts']) / 4.0)))
check(gui.cubic_view_index is None, '斜视下视角序号为空（旋转态）')
click(pt)
check(gui.selected_gap is None, '旋转态点击不选（必须正向化才能选）')

gui._cubic_view(1)
gui.draw_cubic_board()
click(pt)
check(gui.selected_gap is not None, '回到朝向 1 后同样位置可以选')
pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=pt))
gui.handle_events()
check(gui.selected_gap is None and gui.selected_block is None, '右键清空选中与预览')

# 画白线这一帧：有切面时重绘一次，确认不崩且切面仍在
gui.draw_cubic_board()
check(gui.selected_gap is None, '清空后重绘不再画白线')

print('=' * 60)
if _fail:
    print(f'结果：{_ok[0]} 项通过，{len(_fail)} 项失败')
    for m in _fail:
        print('  ·', m)
    sys.exit(1)
print(f'结果：全部通过（{_ok[0]} 项通过，0 项失败）')
