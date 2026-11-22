"""帶標籤走法（正規版，2026-11-24 修正版）：標籤用整數 id，不用座標。

舊版 `_chk_labels.py` 用「標籤 = 起始座標」並只做**格子**的平移正規化，結果是：
整體平移一格（例如棋形的 min 座標奇偶換了）會被當成另一個局面，於是同一個物理
局面被重複計 4 次（殘餘 (0,0)/(1,0)/(0,1)/(1,1) 各一份）。表現在數字上就是
G 可能超過上界（例：`###./####/.#..` 上界 16 卻算出 32）。本檔改用 id 標籤，
只正規化格子座標，物理上等價的局面就真的合併了。

用法：D:\\python\\python.exe _chk_labels2.py <dump_dir> <s> <goal_id>
"""
import os
import sys
from collections import Counter, deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import moves as mv


def cells_of(bd, i, lim=16):
    return frozenset((r, c) for r in range(lim) for c in range(lim) if (int(bd[i][r]) >> c) & 1)


def norm(lab):
    """lab: frozenset[(r,c,id)] → 按最小座標平移，id 不動"""
    r0 = min(p[0] for p in lab)
    c0 = min(p[1] for p in lab)
    return tuple(sorted((r - r0, c - c0, i) for (r, c, i) in lab))


def bfs(start, s):
    dist = {norm(start): 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        kc = norm(cur)
        d = dist[kc]
        S = {(r, c) for (r, c, _) in cur}
        for seam, side, comp, unit in mv.legal_moves(S, s):
            if mv.apply_move(S, comp, unit, s) is None:
                continue
            nxt = frozenset((r + unit[0] * s, c + unit[1] * s, i) if (r, c) in comp else (r, c, i)
                            for (r, c, i) in cur)
            k = norm(nxt)
            if k not in dist:
                dist[k] = d + 1
                q.append(nxt)
    return dist


def cycle_type(m):
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
    return tuple(sorted(types, reverse=True))


def main(d, s, g):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    S = sorted(cells_of(bd, g))
    base = mv.normalize(frozenset(S))
    order = sorted(base)
    start = frozenset((r, c, i) for i, (r, c) in enumerate(order))
    print('還原態 id %d，%d 格' % (g, len(S)))
    off = (min(a for a, _ in S), min(b for _, b in S))
    cells0 = {(r - off[0], c - off[1]) for (r, c) in S}
    R = max(r for r, _ in cells0)
    C = max(c for _, c in cells0)
    for r in range(R + 1):
        print('   ', ''.join('#' if (r, c) in cells0 else '.' for c in range(C + 1)))

    dist = bfs(start, s)
    shapes = {frozenset((r, c) for (r, c, _) in k) for k in dist}
    print('\n可達帶標籤狀態: %d' % len(dist))
    print('可達棋形（丟標籤）: %d → 每形平均標籤數 %.6f' % (len(shapes), len(dist) / len(shapes)))

    perms = []
    for k, dd in dist.items():
        if {(r, c) for (r, c, _) in k} != base:
            continue
        mapping = {i: (r, c) for (r, c, i) in k}
        if len(mapping) == len(start):
            # 把「id→落點」翻成「起始格→落點」，才能談循環型
            perms.append((dd, tuple(sorted((order[i], cell) for i, cell in mapping.items()))))
    print('回到還原態（同形狀）的標籤分佈: %d 個' % len(perms))
    if not perms:
        return
    ds = sorted(dd for dd, _ in perms)
    print('最短距離分佈: 最小 %d、中位 %d、平均 %.2f、最大 %d' % (ds[0], ds[len(ds) // 2], sum(ds) / len(ds), ds[-1]))
    print('距離直方圖:', sorted(Counter(ds).items()))
    by_type = {}
    for dd, m in perms:
        by_type.setdefault(cycle_type(dict(m)), []).append(dd)
    print('\n置換型 → (個數, 最短, 最長):')
    for t, v in sorted(by_type.items(), key=lambda x: (-len(x[0]), x[0])):
        print('   %-22s n=%-4d min=%-3d max=%-3d' % (str(t), len(v), min(v), max(v)))


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
