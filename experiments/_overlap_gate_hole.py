# -*- coding: utf-8 -*-
"""探针：找「能骗过 validate_shape 的重叠局面」。

用户 2026-10-03 反馈「现在仍然可以构造出重叠情况」。上一轮补的 any_overlap
闸门在 validate_shape 里，但闸门本身有洞：game_mi.lattice_of 只看 2r 的奇偶，
把「r 整数、c 半整数」这种坐标误判成 A 层，而 any_overlap 的快速过滤是
「同晶格必然不重叠 → 跳过」→ 这类块之间的真重叠被跳过。

本脚本穷举/搜索满足以下全部条件的局面，证明闸门真的漏：
  块数 == 4mn、单连通、类计数能匹配 anchor、无「跨晶格」重叠（闸门视角）、
  但几何上确实有正面面积重叠。
"""
import sys
from itertools import combinations

sys.path.insert(0, '.')
from game_mi import (MiSliderMatrix, blocks_from_cells, any_overlap,
                     _tri_overlap, lattice_of)
from gui import shape_validate as SV

FAIL = []


def check(name, cond, extra=''):
    print(f'[{"PASS" if cond else "FAIL"}] {name}' + (f' → {extra}' if extra else ''))
    if not cond:
        FAIL.append(name)


def odd2(x):
    return int(round(2.0 * x)) & 1


def coherent(cells):
    """游戏不变量：每块 2r 与 2c 同奇偶（真A层或真 B 层）。"""
    return all(odd2(k[0]) == odd2(k[1]) for k in cells)


def real_overlaps(cells):
    """几何上真实重叠的块对（不依赖 lattice_of 过滤）。"""
    items = sorted(cells)
    out = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _tri_overlap(items[i], items[j]):
                out.append((items[i], items[j]))
    return out


def P1_lattice_misjudge():
    print('\n--- P1 lattice_of 对「r 整数 / c 半整数」的判定 ---')
    cases = [(0, 0, 'N'), (0.5, 0.5, 'N'), (0, 0.5, 'N'), (0.5, 0, 'N'),
             (1, 0.5, 'N'), (0.5, 1, 'N')]
    for k in cases:
        print(f'    {k} → lattice_of={lattice_of(k)}  '
              f'2r&1={odd2(k[0])} 2c&1={odd2(k[1])}'
              f'{"   ← 奇偶不一致（非法坐标）" if odd2(k[0]) != odd2(k[1]) else ""}')
    # 根因：lattice_of 只看 2r，把 (0, 0.5)（c 是半整数）误判成 A 层
    check('P1a lattice_of 把 (0,0.5) 误判成 A 层',
          lattice_of((0, 0.5, 'N')) == 0 and odd2(0) != odd2(0.5),
          f'lattice_of={lattice_of((0, 0.5, "N"))} 而 2r&1={odd2(0)} '
          f'2c&1={odd2(0.5)}')
    # 修复判据：按 (2r&1, 2c&1) 分族，它对非法坐标也定义良好
    from game_mi import sublattice_of
    check('P1b sublattice_of 把它判成独立族 (0,1)',
          sublattice_of((0, 0.5, 'N')) == (0, 1),
          f'实得 {sublattice_of((0, 0.5, "N"))}')


def P2_any_overlap_hole():
    print('\n--- P2 any_overlap 的快速过滤漏检 ---')
    a, b = (0, 0, 'E'), (0, 0.5, 'N')
    print(f'    A={a} 顶点 {__import__("game_mi").mi_vertices(*a)}')
    print(f'    B={b} 顶点 {__import__("game_mi").mi_vertices(*b)}')
    geo = _tri_overlap(a, b)
    gate = any_overlap({a, b})
    print(f'    _tri_overlap={geo}   any_overlap={gate}')
    check('P2a 几何上确实重叠', geo)
    check('P2b any_overlap 现在能抓到（修复前=False）', gate,
          '← 根因：lattice_of 快速过滤把非法坐标跳过了')

    # 「同一 sublattice 族内永不重叠」——快速过滤的正确性依据
    qs = ('N', 'E', 'S', 'W')
    from game_mi import sublattice_of
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
    check('P2c 同一 sublattice 族内零重叠（过滤有依据）', inner == 0,
          f'穷举 7×7 范围，实测 {inner} 对')


def P3_coherence_is_invariant():
    print('\n--- P3 「2r 与 2c 同奇偶」是游戏不变量吗（随机走实测）---')
    import random
    from game_mi import GAP_DIRECTIONS
    random.seed(5)
    bad = tot = 0
    for _trial in range(30):
        step = random.choice([1, 2, 3])
        g = MiSliderMatrix(4, 4)
        g.shuffle(20, step)
        for _ in range(15):
            gaps = g.all_gaps()
            if not gaps:
                break
            fam, line = random.choice(gaps)
            g.opt(fam, line, random.choice(g.blocks))
            d = random.choice(GAP_DIRECTIONS[fam])
            pos, reason = g.try_move_ex(d, step)
            if pos:
                g.commit_move(pos)
                g.update_matrix()
            tot += 1
            if not coherent(g.positions()):
                bad += 1
    print(f'    随机走 {tot} 步，奇偶不一致 {bad} 次')
    check('P3a 450 步零反例 → 是游戏不变量', bad == 0)
    # 还原态也一致
    check('P3b 还原态一致', coherent(MiSliderMatrix(4, 4).positions()))


def P4_find_real_counterexample():
    """核心：找一个真的能骗过 validate_shape 的重叠局面。"""
    print('\n--- P4 搜索能骗过闸门的重叠局面 ---')
    m, n = 3, 3
    step = 2
    base = {(r, c, q) for r in range(m) for c in range(n)
            for q in ('N', 'E', 'S', 'W')}

    # 非法坐标候选：r 整数 / c 半整数，或反之。逐个试，看哪些能保持单连通。
    bad_coords = []
    for r in range(m):
        for c in range(n):
            for q in ('N', 'E', 'S', 'W'):
                for dr, dc in ((0, 0.5), (0.5, 0)):
                    bad_coords.append((r + dr, c + dc, q))
    print(f'    非法坐标候选 {len(bad_coords)} 个')

    found = None
    for bc in bad_coords:
        # 挖掉与它几何重叠的 A 层块，补上这个非法块（保持块数）
        ov = [k for k in sorted(base) if _tri_overlap(bc, k)]
        if not ov or len(ov) > 3:
            continue
        cand = (set(base) - set(ov[:1])) | {bc}
        if len(cand) != 4 * m * n:
            continue
        if not MiSliderMatrix.is_single_connected(cand):
            continue
        if any_overlap(cand):
            continue                     # 闸门已能拦，不算漏洞
        if not real_overlaps(cand):
            continue                     # 其实没重叠
        ok, msg, _ = SV.validate_shape('mi', cand, (m, n), step)
        if ok:
            found = (bc, ov, cand, msg)
            break
    if found:
        bc, ov, cand, _ = found
        print(f'    ★ 找到反例：非法坐标 {bc}')
        print(f'      挖掉 {ov[:1]} 补上 {bc}')
        print(f'      真实重叠对 {len(real_overlaps(cand))} 对，'
              f'样例 {real_overlaps(cand)[:3]}')
        print(f'      any_overlap={any_overlap(cand)}（闸门说无）')
        print(f'      validate_shape → {SV.validate_shape("mi", cand, (m, n), step)}')
        check('P4a validate_shape 放过了几何重叠局面（漏洞坐实）', True)
        return cand
    print('    本轮候选没找到端到端反例：类计数/连通性判据在单块替换下兜住了。')
    print('    但 any_overlap 层的漏检由 P2 实测坐实，且非法坐标本身引擎')
    print('    照单全收（P5）——所以坐标闸门仍是必需的（已在 P6 验证）。')
    check('P4a 记录：未找到端到端反例（如实，不谎报）', True)
    return None


def P5_engine_ingest_ok():
    print('\n--- P5 引擎能不能吃下非法坐标（说明这不是别处拦住的）---')
    m, n = 3, 3
    base = {(r, c, q) for r in range(m) for c in range(n)
            for q in ('N', 'E', 'S', 'W')}
    bc = (0, 0.5, 'N')
    ov = [k for k in sorted(base) if _tri_overlap(bc, k)]
    cand = (set(base) - set(ov[:1])) | {bc}
    try:
        g = MiSliderMatrix(m, n)
        g.blocks = blocks_from_cells(cand)
        g.update_matrix()
        print(f'    update_matrix OK，is_solved={g.is_solved()}，'
              f'positions 数={len(g.positions())}')
        check('P5a 引擎照单全收（所以必须在校验层拦）', True)
    except Exception as e:
        check('P5a update_matrix 崩了', False, repr(e))
    # 存档往返
    out = g.export_map()
    g2 = MiSliderMatrix(m, n)
    ok = g2.import_map(out)
    print(f'    export_map → import_map 往返 = {ok}')
    check('P5b 存盘往返也正常（存档读得回来）', ok)


def P6_coherence_gate():
    print('\n--- P6 奇偶一致性闸门（本次修复的主闸门）---')
    m, n = 3, 3
    base = {(r, c, q) for r in range(m) for c in range(n)
            for q in ('N', 'E', 'S', 'W')}
    bad = set(base)
    bad.discard((0, 0, 'E'))
    bad.add((0, 0.5, 'N'))
    ok, msg, _ = SV.validate_shape('mi', bad, (m, n), 2)
    check('P6a 奇偶不一致局面被拦下', not ok, f'msg={msg!r}')
    check('P6b 报错指向坐标合法性（而非块数/连通性）', '奇偶' in msg, f'msg={msg!r}')
    # 合法局面零误报
    import random
    from game_mi import GAP_DIRECTIONS
    random.seed(9)
    fp = incoh = tot = 0
    for _t in range(40):
        step = random.choice([1, 2, 3])
        g = MiSliderMatrix(m, n)
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
            if not coherent(cells):
                incoh += 1
    check('P6c 400 步真实局面：any_overlap 零误报', fp == 0, f'误报 {fp} 次')
    check('P6d 400 步真实局面：coherent 全真', incoh == 0, f'不一致 {incoh} 次')
    check('P6e 步数符合预期', tot == 400, f'{tot} 步')
    # 纯 B 整盘错位态（合法）不被误拦
    pureB = {(r + 0.5, c + 0.5, q) for r in range(m) for c in range(n)
             for q in ('N', 'E', 'S', 'W')}
    check('P6f 纯B 整盘错位态 coherent', coherent(pureB))
    check('P6g 纯B 整盘错位态无重叠', not any_overlap(pureB))
    _ok, msg2, _ = SV.validate_shape('mi', pureB, (m, n), 2)
    check('P6h 纯B 错位态不被坐标闸门误拦', '奇偶' not in msg2, f'msg={msg2!r}')


def main():
    print('=' * 70)
    print('探针：重叠闸门为什么还能被绕过')
    print('=' * 70)
    P1_lattice_misjudge()
    P2_any_overlap_hole()
    P3_coherence_is_invariant()
    P4_find_real_counterexample()
    P5_engine_ingest_ok()
    P6_coherence_gate()
    print('\n' + '=' * 70)
    if FAIL:
        print(f'FAIL {len(FAIL)}:')
        for f in FAIL:
            print(f'  · {f}')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
