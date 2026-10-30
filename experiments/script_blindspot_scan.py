# -*- coding: utf-8 -*-
"""盲区覆盖 + 解长质量批量扫描（blindspot scan，2026-10-16）。

按 `docs/solver/批量实验设计_盲区与解长.md` 执行：对每个盘面跑 auto_solve，
按返回协议分拣（全解 / fill_partial / fill_fail / 超时 / 异常），失败样本
落成**标准游戏存档**（save/blindspot/，可在游戏里 Ctrl+O 打开复盘），
元数据逐局追加 results/blindspot/rounds.jsonl。

数据源两种：
  --src corpus（默认）：harness.gen_state 正向随机游走，必然可解，seed 可复现；
  --src save：save/**/*.json 回放 history 得中段局面（不保证可解，真实失败源）。

用法示例：
  python -u experiments/script_blindspot_scan.py --m 4 --n 4 --step 2 --seeds 15 --budget 180
  python -u experiments/script_blindspot_scan.py --m 5 --n 5 --step 2 --seeds 6 --start 3
  python -u experiments/script_blindspot_scan.py --src save --files 10 --budget 180

分块执行（绕本机后台 10~15 分钟截断）：--start/--seeds（或 --start-file/--files）
参数化；每局立即落盘；断点续跑（已跑过的 seed 组合自动跳过）。
"""

import argparse
import glob
import json
import os
import random
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game import SliderMatrix  # noqa: E402
from experiments.harness import gen_state, load_game  # noqa: E402
from solver.ml.fill_macro import build_game, _replay_apply  # noqa: E402
from solver.auto_solver import auto_solve, _phi_of  # noqa: E402
from solver.deadend_guard import has_deadend_guard, is_deadend  # noqa: E402
from history import GameHistory  # noqa: E402

RESULTS_DIR = os.path.join(ROOT, 'experiments', 'results', 'blindspot')
ROUNDS_PATH = os.path.join(RESULTS_DIR, 'rounds.jsonl')
BLINDSPOT_SAVE_DIR = os.path.join(ROOT, 'save', 'blindspot')


# ---------- 存档构造（协议同 gui/file_ops.py::_build_save_data 普通格式路径） ----------

def _compute_checksum(data):
    """与 gui.file_ops._compute_checksum 同算法：puzzle+history 序列化 SHA256
    （排除 checksum 自身）。file_ops 模块 import pygame，headless 不可用，
    故内联复制（算法 3 行，无逻辑，随上游变更需同步）。"""
    import hashlib
    payload = {k: v for k, v in data.items() if k != 'checksum'}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _snap(game):
    """单快照（matrix+bounds），字段同 history.GameHistory.save_snapshot 产物。"""
    game.update_matrix()
    b = game.matrix_bounds
    return {'matrix': [list(row) for row in game.matrix],
            'bounds': {'min_row': b['min_row'], 'max_row': b['max_row'],
                       'min_col': b['min_col'], 'max_col': b['max_col']}}


def _replay_steps(coords0, actions, reps, m, n, step):
    """逐步回放动作链，返回每步的 game 快照列表（含初始态）。

    回放口径同 solver.auto_solver._end_state：acts 四元组 + reps 平行，
    统一补 5 元组（None 交引擎按侧首块兜底）。任一步非法返回 None。
    """
    if not actions:
        return None
    a5 = []
    for i, a in enumerate(actions):
        rep = reps[i] if (reps and i < len(reps) and reps[i]) else None
        a5.append(tuple(a) + ((tuple(rep),) if rep else (None,)))
    g = build_game(coords0, m, n)
    snaps = [_snap(g)]
    for a in a5:
        if not _replay_apply(g, [a], m, n, step):
            return None
        snaps.append(_snap(g))
    return snaps


def _write_save(path, snaps, history_index, m, n, step, step_count):
    """按 v1 普通方形格式组装并写盘（与手动存档同构，load 路径可直接读）。"""
    data = {
        'version': 1,
        'puzzle': {'m': m, 'n': n, 'step': step},
        'step_count': step_count,
        'history': {'history_index': history_index,
                    'snapshots': [{'matrix': s['matrix'],
                                   'bounds': s['bounds']} for s in snaps]},
    }
    data['checksum'] = _compute_checksum(data)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def save_failure_sample(name, kind, coords0, m, n, step, actions=None, reps=None):
    """失败样本存档。返回 (文件名, 快照数)。

    kind='partial'：回放动作链，每步一快照，停在历史最优终态（设计 §3.1）；
    kind='fail'：双快照停原地（复原态 + 初始盘面），= 求解器零进展（§3.2）。
    """
    path = os.path.join(BLINDSPOT_SAVE_DIR, name + '.json')
    if kind == 'partial':
        snaps = _replay_steps(coords0, actions, reps, m, n, step)
        if snaps is None:
            # 回放失败（理论仅当协议不一致）——降级双快照，保证样本不丢
            g = build_game(coords0, m, n)
            snaps = [_snap(g), _snap(g)]
            _write_save(path, snaps, 1, m, n, step, 0)
            return os.path.basename(path), len(snaps), 'degraded'
        _write_save(path, snaps, len(snaps) - 1, m, n, step,
                    len(snaps) - 1)
        return os.path.basename(path), len(snaps), 'ok'
    g = build_game(coords0, m, n)
    snaps = [_snap(g), _snap(g)]
    _write_save(path, snaps, 1, m, n, step, 0)
    return os.path.basename(path), len(snaps), 'ok'


# ---------- 语料 ----------

def save_mid_states(m, n, step, limit):
    """从 save/**/*.json 回放 history，取 (m,n,step) 匹配的中段局面。

    取 history_index 当前局面（非 snapshots[0] 初始态）；每档最多 limit 个，
    按文件名字典序保可复现。
    """
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'save', '**', '*.json'),
                              recursive=True)):
        try:
            d = json.load(open(f, encoding='utf-8'))
            p = d.get('puzzle', {})
            if (p.get('m'), p.get('n'), p.get('step')) != (m, n, step):
                continue
            h = d.get('history', {})
            idx = h.get('history_index', 0)
            snap = h['snapshots'][idx]
            b = snap['bounds']
            coords = frozenset((r + b['min_row'], c + b['min_col'])
                               for r, row in enumerate(snap['matrix'])
                               for c, v in enumerate(row) if v)
            out.append({'coords': coords, 'src_file': os.path.relpath(f, ROOT),
                        'src': 'save_mid', 'seed': None})
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out


# ---------- 主流程 ----------

def run_one(coords0, m, n, step, budget):
    """跑一局，返回结果 dict（不含存档信息）。"""
    g = build_game(coords0, m, n)
    stages = []
    t0 = time.time()

    def cb(s):
        stages.append(s)

    def cc():
        return (time.time() - t0) >= budget

    err = None
    try:
        r = auto_solve(g, step, stage_cb=cb, time_budget=budget,
                       cancel_check=cc)
    except Exception:
        r = None
        err = traceback.format_exc()
    dt = time.time() - t0

    out = {'dt': round(dt, 2), 'err': err, 'stages': stages,
           'holes': sum(1 for row in g.matrix for v in row if not v)
                    if g.matrix else None}
    if err is not None:
        out['outcome'] = 'error'
    elif r is False or r is None:
        out['outcome'] = 'timeout'
    elif isinstance(r, tuple):
        out['outcome'] = 'solved'
        out['n_actions'] = len(r[0])
        out['solve_layer'] = (stages[-1]['label'] if stages
                              and stages[-1].get('solved') else None)
        out['end_phi'] = 0
    elif isinstance(r, dict) and r.get('type') == 'fill_partial':
        out['outcome'] = 'partial'
        out['score'] = r.get('score')
        out['phi'] = r.get('phi')
        out['actions'] = r.get('actions')
        out['rep_cells'] = r.get('rep_cells')
        out['n_actions'] = len(r.get('actions') or [])
    elif isinstance(r, dict) and r.get('type') == 'fill_fail':
        out['outcome'] = 'fail'
    else:
        out['outcome'] = 'unknown:%s' % type(r).__name__
    # 死局标注（当前仅 (4,4,2) 有黑名单真值）
    if has_deadend_guard(m, n, step):
        try:
            out['deadend'] = is_deadend(m, n, step, coords0)
        except Exception:
            out['deadend'] = 'unknown'
    else:
        out['deadend'] = 'unknown'
    return out


def done_keys():
    """已跑过的 (src, m, n, step, seed) 组合（断点续跑）。"""
    keys = set()
    if not os.path.exists(ROUNDS_PATH):
        return keys
    for line in open(ROUNDS_PATH, encoding='utf-8'):
        try:
            r = json.loads(line)
            keys.add((r.get('src'), r.get('m'), r.get('n'), r.get('step'),
                      r.get('seed'), r.get('src_file')))
        except Exception:
            continue
    return keys


def append_round(rec):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(ROUNDS_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        f.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--m', type=int, default=4)
    ap.add_argument('--n', type=int, default=4)
    ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--src', choices=['corpus', 'save'], default='corpus')
    ap.add_argument('--seeds', type=int, default=15, help='corpus 模式局数')
    ap.add_argument('--start', type=int, default=0, help='corpus 起始序号')
    ap.add_argument('--files', type=int, default=10, help='save 模式局数')
    ap.add_argument('--start-file', type=int, default=0)
    ap.add_argument('--budget', type=float, default=180.0, help='单局秒数硬顶')
    ap.add_argument('--wall-cap', type=float, default=540.0,
                    help='本次调用墙钟上限（秒），到点干净退出保数据')
    ap.add_argument('--attempts', type=int, default=140)
    ap.add_argument('--bias', type=float, default=0.8)
    args = ap.parse_args()

    t_start = time.time()
    done = done_keys()

    if args.src == 'save':
        cases = save_mid_states(args.m, args.n, args.step, args.files)
        cases = cases[args.start_file:]
        print('[blindspot] save 模式：%s 共 %d 局可用' %
              ('%dx%d s%d' % (args.m, args.n, args.step), len(cases)),
              flush=True)
    else:
        cases = []
        for k in range(args.start, args.start + args.seeds):
            seed = 1000 + k
            cases.append({'seed': seed, 'src': 'corpus', 'src_file': None})

    ran = skipped = 0
    for c in cases:
        if time.time() - t_start >= args.wall_cap:
            print('[blindspot] 墙钟到点，剩余下块继续', flush=True)
            break
        key = (c['src'], args.m, args.n, args.step, c.get('seed'),
               c.get('src_file'))
        if key in done:
            skipped += 1
            continue
        if c['src'] == 'corpus':
            snap = gen_state(args.m, args.n, args.step, c['seed'],
                             attempts=args.attempts, bias=args.bias)
            coords0 = frozenset(tuple(x) for x in snap['coords'])
        else:
            coords0 = c['coords']
        r = run_one(coords0, args.m, args.n, args.step, args.budget)
        rec = {'m': args.m, 'n': args.n, 'step': args.step,
               'src': c['src'], 'seed': c.get('seed'),
               'src_file': c.get('src_file'),
               'outcome': r['outcome'], 'dt': r['dt'],
               'holes': r['holes'], 'deadend': r['deadend'],
               'err': r['err'],
               'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
        if 'n_actions' in r:
            rec['n_actions'] = r['n_actions']
        if 'solve_layer' in r:
            rec['solve_layer'] = r['solve_layer']
        if 'score' in r:
            rec['score'] = r['score']
        if 'phi' in r:
            rec['phi'] = r['phi']
        # 失败样本存档（partial/fail/timeout 都是「求解器没解开」的盲区样本；
        # timeout 时 auto_solve 返回 False 无动作链 → 双快照停原地）
        if r['outcome'] in ('partial', 'fail', 'timeout'):
            name = 'blindspot-%d-%d-%d-%s' % (
                args.step, args.m, args.n, c.get('seed')
                if c.get('seed') is not None else
                os.path.splitext(os.path.basename(c['src_file'] or 'x'))[0])
            kind = 'partial' if r['outcome'] == 'partial' else 'fail'
            fn, nsnap, status = save_failure_sample(
                name, kind, coords0, args.m, args.n, args.step,
                r.get('actions'), r.get('rep_cells'))
            rec['save_file'] = fn
            rec['save_snaps'] = nsnap
            rec['save_status'] = status
        # stages 摘要（不入库太大，只留段标签+分数+耗时）
        rec['stage_brief'] = [
            {'label': s['label'], 'score': round(s['score'], 3),
             'solved': bool(s.get('solved'))} for s in r['stages']]
        append_round(rec)
        ran += 1
        tag = rec.get('save_file') or ''
        print('[blindspot %dx%d s%d] seed=%s %-8s %6.1fs %s %s' %
              (args.m, args.n, args.step, c.get('seed'), r['outcome'],
               r['dt'],
               ('%d步' % r['n_actions']) if 'n_actions' in r else '',
               tag), flush=True)
    print('[done] 本次 %d 局 / 跳过已完成 %d → %s' %
          (ran, skipped, ROUNDS_PATH), flush=True)


if __name__ == '__main__':
    main()
