# -*- coding: utf-8 -*-
"""
R2 的带方向复核：形状图到底是不是无向的。

背景
  05 L620 原来写「任何路径都能原路返回，这是定理」，_k1_r2_k9.py 的
  docstring 也据此写「单步可逆 => 形状图是无向图，距离对称」，于是只跑
  正向（矩形 -> 形状）就当作双向距离用了。
  但 out_2x4 的实测是 2,469 条边里 295 条单向（_cmp_edges.py /
  _chk_oneway.py），那条「定理」已撤回。所以「矩形 -> 形状」和
  「形状 -> 矩形」可能不是一个数，R2 的整张表都建在这个假设上。

做法
  1. 正向 BFS：从全部矩形出发，用 moves.legal_moves 推一步。
     沿途把每条有向边 (u -> v) 收进 rev[v]，得到完整反向邻接。
     同时得到 dist_f[v] = 矩形推到 v 的最少步数。
  2. 反向 BFS：还是从矩形出发，但只走 rev，得到 dist_r[v] = v 推回
     矩形的最少步数——这才是 R2 真正问的量。
  3. 逐点比较：相等 / 差一 / 只在一边有（即单向可达）。

输出
  形状总数、正向覆盖数、双向覆盖数、两侧 max、差异直方图、
  不一致的形状（含 ASCII）。
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


def ascii_of(S):
    rmin = min(r for r, _ in S); rmax = max(r for r, _ in S)
    cmin = min(c for _, c in S); cmax = max(c for _, c in S)
    return "\n".join(
        "".join("#" if (r, c) in S else "." for c in range(cmin, cmax + 1))
        for r in range(rmin, rmax + 1)
    )


def rect_sources(K):
    out = []
    for m in range(1, K + 1):
        if K % m:
            continue
        n = K // m
        S = frozenset((r, c) for r in range(m) for c in range(n))
        out.append(canon(S))
    return list(dict.fromkeys(out))


def main():
    K = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    sources = rect_sources(K)
    print(f"K={K}  rectangle sources: {len(sources)}")

    # ---------- 1. 正向 BFS，顺路建反向邻接 ----------
    dist_f = {}
    rev = {}
    fwd = {}
    edges = 0
    q = deque()
    for s0 in sources:
        if s0 not in dist_f:
            dist_f[s0] = 0
            q.append(s0)

    while q:
        S = q.popleft()
        for seam, side, comp, unit in moves.legal_moves(S, s=1):
            nxt = moves.apply_move(S, comp, unit, 1)
            if nxt is None:
                continue
            nn = canon(nxt)
            edges += 1
            rev.setdefault(nn, []).append(S)
            fwd.setdefault(S, []).append(nn)
            if nn not in dist_f:
                dist_f[nn] = dist_f[S] + 1
                q.append(nn)

    print(f"正向可达形状: {len(dist_f)}   有向边: {edges}")

    # ---------- 2. 反向 BFS：沿 rev 走回矩形 ----------
    dist_r = {}
    q = deque()
    for s0 in sources:
        if s0 not in dist_r:
            dist_r[s0] = 0
            q.append(s0)

    while q:
        S = q.popleft()
        for u in rev.get(S, ()):
            if u not in dist_r:
                dist_r[u] = dist_r[S] + 1
                q.append(u)

    print(f"反向可达形状: {len(dist_r)}")

    # ---------- 3. 比较 ----------
    both = set(dist_f) & set(dist_r)
    only_f = set(dist_f) - set(dist_r)   # 矩形推得出去，回不来
    only_r = set(dist_r) - set(dist_f)   # 理论上不可能：能回来的必然推得出

    max_f = max(dist_f.values())
    max_r = max(dist_r.values())
    print(f"max 正向 = {max_f}   max 反向 = {max_r}")
    print(f"只在正向有: {len(only_f)}   只在反向有: {len(only_r)}")

    diff = {}
    same = 0
    for v in both:
        d = dist_f[v] - dist_r[v]
        if d == 0:
            same += 1
        else:
            diff[d] = diff.get(d, 0) + 1
    print(f"两侧相等: {same} / {len(both)}  差分布: {dict(sorted(diff.items()))}")

    if only_f:
        print("\n=== 单向可达（推得出去、推不回来）===")
        for v in sorted(only_f, key=lambda s: dist_f[s]):
            print(f"[d_f={dist_f[v]}]")
            print(ascii_of(v))
            print()

    if diff:
        print("\n=== 距离不一致（d_f - d_r != 0）===")
        for v in sorted(both, key=lambda s: -(dist_f[s] - dist_r[s])):
            d = dist_f[v] - dist_r[v]
            if d == 0:
                continue
            print(f"[d_f={dist_f[v]} d_r={dist_r[v]} 差={d:+d}]")
            print(ascii_of(v))
            print()

    # 反向距离直方图（R2 应该用的那张）
    hist = {}
    for v in dist_r.values():
        hist[v] = hist.get(v, 0) + 1
    print("\n反向距离直方图:")
    for k in sorted(hist):
        print(f"  {k:2d}: {hist[k]}")

    # ---------- 4. 无向化 BFS：旧 _k1_rectdist.py 的口径 ----------
    # 把每条有向边都补上反向，等价于「假设可以原路走回」
    und = {}
    q = deque()
    for s0 in sources:
        und[s0] = 0
        q.append(s0)
    while q:
        S = q.popleft()
        for nn in fwd.get(S, ()):
            if nn not in und:
                und[nn] = und[S] + 1
                q.append(nn)
        for u in rev.get(S, ()):
            if u not in und:
                und[u] = und[S] + 1
                q.append(u)

    max_u = max(und.values())
    print(f"\nmax 无向化 = {max_u}   （旧表用的就是这个口径）")
    print(f"无向化覆盖: {len(und)}")

    eq_u_r = sum(1 for v in und if v in dist_r and und[v] == dist_r[v])
    gt_u_r = sum(1 for v in und if v in dist_r and und[v] > dist_r[v])
    lt_u_r = sum(1 for v in und if v in dist_r and und[v] < dist_r[v])
    print(f"无向化 vs 反向: 相等 {eq_u_r} / 反向更短 {gt_u_r} / 无向化更短 {lt_u_r}")

    print("\n=== 反向 max 的形状（R2 的真正最远集合）===")
    mx = max(dist_r.values())
    cnt = 0
    for v in sorted(dist_r):
        if dist_r[v] == mx:
            cnt += 1
            print(f"[{cnt}] d_r={mx}")
            print(ascii_of(v))
            print()
    print(f"距离 {mx} 的形状共 {cnt} 个")


if __name__ == "__main__":
    main()
