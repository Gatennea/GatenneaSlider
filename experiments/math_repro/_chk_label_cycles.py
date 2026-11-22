"""置換的「循環結構」檢查（配合 _chk_labels.py）：
  1) 還原態的著色類（r%s, c%s）各有幾格；
  2) 只動 k 格、其餘原位的那類循環該怎麼數——這裡專門查「純三循環」；
     順便驗證它是否恰好等於「某著色類裡任取 3 格 × 2 方向」的全體；
  3) 每個純三循環的最短步數與**最短走法條數**（層序 DP 計數）。

注意：三循環的最短步數**不是**普適常數。(3,3,2) 全部 7 步；
(3,2,1) 是 6／8／10／12 步混排（見 01 §5.1），寫文檔時別當定理。

用法：D:\\python\\python.exe _chk_label_cycles.py <dump_dir> <s> <goal_id>
"""
import os
import sys
from collections import defaultdict, deque
from itertools import combinations

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import moves as mv


def cells_of(bd, i, lim=16):
    return frozenset((r, c) for r in range(lim) for c in range(lim) if (int(bd[i][r]) >> c) & 1)


def norm(labeled):
    r0 = min(p[0] for p in labeled)
    c0 = min(p[1] for p in labeled)
    return frozenset((r - r0, c - c0, lab) for (r, c, lab) in labeled)


def key(state):
    return tuple(sorted(state))


def nbrs(cur, s):
    S = {(r, c) for (r, c, _) in cur}
    out = []
    for seam, side, comp, unit in mv.legal_moves(S, s):
        if mv.apply_move(S, comp, unit, s) is None:
            continue
        nxt = set()
        for (r, c, lab) in cur:
            if (r, c) in comp:
                nxt.add((r + unit[0] * s, c + unit[1] * s, lab))
            else:
                nxt.add((r, c, lab))
        out.append(norm(nxt))
    return out


def bfs_full(start, s):
    """回傳 dist 與 ways（ways = 到該狀態的最短走法條數）。"""
    k0 = key(norm(start))
    dist = {k0: 0}
    ways = {k0: 1}
    q = deque([norm(start)])
    while q:
        cur = q.popleft()
        kc = key(cur)
        d = dist[kc]
        for nxt in nbrs(cur, s):
            k = key(nxt)
            if k not in dist:
                dist[k] = d + 1
                ways[k] = ways[kc]
                q.append(nxt)
            elif dist[k] == d + 1:
                ways[k] += ways[kc]
    return dist, ways


def cycles_of(m):
    """把映射 m: 舊座標 -> 新座標 拆成循環 list。"""
    seen = set()
    out = []
    for lab in m:
        if lab in seen:
            continue
        cyc = []
        cur = lab
        while True:
            seen.add(cur)
            cyc.append(cur)
            cur = m[cur]
            if cur == lab:
                break
        out.append(cyc)
    return out


def main(d, s, g):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    S = cells_of(bd, g)

    classes = defaultdict(list)
    for (r, c) in sorted(S):
        classes[(r % s, c % s)].append((r, c))
    print('著色類（r%%%d, c%%%d）→ 格數：' % (s, s))
    for k, v in sorted(classes.items()):
        print('   %s : %d 格  %s' % (k, len(v), v))

    cand = set()
    for k, v in classes.items():
        if len(v) < 3:
            continue
        for tri in combinations(v, 3):
            cand.add(tuple(sorted(tri)))
    print('\n著色類內可組出的三格支撐集: %d 個' % len(cand))

    start = frozenset((r, c, (r, c)) for (r, c) in S)
    dist, ways = bfs_full(start, s)
    print('可達帶標籤狀態 %d' % len(dist))

    pure3 = []
    for k, dd in dist.items():
        if {(r, c) for (r, c, _) in k} != S:
            continue
        m = {lab: (r, c) for (r, c, lab) in k}
        cyc = cycles_of(m)
        if len(cyc) != len(S) - 2:          # 只有一個 3-循環，其餘全固定
            continue
        three = [c for c in cyc if len(c) == 3]
        if len(three) != 1:
            continue
        pure3.append((dd, three[0], ways[k], m))

    print('\n純三循環: %d 個' % len(pure3))
    sup = {tuple(sorted(c)) for _, c, _, _ in pure3}
    print('其中三格支撐集: %d 種；與「同色任取 3 格」集合相同: %s' % (len(sup), sup == cand))
    if sup != cand:
        print('   同色集合:', sorted(cand))

    from collections import Counter
    print('最短步數分佈:', sorted(Counter(dd for dd, _, _, _ in pure3).items()))

    for dd, cyc, w, m in sorted(pure3, key=lambda x: x[0]):
        a, b, c3 = cyc
        print('   %d 步 · 最短走法 %d 條 · %s → %s → %s → %s' % (dd, w, a, b, c3, a))


if __name__ == '__main__':
    if len(sys.argv) < 4:
        sys.exit('用法: _chk_label_cycles.py <dump_dir> <s> <goal_id>')
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
