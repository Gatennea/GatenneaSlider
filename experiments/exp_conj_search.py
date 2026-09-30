# -*- coding: utf-8 -*-
"""实验8：双层共轭自动合成（缺口→A→填洞→A'），免表验证。

对 gather 残局 S：
  1) 单洞宏可直接解 → 完成；
  2) 否则正向 BFS（exp 动作）找短序列 A，使 A(S) 成为
     「单内部洞 + 单凸起」的可填状态；
  3) solve_single_void 填洞（局部宏）；
  4) 反向 BFS（predecessors）+ 动作匹配，从填后状态找回目标 = A' 段。
整链不需要距离表；4x4 上用完整表仅作最优性对照。
"""
import time
from collections import deque

from experiments import harness as H
from experiments.exp_actions import enumerate_exp_actions, apply_exp_action
from experiments.exp_table_solve import load_table
from solver.state import snapshot, restore
from solver.table_core import canonicalize, int_to_coords, predecessors
from solver.ml.fill_macro import window_of, solve_single_void, _capture_apply


def apply_step(g, a, step):
    """统一应用：4 元组=exp动作，5 元组=fill动作（带 rep）。"""
    if len(a) == 4:
        return apply_exp_action(g, a, step)
    ok, _ = _capture_apply(g, a, step)
    return ok


def replay_all(residual_coords, m, n, step, actions):
    g = H.load_game({'m': m, 'n': n, 'step': step,
                     'coords': sorted(residual_coords)})
    for a in actions:
        if not apply_step(g, a, step):
            return False
    return g.is_solved()


def hole_kind(win, holes):
    r0, c0, (rh, cw) = win
    kinds = []
    for (r, c) in holes:
        edge = (r == r0 or r == r0 + rh - 1 or c == c0 or c == c0 + cw - 1)
        kinds.append('edge' if edge else 'inner')
    return kinds


def structurally_fillable(coords, m, n, step):
    """恰好 1 个内部洞 + 1 个凸起（洞不在窗口边缘）。"""
    win, _ov, holes, outside = window_of(frozenset(coords), m, n, step)
    if len(holes) != 1 or len(outside) != 1:
        return False
    return hole_kind(win, holes) == ['inner']


def find_A(coords, m, n, step, max_depth=6, node_cap=250000,
           skip_keys=()):
    """正向 BFS 找短序列 A → 结构化可填状态（纯集合转移）。"""
    from experiments.exp_actions import succ_pure
    start = frozenset(coords)
    start_key = canonicalize(start)
    skip = set(skip_keys)
    if start_key in skip:
        return None
    visited = {start_key}
    q = deque([(start, [])])
    while q:
        cur, path = q.popleft()
        if len(path) >= max_depth:
            continue
        for a, nxt in succ_pure(cur, m, n, step):
            k = canonicalize(nxt)
            if k in visited or k in skip:
                continue
            visited.add(k)
            newpath = path + [a]
            if structurally_fillable(nxt, m, n, step):
                return newpath, nxt
            q.append((nxt, newpath))
            if len(visited) > node_cap:
                return None
    return None


def find_A_guided(coords, m, n, step, max_depth=8, node_cap=50000,
                  skip_keys=(), hfn=None):
    """引导式 A 搜索：优先让「洞离开窗口边缘」的状态先扩展。

    启发：h = 边缘洞数；边缘洞越少越接近可填态（对应缺口→洞的梯度）。
    用优先队列做 best-first，深度限 max_depth；失败回退 BFS。
    """
    import heapq
    from experiments.exp_actions import succ_pure
    if hfn is None:
        hfn = edge_holes
    start = frozenset(coords)
    start_key = canonicalize(start)
    skip = set(skip_keys)
    if start_key in skip:
        return None
    visited = {start_key}
    pq = [(0, 0, start, [])]
    nxt_id = 1
    while pq:
        _h, _g, cur, path = heapq.heappop(pq)
        if len(path) >= max_depth:
            continue
        for a, nxt in succ_pure(cur, m, n, step):
            k = canonicalize(nxt)
            if k in visited or k in skip:
                continue
            visited.add(k)
            newpath = path + [a]
            if structurally_fillable(nxt, m, n, step):
                return newpath, nxt
            h = hfn(nxt, m, n, step)
            heapq.heappush(pq, (h * 100 + len(newpath), nxt_id, nxt, newpath))
            nxt_id += 1
            if len(visited) > node_cap:
                return None
    return None


def edge_holes(coords, m, n, step):
    """缺口数启发（简单）：边缘洞计数。"""
    win, _ov, holes, _out = window_of(frozenset(coords), m, n, step)
    r0, c0, (rh, cw) = win
    cnt = 0
    for (r, c) in holes:
        if r == r0 or r == r0 + rh - 1 or c == c0 or c == c0 + cw - 1:
            cnt += 1
    return cnt


def edge_holes_weighted(coords, m, n, step):
    """加权缺口分数：洞越靠边越大，另加凸起惩罚。"""
    win, _ov, holes, outside = window_of(frozenset(coords), m, n, step)
    r0, c0, (rh, cw) = win
    score = len(outside)
    for (r, c) in holes:
        dr = min(r - r0, r0 + rh - 1 - r)
        dc = min(c - c0, c0 + cw - 1 - c)
        # 内部洞 dr,dc >= 1；越靠边越小 → 分数越高
        score += 10 * (1 - min(dr, dc, 1)) + max(0, 3 - min(dr, dc))
    return score


def reverse_find(coords, goal_key, m, n, step, max_depth, node_cap):
    """反向 BFS 从 coords 找 goal；返回 key 链 [start_key, ..., goal]。"""
    start_key = canonicalize(coords)
    if start_key == goal_key:
        return [start_key]
    visited = {start_key}
    parent = {start_key: None}
    depth = {start_key: 0}
    q = deque([start_key])
    found = None
    while q:
        k = q.popleft()
        if depth[k] >= max_depth:
            continue
        for pk in predecessors(int_to_coords(k, m * n), m, n, step):
            if pk in visited:
                continue
            visited.add(pk)
            parent[pk] = k
            depth[pk] = depth[k] + 1
            if pk == goal_key:
                found = pk
                break
            q.append(pk)
        if found:
            break
        if len(visited) > node_cap:
            break
    if found is None:
        return None
    keys = []
    cur = found
    while cur is not None:
        keys.append(cur)
        cur = parent[cur]
    keys.reverse()
    return keys


def match_action(cur_coords, target_key, m, n, step):
    """从当前状态找 exp 动作，使结果 canonical 等于 target_key。"""
    g = H.load_game({'m': m, 'n': n, 'step': step,
                     'coords': sorted(cur_coords)})
    for a in enumerate_exp_actions(g, step):
        s = snapshot(g)
        ok = apply_exp_action(g, a, step)
        k = canonicalize(H.coords_of(g)) if ok else None
        restore(g, s)
        if ok and k == target_key:
            return a
    return None


def conj_chain(residual_coords, m, n, step, goal_key,
               max_a=6, undo_margin=5, guided=True):
    """返回 (actions, info)；失败抛 None 由调用方处理。"""
    g = H.load_game({'m': m, 'n': n, 'step': step,
                     'coords': sorted(residual_coords)})
    # 1) 直接单洞宏（仅当结构上恰好 1 内部洞 + 1 凸起）
    if structurally_fillable(residual_coords, m, n, step):
        acts, _ = solve_single_void(residual_coords, m, n, step)
        if acts is not None:
            if replay_all(residual_coords, m, n, step, acts):
                return acts, {'mode': 'direct_fill', 'fill': len(acts)}

    # 2) 找 A（两种 guided 启发先后试，BFS 最后保完备）
    skip = set()
    found = None
    for _try in range(3):
        if guided:
            for hfn in (edge_holes, edge_holes_weighted):
                found = find_A_guided(residual_coords, m, n, step,
                                      max_a + 2, 200000,
                                      skip_keys=tuple(skip), hfn=hfn)
                if found is not None:
                    break
        if found is None:
            found = find_A(residual_coords, m, n, step, max_a,
                           250000, skip_keys=tuple(skip))
        if found is None:
            return None, {'mode': 'no_A'}
        A, s1_coords = found
        # 3) 填洞（候选已保证结构化可填）
        acts, _ = solve_single_void(s1_coords, m, n, step)
        if acts is not None:
            break
        skip.add(canonicalize(s1_coords))
    else:
        return None, {'mode': 'fill_fail'}

    g2 = H.load_game({'m': m, 'n': n, 'step': step,
                      'coords': sorted(residual_coords)})
    for a in A:
        if not apply_exp_action(g2, a, step):
            return None, {'mode': 'A_replay_fail'}
    for a in acts:
        ok, _ = _capture_apply(g2, a, step)
        if not ok:
            return None, {'mode': 'fill_apply_fail'}
    s2_coords = H.coords_of(g2)

    # 4) 反向找 A'
    keys = reverse_find(s2_coords, goal_key, m, n, step,
                        len(A) + undo_margin, 300000)
    if keys is None:
        return None, {'mode': 'no_reverse'}
    undo = []
    cur = s2_coords
    for tkey in keys[1:]:
        a = match_action(cur, tkey, m, n, step)
        if a is None:
            return None, {'mode': 'undo_match_fail'}
        undo.append(a)
        cur = frozenset(int_to_coords(tkey, m * n))

    full = A + acts + undo
    # 整体重放验证（统一应用两种动作）
    ok = replay_all(residual_coords, m, n, step, full)
    return (full if ok else None), {'mode': 'conj', 'A': len(A),
                                    'fill': len(acts), 'undo': len(undo)}


def main():
    table = load_table()
    goal_key = canonicalize(frozenset((r, c) for r in range(4)
                                      for c in range(4)))
    seeds = list(range(1000, 1040))
    from solver.ml.gather_solver import gather_solve, gradient_gather

    for gname, gfn in (('plain', gather_solve), ('gradient', gradient_gather)):
        n_solved = 0
        stats = []
        for seed in seeds:
            snap = H.gen_state(4, 4, 2, seed)
            g = H.load_game(snap)
            d_opt = table[canonicalize(H.coords_of(g))]
            gfn(g, 2)
            if g.is_solved():
                n_solved += 1
                stats.append((seed, 'gather', 0, 0, 0))
                continue
            rc = H.coords_of(g)
            d_res = table[canonicalize(rc)]
            t0 = time.perf_counter()
            res = conj_chain(rc, 4, 4, 2, goal_key)
            dt = time.perf_counter() - t0
            if res[0] is None:
                stats.append((seed, f'FAIL:{res[1]["mode"]}', d_res,
                              d_opt, round(dt, 1)))
                continue
            acts, info = res
            n_solved += 1
            info_extra = f"A{info.get('A',0)}/f{info['fill']}/u{info.get('undo',0)}"
            stats.append((seed, info['mode'], d_res, d_opt, len(acts)))
            print(f'  seed{seed} {info["mode"]:11s} {info_extra} '
                  f'链长={len(acts):3d} 残局最优={d_res} '
                  f'初始最优={d_opt} 差={len(acts)-d_res:+3d} {dt:.1f}s')
        print(f'=== {gname}: 解出 {n_solved}/{len(seeds)} ===')
        fails = [s for s in stats if s[1].startswith('FAIL')]
        for f in fails:
            print(f'    {f[0]} {f[1]} 残局距离={f[2]}')
        chain_lens = [s[4] for s in stats if not s[1].startswith('FAIL')]
        if chain_lens:
            opt = [s[3] for s in stats if not s[1].startswith('FAIL')]
            excess = [a - o for a, o in zip(chain_lens, opt)]
            print(f'    全链超出最优: 中位={sorted(excess)[len(excess)//2]} '
                  f'最大={max(excess)}')


if __name__ == '__main__':
    main()
