# -*- coding: utf-8 -*-
"""最后一公里搜索：从高聚拢度状态出发的有界 IDDFS。

动机：gather/填洞把局面带到 0.9+ 后，剩余状态空间很小，固定共轭宏会被
几何卡住（"需双层"）。此时用带置换表 + 逆动作剪枝 + 分数排序的有界
迭代加深搜索直接找复原路径，作为填洞失败时的兜底。

与现有 ida_star 的区别：只做"整形"单目标（is_solved），从任意高重叠
状态启动，不设 G1 阶段；启发只用于排序（不需要可纳性）。
"""
import time

from solver.actions import (enumerate_valid_actions, apply_action,
                            is_inverse_action)
from solver.heuristic import compute_score
from solver.state import snapshot, restore, state_key


def last_mile_solve(game, step, max_depth=40, max_nodes=400000,
                    time_limit=20.0, cancel_check=None):
    """返回动作列表或 None。game 不会被改动（内部快照还原）。"""
    if game.is_solved():
        return []
    start = time.time()
    nodes = [0]

    def dfs(g, g_cost, bound, path):
        if cancel_check and cancel_check():
            return None
        if time.time() - start > time_limit:
            return None
        nodes[0] += 1
        if nodes[0] > max_nodes:
            return None
        key = state_key(g)
        if key in tt and tt[key] <= g_cost:
            return None
        tt[key] = g_cost
        if g.is_solved():
            return list(path)
        if g_cost == bound:
            return None

        acts = [a for a in enumerate_valid_actions(g, step)
                if not path or not is_inverse_action(path[-1], a)]

        scored = []
        for a in acts:
            s = snapshot(g)
            if not apply_action(g, a, step):
                restore(g, s)
                continue
            sc = compute_score(g)
            restore(g, s)
            scored.append((sc, a))
        scored.sort(key=lambda x: -x[0])

        for _sc, a in scored:
            s = snapshot(g)
            if not apply_action(g, a, step):
                restore(g, s)
                continue
            r = dfs(g, g_cost + 1, bound, path + [a])
            restore(g, s)
            if r is not None:
                return r
        return None

    for bound in range(1, max_depth + 1):
        tt = {}
        nodes[0] = 0
        r = dfs(game, 0, bound, [])
        if r is not None:
            return r
        if time.time() - start > time_limit:
            break
    return None
