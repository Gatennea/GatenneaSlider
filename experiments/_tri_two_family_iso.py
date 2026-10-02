# -*- coding: utf-8 -*-
"""验证用户提案：三角形谜题「菱形复原 + 只用两个胞对齐方向族」是否与矩形谜题同构。

三个实验：
  T1  同构性：tri 菱形 M×N 胞 + 只许 h/p 两族  ↔  方形 M×N，可达状态集逐一相等
  T2  胞完整性不变量：{h,p} 下「▲▼同在」永远成立；一旦开 n 族立刻被破坏
  T3  形态谱系：tri{h,p,n} ↔ mi{h,v,d2} 的族/邻接/切胞对应，mi 多出的 d1 = 切开 ▲ 原子的那一族

跑法：python -u experiments/_tri_two_family_iso.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import Block, SliderMatrix
from game_triangle import (TriangleSliderMatrix, blocks_from_cells, tri_key,
                           GAP_DIRECTIONS, neighbors as tri_neighbors, side_of)
from game_mi import MiSliderMatrix, neighbors as mi_neighbors
from game_mi import side_of as mi_side_of

# ---------------------------------------------------------------- 工具

def rhombus_cells(M: int, N: int) -> set:
    """菱形复原态：M×N 个菱形胞，每胞 ▲+▼ 俱全（2MN 个单位三角）。"""
    cells = set()
    for i in range(M):
        for j in range(N):
            cells.add((i, j, True))
            cells.add((i, j, False))
    return cells


def cell_of(state: set) -> set:
    """三角位置集合 → 占用的菱形胞集合（每胞无论 ▲▼ 都折算一次）。"""
    return {(i, j) for (i, j, _up) in state}


def tri_norm(state) -> frozenset:
    """整体平移归一：按全部三角的 min(i,j) 挪到 (0,0)。

    整盘可以当一个连通分量整体滑走，所以原始状态空间是无穷的；
    与矩形谜题一样，比较状态必须先除掉这个平移自由度。
    注意必须按**三角**归一而不是按胞归一——半胞局面里 ▲▼ 不同胞，
    按胞折算会把两种不同局面混成同一个 key。
    """
    if not state:
        return frozenset()
    i0 = min(i for (i, _j, _u) in state)
    j0 = min(j for (_i, j, _u) in state)
    return frozenset((i - i0, j - j0, u) for (i, j, u) in state)


def sq_norm(state) -> frozenset:
    rs = [r for r, _ in state]
    cs = [c for _, c in state]
    return frozenset((r - min(rs), c - min(cs)) for (r, c) in state)


def is_cell_complete(state: set) -> bool:
    """胞完整性：每个菱形胞要么 ▲▼ 俱全、要么整个不在。"""
    for (i, j) in cell_of(state):
        if ((i, j, True) in state) != ((i, j, False) in state):
            return False
    return True


def make_tri(cells: set) -> TriangleSliderMatrix:
    g = TriangleSliderMatrix(2)
    g.blocks = blocks_from_cells(cells)
    g.update_matrix()
    return g


def tri_successors(state: frozenset, families: tuple, max_step: int) -> set:
    """tri 一步可达：只允许 families 里的方向族。

    选组结果必须按 (族, 线号, 起始块) 三元组缓存——opt 的结果同时依赖
    缝线和起始块，只按块缓存会让不同缝线复用同一个选组（曾导致 T1/T2 全错）。
    """
    g = make_tri(state)
    out = set()
    for gtype, line in g.all_gaps():
        if gtype not in families:
            continue
        sel_cache = {}
        for key in state:
            if key not in sel_cache:
                b = g.block_at(key)
                g.opt(gtype, line, b)
                sel = [bb for bb in g.blocks if bb.be_opted]
                sel_cache[key] = frozenset(tri_key(bb) for bb in sel)
            selkeys = sel_cache[key]
            if not selkeys or selkeys == state:
                continue
            for d in GAP_DIRECTIONS[gtype]:
                for step in range(1, max_step + 1):
                    pos, reason = g.try_move_ex(d, step)
                    if not pos:
                        break
                    new = (set(state) - set(selkeys)) | {tuple(p) for p in pos}
                    out.add(frozenset(new))
    return out


def make_sq(cells: set) -> SliderMatrix:
    g = SliderMatrix(1, 1)
    g.blocks = [Block([r, c]) for (r, c) in cells]
    g.update_matrix()
    return g


def sq_successors(state: frozenset, max_step: int) -> set:
    """方形一步可达。只取「两侧非空」的缝，与 tri 的 is_valid_gap 口径对齐。"""
    g = make_sq(state)
    bmap = {(r, c): Block([r, c]) for (r, c) in state}
    rows = [r for r, _ in state]
    cols = [c for _, c in state]
    gaps = []
    for line in range(min(rows), max(rows)):
        if any(r <= line for r, _ in state) and any(r > line for r, _ in state):
            gaps.append(('h', line))
    for line in range(min(cols), max(cols)):
        if any(c <= line for _, c in state) and any(c > line for _, c in state):
            gaps.append(('v', line))
    out = set()
    for gtype, line in gaps:
        sel_cache = {}
        for key in state:
            if key not in sel_cache:
                g.opt(gtype, line, bmap[key])
                sel = [bb for bb in g.blocks if bb.be_opted]
                sel_cache[key] = frozenset(tuple(bb.location) for bb in sel)
            selkeys = sel_cache[key]
            if not selkeys or selkeys == state:
                continue
            for d in ('a', 'd') if gtype == 'h' else ('w', 's'):
                for step in range(1, max_step + 1):
                    pos, reason = g.try_move_ex(d, step)
                    if not pos:
                        break
                    new = (set(state) - set(selkeys)) | {tuple(p) for p in pos}
                    out.add(frozenset(new))
    return out


def bfs(start: frozenset, succ, cap: int):
    seen = {start}
    frontier = [start]
    t0 = time.time()
    while frontier:
        nxt = []
        for s in frontier:
            for t in succ(s):
                if t not in seen:
                    seen.add(t)
                    nxt.append(t)
                    if len(seen) > cap:
                        return seen, False, time.time() - t0
        frontier = nxt
    return seen, True, time.time() - t0


# ---------------------------------------------------------------- T1

def T1(M: int, N: int, cap: int = 400000) -> bool:
    print(f'\n=== T1 菱形 {M}×{N} + {{h,p}} 两族  ↔  方形 {M}×{N} ===')
    start_tri = tri_norm(frozenset(rhombus_cells(M, N)))
    # 对应关系：菱形胞 (i,j) → 方形格 (row=j, col=i)。
    #   tri 'h' 族按 j 切行、沿 ±e1（改 i）动 = 方形「按行切、沿列动」
    #   tri 'p' 族按 i 切列、沿 ±e2（改 j）动 = 方形「按列切、沿行动」
    # 胞完整性成立时，两颗三角 ▲▼ 映到同一格，天然去重。
    def to_square(s):
        return frozenset((j, i) for (i, j, _u) in s)
    bad_cells = []

    def succ(s):
        out = set()
        for t in tri_successors(s, ('h', 'p'), M + N + 2):
            if not is_cell_complete(t):
                bad_cells.append(t)
            out.add(tri_norm(t))
        return out

    tri_states, ok1, t_tri = bfs(start_tri, succ, cap)
    start_sq = frozenset((j, i) for i in range(M) for j in range(N))
    sq_states, ok2, t_sq = bfs(
        start_sq,
        lambda s: {sq_norm(t) for t in sq_successors(s, M + N + 2)},
        cap)
    print(f'  tri 可达状态 {len(tri_states)}  ({t_tri:.1f}s, 跑完={ok1})')
    print(f'  方形可达状态 {len(sq_states)}  ({t_sq:.1f}s, 跑完={ok2})')
    print(f'  tri 破坏胞完整性的局面数：{len(bad_cells)}  ← 必须为 0')
    mapped = {to_square(s) for s in tri_states}
    same = (mapped == sq_states)
    print(f'  映射后状态集合逐一相等：{same}')
    if not same and ok1 and ok2:
        only_tri = mapped - sq_states
        only_sq = sq_states - mapped
        print(f'    仅 tri 有：{len(only_tri)}  仅方形有：{len(only_sq)}')
        for s in sorted(only_tri)[:3]:
            print(f'      仅 tri: {sorted(s)}')
        for s in sorted(only_sq)[:3]:
            print(f'      仅方形: {sorted(s)}')
    return same and not bad_cells


# ---------------------------------------------------------------- T2

def T2(M: int = 2, N: int = 3, depth: int = 7) -> None:
    print(f'\n=== T2 胞完整性不变量（菱形 {M}×{N}，{depth} 步）===')
    for fams in (('h', 'p'), ('h', 'p', 'n')):
        frontier = [tri_norm(frozenset(rhombus_cells(M, N)))]
        seen = set(frontier)
        bad = None
        reached = 0
        for d in range(depth):
            nxt = []
            for s in frontier:
                for t in tri_successors(s, fams, M + N + 2):
                    reached += 1
                    if not is_cell_complete(t):
                        bad = (d + 1, t)
                        break
                    nt = tri_norm(t)
                    if nt not in seen:
                        seen.add(nt)
                        nxt.append(nt)
                if bad:
                    break
            if bad:
                break
            frontier = nxt
        tag = '＋'.join(fams)
        if bad:
            step, st = bad
            print(f'  族 {tag:8s}：第 {step} 步出现半胞局面 '
                  f'（{len(st)} 颗三角，占胞 {sorted(cell_of(st))}）')
            print(f'                孤立原子示例：'
                  f'{sorted(cell_of(st) - {c for c in cell_of(st) if ((c[0], c[1], True) in st and (c[0], c[1], False) in st)})[:4]}')
        else:
            print(f'  族 {tag:8s}：{depth} 步内 {len(seen)} 个状态'
                  f'（{reached} 次转移），胞完整性全成立')


# ---------------------------------------------------------------- T3

_ATOM2MI = {True: (('N', 'W')), False: (('E', 'S'))}
_FAM2MI = {'h': 'v', 'p': 'h', 'n': 'd2'}


def T3(M: int = 2, N: int = 3) -> None:
    print(f'\n=== T3 形态谱系对应（菱形 {M}×{N} ↔ mi {M}×{N}）===')
    tri = make_tri(rhombus_cells(M, N))
    mi = MiSliderMatrix(M, N)
    tri_gaps = {}
    for fam in ('h', 'p', 'n'):
        tri_gaps[fam] = [ln for (t, ln) in tri.all_gaps() if t == fam]
    mi_gaps = {}
    for fam in ('h', 'v', 'd1', 'd2'):
        mi_gaps[fam] = [ln for (t, ln) in mi.all_gaps() if t == fam]
    print(f'  tri 有效缝线：' + '  '.join(f'{f}={len(v)}条' for f, v in tri_gaps.items()))
    print(f'  mi  有效缝线：' + '  '.join(f'{f}={len(v)}条' for f, v in mi_gaps.items()))

    def tri_sep(x, y):
        return {f for f, lines in tri_gaps.items()
                if any(side_of(f, ln, x) != side_of(f, ln, y) for ln in lines)}

    def mi_sep(u, v):
        return {f for f, lines in mi_gaps.items()
                if any(mi_side_of(f, ln, u) != mi_side_of(f, ln, v)
                       for ln in lines)}

    # (a) 相邻对：tri 的可分族集合 == mi 映射后相邻对的可分族集合
    bad = []
    pairs = 0
    atoms = sorted(rhombus_cells(M, N))
    for x in atoms:
        for y in tri_neighbors(x):
            if y not in atoms:
                continue
            pairs += 1
            want = {_FAM2MI[f] for f in tri_sep(x, y)}
            got = set()
            for qx in _ATOM2MI[x[2]]:
                for qy in _ATOM2MI[y[2]]:
                    ux = (x[0], x[1], qx)
                    uy = (y[0], y[1], qy)
                    if uy in mi_neighbors(ux):
                        got |= mi_sep(ux, uy)
            if want != got:
                bad.append((x, y, sorted(want), sorted(got)))
    print(f'  (a) 边相邻对 {pairs} 对，族分离对应不符：{len(bad)}')
    for row in bad[:4]:
        print(f'      {row[0]} ~ {row[1]}  期望 {row[2]}  实得 {row[3]}')

    # (b) 切胞：谁能把一个「胞」切成两半
    #   tri 的胞 = {▲,▼}；映射到 mi 是 {N,W} | {E,S} 两组原子。
    #   「切胞」= 把这两组分开 → 用跨组对测。
    #   「切原子」= 把同一组内部切开（如 N 与 W 分家）→ 用组内对测。
    print('  (b) 切胞 / 切原子：')
    tri_cut = {f: 0 for f in ('h', 'p', 'n')}
    for (i, j) in sorted({(i, j) for (i, j, _) in atoms}):
        for pair in (((i, j, True), (i, j, False)),):
            got = tri_sep(*pair)
            for f in tri_cut:
                if got == {f}:
                    tri_cut[f] += 1
    print(f'      tri 切胞  ：' + '  '.join(
        f'{f} {tri_cut[f]}/{M * N}' for f in ('h', 'p', 'n')) + '   (胞 = ▲|▼)')
    mi_cut, mi_atom = {}, {}
    for i in range(M):
        for j in range(N):
            got = mi_sep((i, j, 'N'), (i, j, 'E'))
            for f in ('h', 'v', 'd1', 'd2'):
                if got == {f}:
                    mi_cut[f] = mi_cut.get(f, 0) + 1
            got2 = mi_sep((i, j, 'N'), (i, j, 'W'))
            for f in ('h', 'v', 'd1', 'd2'):
                if got2 == {f}:
                    mi_atom[f] = mi_atom.get(f, 0) + 1
    print(f'      mi  切胞  ：' + '  '.join(
        f'{f} {mi_cut.get(f, 0)}/{M * N}' for f in ('h', 'v', 'd1', 'd2'))
        + '   (胞 = {N,W}|{E,S})')
    print(f'      mi  切原子：' + '  '.join(
        f'{f} {mi_atom.get(f, 0)}/{M * N}' for f in ('h', 'v', 'd1', 'd2'))
        + '   (原子 = N|W 同胞)')
    print('      → tri 的胞只有一条切法（n）；mi 的胞有两条切法（d1/d2）')
    print('      → 对应：tri h↔mi v, tri p↔mi h, tri n↔mi d2；mi 多出的 d1 是「切原子」那一刀，tri 里没有对应')


def T4(M: int = 2, N: int = 3) -> None:
    """三族为什么立刻破坏胞模型：n 族那一刀沿胞内对角线切开、且两侧朝不同方向走。

    n 缝把 ▲(i,j)（rank=i+j）和 ▼(i,j)（rank=i+j+1）分到两侧，选组时胞被切开；
    随后这一侧沿 ±(e2−e1) 平移 —— 该向量**不是**胞的平移方向（胞的两条边是
    e1、e2），所以配对被打散：▲ 与 ▼ 落到不同的胞。
    实测第一步就能造出只含▲或只含▼的胞（见 T2 输出）。
    """
    print(f'\n=== T4 n 族破坏胞模型的具体一步（菱形 {M}×{N}）===')
    tri = make_tri(frozenset(rhombus_cells(M, N)))
    for gtype, line in tri.all_gaps():
        if gtype != 'n':
            continue
        for key in sorted(rhombus_cells(M, N)):
            b = tri.block_at(key)
            tri.opt('n', line, b)
            sel = [bb for bb in tri.blocks if bb.be_opted]
            selk = {tri_key(bb) for bb in sel}
            cut = [c for c in {(i, j) for (i, j, _) in selk}
                   if ((c[0], c[1], True) in selk) != ((c[0], c[1], False) in selk)]
            if not cut:
                continue
            for d in ('w', 'x'):
                pos, reason = tri.try_move_ex(d, 1)
                if not pos:
                    continue
                new = frozenset(set(selk) | {tuple(p) for p in pos})
                if is_cell_complete(new):
                    continue
                ups = sorted({(i, j) for (i, j, u) in new if u})
                dns = sorted({(i, j) for (i, j, u) in new if not u})
                print(f'  n 缝 line={line}，选 {len(selk)} 颗，被切开的胞 {sorted(cut)}')
                print(f'  沿 {d!r}（n 向 ±(e2−e1)）滑 1 格后：')
                print(f'    占胞 {sorted(cell_of(new))}')
                print(f'    只有 ▲ 的胞（缺 ▼）：{sorted(set(ups) - set(dns))}')
                print(f'    只有 ▼ 的胞（缺 ▲）：{sorted(set(dns) - set(ups))}')
                print(f'    胞完整性：{is_cell_complete(new)}')
                print('  → 结论：只有 h/p 两族时胞模型封闭；开 n 族第一步就破。')
                return
    print('  （本尺寸未找到反例）')


def main():
    print('=' * 70)
    print('实验 1：菱形复原 + 两个胞对齐方向族 ⇒ 与矩形谜题同构？')
    print('实验 2：胞完整性在两族 / 三族下是否封闭')
    print('实验 3：tri 三族 ↔ 米字格 的族对应（子集关系的证据）')
    print('实验 4：三族下胞完整性为何仍成立')
    print('=' * 70)
    r1 = T1(2, 2)
    r2 = T1(2, 3)
    T1(3, 3, cap=800000)
    T2(depth=8)
    T3()
    T4()
    print('\n结论 T1：', '同构成立（三个尺寸全对）' if (r1 and r2) else '见上')


if __name__ == '__main__':
    main()