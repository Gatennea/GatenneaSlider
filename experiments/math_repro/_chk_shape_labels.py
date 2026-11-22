"""非實心塊的穩定子：測試「滿／平凡」二分律是不是只在實心矩形成立。

形狀由內建表給定：
  corner8 ：3×3 缺一角 (2,2)   K=8
  ring8   ：3×3 缺中心 (1,1)   K=8
  corner11：4×3 缺一角 (3,2)  K=11
  twin    ：3×2 兩塊？(預留)

用法：D:\\python\\python.exe _chk_shape_labels.py <形狀名> <s>
"""
import os
import sys
from collections import Counter, deque
from math import factorial, prod

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import moves as mv

SHAPES = {
    'corner8': [(r, c) for r in range(3) for c in range(3) if (r, c) != (2, 2)],
    'ring8': [(r, c) for r in range(3) for c in range(3) if (r, c) != (1, 1)],
    'corner11': [(r, c) for r in range(4) for c in range(3) if (r, c) != (3, 2)],
    'line5': [(0, c) for c in range(5)],
    'line7': [(0, c) for c in range(7)],
    'plus5': [(1, 1)] + [(r, 1) for r in (0, 2)] + [(1, c) for c in (0, 2)],
    'slab23': [(r, c) for r in range(2) for c in range(3)],
    'slab24': [(r, c) for r in range(2) for c in range(4)],
    'L5': [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2)],
    'T6': [(0, 0), (0, 1), (0, 2), (1, 1), (2, 1), (2, 2)],
}


def norm_lab(lab):
    r0 = min(p[0] for p in lab)
    c0 = min(p[1] for p in lab)
    return frozenset((r - r0, c - c0, l) for (r, c, l) in lab)


def key(lab):
    return tuple(sorted(lab))


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


def main(name, s):
    P = SHAPES[name]
    S = frozenset(P)
    # 標籤用整數 id（第 i 格），只正規化格子座標——用座標當標籤會被「整體平移」騙出假狀態
    order = sorted(mv.normalize(S))
    base = frozenset(order)
    start = frozenset((r, c, i) for i, (r, c) in enumerate(order))
    dist = {key(norm_lab(start)): 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        kc = key(norm_lab(cur))
        for nxt in nbrs(cur, s):
            k = key(norm_lab(nxt))
            if k not in dist:
                dist[k] = dist[kc] + 1
                q.append(nxt)

    # 著色類與上界
    from collections import defaultdict
    classes = defaultdict(int)
    for (r, c) in S:
        classes[(r % s, c % s)] += 1
    bound = prod(factorial(v) for v in classes.values())

    # 回到本形狀的置換
    perms = []
    for k, dd in dist.items():
        if {(r, c) for (r, c, _) in k} != base:
            continue
        perms.append(dd)
    print('%s（s=%d，K=%d）' % (name, s, len(S)))
    print('  著色類大小: %s' % sorted(classes.values(), reverse=True))
    print('  上界 Π(類階乘): %d' % bound)
    shapes = {frozenset((r, c) for (r, c, _) in k) for k in dist}
    print('  可達帶標籤狀態: %d' % len(dist))
    print('  可達棋形（丟標籤）: %d → 每形平均標籤數 %.4f'
          % (len(shapes), len(dist) / len(shapes)))
    print('  回到本形狀的置換: %d  最短/最長: %s/%s'
          % (len(perms), min(perms) if perms else '-', max(perms) if perms else '-'))
    print('  判定: %s' % ('滿' if len(perms) == bound else ('平凡' if len(perms) == 1 else '中間值！')))


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
