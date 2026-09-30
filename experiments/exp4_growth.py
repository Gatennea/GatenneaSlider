# -*- coding: utf-8 -*-
"""实验4：反向 BFS 增长探测（限深反向表可行性）。

从还原矩形出发，用 table_core.predecessors 逐层反向展开并规范化，
统计每个深度新增/累计的规范状态数，判断"距复原 ≤K 步"局部表的规模。
"""
import argparse
import time

from solver import table_core as TC


def probe(m, n, step, max_depth=14, time_budget=180.0):
    goal = TC.goal_state(m, n)
    goal_key = TC.canonicalize(goal)
    visited = {goal_key}
    frontier = [goal_key]
    print(f"{m}x{n} step{step}  还原态规范key数=1")
    t0 = time.time()
    for d in range(1, max_depth + 1):
        new_keys = set()
        for key in frontier:
            coords = frozenset(TC.int_to_coords(key, m * n))
            # predecessors 已返回规范 int 键
            new_keys |= TC.predecessors(coords, m, n, step)
        new_keys -= visited
        visited |= new_keys
        frontier = list(new_keys)
        dt = time.time() - t0
        print(f"  深度{d:>2}: 新增 {len(new_keys):>7}  累计 "
              f"{len(visited):>8}  {dt:>7.1f}s")
        if not new_keys:
            print("  （已穷尽）")
            break
        if dt > time_budget:
            print("  （超出时间预算，停止）")
            break
    return len(visited)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--depth', type=int, default=14)
    ap.add_argument('--time', type=float, default=180.0)
    args = ap.parse_args()
    for s in args.configs.split(','):
        m, n, st = s.split('x')
        probe(int(m), int(n), int(st), args.depth, args.time)
        print()


if __name__ == '__main__':
    main()
