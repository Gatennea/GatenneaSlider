# -*- coding: utf-8 -*-
"""
R2 反向距离的精简版，专为大 K 设计。

与 _k1_r2_dir.py 的区别：
  只建 rev（反向邻接），不建 fwd、不做无向化对比、不做逐点比较。
  内存大约减半，K=14（901,971 形状）才跑得动。

用法
  python _k1_r2_r.py <K>
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
    srcs = rect_sources(K)
    print(f"K={K}  矩形源: {[(m, n) for m, n, _ in srcs]}", flush=True)

    rev = {}
    seen = set(s[2] for s in srcs)
    q = deque(seen)
    n_edges = 0
    while q:
        S = q.popleft()
        for seam, side, comp, unit in moves.legal_moves(S, s=1):
            nxt = moves.apply_move(S, comp, unit, 1)
            if nxt is None:
                continue
            nn = canon(nxt)
            n_edges += 1
            rev.setdefault(nn, []).append(S)
            if nn not in seen:
                seen.add(nn)
                q.append(nn)
    print(f"形状总数: {len(seen)}   有向边: {n_edges}", flush=True)

    # 反向 BFS：形状 -> 任一矩形
    dist = {}
    q = deque()
    for _, _, s0 in srcs:
        if s0 not in dist:
            dist[s0] = 0
            q.append(s0)
    while q:
        S = q.popleft()
        for u in rev.get(S, ()):
            if u not in dist:
                dist[u] = dist[S] + 1
                q.append(u)

    mx = max(dist.values())
    print(f"反向可达: {len(dist)} / {len(seen)}   max = {mx}", flush=True)

    hist = {}
    for v in dist.values():
        hist[v] = hist.get(v, 0) + 1
    print("反向距离直方图:")
    for k in sorted(hist):
        print(f"  {k:2d}: {hist[k]}", flush=True)

    cnt = 0
    for v in sorted(dist):
        if dist[v] == mx:
            cnt += 1
            if cnt <= 12:
                print(f"[{cnt}] d={mx}")
                print(ascii_of(v))
                print()
    print(f"距离 {mx} 的形状共 {cnt} 个")


if __name__ == "__main__":
    main()
