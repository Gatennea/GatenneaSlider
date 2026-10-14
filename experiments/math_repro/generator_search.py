# -*- coding: utf-8 -*-
"""
数字谜题「可达排列群」生成元法实验（Q1 第 2 步，2026-10）

问题背景（接 numbered_monodromy.py 第 1 步）：
  第 1 步用提升状态空间直接 BFS 求复原矩形上的可达排列群，但 3_3_1 的
  全空间是亿级（BFS 150 万截断时群阶只有 817，仅是下界），4_4_2 更大，
  暴力不可行。本脚本改用生成元法：

  方法：在「形态图」上枚举从复原矩形出发的简单有向回路（路径上不重复
  形态、中途不穿回复原矩形——穿过复原矩形的回路是两个子回路的拼接，
  子回路的生成元在群闭包下已覆盖）。每条回路把编号沿移动搬运一圈，
  得到复原矩形上的一个置换（生成元）；对生成元集合求乘法闭包即得
  可达排列群的下界；若闭包大小追上候选集上限（各着色类格子数阶乘
  之积 = 保着色类置换群的阶），即为精确解。

  群运算沿用第 1 步实证口径：(L_A ⋆ L_B)[i] = L_A[L_B[i]-1]。
  有限群中「只用生成元右乘的全体乘积」已经等于生成的子群（每个元素的
  逆是它的正幂），故闭包只需单侧乘法。

深度策略：逐层加深（第 d 层只枚举长度恰为 d 的简单回路），每层闭包一次，
达到候选上限立即停止；单层路径数超过预算则截断（结论降为下界）。

标定基准（第 1 步精确值）：
  2_3_1 -> 720（= 6!），2_3_2 -> 1，3_3_2 -> 96（= 4!·2!·2!·1!）
目标：
  3_3_1 -> 362,880（= 9!），4_4_2 -> 331,776（= (4!)^4）

用法：
  python experiments/math_repro/generator_search.py 2 3 1
  python experiments/math_repro/generator_search.py 3 3 1 --max-depth 6
  python experiments/math_repro/generator_search.py 4 4 2 --max-depth 5 --max-paths 5000000
"""

import argparse
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numbered_monodromy as nm  # noqa: E402


# ---------------------------------------------------------------------------
# 群闭包
# ---------------------------------------------------------------------------
def closure(gens, K, cap):
    """生成元集合的乘法闭包（单侧右乘，有限群下等于生成的子群）。

    达到 cap 时提前返回（此时闭包 == 候选上限，为精确解）。
    """
    ident = tuple(range(1, K + 1))
    group = {ident}
    dq = deque([ident])
    add = group.add
    while dq:
        g = dq.popleft()
        for gen in gens:
            h = tuple(gen[v - 1] for v in g)   # (gen ⋆ g)[i] = gen[g[i]-1]
            if h not in group:
                if len(group) >= cap:
                    return group
                add(h)
                dq.append(h)
    return group


# ---------------------------------------------------------------------------
# 逐层枚举简单回路
# ---------------------------------------------------------------------------
def cycles_layer(rect, depth, move_cache, K, budget, counter):
    """枚举长度恰为 depth、从 rect 出发回到 rect 的简单回路，返回生成元集合。

    - 路径上不重复形态（简单回路）
    - 中途不穿回 rect（两个子回路的拼接在闭包下已覆盖）
    - counter[0] 累计探索的路径边数，超过 budget 抛 RuntimeError
    """
    gens = set()

    def dfs(shape, labels, visited, d):
        if counter[0] > budget:
            raise RuntimeError('budget')
        if d == depth:
            return
        for new_shape, mp in _moves(shape, move_cache):
            if new_shape == rect:                 # 回到起点（须先于 visited 判断）
                if d + 1 == depth:
                    gens.add(_transport(labels, shape, mp, rect))
                continue                          # 不穿回 rect，继续只会绕圈
            if new_shape in visited:
                continue
            counter[0] += 1
            new_labels = _transport(labels, shape, mp, new_shape)
            dfs(new_shape, new_labels, visited | {new_shape}, d + 1)

    dfs(rect, tuple(range(1, K + 1)), frozenset({rect}), 0)
    gens.discard(tuple(range(1, K + 1)))
    return gens


def _moves(shape, move_cache):
    if shape not in move_cache:
        move_cache[shape] = nm.forward_moves(shape, nm.STEP)
    return move_cache[shape]


def _transport(labels, shape, mp, new_shape):
    """标签沿移动搬运：新形态格子 -> 旧格子映射 mp（同 forward_bfs 口径）。"""
    cells_old = sorted(shape)
    idx_old = {c: i for i, c in enumerate(cells_old)}
    cells_new = sorted(new_shape)
    return tuple(labels[idx_old[mp[c]]] for c in cells_new)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def solve(m, n, step, max_depth, max_paths):
    nm.STEP = step
    K = m * n
    tag = f'{m}_{n}_{step}'
    print('=' * 70)
    print(f'[{tag}] 生成元法：{m}×{n} 等级{step}，K={K}')
    t0 = time.time()

    rect = frozenset((r, c) for r in range(m) for c in range(n))
    candidate_count, _, _ = nm.make_candidate(m, n, step)
    cap = candidate_count(rect)
    print(f'  候选上限（保着色类置换群阶）= {cap:,}')

    move_cache = {}
    all_gens = set()
    total_paths = 0
    hit_cap = False
    truncated = False

    for depth in range(1, max_depth + 1):
        counter = [0]
        try:
            layer = cycles_layer(rect, depth, move_cache, K, max_paths, counter)
        except RuntimeError:
            truncated = True
            print(f'  深度 {depth}: 路径数超预算 {max_paths:,}，本层截断')
            break
        total_paths += counter[0]
        new_gens = layer - all_gens
        all_gens |= layer
        group = closure(all_gens, K, cap)
        print(f'  深度 {depth}: 路径 {counter[0]:,}，生成元 '
              f'{len(all_gens):,}（本层新增 {len(new_gens):,}），'
              f'闭包阶 {len(group):,}，累计路径 {total_paths:,}，'
              f'{time.time() - t0:.0f}s', flush=True)
        if len(group) >= cap:
            hit_cap = True
            break

    # 收尾：全量闭包确认（提前 break 时 closure 已到 cap）
    group = closure(all_gens, K, cap)
    print(f'  结果: 可达排列群阶 = {len(group):,}'
          + ('（达到候选上限，精确解）' if hit_cap else '（下界，未达上限）'))
    print(f'  生成元 {len(all_gens):,} 个，累计路径 {total_paths:,}'
          + ('，有截断' if truncated else ''))
    print(f'  总耗时 {time.time() - t0:.0f}s')


def main():
    ap = argparse.ArgumentParser(description='可达排列群生成元法')
    ap.add_argument('m', type=int)
    ap.add_argument('n', type=int)
    ap.add_argument('step', type=int)
    ap.add_argument('--max-depth', type=int, default=5,
                    help='回路最大深度（默认 5）')
    ap.add_argument('--max-paths', type=int, default=2_000_000,
                    help='单层路径数预算（默认 200 万）')
    args = ap.parse_args()
    solve(args.m, args.n, args.step, args.max_depth, args.max_paths)


if __name__ == '__main__':
    main()
