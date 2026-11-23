"""檢查「同一類對換的最短距離只依賴盤面對稱軌道」這個口徑。

盤面自同構：非正方形只有 4 階（恒等／上下翻／左右翻／轉 180°），正方形再加
90°／270° 旋轉共 8 階。腳本把這些操作作用在 cases 檔裡的每一對上，求軌道，
並檢查同軌道內距離是否全等。

用法：python check_orbits.py [cases.json ...]
無參數時預設檢查 (4,3,2) 與 (3,3,2) 兩份全表。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = [
    os.path.join(HERE, "sequences", "swap_432_all14_cases.json"),
    os.path.join(HERE, "sequences", "swap_332_all8_cases.json"),
    os.path.join(HERE, "sequences", "swap_321_all15_cases.json"),
    os.path.join(HERE, "sequences", "swap_532_all25_cases.json"),
    os.path.join(HERE, "sequences", "swap_442_all24_cases.json"),
]


def board_ops(m, n):
    ops = [
        lambda p: (p[0], p[1]),
        lambda p: (m - 1 - p[0], p[1]),
        lambda p: (p[0], n - 1 - p[1]),
        lambda p: (m - 1 - p[0], n - 1 - p[1]),
    ]
    if m == n:  # 正方形才有 90°／270° 與兩條對角翻，共 8 階
        ops += [
            lambda p: (p[1], m - 1 - p[0]),          # 90°
            lambda p: (m - 1 - p[1], p[0]),          # 270°
            lambda p: (p[1], p[0]),                  # 主對角翻
            lambda p: (m - 1 - p[1], m - 1 - p[0]),  # 副對角翻
        ]
    return ops


def check(path):
    cases = json.load(open(path, encoding="utf-8"))
    m, n, s = cases[0]["m"], cases[0]["n"], cases[0]["s"]
    pairs = {}
    for c in cases:
        a, b = map(tuple, c["target"])
        pairs[frozenset((a, b))] = c["steps"]
    ops = board_ops(m, n)
    seen, orbits = set(), []
    for pr in pairs:
        if pr in seen:
            continue
        grp = set()
        for a, b in [tuple(pr)]:
            for f in ops:
                q = frozenset((f(a), f(b)))
                if q in pairs:
                    grp.add(q)
        seen |= grp
        orbits.append(grp)
    print("=== %s === (%d,%d,%d)  pairs=%d  ops=%d"
          % (os.path.basename(path), m, n, s, len(pairs), len(ops)))
    ok = True
    for grp in sorted(orbits, key=lambda g: (min(pairs[x] for x in g), len(g))):
        ds = {pairs[x] for x in grp}
        print("  軌道 size=%d  distance=%s  常數=%s" % (len(grp), sorted(ds), len(ds) == 1))
        ok &= len(ds) == 1
    total = sum(len(g) for g in orbits)
    print("  orbits=%d  total=%d  distances=%s  sum=%d  all_const=%s"
          % (len(orbits), total, sorted({pairs[p] for p in pairs}), sum(pairs.values()), ok))
    return ok and total == len(pairs)


def main():
    paths = sys.argv[1:] or DEFAULT
    allok = True
    for p in paths:
        allok &= check(p)
    print("總判定：", "全過" if allok else "有不一致")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
