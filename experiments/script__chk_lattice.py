# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
from engine.shatter_geometry import _solved_tiles, _centroid_point

tiles = _solved_tiles()
pts = [_centroid_point(t) for _, t in tiles]
C = set(pts)
print('n pts', len(C))

diffs = set()
for p in pts:
    for q in pts:
        diffs.add((p[0] - q[0], p[1] - q[1]))

cands = sorted([d for d in diffs if d != (0, 0)],
               key=lambda d: (abs(d[0]) + abs(d[1]), abs(d[0]), abs(d[1])))


def in_lat(v, b1, b2):
    d = b1[0] * b2[1] - b1[1] * b2[0]
    if d == 0:
        return False
    a = v[0] * b2[1] - v[1] * b2[0]
    bb = -v[0] * b1[1] + v[1] * b1[0]
    return a % d == 0 and bb % d == 0


b1 = cands[0]
b2 = None
for d in cands:
    if d != (0, 0) and b1[0] * d[1] - b1[1] * d[0] != 0:
        b2 = d
        break
print('b1', b1, 'b2', b2, 'det', b1[0] * b2[1] - b1[1] * b2[0])
bad = [d for d in cands if not in_lat(d, b1, b2)]
print('diffs not in lat:', len(bad), bad[:10])

dirs = {'L_v': (0, 6), 'L_d30': (3, 3), 'L_d150': (-3, 3), 'G_h': (6, 0),
        'G_d60': (3, 9), 'G_d120': (-3, 9)}
for name, d in dirs.items():
    print(name, d, 'in lat:', in_lat(d, b1, b2))

# Also: what are the smallest translation symmetries of the centroid SET?
# i.e. V in lat with C+V == C (on the 48-set). brute small range.
print('--- set symmetries (C+V subset C) over small V ---')
syms = []
for dx in range(-6, 7):
    for dy in range(-6, 7):
        if (dx, dy) == (0, 0):
            continue
        if all((p[0] + dx, p[1] + dy) in C for p in pts):
            syms.append((dx, dy))
print('V with C+V subset C:', syms)
