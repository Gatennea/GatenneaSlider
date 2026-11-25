# -*- coding: utf-8 -*-
"""
K=9 形状图上的 R2 紧性机检。

问题：05 L533 说「到矩形距离 = 10 的形状只有一个」，但文档只有 10 步构造样本，
      没有「9 步做不到」的机检。这里直接算多源 BFS 距离。

做法：
  - 状态 = 4-连通 9 格形状，按「平移 + D4」规范化（与 repro_fast 的商同口径）
  - 边 = moves.legal_moves + apply_move（s=1），每步检查碰撞与四连通
  - 注意：这里只跑【正向】（矩形 -> 形状）。R2 真正问的是反向（形状 -> 矩形），
    两者在有向图里不是同一个数（见 _k1_r2_dir.py）。
    原 docstring 写【单步可逆 => 形状图无向】是错的，2026-11-25 修正。
  - 多源 = 所有矩形形状（3×3 满块、1×9 直条，D4 后各一个代表）

输出：
  形状总数、距离分布、最远形状的 ASCII、一条最短路径
"""
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import moves


def rot90(S):
    # (r,c) -> (c, R-1-r)
    R = max(r for r, _ in S) + 1
    return frozenset((c, R - 1 - r) for r, c in S)


def mirror(S):
    C = max(c for _, c in S) + 1
    return frozenset((r, C - 1 - c) for r, c in S)


def canon(S):
    """平移 + D4 取最小表示"""
    best = None
    T = moves.normalize(S)
    for _ in range(4):
        for cand in (T, mirror(T)):
            k = tuple(sorted(moves.normalize(cand)))
            if best is None or k < best:
                best = k
        T = moves.normalize(rot90(T))
    return frozenset(best)


def find_path(S, parent):
    """从 S 回溯到源，返回 [(shape, seam, unit), ...]，第一步的 seam 为 None"""
    path = [(S, None, None)]
    while S in parent:
        S0, seam, unit = parent[S]
        path.append((S0, seam, unit))
        S = S0
    return list(reversed(path))


def ascii_of(S):
    rmin = min(r for r, _ in S); rmax = max(r for r, _ in S)
    cmin = min(c for _, c in S); cmax = max(c for _, c in S)
    lines = []
    for r in range(rmin, rmax + 1):
        lines.append("".join("#" if (r, c) in S else "." for c in range(cmin, cmax + 1)))
    return "\n".join(lines)


def main():
    K = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    # 源：所有 m×n 满矩形（m*n = K），D4 去重后
    sources = []
    for m in range(1, K + 1):
        if K % m:
            continue
        n = K // m
        S = frozenset((r, c) for r in range(m) for c in range(n))
        sources.append(canon(S))
    sources = list(dict.fromkeys(sources))
    print(f"K={K}, rectangle sources: {len(sources)}")

    dist = {}
    parent = {}
    q = deque()
    for s0 in sources:
        if s0 not in dist:
            dist[s0] = 0
            q.append(s0)

    while q:
        S = q.popleft()
        for seam, side, comp, unit in moves.legal_moves(S, s=1):
            nxt = moves.apply_move(S, comp, unit, s=1)
            if nxt is None:
                continue
            nn = canon(nxt)
            if nn in dist:
                continue
            dist[nn] = dist[S] + 1
            parent[nn] = (S, seam, unit)
            q.append(nn)

    print(f"reachable shapes: {len(dist)}")
    hist = {}
    for v in dist.values():
        hist[v] = hist.get(v, 0) + 1
    print("distance histogram:", dict(sorted(hist.items())))
    dmax = max(dist.values())
    print(f"max distance: {dmax}")

    far = [S for S, v in dist.items() if v == dmax]
    print(f"\nshapes at distance {dmax}: {len(far)}")
    for S in far:
        rmin = min(r for r, _ in S); rmax = max(r for r, _ in S)
        cmin = min(c for _, c in S); cmax = max(c for _, c in S)
        print(f"--- bbox {rmax - rmin + 1}x{cmax - cmin + 1} ---")
        print(ascii_of(S))

    # 最远的那条路径
    if far:
        S = far[0]
        path = find_path(S, parent)
        nH = sum(1 for _, seam, _ in path if seam and seam.startswith("H"))
        nV = sum(1 for _, seam, _ in path if seam and seam.startswith("V"))
        print(f"\nshortest path from rectangle to the farthest shape: {len(path) - 1} steps  (H={nH}, V={nV})")
        for i, (shp, seam, unit) in enumerate(path):
            tag = "" if seam is None else f"   <{seam} {unit}>"
            print(f"[{i}]{tag}")
            print(ascii_of(shp))


if __name__ == '__main__':
    main()
