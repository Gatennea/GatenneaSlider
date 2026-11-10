# -*- coding: utf-8 -*-
r"""盲区局「不寫公式」對照實驗（2026-11-10，續）。

問題：`experiments/results/blindspot/rounds.jsonl` 的 8 個 timeout 局，
原始 `script_blindspot_scan.py` 用 `time_budget=180` 仍超時，被歸因為
「公式生成器寫不出對應套路」（D3 待辦）。本腳本檢驗：

  這些局是不是能靠「改預算分配」直接解開，而不用寫任何新公式？

配置（全部走 `auto_solve` 既有可注入接縫，不改一行求解器）：
  A  baseline    復刻 run_one：time_budget=budget，無 total/stage/route
  C  +total+route  total_budget=budget 且 route_fn=False（补缺宏後跑）
  E  +total       只加 total_budget=budget，route 維持預設（holes>=3 补缺宏先）

判據（開跑前寫死，不事後挑）：
  · 某配置比 baseline 多 >=1 定稿段或直接 solved ⇒ 該配置有可撿收益；
  · 全配置 0 段且未解 ⇒ 瓶頸確實在機構／公式層。

存檔讀法同 `script_blindspot_scan.py::save_mid_states`：
取 history.snapshots[history_index] 的 matrix+bounds 還原 coords。

用法：
  python -u experiments/script_bench_blindspot_params.py --budget 40
"""
import argparse
import glob
import json
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver.ml.fill_macro import build_game  # noqa: E402
from solver.auto_solver import auto_solve  # noqa: E402

SAVE_DIR = os.path.join(ROOT, 'save', 'blindspot')
ROUNDS = os.path.join(ROOT, 'experiments', 'results', 'blindspot', 'rounds.jsonl')


def load_timeout_cases():
    rows = [json.loads(l) for l in open(ROUNDS, encoding='utf-8') if l.strip()]
    out = []
    for r in rows:
        if r.get('outcome') != 'timeout':
            continue
        sf = r.get('save_file')
        p = os.path.join(SAVE_DIR, sf) if sf else None
        if not p or not os.path.exists(p):
            continue
        out.append((p, r['m'], r['n'], r['step'], sf))
    return out


def load_case(path):
    d = json.load(open(path, encoding='utf-8'))
    p = d['puzzle']
    h = d['history']
    snap = h['snapshots'][h.get('history_index', 0)]
    b = snap['bounds']
    coords = frozenset((r + b['min_row'], c + b['min_col'])
                       for r, row in enumerate(snap['matrix'])
                       for c, v in enumerate(row) if v)
    return coords, p['m'], p['n'], p['step']


def run(coords, m, n, step, budget, mode):
    stages = []
    t0 = time.time()

    def cb(s):
        stages.append(s)

    def cc():
        return (time.time() - t0) >= budget

    kw = {'stage_cb': cb, 'time_budget': budget, 'cancel_check': cc}
    if mode == 'C':
        kw['route_fn'] = lambda holes, cs, mm, nn, st: False
        kw['total_budget'] = budget
    elif mode == 'E':
        kw['total_budget'] = budget
    err = None
    try:
        r = auto_solve(build_game(coords, m, n), step, **kw)
    except Exception:
        r = None
        err = traceback.format_exc(limit=2)
    dt = time.time() - t0
    if err is not None:
        out = 'error'
    elif isinstance(r, tuple):
        out = 'solved'
    elif isinstance(r, dict) and r.get('type') == 'fill_partial':
        out = 'partial'
    elif r is False or r is None:
        out = 'timeout'
    else:
        out = 'fail'
    # 候选级诊断：按 stage 標籤前綴統計各候选产出的段数
    gaps = sum(1 for s in stages if '补缺宏' in s.get('label', ''))
    hyb = sum(1 for s in stages if '混合' in s.get('label', ''))
    return out, len(stages), dt, gaps, hyb, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget', type=float, default=40.0)
    ap.add_argument('--modes', default='ACE')
    args = ap.parse_args()

    cases = load_timeout_cases()
    modes = list(args.modes)
    print('盲區局參數對照｜budget=%.0fs｜%d 局 × %d 配置' %
          (args.budget, len(cases), len(modes)), flush=True)
    print('判據：某配置比 baseline 多段或 solved ⇒ 有可撿收益。',
          flush=True)

    verdict = {}
    recovered = 0
    for path, m, n, step, sf in cases:
        coords, mm, nn, st = load_case(path)
        print('\n=== %s｜%dx%d s%d｜方塊 %d ===' %
              (sf, m, n, step, len(coords)), flush=True)
        base_seg = None
        mode_res = {}
        for mode in modes:
            out, seg, dt, gaps, hyb, err = run(
                coords, m, n, step, args.budget, mode)
            if base_seg is None:
                base_seg = seg
            better = (seg > base_seg) or out == 'solved'
            verdict.setdefault(mode, []).append(better)
            if mode == 'A' and out == 'solved':
                recovered += 1
            mode_res[mode] = (out, seg, dt, gaps, hyb)
            tag = '  <== 優於 baseline' if better else ''
            print('  %s %-8s 段=%d(补缺%d/混合%d) %.1fs%s' %
                  (mode, out, seg, gaps, hyb, dt, tag), flush=True)
            if err:
                print(err[:400], flush=True)
        # 任意非 A 配置解開即算「可撿收益」
        if any(mode_res[k][0] == 'solved' for k in modes if k != 'A'):
            recovered += 1

    print('\n[判據結算]', flush=True)
    for mode in modes:
        gains = verdict.get(mode, [])
        if mode != 'A':
            print('  %s：%d/%d 局優於 baseline' %
                  (mode, sum(gains), len(gains)), flush=True)
    print('結論：%s' %
          ('參數層有可撿收益（詳上），瓶頸不在公式生成器'
           if recovered else '參數層止損，瓶頸在機構／公式層'),
          flush=True)


if __name__ == '__main__':
    main()
