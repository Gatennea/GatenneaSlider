# 按用户「完美洞(8邻)」框架体检：2-7-8 停机局面 vs 2-6-7 残局
import sys
sys.path.insert(0, '.')

from solver.ml.fill_macro import build_game, gcoords, _capture_apply, _replay_apply
from solver.ml.gap_solver import window_of, solve_gap_macro
from experiments._conj_relay import load_start


def show(coords, m, n, step, tag, focus_holes):
    (r0, c0, wh), ov, holes, outside = window_of(coords, m, n, step)
    rs = [p[0] for p in coords]
    cs = [p[1] for p in coords]
    r1, r2 = min(rs) - 1, max(rs) + 1
    c1, c2 = min(cs) - 1, max(cs) + 1
    print('\n== %s  窗(%d,%d) ov=%d' % (tag, r0, c0, ov))
    print('      ' + ''.join('%4d' % c for c in range(c1, c2 + 1)))
    for r in range(r1, r2 + 1):
        line = '%4d |' % r
        for c in range(c1, c2 + 1):
            if (r, c) in coords:
                ch = '#'
            elif r0 <= r < r0 + m and c0 <= c < c0 + n:
                ch = '.'
            else:
                ch = ' '
            line += '   ' + ch
        print(line)
    for h in focus_holes:
        nb = [(h[0] + dr, h[1] + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
              if (dr, dc) != (0, 0)]
        empty = [q for q in nb if q not in coords]
        print('   洞 %s 的8邻空位(缺口)=%s %s' % (
            h, empty, '← 不完美洞' if empty else '← 完美洞'))


def endgame_267():
    m, n, step, coords = load_start('archives/2-6-7-20261001-161826.json', 0)
    res = solve_gap_macro(build_game(coords, m, n), step)
    if isinstance(res, dict) and res.get('actions'):
        g = build_game(coords, m, n)
        acts = [tuple(a) + ((tuple(res['rep_cells'][i]),)
                            if res['rep_cells'][i] else (None,))
                for i, a in enumerate(res['actions'])]
        _replay_apply(g, acts, m, n, step)
        coords = gcoords(g)
    return m, n, step, coords


which = sys.argv[1] if len(sys.argv) > 1 else 'both'
if which in ('278', 'both'):
    m, n, step, coords = load_start('archives/2-7-8-20261001-185331.json', 31)
    show(coords, m, n, step, '2-7-8 停机局面(31步后)', [(1, 4), (0, 5)])
if which in ('267', 'both'):
    m, n, step, coords = endgame_267()
    show(coords, m, n, step, '2-6-7 残局(求解器9步后)', [(4, 0), (5, 5)])
