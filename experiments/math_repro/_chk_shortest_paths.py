"""枚舉某個置換的**所有最短走法**，看它們是同一條「圈」的不同說法，還是不同的圈。

做法：先從起點 BFS 得距離，再自目標沿**反向邊**、距離 −1 標出「最短路子圖」，
只在子圖上 DFS——注意圖是**有向**的（有些滑動回不去），不能拿出邊當前驅；
不剪枝直接 DFS 會走進整張圖的死枝而爆炸（74k 狀態時幾分鐘都跑不完）。
最後把每條路徑的棋形序列做循環正規化，數有幾條不同的「圈」，
並逐層統計「幾種說法 → 幾個落點」（同一落點可由縫的兩側各推一次得到）。

結果（(3,3,2)，`01` §5.1）：7 步三循環 64 條最短路＝**1 條圈 × 2⁶ 種說法**；
6 步元素（4,2,1,1,1）256 條＝**4 條圈 × 2⁶**。

用法：D:\\python\\python.exe _chk_shortest_paths.py <dump_dir> <s> <goal_id> <置換型 list>
      例：'[3,1,1,1,1,1,1]' 找三循環
"""
import os
import sys
from collections import Counter, deque

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


def nbrs(cur, s):
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
        yield norm(nxt), (seam, side, len(comp), unit)


def bfs(start, s):
    dist = {key(norm(start)): 0}
    q = deque([norm(start)])
    while q:
        cur = q.popleft()
        d = dist[key(cur)]
        for nxt, _ in nbrs(cur, s):
            k = key(nxt)
            if k not in dist:
                dist[k] = d + 1
                q.append(nxt)
    return dist


def main(d, s, g, want):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    S = cells_of(bd, g)
    start = frozenset((r, c, (r, c)) for (r, c) in S)
    dist = bfs(start, s)

    # 找目標：型別符合且距離最短的那個
    best = None
    for k, dd in dist.items():
        if {(r, c) for (r, c, _) in k} != S:
            continue
        m = {lab: (r, c) for (r, c, lab) in k}
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
        t = tuple(sorted(types, reverse=True))
        if t == tuple(want) and dd > 0 and (best is None or dd < best[0]):
            best = (dd, k)
    if best is None:
        sys.exit('沒找到型別 %s 的置換' % (want,))
    D, tgt_key = best
    print('型別 %s 最短 %d 步' % (want, D))

    # 只走「在最短路上」的點：先由目標沿反向邊、距離 −1 標出 onpath 集合
    # （圖是有向的，必須自己建反向邊；直接 DFS 會走進大量死枝而爆炸）
    rev = {}
    states = {key(start): start}
    seen = {key(start)}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt, _ in nbrs(cur, s):
            k = key(nxt)
            rev.setdefault(k, []).append(key(cur))
            if k not in seen:
                seen.add(k)
                dist[k] = dist[key(cur)] + 1
                states[k] = nxt
                q.append(nxt)

    onpath = {tgt_key}
    q2 = deque([tgt_key])
    while q2:
        k = q2.popleft()
        for p in rev.get(k, ()):
            if p not in onpath and dist[p] == dist[k] - 1:
                onpath.add(p)
                q2.append(p)

    paths = []

    def rec(cur, acc):
        k = key(cur)
        if k == tgt_key:
            paths.append(list(acc))
            return
        for nxt, desc in nbrs(cur, s):
            kk = key(nxt)
            if kk in onpath and dist[kk] == dist[k] + 1:
                rec(nxt, acc + [(desc, nxt)])

    rec(start, [])
    tgt = states[tgt_key]
    print('最短走法條數 %d（在最短路上的狀態 %d 個）' % (len(paths), len(onpath)))

    # 每條路徑的棋形序列（含起點與每步落點）做循環正規化
    shapes = []
    for p in paths:
        seq = [pic(start)] + [pic(np_set) for (_, np_set) in p]
        seq = seq[:-1]  # 最後一步回到起點，去掉重複
        rots = [tuple(seq[i:] + seq[:i]) for i in range(len(seq))]
        shapes.append(min(rots))
    uniq = Counter(shapes)
    print('不同「圈」（棋形序列循環正規化後）: %d 條' % len(uniq))
    for cyc, cnt in uniq.most_common():
        print('   %2d 條最短路共用此圈：' % cnt)
        for sh in cyc:
            print('        ', sh)

    # 每層有幾個「說法」（(前驅態, 動作描述) 對）與幾個狀態
    L = len(paths[0]) if paths else 0
    for i in range(1, L + 1):
        pairs = {(key(p[i - 1][1]) if i > 1 else key(start), p[i - 1][0]) for p in paths}
        sts = {key(p[i - 1][1]) for p in paths}
        print('  第 %d 步：%d 種說法 → %d 個落點' % (i, len(pairs), len(sts)))

    # 首步分佈
    f = Counter(DIRS[p[0][0][3]] + str(p[0][0][2]) + '格' + p[0][0][0] + p[0][0][1] + '側'
                for p in paths)
    print('首步分佈:', sorted(f.items()))


if __name__ == '__main__':
    if len(sys.argv) < 5:
        sys.exit('用法: _chk_shortest_paths.py <dump_dir> <s> <goal_id> <型別 list>')
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), eval(sys.argv[4]))
