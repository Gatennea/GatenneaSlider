# -*- coding: utf-8 -*-
"""
啟發式評估模塊

提供：
    compute_score(game)   - 計算當前狀態的 Score（0~1）
    heuristic(game)       - 啟發函數 h(state) = 1 - Score（用於 A* / IDA*）
    is_solved_state(game) - 判斷是否為通關狀態
"""

from game import SliderMatrix


def compute_score(game: SliderMatrix) -> float:
    """
    計算當前狀態的 Score
    
    Score = 0.5 × fill_rate + 0.5 × (1 - aspect_error)
    
    - fill_rate = K / (bounding_box_area)，方塊越密集分數越高
    - aspect_error 懲罰形狀偏離目標長寬比
    
    參數：
        game: SliderMatrix 實例
    
    返回：
        float: Score ∈ (0, 1]，通關狀態 = 1.0
    """
    if not game.blocks:
        return 0.0
    
    if game.is_solved():
        return 1.0
    
    bounds = game.get_boundaries()
    H = bounds['max_row'] - bounds['min_row'] + 1
    W = bounds['max_col'] - bounds['min_col'] + 1
    K = game.m * game.n
    bb_area = H * W
    
    # fill_rate
    fill_rate = K / bb_area if bb_area > 0 else 0.0
    
    # aspect_error
    m, n = game.m, game.n
    min_dim, max_dim = min(m, n), max(m, n)
    target_ratio = max_dim / min_dim if min_dim > 0 else 1.0
    
    min_hw, max_hw = min(H, W), max(H, W)
    current_ratio = max_hw / min_hw if min_hw > 0 else 1.0
    
    max_ratio = max(current_ratio, target_ratio)
    aspect_error = abs(current_ratio - target_ratio) / max_ratio if max_ratio > 0 else 0.0
    
    score = 0.5 * fill_rate + 0.5 * (1.0 - aspect_error)
    return score


def heuristic(game: SliderMatrix) -> float:
    """
    啟發函數（用於 A* / IDA* 搜索的 h 值）
    
    h(state) = 1 - Score
    
    值域 [0, 1)，越小越接近目標，滿足可納性（admissible）。
    
    參數：
        game: SliderMatrix 實例
    
    返回：
        float: 啟發代價，已通關時返回 0
    """
    if game.is_solved():
        return 0.0
    return 1.0 - compute_score(game)


def fast_heuristic(game: SliderMatrix) -> float:
    """
    快速模式啟發函數（用於 IDA* fast_mode）
    
    加重 fill_rate 權重（0.7），降低 aspect_error 權重（0.3），
    優先聚攏方塊，更快找到可行解（不一定最優）。
    
    參數：
        game: SliderMatrix 實例
    
    返回：
        float: 啟發代價，已通關時返回 0
    """
    if game.is_solved():
        return 0.0
    
    if not game.blocks:
        return 1.0
    
    bounds = game.get_boundaries()
    H = bounds['max_row'] - bounds['min_row'] + 1
    W = bounds['max_col'] - bounds['min_col'] + 1
    K = game.m * game.n
    bb_area = H * W
    
    fill_rate = K / bb_area if bb_area > 0 else 0.0
    
    m, n = game.m, game.n
    min_dim, max_dim = min(m, n), max(m, n)
    target_ratio = max_dim / min_dim if min_dim > 0 else 1.0
    min_hw, max_hw = min(H, W), max(H, W)
    current_ratio = max_hw / min_hw if min_hw > 0 else 1.0
    max_ratio = max(current_ratio, target_ratio)
    aspect_error = abs(current_ratio - target_ratio) / max_ratio if max_ratio > 0 else 0.0
    
    score = 0.7 * fill_rate + 0.3 * (1.0 - aspect_error)
    return 1.0 - score


def is_solved_state(game: SliderMatrix) -> bool:
    """
    判斷當前是否為通關狀態
    
    參數：
        game: SliderMatrix 實例
    
    返回：
        bool
    """
    return game.is_solved()
