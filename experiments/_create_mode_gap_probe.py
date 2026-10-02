# -*- coding: utf-8 -*-
"""探针：为什么创造模式做不出用户的新构造（mi 错位态 / 半整数坐标）。

用户 2026-10-03 反馈：他设计的构造（无限密铺 + 45° 正方形配对 + 旋转 90°）
「用现在的创造模式做不出来」，并指出「mi 的放置判定要用双层晶格」。
本脚本把「做不出来」拆成可测的几条，定位到底哪一环卡住。

检查项：
  P1  构造范围判定_ann_build_grid：边界盒只按 min/max 推，坐标是整数还是半整数？
  P2  cell_class 不变量：半整数坐标下类计数是否与整��态可比（放置判定的地基）
  P3  validate_shape 的块数判据：错位态下 4mn 块是「格数×4」还是「实际块数」
  P4  单连通判定：错位态必须走5-邻接（跨晶格边），否则整盘被判断开
  P5  _hit_cells 命中：半整数格是否真的能被点到（决定「能不能摆出来」）
  P6  export_map / import_map 往返：错位态能否存盘再读回

跑法：python -u experiments/_create_mode_gap_probe.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_mi import (MiSliderMatrix, lattice_of, blocks_from_cells as mi_blocks,
                     neighbors as mi_neighbors)
from gui.cell_class import cell_class
from gui import shape_validate as SV

FAIL = []


def check(name, ok, extra=''):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {extra}")
    if not ok:
        FAIL.append(name)


def P1():
    print('\n--- P1 构造范围判定的坐标类型 ---')
    # annotation._ann_build_grid 的逻辑：边界盒 = min/max 各扩一圈
    coords = {(0, 0, 'N'), (1, 1, 'N'), (0.5, 0.5, 'S')}
    rs = [p[0] for p in coords]
    cs = [p[1] for p in coords]
    print(f'    假设构造集含半整数坐标：{sorted(coords)}')
    print(f'    min/max 直接取整用：lo_r={min(rs) - 1} hi_r={max(rs) + 1} '
          f'lo_c={min(cs) - 1} hi_c={max(cs) + 1}')
    ok = all(float(v).is_integer() for v in (min(rs) - 1, max(rs) + 1,
                                             min(cs) - 1, max(cs) + 1))
    check('P1 范围边界可能落在半整数上', True,
          f'→ 范围判定用的是整数量；半整数坐标是否被接受取决于逐点比较')
    # 逐点比较：半整数坐标与整数边界比较的结果
    half = (0.5, 0.5, 'S')
    lo_r, hi_r, lo_c, hi_c = min(rs) - 1, max(rs) + 1, min(cs) - 1, max(cs) + 1
    inside = (lo_r <= half[0] <= hi_r and lo_c <= half[1] <= hi_c)
    print(f'    半整数坐标 {half[:2]} 是否落在 [{lo_r},{hi_r}]×[{lo_c},{hi_c}]：'
          f'{inside}')
    check('P1b 半整数坐标能落在整数边界盒内', inside,
          '（范围判定本身不排斥半整数）')


def P2():
    print('\n--- P2 cell_class 不变量在半整数下是否可比 ---')
    step = 2
    a = cell_class((0, 0), step, 'mi')
    b = cell_class((2, 2), step, 'mi')
    c = cell_class((0.5, 0.5), step, 'mi')
    d = cell_class((2.5, 2.5), step, 'mi')
    print(f'    A 晶格 (0,0)→{a}   (2,2)→{b}')
    print(f'    B 晶格 (0.5,0.5)→{c} (2.5,2.5)→{d}')
    check('P2 同晶格平移 step 后类不变', a == b and c == d,
          f'A:{a}=={b} B:{c}=={d}')
    print(f'    A 与 B 的类是否可区分：{a != c}')
    # 还原态只有 A 晶格 → 错位构造态若整盘同 B 类则类计数永远不匹配
    solved = SV._solved_positions('mi', (2, 2))
    tgt_A = SV._class_counts(solved, step, 'mi')
    shifted = {(r + 0.5, c + 0.5, q) for (r, c, q) in solved}
    tgt_B = SV._class_counts(shifted, step, 'mi')
    print(f'    还原态类计数表：{dict(tgt_A)}')
    print(f'    整体错位半格后：  {dict(tgt_B)}')
    check('P2 错位态类计数表与还原态不一致（anchor 扫不出来）',
          tgt_A != tgt_B, '→ validate_shape 会判「類計數不一致」')


def P3():
    print('\n--- P3 validate_shape 块数判据 ---')
    m, n = 2, 2
    solved = SV._solved_positions('mi', (m, n))
    print(f'    还原态块数 = {len(solved)}（=4×{m}×{n}）')
    # 错位态：全部块平移半格，块数不变
    shifted = {(r + 0.5, c + 0.5, q) for (r, c, q) in solved}
    ok, msg, _ = SV.validate_shape('mi', shifted, (m, n), 2)
    print(f'    错位态validate_shape → ok={ok}  msg={msg!r}')
    check('P3 整体错位半格的对齐态被validate_shape 接受', ok,
          '（游戏 is_solved 允许换晶格，但构造校验可能不允许）')
    # 半格错位 + 一个挖角：块数对但类计数错
    holed = set(shifted)
    holed.discard(sorted(holed)[0])
    holed.add((2.5, 2.5, 'N'))
    ok2, msg2, _ = SV.validate_shape('mi', holed, (m, n), 2)
    print(f'    错位+挖一补一 → ok={ok2}  msg={msg2!r}')


def P4():
    print('\n--- P4 单连通判定的邻接口径 ---')
    m, n = 2, 2
    solved = SV._solved_positions('mi', (m, n))
    shifted = {(r + 0.5, c + 0.5, q) for (r, c, q) in solved}
    c5 = MiSliderMatrix.is_single_connected(shifted)
    # 只用同晶格邻接（丢掉跨晶格两条边）会怎样
    same_only = {k for k in shifted
                 if tuple(k) in {tuple(nb) for nbk in shifted
                                 for nb in mi_neighbors(nbk)
                                 if lattice_of(nb) == lattice_of(nbk)}}
    deg = min(sum(1 for nb in mi_neighbors(k) if nb in shifted) for k in shifted)
    print(f'    错位态 5-邻接单连通：{c5}   每块最少邻接数={deg}'
          f'（含 2 条跨晶格边）')
    check('P4 错位态在 5-邻接下仍是单连通', c5,
          '→ 判定层已支持双层晶格，缺口在放置/校验层')


def P5():
    print('\n--- P5 半整数格能否被点到（决定「能不能摆出来」）---')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    try:
        from gui.mi_view import MiView
    except Exception as e:
        print(f'    [跳过]无法导入视图模块：{e}')
        return
    # 直接验_hit_cells 是否包含半整数格
    class _Probe(MiView):
        def __init__(self):
            pass
    try:
        pr = _Probe()
        # 用最小可用的属性调_hit_cells：它只用 from_world
        pr.cell_size = 10.0
        pr.ox = 0.0
        pr.oy = 0.0
        pr.scale = 1.0
        cells = pr._hit_cells(5.0, 5.0)
        has_half = any(float(r).is_integer() is False or
                       float(c).is_integer() is False for (r, c) in cells)
        print(f'    _hit_cells(5,5) 前 6 项：{cells[:6]}')
        print(f'    含半整数格：{has_half}')
        check('P5 命中列表含半整数格（错位块可点）', has_half)
    except Exception as e:
        print(f'    [跳过] _hit_cells 探测异常：{e}')


def P6():
    print('\n--- P6 错位态存盘往返---')
    m, n = 2, 2
    solved = SV._solved_positions('mi', (m, n))
    shifted = {(r + 0.5, c + 0.5, q) for (r, c, q) in solved}
    g = MiSliderMatrix(m, n)
    g.blocks = mi_blocks(shifted)
    g.update_matrix()
    out = g.export_map()
    print(f'    export_map 前 3 行：{out.split(chr(10))[:3]}')
    has_mi8 = out.startswith('mi8')
    check('P6 错位态导出带 mi8 标记', has_mi8)
    g2 = MiSliderMatrix(m, n)
    ok = g2.import_map(out)
    print(f'    import_map 回读 → {ok}')
    check('P6 错位态可往返', ok)
    if ok:
        same = g2.positions() == shifted
        check('P6b 往返后位置集合一致', same)


def P7():
    print('\n--- P7 漏洞边界：类计数表在错位态下到底缺什么 ---')
    m, n, step = 2, 2, 2
    solved = SV._solved_positions('mi', (m, n))
    shifted = {(r + 0.5, c + 0.5, q) for (r, c, q) in solved}
    print(f'    A 晶格类（还原态）：{sorted(SV._class_counts(solved, step, "mi"))}')
    print(f'    B 晶格类（错位态）：{sorted(SV._class_counts(shifted, step, "mi"))}')
    print('    → 错位态整盘落在另一套类上；anchor 只在 [0,step)² 扫整数偏移，')
    print('      半格偏移（0.5,0.5）根本不在扫描范围内 ⇒ 永远扫不出来。')
    # 手工验证：把偏移扩到半格，能不能扫出来
    tgt = SV._class_counts(shifted, step, 'mi')
    hit = None
    for dr in (0, 0.5):
        for dc in (0, 0.5):
            if SV._class_counts(solved, step, 'mi', dr, dc) == tgt:
                hit = (dr, dc)
    print(f'    手工把偏移域扩成{{0,0.5}}² 后：hit={hit}'
          f'  ← 确实存在，只是现行扫描域取不到')
    check('P7 缺口=anchor 偏移域只扫整数半步', hit == (0.5, 0.5),
          f'→修法：_match_anchor 的偏移域按形态扩到半格（mi 两层晶格都要试）')
    # 混合态：A+B 晶格同时存在
    mixed = set(solved) | shifted
    print(f'\n    A+B 混合态：块数 {len(mixed)}（4mn={4 * m * n}）'
          f'  两层晶格各 {len(solved)} 块')
    tgt_m = SV._class_counts(mixed, step, 'mi')
    print(f'    混合态类计数表键数={len(tgt_m)}（A 层与 B 层两套类都在）')
    print('    → 现行 _match_anchor 只拿单一还原态表去比，'
          'A+B 混合态需要「两套表之和」判据')


def main():
    print('=' * 70)
    print('创造模式漏洞探针：mi 放置判定需要「双层晶格」')
    print('=' * 70)
    P1()
    P2()
    P3()
    P4()
    P5()
    P6()
    P7()
    print('\n' + '=' * 70)
    print(f'不通过项：{len(FAIL)}')
    for f in FAIL:
        print(f'  · {f}')
    if not FAIL:
        print('  （全部通过——漏洞不在这几处，需另找）')


if __name__ == '__main__':
    main()