"""帶標籤 BFS + 路徑重建：列出某些置換的最短走法序列（用遊戲語言逐步打印）。

與 _chk_labels.py 同一套 BFS，只是多存父指針；座標同樣是具體座標，不做 D4。

用法：D:\\python\\python.exe _chk_labels_path.py <dump_dir> <s> <goal_id> [置換型 list]
      [置換型] 例：'[3,1]' 找三循環；省略則印最長的三個置換。
"""
import os
import sys
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import moves as mv

DIRS = {(0, 1): '右', (0, -1): '左', (1, 0): '下', (-1, 0): '上'}


def cells_of(bd, i, lim=16):
    return frozenset((r, c) for r in range(lim) for c in range(lim) if (int(bd[i][r]) >> c) & 1)


def norm(labeled):
    r0 = min(p[0] for p in labeled)
    c0 = min(p[1] for p in labeled)
    return frozenset((r - r0, c - c0, lab) for (r, c, lab) in labeled)


def key(state):
    return tuple(sorted(state))


def pic(state):
    S = {(r, c) for (r, c, _) in state}
    R = max(r for r, _ in S)
    C = max(c for _, c in S)
    return '/'.join(''.join('#' if (r, c) in S else '.' for c in range(C + 1)) for r in range(R + 1))


def bfs(start, s):
    k0 = key(norm(start))
    dist = {k0: 0}
    par = {k0: None}
    q = deque([norm(start)])
    while q:
        cur = q.popleft()
        d = dist[key(cur)]
        S = {(r, c) for (r, c, _) in cur}
        for seam, side, comp, unit in mv.legal_moves(S, s):
            if mv.apply_move(S, comp, unit, s) is None:
                continue
            nxt = set()
            for (r, c, lab) in cur:
                if (r, c) in comp:
                    nxt.add((r + unit[0] * s, c + unit[1] * s, lab))
                else:
                    nxt.add((r, c, lab))
            nxt = norm(nxt)
            k = key(nxt)
            if k not in dist:
                dist[k] = d + 1
                par[k] = (key(cur), (seam, side, len(comp), unit))
                q.append(nxt)
    return dist, par


def main(d, s, g, want=None):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    S = cells_of(bd, g)
    start = frozenset((r, c, (r, c)) for (r, c) in S)
    dist, par = bfs(start, s)
    tgt = frozenset(S)

    cands = []
    for k, dd in dist.items():
        if {(r, c) for (r, c, _) in k} != tgt or dd == 0:
            continue
        m = {lab: (r, c) for (r, c, lab) in k}
        seen = set()
        types = []
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
        cands.append((dd, tuple(sorted(types, reverse=True)), k, m))

    print('可達帶標籤狀態 %d；回到還原態的置換 %d 個' % (len(dist), len(cands)))
    sel = [c for c in cands if c[1] == tuple(want)] if want else sorted(cands, key=lambda x: -x[0])[:3]
    for dd, t, k, m in sel:
        print('\n=== 置換型 %s，最短 %d 步 ===' % (t, dd))
        print('標籤映射（原座標 → 現座標）:', {a: b for a, b in sorted(m.items())})
        path = []
        cur = k
        while par[cur] is not None:
            p, mvdesc = par[cur]
            path.append((p, mvdesc, cur))
            cur = p
        path.reverse()
        print('起點', pic(frozenset((r, c, (r, c)) for (r, c) in S)))
        for i, (_, (seam, side, ncomp, unit), st) in enumerate(path, 1):
            print(' %2d. %s %s側 %d格 往%s %d 格 → %s'
                  % (i, seam, side, ncomp, DIRS[unit], s, pic(st)))


if __name__ == '__main__':
    if len(sys.argv) < 4:
        sys.exit('用法: _chk_labels_path.py <dump_dir> <s> <goal_id> [置換型 list]')
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]),
         eval(sys.argv[4]) if len(sys.argv) > 4 else None)
