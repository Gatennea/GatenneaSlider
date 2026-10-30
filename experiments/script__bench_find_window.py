# -*- coding: utf-8 -*-
"""深夜优化（2026-10-17）差分测试 + ABAB 基准 —— 覆盖全部改动点。

改动清单（全部要求「输出逐字相同」，差分零差异才许上线）：
  1. gather_solver.find_best_window   前缀和查窗（消逐窗 O(K) 函数呼叫）
  2. search_core.fast_window          前缀和查窗（GBFS 每节点/每后继）
  3. table_core.is_single_connected   set-DFS → 位並行 BFS（語義等價）
  4. table_core._canonicalize_fs      8 變體鏈去 frozenset 中間構造
  5. bitboard.build_occupancy         列掩碼等比級數閉式（代 O(H) 迴圈）
  6. state.restore                    原地恢復（代全量重建 Block）
  7. gather_solver.max_overlap        扁平化 **已回退**（實測 0.94× 無增益），
                                       此處保留舊版復刻做回退後對照

用法：
    D:/python/python.exe -u experiments/script__bench_find_window.py
"""
import os
import random
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.gather_solver import (find_best_window,          # noqa: E402
                                     max_overlap,
                                     detect_target_corner,
                                     _overlap_at)
from solver.search_core import fast_window                       # noqa: E402
from solver.table_core import (is_single_connected,              # noqa: E402
                               canonicalize, _canonicalize_fs,
                               _normalize, _variants)
from bitboard import build_occupancy                           # noqa: E402
from solver.state import snapshot, restore                      # noqa: E402
from game import SliderMatrix, Block                            # noqa: E402

FAILS = []


def check(name, cond, extra=''):
    tag = 'PASS' if cond else 'FAIL'
    print('[%s] %s%s' % (tag, name, ('  %s' % extra) if extra else ''))
    if not cond:
        FAILS.append(name)


# ===========================================================================
# 舊實現逐字復刻（改前快照，作為差分基準）
# ===========================================================================
def find_best_window_legacy(coords, m, n, step):
    if not coords:
        return 0, 0, (m, n), 0
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    min_r, max_r = min(rs), max(rs)
    min_c, max_c = min(cs), max(cs)
    tc = detect_target_corner(coords, m, n, step)
    r_mod = tc[0] if (tc is not None and m % step != 0) else None
    c_mod = tc[1] if (tc is not None and n % step != 0) else None
    integral = all(float(v).is_integer() for v in rs + cs)
    scale = 1 if integral else 2
    lo_r, hi_r = int(round(min_r * scale)), int(round(max_r * scale))
    lo_c, hi_c = int(round(min_c * scale)), int(round(max_c * scale))

    def _out(v):
        return v // scale if scale == 1 else v / 2.0

    best = (_out(lo_r), _out(lo_c), (m, n), 0)
    for rh, cw in ((m, n), (n, m)):
        for i_r in range(lo_r - rh * scale + scale, hi_r + scale, scale):
            r0 = _out(i_r)
            if r_mod is not None and r0 % step != r_mod:
                continue
            for i_c in range(lo_c - cw * scale + scale, hi_c + scale, scale):
                c0 = _out(i_c)
                if c_mod is not None and c0 % step != c_mod:
                    continue
                cnt = _overlap_at(coords, rh, cw, r0, c0)
                if cnt > best[3]:
                    best = (r0, c0, (rh, cw), cnt)
                    if cnt == m * n:
                        return best
    return best


def fast_window_legacy(coords, m, n):
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


def is_single_connected_legacy(positions) -> bool:
    if not positions:
        return True
    positions = set(positions)
    start = next(iter(positions))
    visited = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in visited:
            continue
        visited.add(cur)
        r, c = cur
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nb = (r + dr, c + dc)
            if nb in positions and nb not in visited:
                stack.append(nb)
    return len(visited) == len(positions)


def canonicalize_legacy(coords) -> int:
    fs = coords if isinstance(coords, frozenset) else frozenset(coords)
    best = None
    for v in _variants(fs):
        nv = sorted(_normalize(v))
        if best is None or nv < best:
            best = nv
    h = 0
    for r, c in best:
        h = h * 65536 + (r * 256 + c)
    return h


def build_occupancy_legacy(cells):
    if not cells:
        return 0, 1, 0, 0, 0, 0, 0
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    min_r, max_r = min(rs), max(rs)
    min_c, max_c = min(cs), max(cs)
    W = max_c - min_c + 1
    H = max_r - min_r + 1
    mask = 0
    for r, c in cells:
        idx = (r - min_r) * W + (c - min_c)
        mask |= 1 << idx
    col0 = 0
    colW = 0
    for r in range(H):
        col0 |= 1 << (r * W)
        colW |= 1 << (r * W + (W - 1))
    return mask, W, H, col0, colW, min_r, min_c


# ===========================================================================
# 局面生成
# ===========================================================================
def rand_coords(m, n, step, rng, spread=0):
    """随机局面：K=m*n/step^2 个块，在放大边界盒内随机撒。"""
    K = m * n // (step * step)
    H = m + spread
    W = n + spread
    cells = [(r, c) for r in range(H) for c in range(W)]
    rng.shuffle(cells)
    return frozenset(cells[:K])


def full_coords(m, n, rng, spread=3):
    """满额 m*n 块局面（max_overlap 要求）。"""
    cells = [(r, c) for r in range(m + spread) for c in range(n + spread)]
    rng.shuffle(cells)
    return frozenset(cells[:m * n])


def half_coords(m, n, step, rng, spread=0):
    """米字式半整数坐标（B 晶格错位态）。"""
    base = rand_coords(m, n, step, rng, spread)
    return frozenset((r + 0.5, c + 0.5) for r, c in base)


def mixed_coords(m, n, step, rng, spread=0):
    """米字錯位態的**混合晶格**：一部塊半整數、一部塊整數。

    這正是 2026-10-17 深夜回歸的覆蓋空洞：全半整數時 lo/hi 在 2× 下
    奇偶一致（對齊），而混合時奇偶不同，枚舉區間多半格——舊版
    _overlap_at 不建網格無害，前綴和版按對齊區間開網格會越界。
    保證至少一塊移位、一塊不移（其餘隨機）。
    """
    base = sorted(rand_coords(m, n, step, rng, spread))
    out = []
    for i, (r, c) in enumerate(base):
        if i < 2:
            shift = (i == 0)          # 第 0 塊移位、第 1 塊不移，強制造混合
        else:
            shift = rng.random() < 0.5
        out.append((r + 0.5, c + 0.5) if shift else (r, c))
    return frozenset(out)


def same_result(a, b):
    """完全相等含类型（int 0 与 float 0.0 也算不同，保守）。"""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if type(x) is not type(y) or x != y:
            return False
    return True


SPECS = [(4, 4, 2), (4, 4, 3), (4, 4, 1), (3, 3, 2), (5, 5, 2),
         (6, 6, 2), (4, 6, 2), (6, 4, 2), (8, 8, 2), (3, 4, 3),
         (4, 3, 3), (2, 2, 2), (5, 5, 3), (6, 6, 3), (3, 5, 1),
         (10, 10, 2), (5, 4, 2), (4, 5, 2)]


# ===========================================================================
# 差分
# ===========================================================================
def diff_all():
    rng = random.Random(20261018)

    # ---- 1. find_best_window ----
    cases = bad = 0
    for (m, n, s) in SPECS:
        for spread in (0, 1, 2, 3):
            for t in range(6):
                coords = rand_coords(m, n, s, rng, spread)
                ra = find_best_window_legacy(coords, m, n, s)
                rb = find_best_window(coords, m, n, s)
                cases += 1
                if not same_result(ra, rb):
                    bad += 1
                    if bad <= 3:
                        print('  差異 %dx%d s=%d sp=%d:\n    old=%s\n    new=%s'
                              % (m, n, s, spread, ra, rb))
    for (m, n, s) in [(4, 4, 2), (5, 5, 2), (6, 6, 2), (4, 6, 2)]:
        for spread in (0, 2):
            for t in range(6):
                coords = half_coords(m, n, s, rng, spread)
                ra = find_best_window_legacy(coords, m, n, s)
                rb = find_best_window(coords, m, n, s)
                cases += 1
                if not same_result(ra, rb):
                    bad += 1
                    if bad <= 6:
                        print('  半整數差異 %dx%d s=%d sp=%d:\n    old=%s\n    new=%s'
                              % (m, n, s, spread, ra, rb))
    # 混合晶格（米字錯位態真實形態）：多半格枚舉路徑，2026-10-17 回歸教訓
    for (m, n, s) in [(4, 4, 2), (5, 5, 2), (6, 6, 2), (4, 6, 2), (3, 3, 2),
                      (6, 4, 2), (8, 8, 2)]:
        for spread in (0, 1, 3):
            for t in range(6):
                coords = mixed_coords(m, n, s, rng, spread)
                ra = find_best_window_legacy(coords, m, n, s)
                rb = find_best_window(coords, m, n, s)
                cases += 1
                if not same_result(ra, rb):
                    bad += 1
                    if bad <= 6:
                        print('  混合晶格差異 %dx%d s=%d sp=%d:\n    old=%s\n    new=%s'
                              % (m, n, s, spread, ra, rb))
    for coords, m, n, s in [
            (frozenset((r, c) for r in range(4) for c in range(4)), 4, 4, 2),
            (frozenset({(0, 0)}), 4, 4, 2),
            (frozenset(), 4, 4, 2),
            (frozenset((r, c) for r in range(4) for c in range(4)), 4, 4, 1),
            (frozenset((r + 0.5, c + 0.5) for r in range(4) for c in range(4)), 4, 4, 2),
            # 混合晶格邊界：一塊整數 + 一塊半整數（lo/hi 奇偶必異）
            (frozenset({(0, 0), (0.5, 0.5)}), 4, 4, 2),
            (frozenset({(0, 0), (1.5, 1.5), (2, 2), (3.5, 0.5)}), 4, 4, 2)]:
        ra = find_best_window_legacy(coords, m, n, s)
        rb = find_best_window(coords, m, n, s)
        cases += 1
        if not same_result(ra, rb):
            bad += 1
            print('  邊界差異 m=%d n=%d s=%d:\n    old=%s\n    new=%s' % (m, n, s, ra, rb))
    check('1. find_best_window：%d 局面零差異' % cases, bad == 0,
          '' if bad == 0 else '%d 處' % bad)

    # ---- 2. fast_window ----
    cases = bad = 0
    for (m, n, s) in SPECS:
        for spread in (0, 1, 2, 3, 5):
            for t in range(6):
                coords = rand_coords(m, n, s, rng, spread)
                ra = fast_window_legacy(coords, m, n)
                rb = fast_window(coords, m, n)
                cases += 1
                # 返回值 (win, holes, protr)：win/holes/protr 都必須相等
                ok = (same_result(ra[0], rb[0])
                      and ra[1] == rb[1] and ra[2] == rb[2]
                      and type(ra[1]) is type(rb[1]))
                if not ok:
                    bad += 1
                    if bad <= 3:
                        print('  差異 %dx%d s=%d sp=%d:\n    old=%s\n    new=%s'
                              % (m, n, s, spread, ra, rb))
    # 邊界：單塊 / 貼邊 / 已還原滿盤
    for coords, m, n in [(frozenset({(0, 0)}), 4, 4),
                         (frozenset({(3, 3)}), 4, 4),
                         (frozenset((r, c) for r in range(4) for c in range(4)), 4, 4),
                         (frozenset({(-2, -3)}), 5, 5),
                         (frozenset({(0, 0), (0, 1), (1, 0)}), 6, 6)]:
        ra = fast_window_legacy(coords, m, n)
        rb = fast_window(coords, m, n)
        cases += 1
        if not (same_result(ra[0], rb[0]) and ra[1] == rb[1] and ra[2] == rb[2]):
            bad += 1
            print('  邊界差異 m=%d n=%d:\n    old=%s\n    new=%s' % (m, n, ra, rb))
    check('2. fast_window：%d 局面零差異' % cases, bad == 0,
          '' if bad == 0 else '%d 處' % bad)

    # ---- 3. is_single_connected ----
    cases = bad = 0
    for (m, n, s) in SPECS[:10]:
        for spread in (0, 1, 2):
            for t in range(4):
                coords = rand_coords(m, n, s, rng, spread)
                # 隨機再拆掉幾塊，製造大量不連通案
                cl = list(coords)
                rng.shuffle(cl)
                for drop in (0, 1, 2):
                    sub = frozenset(cl[:max(1, len(cl) - drop)])
                    va = is_single_connected_legacy(sub)
                    vb = is_single_connected(sub)
                    cases += 1
                    if va != vb:
                        bad += 1
                        if bad <= 3:
                            print('  差異 sub=%s: old=%s new=%s' % (sorted(sub), va, vb))
    for coords in [set(), {(0, 0)}, {(0, 0), (0, 1)}, {(0, 0), (2, 2)},
                   {(r, c) for r in range(4) for c in range(4)},
                   {(0, 0), (0, 1), (1, 1), (1, 2), (5, 5)},
                   {(-3, -3), (-3, -2), (-2, -3)}]:
        va = is_single_connected_legacy(coords)
        vb = is_single_connected(coords)
        cases += 1
        if va != vb:
            bad += 1
            print('  邊界差異 %s: old=%s new=%s' % (sorted(coords), va, vb))
    check('3. is_single_connected：%d 局面零差異' % cases, bad == 0,
          '' if bad == 0 else '%d 處' % bad)

    # ---- 4. canonicalize ----
    cases = bad = 0
    for (m, n, s) in SPECS:
        for spread in (0, 1, 2, 3):
            for t in range(6):
                coords = rand_coords(m, n, s, rng, spread)
                va = canonicalize_legacy(coords)
                vb = canonicalize(coords)
                cases += 1
                if type(va) is not type(vb) or va != vb:
                    bad += 1
                    if bad <= 3:
                        print('  差異 %dx%d s=%d sp=%d: old=%d new=%d'
                              % (m, n, s, spread, va, vb))
    # 平移/D4 不變量抽查 + 邊界
    base = frozenset({(0, 0), (0, 1), (1, 0)})
    for shift in [(0, 0), (5, -3), (-7, 7)]:
        for tf in [lambda r, c: (r, c), lambda r, c: (c, r),
                   lambda r, c: (-r, c), lambda r, c: (r, -c),
                   lambda r, c: (c, -r)]:
            coords = frozenset((r + shift[0], c + shift[1]) for r, c in base)
            coords = frozenset(tf(r, c) for r, c in coords)
            cases += 1
            if canonicalize(coords) != canonicalize(base):
                bad += 1
                print('  D4/平移不變量違反：%s' % sorted(coords))
    for coords in [frozenset({(0, 0)}), frozenset({(2, 3)}),
                   frozenset({(0, 0), (0, 1)})]:
        cases += 1
        if canonicalize(coords) != canonicalize_legacy(coords):
            bad += 1
            print('  邊界差異 %s' % sorted(coords))
    check('4. canonicalize：%d 局面零差異' % cases, bad == 0,
          '' if bad == 0 else '%d 處' % bad)

    # ---- 5. build_occupancy ----
    cases = bad = 0
    for (m, n, s) in SPECS:
        for spread in (0, 1, 2, 4):
            for t in range(5):
                coords = rand_coords(m, n, s, rng, spread)
                va = build_occupancy_legacy(coords)
                vb = build_occupancy(coords)
                cases += 1
                if va != vb:
                    bad += 1
                    if bad <= 3:
                        print('  差異 %dx%d s=%d sp=%d:\n    old=%s\n    new=%s'
                              % (m, n, s, spread, va, vb))
    for coords in [frozenset(), {(0, 0)}, {(0, 0), (0, 1)},
                   {(0, 0), (1, 0), (0, 1)},
                   {(-3, -3), (-3, -2), (10, 10)}]:
        va = build_occupancy_legacy(coords)
        vb = build_occupancy(coords)
        cases += 1
        if va != vb:
            bad += 1
            print('  邊界差異 %s:\n    old=%s\n    new=%s' % (sorted(coords), va, vb))
    check('5. build_occupancy：%d 局面零差異' % cases, bad == 0,
          '' if bad == 0 else '%d 處' % bad)

    # ---- 6. restore 原地化：快照往返後觀察狀態須與舊版新建等價 ----
    cases = bad = 0
    for (m, n, s) in [(4, 4, 2), (6, 6, 2), (5, 5, 2), (4, 6, 2)]:
        for t in range(6):
            g = SliderMatrix(m, n)
            g.shuffle(attempts=60, step=s)
            # 造一個帶瞬態的狀態：be_opted/number 都被改過
            for i, b in enumerate(g.blocks):
                b.be_opted = (i % 2 == 0)
                b.number = i + 1
            snap = snapshot(g)
            # 亂動棋盤
            for b in g.blocks:
                b.location[0] += 7
                b.location[1] -= 3
                b.be_opted = True
                b.number = 99
            restore(g, snap)
            cases += 1
            locs_ok = [tuple(b.location) for b in g.blocks] == list(snap['blocks'])
            opt_ok = all(b.be_opted is False for b in g.blocks)
            num_ok = all(b.number is None for b in g.blocks)
            mtx_ok = g.matrix is not None
            if not (locs_ok and opt_ok and num_ok and mtx_ok):
                bad += 1
                print('  restore 差異 %dx%d s=%d: locs=%s opt=%s num=%s mtx=%s'
                      % (m, n, s, locs_ok, opt_ok, num_ok, mtx_ok))
    check('6. restore 原地化：%d 局面往返等價' % cases, bad == 0,
          '' if bad == 0 else '%d 處' % bad)


# ===========================================================================
# ABAB 基準（逐輪配對，項目測量紀律）
# ===========================================================================
def bench_all():
    rng = random.Random(20261019)
    # 真實語料：棋局是「滿盤」——每格一塊，m*n 個塊（step 只是滑動距離）。
    # 早期版本用 m*n/step^2 個塊是錯的（那是著色類數，不是塊數），塊數少
    # 會低估前綴和的收益（逐窗 O(K) vs O(1)，K 越大舊版越慘）。
    full_corpus = []
    for (m, n, s) in [(8, 8, 2), (6, 6, 2), (5, 5, 2), (4, 4, 2), (10, 10, 2)]:
        for _ in range(8):
            full_corpus.append((full_coords(m, n, rng, spread=4), m, n, s))
    win_corpus = full_corpus
    fw_corpus = [(c, m, n) for c, m, n, _ in full_corpus]
    conn_corpus = [(c,) for c, _, _, _ in full_corpus]
    # canonicalize：真版帶 lru_cache，舊版復刻不帶——直接比會把「緩存命中」
    # 誤算成本次改動的收益。比未封裝的 __wrapped__（同為冷計算），隔離改動本身。
    can_new = _canonicalize_fs.__wrapped__
    can_corpus = [(c,) for c, _, _, _ in full_corpus]
    occ_corpus = [(c,) for c, _, _, _ in full_corpus]

    def abab(name, n_rounds, old_fn, new_fn, corpus, argn):
        print('\nABAB %s（%d 局面/輪，交替 %d 輪）' % (name, len(corpus), n_rounds))
        for fn in (old_fn, new_fn):
            for row in corpus[:2]:
                fn(*row[:argn])
        wins = 0
        ratios = []
        for r in range(n_rounds):
            def run(fn):
                t0 = time.perf_counter()
                for row in corpus:
                    fn(*row[:argn])
                return time.perf_counter() - t0
            o = (run(old_fn) + run(old_fn)) / 2
            nw = (run(new_fn) + run(new_fn)) / 2
            ratios.append(o / nw)
            if nw < o:
                wins += 1
            print('  輪%d：舊 %.2fms / 新 %.2fms → %.2fx' % (r, o * 1e3, nw * 1e3, o / nw))
        print('  匯總：新勝 %d/%d 輪；平均 %.2fx（最小 %.2fx）'
              % (wins, n_rounds, sum(ratios) / len(ratios), min(ratios)))

    abab('find_best_window', 8, find_best_window_legacy, find_best_window,
         win_corpus, 4)
    abab('fast_window', 8, fast_window_legacy, fast_window, fw_corpus, 3)
    abab('is_single_connected', 8, is_single_connected_legacy,
         is_single_connected, conn_corpus, 1)
    abab('canonicalize(未封裝冷計算)', 8, canonicalize_legacy, can_new,
         can_corpus, 1)
    abab('build_occupancy', 8, build_occupancy_legacy, build_occupancy,
         occ_corpus, 1)


if __name__ == '__main__':
    diff_all()
    bench_all()
    print('\n==== %s ====' % ('全部通过' if not FAILS else '有失败：%s' % FAILS))
    sys.exit(1 if FAILS else 0)
