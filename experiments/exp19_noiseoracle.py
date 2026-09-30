# -*- coding: utf-8 -*-
"""exp19：给「完美距离」加噪声 —— 反推启发函数必须准到什么程度才有用。

背景（2026-09-30）：
  exp17 发现：用 BFS 真值距离当贪心目标（oracle），9~13 步、0.11 秒就能还原；
  而现有 gather_score 走 400 步还停在距离 4~6。差距 100 倍级 —— 说明
  **贪心骨架本身够用，瓶颈全在打分函数的准确性**。
  exp18 发现：距离拟合模型学到的信号几乎为零（4_4_2 上 MAE 相对「猜常数」
  只改进 2%，±1 反而更差；5_5_2 的好成绩是分布退化造成的幻觉）。

那么问题变成：**一个贪心目标要准到什么程度，才值得接进求解器？**
本脚本不给出现成模型，而是构造「带噪声的真值」作为假想启发：
  h(x) = true_dist(x) + N(0, sigma)
用 exp17 同一套贪心骨架跑，看不同噪声水平下还原率/步数怎么退化。

这样得到的是一条**验收线**：任何未来的距离估计方案（拟合模型也好，别的启发也罢），
只要它的实际误差水平落在这条线的哪一侧，就能直接判断值不值得用。

Usage:
    D:/python/python.exe -m experiments.exp19_noiseoracle --n-seeds 5
"""
from __future__ import annotations

import argparse
import random
import sys
import time

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

from experiments import harness as H  # noqa: E402
from solver.table_core import canonicalize  # noqa: E402
from solver.table_solver import load_table  # noqa: E402
from experiments.exp17_greedy import greedy_run  # noqa: E402


def make_noisy_oracle(table, diameter, sigma, rng_seed, frozen=False):
    """frozen=False：每次打分重新采样误差（模拟随机噪声）
       frozen=True ：同一个局面永远得到同一个偏差（模拟模型的系统性偏差）"""
    rng = np.random.default_rng(rng_seed)
    bias_cache = {}

    def scorer(coords_list, key_list):
        vals = np.empty(len(key_list), dtype=np.float64)
        for i, k in enumerate(key_list):
            d = table.get(k)
            if d is None:
                d = diameter
            if sigma > 0:
                if not frozen:
                    b = rng.normal(0.0, sigma)
                else:
                    b = bias_cache.get(k)
                    if b is None:
                        b = float(rng.normal(0.0, sigma))
                        bias_cache[k] = b
                d = float(np.clip(d + b, 0.0, diameter))
            vals[i] = -d / diameter
        return vals
    return scorer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--m', type=int, default=4)
    ap.add_argument('--n', type=int, default=4)
    ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--n-seeds', type=int, default=5, dest='n_seeds')
    ap.add_argument('--max-steps', type=int, default=400)
    ap.add_argument('--max-seconds', type=float, default=30.0)
    ap.add_argument('--sigmas', default='0,0.5,1,1.5,2,3')
    args = ap.parse_args()

    m, n, step = args.m, args.n, args.step
    table = load_table(m, n, step)
    if table is None:
        print(f"无 {m}_{n}_{step} 表，退出。")
        return
    diameter = max(table.values())
    print(f"=== exp19 启发准确度门槛  {m}x{n} step{step}，直径 {diameter} ===")

    def true_dist(key):
        return table.get(key)

    sigmas = [float(x) for x in args.sigmas.split(',')]
    seeds = list(range(1000, 1000 + args.n_seeds))

    print("\n--- A 组：随机噪声（每次打分重新抖一遍）---")
    print(f"\n{'噪声σ':>7}{'还原':>7}{'剩余距离中位':>13}{'步数中位':>10}"
          f"{'耗时中位':>10}  备注")
    print("-" * 62)
    run_group(args, seeds, table, diameter, m, n, step, sigmas, frozen=False)

    print("\n--- B 组：冻结噪声（同一局面永远同一个偏差 = 系统性偏差）---")
    print("这组模拟「模型对某类局面稳定地估错」，用于解释为何 MAE 不算差的模型也救不回来")
    print(f"\n{'噪声σ':>7}{'还原':>7}{'剩余距离中位':>13}{'步数中位':>10}"
          f"{'耗时中位':>10}  备注")
    print("-" * 62)
    run_group(args, seeds, table, diameter, m, n, step, sigmas, frozen=True)

    print("\n读法：σ 就是「启发与实际距离的误差水平」。")
    print("A 组代表打分的随机抖动，B 组代表模型的系统性偏差 —— 后者才真正致命。")


def run_group(args, seeds, table, diameter, m, n, step, sigmas, frozen):
    def true_dist(key):
        return table.get(key)

    for sigma in sigmas:
        solved = 0
        dists, steps, secs = [], [], []
        for seed in seeds:
            snap = H.gen_state(m, n, step, seed)
            g = H.load_game(snap)
            random.seed(seed)
            scorer = make_noisy_oracle(table, diameter, sigma, seed, frozen=frozen)
            try:
                r = greedy_run(g, step, scorer, true_dist,
                               max_steps=args.max_steps,
                               max_seconds=args.max_seconds)
            except Exception as exc:  # noqa: BLE001
                print(f"  seed{seed} 异常 {exc!r}")
                continue
            if r['end_dist'] == 0:
                solved += 1
            dists.append(r['end_dist'])
            steps.append(r['steps'])
            secs.append(r['seconds'])
        if not dists:
            continue
        med = lambda xs: sorted(xs)[len(xs) // 2]  # noqa: E731
        if sigma == 0:
            note = '完美启发（=查表）'
        elif solved == len(seeds):
            note = '可用'
        elif solved >= len(seeds) * 0.8:
            note = '边缘'
        else:
            note = '不可用'
        print(f"{sigma:>7.1f}{solved:>4}/{len(seeds):<2}{med(dists):>13}"
              f"{med(steps):>10}{med(secs):>9.2f}s  {note}")


if __name__ == '__main__':
    main()
