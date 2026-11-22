"""驗證 moves.py 的手寫移動生成器是否與引擎邊一致（用 D4 規範化後比對）。

引擎的狀態 = 整個 D4（8 個正交變換）軌道類的代表，所以必須把生成結果也做 D4 規範化
再比。用法：python _chk_moves.py <dump_dir> <s>

已驗：3_3_2 (s=2) 105/105 全中；4_3_3 (s=3) 1202/1202 全中。
"""
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import moves as mv


def canon(cs):
    """D4 規範化，回傳引擎用的類代表：8 個正交變換下 **memcmp 序（u16 小端逐位元組）** 最小者。

    注意：引擎 canon_from_rows 用 memcmp 比較 u16 陣列，那是「低位元組優先」的字典序，
    與數值序不同——2000 個 4×4 盤面裡有 6.0% 兩者選出不同代表（`_work/_repr_order.py` 已驗）。
    外部腳本必須用同一個序，否則 key 對不上，會誤判成「走法集合不相交」。
    """
    cs = set(cs)
    rmin = min(r for r, _ in cs); cmin = min(c for _, c in cs)
    cs = {(r - rmin, c - cmin) for r, c in cs}
    h = max(r for r, _ in cs) + 1
    w = max(c for _, c in cs) + 1
    best = None
    for flip in (False, True):
        for rot in range(4):
            t = set()
            for r, c in cs:
                cc = (w - 1 - c) if flip else c
                if rot == 0:
                    nr, nc = r, cc
                elif rot == 1:
                    nr, nc = cc, h - 1 - r
                elif rot == 2:
                    nr, nc = h - 1 - r, w - 1 - cc
                else:
                    nr, nc = w - 1 - cc, r
                t.add((nr, nc))
            tr = min(r for r, _ in t); tc = min(c for _, c in t)
            t = tuple(sorted((r - tr, c - tc) for r, c in t))
            rows = tuple(sum(1 << c for r2, c in t if r2 == r) for r in range(max(r2 for r2, _ in t) + 1))
            # memcmp 序 = 逐行的低 8 位、高 8 位
            key = tuple(v for x in rows for v in (x & 0xFF, x >> 8))
            if best is None or key < best[0]:
                best = (key, rows)
    return best[1]


def cells(bd, i, lim=16):
    return frozenset((r, c) for r in range(lim) for c in range(lim) if (int(bd[i][r]) >> c) & 1)


def main(d, s=2):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    mem = np.fromfile(os.path.join(d, 'membership.bin'), dtype=np.uint8).reshape(-1, 16)
    e = np.fromfile(os.path.join(d, 'edges.bin'), dtype='<u4').reshape(-1, 2)
    N = len(bd)
    od = mem[:, 6:8].copy().view('<u2').ravel().astype(int)

    ck2id = {}
    for i in range(N):
        ck2id.setdefault(canon(cells(bd, i)), i)

    src = e[:, 0].astype(int); dst = e[:, 1].astype(int)
    exact = 0
    partial = 0
    bad = []
    for i in range(N):
        S = cells(bd, i)
        gen = set()
        for seam, side, comp, unit in mv.legal_moves(S, s):
            n = mv.apply_move(S, comp, unit, s)
            if n is None:
                continue
            k = canon(n)
            j = ck2id.get(k)
            if j is None:
                gen.add(('MISS', k))
            else:
                gen.add(j)
        act = set(dst[src == i].tolist())
        if gen == act:
            exact += 1
        elif len(gen & act) >= min(len(gen), len(act)) and gen != act:
            partial += 1
            bad.append((i, len(gen), len(act), len(gen & act)))
        else:
            bad.append((i, len(gen), len(act), len(gen & act), len([x for x in gen if isinstance(x, tuple) and x[0] == 'MISS']) if any(isinstance(x, tuple) for x in gen) else 0))
    print(d)
    print('  狀態數', N, '  完全一致', exact, '  部分一致', partial, '  其他', N - exact - partial)
    print('  差異樣本（id, 生成數, 實際數, 交集, 生成卻不在A）:')
    for b in bad[:10]:
        print('   ', b)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.', int(sys.argv[2]) if len(sys.argv) > 2 else 2)
