# -*- coding: utf-8 -*-
r"""
人类模仿求解器 headless 验证（无头，不依赖 GUI）
场景1：真实人类存档开局（坐标在存档区域）
场景2：GUI 真实新谜题（原点 shuffle，检验相对坐标编码的平移泛化）

运行：
    D:\python\python.exe 测试\_test_human_solve.py
"""
import os
import sys
import time
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import SliderMatrix
from solver.ml.human_solver import ai_human_solve, _load_puzzle_start
from solver.ml.gather_solver import gather_metrics


def run(label, game, step):
    coords0 = frozenset((b.location[0], b.location[1]) for b in game.blocks)
    met0 = gather_metrics(coords0, game.m, game.n)
    t0 = time.time()
    res = ai_human_solve(game, step)
    dt = time.time() - t0
    coords1 = frozenset((b.location[0], b.location[1]) for b in game.blocks)
    met1 = gather_metrics(coords1, game.m, game.n)
    n = len(res[0]) if res and res[0] else 0
    rows = [r for r, _ in coords0]
    cols = [c for _, c in coords0]
    print(f'{label}: 起始区 r{min(rows)}..{max(rows)} c{min(cols)}..{max(cols)} | '
          f'{n}步 {dt:.0f}s | 聚拢 {met0["score"]:.2f}->{met1["score"]:.2f}'
          + (' [已还原]' if game.is_solved() else ''))
    return n > 0


def main():
    ok = True
    save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'save')

    # 场景1：存档开局
    for fname, m, n, step in [('2-5-5.json', 5, 5, 2), ('2-6-6.json', 6, 6, 2)]:
        path = os.path.join(save_dir, fname)
        if not os.path.exists(path):
            continue
        g = _load_puzzle_start(m, n, step, path)
        if g is not None:
            ok &= run(f'存档{m}x{n}', g, step)

    # 场景2：GUI 真实新局（原点 shuffle）
    random.seed(1)
    for m, n in [(5, 5), (6, 6), (7, 7)]:
        g = SliderMatrix(m, n)
        g.shuffle(attempts=60, step=2)
        ok &= run(f'新局shuffle {m}x{n}', g, 2)

    print()
    print('ALL PASS' if ok else 'SOME FAILED')


if __name__ == '__main__':
    main()
