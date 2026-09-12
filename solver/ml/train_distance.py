# -*- coding: utf-8 -*-
r"""
訓練距離預測模型

方案：
    訓練模型預測「從當前狀態到還原還需要多少步」（即 BFS 距離 / 啟發值）。

數據來源：
    1. BFS 表（4×4，559k 狀態）—— 標籤為精確 BFS 距離
    2. 人類還原記錄（4×4~9×9）—— 標籤為還原過程中剩餘步數（近似值）

特徵：
    填充網格（16×16） + EMD + 缺陷（孔洞/缺口/凸起） + 填充率 + 長寬比誤差 + 尺寸

輸出：
    solver/ml/models/{m}_{n}_{step}/distance_model.pkl

運行：
    D:\python\python.exe -m solver.ml.train_distance
"""

import os
import sys
import json
import pickle
import time
import random
import numpy as np

from solver.ml.emd_solver import emd_distance

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from history import expand_snapshot_moves  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
SAVE_DIR = os.path.join(ROOT, 'save')
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')

GRID_SIZE = 16  # 填充網格尺寸


# ---------------------------------------------------------------------------
# 缺陷計算（基於已歸一化的 flat_grid）
# ---------------------------------------------------------------------------
def compute_defects(flat_grid, rows, cols, m, n):
    """從歸一化網格計算缺陷：凸起、缺口、孔洞。"""
    protrusions = 0
    region = [[0] * n for _ in range(m)]
    for r in range(min(rows, m + 20)):
        for c in range(cols):
            idx = r * cols + c
            if idx < len(flat_grid) and flat_grid[idx] == 1:
                if r < m and c < n:
                    region[r][c] = 1
                else:
                    protrusions += 1

    # 洪水填充：從區域邊緣的 0 開始，標記為「缺口」
    visited = [[False] * n for _ in range(m)]
    stack = []
    for r in range(m):
        for c in (0, n - 1):
            if region[r][c] == 0 and not visited[r][c]:
                visited[r][c] = True
                stack.append((r, c))
    for c in range(n):
        for r in (0, m - 1):
            if region[r][c] == 0 and not visited[r][c]:
                visited[r][c] = True
                stack.append((r, c))
    while stack:
        r, c = stack.pop()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < m and 0 <= nc < n:
                if region[nr][nc] == 0 and not visited[nr][nc]:
                    visited[nr][nc] = True
                    stack.append((nr, nc))

    dents = 0
    holes = 0
    for r in range(m):
        for c in range(n):
            if region[r][c] == 0:
                if visited[r][c]:
                    dents += 1
                else:
                    holes += 1
    return holes, dents, protrusions


# ---------------------------------------------------------------------------
# 特徵構建
# ---------------------------------------------------------------------------
def build_features(flat_grid, rows, cols, m, n):
    """構建狀態特徵向量。"""
    # 1. 填充網格
    grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.float32)
    for r in range(min(rows, GRID_SIZE)):
        for c in range(min(cols, GRID_SIZE)):
            idx = r * cols + c
            if idx < len(flat_grid):
                grid[r, c] = flat_grid[idx]
    grid_flat = grid.flatten()

    # 2. 座標 + EMD
    coords = []
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            if idx < len(flat_grid) and flat_grid[idx] == 1:
                coords.append((r, c))
    emd = emd_distance(frozenset(coords), m, n) if coords else float('inf')

    # 3. 缺陷
    holes, dents, protr = compute_defects(flat_grid, rows, cols, m, n)

    # 4. 標量特徵
    total = m * n
    fill_rate = total / (rows * cols) if rows * cols > 0 else 0
    target_aspect = min(m, n) / max(m, n)
    actual_aspect = min(rows, cols) / max(rows, cols, 1)
    aspect_error = abs(actual_aspect - target_aspect)

    scalar = np.array([
        emd / 100.0,          # 歸一化 EMD
        holes / 10.0,         # 歸一化孔洞
        dents / 10.0,          # 歸一化缺口
        protr / 10.0,         # 歸一化凸起
        fill_rate,
        aspect_error,
        m / 10.0,             # 尺寸特徵
        n / 10.0,
        total / 100.0,
    ], dtype=np.float32)

    return np.concatenate([grid_flat, scalar])


# ---------------------------------------------------------------------------
# 數據加載
# ---------------------------------------------------------------------------
def load_bfs_data(sample_frac=0.2):
    """加載 BFS 表數據，返回 (X, y, meta)。"""
    path = os.path.join(DATA_DIR, 'training', '4_4_2', 'states_annotated.pkl')
    with open(path, 'rb') as f:
        states = pickle.load(f)

    if sample_frac < 1.0:
        random.seed(42)
        states = random.sample(states, int(len(states) * sample_frac))

    print(f"BFS 數據: {len(states):,} 狀態（採樣 {sample_frac:.0%}）")

    X, y = [], []
    for s in states:
        feat = build_features(s['flat_grid'], s['grid_rows'], s['grid_cols'], 4, 4)
        X.append(feat)
        y.append(s['distance'])

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def load_human_data():
    """加載人類還原記錄，返回 (X, y, meta)。"""
    files = []
    for f in os.listdir(SAVE_DIR):
        if f.endswith('.json') and f not in ('save.json', 'test.json', 'analyzer.py'):
            files.append(os.path.join(SAVE_DIR, f))

    X, y = [], []
    for path in files:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        m, n = data['puzzle']['m'], data['puzzle']['n']
        step_count = data['step_count']
        snaps = data['history']['snapshots']
        # 合併快照（同一次選中連續移動）只存末態矩陣：逐步展開還原中間態，
        # 標籤用該快照的累計步數（step_total）回推，兼容舊存檔（無此欄位）。
        for i in range(1, len(snaps)):
            expanded = expand_snapshot_moves(snaps[i - 1], snaps[i])
            total = snaps[i].get('step_total', i)
            n_exp = len(expanded)
            for j, (_pre, post, _mv) in enumerate(expanded):
                bounds = post['bounds']
                min_r, min_c = bounds['min_row'], bounds['min_col']
                mat = post['matrix']
                coords = []
                for r_i, row in enumerate(mat):
                    for c_j, val in enumerate(row):
                        if val == 1:
                            coords.append((min_r + r_i, min_c + c_j))
                # 歸一化
                if not coords:
                    continue
                rs = [r for r, _ in coords]
                cs = [c for _, c in coords]
                mr, mc = min(rs), min(cs)
                norm = [(r - mr, c - mc) for r, c in coords]
                rows = max(r for r, _ in norm) + 1
                cols = max(c for _, c in norm) + 1
                flat = [0] * (rows * cols)
                for r, c in norm:
                    flat[r * cols + c] = 1

                feat = build_features(flat, rows, cols, m, n)
                X.append(feat)
                # 剩餘步數 = 總步數 - 該步完成後的累計步數（合併快照內逐步回推）
                done = total - (n_exp - 1 - j)
                y.append(step_count - done)

    print(f"人類記錄: {len(X):,} 狀態")
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


# ---------------------------------------------------------------------------
# 訓練
# ---------------------------------------------------------------------------
def train():
    from sklearn.model_selection import train_test_split
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_absolute_error, r2_score

    print("加載 BFS 數據...")
    X_bfs, y_bfs = load_bfs_data(sample_frac=0.2)
    print("加載人類記錄...")
    X_human, y_human = load_human_data()

    # 合併
    X = np.concatenate([X_bfs, X_human])
    y = np.concatenate([y_bfs, y_human])
    print(f"總數據: {len(X):,} 樣本, 特徵維度 {X.shape[1]}")

    # 劃分
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    print(f"訓練: {len(X_train):,}  測試: {len(X_test):,}")

    # 標準化
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 訓練
    print("\n訓練 MLPRegressor ...")
    t0 = time.time()
    mlp = MLPRegressor(
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
        verbose=True,
    )
    mlp.fit(X_train_scaled, y_train)
    elapsed = time.time() - t0
    print(f"訓練耗時: {elapsed:.0f}s")

    # 評估
    y_pred = mlp.predict(X_test_scaled)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    print(f"\nMAE: {mae:.3f}   R²: {r2:.4f}")

    # 保存
    os.makedirs(os.path.join(MODELS_DIR, '4_4_2'), exist_ok=True)
    model_path = os.path.join(MODELS_DIR, '4_4_2', 'distance_model.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump({'mlp': mlp, 'scaler': scaler}, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"模型已保存: {model_path}")
    print(f"  MAE={mae:.3f}  R²={r2:.4f}")


if __name__ == '__main__':
    train()
