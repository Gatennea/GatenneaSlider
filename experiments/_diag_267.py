# -*- coding: utf-8 -*-
"""2-6-7 诊断：窗口结构 / couple 失败分布 / 整形宏逐对尝试。"""
import json
import sys
import os
import time
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import (build_game, _convoy_fill, _rigid_fill,  # noqa: E402
                                  _belt_shift_fill, _comps_ml,
                                  _adj_clusters)
from solver.ml.gap_solver import (window_of, _edge_of, solve_edge_gap,  # noqa: E402
                                  solve_corner_gap, _vacancy_couple_hook)
from solver.ml.gather_solver import find_best_window  # noqa: E402

path = os.path.join(_ROOT, 'save', '2-6-7-20261001-161826.json')
with open(path, encoding='utf-8') as f:
    doc = json.load(f)
m, n = doc['puzzle']['m'], doc['puzzle']['n']
step = doc['puzzle']['step']
snap = doc['history']['snapshots'][0]
b = snap['bounds']
coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                   for i, row in enumerate(snap['matrix'])
                   for j, v in enumerate(row) if v)

reg, ov, holes, outside = window_of(coords, m, n, step)
print('窗口 r0=%s c0=%s wh=%s 窗内方块=%d 洞=%d 凸=%d'
      % (reg[0], reg[1], reg[2], ov, len(holes), len(outside)))
print('洞:', sorted(holes))
print('凸:', sorted(outside))

r0, c0, (wh, ww) = reg
for h in sorted(holes):
    print('  洞 %s edge=%s' % (h, _edge_of(h, r0, c0, wh, ww)))

# 同 mod couple 对
pairs = [(h, p) for h in sorted(holes) for p in sorted(outside)
         if (p[0] - h[0]) % step == 0 and (p[1] - h[1]) % step == 0]
print('\n同mod couple 对数: %d' % len(pairs))

hook = _vacancy_couple_hook(False)
reasons = Counter()
t0 = time.time()
for h, p in pairs:
    acts, st = hook(coords, m, n, step, h, p)
    tag = ('OK %d步' % len(acts)) if acts else (st.get('reason') or st.get('error') or str(st))
    reasons[str(tag)[:60]] += 1
    print('  couple 洞%s←凸%s: %s' % (h, p, tag))
print('hook 总耗时 %.1fs' % (time.time() - t0))
print('\n失败原因分布:')
for k, v in reasons.most_common():
    print('  %2d × %s' % (v, k))

# 洞簇 / 凸簇（rigid 前提）
hcl = _adj_clusters(holes)
pcl = [c for c in _comps_ml(outside) if len(c) >= 2]
print('\n洞簇:', [sorted(c) for c in hcl])
print('凸簇(>=2格):', [sorted(c) for c in pcl])

# 三个整形宏逐对尝试
print('\n--- 整形宏尝试 ---')
for h in sorted(holes):
    t = time.time()
    acts = _belt_shift_fill(coords, m, n, step, h)
    print('带移 洞%s: %s (%.1fs)' % (h, 'OK %d步' % len(acts) if acts else 'None',
                                     time.time() - t))
for Hc in hcl:
    for Pc in pcl:
        if len(Hc) != len(Pc):
            continue
        t = time.time()
        acts, used = _rigid_fill(coords, m, n, step, Hc, Pc, max_nodes=6000)
        print('刚体 洞簇%s←凸簇%s: %s 用节点%d (%.1fs)'
              % (sorted(Hc), sorted(Pc),
                 'OK %d步' % len(acts) if acts else 'None', used,
                 time.time() - t))
for h, p in pairs:
    t = time.time()
    acts, used = _convoy_fill(coords, m, n, step, h, p, max_nodes=2500)
    print('convoy 洞%s←凸%s: %s 用节点%d (%.1fs)'
          % (h, p, 'OK %d步' % len(acts) if acts else 'None', used,
             time.time() - t))
