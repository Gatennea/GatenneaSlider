# -*- coding: utf-8 -*-
"""從本地盤面存檔跑基準（不再重新打亂）。支持多進程並行。

盤面 = experiments/disks/*.json（由 make_disks.py 生成）。每個存檔獨立，天然可並行。

用法：
    D:/python/python.exe experiments/bench_disks.py --mode stochastic --workers 4
    D:/python/python.exe experiments/bench_disks.py --mode pathopt   --workers 4

mode=stochastic : 臂A 确定性(stochastic=False) vs 臂B 随机(stochastic=True, 固定种子)
mode=pathopt    : 臂A 不优化路径(optimize_path=False) vs 臂B 优化路径(optimize_path=True)
"""
import os
import sys
import time
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from disk_plan import iter_disk_paths, load_disk, large_spec_keys
from game import SliderMatrix
from solver.state import restore
from solver.ml.gather_solver import gather_solve

STOCH_SEED = 12345
MAX_STEPS = 2000
HERE = os.path.dirname(os.path.abspath(__file__))


def _solve(rec, *, stochastic, optimize_path, seed, max_steps):
    m, n, step = rec['m'], rec['n'], rec['step']
    cap = rec.get('cap', 25)
    g = SliderMatrix(m, n)
    restore(g, {'m': m, 'n': n, 'blocks': rec['blocks']})
    t = time.time()
    try:
        r = gather_solve(g, step=step, max_steps=max_steps, patience=150,
                         max_wait_time=cap, target_gather_score=1.0,
                         aggressiveness=0.2, optimize_path=optimize_path,
                         stochastic=stochastic, seed=seed)
    except Exception as e:
        return {'crashed': True, 'err': repr(e)}, time.time() - t
    return r, time.time() - t


def run_one(args):
    path, mode, max_steps = args
    try:
        rec = load_disk(path)
    except Exception as e:
        return {'path': path, 'error': f'load: {e}'}

    if mode == 'stochastic':
        rA, eA = _solve(rec, stochastic=False, optimize_path=True, seed=None, max_steps=max_steps)
        rB, eB = _solve(rec, stochastic=True,  optimize_path=True, seed=STOCH_SEED, max_steps=max_steps)
        armA, armB = 'det', 'stoch'
    else:  # pathopt
        rA, eA = _solve(rec, stochastic=False, optimize_path=False, seed=None, max_steps=max_steps)
        rB, eB = _solve(rec, stochastic=False, optimize_path=True,  seed=None, max_steps=max_steps)
        armA, armB = 'off', 'on'

    if rA.get('crashed') or rB.get('crashed'):
        return {'path': path, 'mode': mode, 'crash': True,
                'errA': rA.get('err'), 'errB': rB.get('err')}

    sd, ss = bool(rA['solved']), bool(rB['solved'])
    nd, ns = len(rA['actions']), len(rB['actions'])
    scd, scs = rA['end']['score'], rB['end']['score']
    if ss and not sd:
        flag = f'{armB}+'
    elif sd and not ss:
        flag = f'{armA}+'
    else:
        flag = '='

    return {
        'path': path, 'mode': mode,
        'm': rec['m'], 'n': rec['n'], 'step': rec['step'], 'dseed': rec['dseed'],
        'solvedA': sd, 'solvedB': ss,
        'stepsA': nd, 'stepsB': ns,
        'scoreA': round(scd, 4), 'scoreB': round(scs, 4),
        'timeA': round(eA, 2), 'timeB': round(eB, 2),
        'kicksA': rA.get('kicks', 0), 'kicksB': rB.get('kicks', 0),
        'opt_removed': rB.get('opt_removed', 0),
        'flag': flag,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['stochastic', 'pathopt'], default='stochastic')
    ap.add_argument('--workers', type=int, default=4, help='並行進程數（0=串行）')
    ap.add_argument('--max-steps', type=int, default=MAX_STEPS)
    ap.add_argument('--large', action='store_true', help='只跑大尺寸盤面 (LARGE_SPECS)')
    args = ap.parse_args()

    specs = large_spec_keys() if args.large else None
    paths = iter_disk_paths(specs=specs)
    if not paths:
        print("沒有盤面存檔。請先跑：D:/python/python.exe experiments/make_disks.py")
        return
    print(f"模式={args.mode}  盤面數={len(paths)}  並行={args.workers}\n")

    tasks = [(p, args.mode, args.max_steps) for p in paths]

    t0 = time.time()
    if args.workers and args.workers > 0 and len(tasks) > 1:
        import multiprocessing as mp
        with mp.Pool(args.workers) as pool:
            results = pool.map(run_one, tasks)
    else:
        results = [run_one(t) for t in tasks]
    wall = time.time() - t0

    # 匯總
    winsA = winsB = ties = crashes = errors = 0
    step_diff_sum = score_diff_sum = 0.0
    n_both = 0
    for r in results:
        if 'error' in r or r.get('crash'):
            crashes += 1
            continue
        if r['flag'] == '=':
            ties += 1
        elif r['flag'].endswith('+'):
            # flag 形如 'det+' / 'stoch+' / 'off+' / 'on+'
            if r['flag'] == 'stoch+' or r['flag'] == 'on+':
                winsB += 1
            else:
                winsA += 1
        if r['solvedA'] and r['solvedB']:
            n_both += 1
            step_diff_sum += (r['stepsB'] - r['stepsA'])
            score_diff_sum += (r['scoreB'] - r['scoreA'])

    # 打印每盤
    for r in results:
        if 'error' in r:
            print(f"  {os.path.basename(r['path'])}: ERROR {r['error']}")
            continue
        if r.get('crash'):
            print(f"  {os.path.basename(r['path'])}: CRASH A={r['errA']} B={r['errB']}")
            continue
        print(f"  {os.path.basename(r['path'])}: "
              f"A[solved={int(r['solvedA'])} {r['stepsA']}步 sc={r['scoreA']} 踢{r['kicksA']}] "
              f"vs B[solved={int(r['solvedB'])} {r['stepsB']}步 sc={r['scoreB']} 踢{r['kicksB']} "
              f"opt-{r['opt_removed']}] -> {r['flag']}  ({r['timeA']}s/{r['timeB']}s)")
    print('=' * 60)
    print(f"臂A({('det' if args.mode=='stochastic' else 'off')})胜 : {winsA}")
    print(f"臂B({('stoch' if args.mode=='stochastic' else 'on')})胜 : {winsB}")
    print(f"平手                          : {ties}")
    print(f"崩潰/錯誤                     : {crashes}")
    if n_both:
        print(f"兩臂都還原的 {n_both} 盤：臂B平均步數差 {step_diff_sum/n_both:+.2f} "
              f"（正=臂B更長），平均終聚拢度差 {score_diff_sum/n_both:+.4f}")
    print(f"總牆鐘時間                    : {wall:.1f}s（並行 {args.workers}）")

    suffix = f'{args.mode}' + ('_large' if args.large else '')
    out = os.path.join(HERE, f'bench_results_{suffix}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'mode': args.mode, 'wall_s': round(wall, 1), 'workers': args.workers,
                   'summary': {'winsA': winsA, 'winsB': winsB, 'ties': ties,
                               'crashes': crashes, 'n_both': n_both,
                               'avg_step_diff': (step_diff_sum/n_both) if n_both else None,
                               'avg_score_diff': (score_diff_sum/n_both) if n_both else None},
                   'per_disk': results}, f, ensure_ascii=False, indent=2)
    print(f"結果已寫入：{out}")


if __name__ == '__main__':
    main()
