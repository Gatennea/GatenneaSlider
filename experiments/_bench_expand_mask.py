# -*- coding: utf-8 -*-
"""expand 掩码化差分测试（2026-10-19 深夜实验 B）。

对比：
    旧版（改前快照复刻：逐单位步重建坐标集 + set-DFS 连通判定）
    新版 solver.search_core.expand（网格掩码 + 整数移位 + 位并行 BFS）

差分语料：随机板（各尺寸/非方形/各种 K/含不连通输入/漂移坐标）×
step 1..7，逐字比对输出列表（顺序 + (frozenset, action, rep) 全等）。

用法：D:/python/python.exe experiments/_bench_expand_mask.py
"""
import os
import sys
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver.table_core import _side_components, is_single_connected   # noqa: E402
from solver.search_core import expand, DCHAR                          # noqa: E402


# ---------------------------------------------------------------------------
# 旧实现逐字复刻（改前快照，差分基准）
# ---------------------------------------------------------------------------
def expand_legacy(coords, step):
    B = set(coords)
    total = len(B)
    out = []
    rows = [r for r, _ in B]
    cols = [c for _, c in B]

    def go(comp, gt, L, side, D):
        du = (D[0] // step if D[0] else 0, D[1] // step if D[1] else 0)
        non = B - set(comp)
        cur = set(comp)
        for _ in range(step):
            cur = {(r + du[0], c + du[1]) for r, c in cur}
            if cur & non or not is_single_connected(cur | non):
                return
        res = frozenset(non | cur)
        if len(res) == total:
            out.append((res, (gt, L, side, DCHAR[du]), next(iter(comp))))

    for L in range(min(rows), max(rows)):
        for side in ('above', 'below'):
            for comp in _side_components(B, 'h', L, side):
                for sgn in (-1, 1):
                    go(comp, 'h', L, side, (0, sgn * step))
    for L in range(min(cols), max(cols)):
        for side in ('left', 'right'):
            for comp in _side_components(B, 'v', L, side):
                for sgn in (-1, 1):
                    go(comp, 'v', L, side, (sgn * step, 0))
    return out


def gen_corpus():
    rng = random.Random(20261019)
    cases = []
    for (m, n) in [(2, 2), (3, 3), (4, 4), (3, 5), (5, 3), (4, 6), (5, 5),
                   (6, 6), (2, 7), (7, 2)]:
        for _ in range(60):
            K = m * n
            keep = rng.sample(range(K), rng.randint(2, K))
            coords = frozenset((i // n, i % n) for i in keep)
            for step in (1, 2, 3, 4):
                cases.append((coords, step))
    # 漂移坐标（含负）
    for _ in range(200):
        base, step = rng.choice(cases)
        dr, dc = rng.randint(-300, 300), rng.randint(-300, 300)
        cases.append((frozenset((r + dr, c + dc) for r, c in base), step))
    # 大步长（超过板面尺度）
    for _ in range(60):
        base, _s = rng.choice(cases)
        cases.append((base, rng.choice((5, 6, 7))))
    return cases


def main():
    cases = gen_corpus()
    print('语料 %d 例（板 × step）' % len(cases))
    bad = 0
    n_succ = 0
    for coords, step in cases:
        a = expand_legacy(coords, step)
        b = expand(coords, step)
        n_succ += len(b)
        if a != b:
            bad += 1
            if bad <= 3:
                print('  MISMATCH step=%d coords=%s' % (step, sorted(coords)[:8]))
                print('    legacy %d 项 / new %d 项' % (len(a), len(b)))
                sa, sb = set(a), set(b)
                for x in list(sa - sb)[:2]:
                    print('    only legacy:', x)
                for x in list(sb - sa)[:2]:
                    print('    only new   :', x)
                if sa == sb:
                    print('    （集合相同、順序不同）')
    print('[%s] 差分 %d/%d 一致（共 %d 个后继）' % (
        'PASS' if bad == 0 else 'FAIL', len(cases) - bad, len(cases), n_succ))


if __name__ == '__main__':
    main()
