# -*- coding: utf-8 -*-
"""实验20：填洞宏的效率剖面 + 「填洞 + 聚拢」多段交替链

背景（用户 2026-09-30 提出）：
  手动测试发现「打乱后直接开始用填洞宏，有时能快速提高聚拢度」——
  这不是设计填洞宏时考虑过的用途，而是算法自动涌现出来的行为。
  用户主张：当前最优混合算法应是**多段「填洞 + 聚拢」交替，直到无法改进**。

本实验两部分：
  A 效率剖面：把「填洞宏」与「聚拢」放在同一把尺子上量——
    各花多少毫秒、多少步，换来多少聚拢度提升。得到可比的效率数字。
  B 交替链对照：完整求解，比较 基线 / 交替(先填) / 交替(先聚) / 只填洞。

指标口径：**时间为主**（用户 2026-09-30 定：运算时间比步数更重要）。
"""
import argparse
import io
import time
from contextlib import redirect_stdout

from experiments import harness as H
from experiments.exp9_rep import replay_valid
from experiments.exp12_chain import solve as chain_solve

EPS = 1e-9


def score_of(g):
    return H.gather_metrics(H.coords_of(g), g.m, g.n)['score']


def _quiet(fn, *a, **kw):
    """静音执行（填洞宏会往 stdout 打大量过程日志）。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        return fn(*a, **kw)


def _fill_steps(g, step):
    """填洞宏 → [(action, rep), ...]；无成果返回 []。"""
    from solver.ml.fill_macro import solve_fill_macro
    res = _quiet(solve_fill_macro, g, step)
    if isinstance(res, tuple):
        return list(zip(res[0], res[1]))
    if isinstance(res, dict) and res.get('type') == 'fill_partial':
        return list(zip(res.get('actions', []), res.get('rep_cells', [])))
    return []


def _gather_steps(g, step, chunk):
    """聚拢一小段（增量）→ [(action, rep), ...]。"""
    from solver.ml.gather_solver import gather_solve
    r = gather_solve(g, step, max_steps=chunk,
                     patience=max(30, chunk), max_wait_time=20)
    acts = r['actions']
    reps = r.get('rep_cells') or [None] * len(acts)
    return list(zip(acts, reps)), r.get('solved', False)


def _guided_tail(snap, steps, g):
    """段3：逐次单缺口 guided 消解。返回 (steps, ok, tag)。"""
    from experiments.exp11_guided import guided_reduce_one
    step = snap['step']
    guard = 0
    while not g.is_solved() and guard < 12:
        guard += 1
        path, used = guided_reduce_one(H.coords_of(g), snap['m'],
                                       snap['n'], step)
        if path is None:
            return steps, False, f'guided_stuck_nodes{used}'
        ok, g2 = replay_valid(snap, steps + path)
        if not ok:
            return steps, False, 'guided_replay_bad'
        g = g2
        steps = steps + path
    return steps, g.is_solved(), 'guided'


# ---------------------------------------------------------------------------
# A 部分：效率剖面
# ---------------------------------------------------------------------------

def profile_units(m, n, step, seeds, chunk=30):
    """在初始局面上分别单发「填洞宏 / 小段聚拢 / 全程梯度聚拢」，比较效率。"""
    from solver.ml.gather_solver import gradient_gather

    print(f"\n=== A 效率剖面：{m}x{n} step{step}，初始局面单发 ===")
    print(f"{'seed':>6} {'初score':>8} | {'填洞:步':>7}{'秒':>7}{'Δscore':>8} "
          f"| {'聚拢%d:步' % chunk:>9}{'秒':>7}{'Δscore':>8} "
          f"| {'全程:步':>8}{'秒':>7}{'Δscore':>8}")
    print("-" * 96)

    acc = {'fill': [], 'chunk': [], 'full': []}
    for seed in seeds:
        snap = H.gen_state(m, n, step, seed)
        row = []

        def measure(kind, runner):
            g = H.load_game(snap)
            s0 = score_of(g)
            t = time.perf_counter()
            steps, solved = runner(g)
            dt = time.perf_counter() - t
            ok, g2 = replay_valid(snap, steps)
            s1 = score_of(g2) if ok else s0
            acc[kind].append((len(steps), dt, s1 - s0, dt * 1000, s1 - s0))
            row.append((len(steps), dt, s1 - s0))
            return steps, solved

        measure('fill', lambda g: (_fill_steps(g, step), False))

        def _chunk(g, step=step, chunk=chunk):
            st, sl = _gather_steps(g, step, chunk)
            return st, sl
        measure('chunk', _chunk)

        def _full(g, step=step):
            r = gradient_gather(g, step)
            return [(a, None) for a in r['actions']], r.get('solved', False)
        measure('full', _full)

        f, c, u = row
        print(f"{seed:>6} {score_of(H.load_game(snap)):>8.3f} | "
              f"{f[0]:>7}{f[1]:>7.2f}{f[2]:>+8.3f} | "
              f"{c[0]:>9}{c[1]:>7.2f}{c[2]:>+8.3f} | "
              f"{u[0]:>8}{u[1]:>7.2f}{u[2]:>+8.3f}", flush=True)

    print("\n汇总（中位）：")
    print(f"{'手段':<18}{'步数':>8}{'耗时':>9}{'Δscore':>9}{'ms/步':>9}"
          f"{'ms per +0.1 score':>19}")
    print("-" * 72)
    names = {'fill': '填洞宏(单发)', 'chunk': f'聚拢{chunk}步(单发)',
             'full': '全程梯度聚拢'}
    for kind in ('fill', 'chunk', 'full'):
        xs = acc[kind]
        if not xs:
            continue
        st = sorted(x[0] for x in xs)
        dt = sorted(x[1] for x in xs)
        ds = sorted(x[2] for x in xs)
        ms = dt[len(dt) // 2] * 1000
        per_step = ms / st[len(st) // 2] if st[len(st) // 2] else float('nan')
        per_score = (ms / (ds[len(ds) // 2] * 10)
                     if abs(ds[len(ds) // 2]) > EPS else float('nan'))
        print(f"{names[kind]:<18}{st[len(st)//2]:>8}{dt[len(dt)//2]:>9.2f}s"
              f"{ds[len(ds)//2]:>+9.3f}{per_step:>9.1f}{per_score:>19.0f}")
    print("\n读法：ms per +0.1 score = 「把聚拢度抬高 0.1 要花多少毫秒」，越小越划算。")


# ---------------------------------------------------------------------------
# B 部分：交替链
# ---------------------------------------------------------------------------

def solve_alt(snap, chunk=30, max_rounds=8, order='fill_first',
              use_guided=True, skip_gather=False, skip_fill=False):
    """多段「填洞 + 聚拢」交替，直到无法改进，再交给 guided 收尾。

    skip_gather / skip_fill 用于消融：隔离出「填洞」到底贡献了多少。
    """
    step = snap['step']
    steps = []
    n_fill = n_gather = 0
    rounds = 0

    while rounds < max_rounds:
        rounds += 1
        improved = False

        ops = (('fill', 'gather') if order == 'fill_first'
               else ('gather', 'fill'))
        for op in ops:
            if op == 'gather' and skip_gather:
                continue
            if op == 'fill' and skip_fill:
                continue
            base = replay_valid(snap, steps)[1]
            before = score_of(base)

            if op == 'fill':
                cand = _fill_steps(base, step)
            else:
                cand, _sl = _gather_steps(base, step, chunk)

            if not cand:
                continue
            ok, g_tent = replay_valid(snap, steps + cand)
            if not ok:
                continue
            if g_tent.is_solved():
                steps += cand
                n_fill += len(cand) if op == 'fill' else 0
                n_gather += len(cand) if op == 'gather' else 0
                return steps, f'alt_{op}'
            if score_of(g_tent) > before + EPS:
                steps += cand
                if op == 'fill':
                    n_fill += len(cand)
                else:
                    n_gather += len(cand)
                improved = True

        if not improved:
            break

    g = replay_valid(snap, steps)[1]
    if g.is_solved():
        return steps, 'alt_macro'

    if use_guided:
        steps, ok, tag = _guided_tail(snap, steps, g)
        if ok:
            return steps, f'alt+{tag}'
        return None, f'alt_fail_{tag}'
    return None, 'alt_no_guided'


def solve_fill_only(snap, max_rounds=8):
    """只反复用填洞宏（不聚拢），直到无法改进，再 guided 收尾。"""
    return solve_alt(snap, chunk=30, max_rounds=max_rounds,
                     order='fill_first', skip_gather=True)


def run_chain(m, n, step, seeds, chunk=30, max_rounds=8):
    configs = [
        ('base 基线(全程聚拢)',
         lambda s: chain_solve(s, gather_cap=None)),
        ('alt 先填后聚(交替)',
         lambda s: solve_alt(s, chunk=chunk, max_rounds=max_rounds,
                             order='fill_first')),
        ('alt 先聚后填(交替)',
         lambda s: solve_alt(s, chunk=chunk, max_rounds=max_rounds,
                             order='gather_first')),
        ('alt 只小段聚拢(消融)',
         lambda s: solve_alt(s, chunk=chunk, max_rounds=max_rounds,
                             order='gather_first', skip_fill=True)),
        ('fill 只填洞宏(消融)',
         lambda s: solve_fill_only(s, max_rounds=max_rounds)),
    ]
    print(f"\n=== B 交替链对照：{m}x{n} step{step}，{len(seeds)} seed "
          f"(chunk={chunk}, max_rounds={max_rounds}) ===")
    print(f"{'配置':<20}{'成功':>7}{'步数中位':>10}{'耗时中位':>10}"
          f"{'总耗时':>9}  失败")
    print("-" * 74)
    for label, fn in configs:
        lens, secs, fails, ok_n = [], [], [], 0
        t0 = time.time()
        for seed in seeds:
            snap = H.gen_state(m, n, step, seed)
            t1 = time.perf_counter()
            try:
                res, who = fn(snap)
            except Exception as exc:  # noqa: BLE001
                res, who = None, f'exc:{exc!r}'
            dt = time.perf_counter() - t1
            ok = False
            if res:
                _v, gv = replay_valid(snap, res)
                ok = _v and gv.is_solved()
            if ok:
                ok_n += 1
                lens.append(len(res))
            else:
                fails.append((seed, who))
            secs.append(dt)
        med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0  # noqa: E731
        print(f"{label:<20}{ok_n:>4}/{len(seeds):<2}{med(lens):>10}"
              f"{med(secs):>9.1f}s{time.time()-t0:>8.0f}s  "
              f"{fails if fails else ''}", flush=True)
    print("\n读法：先看「成功」，再看「耗时中位」（时间为主指标），最后看步数。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--seeds', type=int, default=5)
    ap.add_argument('--seed0', type=int, default=1000)
    ap.add_argument('--chunk', type=int, default=30)
    ap.add_argument('--rounds', type=int, default=8)
    ap.add_argument('--part', default='both', choices=['a', 'b', 'both'])
    args = ap.parse_args()

    m, n, st = (int(x) for x in args.configs.split('x'))
    seeds = list(range(args.seed0, args.seed0 + args.seeds))
    if args.part in ('a', 'both'):
        profile_units(m, n, st, seeds, chunk=args.chunk)
    if args.part in ('b', 'both'):
        run_chain(m, n, st, seeds, chunk=args.chunk, max_rounds=args.rounds)


if __name__ == '__main__':
    main()
