# -*- coding: utf-8 -*-
"""
狀態編碼與快照模塊

提供：
    state_key(game)       - 狀態唯一標識（歸一化的 frozenset）
    encode_state(game)     - 6 維特徵向量
    snapshot(game)         - 狀態快照保存
    restore(game, snap)    - 狀態快照恢復
"""

import math
from game import Block, SliderMatrix


def state_key(game: SliderMatrix) -> frozenset:
    """
    獲取當前狀態的唯一標識
    
    將方塊位置歸一化（平移至原點），使相同形狀不同位置的佈局
    映射到同一狀態鍵，用於 Transposition Table 去重。
    
    參數：
        game: SliderMatrix 實例
    
    返回：
        frozenset: 歸一化後的 (row, col) 位置集合
    """
    if not game.blocks:
        return frozenset()
    
    bounds = game.get_boundaries()
    min_r, min_c = bounds['min_row'], bounds['min_col']
    
    normalized = frozenset(
        (b.location[0] - min_r, b.location[1] - min_c)
        for b in game.blocks
    )
    return normalized


def encode_state(game: SliderMatrix, step: int = None) -> list:
    """
    提取緊湊狀態特徵向量（6 維）
    
    StateVec = [m, n, step, fill_rate, aspect_error, dispersion]
    
    參數：
        game: SliderMatrix 實例
        step: 步長（可選，若為 None 則傳入 0）
    
    返回：
        list: [m, n, step, fill_rate, aspect_error, dispersion]
    """
    m, n = game.m, game.n
    
    if not game.blocks:
        return [m, n, step or 0, 0.0, 1.0, 0.0]
    
    bounds = game.get_boundaries()
    H = bounds['max_row'] - bounds['min_row'] + 1
    W = bounds['max_col'] - bounds['min_col'] + 1
    K = m * n
    bb_area = H * W
    
    # fill_rate
    fill_rate = K / bb_area if bb_area > 0 else 0.0
    
    # aspect_error
    target_ratio = max(m, n) / min(m, n) if min(m, n) > 0 else 1.0
    current_ratio = max(W, H) / min(H, W) if min(H, W) > 0 else 1.0
    max_ratio = max(current_ratio, target_ratio)
    aspect_error = abs(current_ratio - target_ratio) / max_ratio if max_ratio > 0 else 0.0
    
    # dispersion
    rows = [b.location[0] for b in game.blocks]
    cols = [b.location[1] for b in game.blocks]
    
    if len(rows) > 1:
        mean_r = sum(rows) / len(rows)
        mean_c = sum(cols) / len(cols)
        var_r = sum((r - mean_r) ** 2 for r in rows) / len(rows)
        var_c = sum((c - mean_c) ** 2 for c in cols) / len(cols)
        dispersion = math.sqrt(var_r) + math.sqrt(var_c)
    else:
        dispersion = 0.0
    
    return [float(m), float(n), float(step or 0), fill_rate, aspect_error, dispersion]


def snapshot(game: SliderMatrix) -> dict:
    """
    保存遊戲狀態快照（用於搜索回溯）
    
    參數：
        game: SliderMatrix 實例
    
    返回：
        dict: 包含 m, n, blocks 位置列表
    """
    return {
        'm': game.m,
        'n': game.n,
        'blocks': [(b.location[0], b.location[1]) for b in game.blocks]
    }


def restore(game: SliderMatrix, snap: dict):
    """
    從快照恢復遊戲狀態（用於搜索回溯）

    **原地恢復**（2026-10-17 深夜優化）：舊實現每呼叫都新建全部 Block
    （`Block([r, c])` × K）+ 全量重建矩陣；求解熱路徑裡「套用→打分→恢復」
    每個候選動作一次，8×8 實測 Block.__init__ 被調 25 萬次。改為就地改寫
    既有 Block 的 location（塊數一致時），並把瞬態槽位清零到與新 Block
    等價的狀態（be_opted=False、number=None——與舊實現新建 Block 的預設值
    逐字一致，觀察行為不變）；塊數不一致（理論不發生）才走重建分支。
    矩陣仍照舊 eager 重建（呼叫方約定恢復後 matrix 可用，不改變語義）。
    """
    game.m = snap['m']
    game.n = snap['n']
    blocks = game.blocks
    snap_blocks = snap['blocks']
    if blocks is not None and len(blocks) == len(snap_blocks):
        for b, loc in zip(blocks, snap_blocks):
            b.location[0] = loc[0]
            b.location[1] = loc[1]
            b.be_opted = False
            b.number = None
    else:
        game.blocks = [Block([r, c]) for r, c in snap_blocks]
    game.matrix = None
    game.update_matrix()
