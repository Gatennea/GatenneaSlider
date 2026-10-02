# -*- coding: utf-8 -*-
r"""三角 F2 调试面板回归（M0 验收项，计划 §4）。

**为什么这块要单独测**：计划 §4 的铁律是「调试面板画框与求解器必须共用同一
结果」——目标框不是求解器的内部细节，而是 GUI 与求解器的共用地基。所以面板
的正确性判据不是「画出来好看」，而是**画框与记号吃的数据源必须与 M1 求解器
将要用的完全同一套**。一旦面板自己另算一份，M1 接上就会两边不一致，而且这种
不一致在画面上看不出来，只能靠单测锁住。

覆盖：
  H1  _compute_target_region 在三角下返回 TriPlacement（不是方形那个三元组）
  H2  面板指标口径 = 求解器口径（score/overlap 与 best_placement 逐值相等）
  H3  洞/凸起检测：还原态 0 洞 0 凸起；打乱态有洞；洞型分类正确
  H4  洞检测吃的是**面板画框同一个** TriPlacement.cells（同源铁律）
  H5  绘制路径不崩（还原态 / 打乱态 / 大 k / step=1）
  H6  三角形下调色板 & 记号语义与方形一致
  H7  方形零回归（面板仍走原来的矩形分支）
  H8  mi 错位态不崩（预先存在 bug 的回归：hole_detector 拿 float 下标）

运行：D:\python\python.exe test\_test_tri_metrics_panel.py
"""

import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


def _gui(k=4, step=2, shuffle=0, mi=False):
    from GUI import SliderGUI
    g = SliderGUI(m=6, n=6, step=step)
    if mi:
        g.new_mi_puzzle(6, 6, step)
    else:
        g.new_triangle_puzzle(k, step)
    if shuffle:
        g.game.shuffle(shuffle, step)
    g.animation_enabled = False
    g._mp_init_state()
    g.show_metrics_panel = True
    g._mp_build_layout()
    g.center_map()
    return g


def h1_region_type():
    print('\n--- H1 三角下返回 TriPlacement ---')
    from solver.ml.tri_placement import TriPlacement
    g = _gui(k=4, step=2, shuffle=12)
    region = g._compute_target_region()
    check('H1a 返回 TriPlacement', isinstance(region, TriPlacement),
          f'实际 {type(region).__name__}')
    check('H1b 有 offset / cells / overlap 三件',
          all(hasattr(region, a) for a in ('offset', 'cells', 'overlap')))
    check('H1c offset 是二元组（不是方形三元组）',
          isinstance(region.offset, tuple) and len(region.offset) == 2,
          f'{region.offset}')
    # 方形分支不变
    g2 = _gui(step=2, shuffle=12, mi=False)
    g2.triangle_mode = False
    g2.game = __import__('game').SliderMatrix(6, 6)
    g2.game.shuffle(12, 2)
    r2 = g2._compute_target_region()
    check('H1d 方形分支仍返回 (r0,c0,(rh,cw))',
          isinstance(r2, tuple) and len(r2) == 3, f'实际 {r2}')


def h2_metrics_match_solver():
    print('\n--- H2 面板指标 = 求解器口径（逐值相等）---')
    from solver.ml.tri_placement import best_placement_of_game
    for k, step, sh in ((4, 2, 12), (5, 2, 15), (6, 3, 20), (3, 1, 0)):
        g = _gui(k=k, step=step, shuffle=sh)
        met = g._mp_current_metrics()
        best = best_placement_of_game(g.game, k=k, step=step)
        check(f'H2a k={k} step={step} score 逐值相等',
              abs(met['score'] - best.score) < 1e-12,
              f"面板 {met['score']} vs 求解器 {best.score}")
        check(f'H2b k={k} step={step} overlap 逐值相等',
              met['overlap'] == best.overlap,
              f"{met['overlap']} vs {best.overlap}")
        check(f'H2c k={k} step={step} fill_rate = overlap/k²',
              abs(met['fill_rate'] - best.score) < 1e-12)


def h3_hole_detection():
    print('\n--- H3 洞/凸起检测 ---')
    from solver.ml.tri_holes import detect_tri_holes
    from solver.ml.tri_placement import best_placement
    from game_triangle import TriangleSliderMatrix
    # 还原态：0 洞 0 凸起
    for k in (3, 4, 5):
        g = TriangleSliderMatrix(k)
        best = best_placement(g.positions(), k, 2)
        holes, prot = detect_tri_holes(g.positions(), best.cells, 2)
        check(f'H3a k={k} 还原态 0 洞', len(holes) == 0, f'洞={len(holes)}')
        check(f'H3b k={k} 还原态 0 凸起', len(prot) == 0, f'凸起={len(prot)}')
    # 打乱态：有洞
    import random
    random.seed(3)
    found_hole = found_gap = found_prot = False
    for _ in range(20):
        g = TriangleSliderMatrix(4)
        g.shuffle(15, 2)
        best = best_placement(g.positions(), 4, 2)
        holes, prot = detect_tri_holes(g.positions(), best.cells, 2)
        if holes:
            found_hole = True
            if any(h['type'] == 'hole' for h in holes):
                found_hole = True
            if any(h['type'] == 'gap' for h in holes):
                found_gap = True
        if prot:
            found_prot = True
    check('H3c 打乱态能检出洞', found_hole)
    check('H3d 打乱态能检出凸起', found_prot)
    # 洞型：手工构造
    goal = frozenset(TriangleSliderMatrix(4).positions())
    # 挖掉内部一格 → 孔洞（被包围）
    interior = (1, 1, True)
    check('H3e (1,1,True) 在 k=4 大三角内部', interior in goal)
    hole_case = set(goal) - {interior}
    holes, prot = detect_tri_holes(hole_case, goal, 2)
    types = {h['type'] for h in holes}
    check('H3f 挖内部一格 → 判为孔洞（非缺口）', types == {'hole'},
          f'得到 {types}，洞={[h["cells"] for h in holes]}')
    # 挖掉角上 → 缺口（连到边界）
    corner = (3, 0, True)
    gap_case = set(goal) - {corner}
    holes, prot = detect_tri_holes(gap_case, goal, 2)
    types = {h['type'] for h in holes}
    check('H3g 挖角上一格 → 判为缺口（连边界）', types == {'gap'},
          f'得到 {types}')


def h4_same_source():
    print('\n--- H4 洞检测吃的是面板画框同一个 cells（同源铁律）---')
    from solver.ml.tri_holes import detect_tri_holes
    g = _gui(k=5, step=2, shuffle=18)
    region = g._compute_target_region()
    # 面板的记号就是拿 region.cells 算的 —— 直接验这条路径
    coords = frozenset(tuple(b.location) for b in g.game.blocks)
    holes_a, prot_a = detect_tri_holes(coords, region.cells, g.current_step)
    # 再从「画框」这条路径取一次（面板 _draw_tri_marks 内部就是这么做）
    from solver.ml.tri_placement import best_placement_of_game
    best = best_placement_of_game(g.game, k=5, step=g.current_step)
    holes_b, prot_b = detect_tri_holes(coords, best.cells, g.current_step)
    check('H4a 面板 region 与 best_placement 是同一结果',
          region.offset == best.offset and region.cells == best.cells,
          f'{region.offset} vs {best.offset}')
    check('H4b 两次洞检测结果一致',
          holes_a == holes_b and prot_a == prot_b)


def h5_render_no_crash():
    print('\n--- H5 绘制路径不崩 ---')
    cases = [
        (4, 2, 12, '打乱 k=4 step2'),
        (4, 2, 0, '还原 k=4 step2'),
        (6, 3, 20, '打乱 k=6 step3'),
        (3, 1, 10, '打乱 k=3 step1'),
        (5, 2, 0, '还原 k=5 step2'),
    ]
    for k, step, sh, label in cases:
        g = _gui(k=k, step=step, shuffle=sh)
        errs = []
        for name in ('_draw_target_window', '_draw_debug_holes',
                     'draw_metrics_panel'):
            try:
                getattr(g, name)()
            except Exception as e:
                errs.append(f'{name}: {type(e).__name__}: {e}')
        check(f'H5a {label} 三个绘制入口全通', not errs, '; '.join(errs))


def h6_palette():
    print('\n--- H6 调色板与记号语义 ---')
    from solver.ml import tri_holes as TH
    from game_triangle import TriangleSliderMatrix
    check('H6a 大洞=红 / 小洞=蓝（与方形同）',
          TH.hole_color({'size': 'large'}) == (255, 80, 80)
          and TH.hole_color({'size': 'small'}) == (80, 160, 255),
          f"large={TH.hole_color({'size': 'large'})} "
          f"small={TH.hole_color({'size': 'small'})}")
    check('H6b 凸起=黄', TH.PROTRUSION_COLOR == (255, 210, 60))
    # 洞的 size 分档：大洞口径 = 边长 step 的大三角单元数 step(step+1)/2
    # step=1 时门槛是 1，所以单个单元就是「大洞」——这与方形一致
    # （step=1 门槛 = 1×1 = 1 格）。我第一版断言写 small，是错的。
    g = TriangleSliderMatrix(4)
    goal = frozenset(g.positions())
    for step, n_cells, want in ((1, 1, 'large'), (1, 2, 'large'),
                                (2, 3, 'large'),   # 门槛 3，边界算大
                                (2, 2, 'small'), (2, 6, 'large'),
                                (3, 6, 'large'), (3, 5, 'small'),
                                (3, 10, 'large')):
        hole = [tuple(x) for x in goal][:n_cells]
        got = TH._size_of(hole, step)
        check(f'H6c step={step} {n_cells} 单元 → {want}', got == want,
              f'实得 {got}（门槛 {step * (step + 1) // 2}）')


def h7_square_no_regression():
    print('\n--- H7 方形零回归 ---')
    from solver.ml.gather_solver import find_best_window, gather_metrics
    g = _gui(step=2, shuffle=12, mi=False)
    from game import SliderMatrix
    g.game = SliderMatrix(6, 6)
    g.game.shuffle(12, 2)
    g.triangle_mode = False
    errs = []
    for name in ('_mp_current_metrics', '_compute_target_region',
                 '_draw_target_window', '_draw_debug_holes',
                 'draw_metrics_panel'):
        try:
            getattr(g, name)()
        except Exception as e:
            errs.append(f'{name}: {type(e).__name__}: {e}')
    check('H7a 方形五个入口全通', not errs, '; '.join(errs))
    met = g._mp_current_metrics()
    coords = frozenset((b.location[0], b.location[1]) for b in g.game.blocks)
    ref = gather_metrics(coords, g.game.m, g.game.n)
    check('H7b 方形指标仍走 gather_metrics',
          abs(met['score'] - ref['score']) < 1e-12,
          f"{met['score']} vs {ref['score']}")


def h8_mi_shifted_no_crash():
    print('\n--- H8 mi 错位态不崩（预先存在 bug 的回归）---')
    from solver.ml.hole_detector import detect_holes
    from game_mi import MiSliderMatrix, GAP_DIRECTIONS
    import random
    random.seed(3)
    g = MiSliderMatrix(4, 4)
    g.shuffle(20, 2)
    for _ in range(10):
        gaps = g.all_gaps()
        if not gaps:
            break
        fam, line = random.choice(gaps)
        g.opt(fam, line, random.choice(g.blocks))
        d = random.choice(GAP_DIRECTIONS[fam])
        pos, _ = g.try_move_ex(d, 2)
        if pos:
            g.commit_move(pos)
            g.update_matrix()

    def _halves(game):
        return [c for c in (tuple(b.location) for b in game.blocks)
                if float(c[0]).is_integer() is False
                or float(c[1]).is_integer() is False]

    # 随机走**不保证**产出错位态（10 步可能全是直滑）——补一刀 d1 斜缝强制
    # 造出来，否则这条断言会被「随机恰好没走到」掩盖掉真正的回归。
    if not _halves(g):
        for fam, line in [(t, l) for (t, l) in g.all_gaps() if t == 'd1']:
            for d in ('q', 'x', 'e', 'z'):
                g._clear_selection()
                g.opt(fam, line, random.choice(g.blocks))
                pos, _ = g.try_move_ex(d, 1)
                if pos:
                    g.commit_move(pos)
                    g.update_matrix()
                    if _halves(g):
                        break
            if _halves(g):
                break
    coords = frozenset((b.location[0], b.location[1]) for b in g.blocks)
    halves = [c for c in coords
              if float(c[0]).is_integer() is False
              or float(c[1]).is_integer() is False]
    check('H8a 造出了错位态（半整数坐标存在）', len(halves) > 0,
          f'{len(halves)}/{len(coords)}')
    try:
        detect_holes(coords, g.m, g.n, 2)
        check('H8b detect_holes 在错位态不崩（曾抛 TypeError）', True)
    except Exception as e:
        check('H8b detect_holes 在错位态不崩', False,
              f'{type(e).__name__}: {e}')
    # GUI 层
    gg = _gui(step=2, shuffle=12, mi=True)
    gg.game.shuffle(20, 2)
    try:
        gg._draw_debug_holes()
        check('H8c mi 面板绘制在错位态不崩', True)
    except Exception as e:
        check('H8c mi 面板绘制在错位态不崩', False,
              f'{type(e).__name__}: {e}')


def main():
    print('=' * 68)
    print('三角 F2 调试面板回归（M0 验收）')
    print('=' * 68)
    h1_region_type()
    h2_metrics_match_solver()
    h3_hole_detection()
    h4_same_source()
    h5_render_no_crash()
    h6_palette()
    h7_square_no_regression()
    h8_mi_shifted_no_crash()
    print('\n' + '=' * 68)
    if _failures:
        print(f'FAIL {len(_failures)}:')
        for f in _failures:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
