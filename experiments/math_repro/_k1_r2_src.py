# -*- coding: utf-8 -*-
"""
R2 的分源复核：到底是哪个矩形源把 max 顶上去的。

背景
  05 说「上界 K+1 只被细长 L 达到」，但没说清「为什么」。K=9 只有一个矩形源
  （3×3，1×9 是孤点），所以答案是全 3×3 的代价。K≥10 有多个矩形源
  （2×5 与 1×10；2×6、3×4 与 1×12），如果某个源单独就能顶到 K+1，
  那就说明「方」的矩形比「长」的贵，细长臂到方的距离就是那个多出来的步。

做法
  1. 建全图有向边（正向 BFS 途中顺手收 rev），得到每个形状的
     dist_r = 「形状 -> 任一矩形」的最短步数（这是 05 真正该用的量）。
  2. 对每个矩形源单独跑一次反向 BFS，得到 dist_r[源]。
  3. 比各源的 max，以及「合并后最远形状」落在哪个源上。

用法
  python _k1_r2_src.py <K>
"""
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import moves


def rot90(S):
    R = max(r for r, _ in S) + 1
    return frozenset((c, R - 1 - r) for r, c in S)


def mirror(S):
    C = max(c for _, c in S) + 1
    return frozenset((r, C - 1 - c) for r, c in S)


def canon(S):
    best = None
    T = moves.normalize(S)
    for _ in range(4):
        for cand in (T, mirror(T)):
            k = tuple(sorted(moves.normalize(cand)))
            if best is None or k < best:
                best = k
        T = moves.normalize(rot90(T))
    return frozenset(best)


def ascii_of(S):
    rmin = min(r for r, _ in S); rmax = max(r for r, _ in S)
    cmin = min(c for _, c in S); cmax = max(c for _, c in S)
    return "\n".join(
        "".join("#" if (r, c) in S else "." for c in range(cmin, cmax + 1))
        for r in range(rmin, rmax + 1)
    )


def rect_sources(K):
    """返回 [(m, n, canon_shape)]，保留尺寸标签"""
    out = []
    seen = set()
    for m in range(1, K + 1):
        if K % m:
            continue
        n = K // m
        S = canon(frozenset((r, c) for r in range(m) for c in range(n)))
        if S in seen:
            continue
        seen.add(S)
        out.append((m, n, S))
    return out


def main():
    K = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    srcs = rect_sources(K)
    print(f"K={K}  矩形源: {[(m, n) for m, n, _ in srcs]}")

    # ---- 建全图（正向推边），收 rev ----
    rev = {}
    all_shapes = set()
    q = deque(s[2] for s in srcs)
    for _, _, S in srcs:
        all_shapes.add(S)
    while q:
        S = q.popleft()
        for seam, side, comp, unit in moves.legal_moves(S, s=1):
            nxt = moves.apply_move(S, comp, unit, 1)
            if nxt is None:
                continue
            nn = canon(nxt)
            rev.setdefault(nn, []).append(S)
            if nn not in all_shapes:
                all_shapes.add(nn)
                q.append(nn)
    print(f"形状总数: {len(all_shapes)}   有向边: {sum(len(v) for v in rev.values())}")

    # ---- 合并口径（R2 真正的量）----
    dist_all = {}
    q = deque()
    for _, _, S in srcs:
        if S not in dist_all:
            dist_all[S] = 0
            q.append(S)
    while q:
        S = q.popleft()
        for u in rev.get(S, ()):
            if u not in dist_all:
                dist_all[u] = dist_all[S] + 1
                q.append(u)
    mx_all = max(dist_all.values())
    print(f"\n合并口径 max = {mx_all}   覆盖 {len(dist_all)} / {len(all_shapes)}")

    # ---- 逐源口径 ----
    print("\n逐源 max:")
    per = {}
    for m, n, S0 in srcs:
        d = {S0: 0}
        q = deque([S0])
        while q:
            S = q.popleft()
            for u in rev.get(S, ()):
                if u not in d:
                    d[u] = d[S] + 1
                    q.append(u)
        per[(m, n)] = d
        print(f"  只用 {m}×{n}: max = {max(d.values())}   覆盖 {len(d)}")

    # ---- 最远形状：合并口径下是谁、各源下是多少 ----
    print(f"\n=== 合并口径距离 {mx_all} 的形状，以及它在各源下的距离 ===")
    for v in sorted(dist_all):
        if dist_all[v] != mx_all:
            continue
        row = "  ".join(
            f"{m}×{n}:{per[(m, n)].get(v, '×')}" for m, n, _ in srcs
        )
        print(f"d_all={mx_all}   {row}")
        print(ascii_of(v))
        print()


if __name__ == "__main__":
    main()
