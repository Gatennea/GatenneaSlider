# -*- coding: utf-8 -*-
"""exp18：距离拟合「质量复评」 —— 之前的好成绩可能是虚高的。

起因（2026-09-30）：exp17 在 4_4_2 上采样 1% 训练，得到 MAE=4.245、±1=0.2%，
与 mig_report2 里 5_5_2 的 MAE=0.345、±1=95.7% 差了两个数量级。查分布后发现：

    4_4_2  距离 0~17，均值 8.73，标准差 1.67  —— 真实跨度
    5_5_2  距离 0~6，其中 462713/612563 = 75.5% 全是 4  —— 退化分布

在退化分布上「永远猜众数」就能拿到很好的 MAE/±1，所以那份成绩可能不代表
模型能力。本脚本做三件事：

  1. 每个尺寸算「预测常数」的基线（众数与均值），对照 mig_report2 的模型成绩；
  2. 在 4_4_2（真实跨度）上用**随机留出**重评（exp17 的留出取自表头，
     而 BFS 表按层序写入 → 表头全是浅层状态，与训练集分布错位，结论作废）；
  3. 报出数据量曲线：1% / 5% 采样各是什么水平。

Usage:
    D:/python/python.exe -m experiments.exp18_fitquality
"""
from __future__ import annotations

import argparse
import pickle
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, r"E:/program_project/other/doubaotest/狀態拓撲圖分析")
sys.stdout.reconfigure(encoding="utf-8")

from mig_feat import features as mig_features  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402

DATA_ROOT = Path(r"E:/program_project/other/doubaotest/slider/GatenneaSlider/solver/data")


def load_dist(name: str):
    folder = DATA_ROOT / name
    p = folder / "checkpoint.pkl"
    if not p.exists():
        p = folder / "table.pkl"
    if not p.exists():
        return None
    with p.open('rb') as fh:
        obj = pickle.load(fh)
    return obj['dist'] if isinstance(obj, dict) and 'dist' in obj else obj


def constant_baseline(vals: np.ndarray) -> dict:
    """永远猜众数 / 均值 的成绩 —— 判断目标分布是否退化的尺子。"""
    vals_f = vals.astype(float)
    counts = np.bincount(vals)
    mode = int(counts.argmax())
    mean = vals_f.mean()
    out = {}
    for label, c in (('mode', mode), ('mean', mean)):
        err = np.abs(vals_f - c)
        out[label] = {
            'pred': c,
            'mae': float(err.mean()),
            'hit1': float((err <= 1.0).mean() * 100.0),
        }
    out['mode_share'] = float(counts.max() / len(vals) * 100.0)
    out['spread'] = (int(vals.min()), int(vals.max()), float(vals_f.std()))
    return out


def sample_grid(dist, frac, n_eval, seed):
    """随机留出：训练集与评估集互斥，且评估集按全表随机抽（不是取表头）。"""
    keys = list(dist.keys())
    total = len(keys)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(total)
    n_train = max(50, int(total * frac))
    train_idx, eval_idx = perm[:n_train], perm[n_train:n_train + n_eval]
    Xtr = np.empty((len(train_idx), 26), dtype=np.float32)
    ytr = np.empty(len(train_idx), dtype=np.int16)
    for i, j in enumerate(train_idx):
        k = keys[j]
        Xtr[i] = mig_features(k, 0, *meta)
        ytr[i] = dist[k]
    Xev = np.empty((len(eval_idx), 26), dtype=np.float32)
    yev = np.empty(len(eval_idx), dtype=np.int16)
    for i, j in enumerate(eval_idx):
        k = keys[j]
        Xev[i] = mig_features(k, 0, *meta)
        yev[i] = dist[k]
    return Xtr, ytr, Xev, yev


def _model():
    return HistGradientBoostingRegressor(
        max_iter=250, learning_rate=0.08, max_leaf_nodes=63,
        l2_regularization=1.0, min_samples_leaf=20, random_state=42)


meta = (4, 4, 2)


def main():
    global meta
    ap = argparse.ArgumentParser()
    ap.add_argument('--sizes', default='4_4_2,5_5_2,4_4_3')
    ap.add_argument('--fracs', default='0.01,0.05')
    ap.add_argument('--n-eval', type=int, default=8000)
    args = ap.parse_args()

    sizes = args.sizes.split(',')
    fracs = [float(x) for x in args.fracs.split(',')]

    print("=" * 76)
    print("一、目标距离分布体检 —— 若某尺寸众数占比极高，其 MAE/±1 天然虚高")
    print("=" * 76)
    print(f"{'尺寸':<8}{'条数':>10}{'距离范围':>10}{'标准差':>8}"
          f"{'众数占比':>9}{'猜众数MAE':>10}{'猜众数±1':>10}")
    dists = {}
    for name in sizes:
        d = load_dist(name)
        if d is None:
            print(f"{name:<8} (无数据)")
            continue
        vals = np.fromiter(d.values(), dtype=np.int16, count=len(d))
        b = constant_baseline(vals)
        dists[name] = (d, b)
        lo, hi, sd = b['spread']
        print(f"{name:<8}{len(vals):>10}{f'{lo}~{hi}':>10}{sd:>8.2f}"
              f"{b['mode_share']:>8.1f}%{b['mode']['mae']:>10.3f}"
              f"{b['mode']['hit1']:>9.1f}%")

    print("\n对照 mig_report2.txt（第二轮训练）声称的模型成绩：")
    print("  | 单尺寸 5_5_2，目标20% | 122512 | 490051 | MAE=0.332 | ±1=95.9% |")
    print("  | 多尺寸源20% + 目标20% | 1266709 | 490051 | MAE=0.345 | ±1=95.7% |")
    if '5_5_2' in dists:
        b = dists['5_5_2'][1]
        print(f"  → 5_5_2 猜常数 {b['mode']['pred']} 的基线："
              f"MAE={b['mode']['mae']:.3f}、±1={b['mode']['hit1']:.1f}%")
        gap = b['mode']['mae']
        print(f"  → 模型 MAE 0.332 相对「猜常数」{gap:.3f} 的改进："
              f"{'几乎为零（模型未学到有效信号）' if 0.332 > gap * 0.7 else '有实质改进'}")

    print("\n" + "=" * 76)
    print("二、4_4_2（真实跨度）重评：随机留出 + 数据量曲线")
    print("=" * 76)
    print("说明：exp17 的留出取自表头，而 BFS 表按层序写入 → 表头全是浅层状态，")
    print("      那次的 MAE=4.245 不成立，本组为修正值。")
    d = load_dist('4_4_2')
    vals = np.fromiter(d.values(), dtype=np.int16, count=len(d))
    b = constant_baseline(vals)
    print(f"\n基线（猜常数 {b['mode']['pred']}）：MAE={b['mode']['mae']:.3f} "
          f"±1={b['mode']['hit1']:.1f}%   猜均值：MAE={b['mean']['mae']:.3f} "
          f"±1={b['mean']['hit1']:.1f}%")
    print(f"\n{'采样':>6}{'训练条数':>10}{'MAE':>8}{'±1':>9}{'与基线MAE比':>12}"
          f"{'训练秒':>9}{'推理ms/千条':>13}")
    print("-" * 76)
    for frac in fracs:
        t0 = time.perf_counter()
        Xtr, ytr, Xev, yev = sample_grid(d, frac, args.n_eval, 20260930)
        t_feat = time.perf_counter() - t0
        model = _model()
        t0 = time.perf_counter()
        model.fit(Xtr, ytr)
        t_fit = time.perf_counter() - t0
        t0 = time.perf_counter()
        pred = model.predict(Xev)
        t_pred = time.perf_counter() - t0
        err = np.abs(pred - yev)
        mae = float(err.mean())
        hit1 = float((err <= 1.0).mean() * 100.0)
        print(f"{frac:>6.0%}{len(ytr):>10}{mae:>8.3f}{hit1:>8.1f}%"
              f"{mae / b['mode']['mae']:>11.2f}x{t_fit:>9.1f}"
              f"{t_pred * 1000 / len(yev):>13.3f}")


if __name__ == '__main__':
    main()
