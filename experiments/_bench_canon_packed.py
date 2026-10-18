# -*- coding: utf-8 -*-
"""canonicalize 打包整数管线差分 + 微基准（2026-10-19 深夜实验 A）。

对比：
    旧版（_bench_find_window.py 同款复刻：tuple 空间 8 变体链）
    新版 solver.table_core._canonicalize_fs（打包整数管线）

内容：
  1. 差分：随机语料（各尺寸/非方形/漂移坐标/各种 K）逐字比对输出，
     必须 100% 一致（含并列变体的 tie-breaking 路径）。
  2. 微基准：未封装版（__wrapped__ vs legacy 函数）ABAB 交替计时。

用法：D:/python/python.exe experiments/_bench_canon_packed.py
"""
import os
import sys
import time
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'experiments'))

from solver.table_core import (_canonicalize_fs, _normalized_sorted,   # noqa: E402
                               _variants)

# ---------------------------------------------------------------------------
# 旧实现逐字复刻（改前快照，差分基准）
# ---------------------------------------------------------------------------
def canonicalize_legacy(coords) -> int:
    fs = coords if isinstance(coords, frozenset) else frozenset(coords)
    best = None
    for v in _variants(fs):
        nv = sorted(_normalized_sorted(v))
        if best is None or nv < best:
            best = nv
    h = 0
    for r, c in best:
        h = h * 65536 + (r * 256 + c)
    return h


# ---------------------------------------------------------------------------
# 语料
# ---------------------------------------------------------------------------
def gen_corpus():
    rng = random.Random(20261019)
    cases = []
    # 1) 常规尺寸随机连通板（K 固定满覆盖的子集）
    for (m, n) in [(2, 2), (3, 3), (4, 4), (3, 5), (5, 3), (4, 6), (6, 4),
                   (5, 5), (6, 6), (8, 8), (2, 7)]:
        for _ in range(120):
            K = m * n
            keep = rng.sample(range(K), rng.randint(max(1, K // 3), K))
            coords = frozenset((i // n, i % n) for i in keep)
            cases.append(coords)
    # 2) 漂移坐标（整体平移，含负）
    for _ in range(300):
        base = rng.choice(cases)
        dr, dc = rng.randint(-500, 500), rng.randint(-500, 500)
        cases.append(frozenset((r + dr, c + dc) for r, c in base))
    # 3) 手工角色：单格、两条、L 形、对称为旧版并列路径
    cases.append(frozenset({(0, 0)}))
    cases.append(frozenset({(0, 0), (0, 1)}))
    cases.append(frozenset({(0, 0), (0, 1), (1, 0)}))
    cases.append(frozenset({(0, 0), (1, 1)}))          # 对角（双分量）
    cases.append(frozenset({(0, 0), (0, 1), (1, 0), (1, 1)}))  # 2x2 全对称
    cases.append(frozenset({(0, 0), (0, 1), (0, 2), (1, 1)}))  # T 形
    return cases


def main():
    cases = gen_corpus()
    print('语料 %d 例' % len(cases))

    # 1) 差分（未封装版，绕开 lru_cache）
    new_raw = _canonicalize_fs.__wrapped__
    bad = 0
    for fs in cases:
        a, b = canonicalize_legacy(fs), new_raw(fs)
        if a != b:
            bad += 1
            if bad <= 3:
                print('  MISMATCH legacy=%d new=%d  %s' % (a, b, sorted(fs)[:6]))
    print('[%s] 差分 %d/%d 一致' % ('PASS' if bad == 0 else 'FAIL',
                                     len(cases) - bad, len(cases)))

    # 2) 微基准 ABAB（未封装；每轮打乱评测序，抵消缓存/GC 波动）
    N = 4
    tl = tn = 0.0
    for i in range(N):
        order = cases if i % 2 == 0 else list(reversed(cases))
        t0 = time.perf_counter()
        for fs in order:
            canonicalize_legacy(fs)
        tl += time.perf_counter() - t0
        t0 = time.perf_counter()
        for fs in order:
            new_raw(fs)
        tn += time.perf_counter() - t0
    print('微基准（未封装，%d 轮 ABAB，共 %d 次调用）' % (N, N * len(cases)))
    print('  旧版 %.3fs   新版 %.3fs   提速 %.2fx' % (tl, tn, tl / tn))


if __name__ == '__main__':
    main()
