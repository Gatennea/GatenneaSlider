# -*- coding: utf-8 -*-
"""mod 不变量采样空间 A 的连通分量分解：与复原态空间的交集、死区结构。

问题（用户审查反例存档后提出）：
  若用 mod 不变量（着色集合匹配）的方式直接采样生成打乱，
  采样空间 A 与「包含复原态的空间」（从 goal 正向可达的集合 cone）
  是否有交集？交集多大？采样落到死区（不可达部分）的风险多大？
  死区的连通分量结构如何（观察到反例分量只有 1~2 个节点）？

口径：
  A    = 满足着色条件的全部规范形状（verify_coloring 同源枚举）
  cone = 从 goal 用 forward_edges 正向 BFS 的可达集（真边 ⟹ 真分量）
  交集 = A ∩ cone（cone ⊆ A 应当成立：移动保着色，可达必满足着色）
  死区 D = A − cone：mod 采样可能命中、但从复原态不可达的状态
  分量 = 全 A 上把单向弧视为无向边的连通分量；「不含复原状态的分量」
         即 docs 中的死分量（口径与 docs 一致，不能只在死区诱导子图上算）

报告：
  |A|、|cone|、|B|（表）、交集大小与采样命中率
  D 的分量个数、大小分布（Counter）、逐个样例渲染
  D→cone 出边数（理论应为 0）

用法：
  D:\\python\\python.exe experiments\math_repro\\shuffle_components.py 3_3_2 4_4_3
"""

import sys
import time
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402
from verify_coloring import (  # noqa: E402
    load_table, parse_puzzle, render, table_key_to_cells,
    enumerate_states, target_variants, class_dist,
)
from forward_closure import forward_edges  # noqa: E402


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def analyze(puzzle, render_n=5):
    m, n, step = parse_puzzle(puzzle)
    K = m * n
    table, tpath, complete = load_table(puzzle)
    B = set(table.keys()) if table else set()
    goal = tc.canonicalize(tc.goal_state(m, n))

    print('=' * 66)
    print(f'[{puzzle}] K={K} step={step}  表 B={len(B):,}'
          f'{"" if complete else "  ⚠表不完整"}')

    # ---- A：着色条件采样空间 ----
    targets, target_arrays = target_variants(m, n, step)
    A = set()
    t0 = time.time()
    n_states, _ = enumerate_states(
        K, target_arrays, step,
        lambda cells: A.add(tc.canonicalize(cells))
        if class_dist(cells, step) in targets else None)
    print(f'  A（着色采样空间）= {len(A):,} 规范形状  '
          f'（枚举 {n_states:,} 状态，{time.time()-t0:.0f}s）')

    # ---- cone：从 goal 正向 BFS ----
    t0 = time.time()
    cone = {goal}
    q = deque([goal])
    while q:
        h = q.popleft()
        cells = tc.int_to_coords(h, K)
        for y, _comp, _d in forward_edges(set(cells), step, K):
            if y not in cone:
                cone.add(y)
                q.append(y)
    print(f'  cone（复原态可达空间）= {len(cone):,}   ({time.time()-t0:.0f}s)')

    # ---- 交集与死区 ----
    inter = A & cone
    not_in_A = cone - A
    D = A - cone
    print(f'  交集 A ∩ cone = {len(inter):,}'
          f'{"   （cone ⊆ A ✓ 移动保着色）" if not not_in_A else f"  ⚠ cone−A={len(not_in_A)}"}')
    if D:
        print(f'  死区 D = A − cone = {len(D):,}  '
              f'（mod 均匀采样命中死区概率 = {len(D)/len(A):.2%}）')
    else:
        print('  死区 D = ∅：mod 采样空间全部可达（该尺寸无风险）')

    # ---- A 上的连通分量（把单向弧 x→y 当作无向边 x–y）----
    # 口径对齐 docs：「不含复原状态的着色集合连通图分量」= 死分量。
    # 含复原态的分量不只包含正向可达集：可解但正向不可达的「缺口」态
    # 沿着它到 goal 的路径也连在复原态分量上；不可解态若有指向可解态
    # 的弧（如逃逸链）同样会被连进去。所以死分量要在全 A 上算，
    # 不能只在 D = A − 正向可达集 的诱导子图上算。
    t0 = time.time()
    uf = _UF()
    d_to_cone = 0
    for h in A:
        uf.find(h)
        cells = tc.int_to_coords(h, K)
        for y, _c, _d in forward_edges(set(cells), step, K):
            uf.union(h, y)
            if h in D and y in cone:
                d_to_cone += 1
    comps = {}
    for h in A:
        comps.setdefault(uf.find(h), []).append(h)
    live = comps.get(uf.find(goal), [])          # 含复原态的分量
    dead_comps = [v for r, v in comps.items() if r != uf.find(goal)]
    dead_states = sum(len(v) for v in dead_comps)
    hist = Counter(len(v) for v in dead_comps)
    print(f'  连通分量（全 A）：含复原态的分量 = {len(live):,} 个状态；'
          f'不含复原态的分量（死分量）= {len(dead_comps):,} 个，'
          f'共 {dead_states:,} 个状态，大小分布 '
          f'{dict(sorted(hist.items()))}   ({time.time()-t0:.0f}s)')
    print(f'  死区中指向正向可达集的出边 {d_to_cone:,} 条'
          f'（来自「可解但正向不可达」的缺口态踏入可达集，合法）')

    # ---- 与表的对照 ----
    if B:
        print(f'  对照表：|B|={len(B):,}  '
              f'B−cone={len(B - cone):,}（缺口）  cone−B={len(cone - B):,}（逃逸）')

    # ---- 样例：最大几个死分量 ----
    ordered = sorted(dead_comps, key=len, reverse=True)
    if ordered:
        print(f'  最大死分量样例（最多 {render_n} 个）：')
        for comp in ordered[:render_n]:
            print(f'    分量大小 {len(comp)}：')
            for h in comp[:3]:
                print(render(table_key_to_cells(h, K)))
    else:
        print('  无死分量：着色集合全部连在复原态分量上')
    return {'puzzle': puzzle, 'A': len(A), 'cone': len(cone), 'B': len(B),
            'inter': len(inter), 'dead': len(D),
            'n_comps': len(dead_comps), 'dead_states': dead_states,
            'hist': dict(sorted(hist.items())),
            'out_to_cone': d_to_cone}


def main():
    puzzles = sys.argv[1:] or ['2_3_1', '3_3_1', '3_3_2']
    results = []
    for p in puzzles:
        try:
            results.append(analyze(p))
        except FileNotFoundError:
            print(f'[{p}] 找不到表，跳过')
        print()
    print('=' * 66)
    print('汇总：')
    for r in results:
        print(f"  {r['puzzle']:<8} |A|={r['A']:>7,}  |cone|={r['cone']:>7,}  "
              f"|B|={r['B']:>7,}  交集={r['inter']:>7,}  死区={r['dead']:>6,}  "
              f"死分量={r['n_comps']:>5,}  分布={r['hist']}")


if __name__ == '__main__':
    main()
