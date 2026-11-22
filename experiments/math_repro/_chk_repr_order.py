"""確認引擎的類代表序：memcmp（u16 小端逐位元組）最小 vs 數值最小。"""
import sys, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from _chk_moves import canon


def boardkey(bd, i, lim=16):
    rows = []
    for r in range(lim):
        v = int(bd[i][r])
        if not v:
            break
        rows.append(v)
    return tuple(rows)


def canon_memcmp(rows):
    """模擬 repro_fast 的 canon_from_rows：對 8 個正交變換取 memcmp 序最小。"""
    cells = [(r, c) for r, v in enumerate(rows) for c in range(16) if (v >> c) & 1]
    h = max(r for r, _ in cells) + 1
    w = max(c for _, c in cells) + 1
    best = None
    for flip in (0, 1):
        for rot in range(4):
            t = [0] * 16
            for r, c in cells:
                c2 = (w - 1 - c) if flip else c
                if rot == 0:
                    nr, nc = r, c2
                elif rot == 1:
                    nr, nc = c2, h - 1 - r
                elif rot == 2:
                    nr, nc = h - 1 - r, w - 1 - c2
                else:
                    nr, nc = w - 1 - c2, r
                t[nr] |= (1 << nc)
            while t and t[-1] == 0:
                t.pop()
            kb = tuple(v for x in t for v in (x & 0xFF, x >> 8))   # memcmp 序
            if best is None or kb < best[0]:
                best = (kb, tuple(t))
    return best[1]


def main(d, n=2000, seed=7):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    rng = np.random.default_rng(seed)
    bad_mem = bad_num = 0
    diff = 0
    for i in rng.choice(len(bd), n, replace=False):
        k = boardkey(bd, int(i))
        if canon_memcmp(k) != k:
            bad_mem += 1
        if canon(frozenset((r, c) for r, v in enumerate(k) for c in range(16) if (v >> c) & 1)) != k:
            bad_num += 1
        if canon_memcmp(k) != canon(frozenset((r, c) for r, v in enumerate(k) for c in range(16) if (v >> c) & 1)):
            diff += 1
    print('%s  n=%d' % (d, n))
    print('  引擎 memcmp 序不自洽（不是自身代表）: %d' % bad_mem)
    print('  數值序不自洽（我的 canon）: %d' % bad_num)
    print('  兩種代表序選出不同代表: %d  （%.1f%%）' % (diff, 100.0 * diff / n))


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2000)
