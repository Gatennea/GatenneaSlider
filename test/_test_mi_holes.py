# -*- coding: utf-8 -*-
r"""mi 洞 / 凸起检测回归（M3 F2 面板数据源）。

覆盖：
  H1  还原态无洞无凸起
  H2  抽掉窗口正中一格的四片 → 一个「孔洞」（不连到窗口边缘）
  H3  抽掉窗口边缘一格 → 「缺口」
  H4  凸起 = 目标形狀外的單元
  H5  **只用同晶格 3 邻接**：跨晶格邻接不得参与，否则每個洞都变缺口
  H6  半格（四分之一格）粒度：缺 1 片 ≠ 缺 4 片，大小分档按片数
  H7  数据同源：goal 必须是 best_placement(...).cells，检测不另算
  H8  退化输入不崩（空 coords / goal 为空 / 全部缺失）

运行：D:\python\python.exe -u test\_test_mi_holes.py
"""

import os
import sys

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

_F = []


def check(name, cond, extra=''):
    print(f'[{"PASS" if cond else "FAIL"}] {name}' + (f'  {extra}' if extra else ''))
    if not cond:
        _F.append(name)


def _mk(cells):
    from game_mi import MiSliderMatrix, blocks_from_cells
    g = MiSliderMatrix(1, 1)
    g.blocks = blocks_from_cells(cells)
    g.update_matrix()
    return g


def h1_solved_no_holes():
    print('\n--- H1 还原态无洞无凸起 ---')
    from game_mi import MiSliderMatrix
    from solver.ml.mi_holes import detect_mi_holes
    from solver.ml.mi_placement import best_placement
    for m, n in ((3, 3), (4, 4), (4, 3)):
        g = MiSliderMatrix(m, n)
        best = best_placement(g.positions(), m, n, 1)
        holes, prot = detect_mi_holes(g.positions(), best.cells, 1)
        check(f'H1a {m}x{n} 还原态无洞', not holes, f'{len(holes)} 个')
        check(f'H1b {m}x{n} 还原态无凸起', not prot, f'{len(prot)} 个')


def h2_inner_hole():
    print('\n--- H2 抽掉正中一格 → 孔洞 ---')
    from game_mi import MiSliderMatrix
    from solver.ml.mi_holes import detect_mi_holes
    from solver.ml.mi_placement import goal_shape
    goal = goal_shape(5, 5)
    mid = (2, 2)
    cells = frozenset(goal - {(mid[0], mid[1], q)
                              for q in ('N', 'E', 'S', 'W')})
    holes, prot = detect_mi_holes(cells, goal, 1)
    check('H2a 检出 1 个洞', len(holes) == 1, f'{[(h["type"], len(h["cells"])) for h in holes]}')
    if holes:
        check('H2b 类型是 hole（不连到边缘）', holes[0]['type'] == 'hole',
              holes[0]['type'])
        check('H2c 含 4 片', len(holes[0]['cells']) == 4, len(holes[0]['cells']))
        check('H2d cells_geo 指向缺的那一格',
              holes[0]['cells_geo'] == [mid], holes[0]['cells_geo'])


def h3_edge_gap():
    print('\n--- H3 抽掉边缘一格 → 缺口 ---')
    from solver.ml.mi_holes import detect_mi_holes
    from solver.ml.mi_placement import goal_shape
    goal = goal_shape(5, 5)
    for edge in ((0, 2), (4, 2), (2, 0), (2, 4)):
        cells = frozenset(goal - {(edge[0], edge[1], q)
                                  for q in ('N', 'E', 'S', 'W')})
        holes, _ = detect_mi_holes(cells, goal, 1)
        check(f'H3a 边缘格 {edge} 检出 1 个洞', len(holes) == 1, str(len(holes)))
        if holes:
            check(f'H3b 边缘格 {edge} 类型是 gap',
                  holes[0]['type'] == 'gap', holes[0]['type'])


def h4_protrusions():
    print('\n--- H4 凸起 = 目标形狀外的單元 ---')
    from solver.ml.mi_holes import detect_mi_holes, PROTRUSION_COLOR
    from solver.ml.mi_placement import goal_shape
    goal = goal_shape(3, 3)
    extra = {(3, 3, 'N'), (3, 4, 'E')}
    cells = frozenset(goal | extra)
    holes, prot = detect_mi_holes(cells, goal, 1)
    check('H4a 凸起被检出', set(prot) == extra, f'{sorted(prot)}')
    check('H4b 凸起不产生洞', not holes, f'{len(holes)} 个')
    check('H4c 凸起颜色已定义', PROTRUSION_COLOR == (255, 210, 60),
          str(PROTRUSION_COLOR))


def h5_same_lattice_only():
    print('\n--- H5 洪水填充只用同晶格邻接（跨晶格会毁掉判定）---')
    from game_mi import MiSliderMatrix, neighbors as nb, sublattice_of
    from solver.ml.mi_holes import _same_lattice_neighbors
    # 构造一个 A 档键，检查过滤后只剩 3 条
    same = _same_lattice_neighbors((0, 0, 'N'))
    check('H5a A 档片只留 3 条同晶格邻接', len(same) == 3, str(same))
    check('H5b 全是 A 档', all(sublattice_of(k) == (0, 0) for k in same))
    same_b = _same_lattice_neighbors((0.5, 0.5, 'N'))
    check('H5c B 档片也只留 3 条', len(same_b) == 3, str(same_b))
    check('H5d B 档全是 B', all(sublattice_of(k) == (1, 1) for k in same_b))
    # 关键行为断言：错位态的洞不应被判成 gap
    from solver.ml.mi_holes import detect_mi_holes
    from solver.ml.mi_placement import goal_shape
    goal_b = goal_shape(5, 5)
    shifted = frozenset((r + 0.5, c + 0.5, q) for r, c, q in goal_b)
    hollow = frozenset(shifted - {(2.5, 2.5, q)
                                  for q in ('N', 'E', 'S', 'W')})
    holes, _ = detect_mi_holes(hollow, shifted, 1)
    check('H5e 错位态(B 档)的正中洞仍判为 hole 而非 gap',
          len(holes) == 1 and holes[0]['type'] == 'hole',
          f'{[(h["type"], len(h["cells"])) for h in holes]}')


def h6_quarter_granularity():
    print('\n--- H6 四分之一格粒度：大小分档按片数 ---')
    from solver.ml.mi_holes import detect_mi_holes
    from solver.ml.mi_placement import goal_shape
    goal = goal_shape(4, 4)
    # 缺 1 片（相邻片仍在）→ 小洞
    one = frozenset(goal - {(1, 1, 'N')})
    h1, _ = detect_mi_holes(one, goal, 2)
    check('H6a 缺 1 片检出 1 个洞', len(h1) == 1, str(len(h1)))
    if h1:
        check('H6b 缺 1 片 = 小洞（step=2 门槛 16 片）', h1[0]['size'] == 'small',
              f"{h1[0]['size']} size={len(h1[0]['cells'])}")
    # 缺整整 2×2 格 = 16 片 → 大洞
    many = frozenset(goal - {(r, c, q)
                             for r in (1, 2) for c in (1, 2)
                             for q in ('N', 'E', 'S', 'W')})
    h2, _ = detect_mi_holes(many, goal, 2)
    total = sum(len(h['cells']) for h in h2)
    check('H6c 缺 2×2 格共 16 片', total == 16, f'{total} 片 / {len(h2)} 个洞')
    check('H6d 其中有大洞', any(h['size'] == 'large' for h in h2),
          str([(h['size'], len(h['cells'])) for h in h2]))


def h7_same_source():
    print('\n--- H7 数据同源（計劃 §4 铁律）---')
    from game_mi import MiSliderMatrix
    from solver.ml import mi_holes
    from solver.ml.mi_holes import detect_mi_holes
    from solver.ml.mi_placement import best_placement
    import inspect
    src = inspect.getsource(mi_holes.detect_mi_holes)
    check('H7a detect_mi_holes 的 docstring 写明 goal 须带放置偏移',
          'MiPlacement.cells' in src or 'best_placement' in
          (mi_holes.detect_mi_holes.__doc__ or ''),
          'goal 参数文档')
    # 真跑一次：goal 来自 best_placement，洞的位置应落在该放置内
    g = MiSliderMatrix(4, 4)
    g.blocks = g.blocks[:60]      # 抽掉 4 块造一个洞
    g.update_matrix()
    best = best_placement(g.positions(), 4, 4, 1)
    holes, prot = detect_mi_holes(g.positions(), best.cells, 1)
    inside = all(c in best.cells for h in holes for c in h['cells'])
    check('H7b 洞的每一片都落在 best_placement.cells 内', inside,
          f'{len(holes)} 个洞')
    check('H7c 凸起全部在 best_placement.cells 外',
          all(c not in best.cells for c in prot), f'{len(prot)} 个凸起')


def h8_degenerate():
    print('\n--- H8 退化输入不崩 ---')
    from solver.ml.mi_holes import detect_mi_holes
    from solver.ml.mi_placement import goal_shape
    goal = goal_shape(3, 3)
    holes, prot = detect_mi_holes(set(), goal, 1)
    check('H8a 空盘面：整个窗口是一个大缺口', len(holes) == 1
          and holes[0]['type'] == 'gap' and len(holes[0]['cells']) == 36,
          f'{[(h["type"], len(h["cells"])) for h in holes]}')
    holes, prot = detect_mi_holes(goal, set(), 1)
    check('H8b 空 goal：全部是凸起', len(prot) == 36 and not holes,
          f'{len(prot)} 凸起 / {len(holes)} 洞')
    holes, prot = detect_mi_holes(goal, goal, 1)
    check('H8c 完全重合：无洞无凸起', not holes and not prot)


def main():
    print('=' * 70)
    print('mi 洞 / 凸起检测回归（M3 F2 面板数据源）')
    print('=' * 70)
    h1_solved_no_holes()
    h2_inner_hole()
    h3_edge_gap()
    h4_protrusions()
    h5_same_lattice_only()
    h6_quarter_granularity()
    h7_same_source()
    h8_degenerate()
    print('\n' + '=' * 70)
    if _F:
        print(f'FAIL {len(_F)}:')
        for f in _F:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
