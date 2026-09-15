# -*- coding: utf-8 -*-
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / 'solver' / 'data'

for p in sorted(DATA_DIR.glob('*/meta.json')):
    m = json.load(open(p, encoding='utf-8'))
    dist = m['distance_distribution']
    ds = sorted(int(k) for k in dist)
    counts = [int(dist[str(d)]) for d in ds]
    total = sum(counts)
    mean = sum(d * c for d, c in zip(ds, counts)) / total
    std = (sum(c * (d - mean) ** 2 for d, c in zip(ds, counts)) / total) ** 0.5
    puzzle = f"{m['step']}~{m['m']}*{m['n']}"
    print(f'{puzzle}: 總={total}, 上帝之數={len(ds)-1}, 均值={mean:.2f}, 標準差={std:.2f}')
    max_c = max(counts)
    for i, d in enumerate(ds):
        bar_len = counts[i] * 40 // max_c
        bar = chr(9608) * bar_len
        print(f'  d={d:>2}: {counts[i]:>6}  {bar}')
    print()
