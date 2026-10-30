# -*- coding: utf-8 -*-
"""探针 2：相邻对 → 缝 的唯一性（含带洞盘面 / 米字错位态）。

规则：对每个缝族算 gap_rank，取 min(rank_a, rank_b) 作线号，保留
side_of 真的把 a/b 分到两侧的候选；真缝应当在 is_valid_gap 仍为 True 的
那几个里唯一。带洞/错位态是最容易出岔子的两种局面，一并统计。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game_mi as gm
import game_triangle as gt


def candidates(a, b, families, rank, side):
    out = []
    for fam in families:
        ra, rb = rank(fam, a), rank(fam, b)
        if ra == rb:
            continue
        line = min(ra, rb)
        if side(fam, line, a) != side(fam, line, b):
            out.append((fam, line))
    return out


def stats(name, cells, neighbors, families, rank, side, valid):
    from collections import Counter
    cnt = Counter()
    samples = []
    seen = set()
    for a in cells:
        for b in neighbors(a):
            if b not in cells:
                continue
            pair = frozenset((tuple(a), tuple(b)))
            if pair in seen:
                continue
            seen.add(pair)
            cands = candidates(a, b, families, rank, side)
            good = [c for c in cands if valid(*c)]
            cnt[len(good)] += 1
            if len(good) != 1 and len(samples) < 5:
                samples.append((a, b, cands, good))
    print(f'{name}: {dict(cnt)}')
    for s in samples:
        print('   ', s)


def tri_case(tag, k, drop=frozenset()):
    from game_triangle import TriangleSliderMatrix
    g = TriangleSliderMatrix(k)
    cells = g.positions() - set(drop)
    g.blocks = [b for b in g.blocks if gt.tri_key(b) in cells]
    g.update_matrix()
    stats(f'三角 {tag}', cells, gt.neighbors, ('h', 'p', 'n'), gt.gap_rank,
          gt.side_of, g.is_valid_gap)


def mi_case(tag, m, n, drop=frozenset(), shift=0.0):
    from game_mi import MiSliderMatrix
    g = MiSliderMatrix(m, n)
    cells = g.positions() - set(drop)
    if shift:
        cells = {(r + shift, c + shift, q) for (r, c, q) in cells}
    g.blocks = [b for b in g.blocks if gm.mi_key(b) in
                g.positions()]  # 重建
    from game import Block
    g.blocks = [Block(list(k)) for k in sorted(cells, key=tuple)]
    g.update_matrix()
    stats(f'米字 {tag}', cells, gm.neighbors, ('h', 'v', 'd1', 'd2'),
          gm.gap_rank, gm.side_of, g.is_valid_gap)


tri_case('满盘 k=5', 5)
tri_case('挖心 k=5', 5, {(2, 1, True), (2, 1, False), (2, 2, True)})
tri_case('缺角 k=4', 4, {(0, 0, True), (3, 0, True)})
mi_case('满盘 3x3', 3, 3)
mi_case('缺块 3x3', 3, 3, {(1, 1, 'N'), (1, 1, 'E')})
mi_case('错位 +0.5', 3, 3, shift=0.5)
