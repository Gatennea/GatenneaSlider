# -*- coding: utf-8 -*-
"""最优解距离分布 + 死局深度。

回答 docs 中两处待补充：
  1. 「以最优解距离为横轴、状态数为纵轴绘制折线图，形状是什么？」
     table.pkl 的值就是每个状态到复原态的最短步数（反向BFS层号），
     直接取值统计，无需任何搜索。
  2. 逃逸死局（正向可达但不可解）在正向图里离复原态多深——
     深度决定游戏随机打乱游走撞上它们的概率量级。

用法：
  D:\\python\\python.exe experiments\math_repro\\distance_distribution.py 4_4_3 4_4_2
  D:\\python\\python.exe experiments\math_repro\\distance_distribution.py 4_4_3 --escape-depth
"""

import argparse
import sys
import time
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402
from verify_coloring import load_table, parse_puzzle  # noqa: E402
from forward_closure import forward_edges  # noqa: E402


def dist_stats(vals):
    """返回 (mean, median, mode, std, skew, p90, p99)。"""
    n = len(vals)
    s = sorted(vals)
    mean = sum(s) / n
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    cnt = Counter(s)
    mode = cnt.most_common(1)[0]
    var = sum((x - mean) ** 2 for x in s) / n
    std = var ** 0.5
    if std > 0:
        skew = sum((x - mean) ** 3 for x in s) / n / std ** 3
    else:
        skew = 0.0
    p90 = s[min(n - 1, int(n * 0.90))]
    p99 = s[min(n - 1, int(n * 0.99))]
    return mean, median, mode, std, skew, p90, p99


def show_hist(vals, width=46):
    cnt = Counter(vals)
    mx = max(cnt.values())
    for d in sorted(cnt):
        c = cnt[d]
        bar = '#' * max(1, round(c / mx * width)) if c else ''
        print(f'    {d:>3} |{bar} {c:,} ({c / len(vals):.1%})')


def analyze(puzzle):
    table, path, complete = load_table(puzzle)
    if table is None:
        print(f'[{puzzle}] 找不到表，跳过')
        return None
    vals = list(table.values())
    mean, median, mode, std, skew, p90, p99 = dist_stats(vals)

    print('=' * 66)
    print(f'[{puzzle}] 可解状态 {len(vals):,}  '
          f'{"" if complete else "⚠表不完整"}  {path}')
    print(f'  上帝之数（最大距离）= {max(vals)}')
    print(f'  均值 {mean:.2f}  中位数 {median}  众数 {mode[0]}（{mode[1]:,} 个）'
          f'  标准差 {std:.2f}  偏度 {skew:+.3f}')
    print(f'  90分位 {p90}  99分位 {p99}')
    print('  距离 → 状态数：')
    show_hist(vals)
    return {'puzzle': puzzle, 'n': len(vals), 'max': max(vals),
            'mean': mean, 'median': median, 'mode': mode[0],
            'std': std, 'skew': skew}


def escape_depth(puzzle):
    """从 goal 正向 BFS 记层号，报告逃逸死局的深度。"""
    m, n, step = parse_puzzle(puzzle)
    K = m * n
    table, _, _ = load_table(puzzle)
    B = set(table.keys())
    goal = tc.canonicalize(tc.goal_state(m, n))

    t0 = time.time()
    depth = {goal: 0}
    q = deque([goal])
    escapes = {}
    while q:
        h = q.popleft()
        d = depth[h]
        for y, _, _ in forward_edges(set(tc.int_to_coords(h, K)), step, K):
            if y not in depth:
                depth[y] = d + 1
                q.append(y)
                if y not in B:
                    escapes[y] = d + 1
    print('=' * 66)
    print(f'[{puzzle}] 死局正向深度（从复原态起的最短步数）  '
          f'(|锥|={len(depth):,}, {time.time()-t0:.0f}s)')
    if not escapes:
        print('  无逃逸死局')
        return
    ds = sorted(escapes.values())
    print(f'  死局 {len(escapes)} 个，深度 {ds}（锥内深度最大 = '
          f'{max(depth.values())}）')
    for h, d in sorted(escapes.items(), key=lambda kv: kv[1]):
        print(f'    深度 {d}: {h}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('puzzles', nargs='+')
    ap.add_argument('--escape-depth', action='store_true')
    args = ap.parse_args()

    results = []
    for p in args.puzzles:
        try:
            if args.escape_depth:
                escape_depth(p)
            else:
                r = analyze(p)
                if r:
                    results.append(r)
        except FileNotFoundError:
            print(f'[{p}] 找不到表，跳过')
        print()

    if results and not args.escape_depth:
        print('=' * 66)
        print('汇总（跨谜题形状对比）：')
        for r in results:
            print(f"  {r['puzzle']:<8} n={r['n']:>8,}  max={r['max']:>3}  "
                  f"均值={r['mean']:>6.2f}  中位={r['median']:>3}  "
                  f"众数={r['mode']:>3}  标准差={r['std']:>5.2f}  "
                  f"偏度={r['skew']:+.3f}")


if __name__ == '__main__':
    main()
