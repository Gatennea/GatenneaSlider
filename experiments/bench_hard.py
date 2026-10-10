# -*- coding: utf-8 -*-
"""把 失败04/07 的初始打乱局面存为盘面存档，并跑「确定性 vs 随机探索」实测。

针对硬死局：单个随机种子证据太弱，故随机臂扫多个种子，报告
「是否有任一随机种子比确定性多解 / 更短」。
多进程并行（每盘 = 1 次确定性 + N 次随机）。

用法：
    D:/python/python.exe experiments/bench_hard.py
"""
import os
import sys
import time
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from disk_plan import DISK_DIR, iter_disk_paths
from render_gallery import build
from game import SliderMatrix
from solver.state import restore
from solver.ml.gather_solver import gather_solve

HERE = os.path.dirname(os.path.abspath(__file__))
GALLERY = os.path.join(HERE, 'disks_gallery.html')

ARCHIVES = {
    'FAIL04': 'archives/失败04.json',
    'FAIL07': 'archives/失败07.json',
}
CAP = 90
MAX_STEPS = 4000
STOCH_SEEDS = [101, 202, 303, 404, 505, 606, 707, 808]


def extract_initial(arch_path):
    d = json.load(open(arch_path, encoding='utf-8'))
    p = d['puzzle']
    m, n, step = p['m'], p['n'], p['step']
    snap0 = d['history']['snapshots'][0]
    mat = snap0['matrix']
    b = snap0['bounds']
    blocks = [[b['min_row'] + i, b['min_col'] + j]
              for i in range(len(mat)) for j in range(len(mat[i]))
              if mat[i][j] == 1]
    return {'m': m, 'n': n, 'step': step, 'attempts': 0, 'dseed': -1,
            'cap': CAP, 'blocks': blocks, 'src': os.path.basename(arch_path)}


def save_disk_file(name, rec):
    os.makedirs(DISK_DIR, exist_ok=True)
    p = os.path.join(DISK_DIR, f"disk_{name}.json")
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(rec, f)
    return p


def solve(rec, stochastic, seed):
    m, n, step = rec['m'], rec['n'], rec['step']
    g = SliderMatrix(m, n)
    restore(g, {'m': m, 'n': n, 'blocks': rec['blocks']})
    t = time.time()
    try:
        r = gather_solve(g, step=step, max_steps=MAX_STEPS, patience=150,
                         max_wait_time=CAP, target_gather_score=1.0,
                         aggressiveness=0.2, optimize_path=True,
                         stochastic=stochastic, seed=seed)
    except Exception as e:
        return {'crashed': True, 'err': repr(e)}, time.time() - t
    return r, time.time() - t


def worker(task):
    rec, stochastic, seed, tag = task
    r, t = solve(rec, stochastic, seed)
    if r.get('crashed'):
        return {'tag': tag, 'crashed': True, 'err': r['err']}
    return {'tag': tag, 'stochastic': stochastic, 'seed': seed,
            'solved': bool(r['solved']), 'steps': len(r['actions']),
            'score': round(r['end']['score'], 4), 'best_score': round(r['best']['score'], 4),
            'kicks': r.get('kicks', 0), 'reason': r.get('reason'),
            'time': round(t, 2)}


def _verdict(det_solved, det_steps, stoch_solved):
    if not det_solved and stoch_solved:
        return f"随机翻盘：确定性未解，随机有 {len(stoch_solved)} 个种子解出了"
    if det_solved and stoch_solved:
        best = min(stoch_solved, key=lambda s: s['steps'])
        if best['steps'] < det_steps:
            return f"都解了，随机更短（最优 {best['steps']} 步 vs 确定性 {det_steps} 步）"
        return f"都解了，确定性已最优（{det_steps} 步），随机未更短"
    if det_solved and not stoch_solved:
        return "确定性已解，随机反而没解（净负）"
    return "两者都没解（死局依旧，随机未翻盘）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=6)
    args = ap.parse_args()

    # 1) 提取并存档
    recs = {}
    for name, apath in ARCHIVES.items():
        rec = extract_initial(apath)
        save_disk_file(name, rec)
        recs[name] = rec
        print(f"{name}: 8x8 step2, 方块 {len(rec['blocks'])}, 已存 disk_{name}.json")

    # 2) 构建任务（每盘：1 次确定性 + 多个随机种子）
    tasks = []
    for name, rec in recs.items():
        tasks.append((rec, False, None, f'{name}/det'))
        for sd in STOCH_SEEDS:
            tasks.append((rec, True, sd, f'{name}/stoch{sd}'))

    t0 = time.time()
    if args.workers and args.workers > 1 and len(tasks) > 1:
        import multiprocessing as mp
        with mp.Pool(args.workers) as pool:
            out = pool.map(worker, tasks)
    else:
        out = [worker(t) for t in tasks]
    wall = time.time() - t0

    # 3) 聚合
    results = {}
    by_tag = {o['tag']: o for o in out}
    for name in recs:
        det = by_tag[f'{name}/det']
        stoch = [by_tag[f'{name}/stoch{sd}'] for sd in STOCH_SEEDS]
        det_solved = bool(det.get('solved'))
        det_steps = det.get('steps')
        stoch_solved = [s for s in stoch if s.get('solved')]
        verdict = _verdict(det_solved, det_steps, stoch_solved)
        results[name] = {'det': det, 'stoch': stoch, 'verdict': verdict}

    # 4) 打印
    for name in recs:
        r = results[name]
        d = r['det']
        print(f"\n=== {name} ===")
        if d.get('crashed'):
            print(f"  确定性: CRASH {d['err']}")
        else:
            print(f"  确定性: solved={d['solved']} 净步数={d['steps']} 峰值聚拢={d['best_score']:.4f} "
                  f"reason={d['reason']} t={d['time']}s")
        for s in r['stoch']:
            if s.get('crashed'):
                print(f"  随机 seed{s['seed']}: CRASH {s['err']}")
            else:
                tag = 'SOLVED' if s['solved'] else ''
                print(f"  随机 seed{s['seed']}: solved={s['solved']} 净步数={s['steps']} "
                      f"峰值聚拢={s['best_score']:.4f} kicks={s['kicks']} reason={s['reason']} "
                      f"t={s['time']}s {tag}")
        print(f"  -> {r['verdict']}")

    # 5) 写结果 + 更新画廊
    outp = os.path.join(HERE, 'bench_results_hard.json')
    with open(outp, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    build(iter_disk_paths(), GALLERY)
    print(f"\n总墙钟 {wall:.1f}s（并行 {args.workers}）；结果 {outp}；画廊已更新 {GALLERY}")


if __name__ == '__main__':
    main()
