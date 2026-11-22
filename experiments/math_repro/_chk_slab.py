"""「窄邊」解釋的量化：當寬或高 ≤ s 時，那個方向的合法推是不是都只是整體平移？

對每個局面、每條合法走法，算正規化後的落點形狀：
  - 與原形狀相同 → 純平移（形狀不變，置換不變）
  - 不同 → 真的換形狀
再按方向（水平推 / 垂直推）分開統計。

用法：D:\\python\\python.exe _chk_slab.py <dump_dir> <s> [m] [n]
"""
import os
import sys
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import moves as mv


def main(d, s, m=None, n=None):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    stat = Counter()
    for i in range(len(bd)):
        S = frozenset((r, c) for r in range(16) for c in range(16) if (int(bd[i][r]) >> c) & 1)
        if not S:
            continue
        shape0 = mv.normalize(S)
        for seam, side, comp, unit in mv.legal_moves(S, s):
            T = mv.apply_move(S, comp, unit, s)
            if T is None:
                continue
            horiz = unit[1] != 0
            same = mv.normalize(T) == shape0
            stat[('水平' if horiz else '垂直', '純平移' if same else '換形狀')] += 1
    print('尺寸 %s（s=%s）走法分類:' % (os.path.basename(d.rstrip('\\/')), s))
    for k in sorted(stat):
        print('   %s推 · %s : %d' % (k[0], k[1], stat[k]))
    h = stat[('水平', '純平移')], stat[('水平', '換形狀')]
    v = stat[('垂直', '純平移')], stat[('垂直', '換形狀')]
    print('   水平：純平移 %d / 換形狀 %d；垂直：純平移 %d / 換形狀 %d' % (h + v))


if __name__ == '__main__':
    a = sys.argv
    main(a[1], int(a[2]), int(a[3]) if len(a) > 3 else None, int(a[4]) if len(a) > 4 else None)
