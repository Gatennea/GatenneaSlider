# -*- coding: utf-8 -*-
"""回归：三维箭头要相对鼠标/屏幕不动。

2026-11-21 用户澄清：要求的是「开启跟随时，滑塊位移但箭头相对鼠标不位移」。
箭头是贴着上一次点击处的操作入口，不是跟着选中组走；相机因跟随质心平移
时，锚点必须反向补掉相机位移，投影回原屏幕点。

钉住：
  A. 无跟随推一步：箭头屏幕位置不变。
  B. 跟随质心：相机 origin 移动，箭头屏幕位置仍不变。
  C. 动画期间（含结束帧）：箭头都钉在原点击位置，不跟着滑塊滑走。
  D. 二级/多格同样不位移。
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

_ok = [0]
_fail = []


def check(cond, msg, detail=None):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg}' + (f'  {detail!r}' if detail is not None else ''))


def setup(follow, step=1):
    g = GUI.SliderGUI()
    g._cubic_camera_prefs = {}
    g.new_cubic_puzzle(4, 4, 4, step)
    g.show_virtual_keyboard = False
    g.cubic_follow_centroid = follow
    g.selected_gap = ('c', 2)
    g.draw_board()
    anchor_w = cv.layout_anchor(g.game.blocks)
    target = next(b for b in g.game.blocks
                  if tuple(b.location)[:3] == (3, 3, 3))
    box = cv.block_boxes([target], g.cubic_gap, anchor=anchor_w)[0]
    hull = cv.screen_hull_of_box(box, g.cubic_camera,
                                 g._cubic_scene['scale'],
                                 g._cubic_scene['origin'])
    g._cubic_click(int(sum(p[0] for p in hull) / len(hull)),
                   int(sum(p[1] for p in hull) / len(hull)))
    g.draw_board()
    centers = {letter: rect.center
               for letter, rect in g._cubic_arrow_buttons}
    return g, centers


def deltas(old, new):
    return {letter: (new[letter][0] - old[letter][0],
                     new[letter][1] - old[letter][1])
            for letter in old if letter in new}


def mag(delta):
    return (delta[0] ** 2 + delta[1] ** 2) ** 0.5


def assert_locked(c0, c1, label):
    d = deltas(c0, c1)
    worst = max((mag(v) for v in d.values()), default=999.0)
    check(d and worst <= 1.5,
          f'{label}：箭头屏幕位置不动（最大 {worst:.2f}px）', d)
    return d


def main():
    print('=' * 60)
    print('A. 关闭跟随时，滑塊动、箭头不动')
    g, c0 = setup(False)
    p0 = tuple(g._cubic_last_click_p)
    check(g._cubic_push_letter('r'), '推 r 成功')
    g.cubic_anim = None                # 排除动画，只看锚点/投影
    g.draw_board()
    c1 = {letter: rect.center for letter, rect in g._cubic_arrow_buttons}
    assert_locked(c0, c1, '无跟随')
    check(tuple(g._cubic_last_click_p) == p0,
          '无跟随时锚点世界坐标不应跟着滑塊走', (p0, g._cubic_last_click_p))

    print('=' * 60)
    print('B. 跟随质心：相机移动，箭头仍钉在鼠标点击处')
    g2, c2a = setup(True)
    o0 = tuple(g2._cubic_scene['origin'])
    p2a = tuple(g2._cubic_last_click_p)
    check(g2._cubic_push_letter('r'), '跟随态推 r 成功')
    g2.cubic_anim = None
    for _ in range(30):
        g2.draw_board()
    c2b = {letter: rect.center for letter, rect in g2._cubic_arrow_buttons}
    o1 = tuple(g2._cubic_scene['origin'])
    p2b = tuple(g2._cubic_last_click_p)
    assert_locked(c2a, c2b, '跟随质心')
    check((o1[0] - o0[0]) ** 2 + (o1[1] - o0[1]) ** 2 > 1.0,
          '相机确实在跟随质心', (o0, o1))
    check(any(abs(p2b[i] - p2a[i]) > 1e-6 for i in range(3)),
          '锚点做了反向补偿（世界坐标微调，投影不变）', (p2a, p2b))

    print('=' * 60)
    print('C. 动画期间箭头也不跟着滑走')
    g3, c3a = setup(False)
    check(g3._cubic_push_letter('r'), '推 r 成功')
    check(g3.cubic_anim is not None, '建立了 cubic_anim')
    now = pygame.time.get_ticks()
    g3.cubic_anim['t0'] = now
    g3.draw_board()
    c3b = {letter: rect.center for letter, rect in g3._cubic_arrow_buttons}
    assert_locked(c3a, c3b, '动画开始帧')
    g3.cubic_anim['t0'] = now - g3.cubic_anim['ms'] - 1
    g3.draw_board()
    c3c = {letter: rect.center for letter, rect in g3._cubic_arrow_buttons}
    assert_locked(c3a, c3c, '动画结束帧')

    print('=' * 60)
    print('D. 二级/多格同样不位移')
    g4, c4a = setup(True, step=2)
    check(g4._cubic_push_letter('r'), '二级推 r 成功')
    g4.cubic_anim = None
    for _ in range(30):
        g4.draw_board()
    c4b = {letter: rect.center for letter, rect in g4._cubic_arrow_buttons}
    assert_locked(c4a, c4b, '二级/跟随')

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
