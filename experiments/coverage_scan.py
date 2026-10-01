# -*- coding: utf-8 -*-
"""全配置覆盖率扫描（2026-10-01）。

把「能解所有矩形谜题」变成可测数字：批量生成 尺寸×孔洞/缺口拆分×种子
的配置，全部跑 GUI 同款入口（补缺宏 gap_macro → 失败再补缺面填洞宏
fill_macro），输出 解出率 + 失败清单。

失败/部分解的盘面自动落盘成 GUI 可打开的存档
（experiments/results/coverage_fails/），直接变成新教学案例候选。

用法：
    python experiments/coverage_scan.py            # 快速档（~20 局）
    python experiments/coverage_scan.py --full     # 大扫描
    python experiments/coverage_scan.py --sizes 6x6 --voids 2 --seeds 5
"""
import argparse
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver.ml.ann_gen import generate_classified, generate_random_void
from solver.ml.fill_macro import (build_game, gcoords, _replay_apply,
                                  solve_fill_macro)
from solver.ml.gap_solver import solve_gap_macro

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'results')
FAILS_DIR = os.path.join(RESULTS_DIR, 'coverage_fails')


def _replay_solved(coords, m, n, step, acts4, reps):
    """回放动作并验收终局——partial 的元组返回不得冒充全解。"""
    g2 = build_game(coords, m, n)
    for a4, r in zip(acts4, reps):
        if not _replay_apply(g2, [tuple(a4) + (r,)], m, n, step):
            return False
    return g2.is_solved()


def _save_archive(coords, m, n, step, path):
    """盘面 → GUI 可打开的 v1 存档（矩阵以滑块边界为范围）。"""
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    bounds = {'min_row': min(rs), 'max_row': max(rs),
              'min_col': min(cs), 'max_col': max(cs)}
    matrix = [[1 if (bounds['min_row'] + i, bounds['min_col'] + j) in coords
               else 0
               for j in range(bounds['max_col'] - bounds['min_col'] + 1)]
              for i in range(bounds['max_row'] - bounds['min_row'] + 1)]
    data = {
        'version': 1,
        'puzzle': {'m': m, 'n': n, 'step': step},
        'step_count': 0,
        'history': {'history_index': 0,
                    'snapshots': [{'matrix': matrix, 'bounds': bounds}]},
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _run_case(coords, m, n, step):
    """跑 GUI 同款双入口，返回 (结果类别, 入口, 步数, 秒)。"""
    t0 = time.time()
    # 补缺宏优先：多空位统一驱动在它里面（填洞+补缺混合规划）
    try:
        with redirect_stdout(io.StringIO()):
            res = solve_gap_macro(build_game(coords, m, n), step)
    except Exception as e:  # 引擎崩了也要记录，不许炸整个扫描
        return ('error', 'gap_macro', 0, time.time() - t0, repr(e))
    if not isinstance(res, dict):
        if _replay_solved(coords, m, n, step, res[0], res[1]):
            return ('solved', 'gap_macro', len(res[0]), time.time() - t0,
                    None)
        return ('partial', 'gap_macro', len(res[0]), time.time() - t0,
                '返回动作回放未还原（partial）')
    if res.get('type') == 'fill_partial':
        return ('partial', 'gap_macro', len(res.get('actions', [])),
                time.time() - t0, res.get('reason'))
    # gap_macro 拒绝 → 填洞宏兜底（纯孔洞局面走这里）
    try:
        with redirect_stdout(io.StringIO()):
            res2 = solve_fill_macro(build_game(coords, m, n), step)
    except Exception as e:
        return ('error', 'fill_macro', 0, time.time() - t0, repr(e))
    if not isinstance(res2, dict):
        if _replay_solved(coords, m, n, step, res2[0], res2[1]):
            return ('solved', 'fill_macro', len(res2[0]), time.time() - t0,
                    None)
        return ('partial', 'fill_macro', len(res2[0]), time.time() - t0,
                '返回动作回放未还原（partial）')
    if res2.get('type') == 'fill_partial':
        return ('partial', 'fill_macro', len(res2.get('actions', [])),
                time.time() - t0, res2.get('reason'))
    return ('fail', 'both', 0, time.time() - t0,
            res2.get('reason', res.get('reason')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sizes', default='4x4,5x5,6x6',
                    help='逗号分隔，如 4x4,6x6,6x8')
    ap.add_argument('--steps', default='2')
    ap.add_argument('--voids', default='1,2', help='空位总数列表')
    ap.add_argument('--seeds', type=int, default=2, help='每配置种子数')
    ap.add_argument('--seed0', type=int, default=1)
    ap.add_argument('--full', action='store_true',
                    help='大扫描：尺寸 4x4~8x8、空位 1~3、种子 3')
    args = ap.parse_args()

    if args.full:
        sizes, steps = ['4x4', '5x5', '6x6', '6x8', '8x8', '8x6'], ['2']
        voids, seeds = [1, 2, 3], 3
    else:
        sizes = [s.strip() for s in args.sizes.split(',') if s.strip()]
        steps = [s.strip() for s in args.steps.split(',') if s.strip()]
        voids = [int(v) for v in args.voids.split(',') if v.strip()]
        seeds = args.seeds

    cases = []
    for size in sizes:
        m, n = (int(x) for x in size.split('x'))
        for step in steps:
            step = int(step)
            for v in voids:
                # 空位拆分：全洞 / 洞缺混合 / 全缺（孔洞=内部空腔，缺口=边缘）
                splits = {(v, 0), (0, v)}
                for k in range(1, v):
                    splits.add((k, v - k))
                for nh, nd in sorted(splits):
                    for seed in range(args.seed0, args.seed0 + seeds):
                        cases.append((m, n, step, nh, nd, seed))

    print('共 %d 个配置' % len(cases))
    records = []
    t_all = time.time()
    for idx, (m, n, step, nh, nd, seed) in enumerate(cases):
        tag = 'cover-%dx%d-s%d-h%d-d%d-seed%d' % (m, n, step, nh, nd, seed)
        rng = __import__('random').Random(seed * 100003 + m * 97 + n * 13)
        try:
            if nh == 0 and nd == 0:
                coords, _h = generate_random_void(m, n, step, 0, rng=rng)
            else:
                coords, _h = generate_classified(m, n, step, nh, nd, rng=rng)
        except ValueError as e:
            records.append({'tag': tag, 'result': 'gen_fail',
                            'note': str(e)})
            print('[%d/%d] %s 生成失败: %s' % (idx + 1, len(cases), tag, e))
            continue
        kind, entry, nacts, secs, note = _run_case(coords, m, n, step)
        rec = {'tag': tag, 'result': kind, 'entry': entry, 'steps': nacts,
               'secs': round(secs, 1), 'note': note}
        records.append(rec)
        mark = {'solved': '✓', 'partial': '◐', 'fail': '✗',
                'error': '💥', 'gen_fail': '-'}.get(kind, '?')
        print('[%d/%d] %s %s %s %.1fs %s' % (
            idx + 1, len(cases), mark, tag, kind, secs,
            ('%d步' % nacts) if kind == 'solved' else (note or '')))
        if kind in ('fail', 'partial', 'error'):
            _save_archive(coords, m, n, step,
                          os.path.join(FAILS_DIR, tag + '.json'))

    # 汇总
    done = [r for r in records if r['result'] != 'gen_fail']
    n_ok = sum(1 for r in done if r['result'] == 'solved')
    n_pa = sum(1 for r in done if r['result'] == 'partial')
    n_bad = sum(1 for r in done if r['result'] in ('fail', 'error'))
    print('\n===== 覆盖率 %.0f%%（%d/%d 解出，部分 %d，失败 %d，'
          '生成失败 %d，总耗时 %.0fs）====='
          % (100.0 * n_ok / max(1, len(done)), n_ok, len(done), n_pa,
             n_bad, len(records) - len(done), time.time() - t_all))
    for r in done:
        if r['result'] != 'solved':
            print('  %s: %s %s' % (r['tag'], r['result'],
                                   r.get('note') or ''))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, 'coverage_%s.json'
                       % time.strftime('%Y%m%d-%H%M%S'))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'records': records,
                   'summary': {'solved': n_ok, 'partial': n_pa,
                               'fail': n_bad, 'total': len(done)}},
                  f, ensure_ascii=False, indent=1)
    print('明细 → %s' % out)
    print('失败盘面 → %s' % FAILS_DIR)


if __name__ == '__main__':
    main()
