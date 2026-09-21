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


def _convex_hull(points) -> list:
    """二維點集的凸包（單調鏈；共線點保留也無妨，裁剪只問穿邊交點）。"""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def half(seq):
        chain = []
        for p in seq:
            while len(chain) >= 2 and cross(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
        return chain

    lower = half(pts)
    upper = half(reversed(pts))
    return lower[:-1] + upper[:-1]


def _chord(pts, level: int, axis: str):
    """斜座標凸多邊形與 axis = level 這條直線相交的參數區間 (t_min, t_max)。

    axis: 'a' → a=level（沿 b 參數化）；'b' → b=level（沿 a 參數化）；
    's' → a+b=level（沿 a 參數化）。凸多邊形與直線相交成一條線段，
    故把所有穿邊交點的另一個座標取最小/最大即得兩端；頂點正好落在線上
    也要算進來（叉積為 0 不算「同側」）。只在一個頂點相切時回傳 None。
    """
    ts = []
    n = len(pts)
    for k in range(n):
        a1, b1 = pts[k]
        a2, b2 = pts[(k + 1) % n]
        if axis == 'a':
            v1, v2, t1, t2 = a1, a2, b1, b2
        elif axis == 'b':
            v1, v2, t1, t2 = b1, b2, a1, a2
        else:
            v1, v2, t1, t2 = a1 + b1, a2 + b2, a1, a2
        d1, d2 = v1 - level, v2 - level
        if d1 == 0:
            ts.append(t1)
        if d2 == 0:
            ts.append(t2)
        if d1 == 0 or d2 == 0 or (d1 > 0) == (d2 > 0):
            continue
        ts.append(t1 + (level - v1) * (t2 - t1) / (v2 - v1))
    if not ts:
        return None
    lo, hi = min(ts), max(ts)
    if hi - lo <= 1e-9:
        return None
    return (lo, hi)


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

    def shared_edge(self, key_a: tuple, key_b: tuple):
        """兩個邊相鄰單位三角的公共邊（世界座標兩端點）。

        密鋪中相鄰兩三角恰有一條公共邊，故取兩多边形頂點的公共點；
        頂點由不同公式算得，用容差而不是精確相等來比對。
        非相鄰（無公共邊）回傳 None。
        """
        tol = 1e-6
        pts = []
        for p in self.piece_polygon(*key_a, inset=False):
            for q in self.piece_polygon(*key_b, inset=False):
                if abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol:
                    pts.append(p)
                    break
        if len(pts) != 2:
            return None
        return (pts[0], pts[1])

    def board_hull(self, positions) -> list:
        """棋形（滑塊併集）的凸包（世界座標頂點列表）。

        原版把縫隙線畫滿棋盤矩形，三角版的棋盤不是矩形，對應的「棋盤範圍」
        就是這個凸包：縫隙線裁剪到它上面，才不會畫到形狀外面的空白處。
        """
        pts = []
        for (i, j, up) in positions:
            pts.extend(self.piece_polygon(i, j, up, inset=False))
        return _convex_hull(pts)

    def gap_line_segment(self, gap_type: str, line: int, hull):
        """縫隙 line 與棋形凸包相交的那一段（世界座標兩端點）；不相交回傳 None。

        原版先畫縫隙線、後畫滑塊蓋住，所以洞裡也留一條直線；三角版照做——
        只按凸包裁剪，不按「縫隙兩側是否都有相鄰塊」截斷，選中的紅線因此
        不會在洞處斷開。凸多邊形與直線相交成一條線段，故把所有穿邊交點
        的另一個座標取最小/最大即得兩端。裁剪在斜座標裡做：三族縫隙線
        分別是 b=level、a=level、a+b=level，只需比較一個座標分量。
        """
        level = line + GAP_LINE_OFFSET
        if not hull:
            return None
        pts = [self.to_oblique(x, y) for (x, y) in hull]
        if gap_type == 'h':
            rng = _chord(pts, level, 'b')
            ends = [(t, level) for t in rng] if rng else None
        elif gap_type == 'p':
            rng = _chord(pts, level, 'a')
            ends = [(level, t) for t in rng] if rng else None
        elif gap_type == 'n':
            rng = _chord(pts, level, 's')
            ends = [(t, level - t) for t in rng] if rng else None
        else:
            raise ValueError(f"unknown gap type: {gap_type}")
        if not ends:
            return None
        return tuple(self.to_world(*p) for p in ends)

    def boundary_edges(self, cells) -> list:
        """棋形外輪廓的每一條單位邊（另一側沒有相鄰滑塊的邊）。

        原版把棋盤矩形的四邊也畫成灰線，棋盤因此有完整輪廓；三角版的
        棋形不是矩形，對應的就是外周這些單位邊。沒有它們的話，三角形
        只有內部縫隙、邊界只是方塊邊框，看上去不像一個完整的棋盤。
        """
        from game_triangle import neighbors
        edges = []
        for a in cells:
            for b in neighbors(a):
                if b in cells:
                    continue
                seg = self.shared_edge(a, b)
                if seg is not None:
                    edges.append(seg)
        return edges

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
