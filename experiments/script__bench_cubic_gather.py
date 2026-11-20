# -*- coding: utf-8 -*-
"""三維聚攏求解器基準 + 剖析（優化方案 P0 第 1 步）。

固定打亂集（每尺寸固定 seed，逐步可重放），量四件事：

  · 牆鐘：中位 / p95（秒）；
  · 解出率：真的還原的局面數；
  · 解長：返回動作步數的中位；
  · 展開節點數：候選評估次數（求解器若回報 `stats` 才記）。

`--profile N` 額外對第 N 個 case 跑 cProfile，輸出 cumtime / tottime 前 20。

用法：
    python experiments/script__bench_cubic_gather.py --label baseline
    python experiments/script__bench_cubic_gather.py --label opt --profile 1

輸出：experiments/results/cubic_gather_bench_<label>.json
"""
import argparse
import cProfile
import io
import json
import os
import pstats
import random
import statistics
import sys
import tempfile
import time

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from solver.ml.cubic_gather import cubic_gather_solve, cubic_metrics  # noqa: E402

OUT_DIR = os.path.join(ROOT, 'experiments', 'results')
# 打亂力度按塊數給：3×3×3=27 塊洗 120 步；4×4×4=64 塊洗 200 步。
SCRAMBLE_MOVES = {(3, 3, 3): 120, (4, 4, 4): 200}


def build_gui():
    """建一個無窗口 GUI（只借它建局 / 打亂，不走渲染）。"""
    pygame.init()
    gui = SliderGUI(m=4, n=4, step=1)
    gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_bench_')
    gui.config_path = os.path.join(gui.config_dir, 'config.json')
    gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui._cubic_camera_prefs = {}
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    return gui


def run_case(gui, dims, seed, max_steps, patience, wait):
    """一個固定 case：同 seed 必然生成同一打亂局面。"""
    gui.new_cubic_puzzle(dims[0], dims[1], dims[2], 1)
    random.seed(1000 + seed)
    gui.game.shuffle(SCRAMBLE_MOVES[dims], 1, record=[])
    gui.game_history.reset()
    gui.step_count = 0

    start = cubic_metrics([tuple(b.location[:3]) for b in gui.game.blocks], dims)
    t0 = time.perf_counter()
    res = cubic_gather_solve(gui.game, step=1, max_steps=max_steps,
                             patience=patience, max_wait_time=wait,
                             target_gather_score=None)
    dt = time.perf_counter() - t0
    return {
        'dims': list(dims),
        'seed': seed,
        'wall': dt,
        'solved': bool(res['solved']),
        'steps': len(res['actions']),
        'reason': res['reason'],
        'score_start': start['score'],
        'score_end': res['end']['score'],
        'expanded': (res.get('stats') or {}).get('expanded'),
        'reps_have_3': all(len(r) == 3 for r in res['rep_cells']),
        'actions_len': sorted({len(a) for a in res['actions']}),
    }


def pct(vals, q):
    if not vals:
        return 0.0
    vals = sorted(vals)
    i = min(len(vals) - 1, max(0, int(round(q * (len(vals) - 1)))))
    return vals[i]


def summarize(rows):
    walls = [r['wall'] for r in rows]
    steps = [r['steps'] for r in rows]
    expanded = [r['expanded'] for r in rows if r['expanded'] is not None]
    return {
        'n': len(rows),
        'solve_rate': sum(1 for r in rows if r['solved']) / len(rows),
        'wall_median': statistics.median(walls),
        'wall_p95': pct(walls, 0.95),
        'wall_total': sum(walls),
        'steps_median': statistics.median(steps) if steps else 0,
        'expanded_median': statistics.median(expanded) if expanded else None,
        'reasons': {k: sum(1 for r in rows if r['reason'] == k)
                    for k in sorted({r['reason'] for r in rows})},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', default='baseline')
    ap.add_argument('--sizes', default='3x3x3,4x4x4')
    ap.add_argument('--seeds', type=int, default=8)
    ap.add_argument('--max-steps', type=int, default=240)
    ap.add_argument('--patience', type=int, default=80)
    ap.add_argument('--wait', type=float, default=20.0)
    ap.add_argument('--profile', type=int, default=0,
                    help='對第 N 個 case（1 起）跑 cProfile；0 = 不剖析')
    args = ap.parse_args()

    dims_list = [tuple(int(x) for x in s.lower().split('x'))
                 for s in args.sizes.split(',')]
    gui = build_gui()
    rows = []
    profile_target = args.profile
    idx = 0
    for dims in dims_list:
        for seed in range(args.seeds):
            idx += 1
            if profile_target and idx == profile_target:
                prof = cProfile.Profile()
                prof.enable()
                row = run_case(gui, dims, seed, args.max_steps,
                               args.patience, args.wait)
                prof.disable()
                buf = io.StringIO()
                stats = pstats.Stats(prof, stream=buf).sort_stats('tottime')
                stats.print_stats(20)
                print(buf.getvalue())
                print(f'  [profiled case] {row}')
            else:
                row = run_case(gui, dims, seed, args.max_steps,
                               args.patience, args.wait)
            rows.append(row)
            print(f'  {dims} seed={seed}: {row["wall"]:.2f}s '
                  f'solved={row["solved"]} steps={row["steps"]} '
                  f'reason={row["reason"]} '
                  f'score {row["score_start"]:.3f}->{row["score_end"]:.3f}')

    overall = summarize(rows)
    by_size = {}
    for dims in dims_list:
        by_size['x'.join(str(v) for v in dims)] = summarize(
            [r for r in rows if tuple(r['dims']) == dims])
    payload = {
        'label': args.label,
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'params': {
            'sizes': ['x'.join(str(v) for v in d) for d in dims_list],
            'seeds': args.seeds, 'max_steps': args.max_steps,
            'patience': args.patience, 'wait': args.wait,
            'scramble': {k[0].__str__() + 'x' + str(k[1]) + 'x' + str(k[2]): v
                         for k, v in SCRAMBLE_MOVES.items()},
        },
        'overall': overall,
        'by_size': by_size,
        'cases': rows,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f'cubic_gather_bench_{args.label}.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print('=' * 60)
    print(json.dumps(overall, ensure_ascii=False, indent=2))
    for k, v in by_size.items():
        print(k, json.dumps(v, ensure_ascii=False))
    print('saved:', path)


if __name__ == '__main__':
    main()
