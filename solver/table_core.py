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
    """对外接口：基于 frozenset 的连通性判定（镜像 game.py）。"""
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


@lru_cache(maxsize=100_000)
def _canonicalize_fs(fs: frozenset) -> int:
    best = None
    for v in _variants(fs):
        nv = sorted(_normalize(v))
        if best is None or nv < best:
            best = nv
    h = 0
    for r, c in best:
        h = h * 65536 + (r * 256 + c)
    return h


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
