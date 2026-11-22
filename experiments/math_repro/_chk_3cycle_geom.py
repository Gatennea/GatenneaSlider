"""八個純三循環的幾何結構：支撐集、缺的那一角、輪換方向（有號面積）。

目的：驗證「8 = 4 個缺角 × 2 個方向」這條組合描述（不是 D4 軌道——D4 共軛會把
置換型改掉，見 _chk_d4_word.py）。

用法：D:\\python\\python.exe _chk_3cycle_geom.py <dump_dir> <s> <goal_id>
"""
import os
import sys
from collections import deque

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


def cycle_type(m):
    seen, types = set(), []
    for lab in m:
        if lab in seen:
            continue
        cur, n = lab, 0
        while True:
            seen.add(cur)
            cur = m[cur]
            n += 1
            if cur == lab:
                break
        types.append(n)
    return tuple(sorted(types, reverse=True))


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


def bfs(start, s):
    k0 = key(norm_lab(start))
    dist = {k0: 0}
    state = {k0: start}
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
    return dist, state


def main(d, s, g):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    S = cells_of(bd, g)
    start = frozenset((r, c, (r, c)) for (r, c) in S)
    dist, state = bfs(start, s)

    from collections import defaultdict
    classes = defaultdict(list)
    for (r, c) in sorted(S):
        classes[(r % s, c % s)].append((r, c))
    big = max(classes.values(), key=len)
    print('著色類:', {k: len(v) for k, v in classes.items()})

    def sign(cyc):
        """有號面積：+1 逆時針、−1 順時針（在 (r,c) 平面上）"""
        a, b, c = cyc
        s1 = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if s1 == 0 else (1 if s1 > 0 else -1)

    print('\n%d 個純三循環：' % 8)
    print('%-28s %-10s %-6s %s' % ('支撐集', '缺角', '方向', '步數'))
    rows = []
    for k, lab in state.items():
        if {(r, c) for (r, c, _) in norm_lab(lab)} != S:
            continue
        m = {l: (r, c) for (r, c, l) in norm_lab(lab)}
        cyc = cycles_of(m)
        if len(cyc) != len(S) - 2 or set(map(len, cyc)) != {1, 3}:
            continue
        three = [c for c in cyc if len(c) == 3][0]
        sup = set(three)
        miss = [p for p in big if p not in sup]
        rows.append((tuple(sorted(sup)), miss[0] if len(miss) == 1 else None,
                     sign(three), dist[k]))
    for sup, miss, sg, dd in sorted(rows):
        print('%-28s %-10s %-6s %d' % (str(list(sup)), str(miss),
                                       '逆時針' if sg > 0 else '順時針' if sg < 0 else '共線', dd))
    print('\n缺角×方向 組合數: %d（支撐 %d 種、方向 %d 種）'
          % (len({(r[1], r[2]) for r in rows}), len({r[0] for r in rows}), len({r[2] for r in rows})))


if __name__ == '__main__':
    if len(sys.argv) < 4:
        sys.exit('用法: _chk_3cycle_geom.py <dump_dir> <s> <goal_id>')
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
