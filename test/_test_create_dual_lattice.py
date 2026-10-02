# -*- coding: utf-8 -*-
r"""mi 创造模式「双层晶格」校验回归（2026-10-03）。

背景：用户要做一种新构造（无限密铺 + 45° 正方形配对 + 旋转 90°），
现有创造模式摆不出来。定位到 gui/shape_validate.py 的两处缺口 +
一处缺失的闸门：

  1. `_match_anchor` 的偏移域只扫 [0,step)² 的整数格 → 错位态（B 晶格）
     的类键与对齐态完全不同，半格偏移 (0.5,0.5) 永远扫不到，所有错位构造
     被冤拒成「類計數不一致」。
  2. 混合态（A/B 两层同时有块）需要「按层分开比」的判据。
  3. **跨晶格正面積重疊闸门缺失**（用户 2026-10-03 明确指出）：错位态下
     位置 key 不同的两块可以疊在一起，引擎只在移动期查（_has_overlap），
     构造校验这条路径完全没走 → 能构造出游戏里走不出来的死盘，违反
     「所有合法局面都该由合法移动到达」的设计哲学。

覆盖：
    1. any_overlap 基本正确性（重叠/不重叠/同晶格不重叠/还原态）
    2. 纯 B 晶格错位态能通过 anchor 扫描（回归第 1 条）
    3. 重叠闸门拦截一个「块数正确 + 单连通 + 但重叠」的局面
    4. 闸门顺序：重叠原因优先于块数原因
    5. 方形态 / 三角形态零回归（偏移域未变）
    6. 偏移域形状：mi 是 4*step²，方形/三角仍是 step²

运行：D:\python\python.exe test\_test_create_dual_lattice.py
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


def _solved(m, n):
    from gui.shape_validate import _solved_positions
    return _solved_positions('mi', (m, n))


def t1_any_overlap():
    print('\n--- T1 any_overlap 基本正确性 ---')
    from game_mi import any_overlap, MiSliderMatrix
    check('T1a 还原态无重叠', not any_overlap(MiSliderMatrix(2, 2).positions()))
    # 重叠组合由几何决定：同格 A(0,0,E) ↔ B(0.5,0.5,N)、A(0,0,S) ↔ B(0.5,0.5,W)
    check('T1b A(0,0,E)+B(0.5,0.5,N) 判重叠',
          any_overlap({(0, 0, 'E'), (0.5, 0.5, 'N')}))
    check('T1c A(0,0,S)+B(0.5,0.5,W) 判重叠',
          any_overlap({(0, 0, 'S'), (0.5, 0.5, 'W')}))
    check('T1d A(0,0,N)+B(0.5,0.5,N) 不重叠（几何上分居两格）',
          not any_overlap({(0, 0, 'N'), (0.5, 0.5, 'N')}))
    check('T1e 同晶格永不重叠',
          not any_overlap({(0, 0, 'E'), (1, 1, 'N'), (2, 0, 'W')}))


def t2_shifted_anchor():
    print('\n--- T2 纯 B 晶格错位态能过 anchor ---')
    from gui import shape_validate as SV
    m, n, step = 2, 2, 2
    shifted = {(r + 0.5, c + 0.5, q) for (r, c, q) in _solved(m, n)}
    hit = SV._match_anchor('mi', shifted, (m, n), step)
    check('T2a 错位态 anchor 扫得到', hit is not None, f'anchor={hit}')
    #半格偏移的精确值由扫描次序决定（先整后半），可能是 (0.5,0.5) 也可能是
    # (0.0,0.5)/(0.5,0.0) —— 类计数表在 r/c 两个方向对称，扫到的第一个
    # 合法偏移不唯一。这里只断言「确实是半格偏移域里的点」，不锁具体值。
    check('T2b 扫到的是半格偏移域内的点',
          hit is not None and (float(hit[0]).is_integer() is False
                               or float(hit[1]).is_integer() is False),
          f'anchor={hit}')
    # 对齐态仍走整数偏移
    ok, msg, anchor = SV.validate_shape('mi', _solved(m, n), (m, n), step)
    check('T2c 对齐态仍被判「无空位」（回归正常）',
          (not ok) and '無空位' in msg, f'msg={msg!r}')


def t3_overlap_gate():
    print('\n--- T3 重叠闸门拦截合法块数的死盘 ---')
    from gui import shape_validate as SV
    from game_mi import MiSliderMatrix, any_overlap
    m, n, step = 3, 3, 2
    b = {(r + 0.5, c + 0.5, q) for (r, c, q) in _solved(m, n)}
    b.discard((0.5, 0.5, 'N'))
    b.add((0, 0, 'E'))          # 与B(0.5,0.5,N) 重叠，但那对已挖
    b.add((0.5, 0.5, 'N'))      # 补回来 → 制造 A(0,0,E) ↔ B(0.5,0.5,N) 重叠
    b.discard((0.5, 1.5, 'S'))  # 块数回到 4mn
    check('T3a 前置条件：块数正确', len(b) == 4 * m * n, f'块数={len(b)}')
    check('T3b 前置条件：单连通', MiSliderMatrix.is_single_connected(b))
    check('T3c 前置条件：确有重叠', any_overlap(b))
    ok, msg, _ = SV.validate_shape('mi', b, (m, n), step)
    check('T3d validate_shape 拦下重叠局面', not ok, f'msg={msg!r}')
    check('T3e 给出的是重叠原因（不是块数原因）',
          '重疊' in msg or '重叠' in msg, f'msg={msg!r}')


def t4_gate_order():
    print('\n--- T4 闸门顺序：重叠优先于块数 ---')
    from gui import shape_validate as SV
    from game_mi import any_overlap
    bad = {(0, 0, 'E'), (0.5, 0.5, 'N')}      # 重叠但块数远不够
    check('T4a 前置：确有重叠', any_overlap(bad))
    ok, msg, _ = SV.validate_shape('mi', bad, (2, 2), 2)
    check('T4b 重叠时优先报重叠', (not ok) and ('重疊' in msg or '重叠' in msg),
          f'msg={msg!r}')
    # 反向：块数不对但不重叠 → 应报块数
    noloop = {(r, c, 'N') for r in range(2) for c in range(2)}
    ok2, msg2, _ = SV.validate_shape('mi', noloop, (2, 2), 2)
    check('T4c 不重叠时正常报块数', (not ok2) and '滑塊數' in msg2,
          f'msg={msg2!r}')


def t5_no_regression():
    print('\n--- T5 方形态 / 三角形态零回归 ---')
    from gui import shape_validate as SV
    sq = {(r, c) for r in range(3) for c in range(3)}
    ok, msg, _ = SV.validate_shape('square', sq, (3, 3), 2)
    check('T5a 方形对齐态仍「无空位」', (not ok) and '無空位' in msg,
          f'msg={msg!r}')
    # 方形挖一补一（合法构造）：补格必须与主块 4-邻接连通
    # （补 (3,2) 会因只对角相邻而先被连通性闸门拒掉——那是闸门正常生效）
    sq2 = set(sq)
    sq2.discard((1, 1))
    sq2.add((1, 3))
    ok2, msg2, a2 = SV.validate_shape('square', sq2, (3, 3), 2)
    check('T5b 方形合法构造通过', ok2, f'msg={msg2!r} anchor={a2}')
    k = 3
    tri = {(i, j, True) for i in range(k) for j in range(k - i)}
    tri |= {(i, j, False) for i in range(k - 1) for j in range(k - 1 - i)}
    ok3, msg3, _ = SV.validate_shape('triangle', tri, (k,), 2)
    check('T5c 三角对齐态仍「无空位」', (not ok3) and '無空位' in msg3,
          f'msg={msg3!r}')


def t6_domain_shape():
    print('\n--- T6 偏移域形状 ---')
    from gui import shape_validate as SV
    for step in (1, 2, 3):
        d_mi = SV._anchor_domain('mi', step)
        d_sq = SV._anchor_domain('square', step)
        d_tri = SV._anchor_domain('triangle', step)
        check(f'T6a mi step={step} 偏移域=4·step²', len(d_mi) == 4 * step * step,
              f'实际 {len(d_mi)}')
        check(f'T6b square step={step} 偏移域=step²（未变）',
              len(d_sq) == step * step, f'实际 {len(d_sq)}')
        check(f'T6c triangle step={step} 偏移域=step²（未变）',
              len(d_tri) == step * step, f'实际 {len(d_tri)}')
        check(f'T6d mi 偏移域含半格', any(float(v).is_integer() is False
                                       for (dr, dc) in d_mi for v in (dr, dc)))


def t7_hit_two_lattices():
    print('\n--- T7 两层晶格都能被点中（根因回归）---')
    from gui.mi_view import MiBoardView
    v = MiBoardView(60.0, 4.0)

    def cen(r, c, q):
        p = v.piece_polygon(r, c, q, inset=False)
        return (sum(t[0] for t in p) / 3, sum(t[1] for t in p) / 3)

    # A 层（整数坐标）裸调用——正常游戏点选路径
    ok = bad = 0
    for r in range(4):
        for c in range(4):
            for q in ('N', 'E', 'S', 'W'):
                px, py = cen(r, c, q)
                if v.world_to_cell(px, py) == (r, c, q):
                    ok += 1
                else:
                    bad += 1
    check('T7a A层 64 块全部命中自身', ok == 64, f'命中 {ok}/64 失配 {bad}')
    # B 层（半整数坐标）裸调用——创造模式点错位块的路径
    ok = bad = 0
    for r in range(4):
        for c in range(4):
            for q in ('N', 'E', 'S', 'W'):
                px, py = cen(r + 0.5, c + 0.5, q)
                if v.world_to_cell(px, py) == (r + 0.5, c + 0.5, q):
                    ok += 1
                else:
                    bad += 1
    check('T7b B层 64 块全部命中自身（曾0/100）', ok == 64,
          f'命中 {ok}/64 失配 {bad}')
    # A/B 混合 + cells 过滤
    A = {(r, c, q) for r in range(4) for c in range(4)
         for q in ('N', 'E', 'S', 'W')}
    B = {(r + 0.5, c + 0.5, q) for r in range(4) for c in range(4)
         for q in ('N', 'E', 'S', 'W')}
    mix = A | B
    ok = bad = 0
    for k in mix:
        px, py = cen(*k)
        if v.world_to_cell(px, py, cells=mix) == k:
            ok += 1
        else:
            bad += 1
    check('T7c A/B 混合 128 块 + cells 过滤全命中', ok == 128,
          f'命中 {ok}/128 失配 {bad}')
    # 空位仍可命中（创造模式要能点空位新增块）
    px, py = cen(10.5, 10.5, 'N')
    check('T7d 空位裸调用返回 B 层 key（可新增）',
          v.world_to_cell(px, py) == (10.5, 10.5, 'N'),
          f'实得 {v.world_to_cell(px, py)}')


def t8_incoherent_coord_gate():
    """T8 奇偶一致性闸门——「重叠还能被构造出来」的根因回归。

    用户 2026-10-03 二次反馈：「现在仍然可以构造出重叠情况」。根因不在
    闸门位置（落盘确实走 validate_shape），而在两个洞：

      ① game_mi.lattice_of 只看 2r 的奇偶，把「r 整数 / c 半整数」这种
         奇偶不一致的非法坐标误判成 A 层 → any_overlap 的「同族不重叠」
         快速过滤直接跳过它。实测 (0,0,'E') 与 (0,0.5,'N') 几何上正面面积
         重叠（_tri_overlap=True）而 any_overlap 曾回 False。
      ② 创造模式的点选候选里一半是非法坐标：mi_view._hit_cells 对
         (r0±½, c0±½) 与 (r0−1,r0,r0+1) 取叉乘，于是 (0, 0.5)、(0.5, 0)
         随时点得出来（实测 121 个候选里 60 个是这种），而引擎照单全收
         （blocks_from_cells / update_matrix / export⇄import 全部正常）。

    且这种坐标能同时骗过三道判据：cell_class 把半整数整数化，所以
    (0.5, 0) 的类算成 (0,0)——和真 A 层同类，类计数表看不出。
    """
    print('\n--- T8 奇偶一致性闸门（重叠漏判的根因）---')
    from game_mi import (MiSliderMatrix, any_overlap, _tri_overlap,
                         coords_coherent, sublattice_of, lattice_of)
    from gui import shape_validate as SV

    def par2(x):
        return int(round(2.0 * x)) & 1

    # (a) lattice_of 对奇偶不一致坐标的误判（这是根因，留作证据）
    check('T8a lattice_of 把 (0,0.5) 误判成 A 层（已知缺陷，仍在）',
          lattice_of((0, 0.5, 'N')) == 0
          and par2(0) != par2(0.5),
          f'lattice_of={lattice_of((0, 0.5, "N"))} 而 2r&1={par2(0)} 2c&1={par2(0.5)}')
    check('T8b sublattice_of 对同一坐标判为独立族（修复后的判据）',
          sublattice_of((0, 0.5, 'N')) == (0, 1),
          f'实得 {sublattice_of((0, 0.5, "N"))}')

    # (b) any_overlap 现在能抓到这组重叠（修复前 False）
    pair = {(0, 0, 'E'), (0, 0.5, 'N')}
    check('T8c 该对几何上确实重叠', _tri_overlap((0, 0, 'E'), (0, 0.5, 'N')))
    check('T8d any_overlap 曾漏判，现在能抓到', any_overlap(pair),
          '修复前=False')

    # (c) 「同一 sublattice 族内永不重叠」——快速过滤的正确性依据
    qs = ('N', 'E', 'S', 'W')
    groups = {}
    for r in [x / 2 for x in range(-2, 5)]:
        for c in [x / 2 for x in range(-2, 5)]:
            groups.setdefault(sublattice_of((r, c)), []).append((r, c))
    inner = 0
    for cs in groups.values():
        for i, (r1, c1) in enumerate(cs):
            for (r2, c2) in cs[i + 1:]:
                for q1 in qs:
                    for q2 in qs:
                        if _tri_overlap((r1, c1, q1), (r2, c2, q2)):
                            inner += 1
    check('T8e 同一族内零重叠（快速过滤有依据）', inner == 0, f'实测 {inner} 对')

    # (d) 命中层确实能产出奇偶不一致坐标（问题的可达性）
    from gui.mi_view import MiBoardView
    v = MiBoardView(60.0, 4.0)
    seen = set()
    for wy in range(0, 120, 15):
        for wx in range(0, 120, 15):
            seen.update(v._hit_cells(wx, wy))
    mixed = [(r, c) for (r, c) in sorted(seen) if par2(r) != par2(c)]
    check('T8f 命中候选含奇偶不一致坐标（所以闸门必要）', len(mixed) > 0,
          f'{len(mixed)}/{len(seen)} 个候选非法')

    # (e) 闸门拦下奇偶不一致局面，且报出正确原因
    m, n = 3, 3
    base = _solved(m, n)
    bad = set(base)
    bad.discard((0, 0, 'E'))
    bad.add((0, 0.5, 'N'))
    ok, msg, _ = SV.validate_shape('mi', bad, (m, n), 2)
    check('T8g 奇偶不一致局面被拦下', not ok, f'msg={msg!r}')
    check('T8h 报错指向坐标合法性（而非块数/连通性）',
          '奇偶' in msg or '走不' in msg, f'msg={msg!r}')

    # (f) 合法局面零误报：随机走 400 步，coherent 全真且 any_overlap 全否
    import random
    from game_mi import GAP_DIRECTIONS
    random.seed(9)
    fp = incoherent = tot = 0
    for _t in range(40):
        step = random.choice([1, 2, 3])
        g = MiSliderMatrix(3, 3)
        g.shuffle(20, step)
        for _ in range(10):
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
            cells = g.positions()
            tot += 1
            if any_overlap(cells):
                fp += 1
            if not coords_coherent(cells):
                incoherent += 1
    check('T8i 400 步真实局面：any_overlap 零误报', fp == 0, f'误报 {fp} 次')
    check('T8j 400 步真实局面：coherent 全真（游戏不变量）',
          incoherent == 0, f'不一致 {incoherent} 次')
    check('T8k 随机走总步数符合预期', tot == 400, f'{tot} 步')

    # (g) 纯 B 整盘错位态（合法）不被误拦
    pureB = {(r + 0.5, c + 0.5, q) for r in range(m) for c in range(n)
             for q in ('N', 'E', 'S', 'W')}
    check('T8l 纯B 整盘错位态 coherent', coords_coherent(pureB))
    check('T8m 纯B 整盘错位态无重叠', not any_overlap(pureB))
    ok2, msg2, _ = SV.validate_shape('mi', pureB, (m, n), 2)
    check('T8n 纯B 错位态不被坐标闸门误拦', '奇偶' not in msg2,
          f'msg={msg2!r}（報「無空位」= 已过坐标与重叠闸门，是还原态，正确）')


def main():
    print('=' * 68)
    print('mi 创造模式「双层晶格」校验回归')
    print('=' * 68)
    t1_any_overlap()
    t2_shifted_anchor()
    t3_overlap_gate()
    t4_gate_order()
    t5_no_regression()
    t6_domain_shape()
    t7_hit_two_lattices()
    t8_incoherent_coord_gate()
    print('\n' + '=' * 68)
    if _failures:
        print(f'FAIL {len(_failures)}:')
        for f in _failures:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()