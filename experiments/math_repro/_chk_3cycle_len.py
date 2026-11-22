"""純三循環的「支撐集 → 最短步數」對照：找步數與幾何（跨度）之間的關係。

用法：D:\\python\\python.exe _chk_3cycle_len.py <dump_dir> <s> <goal_id>
"""
import os
import sys
from collections import defaultdict, deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import moves as mv


def cells_of(bd, i, lim=16):
    return frozenset((r, c) for r in range(lim) for c in range(lim) if (int(bd[i][r]) >> c) & 1)


def norm_lab(lab):
    r0 = min(p[0] for p in lab)
    c0 = min(p[1] for p in lab)
    return frozenset((r - r0, c - c0, l) for (r, c, l) in lab)


def key(lab):
    return tuple(sorted(lab))


def cycles_of(m):
    seen, out = set(), []
    for lab in m:
        if lab in seen:
            continue
        cyc, cur = [], lab
        while True:
            seen.add(cur)
            cyc.append(cur)
            cur = m[cur]
            if cur == lab:
                break
        out.append(cyc)
    return out


def nbrs(lab, s):
    S = {(r, c) for (r, c, _) in lab}
    for seam, side, comp, unit in mv.legal_moves(S, s):
        if mv.apply_move(S, comp, unit, s) is None:
            continue
        nxt = set()
        for (r, c, l) in lab:
            if (r, c) in comp:
                nxt.add((r + unit[0] * s, c + unit[1] * s, l))
            else:
                nxt.add((r, c, l))
        yield frozenset(nxt)


def main(d, s, g):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    S = cells_of(bd, g)
    start = frozenset((r, c, (r, c)) for (r, c) in S)
    dist, state = {key(norm_lab(start)): 0}, {key(norm_lab(start)): start}
    q = deque([start])
    while q:
        cur = q.popleft()
        kc = key(norm_lab(cur))
        for nxt in nbrs(cur, s):
            k = key(norm_lab(nxt))
            if k not in dist:
                dist[k] = dist[kc] + 1
                state[k] = nxt
                q.append(nxt)
    print('可達 %d' % len(dist))

    best = defaultdict(list)
    for k, lab in state.items():
        if {(r, c) for (r, c, _) in norm_lab(lab)} != S:
            continue
        m = {l: (r, c) for (r, c, l) in norm_lab(lab)}
        cyc = cycles_of(m)
        if len(cyc) != len(S) - 2 or set(map(len, cyc)) != {1, 3}:
            continue
        three = [c for c in cyc if len(c) == 3][0]
        sup = tuple(sorted(three))
        best[sup].append(dist[k])

    print('\n支援集 → （最少步數, 方向數, 跨度）:')
    for sup, ds in sorted(best.items(), key=lambda x: (min(x[1]), x[0])):
        rs = [p[0] for p in sup]
        cs = [p[1] for p in sup]
        span = (max(rs) - min(rs), max(cs) - min(cs))
        print('%-30s %s' % (str(list(sup)), (min(ds), len(ds), span)))


if __name__ == '__main__':
    if len(sys.argv) < 4:
        sys.exit('用法: _chk_3cycle_len.py <dump_dir> <s> <goal_id>')
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
