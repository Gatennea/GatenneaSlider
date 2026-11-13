# -*- coding: utf-8 -*-
"""异形聚拢序列的防偏移桥：经典动作 ↔ 几何引擎 Board/Move。

算法本体在 ``engine/drift.py``（板型无关）；本模块只做「经典引擎的
5 元组动作 / 游戏对象」与「引擎 Board/Move」之间的换算，以及**真盘重放
终裁** —— 改写只在「改写后序列在原盘上逐步可执行、且终态形状与原终态
一致」时才采纳。任何一步不能换算/不合法，整条改写放弃并如实报告原因
（AGENTS.md §2：不静默兜底）。
"""
from engine import drift
from engine.board import Board
from engine.compat import direction_table
from engine.registry import mi_spec, tri_spec

__all__ = ['rewrite_gather_actions']


def _spec_and_keys(game, step, start_coords=None):
    """按形态造板型与块键集合；返回 (spec, keys, groups, form)。

    ``start_coords`` 给了就用它当起点（梯度流水线里 self.game 可能正在播
    上一段，不是本段动作的起点）；不给则信任当前 game 就是起点。
    """
    from solver import game_form
    form = game_form(game)
    if form == 'triangle':
        spec = tri_spec(game.k)
        src = ([(c[0], c[1], c[2], 0) for c in start_coords]
               if start_coords is not None
               else [(b.location[0], b.location[1], b.location[2], b.group)
                     for b in game.blocks])
        keys = {((i, j), 'up' if up else 'down'): g for i, j, up, g in src}
    elif form == 'mi':
        spec = mi_spec(game.m, game.n)
        src = ([(c[0], c[1], c[2], 0) for c in start_coords]
               if start_coords is not None
               else [(b.location[0], b.location[1], b.location[2], b.group)
                     for b in game.blocks])
        keys = {((int(round(2 * r)), int(round(2 * c))), q): g
                for r, c, q, g in src}
    else:
        return None, None, None, form
    groups = {k: g for k, g in keys.items() if g}
    return spec, frozenset(keys), groups, form


def _key_of(spec, form, rep):
    """代表块的真实坐标 → 引擎块键。"""
    if form == 'triangle':
        (i, j, up) = rep[0], rep[1], rep[2]
        return ((i, j), 'up' if up else 'down')
    # mi：真实坐标 (r, c, q)，引擎点 = 2×(r, c)
    return ((int(round(2 * rep[0])), int(round(2 * rep[1]))), rep[2])


def _pos_of(spec, form, key):
    """引擎块键 → 真实坐标（与求解器动作里的 rep 同形）。"""
    p, o = key
    if form == 'triangle':
        return (p[0], p[1], True if o == 'up' else False)
    def _half(x):
        v = x / 2
        return int(v) if float(v).is_integer() else v
    return (_half(p[0]), _half(p[1]), o)


def _side_engine(form, side):
    """经典 side → 引擎 side（-1 / +1）。"""
    if form == 'square':
        return -1 if side in ('above', 'left') else 1
    return -1 if side == 0 else 1


def _letter_of(spec, direction):
    table = direction_table(spec)
    for letter, d in table.items():
        if d == direction:
            return letter
    raise ValueError(f'方向 {direction} 在板型 {spec.name!r} 的字母表里没有字母')


def rewrite_gather_actions(game, actions, step, start_coords=None):
    """改写一段异形聚拢动作 → dict（actions/applied/flips/note）。

    只处理 triangle / mi。方形有既有的 ``solver/anti_drift.py``（方形语义的
    特化件），这里不重复接管。

    起点取 ``start_coords``（求解器返回的 ``start_coords``），缺省信任
    ``game`` 当前就是起点。**只在能确认起点时才做真盘回放终裁**；确认
    不了就退化为「引擎层已逐步校验合法」，并在 note 里写明（不假装验过）。
    """
    spec, keys0, groups, form = _spec_and_keys(game, step, start_coords)
    if spec is None:
        return {'actions': list(actions), 'applied': False, 'flips': 0,
                'note': 'anti_drift: 非异形形态，跳过'}
    if not actions:
        return {'actions': [], 'applied': False, 'flips': 0, 'note': ''}

    board0 = Board.from_keys(spec, keys0, groups or None)
    table = direction_table(spec)

    # ---- 1) 经典动作 → Move（逐步校验，任何一步失败就整条放弃）----
    moves = []
    b = board0
    for i, act in enumerate(actions):
        if len(act) < 5:
            return {'actions': list(actions), 'applied': False, 'flips': 0,
                    'note': f'anti_drift: 第{i}步缺 rep，无法换算'}
        gap_type, line, side, letter, rep = act[:5]
        fam = next((f for f in spec.seam_families if f.name == gap_type), None)
        if fam is None or letter not in table:
            return {'actions': list(actions), 'applied': False, 'flips': 0,
                    'note': f'anti_drift: 第{i}步的缝/方向不认识'}
        t = fam.line_scale * line + 1
        # 米字的 line 可能是负数/半整数（t 在 shuffled 局面里可以落到负值），
        # 2×(-2.5)+1 在 Python 里是 -4.0 —— 先判整数再归一，不能直接 isinstance。
        if not float(t).is_integer():
            return {'actions': list(actions), 'applied': False, 'flips': 0,
                    'note': f'anti_drift: 第{i}步线号 {line!r} 换算后非整数'}
        t = int(t)
        try:
            mv = drift.component_move(
                b, fam.name, t, _side_engine(form, side), table[letter],
                step, _key_of(spec, form, rep))
        except ValueError as exc:
            return {'actions': list(actions), 'applied': False, 'flips': 0,
                    'note': f'anti_drift: 第{i}步换算失败（{exc}）'}
        moves.append(mv)
        b = b.apply(mv)

    # ---- 2) 引擎层改写（大片不动、小片滑；整体平移记进 off）----
    rw = drift.FrameRewriter(board0)
    new_moves = rw.feed(moves)
    if rw.board.canonical_key() != b.canonical_key():
        return {'actions': list(actions), 'applied': False, 'flips': 0,
                'note': 'anti_drift: 改写后终态形状不一致，放弃'}

    # ---- 3) Move → 经典动作 ----
    new_actions = []
    for mv in new_moves:
        fam = next(f for f in spec.seam_families if f.name == mv.family)
        raw = (mv.t - 1) / fam.line_scale
        line = int(raw) if float(raw).is_integer() else raw
        letter = _letter_of(spec, mv.direction)
        side = 0 if mv.side == -1 else 1
        new_actions.append((mv.family, line, side, letter,
                            _pos_of(spec, form, mv.moved[0])))

    # ---- 4) 真盘重放终裁 + 漂移门（引擎差分对齐过，仍按纪律实测一遍）----
    if _game_is_at(game, form, start_coords):
        verdict = _verify(game, actions, new_actions, step, form)
        if verdict is None:
            return {'actions': list(actions), 'applied': False, 'flips': 0,
                    'note': 'anti_drift: 改写序列在经典盘上回放失败，放弃'}
        d_old, d_new = verdict
        if d_new > d_old:
            # 换侧不是越多越好：原本漂移已经很小（canonicalize 修好之后常见），
            # 硬换侧反而把整盘推远。宁可不动。
            return {'actions': list(actions), 'applied': False, 'flips': 0,
                    'note': f'anti_drift: 改写后漂移 {d_old:.2f}→{d_new:.2f} '
                            f'格反而变大，放弃'}
        note = ''
    else:
        note = 'anti_drift: 起点非当前盘面，仅做引擎层校验（未做真盘回放）'

    return {'actions': new_actions, 'applied': True, 'flips': rw.flips,
            'note': note}


def _game_is_at(game, form, start_coords):
    """当前盘面是否就是 start_coords 描述的那个局面（用于决定能否真盘回放）。"""
    if start_coords is None:
        return True
    if form == 'triangle':
        import solver.ml.tri_adapter as ad
        cur = ad.tri_coords(game)
    elif form == 'mi':
        import solver.ml.mi_adapter as ad
        cur = ad.mi_coords(game)
    else:
        return False
    return set(map(tuple, cur)) == set(map(tuple, start_coords))


def _drift_of(c0, c1):
    """边界盒最小角的 L∞ 位移（与引擎 drift_offsets 的锚点口径一致）。"""
    mr0, mc0 = min(c[0] for c in c0), min(c[1] for c in c0)
    mr1, mc1 = min(c[0] for c in c1), min(c[1] for c in c1)
    return max(abs(mr1 - mr0), abs(mc1 - mc0))


def _verify(game, old_actions, new_actions, step, form):
    """真盘重放终裁：返回 (原序列漂移, 新序列漂移)；任一条不能回放则 None。

    比较用平移归一（两条路径本就允许差一个整体平移），并顺带校验改写
    序列每一步在经典盘上真的可执行、块数不变。
    """
    import copy
    if form == 'triangle':
        import solver.ml.tri_adapter as ad
        coords_fn, canon = ad.tri_coords, ad.tri_canonical
    elif form == 'mi':
        import solver.ml.mi_adapter as ad
        coords_fn, canon = ad.mi_coords, ad.mi_canonical
    else:
        return None
    n0 = len(coords_fn(game))
    start = coords_fn(game)

    def run(actions):
        g = copy.deepcopy(game)
        for a in actions:
            if not ad.apply_action(g, a, step):
                return None
            if len(coords_fn(g)) != n0:
                return None
        return coords_fn(g)

    old_end = run(old_actions)
    new_end = run(new_actions)
    if old_end is None or new_end is None:
        return None
    if canon(old_end) != canon(new_end):
        return None
    return _drift_of(start, old_end), _drift_of(start, new_end)
