"""抽樣驗證：4×4 兩個尺寸的生成器 vs 引擎邊，並量「一條類轉移平均代表幾條字面滑動」。

已驗：4_4_2 (s=2) 抽 2,000 態 2,000/2,000、4_4_3 (s=3) 抽 2,000 態 2,000/2,000（2026-11-24）。
同時輸出「一條類轉移平均代表幾條字面滑動」，給 01 §3.6 的模型限制當依據。

不用建 canon->id 全表：引擎邊的目標 id 對應的 board 本身就是 D4 類代表，直接取其行列
位圖當 key；生成結果做 canon 後比對 key 集合即可。
用法：python _sample_moves.py <dump_dir> <s> <n_sample> [seed]
"""
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moves as mv
from _chk_moves import canon


def cells(bd, i, lim=16):
    return frozenset((r, c) for r in range(lim) for c in range(lim) if (int(bd[i][r]) >> c) & 1)


def key_of(bd, i, lim=16):
    rows = []
    for r in range(lim):
        v = int(bd[i][r])
        if not v:
            break
        rows.append(v)
    return tuple(rows)


def main(d, s, n, seed=12345):
    bd = np.fromfile(os.path.join(d, 'boards.bin'), dtype='<u2').reshape(-1, 16)
    mem = np.fromfile(os.path.join(d, 'membership.bin'), dtype=np.uint8).reshape(-1, 16)
    e = np.fromfile(os.path.join(d, 'edges.bin'), dtype='<u4').reshape(-1, 2)
    N = len(bd)
    src = e[:, 0].astype(int); dst = e[:, 1].astype(int)
    rng = np.random.default_rng(seed)
    picks = rng.choice(N, size=min(n, N), replace=False)

    exact = 0
    miss = []
    lit_tot = 0
    cls_tot = 0
    worst = []
    for i in picks:
        i = int(i)
        S = cells(bd, i)
        lit = 0
        gen = set()
        for seam, side, comp, unit in mv.legal_moves(S, s):
            nxt = mv.apply_move(S, comp, unit, s)
            if nxt is None:
                continue
            lit += 1
            gen.add(canon(nxt))
        act = {key_of(bd, int(t)) for t in dst[src == i]}
        lit_tot += lit
        cls_tot += len(gen)
        if gen == act:
            exact += 1
        else:
            miss.append((i, len(gen), len(act), len(gen & act), lit))
        if len(gen) and lit / len(gen) >= 6:
            worst.append((i, lit, len(gen)))

    print('%s  (s=%d, 抽 %d 態)' % (d, s, len(picks)))
    print('  完全一致 %d / %d' % (exact, len(picks)))
    for m in miss[:8]:
        print('   差異:', m)
    print('  字面滑動總數 %d，類後繼總數 %d，平均一條類轉移代表 %.2f 條字面滑動'
          % (lit_tot, cls_tot, (lit_tot / cls_tot) if cls_tot else 0))
    print('  一條邊代表 ≥6 條滑動的狀態數:', len(worst),
          '（最多 %d 條）' % (max([w[1] for w in worst], default=0)))


if __name__ == '__main__':
    d = sys.argv[1]
    s = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 500
    main(d, s, n)
