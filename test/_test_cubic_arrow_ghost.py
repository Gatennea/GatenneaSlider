# -*- coding: utf-8 -*-
"""回归：三维箭头只把「真正被块盖住的部分」虚化。

2026-11-21 用户反馈：逐像素裁切后，部分被挡的箭头直接缺一块，彻底看不见。
要求恢复为「可见部分实心、被挡部分虚线」，而不是整支虚化或整块消失。

钉住：
  A. 虚线圈本身能按 mask 只保留被挡区域。
  B. 部分遮挡（覆盖率 < 0.35）的箭头也必须走裁切虚线，不能只对整支被挡
     的箭头补虚线。
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
import GUI  # noqa: E402
from engine import cubic_view as cv  # noqa: E402
from engine.cubic_camera import CubicCamera  # noqa: E402
from gui.renderer import RendererMixin  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, detail=None):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg}' + (f'  {detail!r}' if detail is not None else ''))


def alpha_count(surf):
    n = 0
    for x in range(surf.get_width()):
        for y in range(surf.get_height()):
            if surf.get_at((x, y)).a:
                n += 1
    return n


def alpha_count_rect(surf, rect):
    n = 0
    for x in range(rect.left, rect.right):
        for y in range(rect.top, rect.bottom):
            if surf.get_at((x, y)).a:
                n += 1
    return n


def make_mask(w, h, left_opaque=True):
    m = pygame.Surface((w, h), pygame.SRCALPHA)
    m.fill((0, 0, 0, 0))
    if left_opaque:
        pygame.draw.rect(m, (255, 255, 255, 255), pygame.Rect(0, 0, w // 2, h))
    return m


def main():
    print('=' * 60)
    print('A. 虚线圈按 mask 只保留被挡区域')
    d = type('D', (), {'zoom': 1.0})()
    pts = [(10, 10), (90, 10), (90, 90), (10, 90)]

    full = pygame.Surface((100, 100), pygame.SRCALPHA)
    full.fill((0, 0, 0, 0))
    RendererMixin._cubic_draw_arrow_ghost(d, full, pts, lambda p: p, 1)
    full_n = alpha_count(full)
    check(full_n > 0, f'无 mask 时画整圈虚线（{full_n}px）')

    # 只让左半区可见：虚线只能留在 x<50
    half = pygame.Surface((100, 100), pygame.SRCALPHA)
    half.fill((0, 0, 0, 0))
    clip = (make_mask(100, 100, left_opaque=True), 0, 0)
    RendererMixin._cubic_draw_arrow_ghost(
        d, half, pts, lambda p: p, 1, clip=clip)
    left_n = alpha_count_rect(half, pygame.Rect(0, 0, 50, 100))
    right_n = alpha_count_rect(half, pygame.Rect(50, 0, 50, 100))
    check(left_n > 0, f'被挡区域仍有虚线（左半 {left_n}px）')
    check(right_n == 0, f'未挡区域不补虚线（右半 {right_n}px）')

    empty = pygame.Surface((100, 100), pygame.SRCALPHA)
    empty.fill((0, 0, 0, 0))
    RendererMixin._cubic_draw_arrow_ghost(
        d, empty, pts, lambda p: p, 1,
        clip=(make_mask(100, 100, left_opaque=False), 0, 0))
    check(alpha_count(empty) == 0, '完全没挡住时不画虚线')

    print('=' * 60)
    print('B. 部分遮挡箭头也走裁切虚线（不能只靠覆盖率 ≥ 0.35）')
    g = GUI.SliderGUI()
    g._cubic_camera_prefs = {}
    g.new_cubic_puzzle(4, 4, 4, 2)
    g.show_virtual_keyboard = False
    g.selected_gap = ('c', 2)
    g.draw_board()
    anchor_w = cv.layout_anchor(g.game.blocks)
    target = next(b for b in g.game.blocks
                  if tuple(b.location)[:3] == (3, 3, 3))
    box = cv.block_boxes([target], g.cubic_gap, anchor=anchor_w)[0]
    hull = cv.screen_hull_of_box(box, g.cubic_camera,
                                 g._cubic_scene['scale'],
                                 g._cubic_scene['origin'])
    click = (int(sum(p[0] for p in hull) / len(hull)),
             int(sum(p[1] for p in hull) / len(hull)))
    g._cubic_click(*click)
    g.cubic_camera = CubicCamera.from_yaw_pitch(-150, 40)

    calls = []
    orig = RendererMixin._cubic_draw_arrow_ghost

    def spy(hi, pts_, transform, ss, clip=None):
        calls.append(clip is not None)
        return orig(g, hi, pts_, transform, ss, clip=clip)

    g._cubic_draw_arrow_ghost = spy
    g.draw_board()
    g._cubic_draw_arrow_ghost = orig.__get__(g, type(g))

    clips = set(getattr(g, '_cubic_arrow_clip', {}).keys())
    ghosts = set(getattr(g, '_cubic_arrow_ghosts', set()))
    check('D' in clips and 'D' not in ghosts,
          '找到 D：有遮挡但覆盖率 < 0.35', (sorted(clips), sorted(ghosts)))
    check(len(calls) == len(clips) and all(calls),
          f'每支有遮挡的箭头都传入裁切 mask（{calls}）')

    print('=' * 60)
    if _fail:
        print(f'结果：{len(_fail)} 项失败（{_ok[0]} 项通过）')
        for f_ in _fail:
            print('  -', f_)
        return 1
    print(f'结果：全部通过（{_ok[0]} 项通过，0 项失败）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
