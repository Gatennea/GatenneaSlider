# -*- coding: utf-8 -*-
r"""
人类模仿学习 — 评分模型训练（Learning-to-Rank）

数据：solver/ml/data/human/human_samples.jsonl
    每行一个 (状态, 动作, 正/负, 权重) 样本，来源 = save/*.json 人类还原记录。
    状态以「归一化网格 matrix」存（bounds 原点），动作 = 绝对坐标 gap_line。

训练：
    1. 按「存档文件」分组划分训练/测试（同一局的状态不跨集合 → 评估泛化）
    2. 训练侧加权复制：sklearn MLP 不支持 sample_weight，用 Poisson 复制使样本
       分布逼近 void_block_count 权重设计（收尾阶段样本多份、早期混乱少份）
    3. MLPRegressor 学习 score(state, action)
    4. 测试侧（原始、不加权）评估：回归 MAE/R² + 状态级 Hit@1
       （人类动作得分 > 同状态全部随机负样本）

运行：
    D:\python\python.exe -m solver.ml.train_human_ranker
"""

import os
import sys
import json
import time
import pickle
import random,traceback
from collections import defaultdict
import numpy as np

sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score

from solver.ml.features import build_human_state_features, encode_action

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, 'data', 'human', 'human_samples.jsonl')
_OUT_DIR = os.path.join(_HERE, 'data', 'human')
_SEED = 42


def _row_to_xy(r):
    """一行样本 → (state_feat, action_feat)。

    与 human_solver 推理端严格一致：
    - 状态：归一化矩阵 → build_human_state_features（含聚拢度维度）
    - 动作：gap_line 相对状态边界编码（平移不变，origin = bounds 原点）
    """
    sf = build_human_state_features(r['matrix'], r['m'], r['n'])
    af = encode_action(r['action'], origin=(r['min_row'], r['min_col']))
    return sf, af


def _load_rows(path):
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _resample_indices(weights, seed=_SEED):
    """Poisson 复制：复制份数 ∝ weight/mean(weight)，总规模≈原规模。"""
    rng = random.Random(seed)
    scale = float(np.mean(weights))
    out = []
    for i, w in enumerate(weights):
        k = w / scale
        copies = int(k)
        if rng.random() < (k - copies):
            copies += 1
        out.extend([i] * copies)
    return np.array(out)


def _state_hit_at_1(rows, test_rows, mlp, scaler):
    """测试状态级 Hit@1：每个正样本状态内，人类动作得分是否排第一。"""
    by_state = defaultdict(list)
    for r in test_rows:
        sf, af = _row_to_xy(r)
        feat = scaler.transform(np.concatenate([sf, af]).reshape(1, -1))
        sc = float(mlp.predict(feat)[0])
        by_state[(r['source'], r['seq_idx'])].append((sc, r['kind']))

    hit = 0
    n = 0
    for items in by_state.values():
        items.sort(key=lambda x: -x[0])
        hit += 1 if items[0][1] == 'pos' else 0
        n += 1
    return hit, n


def main():
    rows = _load_rows(_DATA)
    if not rows:
        print(f"无数据: {_DATA}，先运行 export_human_data.py")
        sys.exit(1)

    n_pos = sum(1 for r in rows if r['kind'] == 'pos')
    print(f"样本: 正 {n_pos:,}  负 {len(rows) - n_pos:,}  (共 {len(rows):,})")

    # 按文件分组划分（保证同局状态不跨集合）
    groups = np.array([r['source'] for r in rows])
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=_SEED)
    train_idx, test_idx = next(gss.split(np.arange(len(rows)), y=np.zeros(len(rows)), groups=groups))
    train_rows = [rows[i] for i in train_idx]
    test_rows = [rows[i] for i in test_idx]
    print(f"训练文件 {len(set(groups[train_idx]))} 个 → 样本 {len(train_rows):,}")
    print(f"测试文件 {len(set(groups[test_idx]))} 个 → 样本 {len(test_rows):,}")

    # ── 训练侧：特征 + 加权复制 ──
    Xs, Xa = [], []
    y_tr = []
    w_tr = []
    for r in train_rows:
        sf, af = _row_to_xy(r)
        Xs.append(sf)
        Xa.append(af)
        y_tr.append(1.0 if r['kind'] == 'pos' else 0.0)
        w_tr.append(r['weight'])
    Xs = np.array(Xs, dtype=np.float32)
    Xa = np.array(Xa, dtype=np.float32)
    y_tr = np.array(y_tr, dtype=np.float32)
    w_tr = np.array(w_tr, dtype=np.float32)

    sel = _resample_indices(w_tr)
    Xs, Xa, y_tr = Xs[sel], Xa[sel], y_tr[sel]
    print(f"加权复制后训练样本: {len(sel):,} (平均 {len(sel)/len(train_rows):.2f}x)")

    X_tr_raw = np.concatenate([Xs, Xa], axis=1)
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_tr_raw)

    print(f"\n训练 MLPRegressor (dim={X_tr_raw.shape[1]})...")
    t0 = time.time()
    mlp = MLPRegressor(
        hidden_layer_sizes=(256, 128, 64),
        activation='relu',
        solver='adam',
        alpha=0.0001,
        batch_size=256,
        learning_rate='adaptive',
        max_iter=300,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=15,
        random_state=_SEED,
        verbose=True,  # 每 epoch 输出 loss，便于监督训练进度
    )
    mlp.fit(X_tr, y_tr)
    print(f"  训练耗时: {time.time() - t0:.0f}s  iters={mlp.n_iter_}")

    # ── 测试侧：原始样本评估 ──
    Xs_te, Xa_te, y_te = [], [], []
    for r in test_rows:
        sf, af = _row_to_xy(r)
        Xs_te.append(sf)
        Xa_te.append(af)
        y_te.append(1.0 if r['kind'] == 'pos' else 0.0)
    X_te = scaler.transform(np.concatenate([np.array(Xs_te), np.array(Xa_te)], axis=1))
    y_te = np.array(y_te)

    pred = mlp.predict(X_te)
    mae = mean_absolute_error(y_te, pred)
    r2 = r2_score(y_te, pred)
    pred_bin = (pred >= 0.5).astype(float)
    acc = (pred_bin == y_te).mean()
    print(f"\n测试集 (文件级留出):")
    print(f"  MAE={mae:.4f}  R²={r2:.4f}  二分类准确率={acc*100:.1f}%")

    hit, n_states = _state_hit_at_1(rows, test_rows, mlp, scaler)
    print(f"  状态级 Hit@1: {hit}/{n_states} = {hit/n_states*100:.1f}%")

    # ── 保存 ──
    model_path = os.path.join(_OUT_DIR, 'model_ranker.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump({'mlp': mlp, 'scaler': scaler}, f, protocol=pickle.HIGHEST_PROTOCOL)
    meta = {
        'data': os.path.basename(_DATA),
        'positive': n_pos,
        'negative': len(rows) - n_pos,
        'train_files': len(set(groups[train_idx])),
        'test_files': len(set(groups[test_idx])),
        'effective_train_samples': int(len(sel)),
        'mae': float(mae), 'r2': float(r2), 'binary_acc': float(acc),
        'hit1': {'hit': int(hit), 'states': int(n_states), 'rate': float(hit / n_states)},
        'train_seconds': round(time.time() - t0),
    }
    meta_path = os.path.join(_OUT_DIR, 'human_ranker_report.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"\n模型: {model_path}")
    print(f"报告: {meta_path}")
    input("按任意键结束...")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        input("按任意键结束...")
