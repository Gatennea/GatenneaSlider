# 共轭让位 v3：让位动作 W 允许任意距离 1..D（用户 2-6-7 手解里有位移 5、6 的动作）
import sys
import time
sys.path.insert(0, '.')

from solver.ml.fill_macro import (build_game, gcoords, window_of,
                                  _capture_apply, _replay_apply,
                                  solve_single_void)
from solver.ml.gap_solver import solve_gap_macro
from experiments._conj_relay import apply_seq, ov_of, load_start
from experiments._dist_probe import enum_moves_d

_OPP = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


def apply_dist(coords, m, n, a6):
    """执行带距离的 6 元组动作 (gap,line,side,d,rep,dist)。"""
    g = build_game(coords, m, n)
    ok, a5 = _capture_apply(g, a6[:5], a6[5])
    if not ok:
        return False, coords, None
    return True, gcoords(g), a5


def conj3(coords, m, n, step, ov0, dists=(1, 2, 3, 4, 5, 6),
          budget=240.0, verbose=True, use_slide=False):
    t0 = time.time()
    best = None
    tried = 0
    W = enum_moves_d(coords, m, n, dists, min_size=1)
    if verbose:
        print('  让位候选 %d（距离%s）' % (len(W), dists))
    for (a6, comp, mv, s1) in W:
        if time.time() - t0 > budget:
            print('  预算耗尽 %.0fs 尝试%d' % (time.time() - t0, tried))
            break
        _r, _o, holes, outside = window_of(s1, m, n, step)
        if not holes:
            continue
        # C：现有 couple 宏
        for h in sorted(holes):
            for p in sorted(outside):
                if ((h[0] - p[0]) % step or (h[1] - p[1]) % step):
                    continue
                tried += 1
                acts, _s = solve_single_void(s1, m, n, step, hole=h,
                                             anchor=p, keep_partial=True)
                if not acts:
                    continue
                ok, after_c, used_c = apply_seq(s1, m, n, step, acts)
                if not ok:
                    continue
                # 带复位
                inv = (a6[0], a6[1], a6[2], _OPP[a6[3]], min(mv), a6[5])
                ok1, _c1, w_a = apply_dist(coords, m, n, a6)
                ok2, after_all, rest_u = apply_seq(
                    _c1, m, n, step, list(acts) + [inv])
                ov2 = ov_of(after_all, m, n, step) if ok2 else -1
                if ok2 and ov2 > ov0 and (best is None or ov2 > best[1]):
                    best = ([w_a] + rest_u, ov2, after_all)
                    print('    ★ %s←%s 让位(距%d)+填%d+复位 → ov %d→%d'
                          % (h, p, a6[5], len(used_c), ov0, ov2))
                ov1b = ov_of(after_c, m, n, step)
                if ov1b > ov0 and (best is None or ov1b > best[1]):
                    best = ([w_a] + used_c, ov1b, after_c)
                    print('    ★ %s←%s 让位(距%d)+填%d（不复位）→ ov %d→%d'
                          % (h, p, a6[5], len(used_c), ov0, ov1b))
    if verbose:
        print('  共轭v3 %.1fs 尝试%d best=%s'
              % (time.time() - t0, tried, best[1] if best else None))
    return best


if __name__ == '__main__':
    m, n, step, coords = load_start('archives/2-6-7-20261001-161826.json', 0)
    t0 = time.time()
    res = solve_gap_macro(build_game(coords, m, n), step)
    print('求解器 %.0fs → %s' % (time.time() - t0,
          res.get('reason', '')[:50] if isinstance(res, dict) else '元组'))
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
    cur, total = coords, []
    for it in range(8):
        if build_game(cur, m, n).is_solved():
            print('还原成功！')
            break
        ov = ov_of(cur, m, n, step)
        _r, _o, h2, o2 = window_of(cur, m, n, step)
        print('\n[轮%d] ov=%d 洞%s 凸%s' % (it, ov, sorted(h2), sorted(o2)))
        best = conj3(cur, m, n, step, ov, budget=200.0)
        if not best:
            print('  ✖ 卡住')
            break
        acts, ov2, after = best
        total.extend(acts)
        cur = after
        print('  → 推进 %d 步 ov %d→%d' % (len(acts), ov, ov2))
    print('\n== %s 总%d步' % (
        '还原' if build_game(cur, m, n).is_solved() else '未还原', len(total)))
    g = build_game(coords, m, n)
    print('   回放合法=%s' % _replay_apply(g, total, m, n, step))
