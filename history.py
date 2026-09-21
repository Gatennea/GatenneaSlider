# -*- coding: utf-8 -*-
"""
历史记录模块

采用状态快照方式记录游戏历史，支持撤销和重做。
每条记录保存滑块布局的 0-1 矩阵和边界信息。

快照合并（省空间）：同一次选中（同一 session_key）下的连续移动只占一个
矩阵快照，逐步动作日志存进 'moves'，'steps' 记该快照覆盖的步数，
'step_total' 记到该快照为止的累计步数。撤销粒度 = 每步：首次撤销到该段时
用 moves 日志惰性拆成「一步一条」，之后走普通撤销/重做逻辑。
"""

from game import Block

_DIRS = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}


def snapshot_cells(snap) -> frozenset:
    """快照 → 绝对坐标格集 {(r, c)}"""
    bounds = snap.get('bounds', {})
    min_row = bounds.get('min_row', 0)
    min_col = bounds.get('min_col', 0)
    return frozenset(
        (min_row + i, min_col + j)
        for i, row in enumerate(snap.get('matrix', []))
        for j, v in enumerate(row) if v)


def cells_to_snapshot(cells: set) -> dict:
    """绝对坐标格集 → {matrix, bounds}（紧凑包围盒）"""
    mnr = min(r for r, _ in cells)
    mxr = max(r for r, _ in cells)
    mnc = min(c for _, c in cells)
    mxc = max(c for _, c in cells)
    matrix = [[1 if (r, c) in cells else 0 for c in range(mnc, mxc + 1)]
              for r in range(mnr, mxr + 1)]
    return {'matrix': matrix,
            'bounds': {'min_row': mnr, 'max_row': mxr,
                       'min_col': mnc, 'max_col': mxc}}


def compose_move_info(moves: list):
    """把一段连续移动合成一个动作（供撤销/重做整段位移动画）。

    选中组整体刚性平移，各块位移一致 → 合成位移 = 各步位移之和。
    单步时原样返回；多步时附 'delta'（格数）与 'merged'（步数）。
    """
    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]
    first = moves[0]
    dr = dc = 0
    same_dir = True
    for mv in moves:
        d = _DIRS.get(mv.get('direction') or '', (0, 0))
        k = mv.get('step', 1)
        dr += d[0] * k
        dc += d[1] * k
        if mv.get('direction') != first.get('direction'):
            same_dir = False
    return {
        'gap_type': first.get('gap_type'),
        'gap_line': first.get('gap_line'),
        'direction': first.get('direction') if same_dir else None,
        'step': sum(mv.get('step', 1) for mv in moves),
        'delta': [dr, dc],
        'moved_positions': first.get('moved_positions') or [],
        'merged': len(moves),
    }


def expand_snapshot_moves(prev_snap, snap) -> list:
    """快照 → [(动作前快照, 动作后快照, move_info), ...]（逐步展开）。

    合并快照只存会话末态矩阵，中间态按 moves 日志里的逐步位移重建，
    使标注数据集/训练导出仍能拿到每步的动作前矩阵。
    """
    moves = snap.get('moves')
    if not moves:
        mv = snap.get('move_info')
        return [(prev_snap, snap, mv)] if mv else []
    if len(moves) == 1:
        return [(prev_snap, snap, moves[0])]
    if not all(mv and mv.get('moved_positions') for mv in moves):
        return [(prev_snap, snap, moves[-1])]
    cells = set(snapshot_cells(prev_snap))
    out = []
    pre = prev_snap
    for i, mv in enumerate(moves):
        d = _DIRS.get(mv.get('direction') or '', (0, 0))
        k = mv.get('step', 1)
        dr, dc = d[0] * k, d[1] * k
        moved = {tuple(p) for p in mv['moved_positions']}
        cells = (cells - moved) | {(r + dr, c + dc) for r, c in moved}
        if not cells:
            break
        post = snap if i == len(moves) - 1 else cells_to_snapshot(cells)
        out.append((pre, post, mv))
        pre = post
    return out


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
    
    def save_snapshot(self, game, move_info=None, session_key=None):
        """
        保存当前游戏状态快照到历史记录

        参数：
            game: SliderMatrix 游戏对象
            move_info: dict 或 None - 移动元数据（用于撤销/重做动画）
            session_key: 选中会话标识；与末条快照相同且给了 move_info 时，
                本次移动并入该快照（只留末态矩阵 + 逐步日志），否则新开一条。
                None = 不合并（参考态、宏/求解器播放等）。
        """
        # 更新矩阵
        game.update_matrix()

        # 如果当前不在历史末尾，截断后续记录
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]

        # 编号矩阵辅助：将 game.blocks 的 number 映射到 matrix 对齐的二维表
        # 必须按位置查找：移动后 game.blocks 的顺序不再是矩阵扫描序
        def _numbers_matrix():
            num_map = {tuple(b.location): b.number for b in game.blocks}
            bounds = game.matrix_bounds
            min_row = bounds['min_row']
            min_col = bounds['min_col']
            nums = []
            for row_idx, row in enumerate(game.matrix):
                new_row = []
                for col_idx, val in enumerate(row):
                    if val == 1:
                        num = num_map.get((min_row + row_idx, min_col + col_idx))
                        new_row.append(num if num is not None else 0)
                    else:
                        new_row.append(0)
                nums.append(new_row)
            return nums

        # 合并：同一次选中的连续移动只占一个矩阵快照
        if (session_key is not None and move_info is not None and self.history
                and self.history[-1].get('session_key') == session_key):
            snap = self.history[-1]
            snap['matrix'] = [row[:] for row in game.matrix]
            snap['bounds'] = dict(game.matrix_bounds)
            snap['moves'].append(move_info)
            snap['steps'] += 1
            snap['step_total'] += 1
            snap['move_info'] = compose_move_info(snap['moves'])
            # 同步编号快照（若有）
            if any(getattr(b, 'number', None) is not None for b in game.blocks):
                snap['numbers'] = _numbers_matrix()
            else:
                snap.pop('numbers', None)
            return

        prev_total = self.history[-1].get('step_total', 0) if self.history else 0
        steps = 1 if move_info else 0
        snapshot = {
            'matrix': [row[:] for row in game.matrix],
            'bounds': dict(game.matrix_bounds),
            'move_info': move_info,
            'moves': [move_info] if move_info else [],
            'steps': steps,
            'step_total': prev_total + steps,
            'session_key': session_key,
        }
        if any(getattr(b, 'number', None) is not None for b in game.blocks):
            snapshot['numbers'] = _numbers_matrix()

        # 追加快照
        self.history.append(snapshot)
        self.history_index = len(self.history) - 1

    def step_total_at(self, index: int) -> int:
        """快照 index 处的累计步数（旧存档无该字段时退回索引值）。"""
        if index < 0 or index >= len(self.history):
            return 0
        return self.history[index].get('step_total', index)

    def current_step_total(self) -> int:
        """当前历史位置的累计步数。"""
        return self.step_total_at(self.history_index)

    
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

        if hasattr(game, 'k'):
            # 三角形密鋪：matrix 為菱形胞 2-bit 網格（bit0=▲、bit1=▼）
            game.blocks = []
            for row_idx, row in enumerate(matrix):
                for col_idx, val in enumerate(row):
                    if val & 1:
                        game.blocks.append(Block([min_row + row_idx, min_col + col_idx, True]))
                    if val & 2:
                        game.blocks.append(Block([min_row + row_idx, min_col + col_idx, False]))
        else:
            # 根據矩陣重建滑塊列表
            game.blocks = []
            for row_idx, row in enumerate(matrix):
                for col_idx, val in enumerate(row):
                    if val == 1:
                        game.blocks.append(Block([min_row + row_idx, min_col + col_idx]))
        
        # 恢复编号信息（若有）
        numbers = snapshot.get('numbers')
        if numbers:
            num_map = {}
            for row_idx, row in enumerate(numbers):
                for col_idx, val in enumerate(row):
                    if val != 0:
                        r = min_row + row_idx
                        c = min_col + col_idx
                        num_map[(r, c)] = val
            for block in game.blocks:
                block.number = num_map.get(tuple(block.location))
        
        # 更新游戏内部状态
        game.matrix = [r[:] for r in matrix]
        game.matrix_bounds = dict(bounds)
    
    def can_undo(self) -> bool:
        """判断是否可以撤销"""
        return self.history_index > 0

    def can_redo(self) -> bool:
        """判断是否可以重做"""
        return self.history_index < len(self.history) - 1

    def _ensure_step_granularity(self, index: int) -> int:
        """若快照 index 覆盖多步，就地拆成「一步一条」（惰性），返回段末索引。

        合并快照只存段末矩阵，而撤销/重做要按步进行：首次撤销到该段时，
        用 moves 日志重建中间态，把它展开成多条单步快照，之后走普通逻辑。
        """
        if index <= 0 or index >= len(self.history):
            return index
        snap = self.history[index]
        if snap.get('steps', 1) <= 1:
            return index
        expanded = expand_snapshot_moves(self.history[index - 1], snap)
        if len(expanded) <= 1:
            return index
        base_total = self.step_total_at(index - 1)
        new_snaps = []
        for k, (_pre, post, mv) in enumerate(expanded):
            new_snaps.append({
                'matrix': [row[:] for row in post['matrix']],
                'bounds': dict(post['bounds']),
                'move_info': mv,
                'moves': [mv],
                'steps': 1,
                'step_total': base_total + k + 1,
                'session_key': None,
            })
        self.history[index:index + 1] = new_snaps
        return index + len(new_snaps) - 1

    def peek_undo(self):
        """「下一次撤销将回退的那一步」的 move_info（顺带把合并段惰性展开）。

        供 GUI 提前拿到单步动作做撤销动画；无步可撤时返回 None。
        """
        self.history_index = self._ensure_step_granularity(self.history_index)
        if self.history_index <= 0:
            return None
        return self.history[self.history_index].get('move_info')

    def peek_redo(self):
        """「下一次重做将前进的那一步」的 move_info（顺带把目标段惰性展开）。"""
        nxt = self.history_index + 1
        if nxt >= len(self.history):
            return None
        if self.history[nxt].get('steps', 1) > 1:
            self._ensure_step_granularity(nxt)
        return self.history[nxt].get('move_info')

    def undo(self, game) -> tuple:
        """
        撤销操作（每次一步；合并快照先惰性展开成单步）

        参数：
            game: SliderMatrix 游戏对象

        返回：
            tuple: (success: bool, move_info: dict or None)
        """
        if not self.can_undo():
            return False, None
        self.history_index = self._ensure_step_granularity(self.history_index)
        if self.history_index <= 0:
            return False, None
        current_move_info = self.history[self.history_index].get('move_info')
        self.history_index -= 1
        self.restore_snapshot(game, self.history_index)
        return True, current_move_info

    def redo(self, game) -> tuple:
        """
        重做操作（每次一步；目标段为合并快照时先惰性展开）

        参数：
            game: SliderMatrix 游戏对象

        返回：
            tuple: (success: bool, move_info: dict or None)
        """
        if not self.can_redo():
            return False, None
        nxt = self.history_index + 1
        if self.history[nxt].get('steps', 1) > 1:
            self._ensure_step_granularity(nxt)
        self.history_index += 1
        target_move_info = self.history[self.history_index].get('move_info')
        self.restore_snapshot(game, self.history_index)
        return True, target_move_info
    
    def reset(self):
        """清空历史记录"""
        self.history = []
        self.history_index = -1
