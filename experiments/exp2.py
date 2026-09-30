# -*- coding: utf-8 -*-
"""实验2：智能聚拢 + 填洞（+ 最后一公里搜索兜底）。

验证用户主张：gradient 聚拢后接填洞，能概率性解决整个打乱。
填洞失败/部分推进时，用 last_mile 有界搜索兜底，看成功率能提到多少。
"""
import argparse
import time

from experiments import harness as H


def chain_v2(snap, use_lms=True, lms_time=20.0):
    """gradient → 填洞 → (lms 兜底)。返回 (actions, solved, info)。"""
    from solver.ml.gather_solver import gradient_gather
    from solver.ml.fill_macro import solve_fill_macro, window_of
    from experiments.last_mile import last_mile_solve

    g = H.load_game(snap)
    step = snap['step']
    all_actions = []
    info = {'steps': []}

    # 1) 智能聚拢
    t0 = time.perf_counter()
    r = gradient_gather(g, step)
    info['gather_time'] = round(time.perf_counter() - t0, 2)
    info['gather_reason'] = r['reason']
    info['gather_score'] = round(
        H.gather_metrics(H.coords_of(g), g.m, g.n)['score'], 3)
    all_actions += list(r['actions'])
    if g.is_solved():
        info['solved_by'] = 'gather'
        return all_actions, True, info

    # 记录聚拢后的状态快照（LMS 候选起点）
    from solver.state import snapshot as snap_game
    from experiments.last_mile import last_mile_solve
    g_gather_snap = snap_game(g)
    g_gather_actions = len(all_actions)

    # 2) 填洞（快，人类可读）
    t0 = time.perf_counter()
    res = solve_fill_macro(g, step)
    info['fill_time'] = round(time.perf_counter() - t0, 2)
    f_actions = []
    if isinstance(res, dict):
        info['fill_type'] = res.get('type')
        info['fill_reason'] = res.get('reason')
        if res.get('type') == 'fill_partial':
            f_actions = list(res.get('actions', []))
    else:
        f_actions, _reps = res
        f_actions = list(f_actions)
        info['fill_type'] = 'full'
    for a in f_actions:
        H.apply_action(g, a, step)
    if g.is_solved():
        all_actions += f_actions
        info['solved_by'] = 'fill'
        return all_actions, True, info
    info['post_fill_score'] = round(
        H.gather_metrics(H.coords_of(g), g.m, g.n)['score'], 3)

    # 3) 最后一公里搜索兜底：从 聚拢后 与 填洞后 中更好的状态出发
    if use_lms:
        candidates = [('gather', g_gather_snap, g_gather_actions)]
        if info['post_fill_score'] >= info['gather_score']:
            candidates.append(('post_fill', snap_game(g), len(all_actions)))
        best = max(candidates, key=lambda x: _snap_score(x[1], g))
        _name, _snap, n_keep = best

        from solver.state import restore
        lm_game = H.load_game(snap)
        restore(lm_game, _snap)
        all_actions = all_actions[:n_keep]

        t0 = time.perf_counter()
        lm = last_mile_solve(lm_game, step, time_limit=lms_time)
        info['lms_time'] = round(time.perf_counter() - t0, 2)
        info['lms_from'] = _name
        if lm:
            for a in lm:
                H.apply_action(lm_game, a, step)
            all_actions += lm
            if lm_game.is_solved():
                info['solved_by'] = 'lms'
                return all_actions, True, info
        info['lms_fail'] = True

    return all_actions, g.is_solved(), info


def _snap_score(s, g):
    coords = frozenset(tuple(b) for b in s['blocks'])
    return H.gather_metrics(coords, g.m, g.n)['score']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=10)
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--no-lms', action='store_true')
    ap.add_argument('--lms-time', type=float, default=20.0)
    args = ap.parse_args()

    specs = []
    for s in args.configs.split(','):
        m, n, st = s.split('x')
        specs.append((int(m), int(n), int(st)))

    corpus = H.build_corpus(specs, args.n)
    solved_cnt = 0
    steps_list, time_list = [], []
    fails = []
    t_all = time.perf_counter()

    for snap in corpus:
        t0 = time.perf_counter()
        actions, solved, info = chain_v2(snap, use_lms=not args.no_lms,
                                         lms_time=args.lms_time)
        dt = time.perf_counter() - t0
        verified, _ = H.replay(snap, actions)
        mark = '解' if verified else '败'
        if verified:
            solved_cnt += 1
            steps_list.append(len(actions))
            time_list.append(dt)
        else:
            fails.append((snap['seed'], info, len(actions)))
        print(f"  seed={snap['seed']} {mark} {len(actions):>4}步 "
              f"{dt:>6.1f}s by={info.get('solved_by','-')} "
              f"g={info.get('gather_score')} "
              f"gR={info.get('gather_reason')} "
              f"f={info.get('fill_type','-')}/{info.get('fill_reason','-')} "
              f"lms={info.get('lms_time','-')}s")

    print(f"\n成功率: {solved_cnt}/{len(corpus)}  ({100*solved_cnt/len(corpus):.0f}%)")
    if steps_list:
        s = sorted(steps_list)
        t = sorted(time_list)
        print(f"步数 中位={s[len(s)//2]} 最少={s[0]} 最多={s[-1]}；"
              f"耗时中位={t[len(t)//2]:.1f}s 总耗时={time.perf_counter()-t_all:.0f}s")
    if fails:
        print(f"\n失败 {len(fails)} 例：")
        for seed, info, n in fails:
            print(f"  seed={seed} 步={n} gather={info.get('gather_score')} "
                  f"reason={info.get('gather_reason')} "
                  f"fill={info.get('fill_type')}/{info.get('fill_reason')} "
                  f"post_fill={info.get('post_fill_score')} "
                  f"lms_fail={info.get('lms_fail')}")


if __name__ == '__main__':
    main()
