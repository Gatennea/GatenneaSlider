r"""
评分模型训练：Learning-to-Rank 方式，用全部状态的 (状态, 动作) 对训练

策略：
    1. 加载全部 559k 个状态（不限于单动作状态）
    2. 正样本：每个最优动作 (state, action) → score=1.0
    3. 负样本：方向翻转的难例 (state, flipped_action) → score=0.0
       —— 针对上次发现的"方向混淆"问题
    4. 训练 MLPRegressor 作为评分函数
    5. 评估：对测试集状态，评分其最优动作 + 负样本，检查最优动作是否排第一

运行：
    D:\python\python.exe -m solver.train_ranker [m n step]
    默认 m=4 n=4 step=2
"""

import os
import sys
import pickle
import json
import time
import random
import numpy as np
from collections import Counter

# 强制实时输出
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score

# ---------------------------------------------------------------------------
# 路徑
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
TRAINING_DIR = os.path.join(DATA_DIR, 'training')

MAX_ROWS = 14
MAX_COLS = 15

DIR_FLIP = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


def _pad_grid(flat_grid, rows, cols):
    grid = np.zeros((MAX_ROWS, MAX_COLS), dtype=np.float32)
    for r in range(min(rows, MAX_ROWS)):
        for c in range(min(cols, MAX_COLS)):
            idx = r * cols + c
            if idx < len(flat_grid):
                grid[r, c] = flat_grid[idx]
    return grid.flatten()


def _encode_action(action):
    """将动作编码为固定 9 维向量。"""
    gap_h = 1.0 if action['gap_type'] == 'h' else 0.0
    gap_v = 1.0 if action['gap_type'] == 'v' else 0.0
    gap_line = action['gap_line'] / 10.0  # 归一化
    side_above = 1.0 if action['side'] == 'above' else 0.0
    side_below = 1.0 if action['side'] == 'below' else 0.0
    side_left = 1.0 if action['side'] == 'left' else 0.0
    side_right = 1.0 if action['side'] == 'right' else 0.0
    d_w = 1.0 if action['move_dir'] == 'w' else 0.0
    d_s = 1.0 if action['move_dir'] == 's' else 0.0
    d_a = 1.0 if action['move_dir'] == 'a' else 0.0
    d_d = 1.0 if action['move_dir'] == 'd' else 0.0
    # 只用 9 维（gap_line 被合并 + 4 side + 4 dir，但去掉 gap_type 冗余）
    # gap_type 可由 side 推断（above/below → h, left/right → v）
    return np.array([gap_h, gap_v, gap_line,
                     side_above, side_below, side_left, side_right,
                     d_w, d_s, d_a, d_d], dtype=np.float32)


def _build_state_features(s, m, n):
    """构建单个状态的特征向量。"""
    total_cells = m * n
    grid_feat = _pad_grid(s['flat_grid'], s['grid_rows'], s['grid_cols'])
    fill_rate = total_cells / (s['grid_rows'] * s['grid_cols'])
    target_aspect = min(m, n) / max(m, n)
    actual_aspect = min(s['grid_rows'], s['grid_cols']) / max(s['grid_rows'], s['grid_cols'], 1)
    aspect_error = abs(actual_aspect - target_aspect)
    extra = np.array([
        fill_rate,
        aspect_error,
        s['distance'] / 18.0,
        s.get('dist_to_bottleneck', 0) / 14.0,
        s.get('in_degree', 0) / 100.0,
    ], dtype=np.float32)
    return np.concatenate([grid_feat, extra])


def train_ranker(m=4, n=4, step=2, sample_frac=1.0):
    total_cells = m * n
    training_dir = os.path.join(TRAINING_DIR, f'{m}_{n}_{step}')
    data_path = os.path.join(training_dir, 'states_annotated.pkl')

    if not os.path.exists(data_path):
        print(f"错误: 找不到 {data_path}")
        sys.exit(1)

    # ──── 1. 加载 ────
    print(f"加载: {data_path}")
    t0 = time.time()
    with open(data_path, 'rb') as f:
        all_states = pickle.load(f)
    print(f"  {len(all_states):,} 状态，耗时 {time.time() - t0:.1f}s")

    # 去掉目标状态（无动作）
    states = [s for s in all_states if s['optimal_action_count'] > 0]
    print(f"  有最优动作: {len(states):,}")

    # 可选采样
    if sample_frac < 1.0:
        random.seed(42)
        states = random.sample(states, int(len(states) * sample_frac))
        print(f"  采样后: {len(states):,}")

    # ──── 2. 生成训练对 ────
    print("生成训练对 (正样本 + 方向翻转负样本)...")
    X_state = []   # 状态特征
    X_action = []  # 动作编码
    y_score = []   # 1.0=最优, 0.0=非最优
    pair_hashes = []  # 每个训练对所属的状态 hash

    # 预处理：每个状态只计算一次特征向量（避免重复填充网格）
    state_feat_cache = {}
    for s in states:
        state_feat_cache[s['hash']] = _build_state_features(s, m, n)

    for s in states:
        state_feat = state_feat_cache[s['hash']]
        for action in s['optimal_actions']:
            # 正样本
            X_state.append(state_feat)
            X_action.append(_encode_action(action))
            y_score.append(1.0)
            pair_hashes.append(s['hash'])

            # 负样本：翻转方向
            flipped_dir = DIR_FLIP.get(action['move_dir'], '')
            if flipped_dir and flipped_dir != action['move_dir']:
                flipped = dict(action)
                flipped['move_dir'] = flipped_dir
                X_state.append(state_feat)
                X_action.append(_encode_action(flipped))
                y_score.append(0.0)
                pair_hashes.append(s['hash'])

    X_state = np.array(X_state, dtype=np.float32)
    X_action = np.array(X_action, dtype=np.float32)
    y_score = np.array(y_score, dtype=np.float32)

    print(f"  总样本对: {len(y_score):,}")
    print(f"    正样本: {int((y_score == 1.0).sum()):,}")
    print(f"    负样本: {int((y_score == 0.0).sum()):,}")
    print(f"  X_state: {X_state.shape}  X_action: {X_action.shape}")

    # ──── 3. 按状态拆分训练/测试（保证同一状态不跨集合） ────
    unique_hashes = list(set(pair_hashes))
    train_hashes, test_hashes = train_test_split(
        unique_hashes, test_size=0.2, random_state=42
    )
    train_hashes = set(train_hashes)

    train_mask = np.array([h in train_hashes for h in pair_hashes])
    test_mask = ~train_mask

    X_train = np.concatenate([X_state[train_mask], X_action[train_mask]], axis=1)
    X_test = np.concatenate([X_state[test_mask], X_action[test_mask]], axis=1)
    y_train = y_score[train_mask]
    y_test = y_score[test_mask]

    print(f"  训练集: {len(y_train):,}  测试集: {len(y_test):,}")

    # ──── 4. 标准化 ────
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # ──── 5. 训练评分模型 ────
    print(f"\n训练 MLPRegressor (评分模型)...")
    t_train = time.time()

    mlp = MLPRegressor(
        hidden_layer_sizes=(512, 256, 128),
        activation='relu',
        solver='adam',
        alpha=0.0001,
        batch_size=512,
        learning_rate='adaptive',
        max_iter=100,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=10,
        random_state=42,
        verbose=True,
    )
    mlp.fit(X_train_scaled, y_train)

    train_time = time.time() - t_train
    print(f"  训练耗时: {train_time:.0f}s")

    # ──── 6. 基础评估 ────
    y_pred = mlp.predict(X_test_scaled)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    print(f"\n  MAE: {mae:.4f}   R²: {r2:.4f}")

    # 二分类准确率（阈值=0.5）
    y_pred_bin = (y_pred >= 0.5).astype(np.float32)
    bin_acc = (y_pred_bin == y_test).mean()
    tp = ((y_test == 1.0) & (y_pred_bin >= 0.5)).sum()
    tn = ((y_test == 0.0) & (y_pred_bin < 0.5)).sum()
    fp = ((y_test == 0.0) & (y_pred_bin >= 0.5)).sum()
    fn = ((y_test == 1.0) & (y_pred_bin < 0.5)).sum()
    print(f"  二元分类准确率: {bin_acc:.4f} ({bin_acc*100:.1f}%)")
    print(f"  TP={tp} TN={tn} FP={fp} FN={fn}")
    if (tp + fp) > 0:
        print(f"  Precision: {tp/(tp+fp):.4f}  Recall: {tp/(tp+fn):.4f}")

    # ──── 7. 排序评估 ────
    #     对测试集中的每个状态，收集其所有样本对，检查最优动作是否排第一
    print(f"\n  排序评估 (按状态)...")
    test_hash_list = [pair_hashes[i] for i in range(len(pair_hashes)) if test_mask[i]]
    test_scores_by_hash = {}
    test_labels_by_hash = {}
    for i in range(len(y_test)):
        h = test_hash_list[i]
        if h not in test_scores_by_hash:
            test_scores_by_hash[h] = []
            test_labels_by_hash[h] = []
        test_scores_by_hash[h].append(float(y_pred[i]))
        test_labels_by_hash[h].append(float(y_test[i]))

    hit1 = 0
    hit2 = 0
    mrr_sum = 0.0
    total_eval_states = 0

    for h in test_scores_by_hash:
        scores = test_scores_by_hash[h]
        labels = test_labels_by_hash[h]
        # 按分数降序排列
        ranked = sorted(zip(scores, labels), key=lambda x: -x[0])
        # 最优动作的排名 (1-based)
        for rank, (_, label) in enumerate(ranked, 1):
            if label >= 1.0:
                if rank == 1:
                    hit1 += 1
                if rank <= 2:
                    hit2 += 1
                mrr_sum += 1.0 / rank
                break
        total_eval_states += 1

    hit1_rate = hit1 / total_eval_states if total_eval_states > 0 else 0
    hit2_rate = hit2 / total_eval_states if total_eval_states > 0 else 0
    mrr = mrr_sum / total_eval_states if total_eval_states > 0 else 0

    print(f"  评估状态数: {total_eval_states}")
    print(f"  Hit@1: {hit1_rate:.4f} ({hit1_rate*100:.1f}%) — 最优动作排第一")
    print(f"  Hit@2: {hit2_rate:.4f} ({hit2_rate*100:.1f}%) — 最优动作在前二")
    print(f"  MRR:   {mrr:.4f}")

    # ──── 8. 保存 ────
    print(f"\n保存模型...")
    model_path = os.path.join(training_dir, 'model_ranker.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump({
            'mlp': mlp,
            'scaler': scaler,
        }, f, protocol=pickle.HIGHEST_PROTOCOL)
    model_mb = os.path.getsize(model_path) / 1024 / 1024
    print(f"  → {model_path} ({model_mb:.1f} MB)")

    report = {
        'meta': {'m': m, 'n': n, 'step': step, 'sample_frac': sample_frac},
        'dataset': {
            'total_states': len(all_states),
            'used_states': len(states),
            'train_pairs': len(y_train),
            'test_pairs': len(y_test),
            'positive_pairs': int((y_score == 1.0).sum()),
            'negative_pairs': int((y_score == 0.0).sum()),
        },
        'regression': {
            'mae': float(mae),
            'r2': float(r2),
            'binary_acc': float(bin_acc),
            'precision': float(tp / (tp + fp)) if (tp + fp) > 0 else 0,
            'recall': float(tp / (tp + fn)) if (tp + fn) > 0 else 0,
        },
        'ranking': {
            'eval_states': total_eval_states,
            'hit1': float(hit1_rate),
            'hit2': float(hit2_rate),
            'mrr': float(mrr),
        },
        'train_time_seconds': train_time,
    }

    report_path = os.path.join(training_dir, 'ranker_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  → {report_path}")

    print(f"\n{'='*60}")
    print(f"评分模型训练完成！")
    print(f"  Hit@1: {hit1_rate*100:.1f}%")
    print(f"  Hit@2: {hit2_rate*100:.1f}%")
    print(f"  MRR:   {mrr:.4f}")
    print(f"{'='*60}")


def main():
    m = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    sample_frac = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    train_ranker(m, n, step, sample_frac)


if __name__ == '__main__':
    main()
