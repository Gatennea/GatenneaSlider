# -*- coding: utf-8 -*-
"""解析 tag_bfs 的 gens 导出，按 (r mod 2, c mod 2) 的四类分解支撑集。

回答两个问题：
  Q1 是否存在「严格单类」生成元（support 全落在同一 mod 类）？
  Q2 每类各有多少条、最短的那条多少步？

若 Q1 为真，则 (4!)⁴ 上的联合最短路可以拆成四个 24 状态子问题 —— 这就是
「不用跑 331,776」的依据。
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
            if not line or line.startswith('params') or line.startswith('  depth'):
                continue
            if line[0] not in '0123456789':
                continue
            m = re.search(r'@\s*(\d+)\s*$', line)
            depth = int(m.group(1)) if m else None
            body = line[:m.start()] if m else line
            nums = [int(x) for x in re.findall(r'-?\d+', body)]
            if len(nums) < P:
                continue
            out.append((nums[:P], depth))
    return out


def support(v):
    return [t for t in range(P) if v[t] != t]


def klass(p):
    r, c = divmod(p, N)
    return (r % S, c % S)


def main(path):
    gens = load(path)
    print(f'{path}: {len(gens)} 条生成元')
    print()

    per_class_single = defaultdict(list)
    multi = []
    pure_kind = defaultdict(int)

    for v, dep in gens:
        sup = support(v)
        ks = {klass(p) for p in sup}
        if len(ks) == 1:
            k = ks.pop()
            per_class_single[k].append((len(sup), dep, v, sup))
        else:
            multi.append((len(ks), len(sup), dep, sorted(ks)))

    print('=== Q1 严格单类生成元 ===')
    for k in sorted(per_class_single):
        items = sorted(per_class_single[k], key=lambda x: (x[0], x[1]))
        print(f'类{k}: {len(items)} 条, 最小支撑 {items[0][0]} 个位 (depth {items[0][1]})')
        for nsup, dep, v, sup in items[:4]:
            print(f'    nsup={nsup} depth={dep} sup={sup}')
    if not per_class_single:
        print('  （无）')
    print()

    print('=== 跨类生成元 ===')
    print(f'共 {len(multi)} 条；按涉及类数分布：')
    dist = defaultdict(int)
    for nk, nsup, dep, ks in multi:
        dist[nk] += 1
    for nk in sorted(dist):
        print(f'  {nk} 类: {dist[nk]} 条')
    print()
    print('跨类中最短的 6 条：')
    for nk, nsup, dep, ks in sorted(multi, key=lambda x: (x[2] or 99, x[1]))[:6]:
        print(f'  depth={dep} nsup={nsup} classes={ks}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else '_s2_d8_gens.log'))
