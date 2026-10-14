# -*- coding: utf-8 -*-
"""
B：给「着色集合相同但不可解」的反例找第二不变量。

背景：verify_coloring.py 已证伪猫九的猜想「着色集合（mod 类计数多重集）相同 ⟹ 可解」。
本脚本寻找更强的、能分离 A−B 与可解集的必要条件（不变量）。

方法（全部实证，不靠手推）：
  1. R = 目标帧可达集：从 goal 出发做正向 BFS，状态保留绝对坐标，
     只按「平移模 step 归一」去重（同形状的可达根位置彼此相差 step 的倍数，
     所以锚定 min ≡ 0..step-1 (mod step) 后状态空间有限且帧语义与目标帧一致）。
  2. 候选特征库：对每个状态计算一组特征，保留在 R 上「恒定」的（真不变量候选）。
  3. 分离检验：反例形状取全部 step² 个相位根位置，若没有任何相位能同时命中
     R 的不变量取值 → 该不变量组可先验排除反例。
  4. 充分性检验（3_3_2 等小尺寸）：枚举全部单连通形状，用选出的不变量过滤，
     与表 B 比对——若过滤集 == B，则该尺寸获得完整的先验判定法。

step=1 特例：mod 条件平凡；直线型反例单独用「出度=0（孤立点）」解释。

用法：
  python experiments/math_repro/second_invariant.py 3_3_2
  python experiments/math_repro/second_invariant.py 2_3_1 3_3_1 3_3_2
"""

import argparse
import sys
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402
from verify_coloring import (  # noqa: E402
    enumerate_states, load_table, parse_puzzle, render, target_variants, verify)

DIRS4 = ((-1, 0), (1, 0), (0, -1), (0, 1))


# ---------------------------------------------------------------------------
# 目标帧可达集（平移模 step 锚定，保留帧语义）
# ---------------------------------------------------------------------------
def anchor(cells, step):
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    ar = min(rs) - min(rs) % step
    ac = min(cs) - min(cs) % step
    if ar == 0 and ac == 0:
        return frozenset(cells)
    return frozenset((r - ar, c - ac) for r, c in cells)


def reachable_rooted(m, n, step):
    """从 goal 出发的正向 BFS，按 anchor(step) 去重，返回 frozenset 集合。"""
    total = m * n
    start = anchor(tc.goal_state(m, n), step)
    seen = {start}
    q = deque([start])
    while q:
        cur = q.popleft()
        cells = set(cur)
        rows = [r for r, _ in cells]
        cols = [c for _, c in cells]
        for L in range(min(rows), max(rows)):
            for side in ('above', 'below'):
                for comp in tc._side_components(cells, 'h', L, side):
                    for sign in (-1, 1):
                        nb = _try_move(cells, comp, (0, sign * step), step, total)
                        if nb is not None:
                            a = anchor(nb, step)
                            if a not in seen:
                                seen.add(a)
                                q.append(a)
        for L in range(min(cols), max(cols)):
            for side in ('left', 'right'):
                for comp in tc._side_components(cells, 'v', L, side):
                    for sign in (-1, 1):
                        nb = _try_move(cells, comp, (sign * step, 0), step, total)
                        if nb is not None:
                            a = anchor(nb, step)
                            if a not in seen:
                                seen.add(a)
                                q.append(a)
    return seen


def _try_move(cells, comp, D, step, total):
    """整步移动（含逐步碰撞/连通检查），返回格集或 None。D 为整步位移，逐步施加单位方向。"""
    du = (D[0] // step if D[0] else 0, D[1] // step if D[1] else 0)
    non_sel = cells - set(comp)
    cur = set(comp)
    for _ in range(step):
        cur = {(r + du[0], c + du[1]) for r, c in cur}
        if cur & non_sel:
            return None
        if not tc.is_single_connected(cur | non_sel):
            return None
    result = non_sel | cur
    return result if len(result) == total else None


# ---------------------------------------------------------------------------
# 特征库
# ---------------------------------------------------------------------------
def slot_counts(cells, step):
    """带槽位（固定相位）的 mod 类计数元组，按 (i,j)->i*step+j 排序。"""
    cnt = Counter(((r % step, c % step) for r, c in cells))
    return tuple(cnt.get((i, j), 0)
                 for i in range(step) for j in range(step))


def bbox_normalize(cells):
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    r0, c0 = min(rs), min(cs)
    return [(r - r0, c - c0) for r, c in cells]


def features(cells, step):
    """特征字典。cells 为某个根位置（锚定帧）。"""
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    H = max(rs) - min(rs) + 1
    W = max(cs) - min(cs) + 1
    bb = bbox_normalize(cells)
    cellset = set(cells)
    adj = 0
    ends = branches = 0
    diag = 0
    for r, c in cells:
        d = sum((r + dr, c + dc) in cellset for dr, dc in DIRS4)
        adj += d
        if d == 1:
            ends += 1
        elif d >= 3:
            branches += 1
        for dr, dc in ((-1, -1), (-1, 1)):
            if (r + dr, c + dc) in cellset:
                diag += 1
    # adj 此处为度数和（= 2×邻接对数）；周长 = 4K − 度数和
    perim = 4 * len(cells) - adj
    row_prof = Counter(rs)
    col_prof = Counter(cs)
    # 直径（格图最远 BFS 距离）
    diameter = 0
    for seed in cells:
        seen = {seed}
        frontier = [seed]
        dist = 0
        while frontier:
            nxt = []
            for r, c in frontier:
                for dr, dc in DIRS4:
                    q = (r + dr, c + dc)
                    if q in cellset and q not in seen:
                        seen.add(q)
                        nxt.append(q)
            if nxt:
                dist += 1
            frontier = nxt
        diameter = max(diameter, dist)
    pairs = adj // 2
    cycles = pairs - len(cells) + 1          # 一阶贝蒂数（连通格图）
    H0, W0 = H, W
    border = sum(r == 0 or r == H0 - 1 or c == 0 or c == W0 - 1
                 for r, c in bb)
    # 水平/竖直连续段总数
    h_runs = 0
    row_cols = {}
    for r, c in bb:
        row_cols.setdefault(r, []).append(c)
    for cols in row_cols.values():
        cols.sort()
        h_runs += 1 + sum(b - a - 1 for a, b in zip(cols, cols[1:]))
    v_runs = 0
    col_rows = {}
    for r, c in bb:
        col_rows.setdefault(c, []).append(r)
    for rows in col_rows.values():
        rows.sort()
        v_runs += 1 + sum(b - a - 1 for a, b in zip(rows, rows[1:]))
    rsum = sum(r for r, _ in bb)
    csum = sum(c for _, c in bb)
    rcross = sum(r * c for r, c in bb)
    r2 = sum(r * r for r, _ in bb)
    c2 = sum(c * c for _, c in bb)
    diag_p = max(r + c for r, c in bb)
    diag_m = max(r - c for r, c in bb) - min(r - c for r, c in bb)
    # 洞（外接盒内被包围的空格）
    bbset = set(bb)
    holes = 0
    for r in range(H):
        for c in range(W):
            if (r, c) in bbset:
                continue
            seen = set()
            stack = [(r, c)]
            escaped = False
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                xr, xc = x
                if xr < 0 or xr >= H or xc < 0 or xc >= W:
                    escaped = True
                    break
                if x in bbset:
                    continue
                for dr, dc in DIRS4:
                    stack.append((xr + dr, xc + dc))
            if not escaped:
                holes += 1
    return {
        'slots': slot_counts(cells, step),
        'bbox_slots': slot_counts(bb, step),
        'H': H, 'W': W, 'H_parity': H % 2, 'W_parity': W % 2,
        'min_r_p': min(rs) % step, 'min_c_p': min(cs) % step,
        'even_row': sum(r % 2 == 0 for r, _ in cells),
        'even_col': sum(c % 2 == 0 for _, c in cells),
        'row_prof': tuple(sorted(row_prof.values())),
        'col_prof': tuple(sorted(col_prof.values())),
        'perimeter': perim,
        'adj': adj, 'ends': ends, 'branches': branches, 'diag': diag,
        'bbox_area': H * W,
        'holes': holes,
        'n_rows': len(row_prof), 'n_cols': len(col_prof),
        'diameter': diameter, 'cycles': cycles, 'border': border,
        'h_runs': h_runs, 'v_runs': v_runs,
        'rsum': rsum, 'csum': csum, 'rcross': rcross, 'r2': r2, 'c2': c2,
        'diag_p': diag_p, 'diag_m': diag_m,
    }


FEATURE_KEYS = ['slots', 'bbox_slots', 'H_parity', 'W_parity', 'H', 'W',
                'even_row', 'even_col', 'row_prof', 'col_prof',
                'perimeter', 'adj', 'ends', 'branches', 'diag',
                'bbox_area', 'holes', 'n_rows', 'n_cols',
                'diameter', 'cycles', 'border', 'h_runs', 'v_runs',
                'rsum', 'csum', 'rcross', 'r2', 'c2', 'diag_p', 'diag_m']


# ---------------------------------------------------------------------------
def analyze(puzzle, with_sufficiency=True):
    m, n, step = parse_puzzle(puzzle)
    K = m * n
    print('=' * 66)
    print(f'[{puzzle}] K={K} step={step}')

    table, path, complete = load_table(puzzle)
    B = set(table.keys())
    print(f'  表 B = {len(B):,}  ({path})')

    # 反例
    res = verify(puzzle)
    extra = res.get('example_keys') if res else None
    if extra is None:
        print('  无完整反例数据（表不完整或 A==B），跳过')
        return
    counter_shapes = [frozenset(tc.int_to_coords(h, K)) for h in extra]
    print(f'  反例数 = {len(extra)}')

    # 1. 目标帧可达集
    R = reachable_rooted(m, n, step)
    print(f'  目标帧可达根状态 |R| = {len(R)}')

    # 2. R 上特征值域：一阶（单特征）+ 二阶（特征对联合值域）
    R_feats = [features(s, step) for s in R]
    R_vals = {k: {f[k] for f in R_feats} for k in FEATURE_KEYS}
    R_pairs = {}
    for i, k1 in enumerate(FEATURE_KEYS):
        for k2 in FEATURE_KEYS[i + 1:]:
            R_pairs[(k1, k2)] = {(f[k1], f[k2]) for f in R_feats}
    constants = sorted(k for k, v in R_vals.items() if len(v) == 1)
    print(f'  R 上恒定的特征（经典不变量）: {constants}')
    ranges = ', '.join(
        f'{k}∈{sorted(R_vals[k])[:6]}{"..." if len(R_vals[k]) > 6 else ""}'
        for k in ('H', 'W', 'bbox_area', 'perimeter') if k in R_vals)
    print(f'  R 值域: {ranges}')

    phases = [(a, b) for a in range(step) for b in range(step)]

    def in_domain(f):
        if any(f[k] not in R_vals[k] for k in FEATURE_KEYS):
            return False
        for (k1, k2), dom in R_pairs.items():
            if (f[k1], f[k2]) not in dom:
                return False
        return True

    def solo_excluders(feats_list):
        """能单独排除该形状（所有呈现都出界）的一阶/二阶特征。"""
        out = []
        for k in FEATURE_KEYS:
            if all(f[k] not in R_vals[k] for f in feats_list):
                out.append(k)
        for (k1, k2), dom in R_pairs.items():
            if all((f[k1], f[k2]) not in dom for f in feats_list):
                out.append(f'{k1}+{k2}')
        return out

    # 3. 分离检验：反例的全部 D4 像 × 相位呈现
    passing = []
    for i, shape in enumerate(counter_shapes, 1):
        # 形状级排除须对全部 D4 像成立（规范形相同 ⟹ 旋转/翻转同样不可达）
        presentations = []
        for v in tc._variants(shape):
            bb = frozenset(bbox_normalize(v))
            for pr, pc in phases:
                presentations.append(frozenset((r + pr, c + pc) for r, c in bb))
        feats_list = [features(p, step) for p in presentations]
        alive = [j for j, f in enumerate(feats_list) if in_domain(f)]
        solo = solo_excluders(feats_list)
        bb0 = frozenset(bbox_normalize(shape))
        tag = '✗ 全相位/D4 像被排除' if not alive else f'仍有呈现通过 {len(alive)} 个'
        passing.append(bool(alive))
        print(f'  反例 {i}: {tag}   外接盒 '
              f'{max(r for r, _ in bb0) + 1}×{max(c for _, c in bb0) + 1}'
              f'   排除力特征: {solo[:6]}{"..." if len(solo) > 6 else ""}')

    # step=1 直线特例：出度
    if step == 1:
        for i, shape in enumerate(counter_shapes, 1):
            cells = set(shape)
            rows = [r for r, _ in cells]
            cols = [c for _, c in cells]
            deg = 0
            for L in range(min(rows), max(rows)):
                for side in ('above', 'below'):
                    for comp in tc._side_components(cells, 'h', L, side):
                        for sign in (-1, 1):
                            if _try_move(cells, comp, (0, sign), 1, K) is not None:
                                deg += 1
            for L in range(min(cols), max(cols)):
                for side in ('left', 'right'):
                    for comp in tc._side_components(cells, 'v', L, side):
                        for sign in (-1, 1):
                            if _try_move(cells, comp, (sign, 0), 1, K) is not None:
                                deg += 1
            print(f'  反例 {i}（直线）出度 = {deg}'
                  f'{"（孤立点：任何移动都违规）" if deg == 0 else " ⚠"}')

    # 4. 充分性检验
    if with_sufficiency and complete:
        targets, arrays = target_variants(m, n, step)
        all_shapes = set()

        def on_state(cells):
            all_shapes.add(tc.canonicalize(cells))

        enumerate_states(K, None, step, on_state, progress_every=0)
        print(f'  枚举全部单连通形状（平移规范）= {len(all_shapes):,}')

        # 预计算每个形状全部 D4 像 × 相位呈现的特征（去重）
        pres = {}
        for s in all_shapes:
            cells = tc.int_to_coords(s, K)
            seen_pres = set()
            lst = []
            for v in tc._variants(cells):
                bb = frozenset(bbox_normalize(v))
                for pr, pc in phases:
                    rooted = frozenset((r + pr, c + pc) for r, c in bb)
                    if rooted in seen_pres:
                        continue
                    seen_pres.add(rooted)
                    lst.append(features(rooted, step))
            pres[s] = lst

        def filter_keys(keys):
            """用给定特征集（一阶+二阶值域）过滤全部形状。"""
            vals = {k: {f[k] for f in R_feats} for k in keys}
            kpairs = [(k1, k2) for i, k1 in enumerate(keys) for k2 in keys[i + 1:]]
            prs = {(k1, k2): {(f[k1], f[k2]) for f in R_feats} for k1, k2 in kpairs}
            kept = set()
            for s, lst in pres.items():
                for f in lst:
                    if (all(f[k] in vals[k] for k in keys)
                            and all((f[a], f[b]) in prs[(a, b)] for a, b in kpairs)):
                        kept.add(s)
                        break
            return kept

        kept = filter_keys(FEATURE_KEYS)
        print(f'  值域过滤后保留 = {len(kept):,}   (B = {len(B):,})')
        extra_kept = kept - B
        missed = B - kept
        print(f'  过滤集 − B = {len(extra_kept):,}   B − 过滤集 = {len(missed):,}')
        if not extra_kept and not missed:
            print('  ★ 过滤集 == B：该特征值域构成该尺寸的充要先验判定！')
            # 贪心最小化：逐个尝试移除特征，保持过滤集 == B
            active = list(FEATURE_KEYS)
            changed = True
            while changed:
                changed = False
                for k in list(active):
                    trial = [x for x in active if x != k]
                    if filter_keys(trial) == B:
                        active = trial
                        changed = True
                        break
            print(f'  一阶最小特征子集（{len(active)} 个）: {active}')
        elif extra_kept:
            print('  过滤后仍有不可解形状（特征组非充分），样例:')
            for h in sorted(extra_kept)[:3]:
                print(render(tc.int_to_coords(h, K)))
        if missed:
            print('  ⚠ sanity 失败：有可解形状落在值域外（特征组找错了）')

    all_excluded = not any(passing)
    print(f'  结论: {"全部反例被值域条件排除 ✓" if all_excluded else "存在未被排除的反例 ✗"}')
    return constants, R_vals


def main():
    ap = argparse.ArgumentParser(description='反例第二不变量搜索')
    ap.add_argument('puzzles', nargs='+')
    ap.add_argument('--no-sufficiency', action='store_true',
                    help='跳过充分性检验（枚举全部形状）')
    args = ap.parse_args()
    for p in args.puzzles:
        analyze(p, with_sufficiency=not args.no_sufficiency)
        print()


if __name__ == '__main__':
    main()
