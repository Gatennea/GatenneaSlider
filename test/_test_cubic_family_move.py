# -*- coding: utf-8 -*-
"""回归：三维「一条方向平行两个缝族」时，opt 的族不能被方向反查顶掉。

用户 2026-11-18 报：实心 4×4×4 选切面后只有两枚箭头；换一个方向的层
完全滑不动。根因是 EngineGame._build_action 用方向字母反查缝族，而三维
的 r 同时平行 c/d、c 同时平行 r/d、d 同时平行 r/c，next() 会挑到第一条，
把选中片的缝号套到另一条缝上，判成「选中片横跨缝」。

钉住：
  A. 三个缝族各选一层，四条**平行于缝**的方向都允许，法向不允许。
  B. 四个允许方向都真能走（点箭头/键盘走同一条 move_selected_blocks）。
  C. 画面上四个可点箭头都要出现（世界几何 + 画家序，不再用屏幕外沿回退）。
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import GUI  # noqa: E402
from engine import cubic_pick  # noqa: E402
from engine import cubic_view as cv  # noqa: E402
from engine.cubic_camera import CubicCamera  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, detail=None):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg}' + (f'  {detail!r}' if detail is not None else ''))


def fresh(step=2):
    g = GUI.SliderGUI()
    g._cubic_camera_prefs = {}
    g.new_cubic_puzzle(4, 4, 4, step)
    g.show_virtual_keyboard = False
    return g


LETTERS = ('r', 'R', 'c', 'C', 'd', 'D')
# 缝族 → 平行方向（法向不在此列）
PARALLEL = {'r': ('c', 'C', 'd', 'D'),
            'c': ('r', 'R', 'd', 'D'),
            'd': ('r', 'R', 'c', 'C')}
NORMAL = {'r': ('r', 'R'), 'c': ('c', 'C'), 'd': ('d', 'D')}

print('=' * 60)
print('A. 三族各选一层：平行四向可推，法向不可推')
for fam in ('r', 'c', 'd'):
    g = fresh()
    g.selected_gap = (fam, 2)
    anchor = next(b for b in g.game.blocks
                  if tuple(b.location)[:3] == (0, 0, 0))
    g.selected_block = anchor
    g.game.opt(fam, 2, anchor)
    allowed = {L: bool(g._arrow_move_allowed(L)) for L in LETTERS}
    for L in PARALLEL[fam]:
        check(allowed[L], f'{fam} 缝：{L} 可推', allowed)
    for L in NORMAL[fam]:
        check(not allowed[L], f'{fam} 缝：法向 {L} 不画/不推', allowed)

print('=' * 60)
print('B. 平行四向都真的走一步')
for fam in ('r', 'c', 'd'):
    for L in PARALLEL[fam]:
        g = fresh()
        g.selected_gap = (fam, 2)
        anchor = next(b for b in g.game.blocks
                      if tuple(b.location)[:3] == (0, 0, 0))
        g.selected_block = anchor
        g.game.opt(fam, 2, anchor)
        before = [tuple(b.location) for b in g.game.blocks]
        moved = g._cubic_push_letter(L)
        after = [tuple(b.location) for b in g.game.blocks]
        check(moved and before != after,
              f'{fam} 缝 {L} 真的移动了', (moved, g.step_count))
        check(g.step_count == 1, f'{fam} 缝 {L} 记 1 步', g.step_count)

print('=' * 60)
print('C. 画面上四个可点箭头都出现')
g = fresh()
g.selected_gap = ('c', 2)
anchor = next(b for b in g.game.blocks
              if tuple(b.location)[:3] == (0, 0, 0))
g.selected_block = anchor
g.game.opt('c', 2, anchor)
g.draw_board()
shown = {letter for letter, _rect in g._cubic_arrow_buttons}
check(shown == set(PARALLEL['c']),
      f'c 缝四个箭头全部可点（实得 {sorted(shown)}）', shown)

print('=' * 60)
print('D. 四个箭头贴着上一次点击处，不再散在切面外沿')
g = fresh()
g.selected_gap = ('c', 2)
g.draw_board()
anchor_w = cv.layout_anchor(g.game.blocks)
target = next(b for b in g.game.blocks
              if tuple(b.location)[:3] == (3, 3, 3))
box = cv.block_boxes([target], g.cubic_gap, anchor=anchor_w)[0]
hull = cv.screen_hull_of_box(box, g.cubic_camera, g._cubic_scene['scale'],
                             g._cubic_scene['origin'])
click = (int(sum(p[0] for p in hull) / len(hull)),
         int(sum(p[1] for p in hull) / len(hull)))
check(g._cubic_click(*click), '点在选中块上，选中成功')
g.draw_board()
check(g._cubic_last_click_p is not None, '记下点击锚点')
if g._cubic_last_click_p is not None:
    proj = cv.project_point(g._cubic_last_click_p, g.cubic_camera,
                            g._cubic_scene['scale'], g._cubic_scene['origin'])
    check(abs(proj[0] - click[0]) <= 1.5 and abs(proj[1] - click[1]) <= 1.5,
          '锚点投影回点击处', (click, proj[:2]))
scale = g._cubic_scene['scale']
centers = [rect.center for _letter, rect in g._cubic_arrow_buttons]
check(len(centers) == 4, '四个箭头都画出来了', len(centers))
if centers:
    worst = max(((cx - click[0]) ** 2 + (cy - click[1]) ** 2) ** 0.5
                for cx, cy in centers)
    check(worst <= scale * 1.0,
          f'箭头中心都在点击处一格以内（最远 {worst / scale:.2f} 格）',
          (click, centers))

# 箭头顶/底面法向必须等于切面法向（永远平行切面），侧面可见但不参与这条。
axis = cubic_pick.FAMILY_TO_WORLD_AXIS['c']
items = g._cubic_arrow_items(g._cubic_scene, ('c', 2), g.cubic_gap,
                             g.cubic_camera, g.game.blocks)
caps = [it[2]['normal'] for it in items
        if it[1] == 2 and it[2].get('cap')]
check(len(caps) == 8,
      '四个箭头各有一对顶/底面', len(caps))
check(bool(caps) and all(abs(abs(n[axis]) - 1.0) <= 1e-6 for n in caps),
      '每个箭头顶/底面的法向都等于切面法向', caps)
check(not getattr(g, '_cubic_arrow_ghosts', set()),
      '默认视角箭头没有被遮，不画虚线', getattr(g, '_cubic_arrow_ghosts', None))

# 转到背侧：箭头被前侧块盖住，应补虚线轮廓，且四个命中盒仍在。
g.cubic_camera = CubicCamera.from_yaw_pitch(-150, -30)
g.draw_board()
check(set(getattr(g, '_cubic_arrow_ghosts', set())) == set('rRdD'),
      '被遮时四个箭头都补虚线轮廓',
      getattr(g, '_cubic_arrow_ghosts', None))
check(len(g._cubic_arrow_buttons) == 4,
      '虚线箭头仍然可点（四个命中盒都在）', len(g._cubic_arrow_buttons))
if g._cubic_arrow_buttons:
    before = g.step_count
    _letter, _rect = g._cubic_arrow_buttons[0]
    check(g._cubic_click(*_rect.center), '点虚线箭头能触发滑动', _rect)
    check(g.step_count == before + 1,
          '虚线箭头点击后步数前进', (before, g.step_count))

print('=' * 60)
print('E. 连续同向推：滑后仍连通的前三步不能被拒')
g = fresh(step=1)
g.selected_gap = ('c', 2)
anchor = next(b for b in g.game.blocks
              if tuple(b.location)[:3] == (0, 0, 0))
g.selected_block = anchor
g.game.opt('c', 2, anchor)
for k in range(3):
    moved = g._cubic_push_letter('d')
    check(moved, f'第 {k + 1} 次同向滑动仍合法', getattr(g, '_reject_reason', None))
    check(g.step_count == k + 1, f'第 {k + 1} 次步数正确', g.step_count)
# 第 4 次：选中组已离开其余块两格，真的断开；这一步拒绝是对的。
check(not g._cubic_push_letter('d'), '第 4 次断开时正常拒绝')

print('=' * 60)
print(f'结果：{"全部通过" if not _fail else "有失败"}（{_ok[0]} 项通过，'
      f'{len(_fail)} 项失败）')
if _fail:
    for msg in _fail:
        print(' -', msg)
    sys.exit(1)
