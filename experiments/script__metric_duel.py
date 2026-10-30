# -*- coding: utf-8 -*-
"""度量对决：σ（现有重叠率） vs Φ（行列剖面 L1，无窗口）。

背景：已验证 H 移动保行计数向量、V 移动保列计数向量，且
「行剖面均匀 ∧ 列剖面均匀 ∧ 连通」是还原的完备判定（见
experiments/script__prof_invariant.py）。若成立，则目标度量可以**完全不要窗口枚举**
（实测占端到端 41% 的 find_best_window + _overlap_at）。

但「理论省得快」不等于「引导得好」。本脚本用 4×4/step2 的**精确距离表**
当裁判，回答：
  Q1 全局：哪个度量与真实距离更相关（Spearman）？
  Q2 局部：按该度量选最优后继，命中「距离减 1」的比例（直接决定贪心成败）？
  Q3 平台：有多少局面所有后继的度量值都与父节点相同（梯度消失 →
     只能靠 patience/DFS 兜底）？平台率越低越好。

用法：
    D:/python/python.exe -u experiments/script__metric_duel.py > experiments/_metric_duel_out.txt 2>&1
"""
import math
import os
import pickle
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import build_game                       # noqa: E402
from solver.actions import enumerate_valid_actions, apply_action  # noqa: E402
from solver.table_core import canonicalize, int_to_coords         # noqa: E402
from solver.ml.gather_solver import max_overlap                   # noqa: E402

M = N = 4
STEP = 2
TOTAL = M * N


# ---------------------------------------------------------------- 度量定义
def _sorted_ext(counts, target_len):
    v = sorted(counts, reverse=True)
    return v + [0] * max(0, target_len - len(v))


def profile_defect(coords, m, n):
    """行列剖面缺陷 Φ：越小越接近还原（0 = 已还原）。含转置取优。"""
    rows, cols = {}, {}
    for r, c in coords:
        rows[r] = rows.get(r, 0) + 1
        cols[c] = cols.get(c, 0) + 1

    def defect(row_vals, n_rows, per_row, col_vals, n_cols, per_col):
        R = _sorted_ext(list(row_vals), n_rows)
        C = _sorted_ext(list(col_vals), n_cols)
        dr = sum(abs(R[i] - per_row) for i in range(n_rows))
        dr += sum(R[n_rows:])
        dc = sum(abs(C[i] - per_col) for i in range(n_cols))
        dc += sum(C[n_cols:])
        return dr + dc

    if m == n:
        return defect(list(rows.values()), m, n, list(cols.values()), n, m)
    a = defect(list(rows.values()), m, n, list(cols.values()), n, m)
    b = defect(list(rows.values()), n, m, list(cols.values()), m, n)
    return min(a, b)


def sigma(coords):
    return max_overlap(coords, M, N) / TOTAL


# ---------------------------------------------------------------- 统计
def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx and dy else 0.0


def load_data_dir():
    return os.path.join(_ROOT, 'solver', 'data', '%d_%d_%d' % (M, N, STEP))


def load_table():
    for fn in ('table.pkl', 'checkpoint.pkl'):
        p = os.path.join(load_data_dir(), fn)
        if os.path.exists(p):
            with open(p, 'rb') as f:
                data = pickle.load(f)
            return data if fn == 'table.pkl' else data['dist']
    raise SystemExit('无距离表')


def main():
    tbl = load_table()
    print('距离表载入：%d 个规范状态' % len(tbl))
    keys = list(tbl.keys())
    rnd = random.Random(20261010)

    # 按距离分层抽样，保证样本覆盖不同深度
    by_d = {}
    for k in keys:
        d = tbl[k]
        by_d.setdefault(d, []).append(k)
    print('距离分布（前若干层）：' +
          ', '.join('d=%d:%d' % (d, len(by_d[d])) for d in sorted(by_d)[:20]))

    sample = []
    for d, ks in by_d.items():
        if d == 0:
            continue
        take = min(120, len(ks))
        sample.extend(rnd.sample(ks, take))
    print('抽样状态数：%d' % len(sample))

    pairs_sig, pairs_phi, pairs_d = [], [], []
    hit_sig = hit_phi = tot_n = 0
    plat_sig = plat_phi = plat_tot = 0

    for h0 in sample:
        d0 = tbl[h0]
        if d0 is None or d0 <= 0:
            continue
        cs0 = int_to_coords(h0, TOTAL)
        if not cs0:
            continue
        pairs_sig.append(sigma(cs0))
        pairs_phi.append(profile_defect(cs0, M, N))
        pairs_d.append(d0)

        s0, p0 = pairs_sig[-1], pairs_phi[-1]
        g = build_game(cs0, M, N)
        succ = []
        for a in enumerate_valid_actions(g, STEP):
            g2 = build_game(cs0, M, N)
            if not apply_action(g2, a, STEP):
                continue
            cs2 = frozenset((b.location[0], b.location[1]) for b in g2.blocks)
            if len(cs2) != TOTAL:
                continue
            d2 = tbl.get(canonicalize(cs2))
            if d2 is None:
                continue
            succ.append((sigma(cs2), profile_defect(cs2, M, N), d2))
        if not succ:
            continue
        tot_n += 1

        # Q3 平台：所有后继度量值都与父相同
        if all(abs(s - s0) < 1e-9 for s, _p, _d in succ):
            plat_sig += 1
        if all(abs(p - p0) < 1e-9 for _s, p, _d in succ):
            plat_phi += 1
        plat_tot += 1

        # Q2 最优后继是否真的让距离 -1
        best_phi = min(succ, key=lambda t: t[1])
        best_sig = max(succ, key=lambda t: t[0])
        if best_sig[2] == d0 - 1:
            hit_sig += 1
        if best_phi[2] == d0 - 1:
            hit_phi += 1

    print('\n=== Q1 全局相关性（Spearman，|ρ| 越大越好）===')
    rs = spearman(pairs_sig, pairs_d)
    rp = spearman(pairs_phi, pairs_d)
    print('  σ  vs 距离 : ρ = %+.4f' % rs)
    print('  Φ  vs 距离 : ρ = %+.4f' % rp)
    print('  胜者：%s' % ('Φ' if abs(rp) > abs(rs) else 'σ'))

    print('\n=== Q2 最优后继命中「距离-1」的比例（决定贪心成败）===')
    print('  σ : %d/%d = %.1f%%' % (hit_sig, tot_n, 100.0 * hit_sig / max(1, tot_n)))
    print('  Φ : %d/%d = %.1f%%' % (hit_phi, tot_n, 100.0 * hit_phi / max(1, tot_n)))
    print('  胜者：%s' % ('Φ' if hit_phi > hit_sig else 'σ'))

    print('\n=== Q3 平台率（所有后继度量同值，越低越好）===')
    print('  σ : %d/%d = %.1f%%' % (plat_sig, plat_tot, 100.0 * plat_sig / max(1, plat_tot)))
    print('  Φ : %d/%d = %.1f%%' % (plat_phi, plat_tot, 100.0 * plat_phi / max(1, plat_tot)))
    print('  胜者：%s' % ('Φ' if plat_phi < plat_sig else 'σ'))


if __name__ == '__main__':
    main()
