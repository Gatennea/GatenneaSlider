# -*- coding: utf-8 -*-
"""
基于预建 BFS 距离表的查表求解器

从 solver/data/{m}_{n}_{step}/table.pkl 加载距离表，通过沿 dist-1
邻居逐步走回目标状态，重构出最短 Action 序列。

作为 SOLVER_ALGORITHMS 中的第四种算法（'table'），可直接在 GUI 中选用。
"""

import os
import sys
import pickle
from solver import table_core as tc


# ---------------------------------------------------------------------------
# 表加载
# ---------------------------------------------------------------------------
_table_cache = {}  # (m, n, step) → dict[int, int]


def _get_data_dir():
    """获取 solver/data/ 目录路径，兼容 PyInstaller 打包环境"""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        return os.path.join(base, 'solver', 'data')
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def load_table(m, n, step):
    """加载距离表（带缓存）。优先 table.pkl，建表中回退 checkpoint.pkl。"""
    key = (m, n, step)
    if key in _table_cache:
        return _table_cache[key]
    data_dir = os.path.join(_get_data_dir(), f'{m}_{n}_{step}')
    # 优先成品表，其次断点表
    for fname in ('table.pkl', 'checkpoint.pkl'):
        path = os.path.join(data_dir, fname)
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = pickle.load(f)
            tbl = data if fname == 'table.pkl' else data['dist']
            _table_cache[key] = tbl
            return tbl
    return None


# ---------------------------------------------------------------------------
# 求解器主函数
# ---------------------------------------------------------------------------
def table_solve(game, step: int, cancel_check=None, progress_callback=None):
    """
    查表求解：从当前游戏状态出发，沿预建距离表的最短距离走回目标。

    参数：
        game   : SliderMatrix 实例
        step   : 移动步长
        cancel_check : callable → bool，返回 True 时取消求解
        progress_callback : callable(dict)，接收进度信息

    返回：
        list[Action] | None | False  — 成功返回 Action 列表；表文件不存在返回 None；
                                       状态不在表中/求解失败返回 False；
                                       已是目标返回空列表 []
    """
    # 1. 获取当前坐标
    if not game.blocks:
        return None
    coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
    m, n = game.m, game.n
    total = m * n

    # 2. 规范化并查表
    cur_h = tc.canonicalize(coords)
    table = load_table(m, n, step)
    if table is None:
        return None  # 表文件不存在 → 未找到数据库
    if cur_h not in table:
        return False  # 状态不在表中（死局或表未覆盖）
    distance = table[cur_h]
    if distance == 0:
        return []  # 已是目标状态

    # 3. 沿 dist-1 邻居逐步走回目标
    path = []
    rep_cells = []

    for i in range(distance):
        if cancel_check and cancel_check():
            return None

        if progress_callback:
            remaining = distance - i
            progress_callback({
                'step': i + 1, 'total': distance, 'distance_remaining': remaining,
            })

        cur_coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        found = False
        for nb_h, action in tc.forward_neighbors_with_actions(cur_coords, step, total):
            if nb_h in table and table[nb_h] == table[cur_h] - 1:
                ok, rep = _apply_action_to_target(game, action, step, nb_h, total)
                if not ok:
                    continue
                path.append(action)
                rep_cells.append(rep)
                cur_h = nb_h
                found = True
                break

        if not found:
            return False

    return path, rep_cells


def _apply_action_to_target(game, action, step, target_hash, total):
    """用游戏原生 opt()+try_move()+commit_move() 执行 Action，
    返回 (True, rep_cell) 成功时附带代表方块坐标，失败返回 (False, None)。"""
    from solver.table_core import _side_components, canonicalize, is_single_connected

    gap_type, gap_line, side, move_dir = action
    cur_coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)

    for comp in _side_components(cur_coords, gap_type, gap_line, side):
        for b in game.blocks:
            b.be_opted = False
        rep_cell = next(iter(comp))
        rep_block = None
        for b in game.blocks:
            if (b.location[0], b.location[1]) == rep_cell:
                rep_block = b
                break
        if rep_block is None:
            continue

        game.opt(gap_type, gap_line, rep_block)
        final_positions = game.try_move(move_dir, step)
        if not final_positions:
            continue

        selected = [b for b in game.blocks if b.be_opted]
        test_coords = []
        for b in game.blocks:
            if b.be_opted:
                idx = selected.index(b)
                test_coords.append(tuple(final_positions[idx]))
            else:
                test_coords.append(tuple(b.location))
        if len(test_coords) != total:
            continue
        if not is_single_connected(test_coords):
            continue
        if canonicalize(frozenset(test_coords)) != target_hash:
            continue

        game.commit_move(final_positions)
        for b in game.blocks: b.be_opted = False
        return True, rep_cell

    return False, None
