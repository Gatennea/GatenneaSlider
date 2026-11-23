"""s=1 家族（n=2）最短距離的結構分析。只讀 sequences/，不重算 BFS。

產出四段：
  1. 每張表的分佈、合計、平均
  2. 兩條線性族：Δc=0 → 4+3Δr；Δc=1 → 8+2Δr（例外清單）
  3. R1：對角單步 8 的條件（兩端都在內列）
  4. 對稱軌道數（m×2 矩形的群 = 恆等／上下鏡／左右鏡／180 旋轉）
"""
import json, os, collections, itertools

HERE = os.path.dirname(os.path.abspath(__file__))
SEQ = os.path.join(HERE, "sequences")

TABLES = ["swap_321_all15_cases.json", "swap_421_all28_cases.json", "swap_521_all45_cases.json"]


def load(name):
    cases = json.load(open(os.path.join(SEQ, name), encoding="utf-8"))
    m, n = cases[0]["m"], cases[0]["n"]
    rows = []
    for c in cases:
        t = c["target"]
        a = (int(t[0][0]), int(t[0][1]))
        b = (int(t[1][0]), int(t[1][1]))
        rows.append((a, b, int(c["steps"])))
    return m, n, rows


def orbits(m, n, rows):
    """把無序對 {a,b} 在矩形自同構群下軌道化。

    群有 4 個元素（恆等／上下一翻／左右一翻／180 旋轉）；**同一個變換要同時作用在兩點**，
    不能各自獨立翻轉（那會造出 x=y 的假鑰匙）。
    """
    G = [lambda r, c: (r, c),
         lambda r, c: (m - 1 - r, c),
         lambda r, c: (r, n - 1 - c),
         lambda r, c: (m - 1 - r, n - 1 - c)]

    def canon(a, b):
        return min(tuple(sorted((g(*a), g(*b)))) for g in G)

    seen = collections.OrderedDict()
    for a, b, d in rows:
        k = canon(a, b)
        seen.setdefault(k, []).append(((a, b), d))
    bad = 0
    for k, v in seen.items():
        vals = sorted(d for _, d in v)
        if len(set(vals)) > 1:
            bad += 1
            print("   !! orbit 不同值:", k, vals)
    return len(seen), bad


print("=" * 70)
print("1+4. 分佈與軌道")
for name in TABLES:
    m, n, rows = load(name)
    dist = sorted(collections.Counter(d for _, _, d in rows).items())
    total = sum(d for _, _, d in rows)
    print(f"  ({m},{n},1)  {len(rows):2d} 對  取值 {dist}")
    print(f"      合計 {total}  平均 {total/len(rows):.2f}")
    orb, bad = orbits(m, n, rows)
    print(f"      對稱軌道 {orb} 個（同軌道不同值 {bad} 個）")

print("=" * 70)
print("2. 兩檔定價：Δr>=1 且 Δc=1 時，d 只取 4+3Δr（跨列免費）或 8+2Δr（跨列先付 4）")
for name in TABLES:
    m, n, rows = load(name)
    print(f"  ({m},{n},1)")
    hits, misses = 0, []
    for a, b, d in rows:
        dr, dc = abs(b[0] - a[0]), abs(b[1] - a[1])
        if dc != 1 or dr == 0:
            # Δc=1,Δr=0 是純橫向對換，另計
            continue
        if d in (4 + 3 * dr, 8 + 2 * dr):
            hits += 1
        else:
            misses.append((dr, d, 4 + 3 * dr, 8 + 2 * dr, a, b))
    print(f"     命中 {hits}，例外 {len(misses)}  {misses if misses else ''}")

print("=" * 70)
print("2b. 純縱向（Δc=0）：d = 4+3Δr 是否全中")
for name in TABLES:
    m, n, rows = load(name)
    misses = [(abs(b[0] - a[0]), d, a, b) for a, b, d in rows
              if abs(b[1] - a[1]) == 0 and d != 4 + 3 * abs(b[0] - a[0])]
    tot = sum(1 for a, b, _ in rows if abs(b[1] - a[1]) == 0)
    print(f"  ({m},{n},1): {tot - len(misses)}/{tot} 命中；例外 {misses if misses else ''}")

print("=" * 70)
print("3. R1：對角單步（Δr=Δc=1）→ 8 需要兩端都在內列 1..m-2，否則 10")
for name in TABLES:
    m, n, rows = load(name)
    ok = 0
    tbl = []
    for a, b, d in rows:
        dr, dc = abs(b[0] - a[0]), abs(b[1] - a[1])
        if (dr, dc) != (1, 1):
            continue
        inner = min(a[0], b[0]) >= 1 and max(a[0], b[0]) <= m - 2
        pred = 8 if inner else 10
        tbl.append((a, b, d, inner, pred))
        ok += (d == pred)
    print(f"  ({m},{n},1): {ok}/{len(tbl)} 命中")
    for a, b, d, inner, pred in tbl:
        if d != pred:
            print(f"     miss {a}->{b} d={d} inner={inner}")
