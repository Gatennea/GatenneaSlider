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

print('B. 面 → 缝（非包围盒边界可切 / 边界表面一律 None）')
game = create_adapter_puzzle('cubic', 3, 3, 1, depth=3)
locs = cv.locations_of(game.blocks)
check(cp.face_is_internal({'loc': (1, 1, 1), 'axis': 0, 'sign': 1}, locs),
      '心块 +X 面是内部面')
check(not cp.face_is_internal({'loc': (1, 2, 1), 'axis': 0, 'sign': 1}, locs),
      '最外层 +X 面不是内部面')
check(cp.face_on_outer_boundary({'loc': (1, 2, 1), 'axis': 0, 'sign': 1}, locs),
      '最外层 +X 面在包围盒边界')

seams = {}
for face in faces:
    seam = cp.seam_of_face(face, game.is_valid_gap, locs)
    if not cp.face_on_outer_boundary(face, locs):
        check(seam is not None,
              f'非边界表面 {face["loc"]} 轴{face["axis"]}{face["sign"]:+d} → 切面',
              extra=str(seam))
        if seam:
            seams[seam] = seams.get(seam, 0) + 1
            check(game.is_valid_gap(seam[0], seam[1]),
                  f'切面 {seam} 引擎判为有效', extra=str(seam))
            check(cp._is_internal_cut(seam[0], seam[1], locs),
                  f'切面 {seam} 是块与块之间的内部切面', extra=str(seam))
    else:
        check(seam is None,
              f'包围盒边界表面 {face["loc"]} 轴{face["axis"]}{face["sign"]:+d} 不选切面',
              extra=str(seam))
check(set(seams) <= {('r', 0), ('r', 1), ('c', 0), ('c', 1), ('d', 0), ('d', 1)},
      f'所有切面都落在 3×3×3 的六条有效缝上（实得 {sorted(seams)}）')

outer = {'loc': (0, 0, 0), 'axis': 0, 'sign': -1}     # c=0 外侧，line −1 无效
seam_out = cp.seam_of_face(outer, game.is_valid_gap, locs)
check(seam_out is None, f'外侧表面不许退回相邻内部缝（实得 {seam_out}）')
check(cp.seam_of_face({'loc': (0, 0, 0), 'axis': 2, 'sign': 1},
                      lambda f, l: False, locs) is None,
      '没有任何有效线时返回 None（不硬选）')

print('B2. 只有包围盒边界表面不可选；块堆内部露出的面仍可切')
check(cp.seam_of_face({'loc': (0, 0, 0), 'axis': 0, 'sign': 1},
                      game.is_valid_gap, locs) == ('c', 0),
      'c=0 的 +X 内壁 → 缝 c·0')
check(cp.seam_of_face({'loc': (0, 1, 0), 'axis': 0, 'sign': -1},
                      game.is_valid_gap, locs) == ('c', 0),
      'c=1 的 −X 内壁 → 同一条缝 c·0（两面墙指同一条缝）')
check(cp.seam_of_face({'loc': (0, 2, 0), 'axis': 0, 'sign': 1},
                      game.is_valid_gap, locs) is None,
      '最外层 +X 面（包围盒边界）→ None，不退到内部切面 c·1')
check(cp.seam_of_face({'loc': (2, 2, 2), 'axis': 2, 'sign': 1},
                      game.is_valid_gap, locs) is None,
      '最前面块的前脸（包围盒边界）→ None，不退到后面那层的 r·1')
check(cp.seam_of_face({'loc': (1, 1, 1), 'axis': 0, 'sign': 1},
                      lambda f, l: False, locs) is None,
      '引擎说没有有效线时返回 None（不硬选）')

# 关键回归：块堆因滑动/拆分空出一格时，朝空洞的块面不是包围盒边界，
# 只要缝线两侧都还有块，就应可选。不能用「紧邻有没有块」来判。
hole_locs = {(0, 0, 0), (0, 2, 0)}
hole_face = {'loc': (0, 0, 0), 'axis': 0, 'sign': 1}
check(not cp.face_is_internal(hole_face, hole_locs),
      '空洞内部面不紧邻块，face_is_internal 为假')
check(not cp.face_on_outer_boundary(hole_face, hole_locs),
      '空洞内部面不在包围盒边界')
check(cp.seam_of_face(hole_face, lambda f, l: True, hole_locs) == ('c', 0),
      '空洞内部面仍能选出两侧都有块的切面 c·0')
check(cp.seam_of_face({'loc': (0, 2, 0), 'axis': 0, 'sign': 1},
                      lambda f, l: True, hole_locs) is None,
      '块堆最外侧 +X 面仍被拒绝，防止整体滑出')

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


def _seam_point(scene, face=None, samples=17):
    """找「点下去直接命中缝里的墙（内部面）」的屏幕点，返回 (点, 缝, 面)。

    2026-11-17 用户口径：拆分后缝里的墙就是看得见的缝，判定直接以它们为准。
    """
    locs = {tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks}
    cand = [face] if face is not None and cp.face_is_internal(face, locs) else []
    if face is None:
        cand = [f for f in scene['faces'] if cp.face_is_internal(f, locs)]
    for f in list(cand) + [f for f in scene['faces'] if cp.face_is_internal(f, locs)]:
        seam = cp.seam_of_internal_face(f, gui.game.is_valid_gap, locs)
        if seam is None:
            continue
        pts = f['pts']
        for i in range(1, samples):
            for j in range(1, samples):
                u, v = i / samples, j / samples
                x = ((1 - u) * (1 - v) * pts[0][0] + u * (1 - v) * pts[1][0]
                     + u * v * pts[2][0] + (1 - u) * v * pts[3][0])
                y = ((1 - u) * (1 - v) * pts[0][1] + u * (1 - v) * pts[1][1]
                     + u * v * pts[2][1] + (1 - u) * v * pts[3][1])
                p = (int(round(x)), int(round(y)))
                if cp.hit_face(scene['faces'], p) is f:
                    return p, seam, f
    return None, None, None


def _face_center(face):
    pts = face['pts']
    return (int(round(sum(p[0] for p in pts) / 4.0)),
            int(round(sum(p[1] for p in pts) / 4.0)))


def _surface_point(scene):
    """找一块可见的**外表面**面心，且点下去确实命中它。"""
    locs = {tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks}
    for f in scene['faces']:
        if cp.face_is_internal(f, locs):
            continue
        p = _face_center(f)
        if cp.hit_face(scene['faces'], p) is f:
            return p, f
    return None, None


# 2026-11-17 用户改口径：可点范围从「缝里的墙」扩到**块的任意外表面**，
# 但推出来的必须是内部切面（包围盒那层平面不许选）。
# 2026-11-19 曾收紧成「表面不能选」；2026-11-20 修正：只禁包围盒边界表面，
# 块堆内部朝空洞露出的面只要切面两侧还有块仍可选。
target = gui._cubic_scene['faces'][-1]
pt, pt_seam, target = _seam_point(gui._cubic_scene)
check(pt is not None, '场景里能找到一个「缝里的墙」的屏幕点')
center_pt = (int(round(sum(p[0] for p in target['pts']) / 4.0)),
             int(round(sum(p[1] for p in target['pts']) / 4.0)))
locs_set = {tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks}


def click(pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))
    gui.handle_events()


def right_click(pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=pos))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=3, pos=pos))
    gui.handle_events()


# 2026-11-18 新口径：没有缝时禁止选块 → 点块先什么都不选，必须先右键选缝
click(center_pt)
check(gui.selected_gap is None and gui.selected_block is None,
      '没选缝时左键点块不选块（原版同序：先缝后块）')

right_click(pt)
check(gui.selected_gap is not None,
      f'右键点内部墙 → 选缝（{gui.selected_gap}）')
check(cp._is_internal_cut(gui.selected_gap[0], gui.selected_gap[1], locs_set),
      '推出来的切面是内部切面，不是表面/包围盒平面')
check(not any(getattr(b, 'be_opted', False) for b in gui.game.blocks),
      '右键只选缝，不替用户选块')

right_click(pt)
check(gui.selected_gap == pt_seam,
      f'右键点缝里的墙 → 选到那条缝（期望 {pt_seam}，实得 {gui.selected_gap}）')
check(gui.selected_gap and gui.game.is_valid_gap(*gui.selected_gap),
      '预览的切面是引擎判有效的缝')
check(gui.step_count == step0 and len(getattr(gui.game_history, 'undo_stack', []) or []) == hist0,
      '选缝不产生步数、不入历史（还只是预览）')

click(pt)
check(any(getattr(b, 'be_opted', False) for b in gui.game.blocks),
      '已有缝后左键点块 → 选中这块所在的组')

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

# 2026-11-19 新口径：表面不是空白，右键表面既不能退到下一层缝，也不能清掉已有选中。
surface_pt, surface_face = _surface_point(gui._cubic_scene)
check(surface_pt is not None, '场景里能找到一块可见外表面',
      extra=str(surface_face))
gap_before = gui.selected_gap
sels_before = sorted(tuple(int(v) for v in b.location[:3])
                     for b in gui.game.blocks if getattr(b, 'be_opted', False))
ok = gui._cubic_seam_click(*surface_pt)
check(ok is False, '右键外表面不产生切面')
check(gui.selected_gap == gap_before,
      f'右键外表面不改已有切面（保持 {gap_before}，实得 {gui.selected_gap}）')
check(sorted(tuple(int(v) for v in b.location[:3])
             for b in gui.game.blocks if getattr(b, 'be_opted', False)) == sels_before,
      '右键外表面不改已有选中块')
check('表面' in getattr(gui, 'macro_notify_msg', '') and
      '内部切面' in getattr(gui, 'macro_notify_msg', ''),
      f'提示只能选内部切面（实得 {getattr(gui, "macro_notify_msg", "")}）')

print('E. 拖动只转不选 / 斜视下也能选（2026-11-18 撤销正向化）/ 右键清空')
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

gui._cubic_view_oblique()        # 斜视：不在六朝向之一
gui.draw_cubic_board()
pt, seam_want, target = _seam_point(gui._cubic_scene)
check(pt is not None, '斜视下能找到内部墙的屏幕点')
check(gui.cubic_view_index is None, '斜视下视角序号为空（自由旋转态）')
locs_set = {tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks}
right_click(pt)
check(gui.selected_gap == seam_want,
      f'斜视下照样能右键选内部缝（期望 {seam_want}，实得 {gui.selected_gap}）')
check(gui.selected_gap is not None and
      cp._is_internal_cut(gui.selected_gap[0], gui.selected_gap[1], locs_set),
      '斜视下选到的仍是内部切面')

gui._cubic_clear_selection()
gui._cubic_view(1)
gui.draw_cubic_board()
pt, seam_want, target = _seam_point(gui._cubic_scene)
check(pt is not None, '朝向 1 能找到内部墙的屏幕点')
right_click(pt)
check(gui.selected_gap == seam_want,
      f'回到朝向 1 后内部墙仍可选（期望 {seam_want}，实得 {gui.selected_gap}）')
right_click((8, 8))
check(gui.selected_gap is None and gui.selected_block is None, '空白右键清空选中与预览')

# 旋转中不再清掉已有选中（2026-11-18：任何姿态都能操作）
gui._cubic_view(1)
gui.draw_cubic_board()
right_click(pt)          # 先选缝
click(pt)                # 再选块
selected_before = [tuple(int(v) for v in b.location[:3])
                   for b in gui.game.blocks if getattr(b, 'be_opted', False)]
check(bool(selected_before), '先选中一组')
pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                     pos=(pt[0] - 60, pt[1] - 40)))
gui.handle_events()
pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION,
                                     pos=(pt[0], pt[1]), rel=(60, 40)))
gui.handle_events()
pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pt))
gui.handle_events()
check([tuple(int(v) for v in b.location[:3])
       for b in gui.game.blocks if getattr(b, 'be_opted', False)] == selected_before,
      '旋转一下不清掉已有的选中（转完可以直接推）')
# 画白线这一帧：有切面时重绘一次，确认不崩且切面仍在
gui._cubic_clear_selection()
gui._cubic_view(1)
gui.draw_cubic_board()
check(gui.selected_gap is None, '清空后重绘不再画白线')

print('H. 左键不改缝（缝只由右键选；用户 2026-11-18 新操作方式）')
gui.animation_enabled = False
bad = 0
for view in (0, 3):
    gui._cubic_view(view)
    gui.draw_cubic_board()
    for f in list(gui._cubic_scene['faces']):
        pts = f['pts']
        cx = int(sum(p[0] for p in pts) / 4.0)
        cy = int(sum(p[1] for p in pts) / 4.0)
        # 每次先清掉选中（否则上一轮画出的箭头会把点击抢去当「推」）
        gui._cubic_clear_selection()
        gui.draw_cubic_board()
        gui.selected_gap = ('r', 1)      # 已有缝：左键只选块，缝不许被改
        gui._cubic_click(cx, cy)
        if gui.selected_gap != ('r', 1):
            bad += 1
            print('  BAD', view, tuple(int(v) for v in f['loc']), gui.selected_gap)
check(bad == 0, f'左键选块但从不改缝（{bad} 个例外）')

print('I. 右键选内部缝 / 空白右键取消（2026-11-18 新操作方式）')
gui._cubic_view(0)
gui.draw_cubic_board()
pt, seam_want, target = _seam_point(gui._cubic_scene)
check(pt is not None, '朝向 0 能找到内部墙的屏幕点')
ok_seam = gui._cubic_seam_click(*pt)
check(ok_seam and gui.selected_gap == seam_want,
      f'右键内部墙 → 选出切面（期望 {seam_want}，实得 {gui.selected_gap}）')
check(not any(getattr(b, 'be_opted', False) for b in gui.game.blocks),
      '右键只定切面，不替用户选块（块必须左键再点）')
check(gui._cubic_seam_click(8, 8) is False and gui.selected_gap is None,
      '空白处右键 → 取消选中与切面')
check(not any(getattr(b, 'be_opted', False) for b in gui.game.blocks),
      '取消后没有任何块被选中')

print('=' * 60)
if _fail:
    print(f'结果：{_ok[0]} 项通过，{len(_fail)} 项失败')
    for m in _fail:
        print('  ·', m)
    sys.exit(1)
print(f'结果：全部通过（{_ok[0]} 项通过，0 项失败）')
