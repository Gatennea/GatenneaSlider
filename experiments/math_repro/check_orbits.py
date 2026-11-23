# 驗證：14 對在 4x3 盤的 4 階對稱下恰分成 5 個軌道，且同軌道距離全等
import json, itertools
M, N = 4, 3
cases = json.load(open("experiments/math_repro/sequences/swap_432_all14_cases.json", encoding="utf-8"))
pairs = {}
for c in cases:
    a, b = map(tuple, c["target"]); pairs[frozenset((a, b))] = c["steps"]
def ops():
    f = []
    for r in range(M):
        for col in range(N):
            f.append((r, col)); f.append((M-1-r, col)); f.append((r, N-1-col)); f.append((M-1-r, N-1-col))
    # 每格四個像，按 op 分組
    return [
        lambda p: (p[0], p[1]),
        lambda p: (M-1-p[0], p[1]),          # 上下翻
        lambda p: (p[0], N-1-p[1]),          # 左右翻
        lambda p: (M-1-p[0], N-1-p[1]),      # 180°
    ]
OPS = ops()
seen, orbs = set(), []
for pr in pairs:
    if pr in seen: continue
    o = set()
    for a, b in [tuple(pr)]:
        for f in OPS:
            q = frozenset((f(a), f(b)))
            if q in pairs: o.add(q)
    seen |= o; orbs.append(o)
ok = True
for o in sorted(orbs, key=lambda s: min(pairs[x] for x in s)):
    d = {pairs[x] for x in o}
    print("orbit size=%d  d=%s  ok=%s  e.g.%s" % (len(o), sorted(d), len(d) == 1, sorted(tuple(sorted(x))[0] for x in o)[:1]))
    ok &= (len(d) == 1)
tot = sum(len(o) for o in orbs)
print("orbits=%d total=%d unique_d=%s all_const=%s sum=%d" % (len(orbs), tot, sorted({pairs[p] for p in pairs}), ok, sum(pairs.values())))