# 2-7-8 局面 ASCII 可视化：看清 setup 段每一步在做什么
import json
import sys
sys.path.insert(0, '.')

from solver.ml.gap_solver import window_of

F = 'archives/2-7-8-20261001-185331.json'


def load(f):
    d = json.load(open(f, encoding='utf-8'))
    m, n, step = d['puzzle']['m'], d['puzzle']['n'], d['puzzle']['step']
    snaps = d['history']['snapshots']
    frames = []
    for s in snaps:
        b = s['bounds']
        coords = frozenset(
            (b['min_row'] + i, b['min_col'] + j)
            for i, row in enumerate(s['matrix'])
            for j, v in enumerate(row) if v)
        frames.append((coords, s.get('move_info') or {}))
    return m, n, step, frames


def show(coords, m, n, step, lo=31, hi=50, tag='B'):
    (r0, c0, wh), ov, holes, outside = window_of(coords, m, n, step)
    rs = [p[0] for p in coords]
    cs = [p[1] for p in coords]
    r1, r2 = min(rs) - 1, max(rs) + 1
    c1, c2 = min(cs) - 1, max(cs) + 1
    print('   ov=%d 窗(%d,%d) 洞=%s' % (ov, r0, c0, sorted(holes)))
    print('   凸=%s' % (sorted(outside),))
    hdr = '      ' + ''.join('%3d' % c for c in range(c1, c2 + 1))
    print(hdr)
    for r in range(r1, r2 + 1):
        line = '%4d |' % r
        for c in range(c1, c2 + 1):
            inwin = r0 <= r < r0 + m and c0 <= c < c0 + n
            if (r, c) in coords:
                ch = '#' if inwin else 'O'   # O = 窗外凸起
            else:
                ch = '.' if inwin else ' '   # . = 窗内洞
            line += '  ' + ch
        print(line)


m, n, step, frames = load(F)
for i in range(31, 41):
    coords, mi = frames[i]
    mp = sorted(tuple(p) for p in mi.get('moved_positions', []))
    print('\n===== frames[%d]（第 %d 步执行前）=====' % (i, i))
    show(coords, m, n, step)
    if mp:
        print('   下一步 moved %d 格: %s%s line=%s dir=%s' % (
            len(mp), mi.get('gap_type'), '', mi.get('gap_line'), mi.get('direction')))
        print('   bbox r[%d,%d] c[%d,%d]' % (
            min(p[0] for p in mp), max(p[0] for p in mp),
            min(p[1] for p in mp), max(p[1] for p in mp)))
