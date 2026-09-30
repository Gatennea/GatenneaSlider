# -*- coding: utf-8 -*-
"""实验1：聚拢 → 填洞 串联。

假设：gather 把局面带到 0.9 左右（只剩 1~2 个洞），单洞共轭宏能收掉
最后一公里。现有代码两者是分开的，这里把它们链成一个求解器并验证。
"""
import argparse
import time

from experiments import harness as H


def window_holes(g, step):
    """返回当前局面的 (洞集合, 凸起集合)。"""
    from solver.ml.fill_macro import window_of
    coords = H.coords_of(g)
    _region, _ov, holes, outside = window_of(coords, g.m, g.n, step)
    return holes, outside


def probe(snap):
    """聚拢后看洞数，并尝试单洞宏。"""
    from solver.ml.gather_solver import gather_solve
    from solver.ml.fill_macro import solve_single_void
    g = H.load_game(snap)
    r = gather_solve(g, snap['step'])
    holes, outside = window_holes(g, snap['step'])
    print(f"  seed={snap['seed']} 聚拢后 洞={len(holes)} 凸起={len(outside)} "
          f"solved={g.is_solved()} reason={r['reason']}")
    if len(holes) == 1 and len(outside) == 1:
        coords = H.coords_of(g)
        acts, stats = solve_single_void(coords, g.m, g.n, snap['step'])
        print(f"      单洞宏: {'成功' if acts is not None else '失败'} "
              f"{len(acts) if acts else 0}步 {stats if acts is None else ''}")
        return acts is not None
    return g.is_solved()


def chain_solve(snap, max_rounds=6, gather_gradient=False):
    """聚拢 → 填洞，多轮交替直到复原或无法推进。

    返回 (all_actions, solved, info)。
    """
    from solver.ml.gather_solver import gather_solve, gradient_gather
    from solver.ml.fill_macro import solve_fill_macro

    g = H.load_game(snap)
    step = snap['step']
    all_actions = []
    info = {'rounds': []}

    for rnd in range(max_rounds):
        if g.is_solved():
            break

        # 1) 聚拢（粗调）
        t0 = time.perf_counter()
        if gather_gradient:
            r = gradient_gather(g, step)
        else:
            r = gather_solve(g, step)
        all_actions += list(r['actions'])
        gtime = time.perf_counter() - t0
        if g.is_solved():
            info['rounds'].append(('gather', len(r['actions']), gtime))
            break

        # 2) 填洞（收尾）
        holes_before = len(window_holes(g, step)[0])
        res = solve_fill_macro(g, step)
        f_actions = []
        if isinstance(res, dict):
            if res.get('type') == 'fill_partial':
                f_actions = list(res.get('actions', []))
            else:
                # fill_fail：无法再推进
                info['rounds'].append(('fill_fail', res.get('reason'), gtime))
                break
        else:
            f_actions, _reps = res
            f_actions = list(f_actions)
        for a in f_actions:
            H.apply_action(g, a, step)
        all_actions += f_actions
        info['rounds'].append(
            ('round', holes_before, len(f_actions), round(gtime, 2)))

        # 填洞没有任何动作且聚拢也无改进 → 防止空转
        if not f_actions and not r['actions']:
            break

    return all_actions, g.is_solved(), info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=6)
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--gradient', action='store_true')
    args = ap.parse_args()

    specs = []
    for s in args.configs.split(','):
        m, n, st = s.split('x')
        specs.append((int(m), int(n), int(st)))

    corpus = H.build_corpus(specs, args.n)
    print(f'== 探针（单洞可行性）==')
    ok_cnt = 0
    for snap in corpus:
        if probe(snap):
            ok_cnt += 1
    print(f'单洞可收: {ok_cnt}/{len(corpus)}\n')

    print(f'== 串联求解 ==')
    solved_cnt = 0
    steps_list, time_list = [], []
    for snap in corpus:
        t0 = time.perf_counter()
        actions, solved, info = chain_solve(snap, gather_gradient=args.gradient)
        dt = time.perf_counter() - t0
        # 全链路重放验证
        verified, _ = H.replay(snap, actions)
        mark = '解' if verified else '败'
        if verified:
            solved_cnt += 1
            steps_list.append(len(actions))
            time_list.append(dt)
        print(f'  seed={snap["seed"]} {mark} {len(actions):>4}步 '
              f'{dt:>6.2f}s rounds={info["rounds"]}')

    print(f'\n串联成功率: {solved_cnt}/{len(corpus)}')
    if steps_list:
        s = sorted(steps_list)
        t = sorted(time_list)
        print(f'步数 中位={s[len(s)//2]} 最少={s[0]} 最多={s[-1]}；'
              f'耗时中位={t[len(t)//2]:.2f}s')


if __name__ == '__main__':
    main()
