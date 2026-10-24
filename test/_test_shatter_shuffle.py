# -*- coding: utf-8 -*-
"""回归：碎三角打乱必须是**安全打乱**（每步可逆 ⇒ 终态保证有解）。

用户 2026-10-24：打乱要走原版那招安全打乱，不能踩中不可解的死局。

实现位置：``engine/adapter.py::_random_move`` —— 先提交、再在同一条缝上
遍历方向尝试「精确推回移动前的位置集合」，推不回就回滚坐标。本测试不信
这条注释，直接拿打乱记录**整条反向重放**：能一路退回还原态，才叫安全。

顺带记录耗时：打乱是同步算完再播演示的，碎三角曾要 6.2s（期间界面卡死），
缓存缝线枚举后降到 1s 内。
"""
import os
import queue
import sys
import time

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return cond


def main():
    gui = SliderGUI(m=4, n=4, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5120})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.animation_enabled = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui.new_shatter_puzzle(1)
    gui.center_map()

    g = gui.game
    records = []
    t0 = time.perf_counter()
    g.shuffle(160, 2, bias=0.0, min_score=None, record=records)
    cost = time.perf_counter() - t0
    print(f'  打乱 160 步耗时 {cost:.2f}s，记录 {len(records)} 条')

    check(bool(records), '打乱产出了可重放的记录')
    check(not g.is_solved(), '打乱后不是还原态')
    check(cost < 3.0, f'打乱耗时在可接受范围（{cost:.2f}s < 3s）')

    # 逐步反向重放：每一步都必须能精确退回
    board = g.board
    bad = None
    for i, rec in enumerate(reversed(records)):
        moved = [tuple(p) for p in rec['moved']]
        final = [tuple(p) for p in rec['final']]
        step = rec['step']
        delta = (final[0][0] - moved[0][0], final[0][1] - moved[0][1])
        unit = (delta[0] // step, delta[1] // step)
        keys = frozenset(((f[0], f[1]), f[2]) for f in final)
        nxt = board.slide(keys, (-unit[0], -unit[1]), step)
        if nxt is None:
            bad = (i, rec['gap'], rec['direction'], delta)
            break
        board = nxt
    check(bad is None, '打乱记录可整条反向重放（每步都能精确退回）',
          f'第 {bad} 步推不回' if bad else '')
    if bad is None:
        check(board.is_solved(), '反向重放到底 = 还原态（终态必可解）')
        now = {(b.point, b.orient) for b in board.blocks}
        goal = {(b.point, b.orient) for b in g.spec.goal_blocks}
        check(now == goal, '反向重放的结果与还原态逐块一致',
              f'差集 {sorted(now ^ goal)[:2]}')

    # 每次打乱都应可复现地安全：再打 3 次，每次都能退回
    for r in range(3):
        recs = []
        # 起点可能已经不是还原态（连续打乱），故与“打乱前局面”比对
        before_state = {(b.point, b.orient) for b in g.board.blocks}
        g.shuffle(60, 2, bias=0.0, min_score=None, record=recs)
        bd = g.board
        okr = True
        for rec in reversed(recs):
            moved = [tuple(p) for p in rec['moved']]
            final = [tuple(p) for p in rec['final']]
            st = rec['step']
            d = (final[0][0] - moved[0][0], final[0][1] - moved[0][1])
            u = (d[0] // st, d[1] // st)
            keys = frozenset(((f[0], f[1]), f[2]) for f in final)
            nb = bd.slide(keys, (-u[0], -u[1]), st)
            if nb is None:
                okr = False
                break
            bd = nb
        after_state = {(b.point, b.orient) for b in bd.blocks}
        check(okr and after_state == before_state,
              f'第 {r + 2} 轮打乱同样可整条退回（回到打乱前局面）',
              f'差集 {sorted(after_state ^ before_state)[:2]}')

    print(f'\n通过 {_ok[0]} 项，失败 {len(_fail)} 项')
    if _fail:
        for m in _fail:
            print('  ✗', m)
        print('FAILED')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
