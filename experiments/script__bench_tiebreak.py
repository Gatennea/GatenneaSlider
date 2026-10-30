# -*- coding: utf-8 -*-
"""GBFS 平手打破策略 A/B（2026-10-19 深夜实验 C，不动源码）。

现状堆键 (h, ng, counter)：等 h 时优先浅层（BFS 倾向）。
候选堆键 (h, -ng, counter)：等 h 时优先深层（DFS 倾向，向目标俯冲）。

「至少填一个洞」是存在性目标，俯冲策略通常显著减节点；但可能俯进
死胡同。实测说话：同语料对比 节点数 / 时间 / 解长。

用法：D:/python/python.exe experiments/script__bench_tiebreak.py [--size 5x5]
"""
import os
import sys
import time
import heapq
import argparse
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'experiments'))

from game import SliderMatrix                                    # noqa: E402
from solver.ml.fill_macro import build_game                      # noqa: E402
from solver.table_core import canonicalize                       # noqa: E402
from solver.search_core import expand, fast_window, heuristic    # noqa: E402
import solver.hybrid_solver as _hs                               # noqa: E402


def guided_reduce_one_tb(coords, m, n, step, budget=80000,
                         cancel_check=None, dive=False):
    """guided_reduce_one 复刻，堆键可切（dive=True → 等 h 优先深层）。"""
    start = frozenset(coords)
    h0 = len(fast_window(start, m, n)[1])
    counter = 0
    openq = [(h0, 0, 0, start, [])]
    bestg = {canonicalize(start): 0}
    closed = set()
    expanded = 0
    while openq:
        _f, g, _, cur, path = heapq.heappop(openq)
        ck = canonicalize(cur)
        if g > bestg.get(ck, -1) or ck in closed:
            continue
        if len(fast_window(cur, m, n)[1]) < h0:
            return path, expanded
        closed.add(ck)
        expanded += 1
        if expanded > budget or (cancel_check and cancel_check()):
            return None, expanded
        for new, act, rep in expand(cur, step):
            nk = canonicalize(new)
            ng = g + 1
            if ng >= bestg.get(nk, 10 ** 9):
                continue
            bestg[nk] = ng
            counter += 1
            hh = heuristic(new, m, n, step)
            key = (hh, -ng, counter) if dive else (hh, ng, counter)
            heapq.heappush(openq, key + (new, path + [(act, rep)]))
    return None, expanded


def run(coords, m, n, step, dive):
    _hs.guided_reduce_one = (lambda *a, **k:
                             guided_reduce_one_tb(*a, dive=dive, **k))
    g = build_game(coords, m, n)
    t0 = time.time()
    try:
        res = _hs.hybrid_solve(g, step)
    except Exception as e:
        res = {'type': 'exc', 'err': repr(e)}
    dt = time.time() - t0
    if isinstance(res, tuple):
        return dt, 'solved %d 步' % len(res[0])
    return dt, '%s: %s' % (res.get('type'), str(res.get('reason', ''))[:40])


def shuffled_coords(m, n, step, seed, attempts=140):
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=step)
    return frozenset(tuple(b.location) for b in g.blocks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--size', default='5x5')
    ap.add_argument('--seeds', default='1000,1001,1002,1003')
    args = ap.parse_args()
    m = n = int(args.size.split('x')[0])
    step = 2
    print('%-8s %-24s %-24s' % ('seed', 'BFS(现状)', 'DFS(俯冲)'))
    for sd in [int(x) for x in args.seeds.split(',')]:
        coords = shuffled_coords(m, n, step, sd)
        row = []
        for dive in (False, True):
            dt, desc = run(coords, m, n, step, dive)
            row.append('%.1fs %s' % (dt, desc))
        print('%-8s %-24s %-24s' % (sd, row[0], row[1]))


if __name__ == '__main__':
    main()
