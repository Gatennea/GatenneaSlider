# -*- coding: utf-8 -*-
"""用小尺寸跑 Python 参考引擎，产出基线数值供 C 引擎交叉验证。"""
import json
import sys

sys.path.insert(0, '.')
from repro import PuzzleGraph, run_R1  # noqa: E402

out = {}
for (m, n, s) in [(2, 3, 1), (2, 3, 2), (3, 3, 1), (3, 3, 2)]:
    g = PuzzleGraph(m, n, s)
    r = run_R1(m, n, s)
    out[f'{m},{n},{s}'] = r
    print(f'({m},{n},{s}) -> {r}', flush=True)

with open('baseline_py.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('WROTE baseline_py.json')
