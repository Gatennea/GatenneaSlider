# -*- coding: utf-8 -*-
"""
三角形密鋪棋盤幾何視圖（Stage B1）。

職責：把 (i, j, up) 斜座標滑塊轉成螢幕多邊形、滑鼠座標反查滑塊、
三族縫隙命中、包圍盒計算。所有函式接受浮點斜座標，動畫插值可直接復用。

與 SquareBoardView 的差異：單位單元是三角形而非方形，
故 hit-test 用「點是否在三角形內」，縫隙是三族斜線之一。
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from game_triangle import (
    GAP_DIRECTIONS,
    gap_index_range,
    tri_vertices,
)

_SQRT3 = math.sqrt(3.0)

# game 的 line 是「rank 分界」：縫隙 line 分隔 rank<=line 與 rank>line 兩側
# （見 game_triangle.side_of）。滑塊 (i,j) 佔據斜座標 [i, i+1]×[j, j+1] 的
# 菱形胞，因此這個分界在幾何上正是網格線 line+1：h 族 b=line+1、p 族
# a=line+1、n 族 a+b=line+1（相鄰 rank 的遠側邊）。繪製與命中都必須帶這個
# +1，否則紅線/點擊熱區整體偏離真正的分界一格。
GAP_LINE_OFFSET = 1


class TriangleBoardView:
    """正三角形密鋪棋盤的座標轉換與命中計算。

    螢幕基底：e1 指向右，e2 指向**右上**（pygame 的 y 軸向下，故取負號），
    因此 ▲(i,j) 在螢幕上尖朝上、▼(i,j) 尖朝下，與 game_triangle 的命名一致，
    由初始態拼出的大三角形也是尖朝上的經典造型。
    """

    def __init__(self, cell_size: float = 60.0, gap_width: float = 4.0):
        # cell_size = 單位三角邊長（不含視覺間隙）
        self.cell_size = float(cell_size)
        self.gap_width = float(gap_width)
        self.height = self.cell_size * _SQRT3 / 2.0   # 三角高
        self.inradius = self.cell_size * _SQRT3 / 6.0  # 內心到邊距離

    # ---------- 座標轉換 ----------
    def to_world(self, a: float, b: float) -> Tuple[float, float]:
        """斜座標 (a, b) → 世界座標 (x, y)（y 軸向下，b 增大表示往上）。"""
        return (a * self.cell_size + b * self.cell_size / 2.0,
                -b * self.height)

    def to_oblique(self, wx: float, wy: float) -> Tuple[float, float]:
        """世界座標 (x, y) → 斜座標 (a, b)（浮點）。"""
        b = -wy / self.height
        a = wx / self.cell_size - b / 2.0
        return a, b

    # ---------- 多邊形 ----------
    def piece_polygon(self, i: int, j: int, up: bool,
                      inset: bool = True) -> list:
        """滑塊多邊形（世界座標頂點列表，順時針）。"""
        pts = [self.to_world(a, b) for (a, b) in tri_vertices(i, j, up)]
        if inset and self.gap_width > 0:
            # 均勻縮放：每條邊各內縮 gap_width/2，相鄰滑塊間留出視覺間隙
            f = 1.0 - (self.gap_width / 2.0) / self.inradius
            f = max(0.4, min(1.0, f))
            cx = sum(p[0] for p in pts) / 3.0
            cy = sum(p[1] for p in pts) / 3.0
            pts = [(cx + (x - cx) * f, cy + (y - cy) * f) for (x, y) in pts]
        return pts

    def piece_center(self, i: int, j: int, up: bool) -> Tuple[float, float]:
        """滑塊重心（世界座標）。"""
        pts = [self.to_world(a, b) for (a, b) in tri_vertices(i, j, up)]
        return (sum(p[0] for p in pts) / 3.0, sum(p[1] for p in pts) / 3.0)

    # ---------- 命中 ----------
    def world_to_cell(self, wx: float, wy: float) -> Optional[Tuple[int, int, bool]]:
        """世界座標 → 滑塊 (i, j, up)；空白回傳 None。"""
        a, b = self.to_oblique(wx, wy)
        i0, j0 = math.floor(a), math.floor(b)
        for i in (i0 - 1, i0, i0 + 1):
            for j in (j0 - 1, j0, j0 + 1):
                for up in (True, False):
                    pts = [self.to_world(vx, vy) for (vx, vy) in tri_vertices(i, j, up)]
                    if _point_in_tri(wx, wy, pts):
                        return (i, j, up)
        return None

    def gap_line_distance(self, gap_type: str, line: int,
                          wx: float, wy: float) -> float:
        """點到某條縫隙線的垂直距離（像素）。

        直線方程式（由 to_world 反解，注意 b 軸向上），level = line + 1：
            'h'：b = level          → y = -level * height（水平）
            'p'：a = level          → x + y/√3 = level * s（平行 e2）
            'n'：a+b = level        → x - y/√3 = level * s（平行 e2−e1）
        """
        s = self.cell_size
        level = line + GAP_LINE_OFFSET
        if gap_type == 'h':
            return abs(wy + level * self.height)
        if gap_type == 'p':
            return abs(wx + wy / _SQRT3 - level * s) * _SQRT3 / 2.0
        if gap_type == 'n':
            return abs(wx - wy / _SQRT3 - level * s) * _SQRT3 / 2.0
        raise ValueError(f"unknown gap type: {gap_type}")

    # ---------- 縫隙線定位（繪製用；level = line + 1，見 GAP_LINE_OFFSET） ----------
    def gap_h_y(self, line: int) -> float:
        """'h' 族縫隙 line 的世界 y。"""
        return self.grid_h_y(line + GAP_LINE_OFFSET)

    def gap_oblique_x(self, gap_type: str, line: int, wy: float) -> float:
        """'p'/'n' 族縫隙 line 在世界 y = wy 處的 x。"""
        return self.grid_oblique_x(gap_type, line + GAP_LINE_OFFSET, wy)

    def gap_segment(self, gap_type: str, line: int, box,
                    margin: float = 20.0):
        """縫隙線落在世界包圍盒 (min_x, min_y, max_x, max_y) 內的線段。

        完全在盒外（含外扩 margin）返回 None。斜族按 x 單調性解出 wy 區間，
        避免把線畫到形狀外太遠。
        """
        min_x, min_y, max_x, max_y = box
        x0, x1 = min_x - margin, max_x + margin
        y0, y1 = min_y - margin, max_y + margin
        if gap_type == 'h':
            y = self.gap_h_y(line)
            if not (y0 <= y <= y1):
                return None
            return ((x0, y), (x1, y))
        if gap_type not in ('p', 'n'):
            raise ValueError(f"unknown gap type: {gap_type}")
        level = (line + GAP_LINE_OFFSET) * self.cell_size
        sign = 1.0 if gap_type == 'p' else -1.0

        def x_at(wy):
            return level - sign * wy / _SQRT3

        def wy_at(x):
            return sign * _SQRT3 * (level - x)

        if sign > 0:      # 'p'：x 隨 wy 增大而減小
            wy_lo, wy_hi = wy_at(x1), wy_at(x0)
        else:             # 'n'：x 隨 wy 增大而增大
            wy_lo, wy_hi = wy_at(x0), wy_at(x1)
        lo, hi = max(y0, wy_lo), min(y1, wy_hi)
        if lo > hi:
            return None
        return ((x_at(lo), lo), (x_at(hi), hi))

    # ---------- 網格背景輔助 ----------
    def grid_h_levels(self, wy_top: float, wy_bottom: float) -> range:
        """水平族（b = level）在給定世界 y 範圍內的線號範圍。"""
        lo = int(math.floor(-wy_bottom / self.height)) - 1
        hi = int(math.ceil(-wy_top / self.height)) + 1
        return range(lo, hi + 1)

    def grid_h_y(self, level: int) -> float:
        """水平族第 level 條線的世界 y。"""
        return -level * self.height

    def grid_oblique_levels(self, gap_type: str, corners) -> range:
        """斜族（'p'/'n'）在給定世界矩形內的線號範圍。"""
        sign = 1.0 if gap_type == 'p' else -1.0
        vals = [(x + sign * y / _SQRT3) / self.cell_size for (x, y) in corners]
        return range(int(math.floor(min(vals))) - 1, int(math.ceil(max(vals))) + 2)

    def grid_oblique_x(self, gap_type: str, level: int, wy: float) -> float:
        """斜族第 level 條線在世界 y = wy 處的 x。"""
        sign = 1.0 if gap_type == 'p' else -1.0
        return level * self.cell_size - sign * wy / _SQRT3

    def candidate_gaps(self, wx: float, wy: float, cells,
                       tolerance: float = 10.0):
        """候選縫隙（未經遊戲邏輯驗證），由近到遠。"""
        found = []
        for gap_type in GAP_DIRECTIONS:
            for line in gap_index_range(gap_type, cells):
                dist = self.gap_line_distance(gap_type, line, wx, wy)
                if dist <= tolerance:
                    found.append((dist, (gap_type, line)))
        found.sort()
        return [gap for _dist, gap in found]

    # ---------- 包圍盒 ----------
    def bounding_box(self, positions) -> Tuple[float, float, float, float]:
        """全部滑塊的世界座標包圍盒 (min_x, min_y, max_x, max_y)。"""
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        for (i, j, up) in positions:
            for (x, y) in self.piece_polygon(i, j, up, inset=False):
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)
        if not positions:
            return (0.0, 0.0, 0.0, 0.0)
        return (min_x, min_y, max_x, max_y)


def _point_in_tri(px: float, py: float, pts) -> bool:
    """點是否在三角形內（含邊界）。"""
    (ax, ay), (bx, by), (cx, cy) = pts
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)
