# -*- coding: utf-8 -*-
"""坐标级搜索核心（尺寸无关，无预建表）。

提供：
    expand(coords, step)            - 逐分量展开 [(new_coords, action, rep)]
    best_window / fast_window       - 最佳目标窗口、缺口、凸起识别
    heuristic                       - 距矩形的启发值
    guided_reduce_one               - GBFS 至少填一个洞（逐次消解多缺口）
"""
import heapq

from bitboard import is_connected
from solver.table_core import (canonicalize, _side_components)

DCHAR = {(0, 1): 'd', (0, -1): 'a', (1, 0): 's', (-1, 0): 'w'}
DDIR = {v: k for k, v in DCHAR.items()}


# ---------- 纯坐标逐分量展开 ----------
def expand(coords, step):
    B = set(coords)
    total = len(B)
    out = []
    rows = [r for r, _ in B]
    cols = [c for _, c in B]
    minr, maxr = min(rows), max(rows)
    minc, maxc = min(cols), max(cols)
    # 網格（每次 expand 建一次，全部 go 共用；2026-10-19 深夜優化）：
    #   整體平移歸一到 [step, extent+step]，四邊各留 step 格 guard——
    #   go() 的單位步移位（du=±1 格、最多 step 次）不越界、不繞行。
    #   舊版逐單位步重建坐標集 + set-DFS 連通判定（is_single_connected）。
    #   端到端實測（主指標=運算時間）：5×5 step2 四種子含 canonicalize
    #   優化共 26.8s→18.7s（-30%），其中本項單獨貢獻 8.1s→6.1s（seed1000，
    #   約 -25%）；6×6 硬茬 138.0s→80.8s（-41%，步數不變）。
    #   ⚠️ 2026-10-17 已判過「每次呼叫都重建掩碼」的位棋盤版 0.44× 死刑；
    #   本版勝負手在於掩碼在 go() 內只建一次、移位增量更新。
    W = maxc - minc + 1 + 2 * step
    H = maxr - minr + 1 + 2 * step
    orr, orc = minr - step, minc - step
    B_mask = 0
    for r, c in B:
        B_mask |= 1 << ((r - orr) * W + (c - orc))
    col0 = colW = 0
    for i in range(H):
        col0 |= 1 << (i * W)
        colW |= 1 << (i * W + W - 1)

    def go(comp, gt, L, side, D):
        du = (D[0] // step if D[0] else 0, D[1] // step if D[1] else 0)
        non = B - comp
        # 分量掩碼：每次 go 只建這一次，之後逐單位步整數移位
        cm = 0
        for r, c in comp:
            cm |= 1 << ((r - orr) * W + (c - orc))
        nm = B_mask ^ cm               # non = B - comp（comp ⊆ B）
        sh = du[0] * W + du[1]         # 單位步位移量（±1 格 → ±W 或 ±1）
        for _ in range(step):
            cm = (cm << sh) if sh > 0 else (cm >> -sh)
            if cm & nm or not is_connected(cm | nm, W, col0, colW):
                return
        # 成功：non 用元組集原樣，comp 從掩碼提取（guard 格即真實坐標）
        res = list(non)
        m = cm
        while m:
            b = m & -m
            m ^= b
            i = b.bit_length() - 1
            res.append((orr + i // W, orc + i % W))
        if len(res) == total:
            out.append((frozenset(res), (gt, L, side, DCHAR[du]),
                        next(iter(comp))))

    for L in range(minr, maxr):
        for side in ('above', 'below'):
            for comp in _side_components(B, 'h', L, side):
                for sgn in (-1, 1):
                    go(comp, 'h', L, side, (0, sgn * step))
    for L in range(minc, maxc):
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
    """启发用快速窗口，保证不返回 None。

    **前綴和版**（2026-10-17 深夜優化）：舊實現對每個候選窗口新建一個
    h×w 的座標集合再與 B 相交（≤50 窗 × O(h·w) 集合構造 + 相交）。本函數是
    GBFS（guided_reduce_one）每個節點 + 每個後繼的調用點，實測占 GBFS 段
    33%。改為二維前綴和：建表 O(網格) + 查窗 O(1)，只對最終勝出窗口算一次
    holes/protr（舊版對每個「刷新紀錄」的中間窗口也算，純浪費）。
    枚舉順序（朝向 (m,n)→(n,m)，r0/c0 升序）、「嚴格大於才更新」規則、
    視窗範圍公式（rlo/rhi/clo/chi 與 5 格夾取）與舊版逐字一致，輸出相同
    （差分測試見 experiments/script__bench_find_window.py 的 fast_window 部分）。
    """
    B = set(coords)
    rs = [r for r, _ in B]
    cs = [c for _, c in B]
    minr, maxr, minc, maxc = min(rs), max(rs), min(cs), max(cs)
    best_inside = -1
    best_key = None
    for h, w in ((m, n), (n, m)):
        rlo, rhi = minr - 1, max(maxr - h + 2, minr + 1)
        clo, chi = minc - 1, max(maxc - w + 2, minc + 1)
        r_end = min(rhi, rlo + 5)   # r0 升序枚舉的排他上界（≤ rlo+5，舊版同）
        c_end = min(chi, clo + 5)
        # 網格覆蓋 = 全部候選窗 ∪ B：
        #   行 [rlo, max(r_end + h, maxr + 1))，列 [clo, max(c_end + w, maxc + 1))
        R = max(r_end + h, maxr + 1) - rlo
        C = max(c_end + w, maxc + 1) - clo
        grid = bytearray(R * C)
        for r, c in B:
            ri = r - rlo
            ci = c - clo
            if 0 <= ri < R and 0 <= ci < C:
                grid[ri * C + ci] = 1
        # 二維前綴和：ps[(i+1)*(C+1)+(j+1)] = grid[0..i][0..j] 之和
        W = C + 1
        ps = [0] * ((R + 1) * W)
        for i in range(R):
            row_acc = 0
            gbase = i * C
            cur = (i + 1) * W
            above = i * W
            for j in range(C):
                row_acc += grid[gbase + j]
                ps[cur + j + 1] = ps[above + j + 1] + row_acc
        for r0 in range(rlo, r_end):
            ri = r0 - rlo
            r2 = ri + h
            row2 = r2 * W
            row1 = ri * W
            for c0 in range(clo, c_end):
                ci = c0 - clo
                c2 = ci + w
                inside = ps[row2 + c2] - ps[row1 + c2] - ps[row2 + ci] + ps[row1 + ci]
                if inside > best_inside:
                    best_inside = inside
                    best_key = (r0, c0, h, w)
    if best_key is not None:
        r0, c0, h, w = best_key
        win = set((r, c) for r in range(r0, r0 + h)
                  for c in range(c0, c0 + w))
        return (r0, c0, h, w), win - B, B - win
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
