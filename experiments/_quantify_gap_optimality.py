# -*- coding: utf-8 -*-
"""階段四（PDB 預研第一步·量差距）：4×4 當前混合流水線的解長離最短差多少。

A 段文檔（docs/solver/求解器AI搜索优化方向.md §3.1）要求：先用 (4,4,2)
上帝之數/距離表當標尺，量化 GBFS 給的解離最短差多少，確認「追求最短」
對玩家有無價值，再決定 PDB 投入。

做法：4×4 有全量距離表 → table_solve = 保證最短；hybrid_solve（無表路徑，
入口強制走混合）= 現役「能出解」水準。同種子對比 (最短步數, 混合步數, 倍數)。

用法：$env:PYTHONHASHSEED='0'; python experiments/_quantify_gap_optimality.py
結果落盤：experiments/_quantify_gap_optimality_out.txt
"""
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game import SliderMatrix                          # noqa: E402
from solver.ml.fill_macro import build_game            # noqa: E402
from solver.hybrid_solver import hybrid_solve          # noqa: E402
from solver.table_solver import table_solve            # noqa: E402

OUT = os.path.join(ROOT, 'experiments', '_quantify_gap_optimality_out.txt')
SEEDS = list(range(1000, 1020))   # 與驗收同種子帶（4×4 step2, attempts=140）


def main():
    rows = []
    ratios = []
    h_times = []
    for seed in SEEDS:
        random.seed(seed)
        g = SliderMatrix(4, 4)
        g.shuffle(attempts=140, step=2)
        coords = frozenset(tuple(b.location) for b in g.blocks)
        opt = table_solve(build_game(coords, 4, 4), 2,
                          cancel_check=lambda: False)
        if not isinstance(opt, tuple) or not opt[0]:
            print('seed%-5d 查表無解，跳過' % seed, flush=True)
            continue
        t0 = time.time()
        hy = hybrid_solve(build_game(coords, 4, 4), 2,
                          cancel_check=lambda: False)
        dt = time.time() - t0
        h_times.append(dt)
        if not isinstance(hy, tuple) or not hy[0]:
            rows.append((seed, len(opt[0]), None, None, dt))
            print('seed%-5d opt=%d  hybrid=%s  %.1fs'
                  % (seed, len(opt[0]), hy, dt), flush=True)
            continue
        ratio = len(hy[0]) / len(opt[0])
        ratios.append(ratio)
        rows.append((seed, len(opt[0]), len(hy[0]), ratio, dt))
        print('seed%-5d opt=%3d  hybrid=%3d  %.1fx  %.1fs'
              % (seed, len(opt[0]), len(hy[0]), ratio, dt), flush=True)

    lines = ['== 4×4 step2 解長差距（%d 種子，hybrid 無表路徑 vs 查表最短）=='
             % len(rows)]
    if ratios:
        lines += [
            '倍數中位 %.1fx  均值 %.1fx  最差 %.1fx  ≤2x 的局 %d/%d'
            % (statistics.median(ratios), statistics.mean(ratios),
               max(ratios), sum(1 for r in ratios if r <= 2), len(ratios)),
            '步數中位：最短 %s / 混合 %s'
            % (statistics.median([r[1] for r in rows if r[2]]),
               statistics.median([r[2] for r in rows if r[2]])),
            'hybrid 耗時中位 %.1fs' % statistics.median(h_times),
        ]
    for r in rows:
        lines.append('seed%-5d opt=%s hybrid=%s ratio=%s t=%.1fs' % r)
    text = '\n'.join(lines)
    print(text)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print('results ->', OUT)


if __name__ == '__main__':
    main()
