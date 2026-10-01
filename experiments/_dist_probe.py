# 验证：2-6-7 残局上，允许「任意距离 1..D」的移动能否找到推进
import json
import sys
import time
sys.path.insert(0, '.')

from solver.ml.fill_macro import (build_game, gcoords, window_of,
                                  _connected_ml, _comps_ml, _capture_apply,
                                  _replay_apply)
from experiments._conj_relay import load_start

_DIRS = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}
_OPP = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


def enum_moves_d(coords, m, n, dists, min_size=1, max_size=None):
    """枚举合法动作，距离取 dists 列表（引擎 try_move 支持任意距离）。"""
    out = []
    rows = [r for r, _c in coords]
    cols = [c for _r, c in coords]
    for gap in ('h', 'v'):
        lines = (range(min(rows) - 2, max(rows) + 3) if gap == 'h'
                 else range(min(cols) - 2, max(cols) + 3))
        dirs = ('a', 'd') if gap == 'h' else ('w', 's')
        for line in lines:
            for side in (('above', 'below') if gap == 'h'
                         else ('left', 'right')):
                if gap == 'h':
                    st = ((lambda q: q[0] <= line) if side == 'above'
                          else (lambda q: q[0] > line))
                else:
                    st = ((lambda q: q[1] <= line) if side == 'left'
                          else (lambda q: q[1] > line))
                sel = frozenset(q for q in coords if st(q))
                if not sel or sel == coords:
                    continue
                for comp in _comps_ml(sel):
                    rest = coords - comp
                    if not rest:
                        continue
                    if len(comp) < min_size:
                        continue
                    if max_size and len(comp) > max_size:
                        continue
                    for d in dirs:
                        dr, dc = _DIRS[d]
                        for dist in dists:
                            ok = True
                            for k in range(1, dist + 1):
                                mvk = frozenset(
                                    (q[0] + dr * k, q[1] + dc * k)
                                    for q in comp)
                                if mvk & rest or not _connected_ml(rest | mvk):
                                    ok = False
                                    break
                            if not ok:
                                continue
                            mv = frozenset((q[0] + dr * dist,
                                            q[1] + dc * dist) for q in comp)
                            out.append(((gap, line, side, d, min(comp), dist),
                                        comp, mv, rest | mv))
    return out


def ov_of(c, m, n, s):
    return window_of(c, m, n, s)[1]


if __name__ == '__main__':
    m, n, step, coords = load_start('save/2-6-7-20261001-161826.json', 0)
    # 播掉求解器那 9 步到残局
    from solver.ml.gap_solver import solve_gap_macro
    res = solve_gap_macro(build_game(coords, m, n), step)
    if isinstance(res, dict) and res.get('actions'):
        g = build_game(coords, m, n)
        acts = [tuple(a) + ((tuple(res['rep_cells'][i]),)
                            if res['rep_cells'][i] else (None,))
                for i, a in enumerate(res['actions'])]
        _replay_apply(g, acts, m, n, step)
        coords = gcoords(g)
    ov0 = ov_of(coords, m, n, step)
    _r, _o, holes, outside = window_of(coords, m, n, step)
    print('残局 ov=%d 洞=%s 凸=%s' % (ov0, sorted(holes), sorted(outside)))
    for dists in ([step], [1, 2], list(range(1, 9))):
        t0 = time.time()
        mv = enum_moves_d(coords, m, n, dists)
        gains = []
        for (a5, comp, mvset, s1) in mv:
            o1 = ov_of(s1, m, n, step)
            if o1 > ov0:
                gains.append((o1, a5, len(comp)))
        gains.sort(reverse=True)
        print('距离%s: 动作%d个 提升项%d个  %.1fs  最佳=%s'
              % (dists, len(mv), len(gains), time.time() - t0,
                 gains[:3]))
