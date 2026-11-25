# -*- coding: utf-8 -*-
"""从 gens 导出里筛「纯 N 块循环」：support 恰好 n 个位置、且这 n 个位置构成一个 n-cycle。

用来回答「四块循环最短几步」「三块循环最短几步」。
同时报出这 n 个位置分属哪些 mod 类，区分「类内循环」与「跨类循环」。
"""

import re
import sys
from collections import defaultdict

M = N = 4
S = 2
P = M * N


def load(path):
    out = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line[0] not in '0123456789':
                continue
            m = re.search(r'@\s*(\d+)\s*$', line)
            if not m:
                continue
            depth = int(m.group(1))
            nums = [int(x) for x in re.findall(r'-?\d+', line[:m.start()])]
            if len(nums) < P:
                continue
            out.append((nums[:P], depth))
    return out


def klass(p):
    r, c = divmod(p, N)
    return (r % S, c % S)


def cycle_type(v):
    seen = [False] * P
    lens = []
    for i in range(P):
        if seen[i] or v[i] == i:
            seen[i] = True
            continue
        ln, j = 0, i
        while not seen[j]:
            seen[j] = True
            j = v[j]
            ln += 1
        lens.append(ln)
    return sorted(lens)


def main(path):
    gens = load(path)
    print(f'{path}: {len(gens)} 条')
    print()

    by_ntype = defaultdict(list)
    for v, dep in gens:
        ct = cycle_type(v)
        sup = [t for t in range(P) if v[t] != t]
        ks = sorted({klass(p) for p in sup})
        by_ntype[tuple(ct)].append((dep, sup, ks, v))

    print('=== 按循环型列最短 ===')
    for ct in sorted(by_ntype, key=lambda x: (len(x), -max(x))):
        items = sorted(by_ntype[ct], key=lambda x: (x[0], len(x[1])))
        d0, sup0, ks0, _ = items[0]
        print(f'  型 {ct}  共 {len(items)} 条  最短 depth={d0}  '
              f'支撑{len(sup0)}个 类{len(ks0)}个 {ks0}')
        # 每型前 3 条明细
        for dep, sup, ks, v in items[:3]:
            cyc = []
            if len(sup) <= 6:
                start = sup[0]
                j = start
                while True:
                    cyc.append(j)
                    j = v[j]
                    if j == start:
                        break
            print(f'     depth={dep} sup={sup} 类{ks} 链={cyc}')
    print()

    # 纯块循环（一个 n-cycle，无其他）
    print('=== 纯 n 块单循环 ===')
    for n in range(2, 7):
        items = [x for x in by_ntype.get((n,), [])]
        if not items:
            print(f'  n={n}: 无（{path} 深度内不存在）')
            continue
        best = min(x[0] for x in items)
        cls_split = defaultdict(int)
        for dep, sup, ks, v in items:
            cls_split[len(ks)] += 1
        print(f'  n={n}: {len(items)} 条，最短 depth={best}；'
              f'类跨度分布 {dict(sorted(cls_split.items()))}')
        for dep, sup, ks, v in sorted(items, key=lambda x: x[0])[:3]:
            print(f'     depth={dep} sup={sup} 类{ks}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else '_s2_d8_gens.log'))
