# -*- coding: utf-8 -*-
"""实验16：定位「早交接（gather_cap）后 guided_replay_bad」的真正根因。

不修复任何代码，只做观测。核心观测三点：

  1. 段3 每一轮 guided_reduce_one 给出的 path，**逐步重放时到底有没有非法步**；
     —— 若「全部合法、只是没还原」，则 exp12 的 `if not ok: return
        'guided_replay_bad'` 判据本身有问题（replay_steps 返回的是 is_solved()）。
  2. 「搜索内部推进的局面序列」与「重放推进的局面序列」逐位比对，找第一个分叉点；
     —— 分叉点存在 ⇒ 两条路径不等价 ⇒ (a) 重放/编码错位；
        第一位就不同 ⇒ (b) path 本身不可执行。
  3. 段1/段2 是否也存在「带 rep / 不带 rep」两条路径不等价。

用法：
    D:/python/python.exe -m experiments.exp16_diag --seeds 1001,1008 --caps 15
"""
import argparse
import os
import time

from experiments import harness as H
from experiments.exp9_rep import _apply_with_rep
from experiments.exp11_guided import guided_reduce_one, fast_window
from experiments.exp14_truncate import LONG_SEEDS

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
LOG_PATH = os.path.join(LOG_DIR, 'exp16_diag.log')


def log(msg=''):
    print(msg, flush=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(str(msg) + '\n')


def render(coords, m, n):
    """把局面画成小图，便于人眼比对差异。"""
    if coords is None:
        return '(none)'
    B = set(coords)
    rs = [r for r, _ in B]
    cs = [c for _, c in B]
    out = []
    for r in range(min(rs), max(rs) + 1):
        out.append(''.join('#' if (r, c) in B else '.' for c in
                           range(min(cs), max(cs) + 1)))
    return '\n      |' + '\n      |'.join(out)


def apply_all(snap, steps, use_rep=True):
    """逐步重放，返回 (全部合法?, game, 局面轨迹, 失败详情)。

    use_rep=True 时 rep 非 None 走 _apply_with_rep（分量消歧），
    use_rep=False 时一律走 apply_action（恒取 side_blocks[0]）。
    """
    g = H.load_game(snap)
    trace = []
    for i, (action, rep) in enumerate(steps):
        if use_rep and rep is not None:
            ok = _apply_with_rep(g, action, snap['step'], rep)
        else:
            ok = H.apply_action(g, action, snap['step'])
        if not ok:
            return (False, g, trace,
                    {'idx': i, 'action': action, 'rep': rep,
                     'before': render(H.coords_of(g), snap['m'], snap['n'])})
        trace.append(H.coords_of(g))
    return True, g, trace, None


def search_progression(start_coords, path, step):
    """纯坐标侧：用搜索自己的 expand 把 path 推进一遍，得到局面序列。

    返回 (序列, 出错信息)。出错信息非 None 表示 path 在搜索语义下也走不通。
    """
    from solver.search_core import expand
    cur = frozenset(start_coords)
    seq = []
    for i, (act, rep) in enumerate(path):
        cand = [nw for nw, a, r in expand(cur, step) if a == act and r == rep]
        if not cand:
            return seq, {'idx': i, 'kind': 'no_successor', 'action': act,
                         'rep': rep}
        if len(set(cand)) != 1:
            return seq, {'idx': i, 'kind': 'ambiguous', 'action': act,
                         'rep': rep, 'n': len(set(cand))}
        cur = frozenset(cand[0])
        seq.append(cur)
    return seq, None


def diff_of(a, b, m, n):
    """两个局面的差异描述。"""
    A, B = set(a), set(b)
    only_a, only_b = A - B, B - A
    shift = None
    if len(A) == len(B):
        ra, ca = min(r for r, _ in A), min(c for _, c in A)
        rb, cb = min(r for r, _ in B), min(c for _, c in B)
        moved = {(r - ra, c - ca) for r, c in A}
        moved_b = {(r - rb, c - cb) for r, c in B}
        if moved == moved_b:
            shift = (rb - ra, cb - ca)
    return {'only_expected': sorted(only_a), 'only_actual': sorted(only_b),
            'pure_shift': shift}


def holes_of(coords, m, n):
    return len(fast_window(frozenset(coords), m, n)[1])


def score_of(g, m, n):
    return H.gather_metrics(H.coords_of(g), m, n)['score']


# ---------------------------------------------------------------------------
# 主流程：完整复刻 exp12_chain.solve 的三段，但每一步都留观测点
# ---------------------------------------------------------------------------
def run_one(snap, cap, budget, max_rounds=12):
    from solver.ml.gather_solver import gradient_gather
    from solver.ml.fill_macro import solve_fill_macro

    m, n, st = snap['m'], snap['n'], snap['step']
    log(f"\n{'='*74}\nseed={snap['seed']} cap={cap} "
        f"（起点洞数={holes_of(snap['coords'], m, n)}）")
    t0 = time.time()

    # ---------- 段1 ----------
    g0 = H.load_game(snap)
    r = gradient_gather(g0, st)
    acts = list(r['actions'])
    reps = list(r.get('rep_cells', []))
    if cap is not None:
        acts, reps = acts[:cap], reps[:cap]
    s1 = [(a, None) for a in acts]
    s1r = list(zip(acts, reps))

    ok1, g1, tr1, f1 = apply_all(snap, s1)
    ok1r, g1r, tr1r, f1r = apply_all(snap, s1r)
    same1 = (tr1 == tr1r)
    log(f"  段1 聚拢 {len(s1)} 步：重放全部合法={ok1} "
        f"（带rep路径也合法={ok1r}）两条路径轨迹一致={same1}")
    if not ok1:
        log(f"    !! 段1 重放就在第 {f1['idx']} 步失败：{f1['action']} "
            f"执行前\n{f1['before']}")
        return None, 'seg1_replay_bad'
    if not same1:
        k = next(i for i in range(len(tr1)) if tr1[i] != tr1r[i])
        log(f"    !! 段1 两条路径在第 {k+1} 步分叉（多分量歧义确实存在）")
    log(f"    段1 后：洞数={holes_of(H.coords_of(g1), m, n)} "
        f"score={score_of(g1, m, n):.3f} solved={g1.is_solved()}")
    steps = list(s1)
    if g1.is_solved():
        log("  段1 已还原")
        return steps, 'gather'

    # ---------- 段2 ----------
    res = solve_fill_macro(g1, st)
    fsteps = []
    if isinstance(res, tuple):
        fsteps = list(zip(res[0], res[1]))
    elif isinstance(res, dict) and res.get('type') == 'fill_partial':
        fsteps = list(zip(res.get('actions', []), res.get('rep_cells', [])))
    if fsteps:
        okf, gf, _trf, ff = apply_all(snap, steps + fsteps)
        before = score_of(apply_all(snap, steps)[1], m, n)
        after = score_of(gf, m, n) if okf else -1
        log(f"  段2 填洞 {len(fsteps)} 步：合法={okf} score {before:.3f}→"
            f"{after:.3f} 采纳={okf and after >= before}")
        if okf and gf.is_solved():
            return steps + fsteps, 'fill'
        if okf and after >= before:
            steps += fsteps
        ok_again, g1, _t, _f = apply_all(snap, steps)
        if not ok_again:
            return None, 'seg2_replay_bad'

    # ---------- 段3 ----------
    g = apply_all(snap, steps)[1]
    exp12_abort = None
    for rnd in range(1, max_rounds + 1):
        if g.is_solved():
            break
        coords = H.coords_of(g)
        h_before = holes_of(coords, m, n)
        t1 = time.perf_counter()
        path, used = guided_reduce_one(coords, m, n, st, budget=budget)
        dt = time.perf_counter() - t1
        if not path:
            log(f"  段3 第{rnd}轮：搜索无解（nodes={used} {dt:.1f}s）"
                f" → guided_stuck")
            return None, 'guided_stuck'
        log(f"  段3 第{rnd}轮：洞数={h_before} 搜索出 {len(path)} 步 "
            f"(nodes={used} {dt:.1f}s)")

        # (1) 重放：逐步是否合法
        ok_rep, g_after, tr_rep, f_rep = apply_all(snap, steps + path)
        # (2) 重放（忽略 rep，一律 apply_action）——看 rep 是否关键
        ok_plain, g_plain, tr_plain, f_plain = apply_all(snap, steps + path,
                                                         use_rep=False)
        # (3) 搜索内部推进
        seq_srch, err_srch = search_progression(coords, path, st)

        tail_rep = tr_rep[len(steps):]
        tail_plain = tr_plain[len(steps):]
        diverge_rep = next((i for i in range(min(len(tail_rep), len(seq_srch)))
                            if tail_rep[i] != seq_srch[i]), None)
        diverge_plain = next((i for i in range(min(len(tail_plain),
                                                   len(seq_srch)))
                              if tail_plain[i] != seq_srch[i]), None)

        solved_after = g_after.is_solved()
        log(f"    重放(带rep) 全部步合法={ok_rep}；重放(忽略rep) 合法="
            f"{ok_plain}；搜索内部推进 {'通' if err_srch is None else '不通'}")
        log(f"    与搜索序列首个分叉点：带rep={diverge_rep} 忽略rep="
            f"{diverge_plain}（None=完全一致）")
        if err_srch is not None:
            log(f"    !! 搜索语义下该 path 自身走不通：{err_srch}")
        if f_rep is not None:
            log(f"    !! 重放第 {f_rep['idx']-len(steps)} 步（path 内）非法："
                f" action={f_rep['action']} rep={f_rep['rep']}\n"
                f"      执行前\n{f_rep['before']}")

        h_after = holes_of(H.coords_of(g_after), m, n) if ok_rep else -1
        log(f"    结果：洞数 {h_before}→{h_after} 已还原={solved_after}")

        # exp12 的判据：replay_steps 返回的是 is_solved()
        if exp12_abort is None and ok_rep and not solved_after:
            exp12_abort = {
                'round': rnd, 'applied_all': True, 'solved': False,
                'holes_before': h_before, 'holes_after': h_after,
                'path_len': len(path),
                'note': ('exp12 会在此处 return None,"guided_replay_bad"，'
                         '但 path 每一步都合法，只是尚未还原'),
            }
            log("    >>> 【关键】全部步合法但未还原 ⇒ exp12 在此判为 "
                "guided_replay_bad（误判点）")
        if not ok_rep:
            return None, 'guided_replay_bad_TRUE'
        steps += path
        g = g_after

    final_ok = g.is_solved()
    log(f"  段3 结束：轮数={rnd} 总步={len(steps)} 还原={final_ok} "
        f"({time.time()-t0:.0f}s)")
    if exp12_abort:
        log(f"  exp12 误判点摘要：{exp12_abort}")
    if not final_ok:
        return None, 'guided_guard'
    return steps, 'guided'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--seeds', default=None)
    ap.add_argument('--caps', default='15')
    ap.add_argument('--budget', type=int, default=80000)
    ap.add_argument('--opt', action='store_true', help='额外查表算最优倍数')
    args = ap.parse_args()

    m, n, st = (int(x) for x in args.configs.split('x'))
    seeds = ([int(s) for s in args.seeds.split(',')] if args.seeds
             else LONG_SEEDS[:3])
    caps = [None if c == 'none' else int(c) for c in args.caps.split(',')]

    os.makedirs(LOG_DIR, exist_ok=True)
    log(f"\n\n########## exp16 诊断启动 {time.strftime('%F %T')} "
        f"seeds={seeds} caps={caps} budget={args.budget} ##########")

    table = None
    if args.opt:
        from solver.table_solver import load_table
        table = load_table(m, n, st)
        log(f"距离表已加载：{len(table) if table else 0} 项")

    summary = []
    for cap in caps:
        for seed in seeds:
            snap = H.gen_state(m, n, st, seed)
            steps, who = run_one(snap, cap, args.budget)
            row = {'seed': seed, 'cap': cap, 'who': who,
                   'len': len(steps) if steps else 0}
            if steps and table is not None:
                from solver.table_core import canonicalize
                opt = table.get(canonicalize(frozenset(
                    tuple(c) for c in snap['coords'])))
                row['opt'] = opt
                row['ratio'] = (len(steps) / opt) if opt else None
                log(f"  最优={opt} 倍数={row['ratio']:.1f}x"
                    if row['ratio'] else f"  最优={opt}")
            summary.append(row)

    log("\n=== 汇总 ===")
    for row in summary:
        extra = f" 倍数={row['ratio']:.1f}x" if row.get('ratio') else ''
        log(f"  cap={str(row['cap']):>4} seed{row['seed']} "
            f"{row['who']:<20} {row['len']:>4}步{extra}")
    log(f"日志：{LOG_PATH}")


if __name__ == '__main__':
    main()
