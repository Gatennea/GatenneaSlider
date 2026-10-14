# -*- coding: utf-8 -*-
r"""三角聚拢求解器回归（M1）。

验收纪律（計劃 §8 M1）：
  ①随机打乱 N 盘批量报告复原率/时间/步数；
  ②score=1.0 与 is_solved 全量对齐；
  ③重放验证全过；
  ④**先跑方形回归确认共享骨架无误伤**（鐵律：对照实验先跑方形）。

另外锁住三条容易退化的机制：
  A5 元组动作不带「事后猜代表」——同缝两侧多分量时 rep 必须唯一确定；
  A `_components` 与引擎 `opt` 的 DFS 判据必须一致（否则动作静默变样）；
  C 共享骨架的 `canonicalize` 不能省（平移归一化，去环的前提）。

运行：
    D:\python\python.exe -u test\_test_tri_gather.py
"""

import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_triangle import (  # noqa: E402
    GAP_DIRECTIONS, TriangleSliderMatrix, gap_rank, neighbors, side_of,
)
from solver.ml import tri_adapter as TA  # noqa: E402
from solver.ml.shape_gather import ShapeGather  # noqa: E402
from solver.ml.tri_placement import best_placement  # noqa: E402

_F = []


def check(name, cond, extra=''):
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{tag}] {name}' + (f'  {extra}' if extra else ''))
    if not cond:
        _F.append(name)


def _solver():
    return ShapeGather(TA.shape_score, TA.enumerate_actions, TA.apply_action,
                       TA.snap, TA.restore, TA.tri_coords)


# ---------------------------------------------------------------------------
def a1_actions_are_5tuple():
    print('\n--- A1 动作是 5 元组且每侧每个分量各一个 ---')
    random.seed(3)
    g = TriangleSliderMatrix(4)
    g.shuffle(15, 2)
    acts = TA.enumerate_actions(g, 2)
    check('A1a 全部动作长度 5', all(len(a) == 5 for a in acts),
          f'{len(acts)} 个动作')
    check('A1b (族,线,侧,向) 取值合法',
          all(a[0] in GAP_DIRECTIONS
              and a[3] in GAP_DIRECTIONS[a[0]]
              and a[2] in (0, 1)
              for a in acts))
    # 同 (族,线,侧,向) 下若有多分量 → rep 必须不同（否则两个分量被吞成一个）
    from collections import Counter
    grp = Counter((a[0], a[1], a[2], a[3]) for a in acts)
    dup = [k for k, v in grp.items() if v > 1]
    check('A1c 同一 (族,线,侧,向) 多动作必是不同 rep',
          all(len({a[4] for a in acts
                   if (a[0], a[1], a[2], a[3]) == k}) == v
              for k, v in grp.items()),
          f'有 {len(dup)} 组含多动作')
    # rep 必须真在该侧
    bad = []
    for a in acts:
        if side_of(a[0], a[1], a[4]) != a[2]:
            bad.append(a)
    check('A1d rep_key 真在指定侧', not bad, f'{len(bad)} 个越侧')


def a2_components_match_opt():
    print('\n--- A2 _components 与引擎 opt 同判据（动作不静默变样）---')
    from game_triangle import tri_key
    random.seed(7)
    g = TriangleSliderMatrix(4)
    g.shuffle(15, 2)
    total = 0
    mismatch = 0
    for (fam, line) in g.all_gaps():
        cells = g.positions()
        for side in (0, 1):
            sc = {c for c in cells if side_of(fam, line, c) == side}
            if not sc:
                continue
            for rep in TA._components(g, fam, line, sc):
                g._clear_selection()
                g.opt(fam, line, g.block_at(rep))
                n_opt = sum(1 for b in g.blocks if b.be_opted)
                comp = {rep}
                stack = [rep]
                while stack:
                    cur = stack.pop()
                    for nb in neighbors(cur):
                        if nb in sc and nb not in comp:
                            comp.add(nb)
                            stack.append(nb)
                total += 1
                if n_opt != len(comp):
                    mismatch += 1
    check('A2a opt 选中块数 == 组件大小', mismatch == 0,
          f'比对 {total} 组，不一致 {mismatch}')


def a3_apply_no_rewrite():
    print('\n--- A3 apply_action 不静默改写（位移/朝向逐块核对）---')
    exp = {
        'h': lambda d, st: (st, 0) if d == 'a' else (-st, 0),
        'p': lambda d, st: (0, st) if d == 'e' else (0, -st),
        'n': lambda d, st: (-st, st) if d == 'w' else (st, -st),
    }
    random.seed(3)
    g = TriangleSliderMatrix(4)
    g.shuffle(15, 2)
    ok = 0
    bad = []
    for a in TA.enumerate_actions(g, 2):
        s = TA.snap(g)
        fam, line, side, d, rep = a
        g._clear_selection()
        g.opt(fam, line, g.block_at(rep))
        selblocks = [b for b in g.blocks if b.be_opted]
        pos, reason = g.try_move_ex(d, 2)
        if pos:
            want = exp[fam](d, 2)
            good = len(pos) == len(selblocks)
            if good:
                for b, p in zip(selblocks, pos):
                    if (p[0] - b.location[0], p[1] - b.location[1]) != want \
                            or p[2] != b.location[2]:
                        good = False
                        break
            if good:
                ok += 1
            else:
                bad.append(a)
            g.commit_move(pos)
        TA.restore(g, s)
    check('A3a 每个可执行动作的位移/朝向与 (族,向,step) 精确一致',
          not bad, f'一致 {ok}，异常 {len(bad)}')


def a4_side_reject():
    print('\n--- A4 side 与 rep 不符时拒绝执行（不静默改写成别的动作）---')
    random.seed(5)
    g = TriangleSliderMatrix(4)
    g.shuffle(15, 2)
    acts = TA.enumerate_actions(g, 2)
    wrong = [a for a in acts if side_of(a[0], a[1], a[4]) != a[2]]
    if not wrong:
        print('     （本局面没有可测的越侧动作，跳过）')
    n_reject = 0
    for a in wrong:
        s = TA.snap(g)
        before = TA.tri_coords(g)
        ok = TA.apply_action(g, a, 2)
        if not ok and TA.tri_coords(g) == before:
            n_reject += 1
        TA.restore(g, s)
    check('A4a 越侧动作被拒且局面不变', n_reject == len(wrong),
          f'{n_reject}/{len(wrong)}')


# ---------------------------------------------------------------------------
def c1_score_matches_is_solved():
    print('\n--- C1 score=1.0 ⇔ is_solved 全量对齐（M1 验收 ②）---')
    sg = _solver()
    tot = 0
    mis = 0
    for k, step in ((3, 1), (3, 2), (4, 2), (5, 2)):
        spec = TA.TriSpec(k, step)
        for seed in range(10):
            random.seed(seed)
            g = TriangleSliderMatrix(k)
            g.shuffle(12, step)
            for _ in range(20):
                tot += 1
                s = TA.shape_score(TA.tri_coords(g), spec)
                if (s >= 1.0 - 1e-9) != g.is_solved():
                    mis += 1
                acts = sg.enumerate_actions(g, step)
                if not acts:
                    break
                random.shuffle(acts)
                if not sg.apply_action(g, acts[0], step):
                    sg.restore(g, sg.snap(g))
    check('C1a score 与 is_solved 口径一致', mis == 0,
          f'比对 {tot} 个局面，不一致 {mis}')


def c2_replay_all():
    print('\n--- C2 真盘重放验证（M1 验收 ③ / 計劃 §3 终裁原则）---')
    sg = _solver()
    tot = 0
    bad = 0
    for k, step, n, shuf in ((3, 1, 5, 60), (4, 2, 7, 120), (5, 2, 4, 200)):
        spec = TA.TriSpec(k, step)
        for seed in range(n):
            random.seed(seed)
            g = TriangleSliderMatrix(k)
            g.shuffle(shuf, step)
            init = sg.snap(g)
            res = sg.solve(g, spec, step, max_steps=400, patience=150,
                           max_wait_time=20)
            end = sorted(TA.tri_coords(g))
            g2 = TriangleSliderMatrix(k)
            sg.restore(g2, init)
            ok = True
            for a in res['actions']:
                if not sg.apply_action(g2, a, step):
                    ok = False
                    break
            tot += 1
            if not (ok and sorted(TA.tri_coords(g2)) == end
                    and g2.is_solved() == res['solved']):
                bad += 1
    check('C2a 动作序列在独立真盘上重放到底态一致', bad == 0,
          f'{tot - bad}/{tot} 通过')


def c3_batch_report():
    print('\n--- C3 批量报告（時間 > 步數；計劃 §8 M1 验收 ①）---')
    # 打乱强度必须够：**shuffle(15, step) 对三角几乎不改变聚拢度**（k=4 打乱
    # 5/15/30/60 步，初始 score 一直是 0.75）—— 用它测出来的「复原 9/10、
    # 成功局均步 1.0」是虚的：局面本来就有 12/16 聚拢，一步就能补完。
    # 实测把初始 score 压到 0.7 上下才反映真实难度（对照：方形 shuffle(15)
    # 初始 score 就是 0.50~0.75，本来就比三角低）。
    sg = _solver()
    for k, step, n, shuf in ((4, 2, 10, 120), (5, 2, 8, 200)):
        spec = TA.TriSpec(k, step)
        got = 0
        init, steps, secs, scores = [], [], [], []
        t0 = time.time()
        for seed in range(n):
            random.seed(seed)
            g = TriangleSliderMatrix(k)
            g.shuffle(shuf, step)
            init.append(TA.shape_score(TA.tri_coords(g), spec))
            res = sg.solve(g, spec, step, max_steps=400, patience=150,
                           max_wait_time=25)
            got += bool(res['solved'])
            steps.append(res['steps'])
            secs.append(res['elapsed'])
            scores.append(res['score'])
        solved_steps = [x for x, s in zip(steps, scores) if s >= 1.0]
        print(f'     k={k} step={step} shuffle({shuf}): 初始score '
              f'{statistics.mean(init):.3f} → 复原 {got}/{n}  '
              f'末score {statistics.mean(scores):.3f}  '
              f'均时 {statistics.mean(secs):.2f}s  '
              f'成功局均步 {statistics.mean(solved_steps) if solved_steps else 0:.1f}'
              f'  总 {time.time() - t0:.1f}s')
        el = time.time() - t0
        check(f'C3a k={k} 批量跑完且时间在预算内', el < 200, f'{el:.1f}s')
        check(f'C3b k={k} 初始局面确实被打乱（score < 0.85）',
              statistics.mean(init) < 0.85, f'{statistics.mean(init):.3f}')
        check(f'C3c k={k} 有复原能力（基线 > 0）', got > 0, f'{got}/{n}')
        check(f'C3d k={k} 成功局步数不为 0', all(x > 0 for x in solved_steps))
        # M1 基线（2026-10-03 实测，k=4 打乱 120 步 8/10；k=5 打乱 200 步
        # 1/8 —— 大三角上贪心确实卡住，属計劃 §9 风险 1 的预期范围，
        # 兜底不在 M1 期）。锁住是为了让后续改动一旦把 k=4 打到 < 5/10
        # 就会失败，那是真回归。
        if k == 4:
            check('C3e k=4 基线未退化（>= 5/10）', got >= 5, f'{got}/{n}')


# ---------------------------------------------------------------------------
def d1_square_no_regression():
    print('\n--- D1 共享骨架对方形无误伤（鐵律：对照先跑方形）---')
    from game import SliderMatrix
    from solver.ml.gather_solver import gather_solve
    from solver.ml.shape_gather import square_gatherer
    sg = square_gatherer()
    n = 10
    same = 0
    s_orig, s_new = [], []
    for seed in range(n):
        random.seed(seed)
        g = SliderMatrix(4, 4)
        g.shuffle(30, 2)
        a = gather_solve(g, 2, max_steps=300, patience=150, max_wait_time=10)
        random.seed(seed)
        g2 = SliderMatrix(4, 4)
        g2.shuffle(30, 2)
        b = sg.solve(g2, (4, 4, 2), 2, max_steps=300, patience=150,
                     max_wait_time=10)
        s_orig.append(a['end']['score'])
        s_new.append(b['score'])
        if abs(a['end']['score'] - b['score']) < 0.02:
            same += 1
    print(f'     原骨架末score均值 {statistics.mean(s_orig):.3f} / '
          f'共享 {statistics.mean(s_new):.3f}')
    check('D1a 共享骨架在方形上末 score 与原骨架相当（不劣化）',
          statistics.mean(s_new) >= statistics.mean(s_orig) - 0.02,
          f'{statistics.mean(s_new):.3f} vs {statistics.mean(s_orig):.3f}')
    check('D1b 逐盘一致率过半', same >= n // 2, f'{same}/{n}')


def d2_canonicalize_required():
    print('\n--- D2 canonicalize 缺失会降质（锁住这个依赖）---')
    from game import SliderMatrix
    from solver.state import snapshot, restore
    from solver.actions import enumerate_valid_actions, apply_action
    from solver.ml.gather_solver import gather_metrics
    from solver.table_core import canonicalize

    def coords_of(g):
        return frozenset((b.location[0], b.location[1]) for b in g.blocks)

    def score(c, sp):
        return gather_metrics(c, sp[0], sp[1])['score']

    with_c = ShapeGather(score, enumerate_valid_actions, apply_action,
                         snapshot, restore, coords_of,
                         canonicalize=canonicalize)
    without = ShapeGather(score, enumerate_valid_actions, apply_action,
                          snapshot, restore, coords_of)
    n = 8
    a, b = [], []
    for seed in range(n):
        random.seed(seed)
        g = SliderMatrix(4, 4)
        g.shuffle(30, 2)
        a.append(with_c.solve(g, (4, 4, 2), 2, max_steps=250, patience=120,
                              max_wait_time=10)['score'])
        random.seed(seed)
        g2 = SliderMatrix(4, 4)
        g2.shuffle(30, 2)
        b.append(without.solve(g2, (4, 4, 2), 2, max_steps=250, patience=120,
                               max_wait_time=10)['score'])
    print(f'     有 canonicalize {statistics.mean(a):.3f} / '
          f'无 {statistics.mean(b):.3f}')
    check('D2a 有 canonicalize 不劣于无', statistics.mean(a) >=
          statistics.mean(b) - 0.02)


def main():
    print('=' * 68)
    print('三角聚拢求解器回归（M1）')
    print('=' * 68)
    a1_actions_are_5tuple()
    a2_components_match_opt()
    a3_apply_no_rewrite()
    a4_side_reject()
    c1_score_matches_is_solved()
    c2_replay_all()
    c3_batch_report()
    d1_square_no_regression()
    d2_canonicalize_required()
    print('\n' + '=' * 68)
    if _F:
        print(f'FAIL {len(_F)}:')
        for f in _F:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()