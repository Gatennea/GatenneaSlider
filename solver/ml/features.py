# -*- coding: utf-8 -*-
"""
共享特征构建：状态特征向量 + 动作编码

供训练脚本和 AI 推理求解器共用，避免重复代码。
"""

import numpy as np

from solver import table_core as tc

# 网格填充参数（覆盖所有已知数据）
MAX_ROWS = 14
MAX_COLS = 15

# 方向翻转映射（用于生成负样本 / 候选动作）
DIR_FLIP = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


def pad_grid(flat_grid, rows, cols):
    """将可变尺寸网格填充到固定尺寸，返回 flatten 数组。"""
    grid = np.zeros((MAX_ROWS, MAX_COLS), dtype=np.float32)
    for r in range(min(rows, MAX_ROWS)):
        for c in range(min(cols, MAX_COLS)):
            idx = r * cols + c
            if idx < len(flat_grid):
                grid[r, c] = flat_grid[idx]
    return grid.flatten()


def build_state_features(hash_or_state, m, n, dist_to_bn=0, in_degree=0):
    """从规范化哈希解码并构建状态特征向量。

    参数：
        hash_or_state : int 或 dict — 状态哈希（从表解码）或完整的状态条目
        m, n          : 目标尺寸
        dist_to_bn    : dist_to_bottleneck（运行时可能未知，填 0）
        in_degree     : 入度（运行时可能未知，填 0）

    返回：np.ndarray (grid_padded + extra_features)
    """
    total_cells = m * n

    if isinstance(hash_or_state, dict):
        flat_grid = hash_or_state['flat_grid']
        grid_rows = hash_or_state['grid_rows']
        grid_cols = hash_or_state['grid_cols']
        distance = hash_or_state.get('distance', 0)
        dist_to_bn = hash_or_state.get('dist_to_bottleneck', 0)
        in_degree = hash_or_state.get('in_degree', 0)
    else:
        h = hash_or_state
        coords = tc.int_to_coords(h, total_cells)
        rs = [r for r, _ in coords]
        cs = [c for _, c in coords]
        mr, mc = min(rs), min(cs)
        norm = [(r - mr, c - mc) for r, c in coords]
        grid_rows = max(r for r, _ in norm) + 1
        grid_cols = max(c for _, c in norm) + 1
        flat_grid = []
        for r in range(grid_rows):
            for c in range(grid_cols):
                flat_grid.append(1 if (r, c) in norm else 0)
        distance = 0  # 运行时未知

    grid_feat = pad_grid(flat_grid, grid_rows, grid_cols)

    fill_rate = total_cells / (grid_rows * grid_cols)
    target_aspect = min(m, n) / max(m, n)
    actual_aspect = min(grid_rows, grid_cols) / max(grid_rows, grid_cols, 1)
    aspect_error = abs(actual_aspect - target_aspect)
    extra = np.array([
        fill_rate,
        aspect_error,
        distance / 18.0,
        dist_to_bn / 14.0,
        in_degree / 100.0,
    ], dtype=np.float32)

    return np.concatenate([grid_feat, extra])


def encode_action(action):
    """将动作字典编码为固定 11 维向量。"""
    gap_h = 1.0 if action['gap_type'] == 'h' else 0.0
    gap_v = 1.0 if action['gap_type'] == 'v' else 0.0
    gap_line = action['gap_line'] / 10.0
    side_above = 1.0 if action['side'] == 'above' else 0.0
    side_below = 1.0 if action['side'] == 'below' else 0.0
    side_left = 1.0 if action['side'] == 'left' else 0.0
    side_right = 1.0 if action['side'] == 'right' else 0.0
    d_w = 1.0 if action['move_dir'] == 'w' else 0.0
    d_s = 1.0 if action['move_dir'] == 's' else 0.0
    d_a = 1.0 if action['move_dir'] == 'a' else 0.0
    d_d = 1.0 if action['move_dir'] == 'd' else 0.0
    return np.array([gap_h, gap_v, gap_line,
                     side_above, side_below, side_left, side_right,
                     d_w, d_s, d_a, d_d], dtype=np.float32)
