# -*- coding: utf-8 -*-
"""逐动作追踪一个失败档案：打印每步动作与 p/h/洞数/solved，定位错误点。"""
import json
import sys

sys.path.insert(0, '.')
from solver.ml.fill_macro import (solve_single_void, replay_and_verify,
                                  window_of)

fn = sys.argv[1] if len(sys.argv) > 1 else \
    'save/填洞失敗案例/2-6-6-20260905-173340錯誤歸一化.json'
d = json.load(open(fn, encoding='utf-8'))
pz = d['puzzle']
st = d['history']['snapshots'][0]
b = st['bounds']
co = frozenset((i + b['min_row'], j + b['min_col'])
               for i, row in enumerate(st['matrix'])
               for j, v in enumerate(row) if v)
print('file:', fn)
print('puzzle:', pz)
(w, ov, holes, outside) = window_of(co, pz['m'], pz['n'], pz['step'])
print('窗口:', w, 'ov:', ov, '洞:', sorted(holes), '凸:', sorted(outside))
acts, stats = solve_single_void(co, pz['m'], pz['n'], pz['step'],
                                keep_partial=True)
print('stats:', stats)
for i, a in enumerate(acts or []):
    print('  %2d %s' % (i, a))
print('replay最终还原:', replay_and_verify(co, pz['m'], pz['n'],
                                        pz['step'], acts)
      if acts else None)
