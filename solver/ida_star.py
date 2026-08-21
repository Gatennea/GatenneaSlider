# -*- coding: utf-8 -*-
"""
IDA* 求解器模塊

提供：
    ida_star_solve(game, step, max_depth, cancel_check, progress_callback)
        - IDA* 主求解函數，支援取消和中途進度回調

算法特點：
    - IDA*（迭代加深 A*）：從 bound=ceil(h0) 開始，逐層加深
    - Transposition Table：避免重複搜索相同狀態
    - 動作排序：優先嘗試啟發值最低（最有希望）的動作
    - 逆向動作過濾：禁止連續兩步互為逆操作
    - 階段性分段搜索：G1（聚攏）→ G2（整形目標矩形）
    - 取消支援：cancel_check() 返回 True 時中止搜索
    - 進度回調：progress_callback(info) 報告當前搜索狀態
"""

import time
from copy import deepcopy

from game import SliderMatrix
from solver.state import state_key, snapshot, restore
from solver.actions import enumerate_valid_actions, apply_action, is_inverse_action
from solver.heuristic import heuristic, fast_heuristic, is_solved_state


FOUND = 0
INF = float('inf')
CANCELLED = -1

# 單次迭代最大節點數限制（防止個別難例耗時過長）
MAX_NODES_PER_ITER = 200000
# fast_mode 參數
FAST_MAX_NODES_PER_ITER = 50000
FAST_TIME_LIMIT = 15.0
FAST_ACTION_SAMPLE = 15  # 動作排序時只預覽前 N 個


# ---------------- 階段 G1：聚攏 -----------------
def _fill_rate_heuristic(game: SliderMatrix) -> float:
    if not game.blocks:
        return 1.0
    bounds = game.get_boundaries()
    H = bounds['max_row'] - bounds['min_row'] + 1
    W = bounds['max_col'] - bounds['min_col'] + 1
    K = game.m * game.n
    bb_area = H * W
    fill_rate = K / bb_area if bb_area > 0 else 0.0
    return 1.0 - fill_rate


def _is_g1_goal(game: SliderMatrix) -> bool:
    if not game.blocks:
        return False
    bounds = game.get_boundaries()
    bb_area = (bounds['max_row'] - bounds['min_row'] + 1) * \
              (bounds['max_col'] - bounds['min_col'] + 1)
    return bb_area == game.m * game.n


def _sort_actions_by_heuristic(game: SliderMatrix, step: int,
                                actions: list, h_func, sample_size: int = None) -> list:
    """按啟發值排序動作：優先嘗試最有希望的動作。
       若 sample_size 指定，只預覽前 sample_size 個（其餘保持原序）。"""
    if sample_size is not None and len(actions) > sample_size:
        sampled = actions[:sample_size]
        rest = actions[sample_size:]
    else:
        sampled = actions
        rest = []
    
    scored = []
    for action in sampled:
        saved = snapshot(game)
        if not apply_action(game, action, step):
            restore(game, saved)
            continue
        h_val = h_func(game)
        restore(game, saved)
        scored.append((h_val, action))
    
    scored.sort(key=lambda x: x[0])
    return [a for _, a in scored] + rest


# ---------------- IDA* 核心搜索 -----------------
def _search(game: SliderMatrix, step: int, g: int, bound: int,
            path: list, tt: dict, h_func, goal_func,
            nodes_visited: list, start_time: float, time_limit: float,
            cancel_check=None, progress_callback=None,
            progress_ctx: dict = None,
            max_nodes: int = MAX_NODES_PER_ITER,
            action_sample_size: int = None) -> tuple:
    """
    IDA* 遞歸搜索（帶取消檢查和進度回調）

    參數：
        cancel_check: callable() → bool，返回 True 表示取消
        progress_callback: callable(info_dict)，搜索進度回調
        progress_ctx: progress_callback 的上下文共用字典
        max_nodes: 單次迭代最大節點數
        action_sample_size: 動作排序時預覽取樣數（None=全部）
    """
    # 取消檢查
    if cancel_check and cancel_check():
        return CANCELLED, None
    
    # 超時檢查
    if time.time() - start_time > time_limit:
        return INF, None
    
    # 節點限制檢查
    nodes_visited[0] += 1
    if nodes_visited[0] > max_nodes:
        return INF, None
    
    # 進度回調（每 5000 節點或深度變化時報告）
    if progress_callback and progress_ctx is not None:
        progress_ctx['total_nodes'] += 1
        if progress_ctx['total_nodes'] % 5000 == 0:
            elapsed = time.time() - start_time
            progress_callback({
                'depth': g,
                'bound': bound,
                'nodes': progress_ctx['total_nodes'],
                'path_len': len(path),
                'path_preview': _format_path_preview(path),
                'elapsed': elapsed,
                'stage': progress_ctx.get('stage', ''),
            })
    
    f = g + h_func(game)
    if f > bound:
        return f, None
    
    key = state_key(game)
    if key in tt and tt[key] <= g:
        return INF, None
    tt[key] = g
    
    if goal_func(game):
        return FOUND, path[:]
    
    valid_actions = enumerate_valid_actions(game, step)
    filtered = [a for a in valid_actions
                if not path or not is_inverse_action(path[-1], a)]
    sorted_actions = _sort_actions_by_heuristic(game, step, filtered, h_func,
                                                sample_size=action_sample_size)
    
    min_cost = INF
    
    for action in sorted_actions:
        # 每個動作前檢查取消
        if cancel_check and cancel_check():
            return CANCELLED, None
        
        snap = snapshot(game)
        
        if not apply_action(game, action, step):
            restore(game, snap)
            continue
        
        cost, sol = _search(game, step, g + 1, bound, path + [action],
                            tt, h_func, goal_func, nodes_visited, start_time, time_limit,
                            cancel_check, progress_callback, progress_ctx,
                            max_nodes=max_nodes, action_sample_size=action_sample_size)
        
        restore(game, snap)
        
        if cost == FOUND:
            return FOUND, sol
        if cost == CANCELLED:
            return CANCELLED, None
        if cost < min_cost:
            min_cost = cost
    
    return min_cost, None


def _format_path_preview(path: list) -> str:
    """將路徑格式化為簡短的可讀字串（用於進度顯示）"""
    if not path:
        return ''
    # 只取最後 3 步
    recent = path[-3:]
    parts = []
    for action in recent:
        gap_dir, gap_line, side, move_dir = action
        side_short = {'above': '上', 'below': '下', 'left': '左', 'right': '右'}.get(side, side)
        dir_short = {'w': '↑', 's': '↓', 'a': '←', 'd': '→'}.get(move_dir, move_dir)
        parts.append(f"{gap_dir}{gap_line}{side_short}{dir_short}")
    return ' '.join(parts)


# ---------------- 主求解函數 -----------------
def ida_star_solve(game: SliderMatrix, step: int, max_depth: int = 120,
                   cancel_check=None, progress_callback=None,
                   fast_mode: bool = False) -> list | None:
    """
    求解器主函數（IDA* + 動作排序 + 兩階段搜索）

    參數：
        game: SliderMatrix 實例
        step: 移動步長
        max_depth: 最大搜索深度（default 120）
        cancel_check: callable() → bool，返回 True 取消搜索
        progress_callback: callable(info_dict)，進度回調
        fast_mode: 快速模式（不保證最優解，但更快找到可行解）

    返回：
        list[Action] | None
    """
    game_copy = deepcopy(game)
    
    if game_copy.is_solved():
        return []
    
    progress_ctx = {'total_nodes': 0, 'stage': ''}
    
    # ---- 階段 G1：聚攏 ----
    if not _is_g1_goal(game_copy):
        progress_ctx['stage'] = 'G1'
        g1_solution = _single_stage_solve(
            game_copy, step, max_depth,
            _fill_rate_heuristic, _is_g1_goal,
            cancel_check, progress_callback, progress_ctx,
            fast_mode=fast_mode
        )
        if g1_solution is None:
            return None
        if g1_solution == CANCELLED:
            return None
        
        for action in g1_solution:
            ok = apply_action(game_copy, action, step)
            if not ok:
                return None
    else:
        g1_solution = []
    
    # ---- 階段 G2：整形 ----
    if game_copy.is_solved():
        return g1_solution
    
    progress_ctx['stage'] = 'G2'
    # fast_mode 使用不同的啟發函數（加重 fill_rate 權重）
    h_func = fast_heuristic if fast_mode else heuristic
    g2_solution = _single_stage_solve(
        game_copy, step, max_depth,
        h_func, is_solved_state,
        cancel_check, progress_callback, progress_ctx,
        fast_mode=fast_mode
    )
    if g2_solution is None:
        return None
    if g2_solution == CANCELLED:
        return None
    
    return g1_solution + g2_solution


def _single_stage_solve(game: SliderMatrix, step: int, max_depth: int,
                        h_func, goal_func,
                        cancel_check=None, progress_callback=None,
                        progress_ctx: dict = None,
                        fast_mode: bool = False) -> list | None:
    """
    單階段 IDA* 求解
    
    參數：
        fast_mode: 快速模式（bound 每次 +2、更低的節點/時間限制）
    """
    import math
    
    h0 = h_func(game)
    bound = max(1, int(math.ceil(h0)))
    
    if fast_mode:
        time_limit = FAST_TIME_LIMIT
        max_nodes = FAST_MAX_NODES_PER_ITER
        action_sample_size = FAST_ACTION_SAMPLE
        bound_increment = 2
    else:
        time_limit = 60.0
        max_nodes = MAX_NODES_PER_ITER
        action_sample_size = None
        bound_increment = 1
    
    while bound <= max_depth:
        # 檢查取消
        if cancel_check and cancel_check():
            return CANCELLED
        
        tt = {}
        nodes_visited = [0]
        start_time = time.time()
        
        # 進度回調：新深度層開始
        if progress_callback and progress_ctx is not None:
            progress_ctx['total_nodes'] = 0
            progress_callback({
                'depth': 0,
                'bound': bound,
                'nodes': 0,
                'path_len': 0,
                'path_preview': f'搜索深度 {bound}...',
                'elapsed': 0,
                'stage': progress_ctx.get('stage', ''),
            })
        
        cost, solution = _search(game, step, 0, bound, [], tt,
                                 h_func, goal_func, nodes_visited,
                                 start_time, time_limit,
                                 cancel_check, progress_callback, progress_ctx,
                                 max_nodes=max_nodes,
                                 action_sample_size=action_sample_size)
        
        elapsed = time.time() - start_time
        
        if cost == FOUND:
            return solution
        if cost == CANCELLED:
            return CANCELLED
        
        if cost == INF or elapsed >= time_limit:
            pass
        
        bound += bound_increment
    
    return None
