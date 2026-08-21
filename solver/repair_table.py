# -*- coding: utf-8 -*-
"""
修复不完整的建表数据（因并行 BFS 停止时 break 丢数据导致）。

扫描表中所有状态，找出"正邻居不在表中或距离异常"的缺口，
将缺失状态按正确距离补入，构建前沿后继续 BFS。

运行：
    D:\\python\\python.exe -m solver.repair_table [m n step]
    默认 m=4 n=4 step=2
"""

import os
import sys
import time
import pickle

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def main():
    m = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    total = m * n

    data_dir = os.path.join(DATA_DIR, f'{m}_{n}_{step}')
    table_path = os.path.join(data_dir, 'table.pkl')
    ckpt_path = os.path.join(data_dir, 'checkpoint.pkl')

    if not os.path.exists(table_path):
        print(f"错误: 找不到 {table_path}，请先建表。")
        sys.exit(1)

    print(f"加载表...", flush=True)
    with open(table_path, 'rb') as f:
        dist = pickle.load(f)

    orig_count = len(dist)
    max_d = max(dist.values()) if dist else 0
    print(f"表内状态: {orig_count:,}  最大距离: {max_d}", flush=True)

    from solver import table_core as tc

    # 迭代填补：每次扫描所有已知状态的正邻居，填入缺失者，直到无新缺口
    iteration = 0
    total_filled = 0
    all_filled = {}  # 所有轮次填补的状态 hash → distance
    while True:
        iteration += 1
        print(f"\n--- 第 {iteration} 轮扫描 ---", flush=True)
        t0 = time.time()
        holes = 0
        filled = {}  # missing_hash → corrected_distance
        seen = set(dist.keys())

        sorted_items = sorted(dist.items(), key=lambda x: x[1])
        for idx, (h, d) in enumerate(sorted_items):
            if idx % 50000 == 0 and idx > 0:
                elapsed = time.time() - t0
                rate = idx / elapsed if elapsed > 0 else 1
                eta = (len(sorted_items) - idx) / rate
                print(f"  扫描 {idx:,}/{len(sorted_items):,}  "
                      f"({100*idx/len(sorted_items):.0f}%)  "
                      f"已发现 {holes} 缺口  ETA {eta:.0f}s", flush=True)

            B = set(tc.int_to_coords(h, total))
            for nb_h in tc.forward_neighbors(B, step, total):
                if nb_h not in seen and nb_h not in filled:
                    correct_d = d - 1 if d > 0 else None
                    if correct_d is not None and correct_d >= 0:
                        filled[nb_h] = correct_d
                        holes += 1

        elapsed = time.time() - t0
        print(f"扫描完成: {holes} 缺口, 耗时 {elapsed:.0f}s", flush=True)

        if holes == 0:
            break

        for h, d in filled.items():
            dist[h] = d
            all_filled[h] = d
        total_filled += holes

    print(f"\n迭代 {iteration} 轮, 共填补 {total_filled} 状态", flush=True)
    if total_filled == 0:
        print("表已完整，无需修复。")
        sys.exit(0)

    print(f"填补后状态数: {len(dist):,} (+{total_filled})", flush=True)

    # 构建前沿：用所有填补的状态，取最深层的一批继续 BFS
    frontier = sorted(all_filled.keys(), key=lambda x: all_filled[x], reverse=True)
    # 只取最深距离层的（因为浅层的前驱可能已被 BFS 处理过，
    # 但深层的新状态需要继续扩散）
    if frontier:
        deepest_dist = all_filled[frontier[0]]
        frontier = [h for h in frontier if all_filled[h] >= deepest_dist - 1]
        # 去重
        frontier = list(dict.fromkeys(frontier))

    print(f"前沿大小: {len(frontier)}  最深距离: {deepest_dist}", flush=True)

    # 保存 checkpoint（建表程序可从中续算）
    ckpt = {
        'meta': {
            'm': m, 'n': n, 'step': step,
            'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'last_saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'version': 1,
        },
        'dist': dist,
        'frontier': frontier,
        'current_dist': deepest_dist,
        'stats': {
            'total_states': len(dist),
            'max_distance': max(dist.values()) if dist else 0,
            'distance_distribution': {},
            'layers_done': deepest_dist,
        },
    }

    # 也更新 table.pkl（做备份）
    backup = table_path + '.bak'
    os.replace(table_path, backup)
    print(f"备份旧表: {backup}", flush=True)

    with open(table_path, 'wb') as f:
        pickle.dump(dist, f, protocol=pickle.HIGHEST_PROTOCOL)

    with open(ckpt_path, 'wb') as f:
        pickle.dump(ckpt, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"\n修复完成！", flush=True)
    print(f"  旧状态数: {orig_count:,}", flush=True)
    print(f"  新状态数: {len(dist):,} (+{holes})", flush=True)
    print(f"  前沿: {len(frontier)}", flush=True)
    print(f"\n现在运行 python -m solver.build_table {m} {n} {step} --no-gui 继续建表。", flush=True)


if __name__ == '__main__':
    main()
