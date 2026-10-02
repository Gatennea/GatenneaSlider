# 精确还原 2-7-8 第32~39步：从相邻快照差集算移动前/后与位移
import json
import sys
sys.path.insert(0, '.')

from solver.ml.gap_solver import window_of

F = 'archives/2-7-8-20261001-185331.json'


def load(f):
    d = json.load(open(f, encoding='utf-8'))
    m, n, step = d['puzzle']['m'], d['puzzle']['n'], d['puzzle']['step']
    frames = []
    for s in d['history']['snapshots']:
        b = s['bounds']
        coords = frozenset(
            (b['min_row'] + i, b['min_col'] + j)
            for i, row in enumerate(s['matrix'])
            for j, v in enumerate(row) if v)
        frames.append((coords, s.get('move_info') or {}))
    return m, n, step, frames


m, n, step, frames = load(F)
for i in range(32, 40):
    prev, _ = frames[i - 1]
    cur, mi = frames[i]
    frm = sorted(prev - cur)
    to = sorted(cur - prev)
    delta = None
    if frm and to and len(frm) == len(to):
        # 检查是否纯平移
        d0 = (to[0][0] - frm[0][0], to[0][1] - frm[0][1])
        pure = all((to[k][0] - frm[k][0], to[k][1] - frm[k][1]) == d0
                   for k in range(len(frm))) and \
            sorted((r + d0[0], c + d0[1]) for r, c in frm) == to
        delta = d0 if pure else '非平移'
    (r0, c0, wh), ov, holes, outside = window_of(cur, m, n, step)
    (r1, c1, _w2), ov0, h0, o0 = window_of(prev, m, n, step)
    print('\n第 %d 步  move_info=%s%s line=%s dir=%s' % (
        i, mi.get('gap_type'), '', mi.get('gap_line'), mi.get('direction')))
    print('  移动 %d 格 位移=%s' % (len(frm), delta))
    print('    from bbox r[%d,%d] c[%d,%d]  ->  to bbox r[%d,%d] c[%d,%d]' % (
        min(p[0] for p in frm), max(p[0] for p in frm),
        min(p[1] for p in frm), max(p[1] for p in frm),
        min(p[0] for p in to), max(p[0] for p in to),
        min(p[1] for p in to), max(p[1] for p in to)))
    print('  ov %d -> %d' % (ov0, ov))
    print('  洞 %d -> %d   新填上的洞: %s' % (
        len(h0), len(holes), sorted(set(h0) - set(holes))))
    print('  凸 %d -> %d   消失的凸: %s' % (
        len(o0), len(outside), sorted(set(o0) - set(outside))))
