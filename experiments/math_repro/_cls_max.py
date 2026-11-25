# -*- coding: utf-8 -*-
"""列每类 24 状态里距离最大的那些，并标出各自的循环型。

用来确认「类内 4-cycle 到底几步」，以及 15 步那一档都是什么。
"""

import heapq
import re
import sys

P = 16
N = 4
S = 2
K = 4


def load(path):
    out = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line[0] not in '0123456789':
                continue
            m = re.search(r'@\s*(\d+)\s*$', line)
            if not m:
                continue
            d = int(m.group(1))
            v = [int(x) for x in re.findall(r'-?\d+', line[:m.start()])]
            if len(v) < P:
                continue
            out.append((v[:P], d))
    return out


def klass(p):
    r, c = divmod(p, N)
    return (r % S, c % S)


def apply(c, inv):
    return tuple(c[inv[j]] for j in range(len(c)))


def inv_of(g):
    inv = [0] * len(g)
    for i, p in enumerate(g):
        inv[p] = i
    return tuple(inv)


def cyc_of(g):
    seen = [False] * len(g)
    lens = []
    for i in range(len(g)):
        if seen[i]:
            continue
        ln, j = 0, i
        while not seen[j]:
            seen[j] = True
            j = g[j]
            ln += 1
        if ln > 1:
            lens.append(ln)
    return sorted(lens)


def main(path):
    gens = load(path)
    pts = {k: [p for p in range(P) if klass(p) == k]
           for k in sorted({klass(p) for p in range(P)})}

    for k in sorted(pts):
        pl = pts[k]
        idx = {p: i for i, p in enumerate(pl)}
        uniq = {}
        for v, d in gens:
            sup = [t for t in range(P) if v[t] != t]
            if len({klass(p) for p in sup}) != 1:
                continue
            if klass(sup[0]) != k:
                continue
            g = tuple(idx.get(v[p]) for p in pl)
            if any(x is None for x in g):
                continue
            if g not in uniq or d < uniq[g]:
                uniq[g] = d
        gens24 = [(inv_of(g), w, g) for g, w in uniq.items()]

        ident = tuple(range(K))
        best = {ident: 0}
        parent = {ident: None}
        pq = [(0, ident)]
        while pq:
            d, st = heapq.heappop(pq)
            if d > best.get(st, 1 << 30):
                continue
            for inv, w, g in gens24:
                ns = apply(st, inv)
                nd = d + w
                if nd < best.get(ns, 1 << 30):
                    best[ns] = nd
                    parent[ns] = (st, w, g)
                    heapq.heappush(pq, (nd, ns))

        mx = max(best.values())
        print(f'类{k} 位置{pl} 直径={mx}')
        for st, d in sorted(best.items(), key=lambda x: -x[1]):
            if d < mx:
                continue
            ct = cyc_of(st)
            path = []
            cur = st
            while parent.get(cur):
                prev, w, g = parent[cur]
                path.append((w, cyc_of(g)))
                cur = prev
            path.reverse()
            print(f'   dist={d} perm={st} 型={ct}')
            print(f'      组成: ' + ' + '.join(str(w) for w, _ in path))
        print()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else '_s2_d9_c4.log'))
