# -*- coding: utf-8 -*-
"""2-6-7 组合探索：ov40 残局上带移+couple 能否接力推进到全解。"""
import json
import sys
import os
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import (build_game, gcoords, _replay_apply,  # noqa: E402
                                  _belt_shift_fill, _overlap_raised)
from solver.ml.gap_solver import window_of, _vacancy_couple_hook  # noqa: E402

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

hook = _vacancy_couple_hook(False)
acts9, st = hook(coords, m, n, step, (0, 5), (6, 3))
g = build_game(coords, m, n)
_replay_apply(g, acts9, m, n, step)


def state(cur, tag):
    reg, ov, holes, outside = window_of(cur, m, n, step)
    print('%s: ov=%d 洞%s 凸%s' % (tag, ov, sorted(holes), sorted(outside)))
    return cur


cur = frozenset(gcoords(g))
state(cur, '9步后残局')

# 带移盖洞探测（残局三洞）
for hi in range(4):
    cur0 = frozenset(gcoords(g))
    _reg, _ov, holes, outside = window_of(cur0, m, n, step)
    for h in sorted(holes):
        bacts, _end = _belt_shift_fill(cur0, m, n, step, h)
        if not bacts:
            continue
        g2 = build_game(cur0, m, n)
        if not _replay_apply(g2, bacts, m, n, step):
            print('  带移 洞%s: 回放失败' % (h,))
            continue
        cur2 = frozenset(gcoords(g2))
        reg, ov2, holes2, outside2 = window_of(cur2, m, n, step)
        raised = ov2 > _ov
        print('  带移 洞%s: %d步 → ov %d→%d 提升=%s 洞%s 凸%s'
              % (h, len(bacts), _ov, ov2, raised, sorted(holes2),
                 sorted(outside2)))

# 残局 couple 全试
cur0 = frozenset(gcoords(g))
_reg, _ov, holes, outside = window_of(cur0, m, n, step)
for h in sorted(holes):
    for p in sorted(outside):
        if (p[0] - h[0]) % step or (p[1] - h[1]) % step:
            continue
        acts, st2 = hook(cur0, m, n, step, h, p)
        if acts is None:
            print('  couple 洞%s←凸%s: 无产物' % (h, p))
            continue
        g2 = build_game(cur0, m, n)
        ok = _replay_apply(g2, acts, m, n, step)
        ov2 = window_of(frozenset(gcoords(g2)), m, n, step)[1] if ok else '?'
        print('  couple 洞%s←凸%s: %d步 回放=%s ov %d→%s 提升=%s'
              % (h, p, len(acts), ok, _ov, ov2,
                 _overlap_raised(cur0, m, n, step, acts) if ok else '?'))

# 手动贪心接力：带移(允许 ov 不降)+couple，看能否一路推到全解
print('\n--- 手动接力（couple 优先，无 couple 则带移整形） ---')
g = build_game(coords, m, n)
_replay_apply(g, acts9, m, n, step)
total = list(acts9)
t0 = time.time()
for it in range(12):
    cur = frozenset(gcoords(g))
    reg, ov, holes, outside = window_of(cur, m, n, step)
    if not holes and build_game(cur, m, n).is_solved():
        print('第%d轮: 已全解! 总步数=%d' % (it, len(total)))
        break
    progressed = False
    # couple 尝试
    for h in sorted(holes):
        for p in sorted(outside):
            if (p[0] - h[0]) % step or (p[1] - h[1]) % step:
                continue
            acts, _s = hook(cur, m, n, step, h, p)
            if acts is None:
                continue
            g2 = build_game(cur, m, n)
            if _replay_apply(g2, acts, m, n, step):
                ov2 = window_of(frozenset(gcoords(g2)), m, n, step)[1]
                if ov2 > ov:
                    _replay_apply(g, acts, m, n, step)
                    total.extend(acts)
                    print('第%d轮: couple 洞%s←凸%s %d步 ov %d→%d'
                          % (it, h, p, len(acts), ov, ov2))
                    progressed = True
                    break
        if progressed:
            break
    if progressed:
        continue
    # 带移整形（不降即可）
    for h in sorted(holes):
        bacts, _e = _belt_shift_fill(cur, m, n, step, h)
        if not bacts:
            continue
        g2 = build_game(cur, m, n)
        if _replay_apply(g2, bacts, m, n, step):
            ov2 = window_of(frozenset(gcoords(g2)), m, n, step)[1]
            if ov2 >= ov:
                _replay_apply(g, bacts, m, n, step)
                total.extend(bacts)
                print('第%d轮: 带移 洞%s %d步 ov %d→%d'
                      % (it, h, len(bacts), ov, ov2))
                progressed = True
                break
    if not progressed:
        print('第%d轮: 接力停滞（无可用动作）' % it)
        break
print('接力结束: 总步数=%d 用时%.1fs' % (len(total), time.time() - t0))
if _replay_apply(build_game(coords, m, n), total, m, n, step):
    g3 = build_game(coords, m, n)
    _replay_apply(g3, total, m, n, step)
    print('整链回放后 is_solved =', g3.is_solved())
