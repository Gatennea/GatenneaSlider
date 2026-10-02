# -*- coding: utf-8 -*-
r"""mi 坐标类型回归：location 分量必须是 int（2026-10-03 fatal error 修复）。

**故障现象**：用户报「游戏直接 fatal error 打不开」。config/error_log.jsonl
里是主循环异常：

    File "GUI.py", line 3499, in run
      self.draw_metrics_panel()
    File "gui/metrics_panel.py", line 88, in _compute_target_region
      r0, c0, (rh, cw), _ = find_best_window(coords, game.m, game.n, step)
    File "solver/ml/gather_solver.py", line 128, in find_best_window
      for r0 in range(min_r - rh + 1, max_r + 1):
  TypeError: 'float' object cannot be interpreted as an integer

**根因**：`MiSliderMatrix.commit_move` 原样写入 `final_positions`，而滑动
向量是 ½ 的倍数 → 算出来是 float → `b.location[0]` 变成 `3.0` 而不是 `3`。
下游 `find_best_window` 拿它做 `range()` 的端点，直接炸。

方形/三角坐标恒整数所以从没触发；**米字是第一个真正会产生半整数的形态**，
而米字的调试面板路径此前没有任何测试覆盖 —— 这是「补了 A 洞却撞出 B 坑」。

修法：commit_move 写入前过 `_norm_loc`（整数分量转 int、半整数保持 float、
q 原样），见 game_mi.py。

运行：D:\python\python.exe test\_test_mi_loc_type.py
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


def _loc_types(game):
    return {tuple(type(v).__name__ for v in b.location)
            for b in game.blocks}


def _make_shifted(game, moves=10, seed=3):
    """把 game 走到错位态（B 晶格），模拟最容易触发下游 bug 的输入。

    随机走**不保证**能产出错位态（10 步可能全是直滑），所以先试随机、
    不行就补一刀 d1 斜缝强制错位——本测试要的是「含半整数坐标的输入」，
    不是「随机过程恰好走了多少步」。
    """
    from game_mi import GAP_DIRECTIONS
    random.seed(seed)
    for _ in range(moves):
        gaps = game.all_gaps()
        if not gaps:
            break
        fam, line = random.choice(gaps)
        game.opt(fam, line, random.choice(game.blocks))
        d = random.choice(GAP_DIRECTIONS[fam])
        pos, _ = game.try_move_ex(d, 2)
        if pos:
            game.commit_move(pos)
            game.update_matrix()
    if not _has_half(game):
        # 补一刀斜向一格（d1）——这是产生 B 晶格最直接的手段
        for fam, line in [(t, l) for (t, l) in game.all_gaps() if t == 'd1']:
            for d in ('q', 'x', 'e', 'z'):
                game._clear_selection()
                game.opt(fam, line, random.choice(game.blocks))
                pos, _ = game.try_move_ex(d, 1)
                if pos:
                    game.commit_move(pos)
                    game.update_matrix()
                    if _has_half(game):
                        break
            if _has_half(game):
                break
    return game


def _has_half(game):
    return any(float(b.location[0]).is_integer() is False
               or float(b.location[1]).is_integer() is False
               for b in game.blocks)


def t1_shuffle_keeps_int():
    print('\n--- T1 shuffle 后整数坐标不是 float（曾全是 float）---')
    from game_mi import MiSliderMatrix
    for m, n, step in ((3, 3, 2), (4, 4, 1), (4, 4, 3)):
        g = MiSliderMatrix(m, n)
        g.shuffle(20, step)
        # 判据不是「全是 int」——错位态本来就该有 float 半整数坐标。
        # 真正的判据是「**整数坐标不得是 float**」：修复前 3.0 这类会残留。
        ghosts = [b.location for b in g.blocks
                  if (type(b.location[0]) is float
                      and float(b.location[0]).is_integer())
                  or (type(b.location[1]) is float
                      and float(b.location[1]).is_integer())]
        check(f'T1a mi {m}x{n} step{step} 无 float 整数残留', not ghosts,
              f'残留 {len(ghosts)} 块 {ghosts[:2]}')
        # 每个分量的类型必须是 int 或 float（不能是 numpy/str 等）
        ok_types = all(type(b.location[0]) in (int, float)
                       and type(b.location[1]) in (int, float)
                       and isinstance(b.location[2], str)
                       for b in g.blocks)
        check(f'T1b mi {m}x{n} step{step} 分量类型合法', ok_types)


def t2_moves_keep_int():
    print('\n--- T2 真实滑动后无 float 整数残留 ---')
    from game_mi import MiSliderMatrix
    g = _make_shifted(MiSliderMatrix(4, 4), moves=10)
    ghosts = [b.location for b in g.blocks
              if (type(b.location[0]) is float and float(b.location[0]).is_integer())
              or (type(b.location[1]) is float and float(b.location[1]).is_integer())]
    check('T2a 走 10 步（含错位）后无 float 整数残留', not ghosts,
          f'残留 {len(ghosts)} 块 {ghosts[:2]}')
    check('T2b 局面仍自洽（is_solved 不炸、positions 数正确）',
          g.is_solved() in (True, False) and len(g.positions()) == 64,
          f'positions={len(g.positions())}')


def t3_find_best_window_no_crash():
    print('\n--- T3 崩溃点：find_best_window（曾抛 TypeError）---')
    from game_mi import MiSliderMatrix
    from solver.ml.gather_solver import find_best_window, _game_coords
    # 还原态
    g0 = MiSliderMatrix(4, 4)
    try:
        r = find_best_window(_game_coords(g0), g0.m, g0.n, 2)
        check('T3a 还原态可算', True, f'→ {r}')
    except Exception as e:
        check('T3a 还原态可算', False, f'{type(e).__name__}: {e}')
    # 打乱态
    g1 = MiSliderMatrix(4, 4)
    g1.shuffle(20, 2)
    try:
        r = find_best_window(_game_coords(g1), g1.m, g1.n, 2)
        check('T3b 打乱态可算（曾抛 TypeError）', True, f'→ {r}')
    except Exception as e:
        check('T3b 打乱态可算', False, f'{type(e).__name__}: {e}')
    # 错位态
    g2 = _make_shifted(MiSliderMatrix(4, 4), moves=10)
    try:
        r = find_best_window(_game_coords(g2), g2.m, g2.n, 2)
        check('T3c 错位态可算', True, f'→ {r}')
    except Exception as e:
        check('T3c 错位态可算', False, f'{type(e).__name__}: {e}')


def t4_gather_metrics_no_crash():
    print('\n--- T4 聚拢度相关下游不崩 ---')
    from game_mi import MiSliderMatrix
    from solver.ml import gather_solver
    for label, mk in (('还原态', lambda: MiSliderMatrix(4, 4)),
                      ('打乱态', lambda: _shuffled()),
                      ('错位态', lambda: _make_shifted(MiSliderMatrix(4, 4)))):
        g = mk()
        for fn_name in ('gather_metrics', 'max_overlap', 'detect_target_corner'):
            fn = getattr(gather_solver, fn_name, None)
            if fn is None:
                continue
            try:
                if fn_name == 'gather_metrics':
                    fn(_game_coords_of(g), g.m, g.n)
                elif fn_name == 'max_overlap':
                    fn(_game_coords_of(g), g.m, g.n)
                else:
                    fn(_game_coords_of(g), g.m, g.n, 2)
                check(f'T4 {label} {fn_name} 不崩', True)
            except Exception as e:
                check(f'T4 {label} {fn_name} 不崩', False,
                      f'{type(e).__name__}: {e}')


def _shuffled():
    from game_mi import MiSliderMatrix
    g = MiSliderMatrix(4, 4)
    g.shuffle(20, 2)
    return g


def _game_coords_of(game):
    return gather_solver_coords(game)


def gather_solver_coords(game):
    from solver.ml.gather_solver import _game_coords
    return _game_coords(game)


def t5_half_int_preserved():
    print('\n--- T5 半整数必须保留（归一化不能把错位态压回整数）---')
    from game_mi import MiSliderMatrix
    g = _make_shifted(MiSliderMatrix(4, 4), moves=10, seed=3)
    halves = [b.location for b in g.blocks
              if float(b.location[0]).is_integer() is False
              or float(b.location[1]).is_integer() is False]
    check('T5a 错位态确实含半整数坐标（B 晶格存在）', len(halves) > 0,
          f'{len(halves)}/{len(g.blocks)} 块半整数')
    check('T5b 半整数是真正的 float 类型（不是 int 伪装）',
          all(type(b.location[0]) is float or type(b.location[1]) is float
              for b in g.blocks
              if float(b.location[0]).is_integer() is False
              or float(b.location[1]).is_integer() is False))
    # 导出/导入往返。**注意：往返后整盘会重新锚定到原点**（导出格式以边界盒
    # 为基准），这是平移等价的既有设计、不是 bug——实测改动前后行为一致。
    # 所以这里比的是「相对形状」而不是绝对坐标。
    out = g.export_map()
    g2 = MiSliderMatrix(4, 4)
    ok = g2.import_map(out)
    check('T5c 存盘往返成功', ok)
    p1, p2 = set(g.positions()), set(g2.positions())
    check('T5d 往返后块数一致', len(p1) == len(p2), f'{len(p1)} vs {len(p2)}')

    def canon(cells):
        """平移归一后的形状签名（去掉整盘锚定偏移）。"""
        mr = min(float(c[0]) for c in cells)
        mc = min(float(c[1]) for c in cells)
        return {(round(float(c[0]) - mr, 3), round(float(c[1]) - mc, 3), c[2])
                for c in cells}

    check('T5e 往返后形状一致（平移归一后）', canon(p1) == canon(p2),
          f'{"一致" if canon(p1) == canon(p2) else "不一致"}')
    halves2 = [b.location for b in g2.blocks
               if float(b.location[0]).is_integer() is False
               or float(b.location[1]).is_integer() is False]
    check('T5f 导入后半整数仍保留', len(halves2) > 0,
          f'{len(halves2)} 块半整数')


def t6_knorm_loc_unit():
    print('\n--- T6 _norm_loc 单元行为 ---')
    from game_mi import _norm_loc
    check('T6a (3.0, -5.0, "N") → (3, -5, "N")',
          _norm_loc((3.0, -5.0, 'N')) == (3, -5, 'N'),
          f'实得 {_norm_loc((3.0, -5.0, "N"))}')
    check('T6b (0.5, 0.5, "S") → (0.5, 0.5, "S") 半整数保留',
          _norm_loc((0.5, 0.5, 'S')) == (0.5, 0.5, 'S'),
          f'实得 {_norm_loc((0.5, 0.5, "S"))}')
    check('T6c 混合坐标 (1.0, 2.5, "E") → (1, 2.5, "E")',
          _norm_loc((1.0, 2.5, 'E')) == (1, 2.5, 'E'),
          f'实得 {_norm_loc((1.0, 2.5, "E"))}')
    check('T6d 原整数不变（幂等）',
          _norm_loc((3, 4, 'W')) == (3, 4, 'W'))
    check('T6e 幂等：_norm_loc(_norm_loc(x)) == _norm_loc(x)',
          all(_norm_loc(_norm_loc(x)) == _norm_loc(x)
              for x in ((3.0, -5.0, 'N'), (0.5, 0.5, 'S'), (1.0, 2.5, 'E'))))


def t7_square_triangle_untouched():
    print('\n--- T7 方形/三角零回归（它们坐标恒整数）---')
    from game import SliderMatrix
    from game_triangle import TriangleSliderMatrix
    from solver.ml.gather_solver import find_best_window, _game_coords
    sq = SliderMatrix(4, 4)
    sq.shuffle(20, 2)
    check('T7a 方形 location 全 int',
          {tuple(type(v).__name__ for v in b.location)
           for b in sq.blocks} == {('int', 'int')},
          f'实际 {sq.blocks[0].location}')
    try:
        find_best_window(_game_coords(sq), sq.m, sq.n, 2)
        check('T7b 方形 find_best_window 不崩', True)
    except Exception as e:
        check('T7b 方形 find_best_window 不崩', False, f'{e!r}')
    tri = TriangleSliderMatrix(5)
    tri.shuffle(20, 2)
    check('T7c 三角 location 前两分量全 int',
          all(isinstance(b.location[0], int) and isinstance(b.location[1], int)
              for b in tri.blocks),
          f'实际 {tri.blocks[0].location}')


def main():
    print('=' * 68)
    print('mi 坐标类型回归（fatal error 修复）')
    print('=' * 68)
    t1_shuffle_keeps_int()
    t2_moves_keep_int()
    t3_find_best_window_no_crash()
    t4_gather_metrics_no_crash()
    t5_half_int_preserved()
    t6_knorm_loc_unit()
    t7_square_triangle_untouched()
    print('\n' + '=' * 68)
    if _failures:
        print(f'FAIL {len(_failures)}:')
        for f in _failures:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
