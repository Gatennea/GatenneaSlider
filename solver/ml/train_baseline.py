# -*- coding: utf-8 -*-
r"""
快速原型：scikit-learn MLPClassifier 基線訓練

策略：
    1. 加載 states_annotated.pkl
    2. 僅使用「只有 1 個最優動作」的狀態（約 65k 個），確保標籤唯一
    3. 將網格 padding 到固定尺寸 (MAX_ROWS × MAX_COLS)，flatten 為特徵向量
    4. 將動作編碼為類別標籤（建立動作詞彙表）
    5. 訓練 MLPClassifier，評估準確率
    6. 同時訓練一個輔助任務：預測 dist_to_bottleneck（回歸）

輸出：
    solver/data/training/4_4_2/model_baseline.pkl   — 訓練好的模型
    solver/data/training/4_4_2/baseline_report.json — 評估報告

運行：
    D:\python\python.exe -m solver.train_baseline [m n step]
    默認 m=4 n=4 step=2
"""

import os
import sys
import pickle
import json
import time
import random
import numpy as np
from collections import Counter

from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import (
    accuracy_score, classification_report, mean_absolute_error, r2_score,
)

# ---------------------------------------------------------------------------
# 路徑
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
TRAINING_DIR = os.path.join(DATA_DIR, 'training')

# 網格參數（根據實際數據的最大行列調整）
MAX_ROWS = 12
MAX_COLS = 12


def _pad_grid(flat_grid, rows, cols):
    """將可變尺寸網格填充到固定尺寸 MAX_ROWS×MAX_COLS，返回 flatten 的固定長度數組。"""
    grid = np.zeros((MAX_ROWS, MAX_COLS), dtype=np.float32)
    for r in range(min(rows, MAX_ROWS)):
        for c in range(min(cols, MAX_COLS)):
            idx = r * cols + c
            if idx < len(flat_grid):
                grid[r, c] = flat_grid[idx]
    return grid.flatten()


def _action_to_label(action, action_vocab):
    """將動作字典轉為標籤字符串 → 查詞彙表得到整數 ID。"""
    key = f"{action['gap_type']}|{action['gap_line']}|{action['side']}|{action['move_dir']}"
    return action_vocab.get(key, -1)


def _build_action_vocab(states):
    """建立動作詞彙表：收集所有出現過的動作。"""
    vocab = {}
    for s in states:
        for a in s['optimal_actions']:
            key = f"{a['gap_type']}|{a['gap_line']}|{a['side']}|{a['move_dir']}"
            if key not in vocab:
                vocab[key] = len(vocab)
    return vocab


def train_baseline(m=4, n=4, step=2):
    total_cells = m * n
    training_dir = os.path.join(TRAINING_DIR, f'{m}_{n}_{step}')
    data_path = os.path.join(training_dir, 'states_annotated.pkl')

    if not os.path.exists(data_path):
        print(f"錯誤: 找不到 {data_path}，請先運行 annotate_bottlenecks.py")
        sys.exit(1)

    # ──── 1. 加載數據 ────
    print(f"加載: {data_path}")
    t0 = time.time()
    with open(data_path, 'rb') as f:
        states = pickle.load(f)
    print(f"  {len(states):,} 狀態，耗時 {time.time() - t0:.1f}s")

    # ──── 2. 過濾：只取恰好 1 個最優動作的狀態 ────
    single_action_states = [s for s in states if s['optimal_action_count'] == 1]
    print(f"  其中恰好 1 個最優動作: {len(single_action_states):,} 個")

    if len(single_action_states) < 100:
        print("  樣本太少，無法訓練。")
        sys.exit(1)

    # 檢查最大行列
    max_rows_actual = max(s['grid_rows'] for s in states)
    max_cols_actual = max(s['grid_cols'] for s in states)
    print(f"  實際最大網格: {max_rows_actual}×{max_cols_actual}")

    # ──── 3. 建立動作詞彙表 ────
    action_vocab = _build_action_vocab(single_action_states)
    num_actions = len(action_vocab)
    print(f"  動作詞彙表大小: {num_actions}")

    # ──── 4. 構建特徵和標籤 ────
    print("構建特徵矩陣...")
    X_grid = []    # 網格特徵（固定大小）
    X_extra = []   # 輔助特徵
    y_action = []  # 動作標籤
    y_bn = []      # dist_to_bottleneck

    skipped = 0
    for s in single_action_states:
        action = s['optimal_actions'][0]
        label = _action_to_label(action, action_vocab)
        if label < 0:
            skipped += 1
            continue

        grid_feat = _pad_grid(s['flat_grid'], s['grid_rows'], s['grid_cols'])
        X_grid.append(grid_feat)

        # 輔助特徵：包裹率、長寬比偏差、距離等
        fill_rate = total_cells / (s['grid_rows'] * s['grid_cols'])  # 方塊數 ÷ 邊界盒面積，越接近 1 越緊湊
        target_aspect = min(m, n) / max(m, n)  # 目標長寬比（m*n 或 n*m 都是勝利）
        actual_aspect = min(s['grid_rows'], s['grid_cols']) / max(s['grid_rows'], s['grid_cols'], 1)
        aspect_error = abs(actual_aspect - target_aspect)  # 偏離目標長寬比的程度，越小越好
        extra = [
            fill_rate,
            aspect_error,
            s['distance'] / 18.0,          # 歸一化 BFS 距離
            s.get('dist_to_bottleneck', 0) / 14.0,  # 歸一化瓶頸距離
            s.get('in_degree', 0) / 100.0,           # 歸一化入度
        ]
        X_extra.append(extra)
        y_action.append(label)
        y_bn.append(s.get('dist_to_bottleneck', 0))

    X_grid = np.array(X_grid, dtype=np.float32)
    X_extra = np.array(X_extra, dtype=np.float32)
    y_action = np.array(y_action, dtype=np.int32)
    y_bn = np.array(y_bn, dtype=np.float32)

    print(f"  有效樣本: {len(y_action):,} (跳過 {skipped})")
    print(f"  X_grid: {X_grid.shape}  X_extra: {X_extra.shape}")

    # ──── 5. 劃分訓練/測試集 ────
    X_all = np.concatenate([X_grid, X_extra], axis=1)
    indices = np.arange(len(X_all))

    train_idx, test_idx = train_test_split(
        indices, test_size=0.2, random_state=42,
    )

    X_train, X_test = X_all[train_idx], X_all[test_idx]
    y_train, y_test = y_action[train_idx], y_action[test_idx]
    y_bn_train, y_bn_test = y_bn[train_idx], y_bn[test_idx]

    print(f"  訓練集: {len(X_train):,}  測試集: {len(X_test):,}")

    # ──── 6. 標準化 ────
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # ──── 7. 訓練動作分類器 ────
    print(f"\n訓練 MLPClassifier (動作預測, {num_actions} 類)...")
    t_train = time.time()

    mlp_action = MLPClassifier(
        hidden_layer_sizes=(512, 256, 128),
        activation='relu',
        solver='adam',
        alpha=0.0001,
        batch_size=256,
        learning_rate='adaptive',
        max_iter=100,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=10,
        random_state=42,
        verbose=True,
    )
    mlp_action.fit(X_train_scaled, y_train)

    train_time = time.time() - t_train
    print(f"  訓練耗時: {train_time:.0f}s")

    # ──── 8. 評估動作分類 ────
    y_pred = mlp_action.predict(X_test_scaled)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n  測試集準確率: {acc:.4f} ({acc*100:.1f}%)")

    # Top-3 準確率
    y_proba = mlp_action.predict_proba(X_test_scaled)
    top3_acc = 0
    for i, true_label in enumerate(y_test):
        top3 = np.argsort(y_proba[i])[-3:]
        if true_label in top3:
            top3_acc += 1
    top3_acc /= len(y_test)
    print(f"  Top-3 準確率: {top3_acc:.4f} ({top3_acc*100:.1f}%)")

    # ──── 9. 訓練 dist_to_bottleneck 回歸器 ────
    print(f"\n訓練 MLPRegressor (瓶頸距離預測)...")
    t_reg = time.time()

    mlp_bn = MLPRegressor(
        hidden_layer_sizes=(256, 128, 64),
        activation='relu',
        solver='adam',
        alpha=0.001,
        batch_size=256,
        learning_rate='adaptive',
        max_iter=100,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=10,
        random_state=42,
    )
    mlp_bn.fit(X_train_scaled, y_bn_train)

    reg_time = time.time() - t_reg
    y_bn_pred = mlp_bn.predict(X_test_scaled)
    mae = mean_absolute_error(y_bn_test, y_bn_pred)
    r2 = r2_score(y_bn_test, y_bn_pred)
    print(f"  訓練耗時: {reg_time:.0f}s")
    print(f"  MAE: {mae:.3f}   R²: {r2:.4f}")

    # ──── 10. 按距離層分析準確率 ────
    # 從 states 中提取測試集的 BFS 距離
    single_states_list = [s for s in single_action_states
                          if _action_to_label(s['optimal_actions'][0], action_vocab) >= 0]
    test_distances = [single_states_list[i]['distance'] for i in test_idx]
    print(f"\n  按 BFS 距離層準確率:")
    for d in sorted(set(test_distances)):
        mask = [td == d for td in test_distances]
        if sum(mask) == 0:
            continue
        d_acc = accuracy_score([y_test[i] for i, m in enumerate(mask) if m],
                               [y_pred[i] for i, m in enumerate(mask) if m])
        count = sum(mask)
        print(f"    距離 {d:2d}: {d_acc:.3f}  (n={count})")

    # ──── 11. 保存 ────
    print(f"\n保存模型...")
    model_path = os.path.join(training_dir, 'model_baseline.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump({
            'mlp_action': mlp_action,
            'mlp_bottleneck': mlp_bn,
            'scaler': scaler,
            'action_vocab': action_vocab,
            'label_encoder': None,  # 使用詞彙表代替
        }, f, protocol=pickle.HIGHEST_PROTOCOL)
    model_mb = os.path.getsize(model_path) / 1024 / 1024
    print(f"  → {model_path} ({model_mb:.1f} MB)")

    # 評估報告
    report = {
        'meta': {'m': m, 'n': n, 'step': step, 'max_grid': [max_rows_actual, max_cols_actual]},
        'dataset': {
            'total_states': len(states),
            'single_action_states': len(single_action_states),
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'num_action_classes': num_actions,
        },
        'action_classifier': {
            'accuracy': float(acc),
            'top3_accuracy': float(top3_acc),
            'train_time_seconds': train_time,
            'hidden_layers': [512, 256, 128],
            'by_distance': {
            int(d): float(accuracy_score(
                [y_test[i] for i, td in enumerate(test_distances) if td == d],
                [y_pred[i] for i, td in enumerate(test_distances) if td == d]
            ))
            for d in sorted(set(test_distances))
            if sum(1 for td in test_distances if td == d) > 0
        },
        },
        'bottleneck_regressor': {
            'mae': float(mae),
            'r2': float(r2),
            'train_time_seconds': reg_time,
        },
        'feature_dims': {
            'grid_padded': int(MAX_ROWS * MAX_COLS),
            'extra': len(X_extra[0]),
            'total': int(X_all.shape[1]),
        },
    }

    report_path = os.path.join(training_dir, 'baseline_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  → {report_path}")

    # ──── 12. 錯誤分析：最常見的混淆對 ────
    print(f"\n{'='*60}")
    print(f"最常見的錯誤預測 (混淆對 Top 10):")
    errors = []
    for i in range(len(y_test)):
        if y_pred[i] != y_test[i]:
            errors.append((y_test[i], y_pred[i]))
    confusion_counter = Counter(errors)
    # 反查詞彙表
    id_to_action = {v: k for k, v in action_vocab.items()}
    for (true_id, pred_id), count in confusion_counter.most_common(10):
        true_str = id_to_action.get(true_id, '?')
        pred_str = id_to_action.get(pred_id, '?')
        print(f"  真: {true_str:40s} → 誤: {pred_str:40s}  ({count} 次)")

    print(f"{'='*60}")
    print(f"\n基線訓練完成。")
    print(f"  動作分類準確率: {acc*100:.1f}%")
    print(f"  Top-3 準確率:   {top3_acc*100:.1f}%")
    print(f"  瓶頸距離 MAE:   {mae:.3f}")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    m = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    train_baseline(m, n, step)


if __name__ == '__main__':
    main()
