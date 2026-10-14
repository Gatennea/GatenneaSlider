# -*- coding: utf-8 -*-
"""驗證哈密頓路徑（DFS回溯版）+ 計算邊密度"""
import pickle
import time
from solver.table_core import int_to_coords, forward_neighbors
from collections import defaultdict

puzzles = [
    ("2_3_1", 2, 3, 1),
    ("3_3_1", 3, 3, 1),
    ("3_3_2", 3, 3, 2),
]

print("=" * 70)
print("Q1.2 哈密頓路徑 + Q6 邊密度")
print("=" * 70)

for name, m, n, step in puzzles:
    total = m * n
    path = f"solver/data/{name}/table.pkl"
    tbl = pickle.load(open(path, "rb"))
    states = list(tbl.keys())
    N = len(states)
    print(f"\n{name} (m={m},n={n},step={step}): N={N} 狀態")

    # ---- 建圖 ----
    t0 = time.time()
    adj = {}
    degree_dist = defaultdict(int)
    for h in states:
        coords = int_to_coords(h, total)
        nbrs = list(forward_neighbors(frozenset(coords), step, total))
        adj[h] = nbrs
        degree_dist[len(nbrs)] += 1
    elapsed_build = time.time() - t0

    total_degree = sum(len(v) for v in adj.values())
    edge_count = total_degree // 2
    max_edges = N * (N - 1) // 2
    density = edge_count / max_edges if max_edges > 0 else 0
    avg_degree = total_degree / N
    min_d = min(degree_dist.keys())
    max_d = max(degree_dist.keys())

    print(f"  建表耗時: {elapsed_build:.2f}s")
    print(f"  實際邊數 = {edge_count:,}  |  最大邊數 = {max_edges:,}")
    print(f"  邊密度 = {density:.6f} ({density*100:.4f}%)")
    print(f"  平均度數 = {avg_degree:.2f}, 最小度 = {min_d}, 最大度 = {max_d}")
    print(f"  度數分佈: {dict(sorted(degree_dist.items()))}")

    # 記錄度數1的節點
    deg1_nodes = [h for h in states if len(adj[h]) == 1]
    print(f"  度數=1的節點數量 = {len(deg1_nodes)}")

    # ---- 哈密頓路徑（DFS回溯）----
    if N <= 2000 and len(deg1_nodes) <= 2:
        # 關鍵：度數1的節點必須是起點或終點，從它們開始搜
        print(f"  尋找哈密頓路徑（DFS回溯）...")

        idx_map = {h: i for i, h in enumerate(states)}
        visited = bytearray(N)
        path_list = []
        found = [False]

        # 預計算每個節點的未訪問鄰居數量
        remaining_deg = [len(adj[h]) for h in states]

        def dfs(u_idx, count):
            if found[0]:
                return
            visited[u_idx] = 1
            path_list.append(u_idx)
            if count == N:
                found[0] = True
                return
            u = states[u_idx]
            # 選未訪問鄰居中「剩餘未訪問度數」最小的（Warnsdorff）
            cand = []
            for v in adj[u]:
                vi = idx_map[v]
                if not visited[vi]:
                    # 計算v在未訪問集合中的度數
                    rd = sum(1 for w in adj[v] if not visited[idx_map[w]])
                    cand.append((rd, vi))
            cand.sort()
            for _, v_idx in cand:
                dfs(v_idx, count + 1)
                if found[0]:
                    return
            path_list.pop()
            visited[u_idx] = 0

        t1 = time.time()
        # 從度數1的節點開始
        start_nodes = deg1_nodes if deg1_nodes else [states[0]]
        for sn in start_nodes:
            si = idx_map[sn]
            if not found[0]:
                dfs(si, 1)

        elapsed_search = time.time() - t1

        if found[0]:
            hp = [states[i] for i in path_list]
            valid = all(hp[i + 1] in adj[hp[i]] for i in range(N - 1))
            if valid:
                print(f"  ✓ 找到哈密頓路徑！（搜索耗時 {elapsed_search:.2f}s）")
                print(f"    路徑長度 = {len(hp)}, 首距離={tbl[hp[0]]}, 尾距離={tbl[hp[-1]]}")
            else:
                print(f"  警告：路徑有非法邊！")
        else:
            print(f"  ✗ 未找到哈密頓路徑（搜索耗時 {elapsed_search:.2f}s）")
            # 如果度數1的節點 > 2，說明不可能有哈密頓路徑
            if len(deg1_nodes) > 2:
                print(f"    原因：度數1的節點有 {len(deg1_nodes)} 個，哈密頓路徑最多容許 2 個端點")
    elif N <= 2000 and len(deg1_nodes) > 2:
        print(f"  ✗ 不可能存在哈密頓路徑：度數1的節點有 {len(deg1_nodes)} 個")
    else:
        print(f"  狀態數太多，跳過搜尋")

print("\n" + "=" * 70)
print("總結：")
print("""
邊密度極低（0.6%~11%），狀態圖非常稀疏。
Dirac 定理完全不適用。
但對小謎題可以暴力搜索。
""")
