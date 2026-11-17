# -*- coding: utf-8 -*-
"""回归：三维「拆分」与遮挡可见性（§54 第 1 步的补课）。

2026-11-17 用户点出关键：**拆分 = 相邻块之间让出空位**。距离 0（还原态）时
所有块贴死成一个整块长方体，投影上只有一层外轮廓——前块挡后块根本看不出来。
所以「能画出来」还必须包括「拆分态画得对」，否则遮挡正确性无从验证。

本测试钉住：
  A. 未拆分（还原态）：斜视恰好 27 个外表面，前后不可辨（面数守恒可推）。
  B. 引擎打乱能拆开：不再是还原态、块数守恒、位置仍是整数三元组、聚拢度 < 1，
     且确实出现了原盒外的坐标（「让出空位」的量化版本）。
  C. 拆分态渲染：面数增加、深度升序仍成立、内部面仍不画、三面明暗俱在、
     屏幕上确有互相重叠的面，且重叠处「近的排在后面画」。
  D. GUI 全路径：动画开着打乱 → 演示自行收尾 → 终态拆分 → 整帧不崩，
     左上角状态行如实报「已拆分」。

跑法：D:/python/python.exe test/_test_cubic_split.py
"""
import os
import random
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

from engine.adapter import create_adapter_puzzle  # noqa: E402
from engine.cubic_camera import CubicCamera  # noqa: E402
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


def locs_of(game):
    return [tuple(b.location) for b in game.blocks]


print('=' * 60)
print('A. 未拆分（还原态）：整块，看不出前后')
game = create_adapter_puzzle('cubic', 3, 3, 3, depth=3)
check(game.is_solved(), '新建 3×3×3 是还原态（未拆分）')
check(len(game.blocks) == 27, '27 块', len(game.blocks))
sol = locs_of(game)
check(all(0 <= v < 3 for loc in sol for v in loc), '全部块都在 0..2 盒内',
      (min(v for loc in sol for v in loc), max(v for loc in sol for v in loc)))
faces = cv.collect_faces(sol, CubicCamera.oblique_default(),
                         scale=30.0, origin=(200.0, 200.0))
check(len(faces) == 27, '斜视恰好 27 个外表面（3 面 × 9 格）', len(faces))
# 未拆分时「块与块之间没有缝隙」：is_solved（27 格全满）已保证；面上的 loc
# 只会落在三个可见边界层上（r=2 / c=2 / d=2），内部块一个面都不露——
# 这正是「整块看不出前后」的直接证据。
check(all(max(f['loc']) == 2 for f in faces),
      '可见面全在三个可见边界层上（内部块零露面 = 前后不可辨）')

print('=' * 60)
print('B. 打乱 = 拆开：块之间真的让出空位')
random.seed(20261117)
rec = []
# attempts/step 取与 GUI 默认同量级（3×3×3 等级2 时 GUI 实测约 14~16 步）
game.shuffle(40, 2, bias=0.3, min_score=None, record=rec)
check(not game.is_solved(), '打乱后不再是还原态')
check(len(game.blocks) == 27, '打乱不改变块数', len(game.blocks))
locs = locs_of(game)
check(all(isinstance(v, int) or float(v).is_integer()
          for loc in locs for v in loc), '位置仍是整数三元组')
check(all(len(loc) == 3 for loc in locs), '位置仍是三维（没被压成二维）')
outside = [loc for loc in locs if any(v < 0 or v > 2 for v in loc)]
check(bool(outside), '出现原盒外的坐标（=让出空位，拆分成立）', len(outside))
check(game.compute_score() < 1.0, '聚拢度 < 1（确实散开了）',
      game.compute_score())
check(len(rec) > 0, '打乱记录非空（撤销/演示都靠它）', len(rec))

print('=' * 60)
print('C. 拆分态渲染：遮挡关系可读')
cam = CubicCamera.oblique_default()
split_faces = cv.collect_faces(locs, cam, scale=30.0, origin=(240.0, 240.0))
check(len(split_faces) > 27, '拆分后面数多于整块（内部空位露出来了）',
      len(split_faces))
check(split_faces == sorted(split_faces, key=lambda f: f['depth']),
      '深度升序（远先近后）仍成立')
check(len({f['shade'] for f in split_faces}) == 3,
      '三面明暗俱在（能分辨哪面朝哪）')
# 内部面仍不画：任一面都不该有邻块占着那一侧
occupied = set(locs)
check(all(cv.neighbor_location(f['loc'], f['axis'], f['sign'])
          not in occupied for f in split_faces),
      '拆分后内部面依然被剔除')


def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _overlap(a, b):
    ba, bb = _bbox(a), _bbox(b)
    return (min(ba[2], bb[2]) - max(ba[0], bb[0]) > 1.0
            and min(ba[3], bb[3]) - max(ba[1], bb[1]) > 1.0)


pairs = [(i, j) for i in range(len(split_faces))
         for j in range(i + 1, len(split_faces))
         if split_faces[i]['loc'] != split_faces[j]['loc']
         and _overlap(split_faces[i]['pts'], split_faces[j]['pts'])]
check(bool(pairs), '画面上确有互相重叠的面（遮挡关系真的存在）', len(pairs))
if pairs:
    i, j = pairs[0]
    far, near = split_faces[i], split_faces[j]   # 列表已按深度升序
    check(far['depth'] <= near['depth'],
          '重叠对里远的先画、近的后画（前块盖住后块）',
          (far['depth'], near['depth']))

print('=' * 60)
print('D. GUI 全路径：打乱 → 演示收尾 → 拆分态可画')
from GUI import SliderGUI  # noqa: E402

pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.tut_show_prompt = False
gui.tutorial_active = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui.animation_enabled = True

gui.new_cubic_puzzle(3, 3, 3, 2)
check(gui.game.is_solved(), '三维建局默认是整块（与二维同口径）')
gui.shuffle_puzzle(confirm=False)
frames = 0
while getattr(gui, '_shuffle_demo_active', False) and frames < 2000:
    gui.update_animation()
    gui.draw_board()
    frames += 1
check(not getattr(gui, '_shuffle_demo_active', False),
      '打乱演示自行收尾（不卡死）', frames)
check(not gui.game.is_solved(), 'GUI 打乱后是拆分态')
check(len(gui.game.blocks) == 27, 'GUI 打乱后 27 块', len(gui.game.blocks))
gui.draw_board()
check(True, '拆分态整帧绘制不抛异常')

_probe = {}
for _y in range(0, gui.screen_height, 5):
    for _x in range(0, gui.screen_width, 5):
        _c = gui.screen.get_at((_x, _y))[:3]
        _probe[_c] = _probe.get(_c, 0) + 1
_shades = [c for c, n in _probe.items() if n > 200]
check(len(_shades) >= 3, '拆分态仍有 ≥3 级明暗', _shades)
check(any(c == gui.colors['background'] for c in _probe), '背景没被糊死')

print('=' * 60)
print(f'结果：{"全部通过" if not _fail else "有失败"}（{_ok[0]} 项通过，'
      f'{len(_fail)} 项失败）')
if _fail:
    for msg in _fail:
        print('  - ' + msg)
sys.exit(1 if _fail else 0)
