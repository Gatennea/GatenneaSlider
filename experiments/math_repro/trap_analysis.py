# -*- coding: utf-8 -*-
"""分析 4_4_2 的 9 个死局（逃逸态）是否有共同特点。

数据：experiments/math_repro/trap_paths_4_4_2.json（9 个逃逸态 + 入口边）+ 表 B（table.pkl）。
检验项：
  1. 形态特征分离扫描：复用 second_invariant.features 的全部特征，
     9 个死局 vs 随机 2000 个可解态，找出「死局全体一致、可解态中罕见」的特征。
  2. 距离层分布：死局全在距复原态 13-18 步的浅层，与可解态距离分布对照。
  3. 逃逸子图：9 个死局之间的正向边（谁连谁）、强连通分量、出度（冻结程度）。
  4. 入口边最后一步：终末移动的组大小、移动前后空格结构、逆步是否立即可走回
     （验证粘连锁死）。

用法：
  python experiments/math_repro/trap_analysis.py
"""

import json
import random
import sys
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402
from verify_coloring import (  # noqa: E402
    load_table, parse_puzzle, table_key_to_cells)
from forward_closure import forward_edges  # noqa: E402
from second_invariant import _try_move, features  # noqa: E402

DIRS4 = ((-1, 0), (1, 0), (0, -1), (0, 1))


def hole_stats(cells):
    """外接盒内空格的 4 连通块数、其中不贴盒边的（内部洞）块数、总空格数。"""
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    r0, r1, c0, c1 = min(rs), max(rs), min(cs), max(cs)
    cellset = set(cells)
    empty = {(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)
             if (r, c) not in cellset}
    comps = 0
    interior = 0
    while empty:
        comps += 1
        seed = empty.pop()
        stack = [seed]
        comp = {seed}
        touch = False
        while stack:
            r, c = stack.pop()
            if r in (r0, r1) or c in (c0, c1):
                touch = True
            for dr, dc in DIRS4:
                q = (r + dr, c + dc)
                if q in empty:
                    empty.discard(q)
                    comp.add(q)
                    stack.append(q)
        if not touch:
            interior += 1
    return comps, interior, (r1 - r0 + 1) * (c1 - c0 + 1) - len(cellset)


def scc(nodes, succ):
    """Kosaraju 强连通分量。"""
    rev = {s: [] for s in nodes}
    for a, bs in succ.items():
        for b in bs:
            rev[b].append(a)
    order = []
    seen = set()

    def dfs(u):
        seen.add(u)
        for v in succ[u]:
            if v not in seen:
                dfs(v)
        order.append(u)

    for s in nodes:
        if s not in seen:
            dfs(s)
    comps = []
    seen.clear()

    def rdfs(u, acc):
        seen.add(u)
        acc.append(u)
        for v in rev[u]:
            if v not in seen:
                rdfs(v, acc)

    for s in reversed(order):
        if s not in seen:
            acc = []
            rdfs(s, acc)
            comps.append(sorted(acc))
    return comps


def main():
    src = Path(__file__).resolve().parent / 'trap_paths_4_4_2.json'
    data = json.loads(src.read_text(encoding='utf-8'))
    puzzle = data['puzzle']
    m, n, step = parse_puzzle(puzzle)
    K = m * n
    table, _tpath, complete = load_table(puzzle)
    assert complete, '需要完整表'
    B = set(table.keys())
    traps = data['traps']
    trap_set = {t['state'] for t in traps}

    trap_cells = {t['state']: [tuple(c) for c in table_key_to_cells(t['state'], K)]
                  for t in traps}

    # ------------------------------------------------------------------
    # 1. 特征分离扫描（9 死局 vs 2000 可解态）
    # ------------------------------------------------------------------
    print('=' * 66)
    print('1. 形态特征分离扫描（死局全体一致 且 可解态占比 ≤ 20% 的特征）')
    rng = random.Random(20261012)
    sample = rng.sample(sorted(B), 2000)
    trap_f = {s: features(cs, step) for s, cs in trap_cells.items()}
    samp_f = [features(table_key_to_cells(h, K), step) for h in sample]

    keys = list(next(iter(trap_f.values())).keys())
    rows = []
    for k in keys:
        tv = Counter(trap_f[s][k] for s in trap_cells)
        maj, nagree = tv.most_common(1)[0]
        if nagree < 7:
            continue
        bv = sum(1 for f in samp_f if f[k] == maj) / len(samp_f)
        if bv <= 0.20:
            rows.append((bv, k, maj, nagree, tv))
    for bv, k, maj, nagree, tv in sorted(rows):
        print(f'  {k:<12} 死局 {nagree}/9 取 {maj!r}，可解态中占比 {bv:6.2%}'
              f'  （死局取值分布 {dict(tv)}）')
    if not rows:
        print('  （无全体一致的强分离特征）')

    # ------------------------------------------------------------------
    # 2. 距离层分布
    # ------------------------------------------------------------------
    print('=' * 66)
    print('2. 距离层分布（死局距复原态 13-18 步）')
    b_dists = [table[h] for h in sample]
    shallow = sum(1 for d in b_dists if d <= 18) / len(b_dists)
    print(f'  可解态抽样：最大距离 {max(table.values())}，中位数附近 '
          f'{sorted(b_dists)[len(b_dists) // 2]}')
    print(f'  可解态中距离 ≤ 18 的占比：{shallow:.2%}')
    print(f'  死局距离：{sorted(t["dist"] for t in traps)}（全部 ≤ 18）')

    # ------------------------------------------------------------------
    # 3. 逃逸子图
    # ------------------------------------------------------------------
    print('=' * 66)
    print('3. 逃逸子图（9 个死局之间的正向边）')
    succ = {}
    for t in traps:
        cells = trap_cells[t['state']]
        outs = forward_edges(set(cells), step, K)
        for h, _comp, _d in outs:
            assert h in trap_set or h in B, '出边落到未知区域'
        succ[t['state']] = [h for h, _c, _d in outs if h in trap_set]
    idx = {t['state']: i + 1 for i, t in enumerate(traps)}
    for t in traps:
        s = t['state']
        dests = ', '.join(str(idx[d]) for d in succ[s]) or '无'
        print(f'  死局{idx[s]:>2}（距离 {t["dist"]:>2}）出度 {len(succ[s])}，'
              f'可走到死局：{dests}')
    comps = scc(list(trap_set), succ)
    print(f'  强连通分量：{[[idx[s] for s in c] for c in comps]}')
    frozen = [idx[s] for s in trap_set if not succ[s]]
    print(f'  完全冻结（一步都走不动）的死局：{sorted(frozen)}')

    # ------------------------------------------------------------------
    # 4. 入口边最后一步（粘连锁死验证）
    # ------------------------------------------------------------------
    print('=' * 66)
    print('4. 入口边最后一步（终末移动与逆步验证）')
    for t in traps:
        e = t['edges'][-1]
        comp = [tuple(c) for c in e['comp']]
        d = tuple(e['d'])
        before = [tuple(c) for c in e['parent_cells']]
        after = trap_cells[t['state']]
        hb, hi, hz = hole_stats(before)
        ha, ia, za = hole_stats(after)
        comp_end = {(r + d[0] * step, c + d[1] * step) for r, c in comp}
        back = _try_move(set(after), comp_end, (-d[0] * step, -d[1] * step),
                         step, K)
        print(f'  死局{idx[t["state"]]:>2}（距离 {t["dist"]:>2}）：'
              f'终末移动组 {len(comp)} 格，方向 {d}；'
              f'空格块 {hb}→{ha}（内部洞 {hi}→{ia}）；'
              f'逆步立即走回：{"可行" if back is not None else "非法（锁死）"}')

    print('=' * 66)
    print('完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
