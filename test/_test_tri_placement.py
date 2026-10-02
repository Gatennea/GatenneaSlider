# -*- coding: utf-8 -*-
r"""tri 最佳放置 / 目标框回归（M0 第一步，計劃 §4）。

铁律（《術語規定》§4）：调试面板画框与求解器共用同一结果，所以
`tri_placement.best_placement` 必须是纯逻辑、可单测，GUI 与求解器都调它。

覆盖：
  T1  还原态 score=1.0 且与 is_solved 口径一致（計画 §5 的验收条件）
  T2  **只有 1 个朝向**（修正計劃原「3 个旋转朝向」的说法）——穷举仿射对称，
      断言 goal 上不存在 120° 旋转、只存在恒等与转置
  T3  放置偏移必是 step 倍数（mod 约束是合法性判据，非经验性过滤）
  T4  mod 不变量在引擎真实滑动下守恒（放置约束的根据）
  T5  任意几何平移下不守恒（所以枚举必须按 mod 网格过滤）
  T6  偏移域覆盖：最优放置不会被枚举范围漏掉（拿穷举对照）
  T7  score=1.0 ⇔ is_solved（口径一致）
  T8  退化输入不崩（空集 / 单块 / step=1）

运行：D:\python\python.exe test\_test_tri_placement.py
"""

import itertools
import os
import random
import sys

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


def t1_solved_state():
    print('\n--- T1 还原态 score=1.0 ---')
    from game_triangle import TriangleSliderMatrix
    from solver.ml.tri_placement import best_placement, goal_shape
    for k in (2, 3, 4, 5, 6):
        g = TriangleSliderMatrix(k)
        best = best_placement(g.positions(), k, 1)
        check(f'T1a k={k} 还原态 score=1.0', best.score == 1.0,
              f'score={best.score:.3f} offset={best.offset}')
        check(f'T1b k={k} 重叠 = k²', best.overlap == k * k,
              f'{best.overlap} vs {k * k}')
        check(f'T1c k={k} is_solved 與 score 一致',
              g.is_solved() == (best.score == 1.0))


def t2_only_one_orientation():
    print('\n--- T2 只有 1 个朝向（无 120° 旋转对称）---')
    from game_triangle import TriangleSliderMatrix
    from solver.ml.tri_placement import goal_shape
    for k in (2, 3, 4, 5):
        goal = goal_shape(k)
        syms = []
        # 穷举仿射对称：线性部分 |det|=1（只取旋转/反射，不含缩放）
        for a, b, c, d in itertools.product((-1, 0, 1), repeat=4):
            if abs(a * d - b * c) != 1:
                continue
            for ti, tj in itertools.product(range(-k, k + 1), repeat=2):
                if all(((i * a + j * b + ti), (i * c + j * d + tj), u) in goal
                       for (i, j, u) in goal):
                    syms.append(((a, b, c, d), (ti, tj)))
        # 恒等与转置 (i,j)->(j,i) 各一个
        check(f'T2a k={k} 对称数 = 2（恒等 + 转置）', len(syms) == 2,
              f'实际 {len(syms)}: {syms}')
        # 关键：没有 120° 旋转。120° 旋转的线性部分在斜坐标下应是
        # [[0,-1],[1,-1]] 之类的 3 阶循环矩阵，这里直接断言「对称里没有
        # 线性部分不是恒等/转置的项」——本测试的实质是「对称群很小」。
        lin = {s[0] for s in syms}
        check(f'T2b k={k} 无 120° 旋转（对称群不含三阶循环）', len(lin) == 2,
              f'线性部分 {sorted(lin)}')
    # 几何侧独立验证：绕重心转 120° 后顶点集合不同
    import math
    from game_triangle import tri_vertices
    goal = goal_shape(3)
    allv = set()
    for c in goal:
        allv |= set(tri_vertices(*c))
    cx = sum(p[0] for p in allv) / len(allv)
    cy = sum(p[1] for p in allv) / len(allv)
    ca, sa = math.cos(math.radians(120)), math.sin(math.radians(120))
    rot = {(round(cx + (p[0] - cx) * ca - (p[1] - cy) * sa, 6),
            round(cy + (p[0] - cx) * sa + (p[1] - cy) * ca, 6))
           for p in allv}
    check('T2c 几何验证：120° 旋转后顶点集合改变', rot != allv,
          f'原 {len(allv)} 点，旋转后 {len(rot)} 点')


def t3_offset_multiple_of_step():
    print('\n--- T3 放置偏移必是 step 倍数（合法性判据）---')
    from game_triangle import TriangleSliderMatrix, GAP_DIRECTIONS
    from solver.ml.tri_placement import best_placement, placement_offset_ok
    # 3-1 判据函数本身
    for step in (1, 2, 3, 4):
        ok_zero = placement_offset_ok((0, 0), step)
        check(f'T3a step={step} (0,0) 合法', ok_zero)
    check('T3b step=2 下 (1,0) 非法', not placement_offset_ok((1, 0), 2))
    check('T3c step=2 下 (0,1) 非法', not placement_offset_ok((0, 1), 2))
    check('T3d step=2 下 (2,0) 合法', placement_offset_ok((2, 0), 2))
    check('T3e step=1 全部合法（退化无约束）',
          all(placement_offset_ok(o, 1) for o in
              ((0, 0), (1, 1), (-3, 5))))
    # 3-2 打乱后的最优放置，偏移必是 step 倍数
    random.seed(3)
    for k, step in ((3, 2), (4, 2), (4, 3), (5, 2)):
        g = TriangleSliderMatrix(k)
        g.shuffle(15, step)
        best = best_placement(g.positions(), k, step)
        check(f'T3f k={k} step={step} 打乱后最优偏移合法',
              placement_offset_ok(best.offset, step),
              f'offset={best.offset}')


def t4_mod_conserved_by_moves():
    print('\n--- T4 mod 不变量在引擎滑动下守恒（放置约束的根据）---')
    from game_triangle import TriangleSliderMatrix, GAP_DIRECTIONS
    from gui.cell_class import cell_class
    from collections import Counter
    random.seed(3)
    total_steps = 0
    total_bad = 0
    for k in (3, 4, 5):
        for step in (1, 2, 3):
            if step > k:
                continue
            g = TriangleSliderMatrix(k)
            g.shuffle(15, step)
            before = Counter(
                cell_class((b.location[0], b.location[1]), step, 'triangle')
                + (b.location[2],) for b in g.blocks)
            for _ in range(120):
                gaps = g.all_gaps()
                if not gaps:
                    break
                fam, line = random.choice(gaps)
                g.opt(fam, line, random.choice(g.blocks))
                d = random.choice(GAP_DIRECTIONS[fam])
                pos, _ = g.try_move_ex(d, step)
                if not pos:
                    continue
                g.commit_move(pos)
                g.update_matrix()
                after = Counter(
                    cell_class((b.location[0], b.location[1]), step, 'triangle')
                    + (b.location[2],) for b in g.blocks)
                total_steps += 1
                if after != before:
                    total_bad += 1
                before = after
    check('T4a 引擎滑动 mod 守恒（零反例）', total_bad == 0,
          f'{total_steps} 步，变化 {total_bad} 次')
    check('T4b 样本量足够', total_steps > 100, f'{total_steps} 步')


def t5_not_conserved_by_geometry():
    print('\n--- T5 任意几何平移下不守恒（所以枚举要按 mod 过滤）---')
    from gui.cell_class import cell_class
    from solver.ml.tri_placement import goal_shape
    from collections import Counter
    found_non_multiple = False
    for k in (3, 4):
        goal = goal_shape(k)
        for step in (2, 3):
            if step > k:
                continue
            c0 = Counter(cell_class((i, j), step, 'triangle')
                         for (i, j, _u) in goal)
            for di, dj in ((1, 0), (0, 1), (1, 1), (1, -1)):
                sh = {(i + di, j + dj, u) for (i, j, u) in goal}
                c1 = Counter(cell_class((i, j), step, 'triangle')
                             for (i, j, _u) in sh)
                if c0 != c1:
                    found_non_multiple = True
    check('T5a 非 step 倍数平移确实会翻类计数', found_non_multiple,
          '→ 故 mod 网格过滤是合法性判据')


def t6_offset_domain_complete():
    print('\n--- T6 偏移域覆盖：最优放置不被漏掉 ---')
    from game_triangle import TriangleSliderMatrix
    from solver.ml import tri_placement as TP
    random.seed(11)
    for k, step in ((3, 2), (4, 2), (4, 1)):
        g = TriangleSliderMatrix(k)
        g.shuffle(12, step)
        cells = frozenset(g.positions())
        best = TP.best_placement(cells, k, step)
        # 暴力：全范围枚举（不受 _offset_domain 限制），只保留合法偏移
        is_ = [i for i, _j, _u in cells]
        js = [j for _i, j, _u in cells]
        lo_i, hi_i = min(is_), max(is_)
        lo_j, hi_j = min(js), max(js)
        goal = TP.goal_shape(k)
        brute = 0
        for di in range(lo_i - 2 * k, hi_i + 2 * k + 1):
            for dj in range(lo_j - 2 * k, hi_j + 2 * k + 1):
                if not TP.placement_offset_ok((di, dj), step):
                    continue
                shape = {(i + di, j + dj, u) for (i, j, u) in goal}
                brute = max(brute, len(cells & frozenset(shape)))
        check(f'T6a k={k} step={step} 偏移域内最优 == 暴力最优',
              best.overlap == brute, f'{best.overlap} vs {brute}')


def t7_score_matches_is_solved():
    print('\n--- T7 score=1.0 ⇔ is_solved ---')
    from game_triangle import TriangleSliderMatrix, GAP_DIRECTIONS
    from solver.ml.tri_placement import best_placement
    random.seed(5)
    agree = total = 0
    for k, step in ((3, 1), (3, 2), (4, 2), (4, 3)):
        g = TriangleSliderMatrix(k)
        g.shuffle(10, step)
        for _ in range(30):
            best = best_placement(g.positions(), k, step)
            total += 1
            if (best.score == 1.0) == g.is_solved():
                agree += 1
    check('T7a score=1.0 与 is_solved 全量一致', agree == total,
          f'{agree}/{total} 一致')


def t8_degenerate_inputs():
    print('\n--- T8 退化输入不崩 ---')
    from game_triangle import TriangleSliderMatrix
    from solver.ml.tri_placement import best_placement
    # 空集
    b = best_placement(set(), 3, 2)
    check('T8a 空集不崩', b is not None and b.overlap == 0,
          f'offset={b.offset} overlap={b.overlap}')
    # 单块
    b = best_placement({(0, 0, True)}, 3, 2)
    check('T8b 单块不崩', b is not None, f'offset={b.offset} overlap={b.overlap}')
    # step=1
    g = TriangleSliderMatrix(3)
    b = best_placement(g.positions(), 3, 1)
    check('T8c step=1 不崩', b.score == 1.0, f'score={b.score:.3f}')
    # 远处坐标
    b = best_placement({(50, 50, True), (51, 51, True)}, 3, 2)
    check('T8d 远处坐标不崩', b is not None, f'offset={b.offset}')
    # 重复坐标（不该崩，重叠数按集合算）
    b = best_placement([(0, 0, True), (0, 0, True)], 3, 2)
    check('T8e 重复坐标不崩', b is not None)


def main():
    print('=' * 68)
    print('tri 最佳放置 / 目标框回归（M0 第一步）')
    print('=' * 68)
    t1_solved_state()
    t2_only_one_orientation()
    t3_offset_multiple_of_step()
    t4_mod_conserved_by_moves()
    t5_not_conserved_by_geometry()
    t6_offset_domain_complete()
    t7_score_matches_is_solved()
    t8_degenerate_inputs()
    print('\n' + '=' * 68)
    if _failures:
        print(f'FAIL {len(_failures)}:')
        for f in _failures:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
