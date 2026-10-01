# 「临时粘一下」setup 实验：把块移进洞的 8 邻缺口 → 洞变完美 → 跑标准填洞宏 → 逆复位
import sys
import time
sys.path.insert(0, '.')

from solver.ml.fill_macro import (build_game, gcoords, window_of,
                                  _capture_apply, _replay_apply,
                                  _connected_ml, _comps_ml,
                                  solve_single_void)
from experiments._conj_relay import apply_seq, ov_of, load_start
from experiments._dist_probe import enum_moves_d
from experiments._perfect_check import endgame_267

_DIRS = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}
_OPP = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


def gaps_of(coords, h):
    """洞 h 的 8 邻空位。"""
    return [(h[0] + dr, h[1] + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
            if (dr, dc) != (0, 0) and (h[0] + dr, h[1] + dc) not in coords]


def paste_search(coords, m, n, step, target, budget=120.0, verbose=True):
    """对目标洞 target：枚举单步动作找「粘缺口」的 setup，
    粘后洞完美 → 跑 couple 宏 → 逆复位 → ov 验收。"""
    t0 = time.time()
    ov0 = ov_of(coords, m, n, step)
    _r, _o, holes, outside = window_of(coords, m, n, step)
    # 同 mod 的凸
    anchors = [p for p in outside
               if not ((target[0] - p[0]) % step or (target[1] - p[1]) % step)]
    gaps0 = gaps_of(coords, target)
    if verbose:
        print('目标洞 %s 缺口%s 同mod凸%s ov0=%d'
              % (target, gaps0, anchors, ov0))
    best = None
    # setup 深度最多 2 步（粘多个缺口）
    layer = [(coords, [])]
    seen = {coords}
    for depth in (1, 2):
        nxt = []
        for st, pre in layer:
            if time.time() - t0 > budget:
                break
            for (a5, comp, mv, s1) in enum_moves_d(st, m, n, [step],
                                                   min_size=1):
                if s1 in seen:
                    continue
                seen.add(s1)
                gaps1 = gaps_of(s1, target)
                # 展开：缺口变少、或目标洞被填、或第一层全保留
                if (len(gaps1) < len(gaps_of(st, target))
                        or target in s1 or depth == 1):
                    nxt.append((s1, pre + [(a5, mv)]))
        layer = nxt
        if verbose:
            print('  setup 深度%d：%d 个候选' % (depth, len(layer)))
        for st, pre in layer:
            if time.time() - t0 > budget:
                break
            # 情形A：setup 动作直接把目标洞填掉了 → 直接验收
            if target in st:
                oka = True
                used_all = [a for a, _mv in pre]
                g = build_game(coords, m, n)
                for a in used_all:
                    okx, _a5 = _capture_apply(g, a, step)
                    if not okx:
                        oka = False
                        break
                if oka:
                    after_all = gcoords(g)
                    ov2 = ov_of(after_all, m, n, step)
                    if verbose:
                        print('    ★ setup%d步直接填掉目标洞 → ov %d→%d'
                              % (len(pre), ov0, ov2))
                    if ov2 > ov0 and (best is None or ov2 > best[1]):
                        best = (used_all, ov2, after_all)
                continue
            gaps1 = gaps_of(st, target)
            if gaps1:
                continue          # 还不完美，继续下一层
            # 洞完美 → 跑 couple 宏
            for p in anchors:
                tried_acts, _s = solve_single_void(st, m, n, step, hole=target,
                                                   anchor=p,
                                                   keep_partial=True)
                if not tried_acts:
                    continue
                ok, after_c, used_c = apply_seq(st, m, n, step, tried_acts)
                if not ok:
                    continue
                # 逆复位
                invs = [ (a[0], a[1], a[2], _OPP[a[3]], min(mv))
                         for (a, mv) in reversed(pre) ]
                full = [a for a, _mv in pre] + used_c
                g = build_game(coords, m, n)
                okall = True
                used_all = []
                for a in full + invs:
                    okx, a5 = _capture_apply(g, a, step)
                    if not okx:
                        okall = False
                        break
                    used_all.append(a5)
                if not okall:
                    continue
                after_all = gcoords(g)
                ov2 = ov_of(after_all, m, n, step)
                if verbose:
                    print('    ★ setup%d步+宏%d步+复位 → ov %d→%d 剩洞%s'
                          % (len(pre), len(used_c), ov0, ov2,
                             sorted(window_of(after_all, m, n, step)[2])))
                if ov2 > ov0 and (best is None or ov2 > best[1]):
                    best = (used_all, ov2, after_all)
                # 不复位版
                ov1b = ov_of(after_c, m, n, step)
                if ov1b > ov0 and (best is None or ov1b > best[1]):
                    best = ([a for a, _mv in pre] + used_c, ov1b, after_c)
        if best:
            break
    if verbose:
        print('  粘补搜索 %.1fs best=%s' % (
            time.time() - t0, best[1] if best else None))
    return best


if __name__ == '__main__':
    m, n, step, coords = endgame_267()
    ov0 = ov_of(coords, m, n, step)
    print('2-6-7 残局 ov=%d' % ov0)
    for target in [(5, 5), (4, 0)]:
        print('\n===== 粘补目标洞 %s =====' % (target,))
        best = paste_search(coords, m, n, step, target, budget=150.0)
        if best:
            acts, ov2, after = best
            print('  ✔ 找到 %d 步 ov %d→%d' % (len(acts), ov0, ov2))
            coords = after
            ov0 = ov2
    _r, _o, h2, o2 = window_of(coords, m, n, step)
    print('\n终局 ov=%d 洞=%s 凸=%s' % (_o, sorted(h2), sorted(o2)))
