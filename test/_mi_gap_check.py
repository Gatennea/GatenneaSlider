# -*- coding: utf-8 -*-
"""核准：斜向「一格」（平移 ±(1/2,1/2)，屏幕距离 √2/2）之后，横竖缝隙到底锁不锁。

判据用精确判据而不是旧的 rank 二分（rank 二分在半格位置下会把「骑在线上」
的块误判到某一侧）：
    一条线 L 有效 <=> L 不严格落在任何块的跨度内部，且线两侧都至少有一块。
跨度按族取（r/c 可为半整数）：
    h  (R, R+1)      v  (C, C+1)
    d1 N/E (k-1, k)  S/W (k, k+1)        k = r-c
    d2 N/W (k, k+1)  E/S (k+1, k+2)      k = r+c
"""
import os
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from game_mi import MiSliderMatrix, side_of  # noqa: E402

EPS = 1e-9


def _span(fam, key):
    r, c, q = key
    if fam == 'h':
        return (r, r + 1.0)
    if fam == 'v':
        return (c, c + 1.0)
    k = (r - c) if fam == 'd1' else (r + c)
    if fam == 'd1':
        return (k - 1.0, k) if q in ('N', 'E') else (k, k + 1.0)
    return (k, k + 1.0) if q in ('N', 'W') else (k + 1.0, k + 2.0)


def valid_lines(cells, fam):
    spans = [_span(fam, c) for c in cells]
    lo = min(t for t, _b in spans)
    hi = max(b for _t, b in spans)
    out = []
    x = lo
    while x <= hi + EPS:
        cut = any(t < x - EPS and x + EPS < b for t, b in spans)
        if not cut:
            above = any(b <= x + EPS for _t, b in spans)
            below = any(t >= x - EPS for t, _b in spans)
            if above and below:
                out.append(round(x, 3))
        x += 0.5
    return out


def shift(cells, delta):
    return [(c[0] + delta[0], c[1] + delta[1], c[2]) for c in cells]


def caps(vals):
    return '[' + ', '.join(f'{v:g}' for v in vals) + ']'


DIAG = {
    'q': (-0.5, -0.5), 'x': (0.5, 0.5),
    'e': (-0.5, 0.5), 'z': (0.5, -0.5),
    'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1),
}


def run(m, n, gap_fam, line, direction):
    g = MiSliderMatrix(m, n)
    cells = sorted(g.positions())
    before = {fam: valid_lines(cells, fam) for fam in ('h', 'v', 'd1', 'd2')}
    side1 = [c for c in cells if side_of(gap_fam, line, c) == 1]
    side0 = [c for c in cells if side_of(gap_fam, line, c) == 0]
    if not side1 or not side0:
        print(f'{m}x{n} {gap_fam}{line:g} {direction}：该缝两侧有一侧为空，跳过')
        return
    after_cells = side0 + shift(side1, DIAG[direction])
    after = {fam: valid_lines(after_cells, fam)
             for fam in ('h', 'v', 'd1', 'd2')}
    print(f'{m}x{n} 缝 {gap_fam} line={line:g} 方向 {direction}')
    for fam in ('h', 'v', 'd1', 'd2'):
        b, a = before[fam], after[fam]
        lost = [v for v in b if v not in a]
        gain = [v for v in a if v not in b]
        tag = ''
        if lost:
            tag += '  丢了 ' + caps(lost)
        if gain:
            tag += '  新增 ' + caps(gain)
        print(f'    {fam}: {caps(a)}{tag}')


print('=== 斜向一格后四族缝隙（判据：不切任何块内部 + 两侧非空）===')
run(4, 4, 'd1', 0, 'x')
run(4, 4, 'd1', 0, 'q')
run(4, 4, 'd2', 4, 'e')
run(4, 4, 'd1', 2, 'x')
run(2, 2, 'd1', 0, 'x')
run(1, 6, 'd1', 0, 'x')
run(6, 1, 'd2', 6, 'e')
run(6, 6, 'd1', 6, 'x')
run(6, 6, 'v', 2, 'z')
run(4, 4, 'h', 1, 'a')      # 对照：横向整格，A 晶格内部，不该有任何变化
