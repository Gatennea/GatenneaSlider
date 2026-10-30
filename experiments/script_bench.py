# -*- coding: utf-8 -*-
"""基线基准：在相同语料上跑各现有算法，重放验证并汇总。

用法（在 GatenneaSlider 目录）：
  D:\\python\\python.exe -m experiments.bench --quick
  D:\\python\\python.exe -m experiments.bench --configs 4x4x2,5x5x2,6x6x2 --n 10
"""
import argparse
import json
import os
import time
import traceback

from experiments import harness as H

ALGOS = ['ida', 'fast', 'greedy', 'gather', 'gradient', 'fill']


def run_one(algo, snap):
    """在一个全新局面上跑指定算法，返回 (actions, dt, extra)。"""
    g = H.load_game(snap)
    step = snap['step']
    extra = {}
    t0 = time.perf_counter()
    if algo == 'ida':
        from solver import solve
        r = solve(g, step)
        actions = list(r) if r else None
    elif algo == 'fast':
        from solver import solve_fast
        r = solve_fast(g, step)
        actions = list(r) if r else None
    elif algo == 'greedy':
        from solver import solve_greedy
        r = solve_greedy(g, step)
        actions = list(r) if r else None
    elif algo == 'gather':
        from solver.ml.gather_solver import gather_solve
        r = gather_solve(g, step)
        actions = list(r['actions'])
        extra['reason'] = r['reason']
    elif algo == 'gradient':
        from solver.ml.gather_solver import gradient_gather
        r = gradient_gather(g, step)
        actions = list(r['actions'])
        extra['reason'] = r['reason']
    elif algo == 'fill':
        from solver.ml.fill_macro import solve_fill_macro
        r = solve_fill_macro(g, step)
        if isinstance(r, dict):
            actions = None
            extra['type'] = r.get('type')
            extra['reason'] = r.get('reason')
        else:
            actions, _reps = r
            actions = list(actions)
    else:
        raise ValueError(algo)
    dt = time.perf_counter() - t0
    return actions, dt, extra


def evaluate(algo, snap):
    """跑 + 重放验证，返回一条结果记录。"""
    rec = {'config': f"{snap['m']}x{snap['n']}x{snap['step']}",
           'seed': snap['seed'], 'algo': algo}
    rec['start_score'] = round(H.start_score(snap)['score'], 4)
    try:
        actions, dt, extra = run_one(algo, snap)
    except Exception as e:
        rec.update(solved=False, steps=-1, time=0.0, verified=False,
                   final_score=rec['start_score'], error=repr(e))
        traceback.print_exc()
        return rec
    rec['time'] = round(dt, 3)
    rec.update(extra)
    if not actions:
        rec.update(solved=False, steps=0, verified=False,
                   final_score=rec['start_score'])
        return rec
    ok, final_g = H.replay(snap, actions)
    rec['steps'] = len(actions)
    rec['verified'] = bool(ok)
    rec['solved'] = bool(ok)
    rec['final_score'] = round(
        H.gather_metrics(H.coords_of(final_g), snap['m'], snap['n'])['score'], 4)
    return rec


def aggregate(records):
    groups = {}
    for r in records:
        key = (r['config'], r['algo'])
        groups.setdefault(key, []).append(r)
    rows = []
    for (cfg, algo), rs in sorted(groups.items()):
        n = len(rs)
        solved = [r for r in rs if r['solved']]
        times = [r['time'] for r in rs]
        steps = [r['steps'] for r in solved]
        finals = [r['final_score'] for r in rs]
        rows.append({
            'config': cfg, 'algo': algo, 'n': n,
            'solve_rate': f"{100*len(solved)/n:.0f}%",
            'med_steps': sorted(steps)[len(steps)//2] if steps else '-',
            'med_time': f"{sorted(times)[len(times)//2]:.2f}s",
            'max_time': f"{max(times):.1f}s",
            'med_final': f"{sorted(finals)[len(finals)//2]:.3f}",
        })
    return rows


def print_table(rows):
    hdr = ['config', 'algo', 'n', 'solve_rate', 'med_steps',
           'med_time', 'max_time', 'med_final']
    widths = {h: max(len(h), *(len(str(r[h])) for r in rows)) for h in hdr}
    line = '  '.join(h.ljust(widths[h]) for h in hdr)
    print(line)
    print('-' * len(line))
    for r in rows:
        print('  '.join(str(r[h]).ljust(widths[h]) for h in hdr))


def parse_config(s):
    m, n, st = s.split('x')
    return int(m), int(n), int(st)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--n', type=int, default=8)
    ap.add_argument('--algos', default=','.join(ALGOS))
    ap.add_argument('--out', default=os.path.join('experiments', 'results'))
    args = ap.parse_args()

    if args.quick:
        specs = [(4, 4, 2)]
        n = 3
        algos = ['gather', 'gradient', 'fill', 'greedy']
    else:
        specs = [parse_config(s) for s in args.configs.split(',')]
        n = args.n
        algos = args.algos.split(',')

    corpus = H.build_corpus(specs, n)
    print(f"语料 {len(corpus)} 个局面；配置 {specs}；算法 {algos}\n")

    records = []
    for snap in corpus:
        ss = H.start_score(snap)
        print(f"  局面 {snap['m']}x{snap['n']} step{snap['step']} "
              f"seed={snap['seed']} 起始聚拢度={ss['score']:.3f}")
        for algo in algos:
            rec = evaluate(algo, snap)
            records.append(rec)
            mark = '解' if rec['solved'] else '败'
            print(f"      {algo:9s} {mark} {rec['steps']:>4}步 "
                  f"{rec['time']:>6.2f}s 终={rec['final_score']:.3f}")

    rows = aggregate(records)
    print('\n========== 汇总 ==========')
    print_table(rows)

    os.makedirs(args.out, exist_ok=True)
    tag = time.strftime('%Y%m%d-%H%M%S')
    path = os.path.join(args.out, f'baseline_{tag}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'rows': rows, 'records': records}, f,
                  ensure_ascii=False, indent=2)
    print(f"\n已保存 {path}")


if __name__ == '__main__':
    main()
