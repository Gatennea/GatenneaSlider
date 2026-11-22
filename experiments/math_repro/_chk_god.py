# -*- coding: utf-8 -*-
"""正向半徑 vs 回程半徑：找出正向 18..23 的局面，看它們回程多遠。
只读 dump，不改任何数据。
"""
import numpy as np, sys, os
from collections import Counter, deque

D = sys.argv[1] if len(sys.argv) > 1 else "dump_442e"
mem = np.fromfile(os.path.join(D, "membership.bin"), dtype=np.uint8).reshape(-1, 16)
N = mem.shape[0]
flags = mem[:, 4]
outdeg = mem[:, 6:8].copy().view(np.uint16).ravel().astype(np.int64)
indeg = mem[:, 8:10].copy().view(np.uint16).ravel().astype(np.int64)
dist = mem[:, 10:14].copy().view(np.int32).ravel().astype(np.int64)
ed = np.fromfile(os.path.join(D, "edges.bin"), dtype=np.uint32).reshape(-1, 2)
src, dst = ed[:, 0].astype(np.int64), ed[:, 1].astype(np.int64)
print("states", N, "edges", len(ed))
print("回程 dist 范围", dist.min(), dist.max(), "| 不在 R:", int((dist < 0).sum()))

order = np.argsort(src, kind="stable")
ptr = np.zeros(N + 1, dtype=np.int64)
ptr[1:] = np.cumsum(np.bincount(src, minlength=N))
adj = dst[order]

goal = np.where(dist == 0)[0]
fwd = np.full(N, -1, dtype=np.int32)
q = deque()
for s in goal:
    fwd[s] = 0; q.append(int(s))
while q:
    u = q.popleft()
    nf = fwd[u] + 1
    for v in adj[ptr[u]:ptr[u + 1]]:
        v = int(v)
        if fwd[v] < 0:
            fwd[v] = nf; q.append(v)
reach = fwd >= 0
print("正向可达", int(reach.sum()), "| 正向半徑", int(fwd[reach].max()), "| 回程半徑", int(dist.max()))

print("\n正向距離尾段:")
for d in range(max(10, int(fwd[reach].max()) - 12), int(fwd[reach].max()) + 1):
    n = int((fwd == d).sum())
    if n: print(f"  fwd={d}: {n}")

both = reach & (dist >= 0)
diff = fwd[both] - dist[both]
print("\n最大落差 fwd-回程 =", int(diff.max()), "| 典型:", dict(Counter(diff.tolist()).most_common(6)))

bo = np.fromfile(os.path.join(D, "boards.bin"), dtype=np.uint16).reshape(-1, 16)
# 反向邻接，用于找前驱
rorder = np.argsort(dst, kind="stable")
rptr = np.zeros(N + 1, dtype=np.int64)
rptr[1:] = np.cumsum(np.bincount(dst, minlength=N))
radj = src[rorder]


def show(tag, i):
    print(f"\n{tag}: state {i} fwd={fwd[i]} 回程={dist[i]} outdeg={outdeg[i]} indeg={indeg[i]}")
    for r in bo[i]:
        row = "".join("#" if (r >> c) & 1 else "." for c in range(16))
        if row.strip("."): print("   |" + row[:12])
    pre = radj[rptr[i]:rptr[i + 1]]
    if len(pre):
        print(f"   前驅 {len(pre)} 個，回程距離 {[int(dist[p]) for p in pre[:10]]}")


mx = int(fwd[reach].max())
show("正向最遠", int(np.where(fwd == mx)[0][0]))
show("落差最大", int(np.where(both)[0][np.where(diff == diff.max())[0][0]]))
mm = int(dist.max())
idx17 = np.where(dist == mm)[0]
print(f"\n回程 {mm} 的態 {len(idx17)} 個，其正向距離 {[int(fwd[i]) for i in idx17[:10]]}")

# 正向 > 回程 的邊佔比：一條邊 u->v 若 fwd[v] != fwd[u]+1 或 回程[v] != 回程[u]-1
ok = (fwd[src] >= 0) & (fwd[dst] >= 0)
print("\nF 內邊:", int(ok.sum()), "| 其中不沿正向最短路的:", int((fwd[dst] - fwd[src] != 1)[ok].sum()))
okb = (dist[src] >= 0) & (dist[dst] >= 0)
print("R 內邊:", int(okb.sum()), "| 其中不沿回程最短路的:", int((dist[src] - dist[dst] != 1)[okb].sum()))
