# 共轭让位 v2：新增 C 类型②「小分量沿通道连滑」（2-7-8 解法里的 (1,0)→(1,2)→(1,4)）
import json
import sys
import time
sys.path.insert(0, '.')

from solver.ml.fill_macro import (build_game, gcoords, window_of,
                                  _capture_apply, _replay_apply,
                                  solve_single_void)
from solver.ml.gap_solver import solve_gap_macro
from experiments._conj_relay import (enum_moves, apply_seq, inv_act, ov_of,
                                     load_start)


def pot(s, holes):
    """导引：窗外块到最近洞的最小曼哈顿距离（越小越好）。"""
    if not holes:
        return 0
    best = 999
    for r, c in s:
        for hr, hc in holes:
            d = abs(r - hr) + abs(c - hc)
            if d < best:
                best = d
    return best


def slide_fill(coords, m, n, step, holes, max_depth=3, max_k=3,
               beam=14, verbose=False):
    """小分量连滑：BFS ≤max_depth 步，只走「让某个小分量靠近洞」的动作。

    返回 (act5列表, 终局) 或 None。验收：有块落到原洞位（洞被填）。
    """
    if not holes:
        return None
    p0 = pot(coords, holes)
    layer = [(coords, [], p0)]
    for _d in range(max_depth):
        cand = []
        for st, pre, pw in layer:
            for (a5, comp, mv, s1) in enum_moves(st, m, n, step,
                                                 min_size=1, max_size=max_k):
                p1 = pot(s1, holes)
                if p1 > pw:
                    continue
                cand.append((p1, s1, pre + [a5]))
        cand.sort(key=lambda x: x[0])
        layer = [(s, p, w) for w, s, p in cand[:beam]]
        # 命中：洞被填上
        for _w, s1, pre in cand[:beam]:
            filled = [h for h in holes if h in s1]
            if filled:
                return pre, s1
        if verbose:
            print('      slide 深度%d：%d 候选 pot=%s'
                  % (_d + 1, len(cand), [c[0] for c in cand[:5]]))
    return None


def conj_search2(coords, m, n, step, ov0, w_depth=1, min_w=1,
                 budget=120.0, verbose=True, use_macro=True,
                 use_slide=True, slide_depth=3):
    t0 = time.time()
    best = None
    tried = 0
    layer = [(coords, [])]
    for _d in range(w_depth):
        nl = []
        for st, pre in layer:
            for (a5, comp, mv, s1) in enum_moves(st, m, n, step,
                                                 min_size=min_w):
                nl.append((s1, pre + [(a5, mv)]))
        layer = nl
    if verbose:
        print('  让位局面 %d 个（深度%d, 分量≥%d）' % (len(layer), w_depth,
                                                      min_w))
    for st, wseq in layer:
        if time.time() - t0 > budget:
            print('  预算耗尽 %.0fs（尝试 %d）' % (time.time() - t0, tried))
            break
        _reg, _ov, holes, outside = window_of(st, m, n, step)
        if not holes:
            continue
        results = []
        if use_macro:
            for h in sorted(holes):
                for p in sorted(outside):
                    if ((h[0] - p[0]) % step or (h[1] - p[1]) % step):
                        continue
                    tried += 1
                    acts, _s = solve_single_void(st, m, n, step, hole=h,
                                                 anchor=p, keep_partial=True)
                    if acts:
                        results.append((acts, 'macro'))
        if use_slide:
            tried += 1
            sl = slide_fill(st, m, n, step, holes, max_depth=slide_depth)
            if sl:
                results.append((sl[0], 'slide'))
        for acts, kind in results:
            ok, after_c, used_c = apply_seq(st, m, n, step, acts)
            if not ok:
                continue
            # 带复位
            oka, after_all, used_all = apply_seq(
                coords, m, n, step,
                [a5 for a5, _mv in wseq] + used_c +
                [inv_act(a5, mv) for a5, mv in reversed(wseq)])
            ov2 = ov_of(after_all, m, n, step) if oka else -1
            if oka and ov2 > ov0 and (best is None or ov2 > best[1]):
                best = (used_all, ov2, after_all)
                if verbose:
                    print('    ★ %s 让位%d+填%d+复位 → ov %d→%d'
                          % (kind, len(wseq), len(used_c), ov0, ov2))
            # 不复位
            ov1b = ov_of(after_c, m, n, step)
            if ov1b > ov0 and (best is None or ov1b > best[1]):
                best = ([a5 for a5, _mv in wseq] + used_c, ov1b, after_c)
                if verbose:
                    print('    ★ %s 让位%d+填%d（不复位）→ ov %d→%d'
                          % (kind, len(wseq), len(used_c), ov0, ov1b))
    if verbose:
        print('  共轭v2 %.1fs 尝试 %d best=%s'
              % (time.time() - t0, tried, best[1] if best else None))
    return best


def conj_loop2(coords, m, n, step, max_iter=10, verbose=True, **kw):
    cur = coords
    total = []
    for it in range(max_iter):
        g = build_game(cur, m, n)
        if g.is_solved():
            return True, total, cur
        ov0 = ov_of(cur, m, n, step)
        _r, _o, holes, outside = window_of(cur, m, n, step)
        if verbose:
            print('\n[轮%d] ov=%d 洞%s 凸%s'
                  % (it, ov0, sorted(holes), sorted(outside)))
        # 现成宏先试
        res = solve_gap_macro(build_game(cur, m, n), step)
        if not isinstance(res, dict) and res and res[0]:
            acts = [tuple(a) + ((tuple(res[1][i]),) if res[1][i] else (None,))
                    for i, a in enumerate(res[0])]
            ok, after, used = apply_seq(cur, m, n, step, acts)
            if ok and build_game(after, m, n).is_solved():
                return True, total + used, after
        best = None
        for (wd, mw) in ((1, 1), (2, 3)):
            best = conj_search2(cur, m, n, step, ov0, w_depth=wd, min_w=mw,
                                budget=kw.get('budget', 100.0),
                                verbose=verbose)
            if best:
                break
        if not best:
            if verbose:
                print('  ✖ 无推进，卡住')
            return False, total, cur
        acts, ov2, after = best
        total.extend(acts)
        cur = after
        if verbose:
            print('  → 推进 %d 步 ov %d→%d' % (len(acts), ov0, ov2))
    return build_game(cur, m, n).is_solved(), total, cur


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else '267'
    if which == '278':
        m, n, step, coords = load_start('archives/2-7-8-20261001-185331.json', 31)
        print('== 2-7-8 停机局面(31步后) %dx%d step=%d' % (m, n, step))
    else:
        m, n, step, coords = load_start('archives/2-6-7-20261001-161826.json', 0)
        print('== 2-6-7 起点 %dx%d step=%d' % (m, n, step))
        t0 = time.time()
        res = solve_gap_macro(build_game(coords, m, n), step)
        print('   求解器 %.0fs → %s' % (
            time.time() - t0,
            res.get('reason') if isinstance(res, dict) else '元组'))
        if isinstance(res, dict) and res.get('actions'):
            acts = [tuple(a) + ((tuple(res['rep_cells'][i]),)
                                if res['rep_cells'][i] else (None,))
                    for i, a in enumerate(res['actions'])]
            ok, coords, _ = apply_seq(coords, m, n, step, acts)
            print('   播完 %d 步 → ok=%s' % (len(acts), ok))
    _r, ov0, holes, outside = window_of(coords, m, n, step)
    print('   当前 ov=%d 洞=%s 凸=%s' % (ov0, sorted(holes), sorted(outside)))
    t0 = time.time()
    ok, acts, after = conj_loop2(coords, m, n, step, max_iter=8)
    print('\n== %s  总 %d 步  %.0fs' % ('还原成功' if ok else '未还原',
                                        len(acts), time.time() - t0))
    if after is not None:
        _r, _o, h2, o2 = window_of(after, m, n, step)
        print('   终局 ov=%d 剩洞=%s 剩凸=%s' % (_o, sorted(h2), sorted(o2)))
    g = build_game(coords, m, n)
    print('   回放：%s' % (_replay_apply(g, acts, m, n, step)
                          and g.is_solved()))
