# -*- coding: utf-8 -*-
"""
幾何抽象：單一謎題形態的座標轉換與命中計算。

Stage 0 僅落實 SquareBoardView；TriangleBoardView 留待 Stage B。
"""

from __future__ import annotations

from typing import Tuple, Optional, Generator


class SquareBoardView:
    """正方形網格幾何輔助（接受浮點座標，支援動畫插值）。"""

    def __init__(self, cell_size: float = 60.0, gap_width: float = 4.0):
        self.cell_size = float(cell_size)
        self.gap_width = float(gap_width)
        self._unit = self.cell_size + self.gap_width

    # ---------- 座標轉換 ----------
    def cell_to_world(self, r: float, c: float) -> Tuple[float, float]:
        """格子座標 (row, col) → 世界座標 (x, y)。"""
        return c * self._unit, r * self._unit

    def world_to_cell(self, wx: float, wy: float) -> Optional[Tuple[float, float]]:
        """世界座標 (x, y) → 格子座標 (row, col)；落在縫隙則回傳 None。"""
        c = wx // self._unit
        r = wy // self._unit
        if (wx - c * self._unit) >= self.cell_size or (wy - r * self._unit) >= self.cell_size:
            return None
        return r, c

    def block_rect(self, r: float, c: float) -> Tuple[float, float, float, float]:
        """回傳方塊在世界座標中的 (x, y, w, h)。"""
        x, y = self.cell_to_world(r, c)
        return x, y, self.cell_size, self.cell_size

    # ---------- 縫隙命中 ----------
    def candidate_gaps(
        self,
        wx: float,
        wy: float,
        bounds: dict,
        tolerance: float = 10.0,
    ) -> Generator[Tuple[str, int], None, None]:
        """候選縫隙（未經遊戲邏輯驗證）。"""
        min_row, max_row = bounds['min_row'], bounds['max_row']
        min_col, max_col = bounds['min_col'], bounds['max_col']
        gap = self.gap_width

        for i in range(min_row, max_row + 2):
            gap_y = i * self._unit - gap / 2
            if abs(wy - gap_y) < gap + tolerance:
                board_left = min_col * self._unit
                board_right = (max_col + 1) * self._unit
                if board_left - 50 < wx < board_right + 50:
                    yield 'h', i - 1

        for j in range(min_col, max_col + 2):
            gap_x = j * self._unit - gap / 2
            if abs(wx - gap_x) < gap + tolerance:
                board_top = min_row * self._unit
                board_bottom = (max_row + 1) * self._unit
                if board_top - 50 < wy < board_bottom + 50:
                    yield 'v', j - 1
