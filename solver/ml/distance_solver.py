# -*- coding: utf-8 -*-
r"""
距离预测求解器 — 用训练好的「剩余步数」模型做贪心搜索

思路：
    训练模型预测「从当前状态到还原还需要多少步」（即启发值/距离）。
    求解时枚举所有候选动作，对每个结果状态预测剩余距离，选预测距离最小的动作。
    这与 EMD 贪心同构，只是把 EMD 换成神经网络预测的距离。

模型：
    solver/ml/models/{m}_{n}_{step}/distance_model.pkl
    由 solver.ml.train_distance 训练，内含 {'mlp': MLPRegressor, 'scaler': StandardScaler}。

接口与 table_solve / strategy_solve 一致：
    distance_solve(game, step, max_steps, cancel_check, progress_callback)
    返回 (actions, rep_cells) 或 False / None。

运行测试：
    D:\python\python.exe -m solver.ml.distance_solver [m n step]
"""

import os
import sys
import time
import pickle
import random

import numpy as np

from game import SliderMatrix
from solver.actions import enumerate_valid_actions, apply_action
from solver.state import snapshot, restore
from solver.table_core import canonicalize
from solver.ml.train_distance import build_features
from solver.ml.strategy_solver import _find_rep_cell

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')

_model_cache = {}  # (m, n, step) -> {'mlp': ..., 'scaler': ...} | None


# ---------------------------------------------------------------------------
# 模型加载
# ---------------------------------------------------------------------------
def load_distance_model(m, n, step):
    """加载距离预测模型（带缓存）。找不到模型返回 None。"""
    key = (m, n, step)
    if key in _model_cache:
        return _model_cache[key]

    path = os.path.join(MODELS_DIR, f'{m}_{n}_{step}', 'distance_model.pkl')
    if not os.path.exists(path):
        # 回退到 4_4_2 多尺寸模型：训练数据包含 4x4~9x9 人类记录，且特征含尺寸 m/n，
        # 因此该模型可作为其它尺寸的距离估计（精度随尺寸增大而下降）。
        fallback = os.path.join(MODELS_DIR, '4_4_2', 'distance_model.pkl')
        if os.path.exists(fallback):
            with open(fallback, 'rb') as f:
                data = pickle.load(f)
            _model_cache[key] = data
            return data
        _model_cache[key] = None
        return None

    with open(path, 'rb') as f:
        data = pickle.load(f)
    _model_cache[key] = data
    return data


# ---------------------------------------------------------------------------
# 特征 / 预测
# ---------------------------------------------------------------------------
def _game_to_flat(game):
    """把当前游戏方块归一化（平移至原点）为 flat_grid 和 (rows, cols)。"""
    coords = [(b.location[0], b.location[1]) for b in game.blocks]
    if not coords:
        return None, 0, 0
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    mr, mc = min(rs), min(cs)
    norm = [(r - mr, c - mc) for r, c in coords]
    rows = max(r for r, _ in norm) + 1
    cols = max(c for _, c in norm) + 1
    flat = [0] * (rows * cols)
    for r, c in norm:
        flat[r * cols + c] = 1
    return flat, rows, cols


def predict_distance(game, model):
    """预测当前状态到还原的剩余步数。"""
    flat, rows, cols = _game_to_flat(game)
    if flat is None:
        return float('inf')
    feat = build_features(flat, rows, cols, game.m, game.n)
    scaled = model['scaler'].transform(feat.reshape(1, -1))
    return float(model['mlp'].predict(scaled)[0])


# ---------------------------------------------------------------------------
# 主求解函数
# ---------------------------------------------------------------------------
def distance_solve(game, step: int, max_steps=1000,
                   cancel_check=None, progress_callback=None):
    m, n = game.m, game.n
    total = m * n

    model = load_distance_model(m, n, step)
    if model is None:
        return None  # 模型不存在 → 未找到数据库

    actions = []
    rep_cells = []
    visited = set()
    stuck = 0
    no_improve = 0

    for i in range(max_steps):
        if cancel_check and cancel_check():
            return None
        if game.is_solved():
            break

        coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        cur_pred = predict_distance(game, model)

        if progress_callback and i % 10 == 0:
            progress_callback({'step': i + 1, 'total': max_steps,
                               'pred_distance': cur_pred})

        if no_improve > 80:
            break

        ch = canonicalize(coords)
        if ch in visited:
            stuck += 1
            if stuck > 5:
                break
        visited.add(ch)

        candidates = enumerate_valid_actions(game, step)
        if not candidates:
            break

        snap = snapshot(game)
        scored = []
        for act in candidates:
            if not apply_action(game, act, step):
                restore(game, snap)
                continue
            new_coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
            if len(new_coords) != total:
                restore(game, snap)
                continue
            pred = predict_distance(game, model)
            nh = canonicalize(new_coords)
            scored.append((pred, act, nh))
            restore(game, snap)

        if not scored:
            # 无候选可用：随机扰动
            for _ in range(3):
                act = random.choice(candidates)
                if apply_action(game, act, step):
                    actions.append(act)
                    rep_cells.append(_find_rep_cell(game, act))
                    break
            else:
                break
            continue

        # 优先选「未访问过」且预测距离最小的动作
        scored.sort(key=lambda x: (x[2] in visited, x[0]))
        best_pred, best_action, _ = scored[0]

        restore(game, snap)
        rep = _find_rep_cell(game, best_action)
        if rep is None:
            act = random.choice(candidates)
            if apply_action(game, act, step):
                rep = _find_rep_cell(game, act) or (0, 0)
                actions.append(act)
                rep_cells.append(rep)
                continue
            break
        ok = apply_action(game, best_action, step)
        if not ok:
            break
        actions.append(best_action)
        rep_cells.append(rep)

        if best_pred < cur_pred - 1e-6:
            no_improve = 0
        else:
            no_improve += 1

    if game.is_solved():
        return actions, rep_cells
    return False


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------
def main():
    m, n, step = 4, 4, 2
    if len(sys.argv) > 3:
        m, n, step = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])

    total_tests = 20
    ok = 0
    steps_sum = 0
    time_sum = 0.0

    print(f"距离预测求解器 — {m}x{n} step={step}")
    model = load_distance_model(m, n, step)
    print(f"模型: {'已加载' if model else '未找到'}\n")

    for t in range(total_tests):
        g = SliderMatrix(m, n)
        g.shuffle(attempts=100, step=step)
        t0 = time.time()
        r = distance_solve(g, step=step)
        el = time.time() - t0
        if r:
            acts, _ = r
            ok += 1
            steps_sum += len(acts)
            time_sum += el
            print(f"  测试{t+1:2d}: OK  {len(acts):3d}步  {el:.1f}s")
        else:
            print(f"  测试{t+1:2d}: FAIL  {el:.1f}s")

    print(f"\n{'='*50}")
    print(f"成功率: {ok}/{total_tests} ({100*ok/total_tests:.0f}%)")
    if ok:
        print(f"平均步数: {steps_sum/ok:.1f}  平均耗时: {time_sum/ok:.1f}s")


if __name__ == '__main__':
    main()
