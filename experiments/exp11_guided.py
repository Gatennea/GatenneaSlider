# -*- coding: utf-8 -*-
"""实验11：定向启发搜索（GBFS / weighted A*）作为尺寸无关的"最后一公里"。

从聚拢态出发，目标 = 任意矩形（规范后唯一）；
启发 h = 窗口内洞数 + 凸起到最近缺口的步长距离，引导搜索，canonical 去重。
不建全表，故可放大。
"""
import argparse
import heapq

from solver.table_core import canonicalize
from experiments import harness as H
from experiments.exp9_rep import replay_steps
from experiments.exp10_setup import expand, best_window, fast_window, DDIR


def is_rect(coords):
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    return len(coords) == (max(rs) - min(rs) + 1) * (max(cs) - min(cs) + 1)


def heuristic(coords, m, n, step):
    win, holes, protr = fast_window(coords, m, n)
    h = len(holes)
    # 每个凸起到最近缺口的曼哈顿 / step
    for p in protr:
        if holes:
            d = min(abs(p[0] - q[0]) + abs(p[1] - q[1]) for q in holes)
            h += max(1, d // step)
    return h


def guided_solve(coords, m, n, step, budget=300000, weight=2.0, mode='gbfs'):
    start = frozenset(coords)
    goal = canonicalize(start)  # 占位
    # 矩形目标规范 key：直接用一个 m×n 实心矩形
    rect = frozenset((r, c) for r in range(m) for c in range(n))
    goal = canonicalize(rect)

    def h(c):
        return heuristic(c, m, n, step)

    counter = 0
    # 优先队列项： (f, g, tie, cur, path, P无关——path 已含 rep)
    h0 = h(start)
    openq = [(h0, 0, 0, start, [])]
    bestg = {canonicalize(start): 0}
    closed = set()          # 每个规范状态至多扩展一次（不要求最优）
    expanded = 0
    while openq:
        f, g, _, cur, path = heapq.heappop(openq)
        ck = canonicalize(cur)
        if ck == goal:
            return path, expanded
        if g > bestg.get(ck, -1) or ck in closed:
            continue
        closed.add(ck)
        expanded += 1
        if expanded > budget:
            return None, expanded
        for new, act, rep in expand(cur, step):
            nk = canonicalize(new)
            ng = g + 1
            if ng >= bestg.get(nk, 10 ** 9):
                continue
            bestg[nk] = ng
            hn = h(new)
            fn = hn if mode == 'gbfs' else ng + weight * hn
            counter += 1
            heapq.heappush(openq, (fn, ng, counter, new,
                                   path + [(act, rep)]))
    return None, expanded


def guided_reduce_one(coords, m, n, step, budget=80000):
    """GBFS 目标 = 窗口内洞数比起点少（至少填一个洞），用于逐次消解多缺口。
    返回 (path, expanded)。"""
    import heapq
    start = frozenset(coords)
    h0 = len(fast_window(start, m, n)[1])
    counter = 0
    openq = [(h0, 0, 0, start, [])]
    bestg = {canonicalize(start): 0}
    closed = set()
    expanded = 0
    while openq:
        f, g, _, cur, path = heapq.heappop(openq)
        ck = canonicalize(cur)
        if g > bestg.get(ck, -1) or ck in closed:
            continue
        if len(fast_window(cur, m, n)[1]) < h0:
            return path, expanded
        closed.add(ck)
        expanded += 1
        if expanded > budget:
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


def greedy_dfs(coords, m, n, step, cap=60, budget=120000):
    """贪心深度优先：每次优先扩展 h 最小的子节点，死路才回溯。
    返回 (path, expanded)。"""
    rect = frozenset((r, c) for r in range(m) for c in range(n))
    goal = canonicalize(rect)
    state = {'nodes': 0}

    def dfs(cur, g, visited):
        ck = canonicalize(cur)
        if ck == goal:
            return []
        if g >= cap:
            return None
        state['nodes'] += 1
        if state['nodes'] > budget:
            return None
        children = expand(cur, step)
        children.sort(key=lambda e: heuristic(e[0], m, n, step))
        for new, act, rep in children:
            nk = canonicalize(new)
            if nk in visited:
                continue
            visited.add(nk)
            r = dfs(new, g + 1, visited)
            if r is not None:
                return [(act, rep)] + r
        return None

    r = dfs(frozenset(coords), 0, {canonicalize(frozenset(coords))})
    return r, state['nodes']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='1000,1003')
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--budget', type=int, default=300000)
    ap.add_argument('--weight', type=float, default=2.0)
    ap.add_argument('--mode', default='gbfs')
    args = ap.parse_args()
    m, n, st = (int(x) for x in args.configs.split('x'))

    from solver.ml.gather_solver import gradient_gather
    for seed in (int(s) for s in args.seeds.split(',')):
        snap = H.gen_state(m, n, st, seed)
        g = H.load_game(snap)
        r = gradient_gather(g, st)
        gsteps = [(a, None) for a in r['actions']]
        _ok, g2 = replay_steps(snap, gsteps)
        coords = H.coords_of(g2)
        path, used = guided_solve(coords, m, n, st, args.budget,
                                  args.weight, args.mode)
        if path is None:
            print(f"seed{seed} 搜索耗尽 nodes={used}")
            continue
        allsteps = gsteps + path
        ok, _ = replay_steps(snap, allsteps)
        print(f"seed{seed} 解={ok} 总步={len(allsteps)} 末段{len(path)} "
              f"nodes={used}")


if __name__ == '__main__':
    main()
