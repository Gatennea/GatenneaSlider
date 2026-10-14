# -*- coding: utf-8 -*-
"""尋找 2_3_1 哈密頓路徑（修正版）"""
import pickle
from solver.table_core import int_to_coords, forward_neighbors
from collections import Counter
import time

tbl = pickle.load(open("solver/data/2_3_1/table.pkl", "rb"))
states = list(tbl.keys())
N = 34
total = 6
m, n, step = 2, 3, 1

adj = {}
for h in states:
    coords = int_to_coords(h, total)
    adj[h] = set(forward_neighbors(frozenset(coords), step, total))

idx_map = {h: i for i, h in enumerate(states)}
dists = {h: tbl[h] for h in states}

# ---- 1. 簡單貪心 ----
def greedy_path(start, prefer_forward=True):
    visited = set()
    path = [start]
    visited.add(start)
    u = start
    while len(path) < N:
        neighbors = [v for v in adj[u] if v not in visited]
        if not neighbors:
            break
        if prefer_forward:
            neighbors.sort(key=lambda v: dists[v], reverse=True)
        else:
            def rem_deg(v):
                return sum(1 for w in adj[v] if w not in visited)
            neighbors.sort(key=rem_deg)
        u = neighbors[0]
        path.append(u)
        visited.add(u)
    return path if len(path) == N else None

# 試所有起點
print("=== 貪心搜索 ===")
for start in states:
    for pref in [True, False]:
        p = greedy_path(start, pref)
        if p:
            print(f"找到！起點距離={dists[start]}, 偏好={'向前' if pref else '度數'}")
            print(f"路徑距離: {[dists[h] for h in p]}")
            break
    else:
        continue
    break
else:
    print("所有貪心策略失敗")

# ---- 2. DFS回溯 ----
print("\n=== DFS回溯 ===")
def dfs_find(start_idx, max_calls=200000):
    visited = bytearray(N)
    path = []
    calls = [0]
    found = [False]

    def dfs(u_idx, count):
        if found[0]:
            return
        calls[0] += 1
        if calls[0] > max_calls:
            return
        visited[u_idx] = 1
        path.append(u_idx)
        if count == N:
            found[0] = True
            return
        u = states[u_idx]
        # Warnsdorff: 選未訪問鄰居中剩餘度數最小的
        cand = []
        for v in adj[u]:
            vi = idx_map[v]
            if not visited[vi]:
                rd = sum(1 for w in adj[v] if not visited[idx_map[w]])
                cand.append((rd, dists[v], vi))
        cand.sort()  # 先按剩餘度數，再按距離
        for _, _, v_idx in cand:
            dfs(v_idx, count + 1)
            if found[0]:
                return
        path.pop()
        visited[u_idx] = 0

    dfs(start_idx, 1)
    return (calls[0], [states[i] for i in path] if found[0] else None)

# 從最遠的節點開始
far_nodes = sorted(states, key=lambda h: dists[h], reverse=True)
t0 = time.time()
for sn in far_nodes[:3]:
    si = idx_map[sn]
    calls, hp = dfs_find(si, max_calls=300000)
    elapsed = time.time() - t0
    if hp:
        print(f"找到哈密頓路徑！（起點距離={dists[sn]}, 回溯{calls}次, 耗時{elapsed:.2f}s）")
        print(f"路徑距離序列: {[dists[h] for h in hp]}")
        valid = all(hp[i+1] in adj[hp[i]] for i in range(len(hp)-1))
        print(f"驗證: {'合法 ✓' if valid else '非法 ✗'}")
        break
    else:
        print(f"起點距離={dists[sn]} 未找到（回溯{calls}次）")

# ---- 3. 圖結構分析 ----
print("\n=== 圖結構分析 ===")
deg_dist = Counter(len(v) for v in adj.values())
print(f"度數分佈: {dict(sorted(deg_dist.items()))}")
print(f"總邊數: {sum(d*c for d,c in deg_dist.items())//2}")

layer_edges = Counter()
for h in states:
    d = dists[h]
    for nb in adj[h]:
        layer_edges[(min(d, dists[nb]), max(d, dists[nb]))] += 1
print("\n層間邊數:")
for (d1, d2), cnt in sorted(layer_edges.items()):
    print(f"  層{d1}-層{d2}: {cnt} 條")

# 檢查是否存在哈密頓路徑的必要條件
print("\n=== 哈密頓路徑必要性檢查 ===")
# 刪除k個節點後，連通分量數量必須 <= k+1
for k in range(1, 5):
    # 簡單檢查：刪除了最小度的k個節點後的分量數
    pass
