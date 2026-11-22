"""帶標籤走法搜尋（O-4 的前置工具）：在「形狀 + 每格標籤」上做 BFS，求

  1) 還原態穩定子——走一圈又回到原樣（同形狀同位置集）時，標籤被置換成什麼；
     與引擎 R6 的群階交叉驗證（R6 是「走動能實現的置換」，不必回到原樣，語義不同，見 00 §2）；
  2) 每個置換的**最短走法長度**（O-4 的「最小循環長度」）。

座標一律用具體座標（只做平移正規化，**不做 D4**——旋轉／鏡射不是合法動作，
D4 只是引擎壓縮狀態用的類代表約定；做 D4 會把標籤打亂，群階就算錯）。

用法：D:\\python\\python.exe _chk_labels.py <dump_dir> <s> <goal_id>
      （goal_id 用 _work/_find_goal.py 查；不可省，曾因切片不連續誤取到凍結態）
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


def norm(labeled):
    r0 = min(p[0] for p in labeled)
    c0 = min(p[1] for p in labeled)
    return frozenset((r - r0, c - c0, lab) for (r, c, lab) in labeled)


def key(state):
    return tuple(sorted(state))


def bfs(start, s, limit=None):
    """start: frozenset((r,c,label))。回傳 {key: 距離}。"""
    dist = {key(norm(start)): 0}
    q = deque([norm(start)])
    while q:
        cur = q.popleft()
        d = dist[key(cur)]
        if limit is not None and d >= limit:
            continue
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
    S = cells_of(bd, g)
    print('還原態 id %d，%d 格，形狀：' % (g, len(S)))
    R = max(r for r, _ in S)
    C = max(c for _, c in S)
    for r in range(R + 1):
        print('   ', ''.join('#' if (r, c) in S else '.' for c in range(C + 1)))

    start = frozenset((r, c, (r, c)) for (r, c) in S)   # 標籤 = 起始座標
    dist = bfs(start, s)
    print('\n可達帶標籤狀態（平移正規化後）: %d' % len(dist))
    shapes = {frozenset((r, c) for (r, c, _) in k) for k in dist}
    print('可達棋形（丟標籤）: %d → 每形平均標籤數 %.6f'
          % (len(shapes), len(dist) / len(shapes)))

    perms = []
    for k, dd in dist.items():
        if {(r, c) for (r, c, _) in k} != frozenset(S):
            continue
        mapping = {lab: (r, c) for (r, c, lab) in k}
        if len(mapping) == len(S):
            perms.append((dd, tuple(sorted(mapping.items()))))
    print('回到還原態（同形狀）的標籤分佈: %d 個' % len(perms))
    if not perms:
        return
    ds = sorted(dd for dd, _ in perms)
    print('最短距離分佈: 最小 %d、中位 %d、平均 %.2f、最大 %d'
          % (ds[0], ds[len(ds) // 2], sum(ds) / len(ds), ds[-1]))
    print('距離直方圖:', sorted(Counter(ds).items()))

    by_type = {}
    for dd, m in perms:
        by_type.setdefault(cycle_type(dict(m)), []).append(dd)
    print('\n置換型 → (個數, 最短, 最長):')
    for t, v in sorted(by_type.items(), key=lambda x: (-len(x[0]), x[0])):
        print('   %-18s n=%-4d min=%-3d max=%-3d' % (str(t), len(v), min(v), max(v)))


if __name__ == '__main__':
    if len(sys.argv) < 4:
        sys.exit('用法: _chk_labels.py <dump_dir> <s> <goal_id>')
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
