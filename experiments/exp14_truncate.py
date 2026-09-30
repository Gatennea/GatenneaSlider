# -*- coding: utf-8 -*-
"""实验14：段1「早交接」扫描——梯度聚拢只走前 k 步就交给搜索。

起因：exp13 证明**后处理压缩无效**（删除中位 0 步）——冗长不是绕回旧局面的循环，
而是聚拢段自己走了一条低效路径（每步都在推进，从不回到旧局面）。
所以与其事后压缩，不如**早点把局面交给搜索**：截断 gradient_gather 的输出。

本实验在「已知长解」的种子上扫描 k，看成功率与步数怎么变，回答一件事：
**聚拢步数是不是给多了？**

用法：
    python -m experiments.exp14_truncate --n 5
"""
import argparse
import time

from experiments import harness as H
from experiments.exp9_rep import replay_steps
from experiments.exp12_chain import solve as chain_solve
from experiments.exp13_compress import optimal_distance, median

# 4×4 step2 上已知的长解种子（exp13 实测 299~684 步的那几个）
LONG_SEEDS = [1001, 1008, 1012, 1017, 1019]
CAPS = [None, 60, 30, 15, 8]


def run(m, n, st, seeds, caps):
    table = {}
    for cap in caps:
        rows = []
        t0 = time.time()
        for seed in seeds:
            snap = H.gen_state(m, n, st, seed)
            t1 = time.perf_counter()
            try:
                res, who = chain_solve(snap, gather_cap=cap)
            except Exception as e:
                res, who = None, f'exc:{e!r}'
            dt = time.perf_counter() - t1
            ok = bool(res) and replay_steps(snap, res)[0]
            opt = optimal_distance(snap)
            rows.append({'seed': seed, 'ok': ok, 'len': len(res) if res else 0,
                         'opt': opt, 't': dt, 'who': who})
            tag = f"{len(res):>4}步" if ok else f"败({who})"
            ratio = f"{len(res)/opt:.1f}x" if (ok and opt) else '-'
            print(f"  cap={str(cap):>4} seed{seed} {tag} 最优={opt} {ratio} {dt:>5.1f}s")
        solved = [r for r in rows if r['ok']]
        with_opt = [r for r in solved if r['opt']]
        table[cap] = {
            'rate': 100 * len(solved) / len(rows),
            'median': median([r['len'] for r in solved]) if solved else 0,
            'ratio': median([r['len'] / r['opt'] for r in with_opt]) if with_opt else 0,
            't': time.time() - t0,
        }
        print(f"  → cap={cap}: 成功 {len(solved)}/{len(rows)} "
              f"步数中位 {table[cap]['median']} "
              f"倍数中位 {table[cap]['ratio']:.1f}x "
              f"({table[cap]['t']:.0f}s)\n")

    print("=== 汇总（4x4 step2，长解种子）===")
    print(f"{'cap':>6} {'成功率':>8} {'步数中位':>8} {'倍数中位':>8} {'耗时':>7}")
    for cap in caps:
        t = table[cap]
        print(f"{str(cap):>6} {t['rate']:>7.0f}% {t['median']:>8} "
              f"{t['ratio']:>7.1f}x {t['t']:>6.0f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--n', type=int, default=5, help='取前 n 个长解种子')
    args = ap.parse_args()
    m, n, st = (int(x) for x in args.configs.split('x'))
    run(m, n, st, LONG_SEEDS[:args.n], CAPS)


if __name__ == '__main__':
    main()
