# -*- coding: utf-8 -*-
"""逃逸态（锥 − B）的正向求解验证：决定逃逸根因。

背景：edge_consistency 全量对比证明 E1/E2 在 B 内完全一致（假前驱=0、
表内漏边=0），缺口 1,408 是真实结构不对称。剩下的逃逸态（y ∈ 锥, y ∉ B）
有两种互斥解释：

  ① 表不完整：predecessors 在 B 外侧有假阴性，漏掉了 y（y 实际可解）
     → 需要修复反向生成器/重建表；「打乱可产生死局」的担忧不成立
  ② y 是真死局：从 y 出发任何正向操作都到不了 goal
     → 游戏若用正向移动打乱，会产生不可解局面（文档担心的不可根除 bug）
     → C「任何操作有限步可逆」猜想在 4_4_3 被直接证伪

判定方法（不依赖表）：从每个逃逸态 y 出发做正向 BFS（forward_edges），
  goal 被访问到 → ①；BFS 穷尽仍无 goal → ②。

用法：
  python experiments/math_repro/verify_escapes.py 4_4_3
"""

import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402
from verify_coloring import load_table, parse_puzzle, render, table_key_to_cells  # noqa: E402
from forward_closure import forward_edges  # noqa: E402


def analyze(puzzle, sample=3):
    m, n, step = parse_puzzle(puzzle)
    total = m * n
    table, path, complete = load_table(puzzle)
    B = set(table.keys())
    goal = tc.canonicalize(tc.goal_state(m, n))
    print('=' * 66)
    print(f'[{puzzle}] B={len(B):,}  goal∈B={goal in B}')

    # 1) 找逃逸态：从 goal 正向 BFS 得锥，逃逸 = 锥 − B（口径同 forward_closure，
    #    能覆盖「逃逸态再走到逃逸态」的链）
    t0 = time.time()
    visited = {goal}
    queue = deque([goal])
    esc_edge = {}
    while queue:
        h = queue.popleft()
        cells = set(tc.int_to_coords(h, total))
        for y, _, _ in forward_edges(cells, step, total):
            if y not in B and y not in esc_edge:
                esc_edge[y] = h
            if y not in visited:
                visited.add(y)
                queue.append(y)
    escapes = set(esc_edge)
    print(f'  |锥| = {len(visited):,}   逃逸态（锥−B）= {len(escapes)} 个  ({time.time()-t0:.0f}s)',
          flush=True)

    # 2) 对每个逃逸态：从 y 出发正向 BFS，看 goal 是否可达
    results = []
    for y in sorted(escapes):
        t1 = time.time()
        visited = {y}
        queue = deque([y])
        hit = (y == goal)
        while queue and not hit:
            h = queue.popleft()
            cells = set(tc.int_to_coords(h, total))
            for y2, _, _ in forward_edges(cells, step, total):
                if y2 == goal:
                    hit = True
                    break
                if y2 not in visited:
                    visited.add(y2)
                    queue.append(y2)
        results.append((y, hit, len(visited), time.time() - t1))
        print(f'    逃逸 {y}: '
              f'{"✓ 可解（goal 可达），表漏了它" if hit else "✗ 真死局（BFS 穷尽无 goal）"}  '
              f'BFS 访问 {len(visited):,}  {time.time()-t1:.1f}s', flush=True)

    n_hit = sum(1 for _, hit, _, _ in results if hit)
    print(f'\n  汇总: {n_hit}/{len(results)} 个逃逸态可解')
    if n_hit == len(results) and results:
        print('  → ① 表不完整：predecessors 假阴性漏掉真状态，需修反向生成器/重建表')
        print('     「正向打乱产生死局」不成立；C 猜想不受逃逸影响（缺口另议）')
    elif results:
        print('  → ② 存在真死局：正向移动可走进不可解状态')
        print('     C「有限步可逆」被证伪；游戏打乱若走正向移动会产生不可解局面')

    # 3) 渲染样例
    for y, hit, nv, _ in results[:sample]:
        print(f'\n  逃逸样例 (可解={hit}, BFS {nv:,}): {y}')
        print(render(table_key_to_cells(y, total)))
        if y in esc_edge:
            print(f'    来源边: {esc_edge[y]} → {y}')

    return results


def main():
    puzzles = sys.argv[1:] or ['4_4_3']
    for p in puzzles:
        try:
            analyze(p)
        except FileNotFoundError:
            print(f'[{p}] 找不到表，跳过')
        print()


if __name__ == '__main__':
    main()
