# -*- coding: utf-8 -*-
"""
圖論分析：邊密度、Burnside 驗證、哈密頓路徑
"""
import json
import pickle
import random
import sys
import time
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from solver.table_core import (
    forward_neighbors, canonicalize, goal_state, _normalize, _rot90, _flip
)

DATA_DIR = Path(__file__).parent.parent / 'solver' / 'data'


def load_table(folder):
    with open(DATA_DIR / folder / 'table.pkl', 'rb') as f:
        return pickle.load(f)

def load_meta(folder):
    with open(DATA_DIR / folder / 'meta.json', encoding='utf-8') as f:
        return json.load(f)


def _int_to_coords(h, count):
    cells = []
    for _ in range(count):
        val = h % 65536
        cells.append((val // 256, val % 256))
        h //= 65536
    return frozenset(cells)


# ── 1. 邊密度 ─────────────────────────────────────────────────────────────────
def compute_edge_density(folder, sample=3000):
    m, n, step = load_meta(folder)['m'], load_meta(folder)['n'], load_meta(folder)['step']
    total = m * n
    table = load_table(folder)
    n_states = len(table)

    keys = list(table.keys())
    if n_states > sample:
        keys = random.sample(keys, sample)
        label = f'sample={sample}/{n_states}'
    else:
        label = f'full={n_states}'

    out_degrees = []
    t0 = time.time()
    for i, h in enumerate(keys):
        coords = _int_to_coords(h, total)
        nbrs = forward_neighbors(coords, step, total)
        out_degrees.append(len(nbrs))
        if (i + 1) % 500 == 0:
            print(f'  [{i+1}/{len(keys)}]', end='', flush=True)
    dt = time.time() - t0
    print(f' ({dt:.1f}s)')

    avg_out = sum(out_degrees) / len(out_degrees)
    max_possible = 2 * (m + n)
    density = avg_out / max_possible

    print(f'\n{folder}: {label}')
    print(f'  avg_out_degree = {avg_out:.2f}  (max possible = {max_possible})')
    print(f'  edge_density   = {density:.4f}')
    deg_dist = Counter(out_degrees)
    for d in sorted(deg_dist):
        print(f'    out_degree={d}: {deg_dist[d]}')
    return avg_out, density


# ── 2. Burnside 驗證 ───────────────────────────────────────────────────────────
def burnside_verify(folder, sample=3000):
    """
    方法：對每個 sampled state，計算其在 D8 下的 8 個變體（不歸一化），
    統計有多少個是「不同」的，再與 canonicalize 結果對比。
    若 canonicalize 正確，所有 8 變體的 canonical form 應相同 → 軌道大小=1。
    同時驗證：對每個 state，任意兩個變體的 canonical form 都相同。
    """
    m, n, step = load_meta(folder)['m'], load_meta(folder)['n'], load_meta(folder)['step']
    total = m * n
    table = load_table(folder)
    n_states = len(table)

    def all_8_variants(fs):
        """返回 D8 的全部 8 個變體（未歸一化的 frozenset）。"""
        result = []
        rot = frozenset(fs)
        for _ in range(4):
            result.append(rot)
            result.append(_flip(rot))
            rot = _rot90(rot)
        return result

    keys = list(table.keys())
    if n_states > sample:
        keys = random.sample(keys, sample)

    # 統計：對每個 state，計算其 8 變體中不同 canonical form 的數量
    canonical_counts = []
    raw_variant_sizes = []
    t0 = time.time()
    for i, h in enumerate(keys):
        coords = _int_to_coords(h, total)
        variants = all_8_variants(coords)
        canon_set = set(canonicalize(v) for v in variants)
        canonical_counts.append(len(canon_set))
        raw_variant_sizes.append(len(set(str(sorted(v)) for v in variants)))
        if (i + 1) % 500 == 0:
            print(f'  [{i+1}/{len(keys)}]', end='', flush=True)
    dt = time.time() - t0
    print(f' ({dt:.1f}s)')

    cc_dist = Counter(canonical_counts)
    rv_dist = Counter(raw_variant_sizes)
    print(f'  變體數分佈 (raw, 未歸一化): {dict(sorted(rv_dist.items()))}')
    print(f'  canonical 分佈 (8個變體的 canonical form 數量): {dict(sorted(cc_dist.items()))}')
    print(f'  若所有 canonical=1，表示 D8 規範化正確')
    print(f'  canonical states (BFS): {n_states}')
    return n_states, dict(cc_dist), dict(rv_dist)


# ── 3. 哈密頓路徑 ─────────────────────────────────────────────────────────────
def verify_hamiltonian(folder):
    m, n, step = load_meta(folder)['m'], load_meta(folder)['n'], load_meta(folder)['step']
    total = m * n
    table = load_table(folder)
    n_states = len(table)

    if n_states > 2000:
        print(f'\n{folder}: {n_states} 個狀態，超過閾值，跳過。')
        return None

    print(f'\n{folder}: {n_states} 個狀態，構建鄰接表...')
    adj = {}
    for h in table:
        coords = _int_to_coords(h, total)
        nbrs = forward_neighbors(coords, step, total)
        adj[h] = set(nbrs)
    for h in list(adj.keys()):
        for nb in adj[h]:
            adj.setdefault(nb, set()).add(h)

    # 檢查連通性
    visited_bfs = set()
    queue = [next(iter(adj))]
    visited_bfs.add(queue[0])
    while queue:
        u = queue.pop(0)
        for v in adj[u]:
            if v not in visited_bfs:
                visited_bfs.add(v)
                queue.append(v)
    if len(visited_bfs) < n_states:
        print(f'  ✗ 圖不連通 ({len(visited_bfs)}/{n_states})，無法有哈密頓路徑')
        return False

    # 檢查二分圖奇偶性
    color = {}
    queue = [next(iter(adj))]
    color[queue[0]] = 0
    cnt0 = cnt1 = 0
    while queue:
        u = queue.pop(0)
        if color[u] == 0:
            cnt0 += 1
        else:
            cnt1 += 1
        for v in adj[u]:
            if v not in color:
                color[v] = 1 - color[u]
                queue.append(v)
    is_bipartite = (cnt0 + cnt1 == n_states)
    if is_bipartite and abs(cnt0 - cnt1) > 1:
        print(f'  ✗ 二分圖不平衡 ({cnt0} vs {cnt1})，不可能有哈密頓路徑')
        return False
    print(f'  連通 ✓  二分圖: {is_bipartite} ({cnt0}:{cnt1})')

    # Warnsdorff 貪心 + 回退
    print(f'  嘗試 Warnsdorff DFS...')

    def find_path(start_node):
        stack = [(start_node, [start_node], {start_node}, 1)]
        while stack:
            u, path, visited, depth = stack.pop()
            if depth == n_states:
                return path
            unvisited = [v for v in adj[u] if v not in visited]
            unvisited.sort(key=lambda v: sum(1 for w in adj[v] if w not in visited))
            for v in unvisited:
                new_visited = visited | {v}
                stack.append((v, path + [v], new_visited, depth + 1))
        return None

    t0 = time.time()
    start = min(adj, key=lambda h: len(adj[h]))
    path = find_path(start)
    dt = time.time() - t0
    if path and len(path) == n_states:
        print(f'  ✓ 找到哈密頓路徑！（{dt:.1f}s）')
        return True
    else:
        print(f'  ✗ 未找到（{dt:.1f}s）')
        return False


# ── 主程式 ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    puzzles = ['2_3_1', '3_3_1', '3_3_2', '4_4_2', '4_4_3']
    for p in puzzles:
        print('=' * 55)
        try:
            compute_edge_density(p)
        except Exception as e:
            print(f'{p}: 邊密度失敗 - {e}')
        try:
            burnside_verify(p)
        except Exception as e:
            print(f'{p} Burnside 失敗 - {e}')
        try:
            verify_hamiltonian(p)
        except Exception as e:
            print(f'{p} 哈密頓路徑失敗 - {e}')
        print()
