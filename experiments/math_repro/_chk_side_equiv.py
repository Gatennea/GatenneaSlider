"""檢查「縫的兩側各推一次 → 同一（平移正規化後的）落點」是不是普遍現象。

對 dump 裡每個局面：算 (a) 合法走法條數 M，(b) 平移正規化後落點數 D，
(c) 每個落點被幾種說法命中。若普遍是「2 種說法」，那就是一條規則層的冗餘。

注意：兩種說法的**原始**落點差一個平移（推上側 3 格 vs 推下側 6 格往反方向），
所以要看正規化之後才會合併；原始層面 M＝D 是正常的。

用法：D:\\python\\python.exe _chk_side_equiv.py <dump_dir> <s>
"""
import os
import sys
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import moves as mv


def tnorm(S):
    r0 = min(r for r, _ in S)
    c0 = min(c for _, c in S)
    return frozenset((r - r0, c - c0) for (r, c) in S)


def main(d, s):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    ratio = Counter()
    hit = Counter()
    bad = []
    n = 0
    for i in range(len(bd)):
        S = frozenset((r, c) for r in range(16) for c in range(16) if (int(bd[i][r]) >> c) & 1)
        if not S:
            continue
        n += 1
        outs = {}
        M = 0
        for seam, side, comp, unit in mv.legal_moves(S, s):
            T = mv.apply_move(S, comp, unit, s)
            if T is None:
                continue
            M += 1
            outs.setdefault(tnorm(frozenset(T)), []).append((seam, side, unit))
        ratio[(M, len(outs))] += 1
        for k, v in outs.items():
            hit[len(v)] += 1
            if len(v) != 2 and len(bad) < 10:
                bad.append((i, M, len(outs), len(v)))
    print('局面數 %d' % n)
    print('（走法條數, 正規化後落點數）→ 局面數:', sorted(ratio.items()),
          '共 %d 種組合' % len(ratio))
    print('每個落點被幾種說法命中:', sorted(hit.items()))
    if bad:
        print('不是 2 的例子（前幾個）:', bad)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit('用法: _chk_side_equiv.py <dump_dir> <s>')
    main(sys.argv[1], int(sys.argv[2]))
