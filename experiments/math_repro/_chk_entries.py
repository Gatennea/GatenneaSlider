# -*- coding: utf-8 -*-
"""把孤立死區的入口邊印成棋形：來源局面、目的局面、動了哪幾格。
用法: python _chk_entries.py <dump> <u1:v1> [<u2:v2> ...]
"""
import os, sys
import numpy as np


def show(rows, tag):
    nz = [r for r in range(16) if int(rows[r])]
    print(f"  {tag}")
    for r in nz:
        m = int(rows[r])
        print("     " + "".join("#" if m >> c & 1 else "." for c in range(16)).rstrip("."))
    print("     格座標:", [(r, c) for r in nz for c in range(16) if int(rows[r]) >> c & 1])


d = sys.argv[1]
mem = np.fromfile(os.path.join(d, "membership.bin"), dtype=np.uint8).reshape(-1, 16)
flags = mem[:, 4]
outdeg = mem[:, 6:8].copy().view(np.uint16).ravel().astype(np.int64)
dist = mem[:, 10:14].copy().view(np.int32).ravel().astype(np.int64)
b = np.fromfile(os.path.join(d, "boards.bin"), dtype=np.uint16).reshape(-1, 16)

print(f"===== {os.path.basename(d)}")
for spec in sys.argv[2:]:
    u, v = (int(x) for x in spec.split(":"))
    su = set((r, c) for r in range(16) for c in range(16) if int(b[u][r]) >> c & 1)
    sv = set((r, c) for r in range(16) for c in range(16) if int(b[v][r]) >> c & 1)
    show(b[u], f"來源 {u} flags={flags[u]} outdeg={outdeg[u]} 回程={dist[u]}")
    show(b[v], f"目的 {v} flags={flags[v]} outdeg={outdeg[v]} 回程={dist[v]}")
    print(f"  只出現在來源的格: {sorted(su - sv)}")
    print(f"  只出現在目的的格: {sorted(sv - su)}")
    dr = [r1 - r0 for (r0, c0), (r1, c1) in zip(sorted(su - sv), sorted(sv - su))] if su - sv else []
    dc = [c1 - c0 for (r0, c0), (r1, c1) in zip(sorted(su - sv), sorted(sv - su))] if su - sv else []
    print(f"  位移: Δrow={sorted(set(dr))} Δcol={sorted(set(dc))}  移動格數={len(su - sv)}")
    print()
