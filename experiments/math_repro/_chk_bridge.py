"""找出「不在 B 却能一步进困局」的状态（桥梁态）。
用法: python find_bridge.py <dump>
"""
import os, sys
import numpy as np

d = sys.argv[1]
N = os.path.getsize(os.path.join(d, "membership.bin")) // 16
mem = np.fromfile(os.path.join(d, "membership.bin"), dtype=np.uint8).reshape(N, 16)
b = np.fromfile(os.path.join(d, "boards.bin"), dtype="<u2").reshape(N, 16)
e = np.fromfile(os.path.join(d, "edges.bin"), dtype="<u4").reshape(-1, 2)
fl = mem[:, 4]
inB = (fl & 2) != 0
cone = (fl & 1) != 0
T = np.nonzero(cone & ~inB)[0]
into = e[np.isin(e[:, 1], T)]
print("指向困局的边:", len(into))
starts = [int(x) for x in into[:, 0].tolist() if not inB[x]]
print("起点不在 B 的边:", len(starts), " 起点:", sorted(set(starts)))
for u in sorted(set(starts)):
    print("state", u, "flags", int(fl[u]), "outdeg", int(mem[u, 6]), "indeg", int(mem[u, 8]))
    for r in range(16):
        mm = int(b[u, r])
        if mm:
            print("    " + "".join("#" if mm >> c & 1 else "." for c in range(mm.bit_length())))
