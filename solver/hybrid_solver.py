# -*- coding: utf-8 -*-
"""尺寸无关混合求解器（人类分段规划思路 + 搜索兜底）。

流水线（pipeline='alt'，默认，2026-09-30 起）：
    多段「聚拢小块 + 填洞宏」交替，直到无法改进 → 逐次单缺口 GBFS 消解
    —— exp20 实测（5×5 step2，8 seed）：比旧流水线快约 4.5 倍（34.1s→7.5s），
    成功率不变；填洞与聚拢互补、各有独立贡献（消融：去掉任一段慢 ~70%）。

流水线（pipeline='legacy'，保留作回退）：
    全程梯度聚拢 → 填洞宏(带分量代表格) → 逐次单缺口 GBFS 消解

全程 (action, rep_cell) 统一、每段以"从初始态重放"锚定坐标系，
最终返回 (actions, rep_cells)，与查表求解器一致，GUI 可直接播放。

返回：
    (actions, rep_cells)  成功
    False                未能求解（预算/守卫耗尽）
    None                 缺少必要组件
"""
import io
from contextlib import redirect_stdout
from copy import deepcopy

from solver.actions import apply_action
from solver.table_core import _side_components, is_single_connected
from solver.search_core import (fast_window, guided_reduce_one)
from solver.ml.gather_solver import gradient_gather, gather_solve, gather_metrics
from solver.ml.fill_macro import solve_fill_macro


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


def _quiet(fn, *a, **kw):
    """静音执行（填洞宏会往 stdout 打大量过程日志，交替轮数多时会刷屏）。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        return fn(*a, **kw)


def _fill_pairs(res):
    """填洞宏结果 → [(action, rep), ...]；无成果返回 []。"""
    if isinstance(res, tuple):
        return list(zip(res[0], res[1]))
    if isinstance(res, dict) and res.get('type') == 'fill_partial':
        return list(zip(res.get('actions', []),
                        res.get('rep_cells', [])))
    return []


def hybrid_solve(game, step, cancel_check=None, progress_callback=None,
                 node_budget=80000, max_rounds=12,
                 pipeline='alt', alt_chunk=30, alt_max_rounds=8,
                 alt_order='gather_first', **_kwargs):
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
        # 多段「聚拢 + 填洞」交替，直到无法改进（exp20 实测优于旧流水线）。
        for _round in range(alt_max_rounds):
            g = replay(steps)
            if g is None:
                return False
            if g.is_solved():
                return _finalize(steps)
            improved = False
            ops = (('gather', 'fill') if alt_order == 'gather_first'
                   else ('fill', 'gather'))
            for op in ops:
                if cancelled():
                    return False
                before = score(g)
                if op == 'gather':
                    r = gather_solve(g, step, max_steps=alt_chunk,
                                     patience=max(30, alt_chunk),
                                     max_wait_time=20,
                                     cancel_check=cancel_check)
                    cand = list(zip(r['actions'],
                                    r.get('rep_cells')
                                    or [None] * len(r['actions'])))
                else:
                    cand = _fill_pairs(_quiet(solve_fill_macro, g, step))
                if not cand:
                    continue
                tent = replay(steps + cand)
                if tent is None:
                    continue
                if tent.is_solved():
                    return _finalize(steps + cand)
                if score(tent) > before + 1e-9:
                    steps = steps + cand
                    g = tent
                    improved = True
            if not improved:
                break
    else:
        # 旧流水线（回退用）：全程梯度聚拢 → 填洞宏（仅当不降低聚拢度）
        g = deepcopy(base)
        r = gradient_gather(g, step)
        steps += [(a, None) for a in r['actions']]
        g = replay(steps)
        if g is None:
            return False
        if g.is_solved():
            return _finalize(steps)

        res = _quiet(solve_fill_macro, g, step)
        fsteps = _fill_pairs(res)
        if fsteps:
            tent = replay(steps + fsteps)
            if tent is not None:
                before = score(replay(steps))
                after = score(tent)
                if tent.is_solved():
                    return _finalize(steps + fsteps)
                if after >= before:
                    steps += fsteps

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
