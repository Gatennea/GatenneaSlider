# -*- coding: utf-8 -*-
"""把每类单独缩成 4 点上的置换群，跑带权最短路。

输入：tag_bfs 的 gens 导出（每行 16 个 v[t] + @depth）。
做法：
  1) 只留严格单类生成元（支撑全落在同一 (r mod 2, c mod 2) 类）；
  2) 把该类 4 个位置映射到 0..3，把那个 16 点置换收缩成 4 点置换；
  3) 在 4! = 24 个状态上跑 Dijkstra，边权 = 该公式的游戏步数；
  4) 输出每类的可达群阶与直径（最坏最优步数）。

这直接回答「四类各解一遍要多少步」，不需要 (4!)⁴ 的联合搜索。
"""

import heapq
import itertools
import re
from collections import defaultdict

M = N = 4
S = 2
P = M * N


def load(path):
    out = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line[0] not in '0123456789':
                continue
            m = re.search(r'@\s*(\d+)\s*$', line)
            depth = int(m.group(1)) if m else None
            body = line[:m.start()] if m else line
            nums = [int(x) for x in re.findall(r'-?\d+', body)]
            if len(nums) < P or depth is None:
                continue
            out.append((nums[:P], depth))
    return out


def klass(p):
    r, c = divmod(p, N)
    return (r % S, c % S)


def support(v):
    return [t for t in range(P) if v[t] != t]


def class_points(k):
    return [p for p in range(P) if klass(p) == k]


def shrink(v, pts):
    """把 16 点置换限制到该类，返回 4 点置换映射（标签->位置，索引 0..3）。"""
    idx = {p: i for i, p in enumerate(pts)}
    g = []
    for i, p in enumerate(pts):
        t = v[p]            # 位置 p 上是标签 t
        g.append(idx.get(t, None))
    if any(x is None for x in g):
        return None
    return tuple(g)


def apply(c, inv_g):
    """内容表 c（位置->标签）执行一次置换 g 的逆：c'[j] = c[inv_g[j]]。

    g 的语义是「位置 i 上的标签去位置 g[i]」，所以 inv_g[g[i]] = i。
    """
    return tuple(c[inv_g[j]] for j in range(len(c)))


def inv_of(g):
    inv = [0] * len(g)
    for i, p in enumerate(g):
        inv[p] = i
    return tuple(inv)


K = 4  # 每类 4 个位置


def dijkstra(gens):
    """gens: list[(inv_tuple, weight)]"""
    ident = tuple(range(K))
    best = {ident: 0}
    pq = [(0, ident)]
    while pq:
        d, st = heapq.heappop(pq)
        if d > best.get(st, 1 << 30):
            continue
        for g, w in gens:
            ns = apply(st, g)
            nd = d + w
            if nd < best.get(ns, 1 << 30):
                best[ns] = nd
                heapq.heappush(pq, (nd, ns))
    return best


def main(path):
    gens = load(path)
    per = defaultdict(list)
    for v, dep in gens:
        sup = support(v)
        ks = {klass(p) for p in sup}
        if len(ks) != 1:
            continue
        k = ks.pop()
        per[k].append((v, dep))

    print(f'{path}: 共 {len(gens)} 条；单类 {sum(len(x) for x in per.values())} 条')
    print()

    total_worst = 0
    for k in sorted(per):
        pts = class_points(k)
        items = []
        for v, dep in per[k]:
            g = shrink(v, pts)
            if g is None:
                continue
            items.append((g, dep, support(v)))
        print(f'=== 类{k} 位置 {pts} ===')
        for g, dep, sup in sorted(items, key=lambda x: x[1]):
            print(f'  depth={dep} perm={g} sup={sup}')

        # 去重（同一置换可能在多个深度出现，保留最浅）
        uniq = {}
        for g, dep, sup in items:
            if g not in uniq or dep < uniq[g]:
                uniq[g] = dep
        gens24 = [(inv_of(g), w) for g, w in uniq.items()]

        best = dijkstra(gens24)
        # 群阶 = 闭包大小
        seen = {tuple(range(K))}
        frontier = [tuple(range(K))]
        while frontier:
            nf = []
            for st in frontier:
                for g, w in gens24:
                    ns = apply(st, g)
                    if ns not in seen:
                        seen.add(ns)
                        nf.append(ns)
            frontier = nf
        diam = max(best.values())
        print(f'  唯一置换 {len(gens24)} 个；闭包群阶 {len(seen)}；'
              f'可达状态 {len(best)}；加权直径 {diam}')
        hist = defaultdict(int)
        for s, d in best.items():
            hist[d] += 1
        print('  距离分布:', dict(sorted(hist.items())))
        print()
        total_worst += diam

    print(f'四类最坏相加 = {total_worst} 步')
    print('（对比：四类同步生成元给出的上界是 3 次 4 步 = 12 步）')
    return 0


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else '_s2_d8_gens.log'))
