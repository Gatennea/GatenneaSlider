# -*- coding: utf-8 -*-
"""D5 第一半：全量建表的成本曲線與斷點可信度檢查。

不改 solver/build_table.py，也不動任何已入庫的表檔；只讀 solver/data 的
checkpoint.pkl，用同一份 table_core.predecessors 做「飽和性抽樣」，回答：

  1. 這個斷點是不是完整的？（對已記錄的狀態重新生成前驅，看有沒有漏網）
  2. 若繼續往下建，每層增長多少、耗時多少、按這個速率能不能收斂？
  3. 5_5_3 前沿 = 0 且只有 1278 態，是不是其實已經飽和、只差 final 產物？

⚠️ 2026-11-10 實測答案：**三個斷點都不完整**。各抽 30 態重跑
predecessors，5_5_3 / 5_5_2 第 4 層 / 4_4_1 第 7 層分別抓到
515 / 473 / 171 個未記錄前驅，外推整層漏態約 2.2 萬 / 730 萬 / 1184 萬。
5_5_3 的 frontier=0 是停止時存下的，直接續跑會寫出假全量表。
詳 `docs/solver/求解器優化方向_可行性判據.md` 4.2 節。

反向 BFS 的 dist 是「能到達目標的狀態集合」(cone)。若 cone 完整，
對 dist 內任一個狀態 s 跑 predecessors(s)，結果應全部落在 dist 裡。
抽樣若出現大量新狀態 ⇒ 該斷點是在批次中途存下來的、層不完整，
直接拿 frontier 續跑會漏態、產出假表。

用法：
  D:/python/python.exe -u experiments/script_bench_full_table_cost.py --case 5_5_3 --sample 0
  D:/python/python.exe -u experiments/script_bench_full_table_cost.py --case 4_4_1 --sample 20000
  D:/python/python.exe -u experiments/script_bench_full_table_cost.py --case 5_5_2 --sample 20000
  D:/python/python.exe -u experiments/script_bench_full_table_cost.py --case 5_5_2 --layers 2

--sample 0 表示該層全查。結果寫入 experiments 下的臨時結果檔，未入庫。
"""
import argparse
import collections
import json
import multiprocessing
import os
import pickle
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver import table_core as tc  # noqa: E402

DATA_DIR = os.path.join(ROOT, 'solver', 'data')
WORKERS = min(12, max(2, (os.cpu_count() or 4) - 2))


def _worker(args):
    """模組頂層，Windows spawn 才能 pickle。"""
    h, m, n, step, total = args
    B = set(tc.int_to_coords(h, total))
    return h, list(tc.predecessors(B, m, n, step))


def load_case(case):
    m, n, step = (int(x) for x in case.split('_'))
    path = os.path.join(DATA_DIR, case, 'checkpoint.pkl')
    with open(path, 'rb') as f:
        o = pickle.load(f)
    return (m, n, step), o


def pick_layer(dist, wanted, layer_value=None):
    """wanted=None → 全體；layer_value 指定層；否則取最大 dist 層。"""
    if wanted is None:
        return list(dist)
    if layer_value is not None:
        return [h for h, d in dist.items() if d == layer_value]
    maxd = max(dist.values())
    return [h for h, d in dist.items() if d == maxd]


def run(args):
    (m, n, step), o = load_case(args.case)
    dist = o['dist']
    total = m * n
    layers = collections.Counter(dist.values())
    print('CASE %s  m=%d n=%d step=%d  total=%d' % (args.case, m, n, step, len(dist)))
    print('  layer counts:', dict(sorted(layers.items())))
    print('  frontier=%d current_dist=%d' % (len(o['frontier']), o['current_dist']))

    workers = args.workers or WORKERS
    pool = multiprocessing.Pool(processes=workers)
    try:
        cur = dist
        for lay in range(1, args.layers + 1):
            # 第 1 層用斷點的最大 dist 層（或全體）；之後用上一層新發現的狀態
            if lay == 1:
                seeds = pick_layer(cur, args.layer, args.layer_value)
            else:
                seeds = list(new_hashes)
            if not seeds:
                print('  layer %d: 無可擴展狀態 → 飽和' % lay)
                break
            total_seeds = len(seeds)
            if args.sample and len(seeds) > args.sample:
                random.Random(args.seed).shuffle(seeds)
                seeds = seeds[:args.sample]
                sampled = True
            else:
                sampled = False

            t0 = time.time()
            new_hashes = set()
            seen_preds = 0
            tasks = [(h, m, n, step, total) for h in seeds]
            for _src, preds in pool.imap_unordered(
                    _worker, tasks, chunksize=max(1, len(tasks) // (workers * 4))):
                seen_preds += len(preds)
                for p in preds:
                    if p not in cur:
                        new_hashes.add(p)
            dt = time.time() - t0
            print('  layer %d  seeds=%d/%d%s  preds=%d  新增=%d  耗時=%.1fs  速率=%.0f seeds/s'
                  % (lay, len(seeds), total_seeds, ' (抽樣)' if sampled else '',
                     seen_preds, len(new_hashes), dt, len(seeds) / dt if dt else 0))
            if sampled and new_hashes:
                print('    ⚠️ 抽樣外推：整層約還有 %d 個未記錄前驅 ⇒ 斷點不完整，'
                      '直接續跑會產出假表'
                      % round(len(new_hashes) * total_seeds / len(seeds)))
            if args.stop_new and len(new_hashes) > args.stop_new:
                print('  ⚠️ 單層新增超過 --stop-new=%d，判定「層未收斂、續建不可行」'
                      % args.stop_new)
                break
            if lay < args.layers:
                # 不寫回 dist（避免污染），只把新態當下一層輸入
                cur = dict(cur)
                for h in new_hashes:
                    cur[h] = lay
    finally:
        pool.close()
        pool.join()

    return {
        'case': args.case, 'm': m, 'n': n, 'step': step,
        'total_states': len(dist), 'layer_counts': dict(sorted(layers.items())),
        'frontier': len(o['frontier']),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', default='5_5_3')
    ap.add_argument('--sample', type=int, default=0, help='0 = 全查')
    ap.add_argument('--layers', type=int, default=1)
    ap.add_argument('--stop-new', type=int, default=0)
    ap.add_argument('--seed', type=int, default=20261110)
    ap.add_argument('--workers', type=int, default=0)
    ap.add_argument('--layer', default='max', choices=['max', 'all'])
    ap.add_argument('--layer-value', type=int, default=None)
    ap.add_argument('--out', default='')
    args = ap.parse_args()
    if args.layer == 'all':
        args.layer = None
    summary = run(args)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
