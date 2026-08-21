# -*- coding: utf-8 -*-
"""
動作枚舉與執行模塊

提供：
    Action                      - 動作類型 (gap_dir, gap_line, side, move_dir)
    enumerate_valid_actions()   - 枚舉所有合法動作
    apply_action()              - 在遊戲上執行一個動作（純邏輯，無 GUI）
    is_inverse_action()         - 判斷兩個動作是否互為逆操作
"""

from game import SliderMatrix

# Action 類型：(gap_direction, gap_line, select_side, move_direction)
# gap_direction: 'h' (水平縫隙) 或 'v' (垂直縫隙)
# gap_line: 縫隙位置的行/列索引（整數）
# select_side: 'above'/'below' (對 h) 或 'left'/'right' (對 v)
# move_direction: 'w'/'s'/'a'/'d'，必須垂直於 gap_direction
Action = tuple


def _get_side_blocks(game: SliderMatrix, gap_dir: str, gap_line: int, side: str) -> list:
    """
    獲取在分割線指定側的所有方塊
    
    參數：
        game: SliderMatrix 實例
        gap_dir: 'h' 或 'v'
        gap_line: 分割線位置
        side: 'above'/'below' (h) 或 'left'/'right' (v)
    
    返回：
        list[Block]: 目標側的方塊列表
    """
    result = []
    for b in game.blocks:
        if gap_dir == 'h':
            if side == 'above' and b.location[0] <= gap_line:
                result.append(b)
            elif side == 'below' and b.location[0] > gap_line:
                result.append(b)
        else:  # 'v'
            if side == 'left' and b.location[1] <= gap_line:
                result.append(b)
            elif side == 'right' and b.location[1] > gap_line:
                result.append(b)
    return result


def enumerate_valid_actions(game: SliderMatrix, step: int) -> list[Action]:
    """
    枚舉當前狀態下所有合法的動作
    
    合法動作 = 有效縫隙 × 2 側 × 2 移動方向
    
    參數：
        game: SliderMatrix 實例
        step: 移動步長
    
    返回：
        list[Action]: 合法動作列表，每個為 (gap_dir, gap_line, side, move_dir)
    """
    actions = []
    
    if not game.blocks:
        return actions
    
    bounds = game.get_boundaries()
    
    # 水平縫隙 (h): 在兩行之間，只能左右移動
    for line in range(bounds['min_row'], bounds['max_row']):
        if game.is_valid_h_line(line):
            for side in ('above', 'below'):
                for move_dir in ('a', 'd'):
                    actions.append(('h', line, side, move_dir))
    
    # 垂直縫隙 (v): 在兩列之間，只能上下移動
    for line in range(bounds['min_col'], bounds['max_col']):
        if game.is_valid_v_line(line):
            for side in ('left', 'right'):
                for move_dir in ('w', 's'):
                    actions.append(('v', line, side, move_dir))
    
    return actions


def apply_action(game: SliderMatrix, action: Action, step: int) -> bool:
    """
    在遊戲上執行一個動作（純邏輯，無 GUI 依賴）
    
    流程：
        1. 清除舊選中狀態
        2. 在目標側找一個代表方塊
        3. 調用 opt() 選中該側連通方塊組
        4. 調用 try_move() 逐步驗證並獲取最終位置
        5. 若合法，commit_move()
    
    參數：
        game: SliderMatrix 實例（會被原地修改）
        action: (gap_dir, gap_line, side, move_dir)
        step: 移動步長
    
    返回：
        bool: 成功返回 True，失敗返回 False
    """
    gap_dir, gap_line, side, move_dir = action
    
    # 1. 清除舊選中狀態
    for b in game.blocks:
        b.be_opted = False
    
    # 2. 確定一個在目標側的 representative block
    side_blocks = _get_side_blocks(game, gap_dir, gap_line, side)
    if not side_blocks:
        return False
    representative = side_blocks[0]
    
    # 3. 調用 opt() 選中該側連通方塊組
    game.opt(gap_dir, gap_line, representative)
    
    # 4. 調用 try_move() 逐步驗證並獲取最終位置
    final_positions = game.try_move(move_dir, step)
    if not final_positions:
        # 清除選中狀態後返回失敗
        for b in game.blocks:
            b.be_opted = False
        return False
    
    # 5. 提交移動
    game.commit_move(final_positions)
    
    # 6. 清除選中狀態
    for b in game.blocks:
        b.be_opted = False
    
    return True


def is_inverse_action(a1: Action, a2: Action) -> bool:
    """
    判斷 a2 是否是 a1 的逆操作
    
    逆操作條件：
    - 同一條縫隙
    - 選中同一組方塊（同一側）
    - 移動方向相反
    
    參數：
        a1, a2: Action 元組
    
    返回：
        bool: 互為逆操作返回 True
    """
    gd1, gl1, ss1, md1 = a1
    gd2, gl2, ss2, md2 = a2
    
    if gd1 != gd2 or gl1 != gl2 or ss1 != ss2:
        return False
    
    inverse_pairs = {('w', 's'), ('s', 'w'), ('a', 'd'), ('d', 'a')}
    return (md1, md2) in inverse_pairs
