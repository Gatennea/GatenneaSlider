# -*- coding: utf-8 -*-
r"""
标注跟踪（相对传播）纯函数测试 — headless

约定：move_group_geometry 接收的 moved_positions 是「移动前」的位置
（与 history 快照 move_info 的记录一致）。

覆盖：
    1. 凸起标记：所在滑块被移动带走 → 整体平移；未被带走 → 原位不动
    2. 空位标记：被移动组填上 → 视为完成移除
    3. 空位幻影滑块：随滑组让出的空格平移（ride）
    4. 空位把两个组件桥接 → 不传播（保持原位）
    5. 保持原位的标记仍为空格 → ok；落在占用格 → lost
    6. 凸起不受所在滑块内部位置影响：位于移动组中间也照常跟随

运行：
    D:\python\python.exe 測試\_test_ann_track.py
"""

import sys
import os

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

from gui.annotation import (  # noqa: E402
    advance_anchor_cells, advance_void_cells, move_group_geometry,
)


def _chk(name, ok, detail=''):
    print(f'  [{"OK" if ok else "FAIL"}] {name}{("  | " + detail) if detail else ""}')
    return ok


def main():
    all_ok = True

    # ---- 1. 凸起：随所在滑块移动 ----
    # 移动组旧占位 {(0,0),(0,1)} 向右移 1 格；锚 (0,1) 在被移滑块上 → 跟走
    prev = {(0, 0), (0, 1), (1, 0), (1, 1)}
    moved = [(0, 0), (0, 1)]          # 移动前位置（history 语义）
    got = advance_anchor_cells(prev, moved, 'd', 1, [(0, 1), (1, 1)])
    assert got == [(0, 2), (1, 1)], got
    all_ok &= _chk('凸起随滑块走/不走', True, f'{got}')

    # ---- 6. 凸起在移动组中间：同样跟走（回归：曾因几何错位一步而留下）----
    # 移动组为 1×3 竖条 {(1,0),(2,0),(3,0)} 向下移 1，锚 (2,0) 在中间
    prev6 = {(1, 0), (2, 0), (3, 0), (1, 2), (2, 2)}
    moved6 = [(1, 0), (2, 0), (3, 0)]  # 移动前位置
    got6 = advance_anchor_cells(prev6, moved6, 's', 1, [(2, 0)])
    assert got6 == [(3, 0)], got6
    all_ok &= _chk('凸起在组中间也跟走', True, f'{got6}')

    # ---- 2. 空位：被填上 → 移除 ----
    # 移动组 {(0,0),(0,1)} 右移 1 → 填上 (0,2)
    prev2 = {(0, 0), (0, 1)}
    cur2 = {(0, 1), (0, 2)}
    moved2 = [(0, 0), (0, 1)]          # 移动前位置
    cells, filled, status = advance_void_cells(
        prev2, cur2, moved2, 'v', 0, 'd', 1, [(0, 2)])
    all_ok &= _chk('空位被填→filled', cells == [] and filled == 1 and status == 'filled',
                   f'{cells} f={filled} {status}')

    # ---- 3. 幻影：空位随滑组让出的空格平移 ----
    # 组在行0 col1..2 向左移 1（旧占位即为 moved）；col3 的空位跟在组后
    # → 落点 col2 正是让出的空格
    prev3 = {(0, 1), (0, 2)}
    cur3 = {(0, 0), (0, 1)}
    moved3 = [(0, 1), (0, 2)]
    cells, filled, status = advance_void_cells(
        prev3, cur3, moved3, 'v', 0, 'a', 1, [(0, 3)])
    all_ok &= _chk('空位随组让位平移', cells == [(0, 2)] and status == 'ok',
                   f'{cells} {status}')

    # ---- 4. 桥接两个组件 → 不传播 ----
    # 移动组 {(0,0)} 向左移 1，空位 (0,1) 若作幻影加入会把 (0,2) 桥接进来
    prev4 = {(0, 0), (0, 2)}
    cur4 = {(0, -1), (0, 2)}
    moved4 = [(0, 0)]                  # 移动前位置
    cells, filled, status = advance_void_cells(
        prev4, cur4, moved4, 'h', 0, 'a', 1, [(0, 1)])
    all_ok &= _chk('桥接→保持原位', cells == [(0, 1)] and status == 'ok',
                   f'{cells} {status}')

    # ---- 5. 保持原位但已不空 → lost ----
    # 移动组 {(0,0),(0,1)} 右移后 (0,3) 仍被其它块占住 → 矛盾格
    prev5 = {(0, 0), (0, 1), (0, 3)}
    cur5 = {(0, 1), (0, 2), (0, 3)}    # (0,3) 被其它块占住（异常边界）
    moved5 = [(0, 0), (0, 1)]
    cells, filled, status = advance_void_cells(
        prev5, cur5, moved5, 'h', 0, 'd', 1, [(0, 3)])
    all_ok &= _chk('矛盾格→lost', cells == [(0, 3)] and status == 'lost',
                   f'{cells} {status}')

    # ---- 几何自检（moved = 移动前位置）----
    delta, s_old, new_m = move_group_geometry([(0, 2), (0, 3)], 'a', 2)
    all_ok &= _chk('几何', delta == (0, -2) and s_old == {(0, 2), (0, 3)}
                   and new_m == {(0, 0), (0, 1)},
                   f'{delta} {s_old} {new_m}')

    print('\n全部通过' if all_ok else '\n存在失败')
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
