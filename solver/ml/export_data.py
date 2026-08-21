# -*- coding: utf-8 -*-
"""
导出 BFS 建表数据为训练数据集

功能：
    1. 从 table.pkl 加载距离表
    2. 对每个状态，枚举【所有】dist-1 邻居的对应动作（全部最短路径）
    3. 计算每个状态的「入度」：有多少 dist+1 状态的最短路径经过它
    4. 输出结构化数据供 AI 训练

输出文件（位于 solver/data/training/{m}_{n}_{step}/）：
    states.pkl       — list[StateEntry]，每个状态包含网格、距离、全部最优动作
    in_degree.pkl    — dict[hash→int]，每个状态的入度
    stats.json       — 统计摘要（分布、入度分位数等）

运行：
    D:\python\python.exe -m solver.export_training_data [m n step]
    默认 m=4 n=4 step=2
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
# 路径
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
TRAINING_DIR = os.path.join(DATA_DIR, 'training')
NUM_WORKERS = min(12, cpu_count())

# 子进程全局变量（通过 initializer 注入，避免每个任务序列化 dist 表）
_GLOBAL_DIST = None
_GLOBAL_STEP = None
_GLOBAL_TOTAL = None


def _init_worker(dist_table, step, total):
    """子进程初始化：接收共享的 dist 字典（每进程仅序列化一次）。"""
    global _GLOBAL_DIST, _GLOBAL_STEP, _GLOBAL_TOTAL
    _GLOBAL_DIST = dist_table
    _GLOBAL_STEP = step
    _GLOBAL_TOTAL = total


def _process_one_task(args):
    """处理单个状态，使用全局 dist 表过滤。

    args: (hash, distance_val)
    返回: (entry, in_degree_delta) 或 (None, error_msg)
    """
    global _GLOBAL_DIST, _GLOBAL_STEP, _GLOBAL_TOTAL
    h, dist_val = args
    try:
        coords = tc.int_to_coords(h, _GLOBAL_TOTAL)

        # 归一化网格
        rs = [r for r, _ in coords]
        cs = [c for _, c in coords]
        mr, mc = min(rs), min(cs)
        norm = [(r - mr, c - mc) for r, c in coords]
        max_r = max(r for r, _ in norm)
        max_c = max(c for _, c in norm)

        flat_grid = []
        for r in range(max_r + 1):
            for c in range(max_c + 1):
                flat_grid.append(1 if (r, c) in norm else 0)

        # 枚举正向邻居
        fset = frozenset(norm)
        nbrs_with_actions = tc.forward_neighbors_with_actions(
            fset, _GLOBAL_STEP, _GLOBAL_TOTAL
        )

        # 过滤：只保留 dist-1 的邻居
        optimal_actions = []
        in_degree_delta = {}  # neighbor_hash → 贡献次数
        for nb_hash, action in nbrs_with_actions:
            nb_dist = _GLOBAL_DIST.get(nb_hash)
            if nb_dist is not None and nb_dist == dist_val - 1:
                optimal_actions.append({
                    'gap_type': action[0],
                    'gap_line': action[1],
                    'side': action[2],
                    'move_dir': action[3],
                })
                in_degree_delta[nb_hash] = in_degree_delta.get(nb_hash, 0) + 1

        entry = {
            'hash': h,
            'distance': dist_val,
            'grid_rows': max_r + 1,
            'grid_cols': max_c + 1,
            'flat_grid': flat_grid,
            'optimal_action_count': len(optimal_actions),
            'optimal_actions': optimal_actions,
        }
        return entry, in_degree_delta
    except Exception as e:
        return None, f"hash={h} err={e}"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def export(m=4, n=4, step=2):
    total_cells = m * n
    table_path = os.path.join(DATA_DIR, f'{m}_{n}_{step}', 'table.pkl')
    if not os.path.exists(table_path):
        print(f"错误: 找不到 {table_path}，请先建表。")
        sys.exit(1)

    out_dir = os.path.join(TRAINING_DIR, f'{m}_{n}_{step}')
    os.makedirs(out_dir, exist_ok=True)

    # 1. 加载距离表
    print(f"加载表: {table_path}")
    t0 = time.time()
    with open(table_path, 'rb') as f:
        dist = pickle.load(f)
    print(f"  共 {len(dist):,} 状态，加载耗时 {time.time() - t0:.1f}s")

    # 2. 准备任务列表（hash, distance）— 不含 dist 表
    print("准备任务...")
    tasks = [(h, d) for h, d in dist.items()]
    total_tasks = len(tasks)
    print(f"  共 {total_tasks:,} 个任务，{NUM_WORKERS} 个进程")

    # 3. 多进程处理
    print("开始处理（可能需要数分钟，取决于 CPU）...")
    t_work = time.time()
    states = []
    in_degree = defaultdict(int)
    failed = 0
    report_interval = max(1, total_tasks // 20)

    with Pool(
        processes=NUM_WORKERS,
        initializer=_init_worker,
        initargs=(dist, step, total_cells),
        maxtasksperchild=500,
    ) as pool:
        for i, result in enumerate(
            pool.imap_unordered(_process_one_task, tasks, chunksize=200)
        ):
            if i % report_interval == 0:
                elapsed = time.time() - t_work
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (total_tasks - i - 1) / rate if rate > 0 else 0
                print(
                    f"  进度: {i + 1:,}/{total_tasks:,} "
                    f"({100*(i+1)/total_tasks:.1f}%)  "
                    f"速率 {rate:.0f}/s  ETA {eta:.0f}s",
                    flush=True,
                )

            if result is None:
                failed += 1
                continue

            entry, in_delta = result
            if entry is None:
                failed += 1
                if isinstance(in_delta, str):
                    print(f"  [错误] {in_delta}")
                continue

            states.append(entry)
            for hh, cnt in in_delta.items():
                in_degree[hh] += cnt

    elapsed = time.time() - t_work
    print(f"处理完成: {len(states):,} 状态, {failed} 失败, 耗时 {elapsed:.0f}s")

    # 4. 保存 states
    print("保存 states.pkl ...")
    states_path = os.path.join(out_dir, 'states.pkl')
    with open(states_path, 'wb') as f:
        pickle.dump(states, f, protocol=pickle.HIGHEST_PROTOCOL)
    states_mb = os.path.getsize(states_path) / 1024 / 1024
    print(f"  → {states_path} ({states_mb:.1f} MB)")

    # 5. 保存 in_degree
    print("保存 in_degree.pkl ...")
    in_deg_dict = dict(in_degree)
    in_deg_path = os.path.join(out_dir, 'in_degree.pkl')
    with open(in_deg_path, 'wb') as f:
        pickle.dump(in_deg_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
    in_deg_mb = os.path.getsize(in_deg_path) / 1024 / 1024
    print(f"  → {in_deg_path} ({in_deg_mb:.1f} MB)")

    # 6. 统计摘要
    print("生成统计...")
    dist_counts = Counter(s['distance'] for s in states)
    action_counts = Counter(s['optimal_action_count'] for s in states)
    in_deg_values = list(in_degree.values())

    top_in = sorted(in_degree.items(), key=lambda x: -x[1])[:20]
    top_in_details = []
    for hh, cnt in top_in:
        dd = dist.get(hh, -1)
        coords = tc.int_to_coords(hh, total_cells)
        rs = [r for r, _ in coords]
        cs = [c for _, c in coords]
        mr, mc = min(rs), min(cs)
        grid_str = ''
        norm_set = set((r - mr, c - mc) for r, c in coords)
        max_ri = max(r for r, _ in norm_set)
        max_ci = max(c for _, c in norm_set)
        for r in range(max_ri + 1):
            for c in range(max_ci + 1):
                grid_str += '#' if (r, c) in norm_set else '.'
            grid_str += '\n'
        top_in_details.append({
            'hash': hh,
            'in_degree': cnt,
            'distance': dd,
            'grid': grid_str.strip(),
        })

    stats = {
        'meta': {'m': m, 'n': n, 'step': step, 'total_cells': total_cells},
        'total_states': len(states),
        'failed': failed,
        'elapsed_seconds': elapsed,
        'distance_distribution': dict(sorted(dist_counts.items())),
        'optimal_action_count_distribution': dict(sorted(action_counts.items())),
        'in_degree': {
            'min': min(in_deg_values) if in_deg_values else 0,
            'max': max(in_deg_values) if in_deg_values else 0,
            'mean': sum(in_deg_values) / len(in_deg_values) if in_deg_values else 0,
            'median': sorted(in_deg_values)[len(in_deg_values) // 2] if in_deg_values else 0,
        },
        'top_20_by_in_degree': top_in_details,
        'state_sample': [
            {
                'distance': s['distance'],
                'grid_rows': s['grid_rows'],
                'grid_cols': s['grid_cols'],
                'optimal_action_count': s['optimal_action_count'],
                'actions': s['optimal_actions'][:3],
            }
            for s in states[:5]
        ],
    }

    stats_path = os.path.join(out_dir, 'stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"  → {stats_path}")

    # 7. 摘要输出
    print(f"\n{'='*60}")
    print(f"导出完成！")
    print(f"  状态数: {len(states):,}")
    print(f"  入度范围: {stats['in_degree']['min']} - {stats['in_degree']['max']}")
    print(f"  入度均值: {stats['in_degree']['mean']:.1f}")
    print(f"  入度中位数: {stats['in_degree']['median']}")
    print(f"\n  每个状态的最优动作数分布:")
    for k, v in sorted(action_counts.items()):
        bar = '█' * min(v // max(1, len(states) // 50), 40)
        print(f"    {k} 个动作: {v:8,}  {bar}")
    print(f"\n  入度 Top 10 状态（可能的「瓶颈」）：")
    for i, item in enumerate(top_in_details[:10]):
        print(f"    {i+1}. 入度={item['in_degree']}  距离={item['distance']}")
        for line in item['grid'].split('\n'):
            print(f"       {line}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    m = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    export(m, n, step)


if __name__ == '__main__':
    main()
