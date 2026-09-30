# -*- coding: utf-8 -*-
"""实验12：完整尺寸无关混合链
  梯度聚拢 → 填洞宏(rep) → 定向GBFS最后一公里
全程 (action, rep) 统一、每段重放锚定、最终重放验证。无距离表。
"""
import argparse
import time

from experiments import harness as H
from experiments.exp9_rep import replay_steps
from experiments.exp11_guided import guided_solve


def score_of(g):
    return H.gather_metrics(H.coords_of(g), g.m, g.n)['score']


def solve(snap, use_fill=True, use_guided=True, budget=300000):
    from solver.ml.gather_solver import gradient_gather
    from solver.ml.fill_macro import solve_fill_macro

    step = snap['step']
    steps = []

    # 段1：梯度聚拢
    g = H.load_game(snap)
    r = gradient_gather(g, step)
    steps += [(a, None) for a in r['actions']]
    _ok, g = replay_steps(snap, steps)
    if g.is_solved():
        return steps, 'gather'

    # 段2：填洞（rep 感知），仅当不降低聚拢度
    if use_fill:
        res = solve_fill_macro(g, step)
        fsteps = []
        if isinstance(res, tuple):
            fsteps = list(zip(res[0], res[1]))
        elif isinstance(res, dict) and res.get('type') == 'fill_partial':
            f, fr = res.get('actions', []), res.get('rep_cells', [])
            fsteps = list(zip(f, fr))
        _okb, g_tent = replay_steps(snap, steps + fsteps)
        before = score_of(replay_steps(snap, steps)[1])
        after = score_of(g_tent)
        if g_tent.is_solved():
            return steps + fsteps, 'fill'
        if after >= before:
            steps += fsteps
        _ok, g = replay_steps(snap, steps)

    # 段3：逐次单缺口 guided 消解（处理多缺口，每段都很小）
    if use_guided:
        from experiments.exp11_guided import guided_reduce_one
        guard = 0
        while not g.is_solved() and guard < 12:
            guard += 1
            path, used = guided_reduce_one(H.coords_of(g), snap['m'],
                                           snap['n'], step)
            if path is None:
                return None, f'guided_stuck_nodes{used}'
            ok, g = replay_steps(snap, steps + path)
            if not ok:
                return None, 'guided_replay_bad'
            steps += path
        if g.is_solved():
            return steps, 'guided'
        return None, 'guided_guard'
    return None, 'no_guided'


def run_config(m, n, st, count, budget):
    snaps = H.build_corpus([(m, n, st)], count)
    solved, by = 0, {}
    sc, tc = [], []
    fails = []
    t0 = time.time()
    for snap in snaps:
        t1 = time.perf_counter()
        try:
            res, who = solve(snap, budget=budget)
        except Exception as e:
            res, who = None, f'exc:{e!r}'
        dt = time.perf_counter() - t1
        ok = bool(res) and replay_steps(snap, res)[0]
        if ok:
            solved += 1
            by[who] = by.get(who, 0) + 1
            sc.append(len(res))
            tc.append(dt)
        else:
            fails.append((snap['seed'], who))
        print(f"  seed{snap['seed']} {'解' if ok else '败'} "
              f"{len(res) if res else 0:>4}步 {dt:>6.1f}s {who}")
    rate = 100 * solved / len(snaps)
    print(f"[{m}x{n} step{st}] {solved}/{len(snaps)} ({rate:.0f}%) {by} "
          f"{time.time()-t0:.0f}s")
    if sc:
        s, t = sorted(sc), sorted(tc)
        print(f"   步数中位={s[len(s)//2]} 区间{s[0]}-{s[-1]}; "
              f"耗时中位={t[len(t)//2]:.1f}s")
    if fails:
        print(f"   失败 {fails}")
    return rate, fails


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
