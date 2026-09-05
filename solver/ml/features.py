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


def encode_action(action, origin=None):
    """将动作字典编码为固定 11 维向量。

    参数：
        action : dict — 必须含 gap_type/gap_line/side/move_dir
        origin : (min_row, min_col) — 可选。给定后 gap_line 编码为「相对状态
                 边界的缝隙位置」（平移不变）；None 时保持绝对坐标 /10（旧约定）。
                 人类模仿管线两端（训练/推理）必须传同一 origin 语义。
    """
    gap_h = 1.0 if action['gap_type'] == 'h' else 0.0
    gap_v = 1.0 if action['gap_type'] == 'v' else 0.0
    gap_line = action['gap_line']
    if origin is not None:
        # h 缝隙是行之间的缝 → 用行原点；v 缝隙 → 用列原点
        gap_line -= origin[0] if action['gap_type'] == 'h' else origin[1]
    gap_line = gap_line / 10.0
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


def build_human_state_features(matrix, m, n):
    """人类模仿管线的状态编码唯一入口：归一化矩阵 → 状态特征。

    在 build_state_features 基础上追加聚拢度维度（gather_score = overlap/(m*n)），
    让模型直接看到「还差几个块归位」——这是 void_block_count 权重分段的依据。

    参数：
        matrix : list[list[int]] — 以边界为原点的归一化 0/1 网格（存档 matrix）
        m, n   : 目标尺寸

    返回：np.ndarray（dim = build_state_features + 1）
    """
    from solver.ml.gather_solver import max_overlap  # 延迟导入避免循环依赖

    flat = [1 if v else 0 for row in matrix for v in row]
    pseudo = {
        'flat_grid': flat,
        'grid_rows': len(matrix),
        'grid_cols': len(matrix[0]) if matrix else 0,
        'distance': 0,
        'dist_to_bottleneck': 0,
        'in_degree': 0,
    }
    sf = build_state_features(pseudo, m, n)
    # 矩阵已是归一化网格 → 直接数 overlap（平移不变量）
    coords = frozenset((r, c) for r, row in enumerate(matrix)
                       for c, v in enumerate(row) if v)
    overlap = max_overlap(coords, m, n)
    return np.concatenate([sf, np.array([overlap / float(m * n)], dtype=np.float32)])
