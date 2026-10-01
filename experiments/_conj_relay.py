# 共轭让位原型：W(让位) ... C(填洞) ... W'(复位)
# 动机：2-7-8 停机局面需 A B C C B' A' 六步共轭（ov 49→42→55，中间必须下降），
#      盲搜深度 6 不可行；用「让位-填-复位」模板把搜索压成 枚举W × 枚举C。
import json
import sys
import time
from collections import deque
sys.path.insert(0, '.')

from solver.ml.fill_macro import (build_game, gcoords, window_of,
                                  _capture_apply, _replay_apply,
                                  _connected_ml, _comps_ml, _overlap_raised,
                                  solve_single_void, _belt_shift_fill)
from solver.ml.gap_solver import solve_gap_macro

_DIRS = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}
_OPP = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


def enum_moves(coords, m, n, step, min_size=1, max_size=None):
    """枚举全部合法单步（含同缝多分量）→ [(act5, comp, mv, nxt)]。"""
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
                    st = (lambda q: q[0] <= line) if side == 'above' \
                        else (lambda q: q[0] > line)
                else:
                    st = (lambda q: q[1] <= line) if side == 'left' \
                        else (lambda q: q[1] > line)
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
                        ok = True
                        for k in range(1, step + 1):
                            mvk = frozenset((q[0] + dr * k, q[1] + dc * k)
                                            for q in comp)
                            if mvk & rest or not _connected_ml(rest | mvk):
                                ok = False
                                break
                        if not ok:
                            continue
                        mv = frozenset((q[0] + dr * step, q[1] + dc * step)
                                       for q in comp)
                        out.append(((gap, line, side, d, min(comp)),
                                    comp, mv, rest | mv))
    return out


def ov_of(coords, m, n, step):
    return window_of(coords, m, n, step)[1]


def apply_seq(coords, m, n, step, acts):
    """回放动作序列 → (ok, 新coords, 实际生效的act5列表)"""
    g = build_game(coords, m, n)
    used = []
    for a in acts:
        ok, a5 = _capture_apply(g, a, step)
        if not ok:
            return False, coords, used
        used.append(a5)
    return True, gcoords(g), used


def inv_act(a5, mv):
    return (a5[0], a5[1], a5[2], _OPP[a5[3]], min(mv))


def conj_search(coords, m, n, step, ov0, w_depth=1, c_depth=2,
                budget=60.0, min_w=3, verbose=True):
    """让位-填-复位搜索。返回 (整段act5, 新ov) 或 None。"""
    t0 = time.time()
    W0 = enum_moves(coords, m, n, step, min_size=min_w)
    if verbose:
        print('  让位候选 %d 个（分量≥%d）' % (len(W0), min_w))
    best = None
    # W 层（BFS，深度 w_depth）
    layer = [(coords, [])]
    for _d in range(w_depth):
        nxt_layer = []
        for st, pre in layer:
            for (a5, comp, mv, s1) in enum_moves(st, m, n, step,
                                                 min_size=min_w):
                nxt_layer.append((s1, pre + [(a5, mv)]))
        layer = nxt_layer
        if verbose:
            print('  W 深度%d：%d 个局面' % (_d + 1, len(layer)))
    tried = 0
    for st, wseq in layer:
        if time.time() - t0 > budget:
            if verbose:
                print('  预算耗尽（%.0fs）尝试 %d' % (time.time() - t0, tried))
            break
        # C：在让位后局面跑现有宏
        _reg, _ov1, holes, outside = window_of(st, m, n, step)
        cands = []
        for h in sorted(holes):
            for p in sorted(outside):
                if ((h[0] - p[0]) % step or (h[1] - p[1]) % step):
                    continue
                cands.append((h, p))
        for (h, p) in cands:
            tried += 1
            acts, _st = solve_single_void(st, m, n, step, hole=h, anchor=p,
                                          keep_partial=True)
            if not acts:
                continue
            # 复位（逆序）
            ok, after_c, used_c = apply_seq(st, m, n, step, acts)
            if not ok:
                continue
            full = [a5 for a5, _mv in wseq] + used_c
            oka, after_all, used_all = apply_seq(
                coords, m, n, step,
                full + [inv_act(a5, mv) for a5, mv in reversed(wseq)])
            ov2 = ov_of(after_all, m, n, step) if oka else -1
            if verbose and ov2 > ov0:
                print('    ★ %s←%s 让位%d步+填%d步+复位 → ov %d→%d'
                      % (h, p, len(wseq), len(used_c), ov0, ov2))
            if oka and ov2 > ov0 and (best is None or ov2 > best[1]):
                best = (used_all, ov2, after_all)
            # 不复位版本
            ov1b = ov_of(after_c, m, n, step)
            if ov1b > ov0 and (best is None or ov1b > best[1]):
                best = (full, ov1b, after_c)
    if verbose:
        print('  共轭搜索 %.1fs 尝试 %d 次 best=%s'
              % (time.time() - t0, tried,
                 best[1] if best else None))
    return best


def load_start(f, idx=0):
    d = json.load(open(f, encoding='utf-8'))
    m, n, step = d['puzzle']['m'], d['puzzle']['n'], d['puzzle']['step']
    s = d['history']['snapshots'][idx]
    b = s['bounds']
    coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                       for i, row in enumerate(s['matrix'])
                       for j, v in enumerate(row) if v)
    return m, n, step, coords


def conj_loop(coords, m, n, step, max_iter=12, min_w=3, verbose=True):
    """迭代：每轮现有宏 → 失败则共轭让位推进一步，直到还原或卡住。"""
    cur = coords
    total = []
    for it in range(max_iter):
        g = build_game(cur, m, n)
        if g.is_solved():
            return True, total, cur
        ov0 = ov_of(cur, m, n, step)
        _r, _o, holes, outside = window_of(cur, m, n, step)
        if verbose:
            print('\n[轮%d] ov=%d 洞%d 凸%d' % (it, ov0, len(holes),
                                               len(outside)))
        # 先试便宜的：现有单洞/多洞宏
        res = solve_gap_macro(build_game(cur, m, n), step)
        if not isinstance(res, dict) and res and res[0]:
            acts = [tuple(a) + ((tuple(res[1][i]),) if res[1][i] else (None,))
                    for i, a in enumerate(res[0])]
            ok, after, used = apply_seq(cur, m, n, step, acts)
            if ok and build_game(after, m, n).is_solved():
                return True, total + used, after
        best = conj_search(cur, m, n, step, ov0, w_depth=1,
                           budget=90.0, min_w=min_w, verbose=verbose)
        if not best:
            if verbose:
                print('  ✖ 共轭也无推进，卡住')
            return False, total, cur
        acts, ov2, after = best
        total.extend(acts)
        cur = after
        if verbose:
            print('  → 推进 %d 步 ov %d→%d' % (len(acts), ov0, ov2))
    return build_game(cur, m, n).is_solved(), total, cur


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else '278'
    if which == '278':
        # 2-7-8 停机局面 = B 存档第31步后
        m, n, step, coords = load_start('save/2-7-8-20261001-185331.json', 31)
        print('== 2-7-8 停机局面(31步后)：%dx%d step=%d' % (m, n, step))
    else:
        m, n, step, coords = load_start('save/2-6-7-20261001-161826.json', 0)
        print('== 2-6-7 起点：%dx%d step=%d' % (m, n, step))
        t0 = time.time()
        res = solve_gap_macro(build_game(coords, m, n), step)
        print('   求解器 %.0fs → %s' % (time.time() - t0,
              res.get('reason') if isinstance(res, dict) else '元组'))
        if isinstance(res, dict) and res.get('actions'):
            acts = [tuple(a) + ((tuple(res['rep_cells'][i]),)
                                if res['rep_cells'][i] else (None,))
                    for i, a in enumerate(res['actions'])]
            ok, coords, _ = apply_seq(coords, m, n, step, acts)
            print('   播完 %d 步 → ok=%s' % (len(acts), ok))
    ov0 = ov_of(coords, m, n, step)
    _reg, _ov, holes, outside = window_of(coords, m, n, step)
    print('   当前 ov=%d 洞=%s' % (ov0, sorted(holes)))
    print('   凸=%s' % (sorted(outside),))
    t0 = time.time()
    ok, acts, after = conj_loop(coords, m, n, step, max_iter=12, min_w=3)
    print('\n== 结果：%s  总 %d 步  %.0fs' % (
        '还原成功' if ok else '未还原', len(acts), time.time() - t0))
    if after is not None:
        _r, _o, h2, o2 = window_of(after, m, n, step)
        print('   终局 ov=%d 剩洞=%s 剩凸=%s' % (_o, sorted(h2), sorted(o2)))
    # 整段回放验证
    g = build_game(coords, m, n)
    if _replay_apply(g, acts, m, n, step):
        print('   回放合法：%s' % g.is_solved())
    else:
        print('   回放失败！')
