# -*- coding: utf-8 -*-
"""
数一条最短路用了几次 H、几次 V。

用途
  解释命题 B 比 A 多出来的 2 步。K=9 的 8×1+1 到 3×3 是 10 步，
  K=10 的 9×1+1 到 2×5 是 9 步，差 2。如果两者的 H 次数差 1、
  V 次数也差 1，那 +2 就有了解释。

用法
  python _k1_path_shape.py <K>
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
    # 起点：K-1 格长臂（第 0 行）+ 1 格挂在 (1,0)
    start = canon(frozenset([(0, c) for c in range(K - 1)] + [(1, 0)]))
    srcs = rect_sources(K)
    targets = set(s[2] for s in srcs if s[0] > 1)   # 排除 1×K 自环
    print(f"K={K}  起点:")
    print(ascii_of(start))
    print(f"目标源: {[(m, n) for m, n, _ in srcs if m > 1]}")

    # 正向 BFS：起点 -> 矩形
    parent = {}
    dist = {start: 0}
    q = deque([start])
    hit = start if start in targets else None
    while q and hit is None:
        S = q.popleft()
        for seam, side, comp, unit in moves.legal_moves(S, s=1):
            nxt = moves.apply_move(S, comp, unit, 1)
            if nxt is None:
                continue
            nn = canon(nxt)
            if nn in dist:
                continue
            dist[nn] = dist[S] + 1
            parent[nn] = (S, seam, side, unit)
            if nn in targets:
                hit = nn
                break
            q.append(nn)

    if hit is None:
        print("未找到矩形")
        return

    # 回溯
    path = [(hit, None, None, None)]
    S = hit
    while S in parent:
        S0, seam, side, unit = parent[S]
        path.append((S0, seam, side, unit))
        S = S0
    path.reverse()

    print(f"\n最短 {dist[hit]} 步：")
    nh = nv = 0
    for i, (S, seam, side, unit) in enumerate(path):
        if seam is None:
            continue
        kind = seam[0]
        if kind == "H":
            nh += 1
        else:
            nv += 1
    print(f"  H（水平移动）{nh} 次，V（垂直移动）{nv} 次，合计 {nh + nv} 步")
    print()
    for i, (S, seam, side, unit) in enumerate(path):
        if seam is None:
            print(f"[0] 起点")
            print(ascii_of(S))
            print()
            continue
        print(f"[{i}] {seam}  side={side}  unit={unit}")
        print(ascii_of(S))
        print()


if __name__ == "__main__":
    main()
