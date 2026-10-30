# -*- coding: utf-8 -*-
"""实验9：携带分量代表格(rep_cell)的重放锚定混合链。

统一返回 steps = [(action, rep_or_None), ...]：
- 聚拢/填洞动作 rep=None，用 apply_action（与它们内部执行方式一致）；
- 查表动作 rep=该步所选分量的代表格，用 rep 锁定分量再 opt/move/commit，
  解决"同一侧多分量、4元组无法区分"的问题。
最终全链路重放验证。
"""
import argparse
import time

from experiments import harness as H


def replay_steps(snap, steps):
    """按 (action, rep) 统一重放，返回 (是否复原, game)。"""
    g = H.load_game(snap)
    for action, rep in steps:
        if rep is None:
            ok = H.apply_action(g, action, snap['step'])
        else:
            ok = _apply_with_rep(g, action, snap['step'], rep)
        if not ok:
            return False, g
    return g.is_solved(), g


def replay_valid(snap, steps):
    """按 (action, rep) 重放，返回 (每一步是否都合法, game)。

    与 replay_steps 的区别（重要）：
    - replay_steps 的首返回值是 g.is_solved()，语义是「是否已复原」；
    - 本函数的首返回值语义是「重放过程有没有非法步」。

    段内推进用「是否复原」当「重放是否成功」会误判：填洞宏 / guided 每次
    只保证缺口数减少，不保证一次复原，于是合法的中间态被当成失败。
    需要判断「这段能不能接受」时用本函数；只有最终验收才用 replay_steps。
    """
    g = H.load_game(snap)
    for action, rep in steps:
        if rep is None:
            ok = H.apply_action(g, action, snap['step'])
        else:
            ok = _apply_with_rep(g, action, snap['step'], rep)
        if not ok:
            return False, g
    return True, g


def _apply_with_rep(game, action, step, rep_cell):
    """选中包含 rep_cell 的那个连通分量并执行 action。"""
    from solver.table_core import _side_components, is_single_connected
    gap_type, gap_line, side, move_dir = action
    cur = frozenset((b.location[0], b.location[1]) for b in game.blocks)
    comps = _side_components(cur, gap_type, gap_line, side)
    chosen = next((c for c in comps if rep_cell in c), None)
    if chosen is None:
        return False
    rep_block = next((b for b in game.blocks
                      if (b.location[0], b.location[1]) == rep_cell), None)
    if rep_block is None:
        return False
    for b in game.blocks:
        b.be_opted = False
    game.opt(gap_type, gap_line, rep_block)
    final = game.try_move(move_dir, step)
    if not final:
        for b in game.blocks:
            b.be_opted = False
        return False
    test = []
    selected = [b for b in game.blocks if b.be_opted]
    for b in game.blocks:
        if b.be_opted:
            test.append(tuple(final[selected.index(b)]))
        else:
            test.append(tuple(b.location))
    if len(test) != len(game.blocks) or not is_single_connected(test):
        for b in game.blocks:
            b.be_opted = False
        return False
    game.commit_move(final)
    for b in game.blocks:
        b.be_opted = False
    return True


def replay_to_game(snap, steps):
    _ok, g = replay_steps(snap, steps)
    return g


def score_of(g):
    return H.gather_metrics(H.coords_of(g), g.m, g.n)['score']


def solve(snap, use_fill=True, use_table=True):
    from solver.ml.gather_solver import gradient_gather
    from solver.ml.fill_macro import solve_fill_macro
    from solver.table_solver import table_solve

    step = snap['step']
    steps = []

    # 段1：梯度聚拢
    g = H.load_game(snap)
    r = gradient_gather(g, step)
    steps += [(a, None) for a in r['actions']]
    g = replay_to_game(snap, steps)
    if g.is_solved():
        return steps, 'gather'

    # 段2：填洞（同样携带 rep_cell）
    if use_fill:
        res = solve_fill_macro(g, step)
        fsteps = []
        if isinstance(res, tuple):
            f, freps = list(res[0]), list(res[1])
            fsteps = [(a, rep) for a, rep in zip(f, freps)]
        elif isinstance(res, dict) and res.get('type') == 'fill_partial':
            f = list(res.get('actions', []))
            freps = list(res.get('rep_cells', [None] * len(f)))
            fsteps = [(a, rep) for a, rep in zip(f, freps)]

        _ok, g_tent = replay_steps(snap, steps + fsteps)
        before = score_of(replay_to_game(snap, steps))
        after = score_of(g_tent)
        if g_tent.is_solved():
            steps += fsteps
            return steps, 'fill'
        if after >= before:
            steps += fsteps
        g = replay_to_game(snap, steps)

    # 段3：查表（携带 rep_cell）
    if use_table:
        r2 = table_solve(g, step)
        if isinstance(r2, tuple):
            tpath, treps = r2
            new = [(a, rep) for a, rep in zip(list(tpath), list(treps))]
            ok, _g = replay_steps(snap, steps + new)
            if ok:
                return steps + new, 'table'
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
    steps_count, times = [], []
    fails = []
    t_all = time.time()
    for snap in snaps:
        t0 = time.perf_counter()
        try:
            res, who = solve(snap)
        except Exception as e:
            res, who = None, f'exc:{e!r}'
        dt = time.perf_counter() - t0
        ok = False
        if res:
            ok, _ = replay_steps(snap, res)
        if ok:
            solved += 1
            by[who] = by.get(who, 0) + 1
            steps_count.append(len(res))
            times.append(dt)
        else:
            fails.append((snap['seed'], who, len(res) if res else 0))
        print(f"  seed={snap['seed']} {'解' if ok else '败'} "
              f"{len(res) if res else 0:>4}步 {dt:>6.1f}s by={who}")

    print(f"\n成功率 {solved}/{len(snaps)} ({100*solved/len(snaps):.0f}%) "
          f"收尾 {by} 总耗时 {time.time()-t_all:.0f}s")
    if steps_count:
        s = sorted(steps_count)
        t = sorted(times)
        print(f"步数 中位={s[len(s)//2]} 最少={s[0]} 最多={s[-1]}；"
              f"耗时中位={t[len(t)//2]:.1f}s")
    if fails:
        print(f"失败 {fails}")


if __name__ == '__main__':
    main()
