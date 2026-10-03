# -*- coding: utf-8 -*-
r"""mi 最佳放置的 mod 约束探针（M3 前置，計劃 §4/§6）。

要回答四个问题，**每个都必须实测、不许照抄 tri 的结论**：

  A  `(r+c)%step, (r−c)%step` 的类计数在引擎真实滑动下守恒吗？
     （cell_class 的文档断言，逐条量一遍；不守恒则整个 mod 网格过滤是假的）
  B  哪些平移偏移 (dr, dc) 让目标形状的**类分布**保持不变？
     tri 的结论是「偏移必须是 step 的倍数」，那是 (i%step, j%step) 逐块不变
     的特例。mi 的类是 (r+c, r−c) 的二维余数，平移 (dr,dc) 只把类整体挪
     ((dr+dc)%step, (dr−dc)%step) —— 允许的偏移集合是另一个 lattice，
     形状未知，必须枚举量出来。
  C  半格偏移（换晶格 A→B）在 mod 上合法吗？错位态下 (r+c)%step 怎么变？
  D  偏移枚举域要多大才不漏掉最优放置（拿更宽的暴力范围对照）？

运行：D:\python\python.exe -u experiments\_mi_mod_probe.py
"""
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_mi import GAP_DIRECTIONS, MiSliderMatrix  # noqa: E402
from gui.cell_class import cell_class  # noqa: E402


def _cls(cells, step):
    return Counter(cell_class(k, step, 'mi') for k in cells)


# ---------------------------------------------------------------------------
def probe_a():
    print('\n=== A mod 类计数在引擎滑动下守恒？ ===')
    random.seed(3)
    total = bad = 0
    for m, n in ((3, 3), (4, 4), (4, 3)):
        for step in (1, 2, 3):
            if step >= max(m, n):
                continue
            g = MiSliderMatrix(m, n)
            g.shuffle(20, step)
            before = _cls(g.positions(), step)
            for _ in range(150):
                gaps = g.all_gaps()
                if not gaps:
                    break
                fam, line = random.choice(gaps)
                g.opt(fam, line, random.choice(g.blocks))
                d = random.choice(GAP_DIRECTIONS[fam])
                pos, _ = g.try_move_ex(d, step)
                if not pos:
                    g._clear_selection()
                    continue
                g.commit_move(pos)
                g.update_matrix()
                after = _cls(g.positions(), step)
                total += 1
                if after != before:
                    bad += 1
                    if bad <= 3:
                        print(f'     反例 m={m} n={n} step={step} '
                              f'diff={ (after - before)}')
                before = after
    print(f'     {total} 步，类计数变化 {bad} 次')
    return total, bad


# ---------------------------------------------------------------------------
def probe_b():
    print('\n=== B 哪些平移偏移保持目标形状的类分布？ ===')
    print('     （枚举 dr, dc ∈ [-3, 3]，含半格；比较类计数）')
    for m, n in ((3, 3), (4, 4), (4, 3)):
        for step in (2, 3, 4):
            if step >= max(m, n):
                continue
            goal = MiSliderMatrix(m, n).positions()
            base = _cls(goal, step)
            ok_int, ok_half = [], []
            for di in range(-3, 4):
                for dj in range(-3, 4):
                    half = (di % 2 == 1) or (dj % 2 == 1)
                    sh = {(r + di / 2, c + dj / 2, q) for r, c, q in goal}
                    if _cls(sh, step) == base:
                        (ok_half if half else ok_int).append((di, dj))
            # 归纳：整半格单位下的规律
            def _norm(lst):
                return sorted((a / 2, b / 2) for a, b in lst)
            print(f'     m={m} n={n} step={step}: '
                  f'整格合法 {len(ok_int)} 个 {sorted((a/2, b/2) for a, b in ok_int)}')
            print(f'{"":21s}半格合法 {len(ok_half)} 个 '
                  f'{_norm(ok_half)[:12]}')


# ---------------------------------------------------------------------------
def probe_c():
    print('\n=== C 半格偏移（换晶格）在 mod 上合法吗 ===')
    g = MiSliderMatrix(4, 4)
    goal = g.positions()
    for step in (1, 2, 3):
        base = _cls(goal, step)
        # 换晶格：整盘斜滑一格 → 坐标 ±0.5
        shifted = {(r - 0.5, c - 0.5, q) for r, c, q in goal}
        same = _cls(shifted, step) == base
        # 半格但只错一个轴（r 半、c 整）—— 奇偶不一致，非法局面
        mixed = {(r - 0.5, c, q) for r, c, q in goal}
        print(f'     step={step}: (0.5,0.5) 偏移保持类分布 = {same}；'
              f'(0.5, 0) 偏移 = {_cls(mixed, step) == base}')


# ---------------------------------------------------------------------------
def probe_d():
    print('\n=== D 打乱后的最佳放置落在哪个偏移？（暴力 + mod 过滤对照） ===')

    def best(coords, m, n, step, lo, hi, mod_filter):
        goal = MiSliderMatrix(m, n).positions()
        bestov, bestoff = 0, None
        for di in range(lo, hi + 1):
            for dj in range(lo, hi + 1):
                sh = {(r + di / 2, c + dj / 2, q) for r, c, q in goal}
                if mod_filter and _cls(sh, step) != _cls(coords, step):
                    continue
                ov = len(coords & sh)
                if ov > bestov:
                    bestov, bestoff = ov, (di, dj)
        return bestov, bestoff

    random.seed(7)
    for m, n, step in ((3, 3, 2), (4, 4, 2), (4, 4, 3), (4, 3, 2)):
        g = MiSliderMatrix(m, n)
        g.shuffle(20, step)
        cells = frozenset(g.positions())
        rs = [c[0] for c in cells]
        cs = [c[1] for c in cells]
        lo_r, hi_r = min(rs), max(rs)
        lo_c, hi_c = min(cs), max(cs)
        # 宽范围暴力（覆盖整盘可能散到的全部位置）
        ov_all, off_all = best(cells, m, n, step,
                               int(2 * lo_r) - 2 * m, int(2 * hi_r) + 2, False)
        ov_mod, off_mod = best(cells, m, n, step,
                               int(2 * lo_r) - 2 * m, int(2 * hi_r) + 2, True)
        print(f'     m={m} n={n} step={step}: 无过滤最优 {ov_all}/'
              f'{4 * m * n} @ {off_all}；有 mod 过滤 {ov_mod} @ {off_mod} '
              f'{"（一致）" if ov_all == ov_mod else "★过滤掉了最优"}')


def main():
    print('=' * 70)
    print('mi mod 约束探针（M3 前置）')
    print('=' * 70)
    probe_a()
    probe_b()
    probe_c()
    probe_d()
    print('\n' + '=' * 70)


if __name__ == '__main__':
    main()
