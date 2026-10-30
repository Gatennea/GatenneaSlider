# -*- coding: utf-8 -*-
"""验证「旁观者 AI」提出的不变量（2026-10-10）。

主张（需实证，不信断言）：
  A. H 缝（gap_dir='h'）的移动平移 ±e_col ⟹ **行计数向量不变**；
     V 缝（gap_dir='v'）的移动平移 ±e_row ⟹ **列计数向量不变**。
  B. 完备判定：连通 ∧ 非空行数==m ∧ 每行==n ∧ 非空列数==n ∧ 每列==m
     ∧ 总数==mn  ⟺  是实心矩形（允许 n×m 转置）。
     若成立，则现有 find_best_window + _overlap_at（实测占端到端 41%）
     **不是要加速，而是可以整体省掉**。

用法：
    D:/python/python.exe -u experiments/script__prof_invariant.py > experiments/_prof_invariant_out.txt 2>&1
"""
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import build_game                    # noqa: E402
from solver.actions import enumerate_valid_actions, apply_action  # noqa: E402

FAILS = []


def check(name, cond, extra=''):
    tag = 'PASS' if cond else 'FAIL'
    print('[%s] %s%s' % (tag, name, ('  %s' % extra) if extra else ''))
    if not cond:
        FAILS.append(name)


def coords_of(game):
    return frozenset((b.location[0], b.location[1]) for b in game.blocks)


def row_counts(coords):
    d = {}
    for r, _c in coords:
        d[r] = d.get(r, 0) + 1
    return d


def col_counts(coords):
    d = {}
    for _r, c in coords:
        d[c] = d.get(c, 0) + 1
    return d


def profile_is_solved(coords, m, n):
    """主张 B 的判定：行列剖面同时均匀（含转置）。"""
    rc, cc = row_counts(coords), col_counts(coords)
    if not rc or not cc or len(coords) != m * n:
        return False
    for rows_n, each_r, cols_n, each_c in ((m, n, n, m), (n, m, m, n)):
        if (len(rc) == rows_n and all(v == each_r for v in rc.values())
                and len(cc) == cols_n and all(v == each_c for v in cc.values())):
            return True
    return False


def random_states(m, n, step, nMoves, seed, n_states=40):
    """从复原态随机游走生成合法（连通）局面。"""
    g = build_game(frozenset((r, c) for r in range(m) for c in range(n)), m, n)
    rnd = random.Random(seed)
    out = []
    seen = set()
    for i in range(nMoves):
        acts = enumerate_valid_actions(g, step)
        if not acts:
            break
        a = rnd.choice(acts)
        apply_action(g, a, step)
        if i >= nMoves // 3:                       # 跳过前段，取分散样本
            cs = coords_of(g)
            key = frozenset((r - min(x for x, _ in cs), c - min(y for _, y in cs))
                            for r, c in cs)
            if key not in seen:
                seen.add(key)
                out.append(cs)
            if len(out) >= n_states:
                break
    return out


# ---------------------------------------------------------------------------
def invariance_test():
    """主张 A：H 移动保行计数向量，V 移动保列计数向量。"""
    print('\n=== A. 移动对行列计数向量的作用 ===')
    configs = [(8, 8, 2, '06/07 同规格'), (4, 4, 2, '4x4'), (5, 5, 2, '5x5'),
               (6, 6, 2, '6x6'), (4, 6, 3, '4x6 step3')]
    for m, n, step, label in configs:
        if m * n > 64:
            continue
        states = random_states(m, n, step, 4000, seed=hash((m, n, step)) & 0xffff)
        if not states:
            print('  (%s) 无样本，跳过' % label)
            continue
        viol_h = viol_v = tested = 0
        for cs in states:
            g = build_game(cs, m, n)
            for a in enumerate_valid_actions(g, step):
                gap_dir = a[0]
                rc0, cc0 = row_counts(cs), col_counts(cs)
                g2 = build_game(cs, m, n)
                if not apply_action(g2, a, step):
                    continue
                cs2 = coords_of(g2)
                if len(cs2) != len(cs):
                    continue
                tested += 1
                if gap_dir == 'h' and row_counts(cs2) != rc0:
                    viol_h += 1
                if gap_dir == 'v' and col_counts(cs2) != cc0:
                    viol_v += 1
        print('  %-14s %dx%d step%d  样本 %d 局面 / %d 动作  →  '
              'H违反行向量 %d 次, V违反列向量 %d 次'
              % (label, m, n, step, len(states), tested, viol_h, viol_v))
        check('A/%s H保行计数' % label, viol_h == 0, 'viol=%d' % viol_h)
        check('A/%s V保列计数' % label, viol_v == 0, 'viol=%d' % viol_v)


def completeness_test():
    """主张 B：剖面均匀 ∧ 连通 ⟺ is_solved()。双向都得成立。"""
    print('\n=== B. 剖面判定 与 is_solved() 是否等价 ===')
    configs = [(4, 4, 2), (5, 5, 2), (6, 6, 2), (8, 8, 2), (4, 6, 3), (5, 7, 2)]
    tot = agree = mismatch = 0
    examples = []
    for m, n, step in configs:
        if m * n > 64:
            continue
        states = random_states(m, n, step, 9000, seed=(m * 1000 + n * 10 + step))
        # 混入“顺便抽样”的复原态自身
        solved = frozenset((r, c) for r in range(m) for c in range(n))
        states.append(solved)
        d = 0
        for cs in states:
            g = build_game(cs, m, n)
            want = g.is_solved()
            got = profile_is_solved(cs, m, n)
            tot += 1
            if want == got:
                agree += 1
            else:
                d += 1
                mismatch += 1
                if len(examples) < 5:
                    examples.append((m, n, step, sorted(cs)[:12], want, got))
        print('  %dx%d step%d: %d 局面, 不一致 %d' % (m, n, step, len(states), d))
    print('  合计 %d 局面，一致 %d，不一致 %d' % (tot, agree, mismatch))
    if examples:
        print('  不一致样例（前5）:')
        for e in examples:
            print('    %dx%d s%d want_solved=%s profile=%s coords=%s'
                  % (e[0], e[1], e[2], e[4], e[5], e[3]))
    check('B 剖面判定 ⟺ is_solved', mismatch == 0, 'mismatch=%d' % mismatch)


def main():
    print('=' * 74)
    print('不变量验证（旁观者 AI 主张）')
    print('=' * 74)
    invariance_test()
    completeness_test()
    print('\n' + '=' * 74)
    if FAILS:
        print('FAILED %d:' % len(FAILS))
        for f in FAILS:
            print('  · %s' % f)
    else:
        print('ALL PASS —— 主张 A + B 均成立')
    print('=' * 74)


if __name__ == '__main__':
    main()
