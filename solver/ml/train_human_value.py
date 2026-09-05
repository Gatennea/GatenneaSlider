# -*- coding: utf-8 -*-
r"""
人类模仿 + 价值训练（奖励信号加权，取代 1/0 模仿）

训练目标不再是「复制人类动作」，而是预测「这一步之后局面会变好多少」——
模型对每个 (状态, 动作) 输出价值分，推理选最高分动作。

奖励设计（依据每局完整轨迹离线计算，规则见需求）：
    void = m·n − 目标窗内方块数   （空位数，region-aware，不约分）
    hole = 目标窗内被方块包围的空格数

    4) 该步执行后还原                              → +10    （最大奖励）
    2) void 减少                                  → +3     （较大奖励，同时作为回退底线）
    2) void 不变 且 hole 增多（填缺口常先构造洞）    → +1     （普通奖励）
    1) void 不变 且 hole 未增（徘徊/腾挪）           → +0.2   （轻微，容忍探索）
    3) void 增加 = 拆解/绕路：
         ≤8 步内回落至原 void → 成功的构造性拆解     → +0.3
         大幅提升且久未回升 / 终未回升               → −1.5 − 2·min(Δvoid, 3)

负样本（同状态其他合法动作）target 一律 −10（保守基线：它们至少不比人类的
差动作好——我们无从知晓其真实价值，让模型把高分留给「被验证有效的动作」）。

进度展示：每个阶段计数 + MLPRegressor(verbose) 逐 epoch loss。
运行：
    D:\python\python.exe -m solver.ml.train_human_value
输出：
    solver/ml/data/human/model_ranker.pkl   （推理端不变，仍是打分取最高）
    solver/ml/data/human/human_value_report.json
"""

import os
import sys
import json
import time
import pickle
import random
from collections import defaultdict
import numpy as np

sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error

from solver.ml.features import build_human_state_features, encode_action
from solver.ml.gather_solver import find_best_window
from solver.ml.hole_detector import detect_holes

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, 'data', 'human', 'human_samples.jsonl')
_OUT_DIR = os.path.join(_HERE, 'data', 'human')
_SEED = 42
_REBOUND_DIST = 8   # 拆解后多少步内回落视为「成功的构造」
_NEG_TARGET = -10.0
_R_SOLVED = 10.0
_R_VOID_DOWN = 3.0
_R_HOLE_UP = 1.0
_R_NEUTRAL = 0.2
_R_CONSTRUCT = 0.3
_R_UNKNOWN = 0.0   # 未完成局的最后一步：无后续状态，给中性偏低调值


# ---------------------------------------------------------------------------
# 状态指标（带缓存）
# ---------------------------------------------------------------------------
def _state_key(matrix):
    return tuple(tuple(row) for row in matrix)


def _state_metrics(matrix, m, n, step, cache):
    """返回 (void, hole_cnt)。region 取 find_best_window（mod-aware，与 GUI 一致）。"""
    key = _state_key(matrix)
    if key in cache:
        return cache[key]
    if not matrix or not matrix[0]:
        cache[key] = (m * n, 0)
        return cache[key]
    # matrix 已以边界为原点 → 直接用其索引作坐标（平移不变量）
    coords = frozenset((r, c) for r, row in enumerate(matrix)
                       for c, v in enumerate(row) if v)
    region = find_best_window(coords, m, n, step)   # (r0, c0, (rh, cw), overlap)
    overlap = region[3] if region else 0
    void = m * n - overlap
    if void == 0:
        cache[key] = (0, 0)   # 还原态：无洞
        return cache[key]
    holes, _, _ = detect_holes(coords, m, n, step, region=region[:3])
    hole_cnt = sum(1 for h in holes if h.get('type') == 'hole')
    cache[key] = (void, hole_cnt)
    return cache[key]


# ---------------------------------------------------------------------------
# 数据加载 / 奖励标注
# ---------------------------------------------------------------------------
def _load_pos_by_source(rows):
    """正样本按存档文件分组、按 seq_idx 排序，恢复每局动作序列。"""
    by_src = defaultdict(list)
    for r in rows:
        if r['kind'] == 'pos':
            by_src[r['source']].append(r)
    for src in by_src:
        by_src[src].sort(key=lambda r: r['seq_idx'])
    return by_src


def _annotate_rewards(rows):
    """
    对每个正样本算奖励 target（返回正样本 dict 列表，附 'target'）。
    流程：每局重建状态序列 → 逐状态算 (void, hole) → 逐动作套奖励规则。
    """
    by_src = _load_pos_by_source(rows)
    cache = {}
    targets = {}          # (source, seq_idx) → reward
    n_hit_reward = {'solved': 0, 'void_down': 0, 'hole_up': 0,
                    'neutral': 0, 'construct': 0, 'penalty': 0}
    t0 = time.time()

    for src, evts in by_src.items():
        k = len(evts)                     # 动作数
        finished = any(r['finished'] for r in evts)
        m, n, step = evts[0]['m'], evts[0]['n'], evts[0]['step']

        # before 状态 i = evts[i].matrix（i=0..k-1）
        ms = [evts[i]['matrix'] for i in range(k)]
        metrics = []
        for i in range(k):
            metrics.append(_state_metrics(ms[i], m, n, step, cache))
        if finished:
            # 最后动作后 = 还原态（void 0, hole 0）
            metrics.append((0, 0))

        for i in range(k):
            v_cur, h_cur = metrics[i]
            if finished and i == k - 1:
                R = _R_SOLVED
                n_hit_reward['solved'] += 1
            elif i + 1 >= len(metrics):
                # 未完成局的最后一步：没有「之后状态」可评估
                R = _R_UNKNOWN
                n_hit_reward['neutral'] += 1
            else:
                v_next, h_next = metrics[i + 1]
                if v_next < v_cur:
                    R = _R_VOID_DOWN
                    n_hit_reward['void_down'] += 1
                elif v_next == v_cur:
                    if h_next > h_cur:
                        R = _R_HOLE_UP
                        n_hit_reward['hole_up'] += 1
                    else:
                        R = _R_NEUTRAL
                        n_hit_reward['neutral'] += 1
                elif v_next > v_cur:  # void 增加 = 拆解
                    dv = v_next - v_cur
                    # 找后续第一个 ≤ v_cur 的回落点
                    reb = None
                    for t in range(i + 1, len(metrics)):
                        if metrics[t][0] <= v_cur:
                            reb = t
                            break
                    if reb is not None and (reb - (i + 1)) <= _REBOUND_DIST:
                        R = _R_CONSTRUCT
                        n_hit_reward['construct'] += 1
                    else:
                        R = -1.5 - 2.0 * min(dv, 3)
                        n_hit_reward['penalty'] += 1
            targets[(src, evts[i]['seq_idx'])] = R

    print(f"[奖励标注] {len(targets):,} 个正样本 · 耗时 {time.time()-t0:.0f}s")
    print(f"   还原:{n_hit_reward['solved']} void降:{n_hit_reward['void_down']} "
          f"洞增:{n_hit_reward['hole_up']} 中性:{n_hit_reward['neutral']} "
          f"构造:{n_hit_reward['construct']} 惩罚:{n_hit_reward['penalty']}")

    # 写回 target；正样本加入 target，负样本统一 _NEG_TARGET
    pos_out = []
    neg_out = []
    for r in rows:
        if r['kind'] == 'pos':
            rr = dict(r)
            rr['target'] = targets[(r['source'], r['seq_idx'])]
            pos_out.append(rr)
        else:
            rr = dict(r)
            rr['target'] = _NEG_TARGET
            neg_out.append(rr)
    return pos_out, neg_out


# ---------------------------------------------------------------------------
# 训练
# ---------------------------------------------------------------------------
def _row_to_xy(r):
    """与 human_solver 推理端严格一致。"""
    sf = build_human_state_features(r['matrix'], r['m'], r['n'])
    af = encode_action(r['action'], origin=(r['min_row'], r['min_col']))
    return sf, af


# ---------------------------------------------------------------------------
# 评估：状态级 Hit@1（候选 = 该状态的全部负样本）
# ---------------------------------------------------------------------------
def _eval_state_hit1(all_rows, test_pos, mlp, scaler, cap=400):
    """对测试集正样本状态打分其「全部」负样本，统计人类动作排第一的比例。"""
    rng = random.Random(_SEED)
    if len(test_pos) > cap:
        test_pos = rng.sample(test_pos, cap)

    # 索引：source+seq → 该状态的负样本
    neg_by_state = defaultdict(list)
    for r in all_rows:
        if r['kind'] == 'neg':
            neg_by_state[(r['source'], r['seq_idx'])].append(r)

    hit = 0
    n = 0
    for pr in test_pos:
        negs = neg_by_state.get((pr['source'], pr['seq_idx']), [])
        if not negs:
            continue
        cands = [pr] + negs
        feats = []
        for r in cands:
            sf, af = _row_to_xy(r)
            feats.append(np.concatenate([sf, af]))
        X = scaler.transform(np.array(feats, dtype=np.float32))
        scores = mlp.predict(X)
        if int(np.argmax(scores)) == 0:  # 正样本排在候选第一位
            hit += 1
        n += 1
    return hit, n


def train():
    if not os.path.exists(_DATA):
        print(f"无数据: {_DATA}，先运行 export_human_data.py")
        sys.exit(1)
    with open(_DATA, encoding='utf-8') as f:
        all_rows = [json.loads(l) for l in f if l.strip()]
    print(f"载入 {len(all_rows):,} 行样本")

    # ── 1. 奖励标注 ──
    pos_rows, neg_rows = _annotate_rewards(all_rows)
    n_pos, n_neg = len(pos_rows), len(neg_rows)
    print(f"正样本(带价值): {n_pos:,}  负样本: {n_neg:,}")

    # ── 2. 平衡采样：每正样本配 1 个随机负样本 ──
    rng = random.Random(_SEED)
    if n_neg > n_pos:
        neg_rows = rng.sample(neg_rows, n_pos)
    print(f"平衡采样后: 正 {len(pos_rows):,}  负 {len(neg_rows):,}")

    # ── 3. 特征 ──
    t0 = time.time()
    all_rows_train = pos_rows + neg_rows
    Xs, Xa, y = [], [], []
    for r in all_rows_train:
        sf, af = _row_to_xy(r)
        Xs.append(sf)
        Xa.append(af)
        y.append(r['target'])
    X = np.concatenate([np.array(Xs, dtype=np.float32), np.array(Xa, dtype=np.float32)], axis=1)
    y = np.array(y, dtype=np.float32)
    groups = np.array([r['source'] for r in all_rows_train])
    print(f"[特征构建] {len(all_rows_train):,} 样本 · dim={X.shape[1]} · 耗时 {time.time()-t0:.0f}s")

    # ── 4. 文件级分组划分 ──
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=_SEED)
    tr_idx, te_idx = next(gss.split(np.arange(len(all_rows_train)), y=y, groups=groups))
    print(f"训练 {len(tr_idx):,}（{len(set(groups[tr_idx]))} 文件）  "
          f"测试 {len(te_idx):,}（{len(set(groups[te_idx]))} 文件）")

    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X[tr_idx])
    X_te = scaler.transform(X[te_idx])
    y_tr, y_te = y[tr_idx], y[te_idx]

    # ── 5. 价值回归 ──
    print(f"\n训练 MLPRegressor (dim={X.shape[1]}, verbose 逐 epoch)...")
    t_fit = time.time()
    mlp = MLPRegressor(
        hidden_layer_sizes=(256, 128, 64),
        activation='relu', solver='adam', alpha=0.0001,
        batch_size=256, learning_rate='adaptive',
        max_iter=300, early_stopping=True, validation_fraction=0.1,
        n_iter_no_change=15, random_state=_SEED, verbose=True,
    )
    mlp.fit(X_tr, y_tr)
    print(f"[训练] {time.time()-t_fit:.0f}s · iters={mlp.n_iter_}")

    # ── 6. 评估 ──
    pred = mlp.predict(X_te)
    mae = mean_absolute_error(y_te, pred)
    pos_mask = np.array([r['kind'] == 'pos' for r in all_rows_train])[te_idx]
    test_pos = [all_rows_train[i] for i in te_idx if all_rows_train[i]['kind'] == 'pos']
    hit, n_states = _eval_state_hit1(all_rows, test_pos, mlp, scaler)
    print(f"\n测试集 (文件级留出):")
    print(f"  MAE={mae:.4f}")
    print(f"  正样本均分={pred[pos_mask].mean():.3f}  负样本均分={pred[~pos_mask].mean():.3f}")
    print(f"  状态级 Hit@1: {hit}/{n_states} = {hit/n_states*100:.1f}%")

    # ── 7. 保存 ──
    model_path = os.path.join(_OUT_DIR, 'model_ranker.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump({'mlp': mlp, 'scaler': scaler}, f, protocol=pickle.HIGHEST_PROTOCOL)
    report = {
        'data': os.path.basename(_DATA),
        'positive': n_pos, 'negative': n_neg,
        'train': int(len(tr_idx)), 'test': int(len(te_idx)),
        'mae': float(mae),
        'pos_mean_pred': float(pred[pos_mask].mean()),
        'neg_mean_pred': float(pred[~pos_mask].mean()),
        'hit1': {'hit': int(hit), 'states': int(n_states), 'rate': float(hit / n_states)},
        'train_seconds': round(time.time() - t0),
    }
    rp = os.path.join(_OUT_DIR, 'human_value_report.json')
    with open(rp, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n{'='*60}")
    print(f"[训练完成] 模型已保存: {model_path}")
    print(f"[训练完成] 报告已保存: {rp}")
    print(f"[训练完成] 总耗时 {time.time()-t0:.0f}s")
    print(f"{'='*60}")


def main():
    train()


if __name__ == '__main__':
    main()
