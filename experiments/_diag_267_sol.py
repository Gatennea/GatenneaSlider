# 解剖 2-6-7 用户 31 步手解：每步分量大小/位移/ov/洞凸变化
import json
import sys
sys.path.insert(0, '.')

from solver.ml.gap_solver import window_of

F = 'archives/2-6-7-20261001-161826.json'


def load(f):
    d = json.load(open(f, encoding='utf-8'))
    m, n, step = d['puzzle']['m'], d['puzzle']['n'], d['puzzle']['step']
    frames = []
    for s in d['history']['snapshots']:
        b = s['bounds']
        coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                           for i, row in enumerate(s['matrix'])
                           for j, v in enumerate(row) if v)
        frames.append((coords, s.get('move_info') or {}))
    return m, n, step, frames


m, n, step, frames = load(F)
print('%dx%d step=%d  共 %d 步' % (m, n, step, len(frames) - 1))
for i in range(1, len(frames)):
    prev, _ = frames[i - 1]
    cur, mi = frames[i]
    frm = sorted(prev - cur)
    to = sorted(cur - prev)
    d0 = None
    if frm and to and len(frm) == len(to):
        dd = (to[0][0] - frm[0][0], to[0][1] - frm[0][1])
        if sorted((r + dd[0], c + dd[1]) for r, c in frm) == to:
            d0 = dd
    (r0, c0, _w), ov, holes, outside = window_of(cur, m, n, step)
    (_r1, _c1, _w2), ov0, h0, o0 = window_of(prev, m, n, step)
    print('%2d %s%-3d %s  %2d格 位移=%-8s ov %2d→%2d  洞%2d→%2d 新填=%s' % (
        i, mi.get('gap_type'), mi.get('gap_line'), mi.get('direction'),
        len(frm), str(d0), ov0, ov, len(h0), len(holes),
        sorted(set(h0) - set(holes))[:3]))
