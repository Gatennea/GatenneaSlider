# -*- coding: utf-8 -*-
"""无表尺寸 hybrid 求解性能画像（2026-10-19 深夜实验第一棒）。

背景：前缀和优化（commit c272d72）后，GBFS 段的微基准热点已重排，
但**端到端**的真实分布没测过。本脚本对无表尺寸（5×5/6×6 step2）跑
hybrid_solve，用 cProfile 出 tottime/cumtime 排行，定位下一棒优化目标。

用法：
    D:/python/python.exe experiments/script__bench_hybrid_profile.py [--size 5x5] [--seed 1000]
    D:/python/python.exe experiments/script__bench_hybrid_profile.py --noprofile   # 只测墙钟
"""
import os
import sys
import time
import cProfile
import pstats
import io
import argparse
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'experiments'))

from game import SliderMatrix                                    # noqa: E402
from solver.ml.fill_macro import build_game                      # noqa: E402
from solver.hybrid_solver import hybrid_solve                    # noqa: E402


def shuffled_coords(m, n, step, seed, attempts=140):
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=step)
    return frozenset(tuple(b.location) for b in g.blocks), g


def run(coords, m, n, step, profile):
    box = {}

    def worker():
        g = build_game(coords, m, n)
        t0 = time.time()
        try:
            res = hybrid_solve(g, step)
        except Exception as e:
            res = {'type': 'exc', 'err': repr(e)}
        box['dt'] = time.time() - t0
        box['res'] = res

    if profile:
        pr = cProfile.Profile()
        pr.enable()
        worker()
        pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats('tottime')
        ps.print_stats(28)
        box['profile'] = s.getvalue()
    else:
        worker()
    return box


def describe(res):
    if isinstance(res, tuple):
        return 'solved %d 步' % len(res[0])
    if isinstance(res, dict):
        return '%s: %s' % (res.get('type'), str(res.get('reason', ''))[:50])
    return str(res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--size', default='5x5')
    ap.add_argument('--seed', type=int, default=1000)
    ap.add_argument('--noprofile', action='store_true')
    args = ap.parse_args()
    m = n = int(args.size.split('x')[0])
    step = 2

    coords, g = shuffled_coords(m, n, step, args.seed)
    print(f'[bench] {m}x{n} step{step} seed{args.seed} 方块 {len(coords)} '
          f'solved={g.is_solved()}', flush=True)
    box = run(coords, m, n, step, profile=not args.noprofile)
    print(f'[bench] {box["dt"]:.1f}s  {describe(box["res"])}', flush=True)
    if 'profile' in box:
        print(box['profile'])


if __name__ == '__main__':
    main()
