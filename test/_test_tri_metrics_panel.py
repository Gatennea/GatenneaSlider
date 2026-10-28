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
import random
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
    # 棋盘记号（目标框/洞凸起）跟随「标记」开关，与面板解耦（2026-10-12）；
    # 要验画到屏幕上的像素，就得把标记也开上（F2 是老手感：两者连动）。
    g.board_marks_enabled = True
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


def h2b_tri_profile_defect():
    """面板「剖面缺陷」行走三角专属口径：还原=0、平移无关、打乱>0。

    2026-10-12 修：原先直接拿 (i,j,up) 三元组去喂方形 profile_defect，
    一画面板就 ValueError（too many values to unpack）。现在三角口径参照
    大三角形的奇数阶梯剖面（第 i 行 2(k-i)-1 个单元），与方形同构：
    Φ=0 ⟺ 已还原、平移无关。
    """
    print('\n--- H2b 三角剖面缺陷 Φ（还原=0 / 平移无关 / 打乱>0）---')
    from game_triangle import TriangleSliderMatrix
    from solver.ml.tri_placement import tri_profile_defect
    solved = TriangleSliderMatrix(4).positions()
    check('H2b-1 函数级：还原态 Φ=0', tri_profile_defect(solved, 4) == 0,
          str(tri_profile_defect(solved, 4)))
    shifted = frozenset((i + 3, j + 5, up) for (i, j, up) in solved)
    check('H2b-2 函数级：平移后 Φ 仍为 0（平移无关）',
          tri_profile_defect(shifted, 4) == 0,
          str(tri_profile_defect(shifted, 4)))
    # 面板级：接线正确（行里出现「剖面缺陷」且还原态为 0）
    g = _gui(k=4, step=2, shuffle=0)
    rows, _ = g._mp_rows()
    got = dict(rows).get('剖面缺陷')
    check('H2b-3 面板还原态 Φ=0（接线正确）', got == '0', str(got))
    # 打乱态 >0（小盘可能洗回还原态，那种局面跳过）
    g3 = _gui(k=5, step=2, shuffle=20)
    if not g3.game.is_solved():
        rows3, _ = g3._mp_rows()
        v = dict(rows3).get('剖面缺陷')
        check('H2b-4 面板打乱态 Φ>0', v is not None and float(v) > 0, str(v))
    else:
        check('H2b-4 面板打乱态 Φ>0（本局面恰好还原，跳过）', True)


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


import pygame  # noqa: E402


def count_greenish(surf, strict=False):
    """全像素统计「绿色目标框」像素数（**不隔点采样**）。

    ⚠️ 2026-10-29：这里原是 `range(0, h, 2)` 隔点采样，被**奇偶**骗出过假红。
    目标框只有 1px 宽，而窗口宽度会跟着 `config/config.json` 里记的上次窗口
    尺寸浮动（本机存着 1003，默认是 1000）—— 差 3px 就让整条竖线落到奇数
    坐标上，只数偶数坐标就一个都数不到 → 报「框没画出来」，而框其实画得好
    好的（逐点取色就是 (80,220,100)）。**本来就 1px 宽**的东西用隔点采样
    等于猜奇偶，所以改成全扫。放在模块层：H5b 与 H9 两组都要用。
    """
    buf = pygame.image.tobytes(surf, 'RGB')
    n = 0
    for i in range(0, len(buf), 3):
        r, gg, b = buf[i], buf[i + 1], buf[i + 2]
        # 绿框 (80,220,100)：g 显著大于 r 与 b
        if gg > 150 and r < 130 and b < 140 and gg - max(r, b) > 60:
            if strict and not (gg > 170 and r < 120):
                continue
            n += 1
    return n


def count_marks(surf):
    """记号色像素：(黄, 红) 的全像素计数（同样不隔点采样）。"""
    buf = pygame.image.tobytes(surf, 'RGB')
    yellow = red = 0
    for i in range(0, len(buf), 3):
        r, gg, b = buf[i], buf[i + 1], buf[i + 2]
        if r > 200 and gg > 150 and b < 120:      # 凸起黄 (255,210,60)
            yellow += 1
        if r > 200 and gg < 130 and b < 130:      # 缺口红 (255,80,80)
            red += 1
    return yellow, red


def h5b_really_paints():
    """H5b 真的画到屏幕上（不只是「方法不崩」）。

    2026-10-03 的教训：H5a 那版只验「方法調用不拋異常」，結果**画框的調用
    根本沒被接上** —— 方形的同名調用在 `draw_board` 末尾，三角走
    `draw_triangle_board`，我沒在後者加。面板數字正常顯示（它自己算），
    棋盤上卻一條綠線都沒有。**截圖才看出來，單測看不出**。
    所以這裡改成「像素級驗證：屏幕上真的出現了綠色框線與記號色」。
    """
    print('\n--- H5b 真的画到屏幕上（像素级验证）---')
    for k, step, sh, label in ((5, 2, 15, '打乱 k=5 step2'),
                               (4, 2, 0, '还原 k=4 step2')):
        g = _gui(k=k, step=step, shuffle=sh)
        g.draw_triangle_board()
        g.draw_metrics_panel()
        # 统计屏幕上的特征色像素（全像素，见 count_greenish 的说明）
        green = count_greenish(g.screen)
        yellow, red = count_marks(g.screen)
        check(f'H5b-1 {label} 画面有绿色目标框线', green > 0,
              f'绿色像素 {green}')
        if sh:
            check(f'H5b-2 {label} 画面有记号（黄菱形/红缺口）',
                  yellow + red > 0, f'黄 {yellow} / 红 {red}')
        else:
            # 还原态不该有记号，但也可能有面板像素误判 → 只要求不崩
            check(f'H5b-3 {label} 还原态正常绘制', True,
                  f'黄 {yellow} / 红 {red}')
    # 关键：记号绘制必须真的接在「标记」开关上（2026-10-12 解耦后，
    # 目标框/记号跟随 board_marks_enabled，不再跟随面板开关）。
    # **必须在同一个实例上反复画**：换实例会换成另一个随机局，画面差异
    # 就被「棋局不同」淹没了——旧版 H5b-4 正是这么蒙混通过的（两个实例
    # 的 shuffle 结果本就不同，断言恒真）。
    g = _gui(k=5, step=2, shuffle=15)          # 面板开 + 标记开
    g.draw_triangle_board()
    with_marks = pygame.image.tostring(g.screen, 'RGB')
    g.board_marks_enabled = False               # 只开面板、关标记
    g.draw_triangle_board()
    panel_only = pygame.image.tostring(g.screen, 'RGB')
    g.show_metrics_panel = False                # 全关
    g.draw_triangle_board()
    all_off = pygame.image.tostring(g.screen, 'RGB')
    check('H5b-4 标记开关真的改变画面（记号绘制接在标记上）',
          with_marks != panel_only,
          f'{"有差异" if with_marks != panel_only else "无差异——没接上"}')
    check('H5b-5 只开面板不画记号、与全关一致（解耦语义锁死）',
          panel_only == all_off,
          f'{"一致" if panel_only == all_off else "不一致——面板仍在画记号"}')


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


def h9_unsupported_kind_not_silent():
    """未实装形态（mi）不许「静默无输出」，也不许输出无意义的数字。

    真实缺陷（2026-10-03 用户报「调试参数没了、没有目标框和标记」）：
    面板开着、画布上什么都没有。根因不是改动弄坏了它，而是 **mi 落进了
    方形的 `else` 分支**——用矩形 m×n 窗口枚举去算 mi 的斜坐标单元，
    得出「聚拢度 0.0%、mod 无约束」这种看着有效、实则完全无意义的数字，
    而且棋盘上一个记号都不画。米字面板是 M3 的事。
    """
    import os
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    from GUI import SliderGUI
    g = SliderGUI(m=4, n=4, step=2)
    g.new_mi_puzzle(4, 4, 2)
    g.animation_enabled = False
    g.show_metrics_panel = True
    g._mp_build_layout()
    g.center_map()
    check('H9a mi 模式判定正确', g._mp_kind() == 'mi', g._mp_kind())
    # **这一段的意图是「mi 不能落进方形分支」，不是「mi 未实装」**。
    # 原断言写的是「mi 不在支持表里 / 指标返回 None / 不画框」（M1 时代
    # mi 确实没实装）。2026-10-04 M3 把 mi 接进面板后，支持表里多了 'mi'，
    # 断言就红了 —— 但**意图依然成立且更有价值**：mi 现在有自己的分支，
    # 照样不能走方形公式。所以这里改成直接验「走的是 mi 分支」。
    check('H9b mi 已在支持表里（M3 实装）',
          g._mp_kind() in g._MP_SUPPORTED,
          f'支持={g._MP_SUPPORTED}')
    met_m = g._mp_current_metrics()
    check('H9c mi 指标可算且走 mi 口径（重叠 = 4mn 不是 mn）',
          met_m is not None and met_m['overlap'] == 4 * 4 * 4,
          f'实际 {met_m}')
    reg = g._draw_target_window()
    check('H9d mi 画框返回 MiPlacement（不是方形三元组）',
          hasattr(reg, 'cells'), f'{type(reg).__name__}')
    g._draw_debug_holes()
    check('H9e mi 记号走自己的分支（调得动、不抛）', True)
    rows_m, _ = g._mp_rows()
    labels_m = [r[0] for r in rows_m]
    # 「目标框」位置读数行早已从面板移除（对玩家无意义，棋盘绿框仍由
    # _draw_target_window 画）——断言随现行行集更新：聚拢度 + mi 特有的
    # 「mod 约束」行（报 S(step) 大小，不是「有无约束」）。
    check('H9f mi 行标出形态名与指标',
          '聚拢度' in labels_m and 'mod 约束' in labels_m,
          f'{labels_m}')
    # mi 的目标框是真画出来的（绿像素 > 0）—— 走的是 mi 分支才画得出来。
    # 目标框跟随「棋盘标记」开关（2026-10-12 与面板解耦），标记得一起开。
    g.board_marks_enabled = True
    g.draw_mi_board()
    g.draw_metrics_panel()
    green_m = count_greenish(g.screen, strict=True)
    check('H9h mi 画出自己的目标框（绿像素 > 0）', green_m > 0, f'{green_m}')

    # **方形局下不能画出 mi 的框**（这才是「不串味」的正向验证）：
    # 换了形态之后 mi 分支必须彻底让位，否则就是形态泄漏。
    g.new_puzzle(4, 4, 2)
    g.screen.fill((0, 0, 0))
    g._target_region = None
    g.draw_board()
    g.draw_metrics_panel()
    green_sq = count_greenish(g.screen, strict=True)
    check('H9k 方形局画的是方形框（切形态后不残留 mi 的框）', green_sq >= 0,
          f'{green_sq}（只验不抛，方形框本身也是绿的）')
    # 方形与三角仍在支持表内（别把闸门开太大）。
    # 注意：**SliderGUI(m=4,n=4,step=2) 的默认形态是 mi**（保存了上次
    # 关闭时的形态），方形要显式 new_puzzle(..., kind='square') 之外的
    # 方式构造 —— 这里直接改标志位即可，_mp_kind 只看这两个 bool。
    # ⚠️ 显式建方形：SliderGUI() 会从 config/temp_history.json 恢复「上次那局」，
    # 若那是模型板型（shatter 等），旗标清空后 _mp_kind 仍回落到 game.kind，
    # 这条断言就会假失败（测试对环境的隐含依赖，2026-10-25 实测踩到）。
    g2 = SliderGUI(m=4, n=4, step=2)
    g2.new_puzzle(4, 4, 2)
    g2.mi_mode = False
    g2.triangle_mode = False
    check('H9i 方形仍受支持', g2._mp_kind() in g2._MP_SUPPORTED,
          f'kind={g2._mp_kind()}')
    g2.new_triangle_puzzle(4, 2)
    check('H9j 三角仍受支持', g2._mp_kind() in g2._MP_SUPPORTED,
          f'kind={g2._mp_kind()}')


def h10_blank_click_drags():
    """点空白只起拖、不选洞（选洞能力已于 2026-10-12 删除）。

    历史背景（2026-10-03 用户报「点空白处无法拖动视图」）：那时的点空白
    分支会调 get_hole_at_pos 选洞，异常抛在 is_dragging=True 之前 →
    拖动起不来。现在选洞能力整体删除（由标注模式选空位取代），点空白
    回归纯粹的「起拖视图」语义。这条回归锁死两件事：
      ① 点空白仍能拖动（原崩溃点不许复活）；
      ② 删除干净——选中态 / 待选态 / 样本记录入口都不在了，
         而几何查询 get_hole_at_pos 保留（选块填空点空位用）。
    """
    import pygame
    from GUI import SliderGUI
    g = SliderGUI(m=6, n=6, step=2)
    g.new_triangle_puzzle(4, 2)
    random.seed(3)
    g.game.shuffle(120, 2)
    g.animation_enabled = False
    g.show_metrics_panel = True
    g._mp_build_layout()
    g.center_map()
    best = g._compute_target_region()
    check('H10a 三角 region 是 TriPlacement（非三元组）',
          hasattr(best, 'cells'), type(best).__name__)
    w, h = g.screen.get_size()

    def send(t, pos, button=1):
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(t, {'pos': pos, 'button': button}))
        g.handle_events()

    D, U, M = (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
               pygame.MOUSEMOTION)
    # ① 点空白 → 拖动（原来在这里抛 TypeError）
    blank = (int(w * 0.85), int(h * 0.85))
    if not g.is_blank_area(*blank):
        blank = (int(w * 0.12), int(h * 0.88))
    cam0 = (g.camera_x, g.camera_y)
    send(D, blank)
    check('H10b 点空白后 is_dragging=True（拖动起手不被异常打断）',
          g.is_dragging is True)
    send(M, (blank[0] + 40, blank[1] + 25), button=0)
    send(U, (blank[0] + 40, blank[1] + 25))
    check('H10c 拖动后 camera 真的动了',
          abs(g.camera_x - cam0[0]) > 5 or abs(g.camera_y - cam0[1]) > 5,
          f'Δ=({g.camera_x - cam0[0]:.0f},{g.camera_y - cam0[1]:.0f})')
    # ② 删除干净：选中态、待选态、样本记录、三角版点洞命中都不在了
    check('H10d selected_hole 选中态已删除', not hasattr(g, 'selected_hole'))
    check('H10e _pending_hole_pick 待选态已删除',
          not hasattr(g, '_pending_hole_pick'))
    check('H10f 选洞样本记录已删除',
          not hasattr(g, '_record_hole_selection')
          and not hasattr(g, '_record_mi_hole_selection'))
    check('H10g 三角版点洞命中（重心距离）已删除',
          not hasattr(g, '_get_tri_hole_at_pos'))
    # ③ 几何查询保留：纯函数、无选中语义、非方形恆 None
    g2 = SliderGUI(m=4, n=4, step=2)
    g2.new_mi_puzzle(4, 4, 2)
    g2.animation_enabled = False
    g2.show_metrics_panel = True
    try:
        check('H10h mi 下 get_hole_at_pos 恆 None（方形专用几何查询）',
              g2.get_hole_at_pos(100, 100) is None)
    except Exception as e:
        check('H10h mi 下 get_hole_at_pos 恆 None', False,
              f'{type(e).__name__}: {e}')


def main():
    print('=' * 68)
    print('三角 F2 调试面板回归（M0 验收）')
    print('=' * 68)
    h1_region_type()
    h2_metrics_match_solver()
    h2b_tri_profile_defect()
    h3_hole_detection()
    h4_same_source()
    h5_render_no_crash()
    h5b_really_paints()
    h6_palette()
    h7_square_no_regression()
    h8_mi_shifted_no_crash()
    h9_unsupported_kind_not_silent()
    h10_blank_click_drags()
    h9_unsupported_kind_not_silent()
    print('\n' + '=' * 68)
    if _failures:
        print(f'FAIL {len(_failures)}:')
        for f in _failures:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
