# -*- coding: utf-8 -*-
"""精確驗證 2_3_1 哈密頓路徑（高效版）"""
import pickle
from solver.table_core import int_to_coords, forward_neighbors
from collections import Counter
import time

tbl = pickle.load(open("solver/data/2_3_1/table.pkl", "rb"))
states = list(tbl.keys())
N = 34
total = 6
m, n, step = 2, 3, 1

# 建圖（用整數索引加速）
adj_idx = [[] for _ in range(N)]
for i, h in enumerate(states):
    coords = int_to_coords(h, total)
    nbrs = forward_neighbors(frozenset(coords), step, total)
    for nb in nbrs:
        j = states.index(nb)  # 慢，但N=34可以接受
        if j > i:
            adj_idx[i].append(j)
            adj_idx[j].append(i)

dists = [tbl[h] for h in states]

print(f"N={N}, 邊數={sum(len(v) for v in adj_idx)//2}")
print(f"度數分佈: {dict(Counter(len(v) for v in adj_idx).most_common())}")

# 優化版DFS - 用bytearray和預計算
visited = bytearray(N)
path = []
found = [False]
calls = [0]

def dfs(u, count):
    if found[0]:
        return
    calls[0] += 1
    visited[u] = 1
    path.append(u)
    if count == N:
        found[0] = True
        return
    # 預計算每個neighbor的剩餘未訪問度數
    cand = []
    for v in adj_idx[u]:
        if not visited[v]:
            rd = 0
            for w in adj_idx[v]:
                if not visited[w]:
                    rd += 1
            cand.append((rd, dists[v], v))
    cand.sort()
    for _, _, v in cand:
        dfs(v, count + 1)
        if found[0]:
            return
    path.pop()
    visited[u] = 0

# 從度數最小的節點開始（這些最難訪問）
min_deg = min(len(v) for v in adj_idx)
start_nodes = [i for i in range(N) if len(adj_idx[i]) == min_deg]
print(f"最小度={min_deg}, 從 {len(start_nodes)} 個節點開始")

t0 = time.time()
for si in start_nodes[:3]:
    dfs(si, 1)
    if found[0]:
        break
elapsed = time.time() - t0

if found[0]:
    hp = [states[i] for i in path]
    print(f"\n✓ 找到哈密頓路徑！（回溯{calls[0]}次, 耗時{elapsed:.2f}s）")
    print(f"路徑距離序列: {[dists[i] for i in path]}")
else:
    print(f"\n✗ 未找到哈密頓路徑（回溯{calls[0]}次, 耗時{elapsed:.2f}s）")
    print("圖可能不存在哈密頓路徑")

# 用更嚴格的條件檢查
print("\n=== 圖結構深入分析 ===")
# 檢查是否每個節點對都被連接
for k in range(1, 6):
    # 刪除度數最小的k個節點，看分量數
    min_deg_nodes = sorted(range(N), key=lambda i: (len(adj_idx[i]), -dists[i]))[:k]
    remaining = [i for i in range(N) if i not in set(min_deg_nodes)]
    # BFS檢查連通性
    if not remaining:
        print(f"  刪除{k}個節點後無剩餘節點")
        continue
    visited2 = set()
    queue = [remaining[0]]
    visited2.add(remaining[0])
    while queue:
        u = queue.pop(0)
        for v in adj_idx[u]:
            if v in remaining and v not in visited2:
                visited2.add(v)
                queue.append(v)
    comps = len(remaining) - len(visited2) + 1
    status = "✗ 不可能有哈密頓路徑" if comps > k + 1 else f"({comps} <= {k+1} OK)"
    print(f"  刪除{k}個最小度節點 → {comps} 個分量 {status}")
