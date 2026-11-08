# -*- coding: utf-8 -*-
"""階段三：解長 cap 在**當前 alt 流水線**的重驗（聚攏段投入 vs 時間/解長）。

背景：
· 舊驗收（docs/archive/混合求解器验收.md §三）在 legacy 流水線實測：砍掉段1
  聚攏（cap=0）解長中位 103→19（4×4）、311→61（5×5），成功率不變，代價耗時
  +27~60%——「聚攏段在搜索兜底下把解帶偏」。
· 但 2026-10-17 實測「砍聚攏換搜索 = 時間 +70%」，exp20 又把多段聚攏加回
  （alt 流水線快 4.5×）——兩代流水線結論相反，**必須在當前代碼上重測**。
· 當前旋鈕映射：legacy 的 cap（段1 步數上限）≈ alt 的 `alt_max_rounds`
  （0 = 完全跳過聚攏直進 GBFS；8 = 現默認）。

輸出（落盤 _cap_reverify_alt_out.txt + stdout）：每個 variant 一組
（成功數/總數、耗時中位、步數中位）→ 時間 vs 解長的權衡曲線，供用戶拍板。

用法（必須固定 hash 種子消方差，與驗收同理）：
    $env:PYTHONHASHSEED='0'
    python experiments/_cap_reverify_alt.py --variants 0,1,2,8 --seeds 1000,1001,1002,1003,1004 --size 5 --cap 150
    python experiments/_cap_reverify_alt.py --variants 0,8 --seeds 2,9 --size 6 --cap 150
（6×6 單局 ~100s+，分開跑避免超過後台時長上限；--cap 單局牆鐘熔斷秒數）
"""
import argparse
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game import SliderMatrix                       # noqa: E402
from solver.ml.fill_macro import build_game         # noqa: E402
from solver.hybrid_solver import hybrid_solve       # noqa: E402

OUT = os.path.join(ROOT, 'experiments', '_cap_reverify_alt_out.txt')


def make_coords(size, seed):
    random.seed(seed)
    g = SliderMatrix(size, size)
    g.shuffle(attempts=140, step=2)
    return frozenset(tuple(b.location) for b in g.blocks)


def median(xs):
    return statistics.median(xs) if xs else float('nan')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variants', default='0,1,2,8')
    ap.add_argument('--seeds', default='1000,1001,1002,1003,1004')
    ap.add_argument('--size', type=int, default=5)
    ap.add_argument('--cap', type=float, default=150.0)
    args = ap.parse_args()
    variants = [int(v) for v in args.variants.split(',')]
    seeds = [int(s) for s in args.seeds.split(',')]
    if os.environ.get('PYTHONHASHSEED') != '0':
        print('⚠️ 建議 PYTHONHASHSEED=0 跑（集合迭代序影響 dfs/探索序）')

    lines = []
    rows = []
    for v in variants:
        times, steps, oks = [], [], 0
        for seed in seeds:
            coords = make_coords(args.size, seed)
            t0 = time.time()
            deadline = t0 + args.cap

            def cc():
                return time.time() >= deadline
            res = hybrid_solve(build_game(coords, args.size, args.size), 2,
                               pipeline='alt', alt_max_rounds=v,
                               cancel_check=cc)
            dt = time.time() - t0
            ok = isinstance(res, tuple)
            oks += ok
            st = len(res[0]) if ok else None
            if dt < args.cap:
                times.append(dt)
            if ok:
                steps.append(st)
            print('  v%-2d seed%-5d %6.1fs  %s' %
                  (v, seed, dt, ('%d步' % st) if ok else 'TO/失败'),
                  flush=True)
        row = ('variants(alt_max_rounds)=%d  成功 %d/%d  耗時中位 %.1fs  '
               '步數中位 %s' % (v, oks, len(seeds), median(times),
                                median(steps) if steps else '—'))
        print(row, flush=True)
        lines.append(row)
        rows.append((v, oks, median(times),
                     median(steps) if steps else None))

    head = ('== cap 重驗 %dx%d step2 seeds=%s cap=%.0fs '
            '（PYTHONHASHSEED=%s %s）==' %
            (args.size, args.size, args.seeds, args.cap,
             os.environ.get('PYTHONHASHSEED'), time.strftime('%F %T')))
    print(head)
    out = [head] + lines
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n\n')
    print('appended ->', OUT)


if __name__ == '__main__':
    main()
