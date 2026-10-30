# -*- coding: utf-8 -*-
"""
反向 BFS 建表核心逻辑模块（纯逻辑，不依赖 pygame）—— bitmask 优化版

提供：
    goal_state(m, n)          - 目标状态坐标集合
    canonicalize(coords)      - 状态规范化 → 整数（8 对称取最小 + 位打包）
    int_to_coords(h, count)   - 整数反解为坐标列表（供可视化）
    is_single_connected(s)    - 单一连通分量判定（镜像 game.py）
    predecessors(B, m, n, step) - 真前驱生成（闭包增长 + 正向验证，正确处理不可逆）
    forward_neighbors(B, step, total) - 正向邻居（全分量，供验证）

状态表示约定：
    - 坐标用 (row, col) 元组；状态对外用 frozenset[(row, col)]。
    - 规范化：平移到原点 → 8 对称变体 → 字典序最小 → 位打包为 int。
    - 内部热路径用 bitmask（每状态一个 W = max_extent+2 的网格，bit = r*W+c）加速集合运算与连通性。
"""

import itertools
from functools import lru_cache


# ---------------------------------------------------------------------------
# 目标状态
# ---------------------------------------------------------------------------
def goal_state(m: int, n: int) -> frozenset:
    return frozenset((r, c) for r in range(m) for c in range(n))


# ---------------------------------------------------------------------------
# bitmask 连通性（位并行 BFS）
# ---------------------------------------------------------------------------
def _col_masks(W, H):
    col0 = 0
    colW = 0
    for r in range(H):
        col0 |= 1 << (r * W)
        colW |= 1 << (r * W + (W - 1))
    return col0, colW


@lru_cache(maxsize=50_000)
def _mask_is_connected(mask, W, col0, colW):
    if mask == 0:
        return True
    if mask & (mask - 1) == 0:
        return True
    visited = mask & -mask
    while True:
        right = (visited & ~colW) << 1
        left = (visited & ~col0) >> 1
        up = visited >> W
        down = visited << W
        nb = (right | left | up | down) & mask
        new = nb & ~visited
        if not new:
            break
        visited |= new
    return visited == mask


def is_single_connected(positions) -> bool:
    """對外接口：基於 frozenset 的連通性判定（鏡像 game.py）。

    ⚠️ 2026-10-17 深夜實測留檔：曾改走 bitboard（build_occupancy +
    is_connected 位並行 BFS），語義等價已過 367 例差分，但 ABAB 滿盤語料
    **0.44×（0/8 輪）——慢一倍以上，已回退**。原因：本函數的呼叫方
    （expand 的逐單位步校驗）手頭只有坐標集，位棋盤要先花 O(K+H) 建掩碼，
    而 set-DFS 在 K≤100 的實測規模下直接四鄰居查找更快。位並行的勝場在
    「還要順便取連通分量掩碼」的場景（如 game.opt），純判定不值得。
    """
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


# ---------------------------------------------------------------------------
# 规范化与位打包（带缓存）
# ---------------------------------------------------------------------------
def _normalize(coords):
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    mr, mc = min(rs), min(cs)
    return frozenset((r - mr, c - mc) for r, c in coords)


def _rot90(coords):
    return frozenset((c, -r) for r, c in coords)


def _flip(coords):
    return frozenset((r, -c) for r, c in coords)


def _variants(coords):
    out = []
    rot = frozenset(coords)
    for _ in range(4):
        out.append(rot)
        out.append(_flip(rot))
        rot = _rot90(rot)
    return out


def _normalized_sorted(coords):
    """平移歸一到原點 + 排序成 list（_normalize 的 list 版，供規範化熱路徑）。"""
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    mr, mc = min(rs), min(cs)
    return sorted((r - mr, c - mc) for r, c in coords)


# ---------------------------------------------------------------------------
# 打包整數規範化（2026-10-19）：q = r*B + c（歸一後 r,c ∈ [0, extent]）
#   _PB = 分量進位基；_PS = 分量位移；_PM = 分量掩碼
# 約束（與舊版折疊格式相同）：歸一後 extent < 256（h 折疊 r*256+c 的需要）；
# 打包本身只要求 extent < _PB。
# ---------------------------------------------------------------------------
_PB = 1 << 21
_PS = 21
_PM = _PB - 1


@lru_cache(maxsize=100_000)
def _canonicalize_fs(fs: frozenset) -> int:
    """規範化 + 8 個 D4 變體取字典序最小 → 位打包整數。

    **解析式歸一 + 打包整數管線**（2026-10-19 深夜優化，含一次中間版教訓）：
    舊版變體鏈在 tuple 空間運算（_normalized_sorted × 8：兩次 unpack 遍歷 +
    兩次 min + 元組推導式 + 元組排序）。端到端實測（5×5 step2 四種子，
    主指標=運算時間）：26.8s → 24.8s，約 -7.5%；本函數自身微基準
    （未封裝 ABAB）3.09×。
    ⚠️ 測量坑留檔：cProfile 按調用次數收稅，舊版管線含 273 萬次生成器
    呼叫，「占 GBFS 27.7%」是虛高口径，真實占比約 15%——端到端牆鐘才可信。
    本版：一次性掃描求 min/max 歸一到原點並打包成整數 q=r*B+c；對歸一集
    s（h=max r, w=max c），8 個 D4 變體的歸一偏移是 (h,w) 的顯式函數——
    V0=s, V1={(r,w-c)}, V2={(c,h-r)}, V3={(c,r)}, V4={(h-r,w-c)},
    V5={(h-r,c)}, V6={(w-c,r)}, V7={(w-c,h-r)}——每個變體只需一條整數
    算式（無 min 遍歷、無元組构造），整數排序即字典序。
    ⚠️ 中間版（偏置打包 _PO + 逐變體 _norm_variant 求 min）微基準僅 1.06×：
    min(genexpr) 117k 次調用燒 0.72s，比排序省下的還多——已廢棄，
    復刻見 experiments/script__bench_canon_packed.py 的差分基準（輸出與本版逐字
    一致，因兩版都等價於舊語義）。
    差分測試（含漂移坐標/非方形/對稱并列路徑）見 experiments/script__bench_canon_packed.py。
    """
    PB, PS, PM = _PB, _PS, _PM
    # 1) 單遍掃描求 min/max（fs 非空；空集舊版即拋 ValueError，語義一致）
    it = iter(fs)
    r0, c0 = next(it)
    minr = maxr = r0
    minc = maxc = c0
    for r, c in it:
        if r < minr:
            minr = r
        elif r > maxr:
            maxr = r
        if c < minc:
            minc = c
        elif c > maxc:
            maxc = c
    h = maxr - minr
    w = maxc - minc
    # 2) 打包（歸一後 r,c ∈ [0, extent]，c < PB ⟹ 整數序 = 字典序）
    rot = [(r - minr) * PB + (c - minc) for r, c in fs]
    # 3) 八變體（解析式偏移，無 min 遍歷）
    cands = (
        rot,
        [q - 2 * (q & PM) + w for q in rot],
        [(q & PM) * PB + h - (q >> PS) for q in rot],
        [(q & PM) * PB + (q >> PS) for q in rot],
        [h * PB + w - q for q in rot],
        [h * PB - q + 2 * (q & PM) for q in rot],
        [w * PB - (q & PM) * PB + (q >> PS) for q in rot],
        [w * PB - (q & PM) * PB + h - (q >> PS) for q in rot],
    )
    best = None
    for lst in cands:
        nv = sorted(lst)
        if best is None or nv < best:
            best = nv
    h_out = 0
    for q in best:
        h_out = h_out * 65536 + ((q >> PS) * 256 + (q & PM))
    return h_out


def canonicalize(coords) -> int:
    if isinstance(coords, frozenset):
        return _canonicalize_fs(coords)
    return _canonicalize_fs(frozenset(coords))


def int_to_coords(h: int, count: int):
    cells = []
    for _ in range(count):
        val = h % 65536
        cells.append((val // 256, val % 256))
        h //= 65536
    return cells


# ---------------------------------------------------------------------------
# 侧判定与侧内分量
# ---------------------------------------------------------------------------
def _on_side(cell, gap_type, L, side) -> bool:
    r, c = cell
    if gap_type == 'h':
        return (r <= L) if side == 'above' else (r > L)
    else:
        return (c <= L) if side == 'left' else (c > L)


def _side_components(cells, gap_type, L, side):
    side_cells = {c for c in cells if _on_side(c, gap_type, L, side)}
    visited = set()
    comps = []
    for seed in side_cells:
        if seed in visited:
            continue
        comp = set()
        stack = [seed]
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            visited.add(x)
            r, c = x
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nb = (r + dr, c + dc)
                if nb in side_cells and nb not in comp:
                    stack.append(nb)
        comps.append(comp)
    return comps


# ---------------------------------------------------------------------------
# 真前驱生成（bitmask 内部）
# ---------------------------------------------------------------------------
def _build_chains(sideB, d_unit):
    sideB = set(sideB)
    chains = []
    for c in sideB:
        back = (c[0] - d_unit[0], c[1] - d_unit[1])
        if back not in sideB:
            chain = [c]
            cur = c
            while True:
                nxt = (cur[0] + d_unit[0], cur[1] + d_unit[1])
                if nxt in sideB:
                    chain.append(nxt)
                    cur = nxt
                else:
                    break
            chains.append(chain)
    return chains


def _verify_forward_mask(C_mask, G_pre_mask, gap_type, L, side,
                         step, d_unit, B_mask, W, col0, colW, other_mask, side_mask):
    """验证从 C 选 G_pre 沿 +d_unit 移动 step 格能复现 B（纯 bitmask 版）。

    检查：
      1. G_pre 全在侧 S（用 side_mask 位运算）；
      2. 最大性：G_pre 的邻居不落在 other_mask（C 中侧 S 上 G_pre 之外的格子）；
      3. 逐步沿 d_unit 平移：每格无碰撞且整体连通（镜像 try_move）；
      4. 结果 == B。
    """
    # 1. 在侧 S 上（位运算替代逐格检查）
    if G_pre_mask & ~side_mask:
        return False
    # 2. 最大性
    gpre = G_pre_mask
    gpre_nbrs = (((gpre & ~colW) << 1) | ((gpre & ~col0) >> 1) |
                 (gpre >> W) | (gpre << W))
    if gpre_nbrs & other_mask:
        return False
    # 3. 逐步平移（只沿 d_unit 单一方向）
    non_sel = C_mask & ~G_pre_mask
    cur = G_pre_mask
    for _ in range(step):
        if d_unit == (0, 1):
            cur = (cur & ~colW) << 1
        elif d_unit == (0, -1):
            cur = (cur & ~col0) >> 1
        elif d_unit == (-1, 0):
            cur = cur >> W
        else:  # (1, 0)
            cur = cur << W
        if cur & non_sel:
            return False
        if not _mask_is_connected(cur | non_sel, W, col0, colW):
            return False
    # 4. 结果 == B
    return (non_sel | cur) == B_mask


def _shift_gpre(G_post_mask, d_unit, step, W, col0, colW, grid_mask):
    """内联 G_pre = G_post − D，消除闭包调用开销。"""
    if d_unit == (0, 1):
        for _ in range(step):
            G_post_mask = (G_post_mask & ~col0) >> 1
    elif d_unit == (0, -1):
        for _ in range(step):
            G_post_mask = (G_post_mask & ~colW) << 1
    elif d_unit == (-1, 0):
        G_post_mask = (G_post_mask << (W * step)) & grid_mask
    else:  # (1, 0)
        G_post_mask = G_post_mask >> (W * step)
    return G_post_mask


def _gen_pred_component(B_mask, comp_cells, gap_type, L, side, D, step, total,
                        W, col0, colW, Bset, preds, H):
    d_unit = (D[0] // step if D[0] else 0, D[1] // step if D[1] else 0)
    chains = _build_chains(comp_cells, d_unit)
    if not chains:
        return

    # 预计算每条链的累积 bitmask：chain_masks[i][K] = 前 K+1 个格子的掩码
    chain_masks = []
    for ch in chains:
        masks = [0]  # K=-1 时为空
        m = 0
        for (r, c) in ch:
            m |= 1 << (r * W + c)
            masks.append(m)
        chain_masks.append(masks)

    grid_mask = (1 << (H * W)) - 1

    # 预计算 side_mask（侧 S 上所有格子的掩码，用于 G_pre 侧检查）
    full_row = (1 << W) - 1
    side_mask = 0
    if gap_type == 'h':
        if side == 'above':
            for r in range(max(0, L + 1)):
                side_mask |= full_row << (r * W)
        else:
            for r in range(max(0, L + 1), H):
                side_mask |= full_row << (r * W)
    else:
        left_cols = L + 1
        if side == 'left':
            col_part = 0 if left_cols <= 0 else (1 << left_cols) - 1
        else:
            col_part = full_row if left_cols <= 0 else full_row & ~((1 << left_cols) - 1)
        for r in range(H):
            side_mask |= col_part << (r * W)

    # other_mask 基底：B 中侧 S 上不属于本分量的格子
    sideS_in_B_not_comp = {(r, c) for (r, c) in Bset
                           if _on_side((r, c), gap_type, L, side) and (r, c) not in comp_cells}
    sideS_base_mask = 0
    for (r, c) in sideS_in_B_not_comp:
        sideS_base_mask |= 1 << (r * W + c)

    # comp_cells 的整体掩码（用于 comp_minus 计算）
    comp_mask = 0
    for (r, c) in comp_cells:
        comp_mask |= 1 << (r * W + c)

    single_chain = len(chains) == 1
    choice_lists = [list(range(-1, len(ch))) for ch in chains]

    for combo in itertools.product(*choice_lists):
        # 用 bitmask 直接组合 G_post（无需坐标列表）
        # chain_masks[i] = [0, mask_1cell, mask_2cells, ...]，K=-1→空，K=0→第1格，K=1→前2格
        # 故取 masks[K+1]（K=-1 时跳过）
        G_post_mask = 0
        for masks, K in zip(chain_masks, combo):
            if K >= 0:
                G_post_mask |= masks[K + 1]
        if G_post_mask == 0:
            continue

        # G_pre_mask = shift(G_post_mask)（纯位运算）
        G_pre_mask = _shift_gpre(G_post_mask, d_unit, step, W, col0, colW, grid_mask)

        # vacated 剪枝：(G_pre \ G_post) 必须不在 B
        vacated_mask = G_pre_mask & ~G_post_mask
        if vacated_mask & B_mask:
            continue

        # G_post 连通（单链时必定连通，跳过）
        if not single_chain:
            if not _mask_is_connected(G_post_mask, W, col0, colW):
                continue

        # C = (B \ G_post) ∪ G_pre
        C_mask = (B_mask & ~G_post_mask) | G_pre_mask
        if C_mask.bit_count() != total:
            continue
        if not _mask_is_connected(C_mask, W, col0, colW):
            continue

        # other_mask = (C 侧 S 格子) \ G_pre = sideS_base ∪ (comp \ G_post)
        comp_minus = comp_mask & ~G_post_mask
        other_mask = sideS_base_mask | comp_minus

        if not _verify_forward_mask(C_mask, G_pre_mask, gap_type, L, side,
                                    step, d_unit, B_mask, W, col0, colW, other_mask, side_mask):
            continue
        C_coords = frozenset(_mask_to_coords(C_mask, W))
        preds.add(canonicalize(C_coords))


def _mask_to_coords(mask, W):
    coords = []
    b = mask
    while b:
        low = b & -b
        idx = low.bit_length() - 1
        coords.append((idx // W, idx % W))
        b ^= low
    return coords


def predecessors(B, m: int, n: int, step: int) -> set:
    Bset = set(B)
    total = m * n
    preds = set()
    rows = [r for r, _ in Bset]
    cols = [c for _, c in Bset]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)
    # 偏移帧：G_pre = G_post − D 可能产生负坐标（G_post 在 B 原点附近时），
    # 被 oob 检查误杀会漏掉合法前驱。统一加 offset = step 使所有坐标非负。
    # 偏移后 G_pre 坐标范围 [0, max_extent + 2*step]，全部落在网格内。
    offset = step
    W = max(max_r, max_c) + 2 * offset + 2
    H = max_r + 2 * offset + 1
    col0, colW = _col_masks(W, H)
    B_mask = 0
    Bset_off = set()
    for (r, c) in Bset:
        rr, cc = r + offset, c + offset
        Bset_off.add((rr, cc))
        B_mask |= 1 << (rr * W + cc)

    for L in range(min_r, max_r):
        L_off = L + offset
        for side in ('above', 'below'):
            comps = _side_components(Bset_off, 'h', L_off, side)
            for comp in comps:
                for sign in (-1, 1):
                    _gen_pred_component(B_mask, comp, 'h', L_off, side, (0, sign * step),
                                       step, total, W, col0, colW, Bset_off, preds, H)
    for L in range(min_c, max_c):
        L_off = L + offset
        for side in ('left', 'right'):
            comps = _side_components(Bset_off, 'v', L_off, side)
            for comp in comps:
                for sign in (-1, 1):
                    _gen_pred_component(B_mask, comp, 'v', L_off, side, (sign * step, 0),
                                       step, total, W, col0, colW, Bset_off, preds, H)
    return preds


# ---------------------------------------------------------------------------
# 正向邻居（全分量，供验证）
# ---------------------------------------------------------------------------
def _try_forward(B, comp, gap_type, L, side, D, step, total, nbrs):
    d_unit = (D[0] // step if D[0] else 0, D[1] // step if D[1] else 0)
    non_sel = set(B) - set(comp)
    cur = set(comp)
    for _ in range(step):
        cur = {(r + d_unit[0], c + d_unit[1]) for r, c in cur}
        if cur & non_sel:
            return
        if not is_single_connected(cur | non_sel):
            return
    result = non_sel | cur
    if len(result) == total:
        nbrs.add(canonicalize(frozenset(result)))


def forward_neighbors(B, step: int, total: int) -> set:
    B = set(B)
    nbrs = set()
    rows = [r for r, _ in B]
    cols = [c for _, c in B]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)
    for L in range(min_r, max_r):
        for side in ('above', 'below'):
            for comp in _side_components(B, 'h', L, side):
                for sign in (-1, 1):
                    _try_forward(B, comp, 'h', L, side, (0, sign * step), step, total, nbrs)
    for L in range(min_c, max_c):
        for side in ('left', 'right'):
            for comp in _side_components(B, 'v', L, side):
                for sign in (-1, 1):
                    _try_forward(B, comp, 'v', L, side, (sign * step, 0), step, total, nbrs)
    return nbrs


def _d_to_movedir(d_unit):
    """将位移方向映射为游戏 move_dir 字符。"""
    if d_unit == (0, 1):   return 'd'
    if d_unit == (0, -1):  return 'a'
    if d_unit == (1, 0):   return 's'
    return 'w'  # (-1, 0)


def _try_forward_with_action(B, comp, gap_type, L, side, D, step, total, results):
    """与 _try_forward 相同逻辑，额外返回 (canonical_hash, Action) 对。"""
    d_unit = (D[0] // step if D[0] else 0, D[1] // step if D[1] else 0)
    non_sel = set(B) - set(comp)
    cur = set(comp)
    for _ in range(step):
        cur = {(r + d_unit[0], c + d_unit[1]) for r, c in cur}
        if cur & non_sel:
            return
        if not is_single_connected(cur | non_sel):
            return
    result = non_sel | cur
    if len(result) == total:
        action = (gap_type, L, side, _d_to_movedir(d_unit))
        results.append((canonicalize(frozenset(result)), action))


def forward_neighbors_with_actions(B, step: int, total: int) -> list:
    """与 forward_neighbors 相同遍历逻辑，返回 [(canonical_hash, Action), ...]。"""
    B = set(B)
    results = []
    rows = [r for r, _ in B]
    cols = [c for _, c in B]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)
    for L in range(min_r, max_r):
        for side in ('above', 'below'):
            for comp in _side_components(B, 'h', L, side):
                for sign in (-1, 1):
                    _try_forward_with_action(
                        B, comp, 'h', L, side, (0, sign * step), step, total, results)
    for L in range(min_c, max_c):
        for side in ('left', 'right'):
            for comp in _side_components(B, 'v', L, side):
                for sign in (-1, 1):
                    _try_forward_with_action(
                        B, comp, 'v', L, side, (sign * step, 0), step, total, results)
    return results
