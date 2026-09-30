# -*- coding: utf-8 -*-
"""改进动作：按「缝隙一侧的连通分量」枚举与执行。

现有 Action (gap,line,side,dir) 在一侧含多个连通分量时：
- 枚举只给一个动作（漏掉只移动单个分量的走法）；
- apply 固定选 side_blocks[0]（可能选错分量）。

这里 ExpAction = (gap, line, rep, dir)：
- gap 'h'/'v'；line 缝隙；rep 为该分量代表块坐标（唯一指定分量）；
- dir 垂直于缝隙（h→a/d，v→w/s）。
"""
from collections import deque

from game import SliderMatrix

ExpAction = tuple


def _side_cells(game, gap, line):
    """返回 (左/上侧 cells, 右/下侧 cells)，cell=(r,c)。"""
    a, b = set(), set()
    for blk in game.blocks:
        r, c = blk.location
        if gap == 'h':
            (a if r <= line else b).add((r, c))
        else:
            (a if c <= line else b).add((r, c))
    return a, b


def _components(cells):
    """4-邻接连通分量（不跨越缝隙，cells 已只含一侧）。"""
    comps, used = [], set()
    for seed in cells:
        if seed in used:
            continue
        seen = {seed}
        q = deque([seed])
        while q:
            r, c = q.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (r + dr, c + dc)
                if n in cells and n not in seen:
                    seen.add(n)
                    q.append(n)
        used |= seen
        comps.append(seen)
    return comps


def enumerate_exp_actions(game: SliderMatrix, step: int):
    out = []
    bounds = game.get_boundaries()
    for line in range(bounds['min_row'], bounds['max_row']):
        if game.is_valid_h_line(line):
            for side_cells in _side_cells(game, 'h', line):
                for comp in _components(side_cells):
                    rep = min(comp)
                    for d in ('a', 'd'):
                        out.append(('h', line, rep, d))
    for line in range(bounds['min_col'], bounds['max_col']):
        if game.is_valid_v_line(line):
            for side_cells in _side_cells(game, 'v', line):
                for comp in _components(side_cells):
                    rep = min(comp)
                    for d in ('w', 's'):
                        out.append(('v', line, rep, d))
    return out


def apply_exp_action(game: SliderMatrix, action: ExpAction, step: int) -> bool:
    gap, line, rep, d = action
    rep_block = next((b for b in game.blocks if tuple(b.location) == rep), None)
    if rep_block is None:
        return False
    for b in game.blocks:
        b.be_opted = False
    game.opt(gap, line, rep_block)
    final = game.try_move(d, step)
    if not final:
        for b in game.blocks:
            b.be_opted = False
        return False
    game.commit_move(final)
    for b in game.blocks:
        b.be_opted = False
    return True


def is_inverse_exp(a1, a2):
    g1, l1, r1, d1 = a1
    g2, l2, r2, d2 = a2
    if (g1, l1, r1) != (g2, l2, r2):
        return False
    pairs = {('w', 's'), ('s', 'w'), ('a', 'd'), ('d', 'a')}
    return (d1, d2) in pairs


def inverse_exp(a):
    inv = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}[a[3]]
    return (a[0], a[1], a[2], inv)


def select_component(game, gap, line, rep):
    """选中 rep 所在、不跨越缝隙的分量。"""
    rep_block = next((b for b in game.blocks if tuple(b.location) == rep), None)
    if rep_block is None:
        return False
    for b in game.blocks:
        b.be_opted = False
    game.opt(gap, line, rep_block)
    return True


def apply_exp_n(game, gap, line, rep, d, total, step):
    """把 rep 分量沿 d 连续移动 total（total 为 step 整数倍），逐单位提交。"""
    if total % step != 0 or not select_component(game, gap, line, rep):
        return False
    n_units = total // step
    for _ in range(n_units):
        final = game.try_move(d, step)
        if not final:
            for b in game.blocks:
                b.be_opted = False
            return False
        game.commit_move(final)
        # 下一单位需重新选中同一分量（块已移动，rep 变化）
        if _ + 1 < n_units:
            cells = [tuple(b.location) for b in game.blocks if b.be_opted]
            if not cells:
                return False
            new_rep = min(cells)
            if not select_component(game, gap, line, new_rep):
                return False
    for b in game.blocks:
        b.be_opted = False
    return True


# ---------------------------------------------------------------------------
# 纯集合版转移：不重建 Game，直接对 coords 枚举 (动作, 新coords)
# ---------------------------------------------------------------------------
def _side_sets(coords, gap, line):
    a, b = set(), set()
    for (r, c) in coords:
        if gap == 'h':
            (a if r <= line else b).add((r, c))
        else:
            (a if c <= line else b).add((r, c))
    return a, b


def _components_of(cells):
    comps, used = [], set()
    for seed in cells:
        if seed in used:
            continue
        seen = {seed}
        q = deque([seed])
        while q:
            r, c = q.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (r + dr, c + dc)
                if n in cells and n not in seen:
                    seen.add(n)
                    q.append(n)
        used |= seen
        comps.append(seen)
    return comps


def _is_conn(positions):
    if not positions:
        return True
    start = next(iter(positions))
    seen = {start}
    q = deque([start])
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (r + dr, c + dc)
            if n in positions and n not in seen:
                seen.add(n)
                q.append(n)
    return len(seen) == len(positions)


def succ_pure(coords, m, n, step):
    """纯集合转移：返回 [(exp_action, frozenset新coords), ...]。"""
    coords = frozenset(coords)
    total = m * n
    out = []
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    min_r, max_r, min_c, max_c = min(rs), max(rs), min(cs), max(cs)
    for gap, lines, dirs, dmap in (
            ('h', range(min_r, max_r), ('a', 'd'),
             {'a': (0, -step), 'd': (0, step)}),
            ('v', range(min_c, max_c), ('w', 's'),
             {'w': (-step, 0), 's': (step, 0)})):
        for L in lines:
            for side_cells in _side_sets(coords, gap, L):
                for comp in _components_of(side_cells):
                    rep = min(comp)
                    for d in dirs:
                        dr, dc = dmap[d]
                        moved = {(r + dr, c + dc) for r, c in comp}
                        if moved & (coords - comp):
                            continue
                        new = (coords - comp) | moved
                        if len(new) != total:
                            continue
                        if not _is_conn(new):
                            continue
                        out.append(((gap, L, rep, d), frozenset(new)))
    return out
