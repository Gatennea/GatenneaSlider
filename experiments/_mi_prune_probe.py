# -*- coding: utf-8 -*-
"""探针：mi 聚拢「少枚举 / 快打分」能省多少 —— **先量再改**。

執行：``D:/python/python.exe -u experiments/_mi_prune_probe.py``

背景（2026-10-04 实测）：mi 聚拢每步候选 60~80 个，耗时剖分是
    apply_action 105~163ms/步（53~74%） + shape_score 51~83ms/步（23~42%），
    枚举本身只 8ms（3~4%）。
所以提效有两条路：**少枚举**（剪掉注定不可用的候选）或**快打分**（算分更快）。
本文只量「少枚举」的潜力，三种剪枝各量一遍：

  P1 跨缝重复：(族,线,侧,向) 相同但 rep 不同的动作 —— 枚举里同一组有几个 rep？
     这些 rep 移动后**落点是否相同**？若相同就是纯冗余。
  P2 撞墙预判：方向 d 与 -d 里，往往有一个被边界挡住。用「该分量的包围盒
     是否顶到盘面边界」可以在**不试**的情况下排掉一部分。
  P3 去重后候选数：P1+P2 应用后剩多少。

**只量现象、不改生产代码** —— 结论出来再决定值不值得动。
"""
import os
import random
import statistics
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from game_mi import MiSliderMatrix, side_of                    # noqa: E402
import solver.ml.mi_adapter as MA                             # noqa: E402
from solver.ml.mi_placement import best_placement             # noqa: E402


def probe_actions(m, n, step, n_walk=25, seed0=0):
    """随机走 n_walk 步，统计每步的候选构成。"""
    random.seed(seed0)
    g = MiSliderMatrix(m, n)
    g.shuffle(60, step)
    spec = MA.MiSpec(m, n, step)

    rows = []
    for _ in range(n_walk):
        cells = MA.mi_coords(g)
        acts = MA.enumerate_actions(g, step)
        if not acts:
            break
        n_all = len(acts)

        # ---- P1：同一 (族,线,侧,向) 下有几个 rep？落点是否相同？ ----
        by_key = defaultdict(list)
        for a in acts:
            by_key[(a[0], a[1], a[2], a[3])].append(a)
        n_multi = sum(1 for v in by_key.values() if len(v) > 1)

        # 落点去重：把每个候选真跑一遍，记终态哈希（只在探针里做，代价高无妨）
        base = MA.snap(g)
        outcomes = {}
        n_fail = 0
        for a in acts:
            if not MA.apply_action(g, a, step):
                n_fail += 1
                continue
            outcomes.setdefault(a, frozenset(MA.mi_coords(g)))
            MA.restore(g, base)
        n_distinct = len({v for v in outcomes.values()})

        # ---- P2：包围盒顶边界的比例（撞墙粗判） ----
        # 只统计「该分量的极值恰好压在盘面边界上」的动作数
        n_wall = 0
        for a in acts:
            gt, ln, side, d, rep = a
            grp = by_key[(gt, ln, side, d)]
            # 该 rep 所在分量（用 side_cells 近似：与 rep 同侧同族的块）
            side_cells = {c for c in cells if side_of(gt, ln, c) == side}
            comp = _comp_of(gt, ln, side, side_cells, rep)
            if not comp:
                continue
            if _touch_wall(comp, m, n):
                n_wall += 1

        rows.append({
            'n_all': n_all,
            'n_keys': len(by_key),
            'n_multi': n_multi,
            'n_fail': n_fail,
            'n_distinct': n_distinct,
            'n_wall': n_wall,
        })

        # 随机走一步（用第一个可执行动作）
        for a in acts:
            if MA.apply_action(g, a, step):
                break
            MA.restore(g, base)
        else:
            break
    return rows


def _comp_of(gap_type, line, side, side_cells, rep):
    from game_mi import neighbors as mi_neighbors
    if rep not in side_cells:
        return set()
    comp = {rep}
    stack = [rep]
    while stack:
        cur = stack.pop()
        for nb in mi_neighbors(cur):
            if nb in side_cells and nb not in comp:
                comp.add(nb)
                stack.append(nb)
    return comp


def _touch_wall(comp, m, n):
    """分量里是否有块的坐标落在盘面边界上（0 或 m/n、±半格也算贴边）。"""
    for r, c, _q in comp:
        if r <= -1 or c <= -1 or r >= m or c >= n:
            return True
    return False


def main():
    for (m, n, step) in ((3, 3, 1), (3, 3, 2), (4, 4, 2)):
        rows = probe_actions(m, n, step)
        if not rows:
            print(f'=== mi {m}x{n} step={step}: 没采到样本 ===')
            continue
        avg = lambda k: statistics.mean(r[k] for r in rows)
        print(f'=== mi {m}x{n} step={step}（{len(rows)} 步采样）===')
        print(f'  候选总数        均 {avg("n_all"):.1f}')
        print(f'  唯一(族,线,侧,向) 均 {avg("n_keys"):.1f}'
              f'   ← 同一组下有多个 rep 的组数 均 {avg("n_multi"):.1f}')
        print(f'  真跑失败的        均 {avg("n_fail"):.1f}'
              f'  （{avg("n_fail") / avg("n_all") * 100:.0f}%）')
        print(f'  **落点去重后**    均 {avg("n_distinct"):.1f}'
              f'  （{avg("n_distinct") / avg("n_all") * 100:.0f}% 保留）')
        print(f'  分量贴边          均 {avg("n_wall"):.1f}'
              f'  （{avg("n_wall") / avg("n_all") * 100:.0f}%）')
        gain = 1 - avg('n_distinct') / avg('n_all')
        print(f'  → **候选可省 {gain * 100:.0f}%**'
              f'（每步 0.2s × 省下部分 ≈ 每步省 '
              f'{gain * 0.2 * 1000:.0f}ms）')
        print()


if __name__ == '__main__':
    main()
