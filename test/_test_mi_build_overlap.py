# -*- coding: utf-8 -*-
r"""米字格创造模式「点选增删造成直接重叠」回归（2026-10-23）。

bug：米字格谜题在创造模式（手动构造 / 设计态）中增删方块有可能导致直接
重叠——双层晶格（A 整数 / B 半整数）的三角形几何上互相重叠，而构造画布
的落点解析与增删闸门都只按「位置 key 集合」判，挡不住 key 不同却几何
相叠的两块。方形 / 三角没有双层晶格，不受影响。

两条触发路径（本文件各覆盖一条）：
  1. **落点误配**：满盘上点已有方块靠格心的一角，裸 world_to_cell 的
     「就近取用」把点击解析成另一层的空位 key → 「点方块删它」变成
     「在它上面再放一块」，直接重叠。
  2. **追加重叠**：落点解析出（或玩家途经其它入口得到）一个会与已有
     方块几何重叠的位置，_ann_build_toggle 直接收下。

修法（全在 gui/annotation.py，不动几何引擎）：
  - `_ann_mi_canvas_pick` 两段式解析：先在构造集里挑已有方块（点删），
    挑不到才裸解析空位（点放）；
  - `_ann_build_toggle` 米字追加前过引擎 `any_overlap` 重叠闸门。

运行：D:\python\python.exe test\_test_mi_build_overlap.py
"""

import os
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


def _new_gui():
    from GUI import SliderGUI
    gui = SliderGUI(m=5, n=5, step=2)
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    if gui.triangle_mode or gui.mi_mode:
        gui.new_puzzle(5, 5, 2)
    return gui


def _enter_mi_build(gui, shuffle_steps=0):
    """创造模式 + 米字谜题 + 进手动构造（画布初始 = 当前局面）。"""
    gui.game_mode = 'create'
    assert gui.new_mi_puzzle(6, 6, 2)
    if shuffle_steps:
        gui.game.shuffle(shuffle_steps, gui.current_step)
    gui._ann_btn_manual_build()
    assert gui._ann_view == 'build', f"view={gui._ann_view}"
    return gui


def _click_pt(gui, gx, gy):
    """格坐标 → 屏幕坐标（经 world_to_screen，与真实点击同一条路）。"""
    wx, wy = gui._mi_view().to_world(gx, gy)
    return gui.world_to_screen(wx, wy)


def _click_world(gui, wx, wy):
    """世界坐标（像素）→ 屏幕坐标。"""
    return gui.world_to_screen(wx, wy)


def _no_overlap(cells):
    from game_mi import any_overlap
    return not any_overlap(cells)


def t1_pick_misresolve():
    print('\n--- T1 落点误配：重叠区的点击必须解析到已有方块 ---')
    from gui.mi_view import MiBoardView
    from game_mi import any_overlap
    gui = _enter_mi_build(_new_gui())
    coords = set(gui._ann_build_coords)
    v = gui._mi_view()
    check('T1a 画布初始为对齐态满盘', len(coords) == 144 and _no_overlap(coords))
    # 已知误配点（格坐标）：都在已有 A 方块的三角形内、且裸解析会返回
    # 不在盘上的 B 层/非法 key——旧代码在这里「点方块 → 叠一块」。
    pts = [(0.9, 0.68), (0.95, 0.9), (0.68, 0.9), (0.6, 0.62),
           (5.1, 5.4), (2.4, 2.9)]
    bad_old = 0
    for gx, gy in pts:
        wx, wy = v.to_world(gx, gy)
        bare = v.world_to_cell(wx, wy)           # 旧路径：裸解析
        if bare is not None and bare not in coords:
            bad_old += 1
            # 旧路径把这块放进去就会直接重叠（bug 本体）
            check(f'T1b 旧路径在 ({gx},{gy}) 解析出空位key {bare} 且会重叠',
                  any_overlap(coords | {bare}))
        sx, sy = _click_pt(gui, gx, gy)
        pick = gui._ann_mi_canvas_pick(sx, sy)   # 新路径：两段式
        check(f'T1c 新路径在 ({gx},{gy}) 解析到已有方块',
              pick is not None and pick in coords, f'pick={pick}')
    check('T1d 旧路径在这些点上确实全部误配（bug 证据）', bad_old == len(pts),
          f'{bad_old}/{len(pts)}')


def t2_add_gate():
    print('\n--- T2 追加重叠闸门：会叠在一起的方块放不进去 ---')
    from game_mi import any_overlap
    gui = _enter_mi_build(_new_gui())
    coords = set(gui._ann_build_coords)
    n_blocks = len(gui.game.blocks)
    # 与已有 A 方块几何重叠的 B 层位置（key 不同，集合判据放它过去）
    for pos in [(0.5, 0.5, 'N'), (0.5, 0.5, 'W'), (2.5, 2.5, 'E')]:
        check(f'T2a 前置：{pos} 与满盘几何重叠', any_overlap(coords | {pos}))
        gui._ann_build_toggle(pos)
        check(f'T2b 追加重叠被拒（{pos}）', bool(gui._ann_build_error)
              and '重叠' in gui._ann_build_error, f'err={gui._ann_build_error!r}')
        check(f'T2c 构造集未变（{pos}）', pos not in gui._ann_build_coords
              and gui._ann_build_coords == coords)
        check(f'T2d 棋盘未重建、块数不变（{pos}）',
              len(gui.game.blocks) == n_blocks)
    check('T2e 全程无重叠', _no_overlap(gui._ann_build_coords))
    # 非法坐标（r 整 / c 半，游戏走不出来）且几何重叠的，同样被闸门拦下
    gui._ann_build_toggle((0, 0.5, 'N'))
    check('T2f 奇偶不一致且重叠的追加也被拒',
          bool(gui._ann_build_error) and '重叠' in gui._ann_build_error,
          f'err={gui._ann_build_error!r}')


def t3_roundtrip_all_blocks():
    print('\n--- T3 全盘逐块点选往返：删得了、放得回、永不重叠 ---')
    from game_mi import mi_vertices
    gui = _enter_mi_build(_new_gui())
    coords0 = set(gui._ann_build_coords)
    v = gui._mi_view()
    n = len(coords0)
    for k in sorted(coords0):
        # 点块内心 → 命中自己 → 删
        sx, sy = _click_world(gui, *v.incenter(*k))
        pick = gui._ann_mi_canvas_pick(sx, sy)
        assert pick == k, f'pick={pick} != {k}'
        gui._ann_build_toggle(pick)
        assert k not in gui._ann_build_coords
        assert _no_overlap(gui._ann_build_coords)
        # 再点同一处 → 空位（裸解析）→ 放回
        pick2 = gui._ann_mi_canvas_pick(sx, sy)
        assert pick2 == k, f'pick2={pick2} != {k}'
        gui._ann_build_toggle(pick2)
        assert k in gui._ann_build_coords
        assert _no_overlap(gui._ann_build_coords)
    check(f'T3a {n} 块全部删放往返成功', gui._ann_build_coords == coords0)
    check('T3b 往返后仍无重叠', _no_overlap(gui._ann_build_coords))
    # 每块的「靠外角」误配热点：新路径必须解析到已有方块（旧路径会放叠块）
    hot = 0
    for k in sorted(coords0):
        cx, cy = v.incenter(*k)
        far = max(v.to_world(*p) for p in mi_vertices(*k))
        fx, fy = far
        # 朝所选顶点走 85%（落在跨层误配热点里）
        gx = (cx + 0.85 * (fx - cx)) / v.cell_size
        gy = (cy + 0.85 * (fy - cy)) / v.cell_size
        sx, sy = _click_pt(gui, gx, gy)
        pick = gui._ann_mi_canvas_pick(sx, sy)
        if pick in gui._ann_build_coords:
            hot += 1
            before = set(gui._ann_build_coords)
            gui._ann_build_toggle(pick)
            assert _no_overlap(gui._ann_build_coords)
            assert len(gui._ann_build_coords) == len(before) - 1
            gui._ann_build_toggle(pick)      # 放回，保持满盘
            assert gui._ann_build_coords == before
    check('T3c 全部热点点击都落到已有方块上（无误配放叠块）', hot == n,
          f'{hot}/{n}')


def t4_mixed_lattice():
    print('\n--- T4 混合晶格（错位态）：B 层块点得中、放得回 ---')
    gui = _enter_mi_build(_new_gui())
    # 用引擎走一步斜向，制造合法的 A/B 混合态
    g = gui.game
    d1 = [gp for gp in g.all_gaps() if gp[0] == 'd1']
    g.opt(*d1[len(d1) // 2], g.blocks[0])
    pos = g.try_move('x', 1)
    check('T4a 引擎斜向一步成功', bool(pos))
    g.commit_move(pos)
    gui._ann_btn_manual_build()            # 以混合态进构造
    coords = set(gui._ann_build_coords)
    b_keys = [k for k in coords if not float(k[0]).is_integer()]
    check('T4b 混合态含 B 层块且合法', len(b_keys) > 0 and _no_overlap(coords),
          f'B 层 {len(b_keys)} 颗')
    v = gui._mi_view()
    # 点 B 层块内心 → 命中自己（2026-10-03「就近取用」能力不退化）
    k = b_keys[0]
    sx, sy = _click_world(gui, *v.incenter(*k))
    pick = gui._ann_mi_canvas_pick(sx, sy)
    check('T4c 点 B 层块命中自己', pick == k, f'pick={pick}')
    gui._ann_build_toggle(pick)
    check('T4d B 层块删得掉', k not in gui._ann_build_coords)
    check('T4e 删除后无重叠', _no_overlap(gui._ann_build_coords))
    # 空位再点 → 放回（混合态摆块能力不退化）
    pick2 = gui._ann_mi_canvas_pick(sx, sy)
    check('T4f 空位裸解析放回 B 层块', pick2 == k, f'pick2={pick2}')
    gui._ann_build_toggle(pick2)
    check('T4g 放回后复原且无重叠',
          gui._ann_build_coords == coords and _no_overlap(gui._ann_build_coords))
    # 混合态上追一个会重叠的位置 → 闸门照拦
    overlapper = None
    for cand in [(r + 0.5, c + 0.5, q)
                 for r in range(6) for c in range(6) for q in 'NESW']:
        if cand not in coords:
            from game_mi import any_overlap
            if any_overlap(coords | {cand}):
                overlapper = cand
                break
    if overlapper is None:
        check('T4h 找到混合态上的重叠候选', False, '枚举失败')
    else:
        gui._ann_build_toggle(overlapper)
        check('T4h 混合态上追加重叠同样被拒',
              bool(gui._ann_build_error) and '重叠' in gui._ann_build_error
              and overlapper not in gui._ann_build_coords,
              f'err={gui._ann_build_error!r}')


def t5_numbered_order():
    print('\n--- T5 编号谜题：拒绝重叠放置不吃掉编号 ---')
    gui = _enter_mi_build(_new_gui())
    gui._ann_build_numbered = True
    gui._ann_build_numbers = {}
    gui._ann_build_num_stack = [7]
    coords = set(gui._ann_build_coords)
    gui._ann_build_toggle((0.5, 0.5, 'N'))     # 会重叠 → 应被闸门拦下
    check('T5a 重叠放置被拒', bool(gui._ann_build_error)
          and '重叠' in gui._ann_build_error, f'err={gui._ann_build_error!r}')
    check('T5b 编号栈未被吃掉', gui._ann_build_num_stack == [7])
    check('T5c 编号表未变', gui._ann_build_numbers == {})
    check('T5d 构造集未变', gui._ann_build_coords == coords)


def t6_other_shapes():
    print('\n--- T6 方形 / 三角零回归（无双层晶格，不走新闸门）---')
    for shape, setup in (('square', lambda g: g.new_puzzle(6, 6, 2)),
                         ('triangle', lambda g: g.new_triangle_puzzle(6, 2))):
        gui = _new_gui()
        gui.game_mode = 'create'
        setup(gui)
        gui.game.shuffle(20, gui.current_step)
        gui._ann_btn_manual_build()
        coords0 = set(gui._ann_build_coords)
        pos = next(iter(sorted(coords0)))
        gui._ann_build_toggle(pos)
        # ⚠️ 失败时**必须打印错误串**：2026-10-30 全套里 triangle 这两条红过一次
        # （单跑 11 次 + 按种子扫 40 次都全绿，没能复现），而当时 extra 是空的，
        # 事后完全无法判断是「闸门误伤」还是「删放没生效」。带上 err 才有下次。
        check(f'{shape} 移除一块', pos not in gui._ann_build_coords
              and len(gui._ann_build_coords) == len(coords0) - 1,
              f'err={gui._ann_build_error!r} pos={pos} n={len(coords0)}')
        gui._ann_build_toggle(pos)
        check(f'{shape} 放回复原', gui._ann_build_coords == coords0,
              f'err={gui._ann_build_error!r}')
        check(f'{shape} 无重叠闸门误伤（错误为空）', gui._ann_build_error == '',
              f'err={gui._ann_build_error!r}')


def main():
    print('=' * 68)
    print('米字格创造模式「点选增删造成直接重叠」回归')
    print('=' * 68)
    t1_pick_misresolve()
    t2_add_gate()
    t3_roundtrip_all_blocks()
    t4_mixed_lattice()
    t5_numbered_order()
    t6_other_shapes()
    print('\n' + '=' * 68)
    if _failures:
        print(f'FAIL {len(_failures)}:')
        for f in _failures:
            print('  · ' + f)
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
