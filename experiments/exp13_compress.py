# -*- coding: utf-8 -*-
"""实验13：混合求解器解的**后处理压缩**（循环消除）。

背景（2026-09-30 验收）：4×4 step2 上 hybrid 解长中位是最优的 17.2 倍，
冗余主要来自段1 梯度聚拢——绕一圈又回到已经走过的局面。

原理：本游戏**方块不可区分**，所以「局面」就是坐标的 frozenset。
于是解序列里凡是出现重复局面，中间那一段就是纯绕路（循环），可以直接整段删掉；
共轭结构 A·B·A′ 里的 A/A′ 冗余往返也包含在内（两步净效果为空 = 长度 2 的循环）。

做法：正向扫描，维护 局面→索引；遇到已见局面就删掉中间整段，增量维护局面序列。
**压缩后必须全量重放验证**，并用完整 BFS 表对照最优距离。

用法：
    python -m experiments.exp13_compress --configs 4x4x2 --n 20
"""
import argparse
import time

from experiments import harness as H
from experiments.exp9_rep import replay_steps, _apply_with_rep
from experiments.exp12_chain import solve as chain_solve


def states_of(snap, steps):
    """逐步重放，返回局面序列（长度 = len(steps)+1）。任一步失败返回 None。"""
    g = H.load_game(snap)
    states = [H.coords_of(g)]
    for action, rep in steps:
        if rep is None:
            ok = H.apply_action(g, action, snap['step'])
        else:
            ok = _apply_with_rep(g, action, snap['step'], rep)
        if not ok:
            return None
        states.append(H.coords_of(g))
    return states


def compress(snap, steps):
    """删除所有「回到已访问局面」的绕路段。返回 (压缩后 steps, 删除步数)。

    只做纯序列后处理：不改任何一步的内容，因此 rep_cell 语义保持有效
    （回到同一局面时，当初记录的代表格仍然落在同一个分量里）。
    """
    steps = list(steps)
    states = states_of(snap, steps)
    if states is None:
        return None, 0
    seen = {states[0]: 0}
    removed = 0
    i = 0
    while i < len(steps):
        s = states[i + 1]
        j = seen.get(s)
        if j is not None and j <= i:
            del steps[j:i + 1]
            del states[j + 1:i + 2]
            removed += i - j + 1
            seen = {st: k for k, st in enumerate(states[:j + 1])}
            i = j
            continue
        seen[s] = i + 1
        i += 1
    return steps, removed


def optimal_distance(snap):
    """查完整 BFS 表拿最优距离；无表/未覆盖返回 None。"""
    from solver import table_core as tc
    from solver.table_solver import load_table
    tbl = load_table(snap['m'], snap['n'], snap['step'])
    if tbl is None:
        return None
    coords = frozenset(tuple(c) for c in snap['coords'])
    return tbl.get(tc.canonicalize(coords))


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2] if s else 0


def run_config(m, n, st, count, budget):
    snaps = H.build_corpus([(m, n, st)], count)
    rows = []
    t0 = time.time()
    for snap in snaps:
        t1 = time.perf_counter()
        try:
            res, who = chain_solve(snap, budget=budget)
        except Exception as e:
            res, who = None, f'exc:{e!r}'
        t_solve = time.perf_counter() - t1

        if not res or not replay_steps(snap, res)[0]:
            print(f"  seed{snap['seed']} 败 {who}")
            continue

        t2 = time.perf_counter()
        comp, removed = compress(snap, res)
        t_comp = time.perf_counter() - t2
        ok2 = comp is not None and replay_steps(snap, comp)[0]
        if not ok2:
            print(f"  seed{snap['seed']} 压缩后重放失败（丢弃压缩结果）")
            comp, removed, ok2 = res, 0, True

        opt = optimal_distance(snap)
        rows.append({
            'seed': snap['seed'], 'who': who,
            'orig': len(res), 'comp': len(comp), 'opt': opt,
            't_solve': t_solve, 't_comp': t_comp,
        })
        r0 = f"{len(res)/opt:.1f}x" if opt else '-'
        r1 = f"{len(comp)/opt:.1f}x" if opt else '-'
        print(f"  seed{snap['seed']} {len(res):>4}步 → {len(comp):>4}步 "
              f"(删{removed:>4}) 最优={opt} 倍数 {r0}→{r1} "
              f"[{t_solve:.1f}s+{t_comp:.1f}s] {who}")

    if not rows:
        print("[无成功样本]")
        return

    with_opt = [r for r in rows if r['opt']]
    print(f"\n[{m}x{n} step{st}] 样本 {len(rows)}/{len(snaps)}  总耗时 {time.time()-t0:.0f}s")
    print(f"   步数中位        压缩前={median([r['orig'] for r in rows])} "
          f"→ 压缩后={median([r['comp'] for r in rows])}")
    print(f"   压缩率中位      {median([100*(r['orig']-r['comp'])/max(1, r['orig']) for r in rows]):.0f}%")
    if with_opt:
        print(f"   最优倍数中位    {median([r['orig']/r['opt'] for r in with_opt]):.1f}x "
              f"→ {median([r['comp']/r['opt'] for r in with_opt]):.1f}x")
        print(f"   最优倍数均值    {sum(r['orig']/r['opt'] for r in with_opt)/len(with_opt):.1f}x "
              f"→ {sum(r['comp']/r['opt'] for r in with_opt)/len(with_opt):.1f}x")
        within2 = sum(1 for r in with_opt if r['comp']/r['opt'] <= 2)
        print(f"   压缩后 ≤2倍最优 {within2}/{len(with_opt)}（压缩前 "
              f"{sum(1 for r in with_opt if r['orig']/r['opt'] <= 2)}/{len(with_opt)}）")
    print(f"   压缩耗时中位    {median([r['t_comp'] for r in rows]):.2f}s")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--n', type=int, default=20)
    ap.add_argument('--budget', type=int, default=300000)
    args = ap.parse_args()
    m, n, st = (int(x) for x in args.configs.split('x'))
    run_config(m, n, st, args.n, args.budget)


if __name__ == '__main__':
    main()
