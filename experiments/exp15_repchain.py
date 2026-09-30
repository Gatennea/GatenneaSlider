# -*- coding: utf-8 -*-
"""实验15：给段1（梯度聚拢）的每一步**补上代表格 rep**，消除多分量歧义。

起因（exp14）：截断聚拢后解长从 581 步降到 26~80 步（倍数 83x→3.2x），
但成功率从 100% 崩到 20~40%，失败原因几乎全是 `guided_replay_bad`。

怀疑对象就是那个已知缺陷：`solver/actions.py::apply_action` 恒取
`side_blocks[0]`，分量选择依赖 blocks 列表顺序；**同一串动作在另一时刻重放
可能选中不同分量** → 求解时走得通、事后重放走不通。

本实验不改 apply_action（那是另一项待修），而是在链路上**补 rep**：
执行每一步前先算出 apply_action 会选中的那个分量，把其中一格记为 rep，
然后用 `_apply_with_rep` 执行，重放时按 rep 锁定同一分量 → 全链路确定。

若成功率恢复而步数仍然很短，则证明「早交接」的价值，并且说明
**补 rep 是早交接能落地的前提**。

用法：
    python -m experiments.exp15_repchain --n 5
"""
import argparse
import time

from experiments import harness as H
from experiments.exp9_rep import replay_steps, _apply_with_rep
from experiments.exp13_compress import optimal_distance, median
from experiments.exp14_truncate import LONG_SEEDS

CAPS = [None, 30, 15, 8]


def solve_rep(snap, gather_cap=None):
    """带 rep 的混合链（段1 补代表格）。返回 (steps, who)。"""
    from solver.actions import _get_side_blocks
    from solver.table_core import _side_components
    from solver.ml.gather_solver import gradient_gather
    from solver.ml.fill_macro import solve_fill_macro

    step = snap['step']

    # 先在探针上跑完整聚拢拿到动作序列（它会原地执行，故用副本）
    probe = H.load_game(snap)
    acts = gradient_gather(probe, step)['actions']
    if gather_cap is not None:
        acts = acts[:gather_cap]

    def pick_rep(game, action):
        gt, L, side, _d = action
        side_blocks = _get_side_blocks(game, gt, L, side)
        if not side_blocks:
            return None
        rep = tuple(side_blocks[0].location)
        cur = frozenset(tuple(b.location) for b in game.blocks)
        comps = _side_components(set(cur), gt, L, side)
        return rep if any(rep in c for c in comps) else None

    g = H.load_game(snap)
    steps = []
    for a in acts:
        rep = pick_rep(g, a)
        if rep is None:
            return None, 'no_rep'
        if not _apply_with_rep(g, a, step, rep):
            return None, 'apply_bad'
        steps.append((a, rep))
    if g.is_solved():
        return steps, 'gather'

    # 段2：填洞宏（自带 rep）
    res = solve_fill_macro(g, step)
    fsteps = []
    if isinstance(res, tuple):
        fsteps = list(zip(res[0], res[1]))
    elif isinstance(res, dict) and res.get('type') == 'fill_partial':
        fsteps = list(zip(res.get('actions', []), res.get('rep_cells', [])))
    if fsteps:
        ok, g_tent = replay_steps(snap, steps + fsteps)
        if ok:
            if g_tent.is_solved():
                return steps + fsteps, 'fill'
            # 注意：solve_fill_macro 会**原地修改** g，不能用 g 当 before，
            # 必须从 snap 重放 steps 拿权威的 before 状态（与 exp12_chain 一致）
            _okb, g_before = replay_steps(snap, steps)
            before = H.gather_metrics(H.coords_of(g_before),
                                      g_before.m, g_before.n)['score']
            after = H.gather_metrics(H.coords_of(g_tent),
                                     g_tent.m, g_tent.n)['score']
            if after >= before:
                steps += fsteps
        _ok, g = replay_steps(snap, steps)

    # 段3：逐次单缺口 guided
    from experiments.exp11_guided import guided_reduce_one
    guard = 0
    while not g.is_solved() and guard < 12:
        guard += 1
        path, _used = guided_reduce_one(H.coords_of(g), snap['m'], snap['n'], step)
        if path is None:
            return None, 'guided_stuck'
        ok, g = replay_steps(snap, steps + path)
        if not ok:
            return None, 'guided_replay_bad'
        steps += path
    if g.is_solved():
        return steps, 'guided'
    return None, 'guided_guard'


def run(m, n, st, seeds, caps):
    table = {}
    for cap in caps:
        rows = []
        t0 = time.time()
        for seed in seeds:
            snap = H.gen_state(m, n, st, seed)
            t1 = time.perf_counter()
            try:
                res, who = solve_rep(snap, gather_cap=cap)
            except Exception as e:
                res, who = None, f'exc:{e!r}'
            dt = time.perf_counter() - t1
            ok = bool(res) and replay_steps(snap, res)[0]
            opt = optimal_distance(snap)
            rows.append({'ok': ok, 'len': len(res) if res else 0, 'opt': opt})
            tag = f"{len(res):>4}步" if ok else f"败({who})"
            ratio = f"{len(res)/opt:.1f}x" if (ok and opt) else '-'
            print(f"  cap={str(cap):>4} seed{seed} {tag} 最优={opt} {ratio} {dt:>5.1f}s")
        solved = [r for r in rows if r['ok']]
        with_opt = [r for r in solved if r['opt']]
        table[cap] = {
            'rate': 100 * len(solved) / len(rows),
            'median': median([r['len'] for r in solved]) if solved else 0,
            'ratio': median([r['len'] / r['opt'] for r in with_opt]) if with_opt else 0,
            't': time.time() - t0,
        }
        print(f"  → cap={cap}: 成功 {len(solved)}/{len(rows)} "
              f"步数中位 {table[cap]['median']} 倍数中位 {table[cap]['ratio']:.1f}x\n")

    print("=== 汇总（补 rep 后，4x4 step2 长解种子）===")
    print(f"{'cap':>6} {'成功率':>8} {'步数中位':>8} {'倍数中位':>8}")
    for cap in caps:
        t = table[cap]
        print(f"{str(cap):>6} {t['rate']:>7.0f}% {t['median']:>8} {t['ratio']:>7.1f}x")
    print("\n对照 exp14（未补 rep）：cap=None 100%/581步/83x；cap=15 40%/33步/4.7x")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--n', type=int, default=5)
    args = ap.parse_args()
    m, n, st = (int(x) for x in args.configs.split('x'))
    run(m, n, st, LONG_SEEDS[:args.n], CAPS)


if __name__ == '__main__':
    main()
