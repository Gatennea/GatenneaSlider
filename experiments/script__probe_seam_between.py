# -*- coding: utf-8 -*-
"""探针：任意两相邻单位块之间的「那条缝」能否由 rank 反推。

捆绑需要在「组内相邻两块」之间找到分隔它们的那条缝（用于
bandage_internal_seams + 点缝绑/解）。方形直接 (min行/列)，异形的缝族
不同，靠 gap_rank 反推：同族 rank 相等则这条缝不切它们；不相等就取
min(rank_a, rank_b) 作线号，再用 side_of 复核 a/b 确实落在两侧。

本探针遍历三角/米字的全部相邻对，统计：
  - 有几族给出「a、b 分居两侧」的平局解（应当恰好 1 个）；
  - 该线号在本局面 is_valid_gap 是否为真。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game_mi as gm
import game_triangle as gt


def seams_between(a, b, families, rank, side, valid):
    out = []
    for fam in families:
        ra, rb = rank(fam, a), rank(fam, b)
        if ra == rb:
            continue
        line = min(ra, rb)
        if side(fam, line, a) != side(fam, line, b):
            out.append((fam, line, valid(fam, line)))
    return out


def probe_tri():
    from game_triangle import TriangleSliderMatrix
    g = TriangleSliderMatrix(5)
    cells = g.positions()
    bad = []
    for a in cells:
        for b in gt.neighbors(a):
            if b not in cells or b <= a:
                continue
            got = seams_between(a, b, ('h', 'p', 'n'), gt.gap_rank, gt.side_of,
                                g.is_valid_gap)
            if len(got) != 1 or not got[0][2]:
                bad.append((a, b, got))
    print(f'三角：{len(cells)} 块，异常相邻对 {len(bad)}')
    for row in bad[:8]:
        print('   ', row)


def probe_mi():
    from game_mi import MiSliderMatrix
    g = MiSliderMatrix(3, 3)
    cells = g.positions()
    bad = []
    skipped = 0
    for a in cells:
        for b in gm.neighbors(a):
            if b not in cells:
                continue
            if tuple(a) <= tuple(b):
                continue
            try:
                got = seams_between(a, b, ('h', 'v', 'd1', 'd2'), gm.gap_rank,
                                    gm.side_of, g.is_valid_gap)
            except TypeError:
                skipped += 1
                continue
            if len(got) != 1 or not got[0][2]:
                bad.append((a, b, got))
    print(f'米字：{len(cells)} 块，异常相邻对 {len(bad)}，跳过 {skipped}')
    for row in bad[:8]:
        print('   ', row)


probe_tri()
probe_mi()
