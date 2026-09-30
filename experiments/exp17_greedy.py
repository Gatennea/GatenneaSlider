# -*- coding: utf-8 -*-
"""exp17：聚拢段「贪心目标」四路对照 —— 用 BFS 真值表当裁判。

用户问题（2026-09-30）：距离拟合能不能让聚拢提效？单独用拟合距离、单独用聚拢度，
哪个效率更高？

设计要点：
  * 裁判是 4_4_2 完整 BFS 表 —— 任何一步之后都能查到「离还原还剩几步真值」，
    所以不需要接上后续搜索就能比较「谁更接近目标」。
  * 统一ţ贪心骨架：每步枚举合法动作 → 批量打分 → 排序（未访问优先，再分数）→ 走一步。
    四个模式只换打分函数，其余完全相同；打分耗时计入各自总时间，天然公平。
  * 距离预测一律批量推理（单状态 11.4ms vs 批量 0.018ms，这是能否落地的关键）。

四个模式：
  1 gather  现有口径：gather_score = 最大重叠率
  2 dist    只用拟合距离（越小越好 → 打分 = -pred/直径）
  3 mix     两者加权：alpha*gather_score - (1-alpha)*pred/直径
  4 oracle  用表里的真实距离当贪心目标（理论上限参考，不可用于生产）

Usage:
    D:/python/python.exe -m experiments.exp17_greedy --n 5
    D:/python/python.exe -m experiments.exp17_greedy --n 10 --max-steps 800
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

from experiments import harness as H  # noqa: E402
from solver.actions import apply_action, enumerate_valid_actions  # noqa: E402
from solver.state import restore, snapshot  # noqa: E402
from solver.table_core import canonicalize  # noqa: E402
from solver.table_solver import load_table  # noqa: E402
from solver.ml.gather_solver import (  # noqa: E402
    _is_mod_compliant, detect_target_corner, gather_metrics,
)

MIG_DIR = Path(r"E:/program_project/other/doubaotest/狀態拓撲圖分析")
MODEL2_PATH = MIG_DIR / "mig_model2_histgb.pkl"


# --------------------------------------------------------------------------
# 打分器：统一签名 scorer(coords_list, key_list) -> np.ndarray（越大越好）
# --------------------------------------------------------------------------
def make_gather_scorer(m, n):
    def scorer(coords_list, key_list):
        return np.array([gather_metrics(c, m, n)['score'] for c in coords_list],
                        dtype=np.float64)
    return scorer


def make_dist_scorer(model, m, n, step, diameter):
    def scorer(coords_list, key_list):
        X = np.asarray([mig_features(k, 0, m, n, step) for k in key_list],
                       dtype=np.float32)
        pred = model.predict(X)
        return -pred / max(diameter, 1)
    return scorer


def make_mix_scorer(model, m, n, step, diameter, alpha):
    gather = make_gather_scorer(m, n)
    dist = make_dist_scorer(model, m, n, step, diameter)

    def scorer(coords_list, key_list):
        return alpha * gather(coords_list, key_list) + (1 - alpha) * dist(
            coords_list, key_list)
    return scorer


def make_oracle_scorer(table, diameter):
    def scorer(coords_list, key_list):
        out = np.empty(len(key_list), dtype=np.float64)
        for i, k in enumerate(key_list):
            d = table.get(k)
            out[i] = -(d if d is not None else diameter) / max(diameter, 1)
        return out
    return scorer


# --------------------------------------------------------------------------
# 统一贪心骨架（实验副本：刻意不做「回退历史最优」与去环优化，纯看前进效率）
# --------------------------------------------------------------------------
def greedy_run(game, step, scorer, true_dist, max_steps=600, max_seconds=60.0,
               use_mod=True):
    m, n = game.m, game.n
    total = m * n

    target_corner = detect_target_corner(_coords(game), m, n, step) if use_mod else None
    _mod_compliant = _is_mod_compliant if target_corner is not None else None
    _mod_r0, _mod_c0 = target_corner if target_corner else (0, 0)

    visited = set()
    actions = []
    cand_counts = []
    trace = []  # (累计秒, 步数, 真值剩余距离)

    def cur_dist():
        return true_dist(canonicalize(_coords(game)))

    t_start = time.perf_counter()
    d0 = cur_dist()
    trace.append((0.0, 0, d0))

    reason = 'max_steps'
    for i in range(max_steps):
        if game.is_solved():
            reason = 'solved'
            break
        if time.perf_counter() - t_start >= max_seconds:
            reason = 'timeout'
            break

        snap = snapshot(game)
        cands = enumerate_valid_actions(game, step)
        results = []
        for act in cands:
            if not apply_action(game, act, step):
                restore(game, snap)
                continue
            nc = _coords(game)
            if len(nc) != total:
                restore(game, snap)
                continue
            results.append((act, nc, canonicalize(nc)))
            restore(game, snap)

        if not results:
            reason = 'no_candidates'
            break
        cand_counts.append(len(results))

        scores = scorer([r[1] for r in results], [r[2] for r in results])
        rows = []
        for j, (_act, _nc, key) in enumerate(results):
            mod_ok = (_mod_compliant is None
                      or _mod_compliant(_nc, step, _mod_r0, _mod_c0))
            met = gather_metrics(_nc, m, n)
            rows.append((float(scores[j]), met['bbox_area'], _act, key, mod_ok))
        rows.sort(key=lambda x: (x[3] in visited, -x[0], -x[4], x[1]))

        _, _, best_act, best_key, _ = rows[0]
        ok = apply_action(game, best_act, step)
        if not ok:
            reason = 'invalid_action'
            break
        actions.append(best_act)
        visited.add(best_key)

        trace.append((time.perf_counter() - t_start, len(actions), cur_dist()))

    return {
        'actions': actions,
        'reason': reason,
        'start_dist': d0,
        'end_dist': cur_dist(),
        'steps': len(actions),
        'seconds': trace[-1][0],
        'trace': trace,
        'mean_cands': float(np.mean(cand_counts)) if cand_counts else 0.0,
    }


def _coords(game):
    return frozenset((b.location[0], b.location[1]) for b in game.blocks)


# --------------------------------------------------------------------------
# 模型：优先用现有 mig_model2；可选为当前尺寸专门训练
# --------------------------------------------------------------------------
def eval_model(model, X, y):
    pred = model.predict(X)
    err = np.abs(pred - y)
    return float(err.mean()), float((err <= 1.0).mean() * 100.0)


def train_for_size(table, m, n, step, frac, seed=20260930):
    """在目标尺寸的完整表上采样训练（跨域迁移已证死，每尺寸必须采样）。"""
    from sklearn.ensemble import HistGradientBoostingRegressor
    keys = list(table.keys())
    total = len(keys)
    keep = max(50, int(total * frac))
    rng = np.random.default_rng(seed)
    pick = rng.choice(total, size=keep, replace=False)
    pick_set = set(int(p) for p in pick)

    X = np.empty((keep, 26), dtype=np.float32)
    y = np.empty(keep, dtype=np.int16)
    hold_keys = []
    idx = 0
    for i, (k, d) in enumerate(table.items()):
        if i in pick_set:
            X[idx] = mig_features(k, 0, m, n, step)
            y[idx] = d
            idx += 1
            if idx == keep:
                break
        elif len(hold_keys) < 3000:
            hold_keys.append((k, d))
    model = HistGradientBoostingRegressor(
        max_iter=250, learning_rate=0.08, max_leaf_nodes=63,
        l2_regularization=1.0, min_samples_leaf=20, random_state=42)
    model.fit(X, y)
    return model, X, y, hold_keys


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--m', type=int, default=4)
    ap.add_argument('--n', type=int, default=4)
    ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--n-seeds', type=int, default=5, dest='n_seeds')
    ap.add_argument('--max-steps', type=int, default=600)
    ap.add_argument('--max-seconds', type=float, default=60.0)
    ap.add_argument('--alpha', type=float, default=0.5)
    ap.add_argument('--train-frac', type=float, default=0.01,
                    help='为当前尺寸专门训练时的采样比例；0=只用 mig_model2')
    args = ap.parse_args()

    m, n, step = args.m, args.n, args.step
    print(f"=== exp17 贪心目标四路对照  {m}x{n} step{step} ===")
    print("加载 BFS 真值表（裁判）...", flush=True)
    table = load_table(m, n, step)
    if table is None:
        print(f"无 {m}_{n}_{step} 表，无法做真值裁判。退出。")
        return
    diameter = max(table.values())
    print(f"表 {len(table)} 条，直径 {diameter}", flush=True)

    def true_dist(key):
        return table.get(key)

    # ---- 模型准备 ----
    if args.train_frac > 0:
        print(f"为 {m}x{n} step{step} 专门训练（采样 {args.train_frac:.1%}）...", flush=True)
        t0 = time.perf_counter()
        model, Xtr, ytr, hold = train_for_size(table, m, n, step, args.train_frac)
        used = f"本尺寸采样{args.train_frac:.1%}"
        if hold:
            Xh = np.asarray([mig_features(k, 0, m, n, step) for k, _ in hold],
                            dtype=np.float32)
            yh = np.asarray([d for _, d in hold], dtype=np.int16)
            mae, hit1 = eval_model(model, Xh, yh)
            print(f"  训练 {len(ytr)} 条 / {time.perf_counter()-t0:.1f}s，"
                  f"留出 {len(yh)} 条评测 MAE={mae:.3f} ±1={hit1:.1f}%", flush=True)
    else:
        print("加载 mig_model2（多尺寸源20% + 5_5_2 目标20%）...", flush=True)
        with MODEL2_PATH.open('rb') as fh:
            model = pickle.load(fh)
        used = "mig_model2（跨域）"
        t0 = time.perf_counter()
        keys = list(table.keys())[:5000]
        Xh = np.asarray([mig_features(k, 0, m, n, step) for k in keys], dtype=np.float32)
        yh = np.asarray([table[k] for k in keys], dtype=np.int16)
        mae, hit1 = eval_model(model, Xh, yh)
        print(f"  本尺寸 {len(yh)} 条评测 MAE={mae:.3f} ±1={hit1:.1f}% "
              f"（{time.perf_counter()-t0:.1f}s）", flush=True)

    modes = [
        ('gather', make_gather_scorer(m, n)),
        ('dist', make_dist_scorer(model, m, n, step, diameter)),
        (f'mix{args.alpha:g}', make_mix_scorer(model, m, n, step, diameter, args.alpha)),
        ('oracle', make_oracle_scorer(table, diameter)),
    ]

    seeds = list(range(1000, 1000 + args.n_seeds))
    rows = {name: [] for name, _ in modes}

    for seed in seeds:
        snap = H.gen_state(m, n, step, seed)
        d0 = true_dist(canonicalize(frozenset(snap['coords'])))
        print(f"\n--- seed {seed}  初始真值距离 {d0} ---", flush=True)
        for name, scorer in modes:
            g = H.load_game(snap)
            random.seed(seed)
            try:
                r = greedy_run(g, step, scorer, true_dist,
                               max_steps=args.max_steps,
                               max_seconds=args.max_seconds)
            except Exception as exc:  # noqa: BLE001
                print(f"  {name:<9} 异常 {exc!r}", flush=True)
                continue
            rows[name].append((seed, r))
            ms_step = r['seconds'] * 1000 / max(r['steps'], 1)
            print(f"  {name:<9} {r['steps']:>4}步 {r['seconds']:>6.2f}s "
                  f"{ms_step:>7.1f}ms/步  距离 {r['start_dist']}→{r['end_dist']}"
                  f"  ({r['reason']})  候选{r['mean_cands']:.0f}", flush=True)

    # ---- 汇总 ----
    print("\n" + "=" * 78)
    print(f"汇总 {len(seeds)} 局  模型={used}")
    print(f"{'模式':<10}{'还原':>6}{'剩余距离中位':>13}{'步数中位':>10}"
          f"{'耗时中位':>10}{'ms/步':>9}")
    print("-" * 78)
    for name, _ in modes:
        rs = rows[name]
        if not rs:
            continue
        solved = sum(1 for _, r in rs if r['end_dist'] == 0)
        dists = sorted(r['end_dist'] for _, r in rs)
        steps = sorted(r['steps'] for _, r in rs)
        secs = sorted(r['seconds'] for _, r in rs)
        ms = [r['seconds'] * 1000 / max(r['steps'], 1) for _, r in rs]
        med = lambda xs: xs[len(xs) // 2]  # noqa: E731
        print(f"{name:<10}{solved:>4}/{len(rs):<2}{med(dists):>13}"
              f"{med(steps):>10}{med(secs):>9.2f}s{med(ms):>9.1f}")

    # ---- 关键对照：达到同一距离水平，谁花的时间少 ----
    print("\n各模式『降到某距离所需时间/步数』（取已完成局的中位；'-'=未达成）")
    print(f"{'模式':<10}{'降至≤6':>14}{'降至≤3':>14}{'降至0(还原)':>14}")
    print("-" * 78)
    for name, _ in modes:
        cells = []
        for thr in (6, 3, 0):
            times, cnt = [], 0
            for _, r in rows[name]:
                hit = [t for t, _s, d in r['trace'] if d <= thr]
                if hit:
                    times.append(hit[0])
                    cnt += 1
            if times:
                times.sort()
                cells.append(f"{times[len(times)//2]:>6.2f}s({cnt})")
            else:
                cells.append(f"{'-':>14}")
        print(f"{name:<10}" + "".join(cells))


if __name__ == '__main__':
    main()
