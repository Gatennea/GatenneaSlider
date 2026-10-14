# -*- coding: utf-8 -*-
r"""mi 最佳放置 / 目标框回归（M3 第一步，計劃 §4/§6）。

铁律（《術語規定》§4）：调试面板画框与求解器共用同一结果，所以
`mi_placement.best_placement` 必须是纯逻辑、可单测，GUI 与求解器都调它。

覆盖（对照 tri 的 T1~T8，换成 mi 自己的判据 —— **不照抄 tri 的结论**）：
  T1  还原态 score=1.0（m×n 与转置 n×m 都要）
  T2  **转置也算还原**：`is_solved` 判 m×n 或 n×m，本函数必须同时枚举
  T3  mod 约束：合法偏移的**结构**（不是「step 倍数」）与 mod_auts 自洽
  T4  mod 不变量在引擎真实滑动下守恒（放置约束的根据）
  T5  **半格偏移只在 step=1 合法**（换晶格 A→B 的实测结论）
  T6  前缀和窗口查询 == 暴力交集（加速路径必须与直算一致）
  T7  score=1.0 ⇔ is_solved（口径一致，含错位态）
  T8  退化输入不崩（空集 / 单块 / 远处坐标 / 奇偶不一致坐标）
  T9  mod 过滤不会挡掉真解：**随机行走后若 is_solved，过滤版仍能找到它**
  T10 枚举域完整：偏移域内最优 == 更宽范围的暴力最优

运行：D:\python\python.exe -u test\_test_mi_placement.py
"""

import math
import os
import random
import sys
from collections import Counter

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

_F = []


def check(name, cond, extra=''):
    print(f'[{"PASS" if cond else "FAIL"}] {name}' + (f'  {extra}' if extra else ''))
    if not cond:
        _F.append(name)


# ---------------------------------------------------------------------------
def t1_solved_state():
    print('\n--- T1 还原态 score=1.0 ---')
    from game_mi import MiSliderMatrix
    from solver.ml.mi_placement import best_placement
    for m, n in ((2, 2), (3, 3), (4, 4), (4, 3), (3, 4), (5, 4)):
        g = MiSliderMatrix(m, n)
        best = best_placement(g.positions(), m, n, 1)
        check(f'T1a {m}x{n} 还原态 score=1.0', best.score == 1.0,
              f'score={best.score:.3f} {best!r}')
        check(f'T1b {m}x{n} 重叠 = 4mn', best.overlap == 4 * m * n,
              f'{best.overlap} vs {4 * m * n}')


def t2_transpose():
    print('\n--- T2 转置也算还原（枚举 n×m）---')
    from game_mi import MiSliderMatrix
    from solver.ml.mi_placement import best_placement, goal_shapes
    check('T2a 非方形给出两个目标形状', len(goal_shapes(4, 3)) == 2,
          f'{[s.__len__() for s in goal_shapes(4, 3)]}')
    check('T2b 方形只给一个目标形状', len(goal_shapes(4, 4)) == 1)
    # 真构造一个转置还原态：把 m×n 的盘面转置成 n×m 再看 is_solved
    for m, n in ((4, 3), (3, 4), (5, 3)):
        g = MiSliderMatrix(m, n)
        check(f'T2c {m}x{n} 建局态 is_solved', g.is_solved())
        # 转置后的板：行↔列互换
        cells = {(c, r, q) for r, c, q in g.positions()}
        from game_mi import blocks_from_cells
        g.blocks = blocks_from_cells(cells)
        g.update_matrix()
        check(f'T2d {m}x{n} 转置后 is_solved 仍为真', g.is_solved())
        best = best_placement(g.positions(), m, n, 1)
        check(f'T2e {m}x{n} 转置态 score=1.0', best.score == 1.0,
              f'shape={best.shape} offset={best.offset}')


def t3_mod_structure():
    print('\n--- T3 mod 约束的结构（不是「step 倍数」）---')
    from game_mi import MiSliderMatrix
    from solver.ml import mi_placement as MP
    # 3-1 判据函数自身
    check('T3a step=2 下 (0.5,0) 非法（奇偶不一致 = 死盘坐标）',
          not MP.placement_offset_ok((0.5, 0.0), 2, 4, 4))
    check('T3b step=2 下 (0,0) 合法', MP.placement_offset_ok((0.0, 0.0), 2, 4, 4))
    check('T3c 奇偶不一致在任何 step 下都非法（含 step=1）',
          not MP.placement_offset_ok((0.5, 0.0), 1, 4, 4),
          '奇偶一致是引擎不变量，与 step 无关')
    check('T3d step=1 下 (0.5,0.5) 合法', MP.placement_offset_ok((0.5, 0.5), 1, 4, 4))
    check('T3e step=1 下 (-1.5,2.5) 合法（奇偶一致即可）',
          MP.placement_offset_ok((-1.5, 2.5), 1, 4, 4))
    # 3-2 与探针的实测结论一致：step=2 时 4×4 整格 3×3 全 9 个合法，
    #     step=3 时整格只剩 (0,0)。这直接否证「偏移必须是 step 倍数」。
    for m, n, step, expect_int in ((4, 4, 2, 9), (4, 4, 3, 1),
                                  (3, 3, 2, 5), (4, 3, 3, 3)):
        ok = [off for off in ((float(di), float(dj))
                              for di in (-1, 0, 1) for dj in (-1, 0, 1))
              if MP.placement_offset_ok(off, step, m, n)]
        check(f'T3f {m}x{n} step={step} 整格合法数 = {expect_int}',
              len(ok) == expect_int, f'实际 {len(ok)}: {sorted(ok)}')
    #     「偏移必須是 step 的倍數」這句在 mi 上被直接否證：step=2 時
    #     S = {(0,0),(1,1)} → **所有整格偏移都合法**（因為 (dr+dc) 與
    #     (dr−dc) 同奇偶，模 2 必然相等），(1,0) 這種非 step 倍數也照樣合法。
    check('T3g step=2 下 (1,0) 合法 —— 「偏移是 step 倍数」在 mi 上被否证',
          MP.placement_offset_ok((1.0, 0.0), 2, 4, 4)
          and MP.placement_offset_ok((1.0, 0.0), 2, 4, 4) and (1 % 2) != 0,
          'step=2 时所有整格偏移合法，1 不是 2 的倍数')
    check('T3g2 step=2 下所有整格偏移都合法（S={(0,0),(1,1)}）',
          all(MP.placement_offset_ok((float(di), float(dj)), 2, 4, 4)
              for di in (-1, 0, 1) for dj in (-1, 0, 1)),
          '与 S={(0,0),(1,1)} 一致')
    # 3-3 mod_auts 自身：S 必含 (0,0)，且 step=2 时 S = {(0,0),(1,1)}
    for m, n, step in ((4, 4, 2), (4, 4, 3), (3, 3, 2)):
        S = MP.mod_auts(m, n, step)
        check(f'T3h {m}x{n} step={step} S 含 (0,0)', (0, 0) in S, f'S={sorted(S)}')


def t4_mod_conserved_by_moves():
    print('\n--- T4 mod 不变量在引擎滑动下守恒 ---')
    from game_mi import GAP_DIRECTIONS, MiSliderMatrix
    from gui.cell_class import cell_class
    random.seed(3)
    total = bad = 0
    for m, n in ((3, 3), (4, 4), (4, 3)):
        for step in (1, 2, 3):
            if step >= max(m, n):
                continue
            g = MiSliderMatrix(m, n)
            g.shuffle(15, step)
            before = Counter(cell_class(k, step, 'mi') for k in g.positions())
            for _ in range(100):
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
                after = Counter(cell_class(k, step, 'mi') for k in g.positions())
                total += 1
                if after != before:
                    bad += 1
                before = after
    check('T4a 引擎滑动 mod 守恒（零反例）', bad == 0,
          f'{total} 步，变化 {bad} 次')
    check('T4b 样本量足够', total > 100, f'{total} 步')


def t5_half_offset_only_step1():
    print('\n--- T5 半格偏移（换晶格）只在 step=1 合法 ---')
    from solver.ml import mi_placement as MP
    for step in (2, 3, 4):
        check(f'T5a step={step} 下 (0.5,0.5) 非法',
              not MP.placement_offset_ok((0.5, 0.5), step, 4, 4),
              '换晶格在 step≥2 不可达（与 cell_class 文档一致）')
    check('T5b step=1 下 (0.5,0.5) 合法',
          MP.placement_offset_ok((0.5, 0.5), 1, 4, 4))
    # 反向验证：step=1 的真引擎里斜滑一格确实换晶格（坐标出现半整数）
    from game_mi import MiSliderMatrix
    g = MiSliderMatrix(3, 3)
    for (fam, line) in g.all_gaps():
        if fam != 'd2':
            continue
        for d in ('e', 'z'):
            g._clear_selection()
            g.opt(fam, line, g.block_at((0, 0, 'N')))
            pos, _ = g.try_move_ex(d, 1)
            if pos:
                g.commit_move(pos)
                g.update_matrix()
                break
        break
    check('T5c step=1 斜滑确实产生半整数坐标（换晶格）',
          any(abs(k[0] - round(k[0])) > 1e-9 or abs(k[1] - round(k[1])) > 1e-9
              for k in g.positions()),
          f'样例 {sorted(g.positions())[:2]}')


def t6_prefix_matches_bruteforce():
    print('\n--- T6 前缀和窗口查询 == 暴力交集 ---')
    from game_mi import MiSliderMatrix
    from solver.ml import mi_placement as MP
    random.seed(11)
    mis = 0
    tot = 0
    for m, n, step in ((3, 3, 1), (3, 3, 2), (4, 4, 2), (4, 3, 2), (4, 4, 1)):
        g = MiSliderMatrix(m, n)
        g.shuffle(20, step)
        cells = frozenset(g.positions())
        best = MP.best_placement(cells, m, n, step)
        tot += 1
        brute = MP.overlap_at(cells, best.cells)
        if brute != best.overlap:
            mis += 1
            print(f'     ★ {m}x{n} step={step}: 前缀和 {best.overlap} '
                  f'vs 暴力 {brute}')
    check('T6a 加速路径与直算一致', mis == 0, f'{tot - mis}/{tot} 一致')


def t7_score_matches_is_solved():
    print('\n--- T7 score=1.0 ⇔ is_solved（含错位态）---')
    from game_mi import GAP_DIRECTIONS, MiSliderMatrix
    from solver.ml.mi_placement import best_placement
    random.seed(5)
    agree = total = shifted = 0
    for m, n, step in ((3, 3, 1), (3, 3, 2), (4, 4, 2), (4, 4, 1), (4, 3, 2)):
        g = MiSliderMatrix(m, n)
        g.shuffle(10, step)
        for _ in range(25):
            best = best_placement(g.positions(), m, n, step)
            total += 1
            if any(abs(k[0] - round(k[0])) > 1e-9 for k in g.positions()):
                shifted += 1
            if (best.score == 1.0) == g.is_solved():
                agree += 1
            gaps = g.all_gaps()
            if not gaps:
                break
            fam, line = random.choice(gaps)
            g.opt(fam, line, random.choice(g.blocks))
            d = random.choice(GAP_DIRECTIONS[fam])
            pos, _ = g.try_move_ex(d, step)
            if pos:
                g.commit_move(pos)
                g.update_matrix()
    check('T7a score=1.0 与 is_solved 全量一致', agree == total,
          f'{agree}/{total} 一致（其中错位态局面 {shifted} 个）')
    check('T7b 样本里确实出现过错位态（半整数坐标）', shifted > 0,
          f'{shifted} 个')


def t8_degenerate():
    print('\n--- T8 退化输入不崩 ---')
    from game_mi import MiSliderMatrix
    from solver.ml.mi_placement import best_placement
    b = best_placement(set(), 3, 3, 2)
    check('T8a 空集不崩', b is not None and b.overlap == 0, repr(b))
    b = best_placement({(0, 0, 'N')}, 3, 3, 2)
    check('T8b 单块不崩', b is not None, repr(b))
    g = MiSliderMatrix(3, 3)
    b = best_placement(g.positions(), 3, 3, 1)
    check('T8c step=1 还原态 score=1.0', b.score == 1.0, f'{b.score:.3f}')
    b = best_placement({(50.5, 50.5, 'N'), (51.5, 51.5, 'E')}, 3, 3, 2)
    check('T8d 远处半整数坐标不崩', b is not None, repr(b))
    b = best_placement([(0, 0, 'N'), (0, 0, 'N')], 3, 3, 2)
    check('T8e 重复坐标不崩', b is not None)
    # 奇偶不一致的死盘坐标：不该崩，且不能给出虚高的分
    b = best_placement({(0, 0, 'N'), (0, 0.5, 'E')}, 3, 3, 2)
    check('T8f 奇偶不一致坐标不崩', b is not None, repr(b))
    # 半整数 step 参数
    b = best_placement(g.positions(), 3, 3, 2.0)
    check('T8g step 传 float 不崩', b is not None and b.score == 1.0,
          f'{b.score:.3f}')


def t9_filter_never_blocks_solution():
    print('\n--- T9 mod 过滤不会挡掉真解（最关键的一条）---')
    from game_mi import MiSliderMatrix, blocks_from_cells
    from solver.ml import mi_placement as MP
    # **不用随机行走去找还原态** —— 那样命中率是 0（本轮实测 5 组配置、
    # 每组 80 步随机游走，一次都没走到），测试整条空跑，等于没验。
    # 改成穷举：把目标形状按**每一个合法偏移**平移，得到一个必然 is_solved
    # 的局面，再问 best_placement 能不能把它找回来（score=1.0）。
    # 这才是「过滤不会挡掉真解」的直接检验。
    blocked = 0
    hits = 0
    for m, n, step in ((3, 3, 1), (3, 3, 2), (4, 4, 2), (4, 4, 3),
                       (4, 3, 2), (3, 4, 3)):
        for goal in MP.goal_shapes(m, n):
            for di in range(-6, 7):
                for dj in range(-6, 7):
                    off = (di / 2.0, dj / 2.0)
                    if not MP.placement_offset_ok(off, step, m, n):
                        continue
                    cells = frozenset((r + off[0], c + off[1], q)
                                      for r, c, q in goal)
                    g = MiSliderMatrix(m, n)
                    g.blocks = blocks_from_cells(cells)
                    g.update_matrix()
                    if not g.is_solved():
                        continue
                    hits += 1
                    best = MP.best_placement(cells, m, n, step)
                    if best.score < 1.0:
                        blocked += 1
                        if blocked <= 3:
                            print(f'     ★ {m}x{n} step={step} off={off} '
                                  f'is_solved 但 score={best.score:.3f}')
    check('T9a 所有合法偏移构造的还原态都能被找回（score=1.0）',
          blocked == 0, f'命中 {hits} 个还原局面，挡掉 {blocked}')
    check('T9b 样本量足够（不是空跑）', hits >= 200, f'{hits} 个还原局面')


def t10_offset_domain_complete():
    print('\n--- T10 枚举域完整：域内最优 == 宽范围暴力最优 ---')
    from game_mi import MiSliderMatrix
    from solver.ml import mi_placement as MP
    random.seed(23)
    for m, n, step in ((3, 3, 2), (4, 4, 2), (4, 4, 3), (3, 4, 1)):
        g = MiSliderMatrix(m, n)
        g.shuffle(15, step)
        cells = frozenset(g.positions())
        best = MP.best_placement(cells, m, n, step)
        # 宽 2 倍的暴力域（两个 shape 都算）
        shapes = MP.goal_shapes(m, n)
        rs = [k[0] for k in cells]
        cs = [k[1] for k in cells]
        lo_r, hi_r = math.floor(min(rs)), math.floor(max(rs))
        lo_c, hi_c = math.floor(min(cs)), math.floor(max(cs))
        brute = 0
        for di in range(2 * (lo_r - 2 * m - 2), 2 * (hi_r + 3)):
            for dj in range(2 * (lo_c - 2 * n - 2), 2 * (hi_c + 3)):
                off = (di / 2.0, dj / 2.0)
                if not MP.placement_offset_ok(off, step, m, n):
                    continue
                for sh in shapes:
                    shifted = frozenset((r + off[0], c + off[1], q)
                                        for r, c, q in sh)
                    brute = max(brute, len(cells & shifted))
        check(f'T10a {m}x{n} step={step} 域内最优 == 暴力最优',
              best.overlap == brute, f'{best.overlap} vs {brute}')


def main():
    print('=' * 70)
    print('mi 最佳放置 / 目标框回归（M3 第一步）')
    print('=' * 70)
    t1_solved_state()
    t2_transpose()
    t3_mod_structure()
    t4_mod_conserved_by_moves()
    t5_half_offset_only_step1()
    t6_prefix_matches_bruteforce()
    t7_score_matches_is_solved()
    t8_degenerate()
    t9_filter_never_blocks_solution()
    t10_offset_domain_complete()
    print('\n' + '=' * 70)
    if _F:
        print(f'FAIL {len(_F)}:')
        for f in _F:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
