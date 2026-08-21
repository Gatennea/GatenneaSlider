# -*- coding: utf-8 -*-
"""
table_core 正确性测试：
  1. 前驱/正向边一致性：对随机可达状态 C，
     - 完备性：B ∈ forward_neighbors(C) ⟹ canonical(C) ∈ predecessors(B)
     - 正确性：P ∈ predecessors(B) ⟹ B ∈ forward_neighbors(coords(P))
  2. 反向 BFS 距离 vs 穷举正向 BFS 距离（小尺寸）一致性。
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver import table_core as tc


def random_walk(goal, step, total, steps):
    """从目标出发随机走 steps 步，返回当前状态坐标集合。"""
    cur = set(goal)
    for _ in range(steps):
        nbrs = tc.forward_neighbors(cur, step, total)
        if not nbrs:
            break
        h = random.choice(list(nbrs))
        cur = set(tc.int_to_coords(h, total))
    return cur


def test_consistency(m, n, step, rounds=200, walk=12):
    total = m * n
    goal = tc.goal_state(m, n)
    fails = 0
    for _ in range(rounds):
        C = random_walk(goal, step, total, walk)
        cH = tc.canonicalize(C)
        fw = tc.forward_neighbors(C, step, total)
        # 完备性
        for bH in fw:
            B = set(tc.int_to_coords(bH, total))
            preds = tc.predecessors(B, m, n, step)
            if cH not in preds:
                print(f"[完备性失败] m={m} n={n} step={step}")
                print("  C =", sorted(C))
                print("  B =", sorted(B))
                fails += 1
                if fails > 5:
                    return False
        # 正确性：对 B=C 自身的前驱，每个前驱 P 应满足 C ∈ forward_neighbors(P)
        predsC = tc.predecessors(C, m, n, step)
        for pH in predsC:
            P = set(tc.int_to_coords(pH, total))
            fwP = tc.forward_neighbors(P, step, total)
            if cH not in fwP:
                print(f"[正确性失败] m={m} n={n} step={step}")
                print("  P =", sorted(P))
                print("  C =", sorted(C))
                fails += 1
                if fails > 5:
                    return False
    print(f"[OK] m={m} n={n} step={step}  轮数={rounds} 失败={fails}")
    return True


def reverse_bfs_table(m, n, step):
    """反向 BFS：从目标出发，dist[canonical]=求解距离。"""
    total = m * n
    goal = tc.goal_state(m, n)
    gH = tc.canonicalize(goal)
    dist = {gH: 0}
    frontier = [gH]
    d = 0
    while frontier:
        d += 1
        nxt = []
        for h in frontier:
            B = set(tc.int_to_coords(h, total))
            for pH in tc.predecessors(B, m, n, step):
                if pH not in dist:
                    dist[pH] = d
                    nxt.append(pH)
        frontier = nxt
    return dist


def forward_bfs_distances(m, n, step):
    """正向 BFS 从目标（打乱距离），用于交叉对比状态总数与可达性。"""
    total = m * n
    goal = tc.goal_state(m, n)
    gH = tc.canonicalize(goal)
    dist = {gH: 0}
    frontier = [gH]
    d = 0
    while frontier:
        d += 1
        nxt = []
        for h in frontier:
            B = set(tc.int_to_coords(h, total))
            for nbH in tc.forward_neighbors(B, step, total):
                if nbH not in dist:
                    dist[nbH] = d
                    nxt.append(nbH)
        frontier = nxt
    return dist


def test_bfs_consistency(m, n, step):
    total = m * n
    rev = reverse_bfs_table(m, n, step)
    fwd = forward_bfs_distances(m, n, step)
    print(f"[BFS] m={m} n={n} step={step}  反向状态数={len(rev)} 正向状态数={len(fwd)}")
    # 反向表中的每个状态（可解）应在正向表中（可达），反之未必（不可解的打乱态）
    only_fwd = set(fwd) - set(rev)
    print(f"       仅正向可达(不可解)={len(only_fwd)}  仅反向={len(set(rev)-set(fwd))}")
    # 验证反向距离的正确性：对反向表中随机状态 S，存在正向邻居 dist-1，且无邻居 dist<dist-1
    import random as _r
    sample = _r.sample(list(rev.keys()), min(50, len(rev)))
    bad = 0
    for sH in sample:
        if rev[sH] == 0:
            continue
        S = set(tc.int_to_coords(sH, total))
        fw = tc.forward_neighbors(S, step, total)
        nbr_dists = [rev[x] for x in fw if x in rev]
        if not nbr_dists or min(nbr_dists) != rev[sH] - 1:
            print(f"  [距离错误] dist={rev[sH]} 邻居最小距离={min(nbr_dists) if nbr_dists else None}")
            bad += 1
            if bad > 3:
                break
    print(f"       距离一致性抽样: {'OK' if bad == 0 else f'失败{bad}'}")
    return bad == 0


if __name__ == '__main__':
    random.seed(42)
    print("=== 一致性测试 ===")
    ok = True
    ok &= test_consistency(2, 2, 1)
    ok &= test_consistency(2, 3, 1)
    ok &= test_consistency(3, 2, 1)
    ok &= test_consistency(2, 2, 2)
    ok &= test_consistency(3, 3, 1, rounds=60, walk=10)
    print("\n=== BFS 距离一致性 ===")
    ok &= test_bfs_consistency(2, 2, 1)
    ok &= test_bfs_consistency(2, 3, 1)
    ok &= test_bfs_consistency(2, 2, 2)
    print("\n结果:", "全部通过" if ok else "存在失败")
    sys.exit(0 if ok else 1)
