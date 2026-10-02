# -*- coding: utf-8 -*-
r"""「搭车填洞」轨道：贴边缺口的分量平移捎带机构（用户 07 手解归纳）。

机构三段：
  A   选一个大分量 M 朝背离洞的方向平移 k*step，腾出洞背侧的大通道；
  B   通道顶部与洞对齐的槽位 s = hole + dir*dist 若为空，找一块滑进去；
  A'  M 反向平移 k*step 回程，槽里的块被捎带落到洞位——洞被填。

验证对象：失败07 的贴底缺口 (8,3)（用户手解：v2 右侧上移 6 →
单块 (2,1) 右移 2 → 整体下移 6，(8,3) 被填）。

用法：python experiments/_ride_fill.py
"""
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver.ml.fill_macro import (build_game, window_of, gcoords,
                                  _capture_apply, _overlap_raised)

_DIR_D = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}
_DIR_OPP = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}
_SLIDE_INTO = {  # 从邻位滑进目标位：邻位偏移 -> (滑动方向)
    (-1, 0): 's', (1, 0): 'w', (0, -1): 'd', (0, 1): 'a',
}


def load0(name):
    doc = json.load(open('archives/%s.json' % name, encoding='utf-8'))
    s = doc['history']['snapshots'][0]
    b = s['bounds']
    return (frozenset((b['min_row'] + r, b['min_col'] + c)
                      for r, row in enumerate(s['matrix'])
                      for c, v in enumerate(row) if v), doc['puzzle'])


def side_blocks(g, gap, line, side):
    if gap == 'v':
        sel = (lambda p: p[1] > line) if side == 'right' else (lambda p: p[1] <= line)
    else:
        sel = (lambda p: p[0] > line) if side == 'below' else (lambda p: p[0] <= line)
    return [x for x in g.blocks if sel(tuple(x.location))]


def slide_m(g, gap, line, side, d, dist):
    """动态挑块：侧内任意组件沿 d 平移 dist（一次）。成功返回 True。"""
    for x in side_blocks(g, gap, line, side):
        g.opt(gap, line, x)
        fin, _w = g.try_move_ex(d, dist)
        if fin:
            g.commit_move(fin)
            return True
    return False


def find_ride_fill(coords, m, n, step, hole, budget=25, verbose=True):
    """搭车轨道搜索。返回 (full_acts, info) 或 (None, reason)。

    full_acts 为 5 元组列表 (gap, line, side, dir, rep_cell)，
    全部为 step 单位，可用 _capture_apply 顺序回放。
    """
    reg, ov0, holes0, out0 = window_of(coords, m, n, step)
    dirs = []
    r0, c0, (wh, ww) = reg
    if hole[0] == r0:
        dirs.append('w')
    if hole[0] == r0 + wh - 1:
        dirs.append('s')
    if hole[1] == c0:
        dirs.append('a')
    if hole[1] == c0 + ww - 1:
        dirs.append('d')
    if not dirs:
        return None, '洞不贴边'
    tried = 0
    for d in dirs:
        dr, dc = _DIR_D[d]
        d_opp = _DIR_OPP[d]
        # A 候选：与洞相关缝 × 两侧 × dist 1..3 step，方向 = d（背离洞）
        for dist_k in (1, 2, 3):
            dist = dist_k * step
            slot = (hole[0] + dr * dist, hole[1] + dc * dist)
            cands = []
            for line in range(hole[1] - 2 * step, hole[1] + 2 * step + 1, step):
                cands.append(('v', line, 'right', d, dist))
                cands.append(('v', line, 'left', d, dist))
            for line in range(hole[0] - 2 * step, hole[0] + 2 * step + 1, step):
                cands.append(('h', line, 'above', d, dist))
                cands.append(('h', line, 'below', d, dist))
            for (gap, line, side, d, dist) in cands:
                if tried >= budget:
                    return None, '预算 %d 内未找到' % budget
                # 干净盘上顺序执行 A（记录）→ 槽位检查 → B（记录）→ A'（记录）
                g = build_game(coords, m, n)
                acts = []
                okr = True
                for _ in range(dist_k):
                    if not _slide_record(g, gap, line, side, d, step, acts):
                        okr = False
                        break
                if not okr:
                    continue
                tried += 1
                coordsA = gcoords(g)
                # 槽位必须空（M 走了才空）
                if slot in coordsA:
                    continue
                # B：找槽位四邻的块滑进 slot（直接在 g 上执行并记录）
                slide_ok = False
                for (off_r, off_c), sd in _SLIDE_INTO.items():
                    src = (slot[0] + off_r, slot[1] + off_c)
                    if src not in coordsA:
                        continue
                    blk = None
                    for x in g.blocks:
                        if tuple(x.location) == src:
                            blk = x
                            break
                    if blk is None:
                        continue
                    if _slide_block_record(g, blk, sd, step, acts):
                        slide_ok = True
                        break
                if not slide_ok:
                    continue
                # A' 回程
                okp = True
                for _ in range(dist_k):
                    if not _slide_record(g, gap, line, side, d_opp, step, acts):
                        okp = False
                        break
                if not okp:
                    continue
                fin = gcoords(g)
                if hole not in fin:
                    if verbose:
                        print('  A(%s,%d,%s,%s,%d): 回程后洞未填' %
                              (gap, line, side, d, dist))
                    continue
                gate = _overlap_raised(coords, m, n, step, acts)
                _, ovF, holesF, _o = window_of(fin, m, n, step)
                if verbose:
                    print('  A(%s,%d,%s,%s,%d): 全链=%d步 洞填=%s '
                          'ov %d->%d 闸门=%s 剩洞%s'
                          % (gap, line, side, d, dist, len(acts),
                             hole in fin, ov0, ovF, gate,
                             sorted(holesF)[:5]))
                if gate:
                    return acts, {'ov0': ov0, 'ovF': ovF,
                                  'A': (gap, line, side, d, dist)}
    return None, '预算 %d 内未找到' % budget


def gap_of_blk(g, blk):
    return 'v'


def line_of_blk(g, blk, gap):
    return 0


def _slide_record(g, gap, line, side, d, step, acts):
    """动态挑块滑 step，并把 (gap,line,side,d,rep_cell) 记入 acts。"""
    for x in side_blocks(g, gap, line, side):
        loc = tuple(x.location)
        g.opt(gap, line, x)
        fin, _w = g.try_move_ex(d, step)
        if fin:
            g.commit_move(fin)
            acts.append((gap, line, side, d, loc))
            return True
    return False


def _slide_block_record(g, blk, sd, step, acts):
    """把指定块所在组件沿 sd 滑 step：枚举 (gap,line,side) 找到包含该块的
    滑动组合并执行，记录动作。"""
    loc = tuple(blk.location)
    r, c = loc
    combos = []
    for gap in ('v', 'h'):
        for line in range(c - 6, c + 7) if gap == 'v' else range(r - 6, r + 7):
            for side in (('right', 'left') if gap == 'v' else ('below', 'above')):
                combos.append((gap, line, side))
    # 优先能选中「以 blk 为代表且滑动方向可行」的组合
    for (gap, line, side) in combos:
        sel = side_blocks(g, gap, line, side)
        hit = [x for x in sel if tuple(x.location) == loc]
        if not hit:
            continue
        g.opt(gap, line, hit[0])
        fin, _w = g.try_move_ex(sd, step)
        if fin:
            # 校验落点：loc + step*dir
            dr, dc = _DIR_D[sd]
            want = (loc[0] + dr * step, loc[1] + dc * step)
            g.commit_move(fin)
            acts.append((gap, line, side, sd, loc))
            return True
    return False


def main():
    m, n, step = 8, 8, 2
    coords, pz = load0('失败07')
    reg, ov0, holes0, out0 = window_of(coords, m, n, step)
    hole = (8, 3)
    print('=== 失败07 洞%s 起点 ov=%d 窗%s ===' % (hole, ov0, reg))
    t0 = time.time()
    acts, info = find_ride_fill(coords, m, n, step, hole, verbose=True)
    dt = time.time() - t0
    if acts is None:
        print('未找到: %s (%.1fs)' % (info, dt))
    else:
        print('找到! 全链 %d 步 (%.1fs) info=%s' % (len(acts), dt, info))
        for a in acts:
            print('   ', a)


if __name__ == '__main__':
    main()
