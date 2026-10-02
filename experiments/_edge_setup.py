# -*- coding: utf-8 -*-
r"""贴边缺口的「造窗外邻居」setup 轨道——参数化搜索验证。

用户 2026-10-01/02 手解（失败06/失败07 存档）归纳的通则：
  缺口方向在窗外（贴边缺口）时，先用一次「外层分量平移」A 把窗外的空区
  填上块（等效把窗口往外扩），缺口变普通洞/完美洞，再按标准公式填，
  最后 A' 还原。闸门只看全链净效果（段级聚拢度验收原则）。

本脚本对 失败06 的 (0,2)/(1,0) 与 失败07 的 (8,3) 自动搜索 A：
  A = (gap, line, side, dir, dist)，dir = 把分量推向洞的贴边方向，
  dist ∈ {step, 2*step, 3*step}。A 后要求洞的贴边方向邻居出现块。
  然后跑现有 solve_single_void 填洞，最后 A' 动态还原，整体过聚拢度闸门。

用法：python experiments/_edge_setup.py
"""
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver.ml.fill_macro import (build_game, window_of, gcoords,
                                  _capture_apply, _overlap_raised,
                                  solve_single_void)
from solver.ml.gap_solver import solve_edge_gap, _vacancy_couple_hook

_DIR_OPP = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


def load0(name):
    doc = json.load(open('archives/%s.json' % name, encoding='utf-8'))
    s = doc['history']['snapshots'][0]
    b = s['bounds']
    return (frozenset((b['min_row'] + r, b['min_col'] + c)
                      for r, row in enumerate(s['matrix'])
                      for c, v in enumerate(row) if v), doc['puzzle'])


def side_of(gap, line, side, blocks):
    """侧内块位置集合。"""
    if gap == 'v':
        sel = (lambda p: p[1] > line) if side == 'right' else (lambda p: p[1] <= line)
    else:
        sel = (lambda p: p[0] > line) if side == 'below' else (lambda p: p[0] <= line)
    return [x for x in blocks if sel(tuple(x.location))]


def slide_dyn(g, gap, line, side, d, dist):
    """动态挑块执行一次滑动：遍历侧内所有块，找到能滑的组件即提交。

    返回 (ok, rep_cell, steps)；steps 为拆成 step 单位的动作列表
    （每个动作带当次执行时的 rep_cell，保证顺序回放时定位一致）。
    """
    cands = side_of(gap, line, side, g.blocks)
    for x in cands:
        g.opt(gap, line, x)
        fin, _why = g.try_move_ex(d, dist)
        if not fin:
            continue
        # 记录拆解动作：先回滚再逐 step 执行（try_move_ex 是预测不改盘）
        # 简化：直接按最终位置反推每 step 的 rep_cell 不可靠，
        # 改为逐 step 重放：先 commit 预测结果前先撤销——引擎无撤销，
        # 因此这里改为：拒绝 commit，重新逐 step 执行并记录。
        rep0 = tuple(x.location)
        # 逐 step 执行并记录
        steps = []
        ok_all = True
        cur_rep = rep0
        for _ in range(dist // _step_of(g)):
            blk = None
            for y in g.blocks:
                if tuple(y.location) == cur_rep:
                    blk = y
                    break
            if blk is None:
                ok_all = False
                break
            g.opt(gap, line, blk)
            f2, _w2 = g.try_move_ex(d, _step_of(g))
            if not f2:
                ok_all = False
                break
            g.commit_move(f2)
            steps.append((gap, line, side, d, cur_rep))
            # 分量平移后，原块到了新位置
            dr, dc = _dir_delta(d)
            cur_rep = (cur_rep[0] + dr * _step_of(g),
                       cur_rep[1] + dc * _step_of(g))
        if ok_all:
            return True, rep0, steps
        # 逐 step 失败：盘面已被部分推进，无法就地回滚——放弃该组件。
        # （调用方应在干净的试验盘上重试；本函数假定 g 可弃。）
        return False, None, []
    return False, None, []


_DIR_D = {}


def _dir_delta(d):
    return {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}[d]


def _step_of(g):
    return g.step if hasattr(g, 'step') else _GLOBAL_STEP


_GLOBAL_STEP = 2


def edge_dirs(hole, reg):
    """洞的贴边方向 → 分量应推向的方向（把窗外空区填上块）。"""
    r0, c0, (wh, ww) = reg[0], reg[1], reg[2]
    out = []
    if hole[0] == r0:
        out.append('w')
    if hole[0] == r0 + wh - 1:
        out.append('s')
    if hole[1] == c0:
        out.append('a')
    if hole[1] == c0 + ww - 1:
        out.append('d')
    return out


def neighbor_state(coords, hole, d):
    """洞在 d 方向的窗外邻居是否有块（贴边判定）。"""
    dr, dc = _dir_delta(d)
    return (hole[0] + dr, hole[1] + dc) in coords


def find_edge_setup(coords, m, n, step, hole, budget=8, verbose=True):
    """参数化搜索造邻居 setup 轨道。返回 (full_acts, info) 或 (None, reason)。"""
    _GLOBAL_STEP = step
    reg, ov0, holes0, out0 = window_of(coords, m, n, step)
    hook = _vacancy_couple_hook(gap_only=False)
    dirs = edge_dirs(hole, reg)
    if not dirs:
        return None, '洞不贴边'
    tried = 0
    for d in dirs:
        dr, dc = _dir_delta(d)
        # 枚举：与洞同行/列附近的缝 × 两侧 × 1..3 step
        cands = []
        for dist_k in (1, 2, 3):
            dist = dist_k * step
            for line in range(hole[1] - 2 * step, hole[1] + 2 * step + 1, step):
                for side in ('right', 'left'):
                    cands.append(('v', line, side, d, dist))
            for line in range(hole[0] - 2 * step, hole[0] + 2 * step + 1, step):
                for side in ('above', 'below'):
                    cands.append(('h', line, side, d, dist))
        for (gap, line, side, d, dist) in cands:
            if tried >= budget:
                break
            # 在试验盘上执行 A
            g = build_game(coords, m, n)
            cands_blocks = side_of(gap, line, side, g.blocks)
            if not cands_blocks:
                continue
            ok, rep0, stepsA = slide_dyn(g, gap, line, side, d, dist)
            if not ok:
                continue
            tried += 1
            coordsA = gcoords(g)
            # 筛选：洞的贴边方向邻居出现块（洞不再贴边）
            dr, dc = _dir_delta(d)
            if (hole[0] + dr, hole[1] + dc) not in coordsA:
                continue
            # A 后枚举窗外凸起，跑现有 couple 机制（补缺链/填洞宏/convoy）
            regA, ovA, holesA, outA = window_of(coordsA, m, n, step)
            actsB = None
            for p in sorted(outA):
                if (hole[0] - p[0]) % step or (hole[1] - p[1]) % step:
                    continue
                actsB, stB = hook(coordsA, m, n, step, hole, p)
                if actsB is not None:
                    break
            if actsB is None:
                if verbose:
                    print('  A(%s,%d,%s,%s,%d) 后 couple 全败: %s'
                          % (gap, line, side, d, dist,
                             str(stB.get('reason', '?'))[:50]))
                continue
            # A' 还原：同缝同侧反向同距离（动态挑块）
            g2 = build_game(coordsA, m, n)
            for a5 in actsB:
                okr, _ = _capture_apply(g2, (a5[0], a5[1], a5[2], a5[3], a5[4]), step)
                if not okr:
                    break
            okp = True
            d_opp = _DIR_OPP[d]
            for _ in range(dist // step):
                found = False
                for x in side_of(gap, line, side, g2.blocks):
                    g2.opt(gap, line, x)
                    fin, _w = g2.try_move_ex(d_opp, step)
                    if fin:
                        g2.commit_move(fin)
                        found = True
                        break
                if not found:
                    okp = False
                    break
            if not okp:
                if verbose:
                    print('  A(%s,%d,%s,%s,%d) 还原失败' % (gap, line, side, d, dist))
                continue
            # 全链 = A + B + A'，整体闸门（对 A 前局面）
            full = list(stepsA) + [tuple(a[:5]) for a in actsB] + \
                   [(gap, line, side, d_opp, None)] * (dist // step)
            g3 = build_game(coords, m, n)
            okall = True
            for a5 in full:
                rc = a5[4] if a5[4] is not None else None
                okr, _ = _capture_apply(g3, (a5[0], a5[1], a5[2], a5[3], rc), step)
                if not okr:
                    okall = False
                    break
            if not okall:
                if verbose:
                    print('  A(%s,%d,%s,%s,%d) 全链回放失败' % (gap, line, side, d, dist))
                continue
            fin = gcoords(g3)
            gate = _overlap_raised(coords, m, n, step, full)
            _, ovF, holesF, _o = window_of(fin, m, n, step)
            filled = hole in fin
            if verbose:
                print('  A(%s,%d,%s,%s,%d): %d步B 全链=%d步 洞填=%s ov %d->%d 闸门=%s 剩洞%s'
                      % (gap, line, side, d, dist, len(actsB), len(full),
                         filled, ov0, ovF, gate, sorted(holesF)[:5]))
            if gate and filled:
                return full, {'A': (gap, line, side, d, dist), 'ov0': ov0, 'ovF': ovF}
    return None, '预算 %d 内无可用 A' % budget


def main():
    m, n, step = 8, 8, 2
    cases = [
        ('失败06', (0, 2), '贴顶缺口'),
        ('失败06', (1, 0), '贴左缺口'),
        ('失败07', (8, 3), '贴底缺口'),
    ]
    for name, hole, tag in cases:
        coords, pz = load0(name)
        reg, ov0, holes0, out0 = window_of(coords, m, n, step)
        print('=== %s 洞%s (%s) 起点 ov=%d ===' % (name, hole, tag, ov0))
        t0 = time.time()
        full, info = find_edge_setup(coords, m, n, step, hole, verbose=True)
        dt = time.time() - t0
        if full is None:
            print('  -> 未找到: %s  (%.1fs)' % (info, dt))
        else:
            print('  -> 找到! A=%s 全链 %d 步 (%.1fs)' % (info['A'], len(full), dt))
        print()


if __name__ == '__main__':
    main()
