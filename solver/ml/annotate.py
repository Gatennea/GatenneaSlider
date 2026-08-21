# -*- coding: utf-8 -*-
"""
子目標標註：為每個狀態計算「到最近高入度瓶頸的距離」

算法：
    狀態圖按 BFS 距離排序後構成 DAG（正向移動只會減少距離）。
    從目標（距離 0）出發，逐層計算：
        if 當前狀態是瓶頸:  distance_to_bottleneck = 0
        else:               distance_to_bottleneck = 1 + min(所有正鄰居的 distance_to_bottleneck)

輸出（追加到 states.pkl 同目錄）：
    states_annotated.pkl  — 在原有字段基礎上增加：
        is_bottleneck       : bool
        in_degree           : int
        dist_to_bottleneck  : int   (0 表示自身是瓶頸)
    bottleneck_stats.json  — 瓶頸統計

瓶頸定義：in_degree >= THRESHOLD（可配置，默認取全部分佈的 95 分位數附近）

運行：
    D:\python\python.exe -m solver.annotate_bottlenecks [m n step] [--threshold N]
    默認 m=4 n=4 step=2，threshold 自動計算（in_degree >= top_N_states 或 手動指定）
"""

import os
import sys
import pickle
import json
import time
from collections import defaultdict, Counter
from multiprocessing import Pool, cpu_count

from solver import table_core as tc

# ---------------------------------------------------------------------------
# 路徑
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
TRAINING_DIR = os.path.join(DATA_DIR, 'training')
NUM_WORKERS = min(12, cpu_count())

# 子進程全局變量
_GLOBAL_DIST = None
_GLOBAL_BOTTLENECKS = None
_GLOBAL_DIST_TO_BOTTLENECK = None  # 已計算的結果（距離更小的狀態）
_GLOBAL_STEP = None
_GLOBAL_TOTAL = None


def _init_worker(dist_table, bottleneck_set, dist_to_bn, step, total):
    global _GLOBAL_DIST, _GLOBAL_BOTTLENECKS, _GLOBAL_DIST_TO_BOTTLENECK
    global _GLOBAL_STEP, _GLOBAL_TOTAL
    _GLOBAL_DIST = dist_table
    _GLOBAL_BOTTLENECKS = bottleneck_set
    _GLOBAL_DIST_TO_BOTTLENECK = dist_to_bn
    _GLOBAL_STEP = step
    _GLOBAL_TOTAL = total


def _compute_one(args):
    """計算單個狀態的 dist_to_bottleneck。
    依賴 _GLOBAL_DIST_TO_BOTTLENECK（所有距離更小的狀態已完成計算）。

    args: (hash, distance_val)
    返回: (hash, dist_to_bottleneck) 或 (None, error_msg)
    """
    global _GLOBAL_DIST, _GLOBAL_BOTTLENECKS, _GLOBAL_DIST_TO_BOTTLENECK
    global _GLOBAL_STEP, _GLOBAL_TOTAL
    h, dist_val = args

    try:
        if h in _GLOBAL_BOTTLENECKS:
            return h, 0

        coords = tc.int_to_coords(h, _GLOBAL_TOTAL)
        # 归一到原点
        rs = [r for r, _ in coords]
        cs = [c for _, c in coords]
        mr, mc = min(rs), min(cs)
        norm = frozenset((r - mr, c - mc) for r, c in coords)

        # 枚举【所有】正向邻居（不限於 dist-1）
        nbrs_with_actions = tc.forward_neighbors_with_actions(
            norm, _GLOBAL_STEP, _GLOBAL_TOTAL
        )

        best = None
        for nb_hash, _action in nbrs_with_actions:
            if nb_hash in _GLOBAL_DIST_TO_BOTTLENECK:
                d = _GLOBAL_DIST_TO_BOTTLENECK[nb_hash]
                if best is None or d < best:
                    best = d
            # nb_hash 若不在 GLOBAL_DIST_TO_BOTTLENECK 中，說明它不在表內（不應發生）

        if best is None:
            # 沒有合法正向鄰居，或全部鄰居都未標註（不應發生，除非是最遠端狀態且無瓶頸可達）
            # fallback: 設置一個很大的值
            return h, 999
        return h, best + 1
    except Exception as e:
        return None, f"hash={h} err={e}"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def annotate(m=4, n=4, step=2, threshold=None):
    total_cells = m * n
    training_dir = os.path.join(TRAINING_DIR, f'{m}_{n}_{step}')

    states_path = os.path.join(training_dir, 'states.pkl')
    in_deg_path = os.path.join(training_dir, 'in_degree.pkl')

    if not os.path.exists(states_path):
        print(f"錯誤: 找不到 {states_path}，請先運行 export_training_data.py")
        sys.exit(1)
    if not os.path.exists(in_deg_path):
        print(f"錯誤: 找不到 {in_deg_path}，請先運行 export_training_data.py")
        sys.exit(1)

    # 1. 加載數據
    print(f"加載 states.pkl ...")
    t0 = time.time()
    with open(states_path, 'rb') as f:
        states = pickle.load(f)
    print(f"  {len(states):,} 狀態，耗時 {time.time() - t0:.1f}s")

    print(f"加載 in_degree.pkl ...")
    with open(in_deg_path, 'rb') as f:
        in_degree = pickle.load(f)

    # 2. 確定瓶頸閾值
    in_deg_values = list(in_degree.values())
    in_deg_sorted = sorted(in_deg_values)

    if threshold is None:
        # 自動：取 95 分位數，但至少 >= 10
        p95_idx = int(len(in_deg_sorted) * 0.95)
        threshold = max(10, in_deg_sorted[p95_idx])
    print(f"瓶頸閾值: in_degree >= {threshold}")

    bottleneck_set = {h for h, cnt in in_degree.items() if cnt >= threshold}
    print(f"瓶頸狀態數: {len(bottleneck_set):,} / {len(in_degree):,} "
          f"({100*len(bottleneck_set)/len(in_degree):.1f}%)")

    # 3. 按 BFS 距離分組
    by_dist = defaultdict(list)
    for s in states:
        by_dist[s['distance']].append(s)
    max_dist = max(by_dist.keys())
    print(f"最大距離: {max_dist}，共 {len(by_dist)} 層")

    # 4. 逐層計算 dist_to_bottleneck（從距離 0 開始）
    #    利用 DAG 特性：距離 d 的狀態的正鄰居距離 <= d-1，都已經計算過
    dist_to_bn = {}  # hash → distance_to_bottleneck
    all_tasks_total = sum(len(v) for v in by_dist.values())

    print(f"\n逐層計算 dist_to_bottleneck ...")
    t_work = time.time()
    processed = 0

    for d in range(max_dist + 1):
        layer = by_dist[d]
        if not layer:
            continue

        tasks = [(s['hash'], s['distance']) for s in layer]
        layer_size = len(tasks)

        # 距離 0 的狀態只有一個，直接計算
        if d == 0:
            for h, _ in tasks:
                dist_to_bn[h] = 0 if h in bottleneck_set else 999
            processed += layer_size
            continue

        with Pool(
            processes=NUM_WORKERS,
            initializer=_init_worker,
            initargs=(None, bottleneck_set, dist_to_bn, step, total_cells),
            maxtasksperchild=500,
        ) as pool:
            batch_results = pool.map(_compute_one, tasks, chunksize=max(1, layer_size // NUM_WORKERS))

        for result in batch_results:
            if result is None:
                continue
            h, bn_dist = result
            if h is not None:
                dist_to_bn[h] = bn_dist

        processed += layer_size
        elapsed = time.time() - t_work
        rate = processed / elapsed if elapsed > 0 else 0
        remaining = all_tasks_total - processed
        eta = remaining / rate if rate > 0 else 0
        bn_in_layer = sum(1 for s in layer if s['hash'] in bottleneck_set)
        print(f"  距離 {d:2d}: {layer_size:>8,} 狀態  "
              f"({bn_in_layer} 瓶頸)  "
              f"總進度 {processed:,}/{all_tasks_total:,}  "
              f"速率 {rate:.0f}/s  ETA {eta:.0f}s",
              flush=True)

    elapsed = time.time() - t_work
    print(f"計算完成，耗時 {elapsed:.0f}s")

    # 5. 合併到 states 中
    print("合併標註...")
    hash_to_state = {s['hash']: s for s in states}
    for h, bn_dist in dist_to_bn.items():
        if h in hash_to_state:
            entry = hash_to_state[h]
            entry['in_degree'] = in_degree.get(h, 0)
            entry['is_bottleneck'] = h in bottleneck_set
            entry['dist_to_bottleneck'] = bn_dist

    # 6. 保存
    print("保存 states_annotated.pkl ...")
    annotated_path = os.path.join(training_dir, 'states_annotated.pkl')
    with open(annotated_path, 'wb') as f:
        pickle.dump(states, f, protocol=pickle.HIGHEST_PROTOCOL)
    annotated_mb = os.path.getsize(annotated_path) / 1024 / 1024
    print(f"  → {annotated_path} ({annotated_mb:.1f} MB)")

    # 7. 瓶頸統計
    bottleneck_states = [s for s in states if s.get('is_bottleneck')]
    bn_dist_dist = Counter(s.get('dist_to_bottleneck', -1) for s in states)
    bn_by_bfs_dist = Counter(s['distance'] for s in bottleneck_states)
    bn_by_dist_to_bn = Counter(s.get('dist_to_bottleneck', -1) for s in bottleneck_states)

    bn_stats = {
        'meta': {'m': m, 'n': n, 'step': step, 'threshold': threshold},
        'total_states': len(states),
        'bottleneck_count': len(bottleneck_set),
        'bottleneck_pct': 100 * len(bottleneck_set) / len(states) if states else 0,
        'bottlenecks_by_bfs_distance': dict(sorted(bn_by_bfs_dist.items())),
        'dist_to_bottleneck_distribution': dict(sorted(bn_dist_dist.items())),
        'sample_annotated': [
            {
                'hash': s['hash'],
                'distance': s['distance'],
                'in_degree': s.get('in_degree', 0),
                'is_bottleneck': s.get('is_bottleneck', False),
                'dist_to_bottleneck': s.get('dist_to_bottleneck', -1),
                'optimal_action_count': s.get('optimal_action_count', 0),
            }
            for s in states[:10]
        ],
    }

    bn_stats_path = os.path.join(training_dir, 'bottleneck_stats.json')
    with open(bn_stats_path, 'w', encoding='utf-8') as f:
        json.dump(bn_stats, f, ensure_ascii=False, indent=2)
    print(f"  → {bn_stats_path}")

    # 8. 摘要
    print(f"\n{'='*60}")
    print(f"子目標標註完成！")
    print(f"  瓶頸數: {len(bottleneck_set):,} (in_degree >= {threshold})")
    print(f"  max dist_to_bottleneck: {max(v for v in dist_to_bn.values() if v < 999)}")
    print(f"\n  瓶頸在各 BFS 距離層的分布:")
    for d in sorted(bn_by_bfs_dist.keys()):
        total_in_layer = len(by_dist[d])
        print(f"    距離 {d:2d}: {bn_by_bfs_dist[d]:5,} / {total_in_layer:6,}  "
              f"({100*bn_by_bfs_dist[d]/total_in_layer:.1f}%)")
    print(f"\n  全體狀態的 dist_to_bottleneck 分布（頭部):")
    for k, v in sorted(bn_dist_dist.items())[:15]:
        bar = '█' * min(v // max(1, len(states) // 50), 40)
        print(f"    dist={k:3d}: {v:8,}  {bar}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    m, n, step = 4, 4, 2
    threshold = None

    i = 0
    while i < len(args):
        if args[i] == '--threshold' and i + 1 < len(args):
            threshold = int(args[i + 1])
            i += 2
        elif i == 0:
            m = int(args[i])
            i += 1
        elif i == 1:
            n = int(args[i])
            i += 1
        elif i == 2:
            step = int(args[i])
            i += 1
        else:
            i += 1

    annotate(m, n, step, threshold)


if __name__ == '__main__':
    main()
