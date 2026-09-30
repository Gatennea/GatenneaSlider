# -*- coding: utf-8 -*-
"""实验8：重放锚定混合链（修复坐标系帧错位）。

原则：每一段产出动作后，都在"从起点重放全部动作得到的新游戏"上启动
下一段，保证下游动作始终在上游动作真正产生的那一帧里计算。
最后再做一次全链路重放验证。
"""
import argparse
import time

from experiments import harness as H


def replay_to_game(snap, actions):
    """从起点装载并应用动作，返回该游戏（不要求复原）。"""
    g = H.load_game(snap)
    for a in actions:
        H.apply_action(g, a, snap['step'])
    return g


def score_of(g):
    return H.gather_metrics(H.coords_of(g), g.m, g.n)['score']


def anchored_solve(snap, use_fill=True, use_table=True):
    from solver.ml.gather_solver import gradient_gather
    from solver.ml.fill_macro import solve_fill_macro
    from solver.table_solver import table_solve

    step = snap['step']
    actions = []

    # 段1：梯度聚拢
    g = H.load_game(snap)
    r = gradient_gather(g, step)
    actions += list(r['actions'])
    g = replay_to_game(snap, actions)          # 重放锚定
    if g.is_solved():
        return actions, 'gather'

    # 段2：填洞（在锚定游戏上）
    if use_fill:
        res = solve_fill_macro(g, step)
        f = []
        if isinstance(res, tuple):
            f = list(res[0])
        elif isinstance(res, dict) and res.get('type') == 'fill_partial':
            f = list(res.get('actions', []))
        # 在又一次锚定的副本上试 f，只有不降低聚拢度才采纳
        g_tent = replay_to_game(snap, actions)
        before = score_of(g_tent)
        for a in f:
            H.apply_action(g_tent, a, step)
        if g_tent.is_solved():
            actions += f
            return actions, 'fill'
        if score_of(g_tent) >= before:
            actions += f
        g = replay_to_game(snap, actions)      # 重放锚定

    # 段3：查表（在锚定游戏上）
    if use_table:
        r2 = table_solve(g, step)
        if isinstance(r2, tuple):
            tpath = list(r2[0])
            # 在锚定副本上验证 tpath 真正复原
            g_v = replay_to_game(snap, actions)
            for a in tpath:
                H.apply_action(g_v, a, step)
            if g_v.is_solved():
                actions += tpath
                return actions, 'table'
        return None, f'table_{r2}'

    return None, 'no_table'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=20)
    ap.add_argument('--seeds', default=None)
    ap.add_argument('--configs', default='4x4x2')
    args = ap.parse_args()

    m, n, st = args.configs.split('x')
    m, n, st = int(m), int(n), int(st)
    if args.seeds:
        snaps = [H.gen_state(m, n, st, int(s)) for s in args.seeds.split(',')]
    else:
        snaps = H.build_corpus([(m, n, st)], args.n)

    solved, by = 0, {}
    steps_list, time_list = [], []
    fails = []
    t_all = time.time()
    for snap in snaps:
        t0 = time.perf_counter()
        try:
            actions, who = anchored_solve(snap)
        except Exception as e:
            actions, who = None, f'exc:{e!r}'
        dt = time.perf_counter() - t0
        ok = False
        if actions:
            ok, _ = H.replay(snap, actions)
        if ok:
            solved += 1
            by[who] = by.get(who, 0) + 1
            steps_list.append(len(actions))
            time_list.append(dt)
        else:
            fails.append((snap['seed'], who, len(actions) if actions else 0))
        print(f"  seed={snap['seed']} {'解' if ok else '败'} "
              f"{len(actions) if actions else 0:>4}步 {dt:>6.1f}s by={who}")

    print(f"\n成功率 {solved}/{len(snaps)} ({100*solved/len(snaps):.0f}%) "
          f"收尾分布 {by} 总耗时 {time.time()-t_all:.0f}s")
    if steps_list:
        s = sorted(steps_list)
        t = sorted(time_list)
        print(f"步数 中位={s[len(s)//2]} 最少={s[0]} 最多={s[-1]}；"
              f"耗时中位={t[len(t)//2]:.1f}s")
    if fails:
        print(f"失败 {fails}")


if __name__ == '__main__':
    main()
