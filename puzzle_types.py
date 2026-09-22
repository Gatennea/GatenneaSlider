# -*- coding: utf-8 -*-
"""
謎題形態輔助：puzzle_key 與 create_puzzle 集中管理。

對外契約：
- puzzle_key(step, m, n, kind, ...) -> str
- create_puzzle(m, n, step, kind, ...) -> SliderMatrix | TriangleSliderMatrix
  | MiSliderMatrix

kind: square / numbered / triangle / mi。
"""

from __future__ import annotations

from game import SliderMatrix


def puzzle_key(
    step: int,
    m: int,
    n: int,
    kind: str = 'square',
    *,
    numbered: bool = False,
    triangle_side: int | None = None,
) -> str:
    """生成 puzzle 分組鍵（用於成績、狀態、存檔識別）。

    - square（預設）：沿用原格式 ``f"{step}~{m}*{n}"``。
    - numbered：在 square 後綴 ``#num``。
    - triangle：格式 ``f"{step}~tri{k}"``，k 為大三角形邊長（單元三角個數）。
    - mi：格式 ``f"{step}~mi{m}*{n}"``，m/n 為棋盤行列數（每格 4 個單元）。
    """
    if kind == 'triangle':
        k = triangle_side if triangle_side is not None else m
        return f'{step}~tri{k}'
    if kind == 'mi':
        return f'{step}~mi{m}*{n}'
    base = f'{step}~{m}*{n}'
    if kind == 'numbered' or numbered:
        return f'{base}#num'
    return base


def create_puzzle(
    m: int,
    n: int,
    step: int,
    kind: str = 'square',
    *,
    numbered: bool = False,
    triangle_side: int | None = None,
):
    """依參數建構謎題邏輯物件（對應 GUI 的 self.game）。

    Stage 0 僅回傳 SliderMatrix；triangle/mi 分派至各自模組，模組缺失時
    回退方形（呼叫方需自行處理）。
    """
    if kind == 'triangle':
        # 預留接口：Stage B 實作後取消 try/except 並匯入 TriangleSliderMatrix
        try:
            from game_triangle import TriangleSliderMatrix  # type: ignore
            k = triangle_side if triangle_side is not None else m
            return TriangleSliderMatrix(k)
        except ImportError:
            # 三角形尚未實作時，回退到方形避免引入未支援型態
            pass
    if kind == 'mi':
        try:
            from game_mi import MiSliderMatrix  # type: ignore
            return MiSliderMatrix(m, n)
        except ImportError:
            pass
    return SliderMatrix(m, n)
