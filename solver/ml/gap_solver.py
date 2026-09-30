# -*- coding: utf-8 -*-
r"""缺口求解器（双层共轭）「死代码」— 封壳 + 内部共轭 + 拆壳

外层（本模块新写）：边缘缺口 → 封闭孔洞。
    手法 = 甩料（切横缝把不含洞行的带向外推 step，甩出料条）
         + 垫洞（料条沿缝平移直到盖住洞的朝外邻格）。
    候选表按总步数升序逐个试，引擎 try_move 当裁判，不回溯、无搜索。
内层（复用 fill_macro）：solve_single_void couple 模式——显式指定
    「哪个凸起填哪个洞」，避免 solve_fill_macro 自动识别选错 couple。
收尾：封壳动作逆序宏（同缝同侧、方向取反、目标=侧首块）拆壳复位。

关键不变量：
    · 移动带不得含洞行/洞列（否则洞被拖走，封壳失败——实测一步直推被否）。
    · 料条平移 k = (hr - j_max) / step，j_max 为料条内与洞行同 mod 的最大行号。
    · 每步动作 5 元组 (gap, line, side, dir, rep) 带代表格，精确回放。

运行：
    D:\python\python.exe -m solver.ml.gap_solver --case save/推測題.json
    D:\python\python.exe -m solver.ml.gap_solver --all
"""
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import (build_game, gcoords, window_of,          # noqa: E402
                                  solve_single_void, _capture_apply,
                                  _replay_apply)
from solver.ml import view_rotate                                          # noqa: E402

_INV = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


# ---------------------------------------------------------------------------
# 几何判定
# ---------------------------------------------------------------------------
def _edge_of(h, r0, c0, rh, cw):
    """洞相对窗口的贴边情况 → 'L'/'R'/'U'/'D'/'CORNER'/'INNER'。"""
    hr, hc = h
    edges = []
    if hc == c0:
        edges.append('L')
    if hc == c0 + cw - 1:
        edges.append('R')
    if hr == r0:
        edges.append('U')
    if hr == r0 + rh - 1:
        edges.append('D')
    if not edges:
        return 'INNER'
    if len(edges) >= 2:
        return 'CORNER'
    return edges[0]


_ROT_FOR_EDGE = {'L': 'id', 'R': 'r180', 'U': 'ccw', 'D': 'cw'}
# ccw：上→左；cw：下→左；r180：右→左（均把缺口转到左边缘规范型）


def _hole_sealed(g, h):
    """洞四邻全有块 = 已封成封闭孔洞。"""
    coords = gcoords(g)
    hr, hc = h
    return all((hr + dr, hc + dc) in coords
               for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)))


# ---------------------------------------------------------------------------
# 封壳（左边缘规范型）
# ---------------------------------------------------------------------------
def _seal_candidates(hr, step):
    """左边缘缺口 (hr, 0) 的封壳候选序列（按总步数升序）。

    手法：甩料 (h, line, above, a) —— rows 0..line（不含洞行）西移 step，
    甩出料条 rows 0..line × cols -step..-1；
    垫洞 (v, -1, left, s) × k —— 料条南下 k*step 盖住 (hr, -1)。
    k = (hr - j_max) / step，j_max = 料条内与 hr 同 mod 的最大行号。
    返回 [(完整动作序列, 总步数)]；空列表 = 无可行候选（hr < step 等）。
    """
    j = hr % step
    cands = []
    for line in range(j, hr):                     # 甩料带 rows 0..line
        j_max = line - ((line - hr) % step)       # 料条内同 mod 最大行
        k = (hr - j_max) // step                  # 垫洞平移步数
        acts = [('h', line, 'above', 'a')]
        acts += [('v', -1, 'left', 's')] * k
        cands.append((acts, 1 + k))
    cands.sort(key=lambda t: (t[1], -t[0][0][1]))
    return cands


def _apply4(g, a4, step):
    """单步执行（四元组，目标=该侧首块）。返回 (ok, 动作5元组)。"""
    gap, line, side, _d = a4
    b = g.get_boundaries()
    if gap == 'h' and not (b['min_row'] <= line < b['max_row']):
        return False, None
    if gap == 'v' and not (b['min_col'] <= line < b['max_col']):
        return False, None
    return _capture_apply(g, a4, step)


def _seal(vg, vh, step):
    """在 view 局面上封壳。成功 → (封壳动作5元组列表, 新局面, 凸起新位置)。

    候选逐个在干净副本上试：全部动作合法 + 洞四邻全块 = 封壳成功。
    凸起位置用块对象引用跟踪（commit 改 location，读实例即得）。
    """
    hr = vh[0]
    # 原凸起块 = 甩料前窗外且不在窗口列范围的单块？这里取「行 < 0 或列越界」
    # 的第一块；单缺口单凸场景恰一块。
    b0 = vg.get_boundaries()
    pblk = None
    for blk in vg.blocks:
        r, c = blk.location
        if r < 0 or c < 0 or r > b0['max_row'] or c > b0['max_col']:
            pblk = blk
            break
    for acts, _n in _seal_candidates(hr, step):
        g2 = build_game(gcoords(vg), vg.m, vg.n)
        # 对应凸起块（同初始坐标）
        p2 = None
        if pblk is not None:
            for blk in g2.blocks:
                if tuple(blk.location) == tuple(pblk.location):
                    p2 = blk
                    break
        done = []
        ok = True
        for a4 in acts:
            okk, a5 = _apply4(g2, a4, step)
            if not okk:
                ok = False
                break
            done.append(a5)
        if ok and _hole_sealed(g2, vh):
            vp = tuple(p2.location) if p2 is not None else None
            return done, g2, vp
    return None


# ---------------------------------------------------------------------------
# 顶层：单个边缺口
# ---------------------------------------------------------------------------
def solve_edge_gap(coords, m, n, step, verbose=False):
    """单边缺口全链求解：封壳 → 内部共轭(couple) → 拆壳。

    返回 (世界动作5元组列表, stats)；失败 → (None, stats)。
    """
    t0 = time.time()
    coords = frozenset(coords)
    if len(coords) != m * n:
        return None, {'error': f'格数 {len(coords)} != {m * n}'}
    g0 = build_game(coords, m, n)
    if g0.is_solved():
        return [], {'steps': 0, 'secs': 0.0}

    (r0, c0, wh), _ov, holes, _outside = window_of(coords, m, n, step)
    if len(holes) != 1:
        return None, {'reason': f'非单缺口（窗内空位 {len(holes)} 个）'}
    h_w = next(iter(holes))
    edge = _edge_of(h_w, r0, c0, wh[0], wh[1])
    if edge == 'INNER':
        return None, {'reason': '封闭孔洞（应交填洞宏）'}
    if edge == 'CORNER':
        return None, {'reason': '角缺口（双层封壳，尚未接入）'}

    # ---- 旋转归一化：缺口 → 左边缘 ----
    name = _ROT_FOR_EDGE[edge]
    mv, nv = view_rotate.view_dims(name, m, n)
    vc = frozenset(view_rotate.rotate_xy(name, r - r0, c - c0, m, n)
                   for r, c in coords)
    vh = view_rotate.rotate_xy(name, h_w[0] - r0, h_w[1] - c0, m, n)
    vg = build_game(vc, mv, nv)

    # ---- 封壳 ----
    sealed = _seal(vg, vh, step)
    if sealed is None:
        return None, {'reason': '封壳受阻（候选全败）', 'edge': edge}
    seal_acts, vg, vp = sealed
    if verbose:
        print('  封壳 %d 步，凸起 -> %s' % (len(seal_acts), vp))

    # ---- 内部共轭（couple 显式指定）----
    if vp is None:
        return None, {'reason': '封壳后凸起丢失'}
    iacts, istats = solve_single_void(gcoords(vg), mv, nv, step,
                                      hole=vh, anchor=vp, keep_partial=True)
    if iacts is None:
        return None, {'reason': '内部共轭失败',
                      'inner': {k: v for k, v in istats.items()
                                if k != 'reason'}}
    if verbose:
        print('  内部共轭 %d 步 %s' % (len(iacts), istats))

    # 内部共轭动作回放进 vg（solve_single_void 只吃坐标不回写局面）
    if not _replay_apply(vg, iacts, mv, nv, step):
        return None, {'reason': '内部共轭回放失败'}

    # ---- 拆壳（封壳逆序宏，在已填洞局面上执行）----
    unseal_acts = []
    for a4 in reversed(seal_acts):
        a_inv = (a4[0], a4[1], a4[2], _INV[a4[3]])
        okk, a5 = _apply4(vg, a_inv, step)
        if not okk:
            break
        unseal_acts.append(a5)
    solved = vg.is_solved()

    # ---- view → world 组装 ----
    def _to_world(a):
        gap, line, side, d, rep = a
        gap2, line2, side2, d2 = view_rotate.act_to_world(
            name, gap, line, side, d, m, n)
        line2 = line2 + (r0 if gap2 == 'h' else c0)
        rr, cc = view_rotate.rep_to_world(name, rep[0], rep[1], m, n)
        return (gap2, line2, side2, d2, (rr + r0, cc + c0))

    wall = [_to_world(a) for a in seal_acts] + \
           [_to_world(a) for a in iacts] + \
           [_to_world(a) for a in unseal_acts]

    g = build_game(coords, m, n)
    ok = _replay_apply(g, wall, m, n, step)
    solved_world = ok and g.is_solved()
    stats = {'steps': len(wall),
             'seal': len(seal_acts), 'inner': len(iacts),
             'unseal': len(unseal_acts),
             'rot': name, 'edge': edge,
             'view_solved': solved, 'solved': solved_world,
             'secs': round(time.time() - t0, 3)}
    if not solved_world:
        stats['reason'] = '回放未还原' if not ok else '回放通但未还原'
    return wall, stats


def solve_inner(coords, m, n, step, hole, anchor):
    """步骤1：内部共轭——指定 (hole, anchor) 完成一次填洞（薄封装）。

    与 solve_fill_macro 的区别：显式 couple，不做自动识别（多凸起/料条
    场景自动识别会选错 couple 或多走步）。成功 = 洞格被填（不要求整盘）。
    """
    acts, stats = solve_single_void(coords, m, n, step, hole=hole,
                                    anchor=anchor, keep_partial=True)
    if acts is None:
        return None, stats
    g = build_game(frozenset(coords), m, n)
    if not _replay_apply(g, acts, m, n, step):
        return None, dict(stats, reason='回放失败')
    filled = any(tuple(b.location) == tuple(hole) for b in g.blocks)
    if not filled:
        return None, dict(stats, reason='洞格未被填')
    return acts, stats


def solve_gap(coords, m, n, step):
    """顶层分流（步骤5 雏形）：封闭孔洞 → 填洞宏；边缺口 → 本模块。"""
    coords = frozenset(coords)
    g = build_game(coords, m, n)
    if g.is_solved():
        return [], {'steps': 0, 'secs': 0.0, 'route': 'solved'}
    (r0, c0, wh), _ov, holes, _out = window_of(coords, m, n, step)
    if len(holes) == 1:
        edge = _edge_of(next(iter(holes)), r0, c0, wh[0], wh[1])
        if edge in ('L', 'R', 'U', 'D'):
            wall, stats = solve_edge_gap(coords, m, n, step)
            return wall, dict(stats, route='edge_gap')
    # 其余（封闭孔洞/多洞/角缺口）交填洞宏驱动
    from solver.ml.fill_macro import solve_fill_macro
    res = solve_fill_macro(build_game(coords, m, n), step)
    if isinstance(res, dict) and res.get('type') in ('fill_fail',):
        return None, {'reason': res.get('reason', '填洞宏失败'),
                      'route': 'fill_macro'}
    return res.get('actions', []), {'route': 'fill_macro',
                                    'steps': len(res.get('actions', []))}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_case(path):
    data = json.load(open(path, encoding='utf-8'))
    s0 = data['history']['snapshots'][0]
    b = s0['bounds']
    coords = frozenset((ri + b['min_row'], c + b['min_col'])
                       for ri, row in enumerate(s0['matrix'])
                       for c, v in enumerate(row) if v)
    pz = data['puzzle']
    return coords, pz['m'], pz['n'], pz['step']


def _main():
    args = sys.argv[1:]
    if args and args[0] == '--case':
        coords, m, n, step = _load_case(args[1])
        acts, stats = solve_edge_gap(coords, m, n, step, verbose=True)
        print('结果:', '成功' if acts else '失败', stats)
        return
    if args and args[0] == '--all':
        save = os.path.join(_ROOT, 'save')
        for fname in ('推測題.json', '推測題2.json', '推測題3.json'):
            path = os.path.join(save, fname)
            if not os.path.exists(path):
                continue
            coords, m, n, step = _load_case(path)
            print('=' * 60)
            print(fname)
            acts, stats = solve_edge_gap(coords, m, n, step, verbose=True)
            print('结果:', '成功' if acts else '失败', stats)
        return
    print(__doc__)


if __name__ == '__main__':
    _main()
