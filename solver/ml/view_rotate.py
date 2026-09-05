# -*- coding: utf-8 -*-
r"""视图旋转层：把「凸起在窗口任意一侧」统一转到「凸起在窗口右侧」。

只处理刚体旋转（90° 步进），旋转几乎不耗时。方向/轴的语义：

    Action = (gap_type, gap_line, side, move_dir)
    · gap 'h'（行带）只能在左右移动：dir ∈ {a, d}
    · gap 'v'（列带）只能上下移动：dir ∈ {w, s}

旋转以「窗口左上角平移到原点」的坐标系定义（origin 空间）。旋转后窗口尺寸
可能交换为 (n, m)。逆映射统一把 view 动作换回 origin 空间的 world 动作。

所有函数在 origin 空间（窗口占 (0..m-1, 0..n-1)）工作；整盘平移由调用方负责。
"""
from __future__ import annotations

# 旋转名：
#   'id'   ：已在右侧（恒等）
#   'r180' ：左右镜像/180°（把左侧凸起转到右侧），窗口保持 (m,n)
#   'cw'   ：把上方凸起转到右侧（顺时针 90°），窗口变 (n,m)
#   'ccw'  ：把下方凸起转到右侧（逆时针 90°），窗口变 (n,m)


def choose_rot(lr, lc, m, n):
    """按凸起的窗口内局部坐标 (lr, lc)（已在 origin 空间）选旋转。

    lr/lc 是凸起相对窗口左上角的偏移；凸起恰在窗外某一边。
    """
    if lr < 0:
        return 'cw'          # 上方 → 顺时针转到右
    if lr >= m:
        return 'ccw'         # 下方 → 逆时针转到右
    if lc < 0:
        return 'r180'        # 左侧 → 180° 转到右
    return 'id'              # 已在右侧


def view_dims(name, m, n):
    """旋转后窗口尺寸 (mv, nv)。"""
    if name in ('cw', 'ccw'):
        return n, m
    return m, n


def rotate_xy(name, r, c, m, n):
    """origin 空间坐标 → view 空间坐标（旋转）。"""
    if name == 'r180':
        return m - 1 - r, n - 1 - c
    if name == 'cw':
        return c, m - 1 - r          # 上→右
    if name == 'ccw':
        return n - 1 - c, r          # 下→右
    return r, c                      # id


def _inv_xy(name, rv, cv, m, n):
    """view 空间坐标 → origin 空间坐标（逆旋转）。"""
    if name == 'r180':
        return m - 1 - rv, n - 1 - cv
    if name == 'cw':
        return m - 1 - cv, rv
    if name == 'ccw':
        return cv, n - 1 - rv
    return rv, cv


def act_to_world(name, gap, line, side, d, m, n):
    """把 view 空间动作映射回 origin 空间动作。

    返回 (gap', line', side', d')。注意 side 语义用「含等号侧」精确集合转换
    （即必要时平移 line 一格以维持与 view 相同的分割集合）。
    """
    if name == 'id':
        return gap, line, side, d
    if name == 'r180':
        # 180°：轴不变、上下/左右互换、方向 左右/上下 各自反向。
        if gap == 'h':
            L = m - 1 - line - 1
            s2 = 'below' if side == 'above' else 'above'
            return 'h', L, s2, {'a': 'd', 'd': 'a'}[d]
        L = n - 1 - line - 1
        s2 = 'right' if side == 'left' else 'left'
        return 'v', L, s2, {'w': 's', 's': 'w'}[d]
    if name == 'cw':
        # 顺时针 90°：view 行带(r 向带) ⇄ world 列带；方向：a/d ⇄ s/w
        if gap == 'h':
            # view 行带线 line，在 view 列轴左右移（a/d）
            # view 行 rv ≤ line(above) → world 列 c = rv ≤ line → 左带
            # view 行 rv > line(below) → world 右带
            s2 = 'left' if side == 'above' else 'right'
            d2 = {'a': 's', 'd': 'w'}[d]
            return 'v', line, s2, d2
        # view 列带（上下移 w/s）⇄ world 行带（左右移）
        # view 列 cv ≤ line(left) → world 行 r = m-1-cv ≥ m-1-line → 下带
        L = m - 1 - line - 1          # below：rows > L ⇔ rows ≥ m-1-line
        s2 = 'below' if side == 'left' else 'above'
        d2 = {'w': 'a', 's': 'd'}[d]
        return 'h', L, s2, d2
    # name == 'ccw'
    if gap == 'h':
        # view 行带 line → world 列带；view 行 rv ≤ line → world 列 c=n-1-rv
        # ≥ n-1-line → 右带（cols > L, L = n-1-line-1）
        L = n - 1 - line - 1
        s2 = 'right' if side == 'above' else 'left'
        d2 = {'a': 'w', 'd': 's'}[d]
        return 'v', L, s2, d2
    # view 列带 line → world 行带（上下换左右）
    s2 = 'above' if side == 'left' else 'below'
    d2 = {'w': 'd', 's': 'a'}[d]
    return 'h', line, s2, d2


def rep_to_world(name, rv, cv, m, n):
    """view 空间代表格 → origin 空间代表格。"""
    return _inv_xy(name, rv, cv, m, n)
