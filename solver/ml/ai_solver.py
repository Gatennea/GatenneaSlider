# -*- coding: utf-8 -*-
r"""
AI 推理求解器 — 加载预训练的评分模型，沿最高分动作逐步求解

接口签名与 table_solve / ida_star_solve 一致，可直接接入 GUI 的 SOLVER_ALGORITHMS。

依赖：
    solver/ml/models/{m}_{n}_{step}/model_ranker.pkl  — 预训练评分模型
    solver/table_core.py                              — 状态规范化 + 候选动作生成

运行：
    # 在 GUI 中选择「智能求解」即可自动调用
    # 或通过 CLI 测试：
    D:\python\python.exe -c "from solver.ml.ai_solver import ai_solve; ..."
"""

import os
import pickle
import numpy as np

from solver import table_core as tc
from solver.ml.features import build_state_features, encode_action

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
_MAX_STEPS = 500  # 最大求解步数
_model_cache = {}  # (m, n, step) → {'mlp': ..., 'scaler': ...}


def _get_model_path(m, n, step):
    return os.path.join(_MODELS_DIR, f'{m}_{n}_{step}', 'model_ranker.pkl')


def load_ai_model(m, n, step):
    """加载预训练的评分模型（带缓存）。"""
    key = (m, n, step)
    if key in _model_cache:
        return _model_cache[key]

    path = _get_model_path(m, n, step)
    if not os.path.exists(path):
        return None

    with open(path, 'rb') as f:
        data = pickle.load(f)
    _model_cache[key] = data
    return data


# ---------------------------------------------------------------------------
# 推理主函数
# ---------------------------------------------------------------------------
def ai_solve(game, step: int, cancel_check=None, progress_callback=None):
    """
    AI 智能求解：每一步用评分模型选择最高分动作。

    参数：
        game   : SliderMatrix 实例
        step   : 移动步长
        cancel_check : callable → bool，返回 True 时取消
        progress_callback : callable(dict)，接收进度信息

    返回：
        (actions, rep_cells)  — 成功
        []                    — 已是目标状态
        None                  — 无模型 / 无法求解 / 取消
    """
    if not game.blocks:
        return None

    m, n = game.m, game.n
    total = m * n

    # 加载模型
    model_data = load_ai_model(m, n, step)
    if model_data is None:
        return None  # 无模型 — GUI 会显示「未找到解法」

    mlp = model_data['mlp']
    scaler = model_data['scaler']

    actions = []
    rep_cells = []
    visited = set()      # canonical hash
    visited_raw = set()  # 原始排序坐标（绝对位置去重）

    for i in range(_MAX_STEPS):
        if cancel_check and cancel_check():
            return None

        if game.is_solved():
            break

        if progress_callback:
            progress_callback({'step': i + 1, 'total': _MAX_STEPS})

        # 获取当前状态坐标，循环检测（用排序元组确认真实重复）
        coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        cur_hash = tc.canonicalize(coords)
        coords_sorted = tuple(sorted(coords))
        if coords_sorted in visited_raw:
            break  # 真正重复，放弃
        visited_raw.add(coords_sorted)
        visited.add(cur_hash)

        # 构建特征
        # 归一到原点，构造 flat_grid
        rs = [r for r, _ in coords]
        cs = [c for _, c in coords]
        mr, mc = min(rs), min(cs)
        norm = frozenset((r - mr, c - mc) for r, c in coords)
        norm_rs = [r for r, _ in norm]
        norm_cs = [c for _, c in norm]
        grid_rows = max(norm_rs) + 1
        grid_cols = max(norm_cs) + 1
        flat_grid = []
        for r in range(grid_rows):
            for c in range(grid_cols):
                flat_grid.append(1 if (r, c) in norm else 0)

        pseudo_state = {
            'flat_grid': flat_grid,
            'grid_rows': grid_rows,
            'grid_cols': grid_cols,
            'distance': 0,
            'dist_to_bottleneck': 0,
            'in_degree': 0,
        }
        state_feat = build_state_features(pseudo_state, m, n)

        # 枚举所有候选动作（用绝对坐标，确保 gap_line 匹配游戏坐标）
        candidates = tc.forward_neighbors_with_actions(coords, step, total)
        if not candidates:
            break

        # 对每个候选评分，按分数降序尝试
        scored = []
        for nb_hash, action in candidates:
            action_feat = encode_action({
                'gap_type': action[0],
                'gap_line': action[1],
                'side': action[2],
                'move_dir': action[3],
            })
            feat = np.concatenate([state_feat, action_feat]).reshape(1, -1)
            feat_scaled = scaler.transform(feat)
            score = float(mlp.predict(feat_scaled)[0])
            scored.append((score, nb_hash, action))
        scored.sort(key=lambda x: -x[0])  # 降序

        # 按分数从高到低尝试，直到有一个可执行且不回到已访问状态
        ok = False
        for best_score, best_nb_hash, best_action in scored:
            # 跳过会回到已访问状态的候选
            if best_nb_hash in visited:
                continue
            ok, rep = _apply_and_verify(game, best_action, step, best_nb_hash, total)
            if ok:
                actions.append(best_action)
                rep_cells.append(rep)
                if progress_callback:
                    progress_callback({
                        'step': i + 1, 'total': _MAX_STEPS,
                        'candidates': len(scored), 'score': best_score,
                    })
                break

        if not ok:
            break  # 所有候选都不可执行，放弃

    if game.is_solved():
        return actions, rep_cells
    return None


def _apply_and_verify(game, action, step, target_hash, total):
    """用游戏原生 API 执行动作，验证结果哈希。"""
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
        for b in game.blocks:
            b.be_opted = False
        return True, rep_cell

    return False, None
