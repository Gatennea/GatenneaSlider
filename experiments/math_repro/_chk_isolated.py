# -*- coding: utf-8 -*-
"""把兩個容易混淆的物件分開量：
  (I) 孤立死集合 = 不可解 且 不在吸引盆（舊報告口徑，flag8 未設）
      其「誘導子圖」的 SCC 數 = 舊報告的 127 / 352
  (II) 全局封閉區 = 整圖凝聚圖上零出邊的 SCC（含凍結態）
用法: python _chk_isolated.py <dump> ...
"""
import os, sys
import numpy as np
from collections import Counter

def kosaraju(N, adj, radj):
    order = []
    seen = np.zeros(N, dtype=bool)
    for s in range(N):
        if seen[s]:
            continue
        st = [(s, 0)]; seen[s] = True
        while st:
            u, i = st.pop()
            nb = adj[u]
            while i < len(nb):
                v = nb[i]; i += 1
                if not seen[v]:
                    seen[v] = True
                    st.append((u, i)); st.append((v, 0))
                    break
            else:
                order.append(u)
    comp = np.full(N, -1, dtype=np.int64); c = 0
    for s in reversed(order):
        if comp[s] >= 0:
            continue
        st = [s]; comp[s] = c
        while st:
            u = st.pop()
            for v in radj[u]:
                if comp[v] < 0:
                    comp[v] = c; st.append(v)
        c += 1
    return comp, c


for d in sys.argv[1:]:
    mem = np.fromfile(os.path.join(d, "membership.bin"), dtype=np.uint8).reshape(-1, 16)
    N = mem.shape[0]
    flags = mem[:, 4]
    outdeg = mem[:, 6:8].copy().view(np.uint16).ravel().astype(np.int64)
    ed = np.fromfile(os.path.join(d, "edges.bin"), dtype=np.uint32).reshape(-1, 2)
    src = ed[:, 0].astype(np.int64); dst = ed[:, 1].astype(np.int64)
    adj = [[] for _ in range(N)]; radj = [[] for _ in range(N)]
    for u, v in zip(src.tolist(), dst.tolist()):
        adj[u].append(v); radj[v].append(u)

    print(f"\n===== {os.path.basename(d)}  N={N}  邊={len(ed)}")
    B = (flags & 2).astype(bool)
    basin = (flags & 8).astype(bool)
    S = (~B) & (~basin)                      # (I) 孤立死集合
    print(f"(I) 不可解={int((~B).sum())}  不在吸引盆={int(((~B) & ~basin).sum())}  "
          f"孤立死={int(S.sum())}")
    print(f"    在吸引盆的不可解={int(((~B) & basin).sum())}")

    # 誘導子圖 SCC
    idx = np.nonzero(S)[0]
    m = {int(v): k for k, v in enumerate(idx)}
    sub_adj = [[] for _ in idx]
    sub_radj = [[] for _ in idx]
    for u, v in zip(src.tolist(), dst.tolist()):
        if u in m and v in m:
            sub_adj[m[u]].append(m[v]); sub_radj[m[v]].append(m[u])
    comp, nc = kosaraju(len(idx), sub_adj, sub_radj)
    sizes = Counter(comp.tolist())
    print(f"    誘導子圖 SCC = {nc} 個，最大 {max(sizes.values())}，單點 {sizes[1]} 個")
    en = [(u, v) for u, v in zip(src.tolist(), dst.tolist()) if v in m and u not in m]
    ex = [(u, v) for u, v in zip(src.tolist(), dst.tolist()) if u in m and v not in m]
    print(f"    入口邊 = {len(en)}，出口邊 = {len(ex)}")
    for u, v in en:
        print(f"      {u} -> {v}  （來源 flags={flags[u]} outdeg={outdeg[u]}）")

    # (II) 整圖零出邊 SCC
    comp2, nc2 = kosaraju(N, adj, radj)
    sizes2 = Counter(comp2.tolist())
    out_to = [set() for _ in range(nc2)]
    for u, v in zip(src.tolist(), dst.tolist()):
        cu, cv = comp2[u], comp2[v]
        if cu != cv:
            out_to[cu].add(cv)
    main = max(range(nc2), key=lambda c: sizes2[c])
    closed = [c for c in range(nc2) if not out_to[c] and c != main]
    print(f"(II) 零出邊 SCC（不含主區）= {len(closed)} 個 / {sum(sizes2[c] for c in closed)} 態"
          f"，其中單點凍結 {len([c for c in closed if sizes2[c] == 1])} 個")
    # 兩者交集/差集
    in_closed = np.zeros(N, dtype=bool)
    for c in closed:
        in_closed |= (comp2 == c)
    print(f"    孤立死 ⊂ 零出邊區？ {int((S & in_closed).sum())} / {int(S.sum())}"
          f"；零出邊區中不屬於孤立死的 {int((in_closed & ~S).sum())} 個")
