# -*- coding: utf-8 -*-
"""尺寸无关混合求解器（人类分段规划思路 + 搜索兜底）。

流水线（pipeline='alt'，默认，2026-09-30 起）：
    多段「聚拢小块」交替，直到无法改进 → 逐次单缺口 GBFS 消解
    —— exp20 实测（5×5 step2，8 seed）：比旧流水线快约 4.5 倍（34.1s→7.5s），
    成功率不变。混合内填洞宏已于 2026-10-16 经 exp1 消融确认拖后腿
    （6×6 大尺寸反而超时、5×5 同解长但更慢）而移除；其贡献由独立候选层
    「补缺宏」与段3 GBFS 覆盖。

流水线（pipeline='legacy'，保留作回退）：
    全程梯度聚拢 → 逐次单缺口 GBFS 消解。

全程 (action, rep_cell) 统一、每段以"从初始态重放"锚定坐标系，
最终返回 (actions, rep_cells)，与查表求解器一致，GUI 可直接播放。

返回：
    (actions, rep_cells)  成功
    False                未能求解（预算/守卫耗尽）
    None                 缺少必要组件
"""
from copy import deepcopy

from solver.actions import apply_action
from solver.table_core import _side_components, is_single_connected
from solver.search_core import (fast_window, guided_reduce_one)
from solver.ml.gather_solver import gradient_gather, gather_solve, gather_metrics


def apply_with_rep(game, action, step, rep_cell):
    """选中包含 rep_cell 的连通分量并执行 action（解决多分量歧义）。"""
    gt, L, side, d = action
    cur = frozenset((b.location[0], b.location[1]) for b in game.blocks)
    chosen = next((c for c in _side_components(set(cur), gt, L, side)
                   if rep_cell in c), None)
    if chosen is None:
        return False
    rep_block = next((b for b in game.blocks
                      if (b.location[0], b.location[1]) == rep_cell), None)
    if rep_block is None:
        return False
    for b in game.blocks:
        b.be_opted = False
    game.opt(gt, L, rep_block)
    final = game.try_move(d, step)
    if not final:
        for b in game.blocks:
            b.be_opted = False
        return False
    selected = [b for b in game.blocks if b.be_opted]
    test = []
    for b in game.blocks:
        test.append(tuple(final[selected.index(b)]) if b.be_opted
                    else tuple(b.location))
    if len(test) != len(game.blocks) or not is_single_connected(test):
        for b in game.blocks:
            b.be_opted = False
        return False
    game.commit_move(final)
    for b in game.blocks:
        b.be_opted = False
    return True


def hybrid_solve(game, step, cancel_check=None, progress_callback=None,
                 node_budget=80000, max_rounds=12,
                 pipeline='alt', alt_chunk=30, alt_max_rounds=8,
                 **_kwargs):
    base = deepcopy(game)
    m, n = game.m, game.n

    def replay(steps):
        g = deepcopy(base)
        for act, rep in steps:
            ok = (apply_with_rep(g, act, step, rep) if rep is not None
                  else apply_action(g, act, step))
            if not ok:
                return None
        return g

    def score(g):
        return gather_metrics(frozenset((b.location[0], b.location[1])
                                        for b in g.blocks), m, n)['score']

    def cancelled():
        return cancel_check is not None and cancel_check()

    steps = []

    if pipeline == 'alt':
        # 多段「聚拢」交替，直到无法改进（exp20 实测优于旧流水线；混合内填洞宏
        # 已于 2026-10-16 经 exp1 消融确认拖后腿而移除——其贡献由独立候选层
        # 「补缺宏」与段3 GBFS 覆盖）。
        for _round in range(alt_max_rounds):
            g = replay(steps)
            if g is None:
                return False
            if g.is_solved():
                return _finalize(steps)
            improved = False
            before = score(g)
            r = gather_solve(g, step, max_steps=alt_chunk,
                             patience=max(30, alt_chunk),
                             max_wait_time=20,
                             cancel_check=cancel_check)
            cand = list(zip(r['actions'],
                            r.get('rep_cells')
                            or [None] * len(r['actions'])))
            if cand:
                tent = replay(steps + cand)
                if tent is not None:
                    if tent.is_solved():
                        return _finalize(steps + cand)
                    if score(tent) > before + 1e-9:
                        steps = steps + cand
                        g = tent
                        improved = True
            if not improved:
                break
    else:
        # 旧流水线（回退用）：全程梯度聚拢 → GBFS
        g = deepcopy(base)
        r = gradient_gather(g, step)
        steps += [(a, None) for a in r['actions']]
        g = replay(steps)
        if g is None:
            return False
        if g.is_solved():
            return _finalize(steps)

    # 段3：逐次单缺口 GBFS
    rounds = 0
    while rounds < max_rounds:
        g = replay(steps)
        if g is None:
            return False
        if g.is_solved():
            return _finalize(steps)
        rounds += 1
        coords = frozenset((b.location[0], b.location[1]) for b in g.blocks)
        path, used = guided_reduce_one(coords, m, n, step,
                                      budget=node_budget,
                                      cancel_check=cancel_check)
        if not path:
            return False
        steps += path

    return False


def _finalize(steps):
    actions = [a for a, _ in steps]
    rep_cells = [rep for _, rep in steps]
    return actions, rep_cells
