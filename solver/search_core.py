# -*- coding: utf-8 -*-
"""坐标级搜索核心（尺寸无关，无预建表）。

提供：
    expand(coords, step)            - 逐分量展开 [(new_coords, action, rep)]
    best_window / fast_window       - 最佳目标窗口、缺口、凸起识别
    heuristic                       - 距矩形的启发值
    guided_reduce_one               - GBFS 至少填一个洞（逐次消解多缺口）
"""
import heapq

from solver.table_core import (canonicalize, _side_components,
                               is_single_connected)

DCHAR = {(0, 1): 'd', (0, -1): 'a', (1, 0): 's', (-1, 0): 'w'}
DDIR = {v: k for k, v in DCHAR.items()}


# ---------- 纯坐标逐分量展开 ----------
def expand(coords, step):
    B = set(coords)
    total = len(B)
    out = []
    rows = [r for r, _ in B]
    cols = [c for _, c in B]

    def go(comp, gt, L, side, D):
        du = (D[0] // step if D[0] else 0, D[1] // step if D[1] else 0)
        non = B - set(comp)
        cur = set(comp)
        for _ in range(step):
            cur = {(r + du[0], c + du[1]) for r, c in cur}
            if cur & non or not is_single_connected(cur | non):
                return
        res = frozenset(non | cur)
        if len(res) == total:
            out.append((res, (gt, L, side, DCHAR[du]), next(iter(comp))))

    for L in range(min(rows), max(rows)):
        for side in ('above', 'below'):
            for comp in _side_components(B, 'h', L, side):
                for sgn in (-1, 1):
                    go(comp, 'h', L, side, (0, sgn * step))
    for L in range(min(cols), max(cols)):
        for side in ('left', 'right'):
            for comp in _side_components(B, 'v', L, side):
                for sgn in (-1, 1):
                    go(comp, 'v', L, side, (sgn * step, 0))
    return out


# ---------- 窗口 / 缺口 / 凸起 ----------
def best_window(coords, m, n):
    B = set(coords)
    rs = [r for r, _ in B]
    cs = [c for _, c in B]
    best = None
    for h, w in ((m, n), (n, m)):
        for r0 in range(min(rs) - 1, max(rs) - h + 2):
            for c0 in range(min(cs) - 1, max(cs) - w + 2):
                win = set((r, c) for r in range(r0, r0 + h)
                          for c in range(c0, c0 + w))
                inside = len(win & B)
                holes, protr = win - B, B - win
                score = (inside, -(abs(r0 - min(rs)) + abs(c0 - min(cs))))
                if best is None or score > best[0]:
                    best = (score, (r0, c0, h, w), holes, protr)
    return best[1], best[2], best[3]


def fast_window(coords, m, n):
    """启发用快速窗口，保证不返回 None。"""
    B = set(coords)
    rs = [r for r, _ in B]
    cs = [c for _, c in B]
    minr, maxr, minc, maxc = min(rs), max(rs), min(cs), max(cs)
    best = None
    for h, w in ((m, n), (n, m)):
        rlo, rhi = minr - 1, max(maxr - h + 2, minr + 1)
        clo, chi = minc - 1, max(maxc - w + 2, minc + 1)
        for r0 in range(rlo, min(rhi, rlo + 5)):
            for c0 in range(clo, min(chi, clo + 5)):
                win = set((r, c) for r in range(r0, r0 + h)
                          for c in range(c0, c0 + w))
                inside = len(win & B)
                if best is None or inside > best[0]:
                    best = (inside, (r0, c0, h, w), win - B, B - win)
    if best is not None:
        return best[1], best[2], best[3]
    win = set((r, c) for r in range(minr, maxr + 1)
              for c in range(minc, maxc + 1))
    return (minr, minc, maxr - minr + 1, maxc - minc + 1), win - B, B - win


def is_edge_hole(h, win):
    r0, c0, hh, ww = win
    r, c = h
    return r in (r0, r0 + hh - 1) or c in (c0, c0 + ww - 1)


def component_of(coords, action, rep):
    gt, L, side, _d = action
    comps = _side_components(set(coords), gt, L, side)
    return next((c for c in comps if rep in c), None)


# ---------- 启发 ----------
def heuristic(coords, m, n, step):
    _win, holes, protr = fast_window(coords, m, n)
    h = len(holes)
    for p in protr:
        if holes:
            d = min(abs(p[0] - q[0]) + abs(p[1] - q[1]) for q in holes)
            h += max(1, d // step)
    return h


# ---------- GBFS：至少填一个洞 ----------
def guided_reduce_one(coords, m, n, step, budget=80000, cancel_check=None):
    start = frozenset(coords)
    h0 = len(fast_window(start, m, n)[1])
    counter = 0
    openq = [(h0, 0, 0, start, [])]
    bestg = {canonicalize(start): 0}
    closed = set()
    expanded = 0
    while openq:
        _f, g, _, cur, path = heapq.heappop(openq)
        ck = canonicalize(cur)
        if g > bestg.get(ck, -1) or ck in closed:
            continue
        if len(fast_window(cur, m, n)[1]) < h0:
            return path, expanded
        closed.add(ck)
        expanded += 1
        if expanded > budget or (cancel_check and cancel_check()):
            return None, expanded
        for new, act, rep in expand(cur, step):
            nk = canonicalize(new)
            ng = g + 1
            if ng >= bestg.get(nk, 10 ** 9):
                continue
            bestg[nk] = ng
            counter += 1
            heapq.heappush(openq, (heuristic(new, m, n, step), ng,
                                   counter, new, path + [(act, rep)]))
    return None, expanded
