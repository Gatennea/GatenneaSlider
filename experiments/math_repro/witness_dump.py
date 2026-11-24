# -*- coding: utf-8 -*-
"""导出满盘回路的证人档（带标签重放所需信息）。
用法：python _k1_witness.py <m> <n> <depth> <out.json>
"""
import json
import sys
from collections import deque

sys.path.insert(0, r"E:\program_project\other\doubaotest\slider\math_lab\branch\experiments\math_repro")
import moves as M

m, n, DEPTH, OUT = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
K = m * n


def norm(st):
    rmin = min(r for r, _, _ in st)
    cmin = min(c for _, c, _ in st)
    return tuple(sorted((r - rmin, c - cmin, t) for r, c, t in st))


def shift(st, comp, unit):
    lab = {(r, c): t for r, c, t in st}
    out = {}
    for (r, c), t in lab.items():
        if (r, c) in comp:
            out[(r + unit[0], c + unit[1])] = t
        else:
            out[(r, c)] = t
    return norm(tuple((r, c, t) for (r, c), t in out.items()))


start = norm(tuple((r, c, n * r + c) for r in range(m) for c in range(n)))
shape0 = frozenset((r, c) for r, c, _ in start)

seen = {start: (None, None)}
layer = [start]
loops = []
for k in range(DEPTH):
    nxt = []
    for st in layer:
        S = frozenset((r, c) for r, c, _ in st)
        for seam, side, comp, unit in M.legal_moves(S, 1):
            r = shift(st, comp, unit)
            if len(frozenset((rr, cc) for rr, cc, _ in r)) != K:
                continue
            if r not in seen:
                seen[r] = (st, (seam, side, unit, sorted(comp)))
                nxt.append(r)
                # 回到满盘形状 → 记录回路
                if frozenset((rr, cc) for rr, cc, _ in r) == shape0:
                    chain = []
                    cur = r
                    while seen[cur][0] is not None:
                        prev, step = seen[cur]
                        chain.append({"seam": step[0], "side": step[1],
                                      "unit": list(step[2]), "comp": [list(c) for c in step[3]]})
                        cur = prev
                    chain.reverse()
                    perms = sorted([[t, r_, c_] for r_, c_, t in r], key=lambda x: x[0])
                    loops.append({"depth": sum(1 for _ in chain), "steps": chain, "perm": perms})
    layer = nxt
    print(f"  深度 {k+1}: 状态 {len(seen)}，回路累计 {len(loops)}")

data = {"m": m, "n": n, "K": K, "depth": DEPTH,
        "start": [[r, c, n * r + c] for r in range(m) for c in range(n)],
        "loops": loops}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)
print(f"  写入 {OUT}：{len(loops)} 条回路")
