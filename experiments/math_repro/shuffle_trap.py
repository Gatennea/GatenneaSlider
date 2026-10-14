# -*- coding: utf-8 -*-
"""自动打乱踩死局风险：逃逸态（cone − B）清单与入口边统计。

问题（用户 2026-10 提出）：等级2矩形谜题是最经典玩法，自动打乱
（从 goal 出发的正向随机移动）会不会踩进死局？

口径：
  - 打乱落点必在 cone（goal 正向可达集）内
  - 死局 = 到不了任何通关状态 = 不在完整表 B 内
  - 打乱能踩到的死局恰好 = 逃逸态 cone − B
  - 风险面 = 从 cone 内部指向逃逸态的边（打乱真实会走的入口）

方法：单次正向 BFS 遍历全 cone，展开每个状态时检查每条出边：
  目标 y ∉ B → 记录入口边。BFS 同时给出每个逃逸态的最短距离。
  注意：入口边的逆边必然违规（否则 y 能回到可解侧、进而通关），
  即死局入口全部是单步不可逆边——与「单步不可逆 100% 粘连型」的
  全量验证结论互相咬合。

用法：
  python experiments/math_repro/shuffle_trap.py 4_4_2
"""

import json
import sys
import time
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402
from verify_coloring import (  # noqa: E402
    load_table, parse_puzzle, render, table_key_to_cells,
)
from forward_closure import forward_edges  # noqa: E402


def analyze(puzzle):
    m, n, step = parse_puzzle(puzzle)
    K = m * n
    table, tpath, complete = load_table(puzzle)
    if table is None:
        print(f'[{puzzle}] 找不到表，跳过')
        return None
    B = set(table.keys())
    goal = tc.canonicalize(tc.goal_state(m, n))

    print('=' * 66)
    print(f'[{puzzle}] K={K} step={step}  表 B={len(B):,}'
          f'{"" if complete else "  ⚠表不完整"}')

    # ---- 单次正向 BFS：遍历 cone，顺带抓所有指向 B 之外的出边 ----
    # parent 记录首次发现该状态的前驱与移动分量/位移，用于回放复原态→逃逸态路径
    dist = {goal: 0}
    parent = {goal: None}
    entry = Counter()          # 逃逸态 y -> 来自 cone 的入边数
    entry_from = {}            # y -> 一个入口样例 h
    entry_src = Counter()      # 入口来源分类：可解侧 / 逃逸侧
    q = deque([goal])
    t0 = time.time()
    while q:
        h = q.popleft()
        cells = tc.int_to_coords(h, K)
        for y, comp, d in forward_edges(set(cells), step, K):
            if y not in B:
                entry[y] += 1
                entry_from.setdefault(y, h)
                entry_src['可解侧' if h in B else '逃逸侧'] += 1
            if y not in dist:
                dist[y] = dist[h] + 1
                parent[y] = (h, sorted(comp), tuple(d))
                q.append(y)
    print(f'  cone 遍历 = {len(dist):,} 状态，{time.time()-t0:.0f}s')

    # ---- 逃逸态 = cone 中打乱可达却永远无解的状态 ----
    trap = set(dist) - B
    print(f'  逃逸态（打乱可达但无解）= {len(trap):,}  '
          f'（打乱终态命中率 = {len(trap)/len(dist):.5%}）')
    if not trap:
        print('  该尺寸打乱永远不会踩进死局（cone ⊆ B 精确成立）')
        return {'puzzle': puzzle, 'cone': len(dist), 'trap': 0, 'entry': 0}

    # ---- 入口边汇总 ----
    total_entry = sum(entry.values())
    print(f'  入口边（cone 内部 → 逃逸态）= {total_entry:,} 条，'
          f'其中来自可解侧 {entry_src.get("可解侧", 0):,} 条、'
          f'来自逃逸侧 {entry_src.get("逃逸侧", 0):,} 条')

    # ---- 路径回放数据：复原态 → 每个逃逸态的最短路径（父链回溯） ----
    # 每条边存规范框架下的 (parent_cells, comp, d, child_cells)：
    # comp/d 在 parent 的规范坐标系里，回放脚本按 D4 对齐后映射回绝对坐标。
    def chain(y):
        edges = []
        cur = y
        while parent[cur] is not None:
            h, comp, d = parent[cur]
            edges.append({
                'parent_cells': [list(c) for c in sorted(tc.int_to_coords(h, K))],
                'comp': [list(c) for c in comp],
                'd': list(d),
                'child_cells': [list(c) for c in sorted(tc.int_to_coords(cur, K))],
            })
            cur = h
        edges.reverse()
        return edges

    paths_out = {
        'puzzle': puzzle, 'm': m, 'n': n, 'step': step,
        'goal_cells': [list(c) for c in sorted(tc.int_to_coords(goal, K))],
        'traps': [],
    }
    for y in sorted(trap, key=lambda s: dist[s]):
        paths_out['traps'].append({
            'state': y, 'dist': dist[y],
            'entry_edges': entry[y], 'entry_example': entry_from.get(y),
            'edges': chain(y),
        })
    out_path = Path(__file__).resolve().parent / f'trap_paths_{puzzle}.json'
    out_path.write_text(json.dumps(paths_out, ensure_ascii=False),
                        encoding='utf-8')
    print(f'  路径数据已写入 {out_path.name}'
          f'（{len(paths_out["traps"])} 条路径）')

    # ---- 逐个逃逸态：距离、入边数、入口样例 ----
    print('  逃逸态清单：')
    for y in sorted(trap, key=lambda s: dist[s]):
        h = entry_from.get(y)
        print(f'    距离 {dist[y]:>3}，入边 {entry[y]:>3} 条：')
        print(render(table_key_to_cells(y, K)))
        if h is not None:
            src = '可解侧' if h in B else '逃逸侧'
            print(f'      入口样例（{src}，距离 {dist[h]}）：')
            for line in render(table_key_to_cells(h, K)).splitlines():
                print(f'      {line}')

    # ---- 逃逸态出边必须封闭在逃逸态内（否则能回可解侧）----
    leak = 0
    for y in trap:
        cells = tc.int_to_coords(y, K)
        for z, _c, _d in forward_edges(set(cells), step, K):
            if z in B:
                leak += 1
    print(f'  逃逸态出边指向可解侧的条数 = {leak}（应为 0，否则与表矛盾）')
    print(f'  总耗时 {time.time()-t0:.0f}s')
    return {'puzzle': puzzle, 'cone': len(dist), 'trap': len(trap),
            'entry': total_entry}


def main():
    puzzles = sys.argv[1:] or ['4_4_2']
    results = []
    for p in puzzles:
        try:
            r = analyze(p)
        except FileNotFoundError:
            print(f'[{p}] 找不到表，跳过')
            r = None
        if r:
            results.append(r)
        print()
    if results:
        print('=' * 66)
        print('汇总：')
        for r in results:
            print(f"  {r['puzzle']:<8} cone={r['cone']:>7,}  "
                  f"逃逸态={r['trap']:>4,}  入口边={r['entry']:>5,}")


if __name__ == '__main__':
    main()
