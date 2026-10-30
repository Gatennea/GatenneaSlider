# -*- coding: utf-8 -*-
"""实验6：智能聚拢 → 填洞 → 限深查表（混合链）。

梯度聚拢粗调；填洞宏尝试人类可读收尾；未解决则从更好的状态用限深
距离表（table_solve）拿最短最后一公里。全链路重放验证。
"""
import argparse
import time

from experiments import harness as H
from solver.state import snapshot, restore


def score_game(g):
    return H.gather_metrics(H.coords_of(g), g.m, g.n)['score']


def hybrid_solve(snap, use_fill=True, use_table=True):
    from solver.ml.gather_solver import gradient_gather
    from solver.ml.fill_macro import solve_fill_macro
    from solver.table_solver import table_solve

    g = H.load_game(snap)
    step = snap['step']

    # 1) 梯度聚拢
    r = gradient_gather(g, step)
    base = list(r['actions'])
    if g.is_solved():
        return base, 'gather'
    gathered = snapshot(g)
    s_gathered = score_game(g)

    f_actions = []
    if use_fill:
        res = solve_fill_macro(g, step)
        if isinstance(res, tuple):
            f_actions = list(res[0])
        elif isinstance(res, dict) and res.get('type') == 'fill_partial':
            f_actions = list(res.get('actions', []))
        # 统一从聚拢态重放填洞动作，保证可复现
        restore(g, gathered)
        for a in f_actions:
            H.apply_action(g, a, step)
        if g.is_solved():
            return base + f_actions, 'fill'
        # 填洞有害则回滚
        if score_game(g) < s_gathered:
            restore(g, gathered)
            f_actions = []

    # 2) 限深查表收尾
    if use_table:
        r2 = table_solve(g, step)
        if isinstance(r2, tuple):
            tpath, _reps = r2
            return base + f_actions + list(tpath), 'table'
        return None, f'table_{r2}'

    return None, 'no_table'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=20)
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--mode', default='hybrid',
                    choices=['hybrid', 'table', 'fill'])
    args = ap.parse_args()

    specs = []
    for s in args.configs.split(','):
        m, n, st = s.split('x')
        specs.append((int(m), int(n), int(st)))

    corpus = H.build_corpus(specs, args.n)
    use_fill = args.mode in ('hybrid', 'fill')
    use_table = args.mode in ('hybrid', 'table')

    solved = 0
    steps_list, time_list = [], []
    by = {}
    fails = []
    t_all = time.perf_counter()
    for snap in corpus:
        t0 = time.perf_counter()
        try:
            actions, who = hybrid_solve(snap, use_fill, use_table)
        except Exception as e:
            actions, who = None, f'exc:{e!r}'
        dt = time.perf_counter() - t0
        ok = False
        if actions:
            ok, _ = H.replay(snap, actions)
        if ok:
            solved += 1
            steps_list.append(len(actions))
            time_list.append(dt)
            by[who] = by.get(who, 0) + 1
        else:
            fails.append((snap['seed'], who))
        print(f"  seed={snap['seed']} {'解' if ok else '败'} "
              f"{len(actions) if actions else 0:>4}步 {dt:>6.1f}s by={who}")

    print(f"\n成功率: {solved}/{len(corpus)} ({100*solved/len(corpus):.0f}%)  "
          f"总耗时={time.perf_counter()-t_all:.0f}s")
    print(f"收尾方式分布: {by}")
    if steps_list:
        s = sorted(steps_list)
        t = sorted(time_list)
        print(f"步数 中位={s[len(s)//2]} 最少={s[0]} 最多={s[-1]}；"
              f"耗时中位={t[len(t)//2]:.1f}s")
    if fails:
        print(f"失败: {fails}")


if __name__ == '__main__':
    main()
