# -*- coding: utf-8 -*-
"""
历史记录模块

采用状态快照方式记录游戏历史，支持撤销和重做。
每条记录保存滑块布局的 0-1 矩阵和边界信息。
"""

from copy import deepcopy
from game import Block


class GameHistory:
    """
    游戏历史记录管理类
    
    属性：
        history: list[dict] - 操作历史栈，每条记录包含 matrix 和 bounds
        history_index: int - 当前位置指针
    """
    
    __slots__ = ('history', 'history_index')
    
    def __init__(self):
        """初始化历史记录"""
        self.history = []
        self.history_index = -1
    
    def save_snapshot(self, game, move_info=None):
        """
        保存当前游戏状态快照到历史记录
        
        参数：
            game: SliderMatrix 游戏对象
            move_info: dict 或 None - 移动元数据（用于撤销/重做动画）
        """
        # 更新矩阵
        game.update_matrix()
        
        # 深拷贝矩阵和边界
        snapshot = {
            'matrix': [row[:] for row in game.matrix],
            'bounds': dict(game.matrix_bounds),
            'move_info': move_info
        }
        
        # 如果当前不在历史末尾，截断后续记录
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]
        
        # 追加快照
        self.history.append(snapshot)
        self.history_index = len(self.history) - 1
        
    
    def restore_snapshot(self, game, index: int):
        """
        根据历史快照恢复游戏状态
        
        参数：
            game: SliderMatrix 游戏对象
            index: 历史记录索引
        """
        if index < 0 or index >= len(self.history):
            return
        
        snapshot = self.history[index]
        matrix = snapshot['matrix']
        bounds = snapshot['bounds']
        
        min_row = bounds['min_row']
        min_col = bounds['min_col']
        
        # 根据矩阵重建滑块列表
        game.blocks = []
        for row_idx, row in enumerate(matrix):
            for col_idx, val in enumerate(row):
                if val == 1:
                    game.blocks.append(Block([min_row + row_idx, min_col + col_idx]))
        
        # 更新游戏内部状态
        game.matrix = [r[:] for r in matrix]
        game.matrix_bounds = dict(bounds)
    
    def can_undo(self) -> bool:
        """判断是否可以撤销"""
        return self.history_index > 0
    
    def can_redo(self) -> bool:
        """判断是否可以重做"""
        return self.history_index < len(self.history) - 1
    
    def undo(self, game) -> tuple:
        """
        撤销操作
        
        参数：
            game: SliderMatrix 游戏对象
        
        返回：
            tuple: (success: bool, move_info: dict or None)
        """
        if self.can_undo():
            current_move_info = self.history[self.history_index].get('move_info')
            self.history_index -= 1
            self.restore_snapshot(game, self.history_index)
            return True, current_move_info
        return False, None
    
    def redo(self, game) -> tuple:
        """
        重做操作
        
        参数：
            game: SliderMatrix 游戏对象
        
        返回：
            tuple: (success: bool, move_info: dict or None)
        """
        if self.can_redo():
            self.history_index += 1
            target_move_info = self.history[self.history_index].get('move_info')
            self.restore_snapshot(game, self.history_index)
            return True, target_move_info
        return False, None
    
    def reset(self):
        """清空历史记录"""
        self.history = []
        self.history_index = -1
