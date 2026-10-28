# -*- coding: utf-8 -*-
r"""框选判定回归（2026-10-28 修「漏选」）。

旧版 ``_med_select_box`` 只认单点质心，碎三角 / 长条块质心偏在一侧会漏选
（玩家明明框住了块却选不中）。修复后判据 = 块**任一顶点在框内 或 质心在框内**
（见 ``engine/editor_geom.box_hits_block``）。本文件用纯函数 + shatter 碎盘集成
双向钉住：「顶点进框即选中」、且「旧『仅质心』对照会漏选」。

跑法：D:/python/python.exe test/_test_model_select_box.py
"""
import os
import sys
import traceback

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)

import pygame  # noqa: E402  (dummy 驱动要在 import GUI 前就位)

from engine import editor_geom as eg  # noqa: E402
from engine.model_registry import loaded  # noqa: E402
from _test_model_editor import _make_gui  # noqa: E402

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print('    FAIL:', msg)
    return bool(cond)


def _old_centroid_only(p, offs, box):
    """复刻旧版「只认质心」判据，用作对照。"""
    x0, x1, y0, y1 = box
    n = len(offs)
    if not n:
        return False
    cx = p[0] + sum(v[0] for v in offs) / n
    cy = p[1] + sum(v[1] for v in offs) / n
    return x0 <= cx <= x1 and y0 <= cy <= y1


def t_vertex_or_centroid():
    """窄框只盖住长条三角的一端顶点（质心在框外）：新命中、旧漏选。"""
    p = (0, 0)
    offs = [(0, 0), (30, 0), (1, 2)]           # 细长三角，质心约 (10.3, 0.7)
    box = (25, 40, -1, 3)                       # 只包住右端顶点 (30, 0)
    check(eg.box_hits_block(p, offs, *box),
          '新判定：顶点在框内应命中（修漏选）')
    check(not _old_centroid_only(p, offs, box),
          '对照：旧「仅质心」会漏选此块')
    # 整块包围框：全部顶点进框 → 命中
    allx = [p[0] + o[0] for o in offs]
    ally = [p[1] + o[1] for o in offs]
    big = (min(allx) - 1, max(allx) + 1, min(ally) - 1, max(ally) + 1)
    check(eg.box_hits_block(p, offs, *big), '整块包围框应命中')


def t_no_false_positive():
    """两块分离，框只包围 A：不误选 B。"""
    A = ((0, 0), 'tri', 0)
    B = ((10, 0), 'tri', 0)
    offs = [(0, 0), (2, 0), (0, 2)]
    placed = {A: offs, B: offs}
    box = (-1, 3, -1, 3)
    sel = eg.select_blocks_in_box(placed, box)
    check(A in sel, 'A 应被选中')
    check(B not in sel, 'B 不应被误选')


def t_shatter_select():
    """shatter 碎盘（任意 basis + pos_scale=3）：框选真块的新/旧对照。"""
    if 'shatter' not in loaded():
        check(True, 'shatter 未注册，跳过（不影响其余）')
        return
    gui = _make_gui()
    gui._med_open()
    try:
        check(gui._med_load_model('shatter'), '载入碎三角')
        placed = gui._med['placed']
        check(len(placed) == 48, f'应载入 48 块，实得 {len(placed)}')
        k0 = next(iter(placed))
        offs = placed[k0]
        pts = [(k0[0][0] + o[0], k0[0][1] + o[1]) for o in offs]
        # 只留 k0，做窄框对比（避免邻块顶点干扰）
        gui._med['placed'] = {k0: offs}
        # 取 k0 离原点最远的顶点，窄框只含该顶点
        vx, vy = max(pts, key=lambda q: abs(q[0]) + abs(q[1]))
        narrow = (vx - 0.4, vx + 0.4, vy - 0.4, vy + 0.4)
        sel = eg.select_blocks_in_box(gui._med['placed'], narrow)
        check(k0 in sel, '新判定：碎三角顶点在框内即选中')
        check(not _old_centroid_only(k0[0], offs, narrow),
              '对照：旧「仅质心」会漏选此碎块')
        # 整块包围框也应选中
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        big = (min(xs) - 0.5, max(xs) + 0.5, min(ys) - 0.5, max(ys) + 0.5)
        sel2 = eg.select_blocks_in_box(gui._med['placed'], big)
        check(k0 in sel2, '整块包围框应选中碎块')
    finally:
        gui._med_close()


def main():
    cases = [t_vertex_or_centroid, t_no_false_positive, t_shatter_select]
    for fn in cases:
        print(f'--- {fn.__name__} ---')
        try:
            fn()
        except Exception:
            traceback.print_exc()
            FAILS.append(f'{fn.__name__} 抛异常')
    print()
    if FAILS:
        print(f'共 {len(FAILS)} 项失败：')
        for f in FAILS:
            print('  ·', f)
        sys.exit(1)
    print(f'框选判定回归全部通过（{len(cases)} 组）')


if __name__ == '__main__':
    main()
