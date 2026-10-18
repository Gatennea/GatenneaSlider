# -*- coding: utf-8 -*-
"""统一板型适配器：方形 / 三角 / 米字格 → 同一套枚举接口（板型 B）。

几何、缝、方向生成元全部来自各自游戏模块（真源），本文件只做归一化。每个板型暴露：

    goal_cells()                 还原态（三角只给一个代表姿态，见下注）
    is_connected(cells)          该形态邻接下的连通性
    canonical(cells)             平移规范化键（去重）
    color_sig(cells, step)       守恒着色签名（cell_class = 平移格子Δ的陪集×朝向）
    _all_seams(cells)            全部候选缝 (gap_type, line)
    forward_moves(cells, step)   全部合法前向移动 (new_cells, moved_comp, dvec)
    is_selectable(cells,comp,d)  落位分量 comp 能否被某条「平行于 d」的缝单独框住
                                 （能=可选中→非粘连；不能=粘连→定理所指机制）

注：三角还原态（正三角形）有 120°/240° 旋转+反射等价，S₀ 是「轨道」非单点；
本模块只给一个代表姿态，完整 cone 需多源种子（异形方案 §4.2 待办）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from solver import table_core as tc  # noqa: E402
import game_triangle as tri  # noqa: E402
import game_mi as mi  # noqa: E402
from gui.cell_class import cell_class  # noqa: E402


def _same(a, b):
    return abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9


def components_within(side_cells, neighbors_fn):
    """在某一侧的格集内按邻接求连通分量。"""
    comps, seen = [], set()
    for start in side_cells:
        if start in seen:
            continue
        stack, comp = [start], set()
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            for nb in neighbors_fn(cur):
                if nb in side_cells and nb not in comp:
                    stack.append(nb)
        seen |= comp
        comps.append(comp)
    return comps


class SquareBoard:
    kind = 'square'

    def __init__(self, m, n):
        self.m, self.n, self.K = m, n, m * n

    def goal_cells(self):
        return frozenset(tc.goal_state(self.m, self.n))

    def is_connected(self, cells):
        return tc.is_single_connected(cells)

    def canonical(self, cells):
        return tc.canonicalize(cells)

    def color_sig(self, cells, step):
        return tuple(sorted(cell_class(c, step, 'square') for c in cells))

    def _all_seams(self, cells):
        rows = [r for r, _ in cells]
        cols = [c for _, c in cells]
        out = [('h', L) for L in range(min(rows), max(rows))]
        out += [('v', L) for L in range(min(cols), max(cols))]
        return out

    def forward_moves(self, cells, step):
        B = set(cells)
        total = self.K
        out = []
        for L in range(min(r for r, _ in B), max(r for r, _ in B)):
            for side in ('above', 'below'):
                for comp in tc._side_components(B, 'h', L, side):
                    for sign in (-1, 1):
                        r = self._try(B, comp, (0, sign), step, total)
                        if r is not None:
                            out.append((r, frozenset(comp), (0, sign)))
        for L in range(min(c for _, c in B), max(c for _, c in B)):
            for side in ('left', 'right'):
                for comp in tc._side_components(B, 'v', L, side):
                    for sign in (-1, 1):
                        r = self._try(B, comp, (sign, 0), step, total)
                        if r is not None:
                            out.append((r, frozenset(comp), (sign, 0)))
        return out

    def _try(self, B, comp, dunit, step, total):
        non_sel = B - set(comp)
        cur = set(comp)
        for _ in range(step):
            cur = {(r + dunit[0], c + dunit[1]) for r, c in cur}
            if cur & non_sel:
                return None
            if not tc.is_single_connected(cur | non_sel):
                return None
        res = non_sel | cur
        return res if len(res) == total else None

    def shift(self, comp, dvec, step):
        """平移后的落位分量 C'（定理里的 C′ 就是它，不是平移前的 comp）。"""
        return frozenset((r + dvec[0] * step, c + dvec[1] * step) for r, c in comp)

    def is_selectable(self, cells, comp, dvec):
        """方形：水平移动只能被水平缝(h)选中，垂直移动只能被竖缝(v)选中（同轴）。"""
        B, comp = set(cells), set(comp)
        if _same((dvec[0], 0), (0, 0)) and not _same((0, dvec[1]), (0, 0)):
            gapt, rng = 'h', range(min(r for r, _ in B), max(r for r, _ in B))
        elif _same((0, dvec[1]), (0, 0)) and not _same((dvec[0], 0), (0, 0)):
            gapt, rng = 'v', range(min(c for _, c in B), max(c for _, c in B))
        else:
            return False
        for L in rng:
            for side in (('above', 'below') if gapt == 'h' else ('left', 'right')):
                for c2 in tc._side_components(B, gapt, L, side):
                    if c2 == comp:
                        return True   # 被某条同轴缝单独框住 → 可选中
        return False                  # 无同轴缝能框住 → 粘连


class _TriMi:
    """三角 / 米字格共用的 move 枚举与可选中判定。"""

    def _dir_parallel(self, gap_type, dvec):
        vec = self.DIR
        return any(_same(vec[l], dvec) or _same(vec[l], (-dvec[0], -dvec[1]))
                   for l in self.GD[gap_type])

    def _add(self, cell, dvec):
        return (cell[0] + dvec[0], cell[1] + dvec[1], cell[2])

    def shift(self, comp, dvec, step):
        return frozenset((c[0] + dvec[0] * step, c[1] + dvec[1] * step, c[2])
                         for c in comp)

    def forward_moves(self, cells, step):
        B = set(cells)
        total = len(B)
        out = []
        for gap_type, line in self._all_seams(B):
            sides = {0: set(), 1: set()}
            for c in B:
                sides[self.side_of(gap_type, line, c)].add(c)
            if not sides[0] or not sides[1]:
                continue
            for side in (0, 1):
                for comp in components_within(sides[side], self.NB):
                    for letter in self.GD[gap_type]:
                        dvec = self.DIR[letter]
                        r = self._translate(B, comp, dvec, step, total)
                        if r is not None:
                            out.append((r, frozenset(comp), dvec))
        return out

    def _translate(self, B, comp, dvec, step, total):
        non_sel = B - set(comp)
        cur = set(comp)
        for _ in range(step):
            cur = {self._add(c, dvec) for c in cur}
            if cur & non_sel:
                return None
            if not self.is_connected(cur | non_sel):
                return None
        res = non_sel | cur
        return res if len(res) == total else None

    def is_selectable(self, cells, comp, dvec):
        B, comp = set(cells), set(comp)
        for gap_type, line in self._all_seams(B):
            if not self._dir_parallel(gap_type, dvec):
                continue
            sides = {0: set(), 1: set()}
            for c in B:
                sides[self.side_of(gap_type, line, c)].add(c)
            if not sides[0] or not sides[1]:
                continue
            for side in (0, 1):
                for c2 in components_within(sides[side], self.NB):
                    if c2 == comp:
                        return True    # 可被某条平行缝单独框住 → 可选中
        return False                   # 否则粘连


class TriangleBoard(_TriMi):
    kind = 'triangle'
    NB = staticmethod(tri.neighbors)
    GD = tri.GAP_DIRECTIONS
    DIR = tri.DIRECTIONS

    def __init__(self, k):
        self.k, self.K = k, k * k
        self._goal = frozenset(tri.TriangleSliderMatrix(k).goal_cells())

    def goal_cells(self):
        return self._goal

    def is_connected(self, cells):
        return tri.TriangleSliderMatrix.is_single_connected(set(cells))

    def canonical(self, cells):
        cs = list(cells)
        mi_ = min(c[0] for c in cs)
        mj = min(c[1] for c in cs)
        return frozenset((c[0] - mi_, c[1] - mj, c[2]) for c in cs)

    def color_sig(self, cells, step):
        return tuple(sorted(cell_class(c, step, 'triangle') for c in cells))

    def side_of(self, gap_type, line, key):
        return tri.side_of(gap_type, line, key)

    def _all_seams(self, cells):
        return [(gt, line)
                for gt in ('h', 'p', 'n')
                for line in tri.gap_index_range(gt, cells)]


class MiBoard(_TriMi):
    kind = 'mi'
    NB = staticmethod(mi.neighbors)
    GD = mi.GAP_DIRECTIONS
    DIR = mi.DIRECTIONS

    def __init__(self, m, n):
        self.m, self.n, self.K = m, n, 4 * m * n
        self._goal = frozenset((r, c, q) for r in range(m) for c in range(n)
                               for q in ('N', 'E', 'S', 'W'))

    def goal_cells(self):
        return self._goal

    def is_connected(self, cells):
        cs = set(cells)
        if not cs:
            return True
        start = next(iter(cs))
        seen, stack = {start}, [start]
        while stack:
            cur = stack.pop()
            for nb in mi.neighbors(cur):
                if nb in cs and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        return len(seen) == len(cs)

    def canonical(self, cells):
        cs = list(cells)
        mr = min(c[0] for c in cs)
        mc = min(c[1] for c in cs)
        return frozenset((round((c[0] - mr) * 2), round((c[1] - mc) * 2), c[2])
                         for c in cs)

    def color_sig(self, cells, step):
        return tuple(sorted(cell_class(c, step, 'mi') for c in cells))

    def side_of(self, gap_type, line, key):
        return mi.side_of(gap_type, line, key)

    def _all_seams(self, cells):
        out = []
        for gt in ('h', 'v', 'd1', 'd2'):
            for line in mi.gap_candidates(gt, cells):
                if self._seam_ok(gt, line, cells):
                    out.append((gt, line))
        return out

    @staticmethod
    def _seam_ok(gt, line, cells):
        if {mi.side_of(gt, line, c) for c in cells} != {0, 1}:
            return False
        for c in cells:
            lo, hi = mi.span(gt, c)
            if lo < line < hi:
                return False
        return True
