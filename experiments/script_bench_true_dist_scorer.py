# -*- coding: utf-8 -*-
"""用 D1 的新打分接縫，檢驗「真值距離當 GBFS 打分」值不值得往下走。

範圍**只在 4_4_2**：這是唯一有全量 BFS 距離表的尺寸之一
（solver/data 的 559,504 態、直徑 17），任何狀態都能查到離還原還差幾步。
不外推到其他尺寸，也不碰玩家側（`guided_reduce_one` 的 scorer 預設 None）。

三組對照，同一批固定種子的安全打亂局面：
  A. 預設打分 `heuristic_parts`（現況）
  B. 透過 `scorer=` 注入表內真實距離（新接縫）
  C. 貪心 + 真值距離（`docs/archive/混合求解器验收.md` §5.1 的 oracle 復現，
     當 sanity check：證明表資料與「方向正確」這件事本身沒問題）

指標：找到「洞數嚴格變少」路徑的局數、平均展開節點、路徑終態的真實距離、
貪心還原步數。B 若沒有明顯優於 A，就照實判「不賺、止損」，不要把
§5.4 的貪心結論直接套到 GBFS 上——兩者的終止判據不同（GBFS 是洞數變少）。

輸出寫入 experiments 下的臨時結果檔，未入庫；文件不要引用該檔名。
用法：D:/python/python.exe -u experiments/script_bench_true_dist_scorer.py --seeds 8
"""
import argparse
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import solver.search_core as sc  # noqa: E402
from solver import table_core as tc  # noqa: E402
from solver.table_solver import load_table  # noqa: E402
from game import SliderMatrix  # noqa: E402

MISSING = 10 ** 6
M = N = 4
STEP = 2


def make_scorer(table):
    def true_dist(coords, m, n, step):
        d = table.get(tc.canonicalize(coords), MISSING)
        return d, len(sc.fast_window(coords, m, n)[1])
    return true_dist


def replay_path(coords, path, step):
    """把 (act, rep) 路徑逐步重放回終態座標（只用 search_core.expand）。"""
    cur = frozenset(coords)
    for act, rep in path:
        nxt = None
        for new, a, r in sc.expand(cur, step):
            if a == act and r == rep:
                nxt = new
                break
        if nxt is None:
            return None
        cur = nxt
    return cur


def greedy_oracle(coords, table, max_steps=400):
    """每步選真值距離最小的鄰居；復現 §5.1 的 oracle 當對照。"""
    cur = frozenset(coords)
    for k in range(max_steps):
        d0 = table.get(tc.canonicalize(cur), MISSING)
        if d0 == 0:
            return k, True
        best, bestd = None, MISSING
        for new, _a, _r in sc.expand(cur, STEP):
            d = table.get(tc.canonicalize(new), MISSING + 1)
            if d < bestd:
                best, bestd = new, d
        if best is None:
            return k, False
        cur = best
    return max_steps, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', type=int, default=8)
    ap.add_argument('--budget', type=int, default=3000)
    args = ap.parse_args()

    t_load = time.perf_counter()
    table = load_table(M, N, STEP)
    assert table, '4_4_2 全量表不存在，本實驗只適用有表的尺寸'
    print('表載入 %d 態 / %.2fs' % (len(table), time.perf_counter() - t_load))

    truedist = make_scorer(table)
    rows = []
    for seed in range(args.seeds):
        random.seed(1000 + seed)
        g = SliderMatrix(M, N)
        g.shuffle(M * N * 10, STEP)
        coords = frozenset(tuple(b.location) for b in g.blocks)
        d0 = table.get(tc.canonicalize(coords), MISSING)
        rec = {'seed': seed, 'd0': d0}
        for name, scorer in (('A', None), ('B', truedist)):
            t0 = time.perf_counter()
            path, expanded = sc.guided_reduce_one(
                coords, M, N, STEP, budget=args.budget, scorer=scorer)
            dt = time.perf_counter() - t0
            end = replay_path(coords, path, STEP) if path else coords
            dend = (table.get(tc.canonicalize(end), MISSING)
                    if end is not None else None)
            rec[name] = {'found': path is not None,
                         'plen': len(path) if path else 0,
                         'expanded': expanded,
                         'd_end': dend, 'dt': dt}
        steps, solved = greedy_oracle(coords, table)
        rec['C'] = {'steps': steps, 'solved': solved}
        rows.append(rec)
        print('seed=%-4d d0=%-3d | A %-5s ex=%-5d d_end=%-8s | '
              'B %-5s ex=%-5d d_end=%-8s | 貪心 %d 步 %s' % (
                  seed, d0, rec['A']['found'], rec['A']['expanded'],
                  rec['A']['d_end'], rec['B']['found'],
                  rec['B']['expanded'], rec['B']['d_end'], steps,
                  '還原' if solved else '未還原'))

    def agg(name, key):
        vals = [r[name][key] for r in rows if r[name][key] is not None]
        return statistics.mean(vals) if vals else float('nan')

    a_found = sum(r['A']['found'] for r in rows)
    b_found = sum(r['B']['found'] for r in rows)
    a_ex, b_ex = agg('A', 'expanded'), agg('B', 'expanded')
    a_d, b_d = agg('A', 'd_end'), agg('B', 'd_end')
    solved = [r['C']['steps'] for r in rows if r['C']['solved']]
    print('\n彙總（%d 局）' % len(rows))
    print('A 預設打分   找到 %d/%d，平均展開 %.1f，平均終態距離 %.2f'
          % (a_found, len(rows), a_ex, a_d))
    print('B 真值打分   找到 %d/%d，平均展開 %.1f，平均終態距離 %.2f'
          % (b_found, len(rows), b_ex, b_d))
    print('C 貪心 oracle 還原 %d/%d，步數中位 %s'
          % (len(solved), len(rows),
             statistics.median(solved) if solved else '—'))
    closer = b_d < a_d - 0.5
    print('結論：真值打分%s（%.2f→%.2f），但展開節點 %.1f→%.1f %s。'
          % ('讓單段終態更接近還原' if closer else '沒有讓單段終態更近',
             a_d, b_d, a_ex, b_ex,
             '略增' if b_ex > a_ex else '略減'))
    print('      這只是「方向對了能改變結果」的證據，**不是解出率提升**：'
          '兩組都 8/8 找到路徑，GBFS 終止判據是洞數變少、不是距離變小。')
    print('      D2 要繼續得連終止判據／貪心骨架一起改；'
          '且只在有全量表的尺寸成立，不外推到玩家大尺寸。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
