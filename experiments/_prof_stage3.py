# -*- coding: utf-8 -*-
"""阶段3 可行性探查：对【当前】gather 主循环重新 cProfile，拿到真实热点占比。
不修改任何求解逻辑，仅测量。8x8 step=2（记忆里 06/07 的 46% 热点原型尺寸）。
"""
import sys, time, cProfile, pstats, io

sys.path.insert(0, '.')
from game import SliderMatrix
from solver.ml.gather_solver import gather_solve


def run_one(m, n, step, max_steps, patience, wait, k):
    g = SliderMatrix(m, n)
    g.shuffle(attempts=120, step=step)
    r = gather_solve(g, step=step, max_steps=max_steps, patience=patience,
                     max_wait_time=wait, target_gather_score=1.0,
                     aggressiveness=0.2, phi_prescreen_k=k)
    return r


def main():
    m, n, step = 8, 8, 2
    max_steps, patience, wait, k = 200, 80, 25, 8
    print(f"PROFILE gather_solve {m}x{n} step={step} "
          f"max_steps={max_steps} patience={patience} wait={wait}s k={k}\n")

    pr = cProfile.Profile()
    pr.enable()
    t0 = time.time()
    reps = 3
    last = None
    for i in range(reps):
        r = run_one(m, n, step, max_steps, patience, wait, k)
        last = r
        print(f"  rep{i+1}: reason={r['reason']:14s} steps={len(r['actions']):3d} "
              f"score={r['end']['score']:.4f} solved={r['solved']}")
    pr.disable()
    el = time.time() - t0
    print(f"\n总耗时 {el:.1f}s / {reps} 盘\n")

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s)
    ps.sort_stats('cumulative')
    # 只看 solver/ml 与 game 与 table_core 的热点函数
    ps.print_stats(40)
    out = s.getvalue()
    # 过滤行，聚焦我们关心的调用
    keep = []
    for line in out.splitlines():
        if any(k in line for k in ('gather_solver', 'game.py', 'table_core',
                                    'actions.py', 'invariants', 'opt', 'overlap',
                                    'canonicalize', 'connected', 'restore',
                                    'snapshot', 'profile_defect', 'shuffle',
                                    'try_move', 'commit_move', 'apply_action',
                                    'enumerate', 'is_valid')):
            keep.append(line)
    print('\n'.join(keep))


if __name__ == '__main__':
    main()
