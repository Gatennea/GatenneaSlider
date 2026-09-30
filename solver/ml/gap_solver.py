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
                                  solve_single_void, solve_fill_macro,
                                  _capture_apply, _replay_apply, _Runner)
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
    """单步执行（四/五元组均可，五元组 rep 优先选块）。返回 (ok, 动作5元组)。"""
    gap, line, side, _d = a4[:4]
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
def _solve_couple(coords, m, n, step, h, p, keep_partial=True):
    """couple 内部共轭：流程与 solve_single_void 相同，但 couple 校验用
    本质判定（h=空位、p=块、同 mod），不经窗口——封壳料条会把
    find_best_window 的窗口撑得漂移，凸起可能被圈进窗内而遭误杀。
    （fill_macro 本体不动，此处仅绕过其入口预检，_Runner 语义完全一致。）
    """
    coords = frozenset(coords)
    if h in coords or p not in coords:
        return None, {'reason': 'couple坐标无效（hole须为空位、anchor须为块）'}
    if (h[0] - p[0]) % step or (h[1] - p[1]) % step:
        return None, {'reason': '洞凸不同mod'}
    (r0, c0, _wh), _ov, _holes, _out = window_of(coords, m, n, step)
    name = view_rotate.choose_rot(p[0] - r0, p[1] - c0, m, n)
    if name == 'id':
        g = build_game(coords, m, n)
        return _Runner(g, m, n, step, h=tuple(h), p=tuple(p),
                       require_solved=False,
                       keep_partial=keep_partial).run()
    vc = frozenset(view_rotate.rotate_xy(name, r - r0, c - c0, m, n)
                   for r, c in coords)
    mv, nv = view_rotate.view_dims(name, m, n)
    vg = build_game(vc, mv, nv)
    vh = view_rotate.rotate_xy(name, h[0] - r0, h[1] - c0, m, n)
    vp = view_rotate.rotate_xy(name, p[0] - r0, p[1] - c0, m, n)
    acts, stats = _Runner(vg, mv, nv, step, h=vh, p=vp,
                          require_solved=False,
                          keep_partial=keep_partial).run()
    if acts is None:
        return None, dict(stats, rot=name)
    wacts = []
    for gap, line, side, d, rep in acts:
        gap2, line2, side2, d2 = view_rotate.act_to_world(
            name, gap, line, side, d, m, n)
        line2 = line2 + (r0 if gap2 == 'h' else c0)
        rr, cc = view_rotate.rep_to_world(name, rep[0], rep[1], m, n)
        wacts.append((gap2, line2, side2, d2, (rr + r0, cc + c0)))
    return wacts, dict(stats, rot=name)


def _find_bump(vg):
    """窗外第一块（按窗口 0..m-1 × 0..n-1 判定，单缺口单凸场景恰一块）。"""
    mv, nv = vg.m, vg.n
    for blk in vg.blocks:
        r, c = blk.location
        if r < 0 or r >= mv or c < 0 or c >= nv:
            return blk
    return None


def _bumpcol_chain(vg, vh, step, verbose=False):
    """凸起与洞同列（规范型窗外端点）时的「专列」全链。

    规范型：洞 (hr,0) 左边缘，凸起 (−1,0)（上端）或 (mv,0)（下端）。
    手法（用户 2-6-6 七步解）：凸起全程骑在料条上，不单独搬运——
    甩含凸起的带横移出窗 → 料条沿列平移把凸起捎到 (hr,−step)，
    西邻 (hr,−1) 留空作门 → 凸起单块东移 step 入洞 → 逆序拆壳。
    返回 (view 动作5元组列表, stats) 或 (None, reason)。
    """
    mv = vg.m
    hr = vh[0]
    pblk = _find_bump(vg)
    if pblk is None:
        return None, '专列：找不到窗外凸起'
    pr, pc = pblk.location
    top = (pc == 0 and pr == -1)
    bot = (pc == 0 and pr == mv)
    if not (top or bot):
        return None, '专列：凸起不在洞列端点 %s' % ((pr, pc),)
    dist = (hr + 1) if top else (mv - hr)
    if dist % step:
        return None, '专列：凸起洞距 %d 非步长整倍' % dist
    k = dist // step
    p0 = (pr, pc)

    if top:
        # A：行≤j（含凸起）西移 step，竖条行 0..j；B：竖条南移 k 次
        # （凸起随带到 (hr,−step)，竖条终行 hr+1..，西门恒开）；
        # C：h 缝 line=hr 选上侧，凸起单块东移入洞。
        js = list(range(hr - 1, -1, -1))
        for j in js:
            seal4 = [('h', j, 'above', 'a', p0)]
            inner4 = [('v', -1, 'left', 's')] * k + \
                     [('h', hr, 'above', 'd')]
            # 拆壳 rep=None → 侧首块语义（凸起已入洞，不能再用它定位）
            unseal4 = [('v', -1, 'left', 'w', None)] * k + \
                      [('h', j, 'above', 'd', None)]
            wall, stats = _run_chain(vg, seal4, inner4, unseal4,
                                     p0, step)
            if wall is not None:
                if verbose:
                    print('  专列(上端)：j=%d k=%d' % (j, k))
                return wall, stats
    else:
        # A：行 j'..mv−1（不含凸起行）西移 + 凸起单块西移挂竖条车尾；
        # B：竖条(含凸起)北移 k 次（凸起到 (hr,−step)，竖条终行 ≤hr−1，门开）；
        # C：h 缝 line=hr−1 选下侧，凸起单块东移入洞。
        # （不直接甩含凸起行：同行门位块会随竖条堵住 (hr,−1)。）
        for jp in range(hr + 1, mv):
            seal4 = [('h', jp - 1, 'below', 'a', p0),
                     ('h', mv - 1, 'below', 'a', p0)]
            inner4 = [('v', -1, 'left', 'w')] * k + \
                     [('h', hr - 1, 'below', 'd')]
            unseal4 = [('v', -1, 'left', 's', None)] * k + \
                      [('h', jp - 1, 'below', 'd', None)]
            wall, stats = _run_chain(vg, seal4, inner4, unseal4,
                                     p0, step)
            if wall is not None:
                if verbose:
                    print('  专列(下端)：j\'=%d k=%d' % (jp, k))
                return wall, stats
    return None, '专列：候选全败'


def _run_chain(vg, seal4, inner4, unseal4, p0, step):
    """在副本上执行 封壳→内部→拆壳 三段（rep 动态跟踪凸起）。

    全部动作合法且最终 solved 才成功。
    返回 (view 动作5元组列表, stats) 或 (None, None)。
    """
    g2 = build_game(gcoords(vg), vg.m, vg.n)
    p2 = None
    for blk in g2.blocks:
        if tuple(blk.location) == tuple(p0):
            p2 = blk
            break
    segs, nseg = [], {'seal': 0, 'inner': 0, 'unseal': 0}
    for name, acts in (('seal', seal4), ('inner', inner4),
                       ('unseal', unseal4)):
        out = []
        for a4 in acts:
            a = a4 if len(a4) == 5 else a4 + (tuple(p2.location),)
            okk, a5 = _apply4(g2, a, step)
            if not okk:
                return None, None
            out.append(a5)
        segs += out
        nseg[name] = len(out)
    if not g2.is_solved():
        return None, None
    return segs, nseg


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

    # ---- view → world 组装 ----
    def _to_world(a):
        gap, line, side, d, rep = a
        gap2, line2, side2, d2 = view_rotate.act_to_world(
            name, gap, line, side, d, m, n)
        line2 = line2 + (r0 if gap2 == 'h' else c0)
        rr, cc = view_rotate.rep_to_world(name, rep[0], rep[1], m, n)
        return (gap2, line2, side2, d2, (rr + r0, cc + c0))

    # ---- 封壳 ----（先试「专列」：凸起与洞同列的窗外端点，2-6-6 型）
    pblk0 = _find_bump(vg)
    if pblk0 is not None and pblk0.location[1] == 0 and \
            pblk0.location[0] in (-1, mv):
        res = _bumpcol_chain(vg, vh, step, verbose=verbose)
        if res[0] is not None:
            wall5, bstats = res
            wall = [_to_world(a) for a in wall5]
            g = build_game(coords, m, n)
            ok = _replay_apply(g, wall, m, n, step)
            solved_world = ok and g.is_solved()
            stats = {'steps': len(wall),
                     'seal': bstats['seal'], 'inner': bstats['inner'],
                     'unseal': bstats['unseal'],
                     'rot': name, 'edge': edge, 'route': 'bumpcol',
                     'view_solved': True, 'solved': solved_world,
                     'secs': round(time.time() - t0, 3)}
            if not solved_world:
                stats['reason'] = '专列回放未还原'
                return None, stats
            return wall, stats
        if verbose:
            print('  专列未成(%s)，回常规封壳' % res[1])
    sealed = _seal(vg, vh, step)
    if sealed is None:
        return None, {'reason': '封壳受阻（候选全败）', 'edge': edge}
    seal_acts, vg, vp = sealed
    if verbose:
        print('  封壳 %d 步，凸起 -> %s' % (len(seal_acts), vp))

    # ---- 内部共轭（couple 显式指定，本质校验绕窗口）----
    if vp is None:
        return None, {'reason': '封壳后凸起丢失'}
    iacts, istats = _solve_couple(gcoords(vg), mv, nv, step,
                                  vh, vp, keep_partial=True)
    if iacts is None:
        return None, {'reason': '内部共轭失败: %s' % istats.get('reason', '?'),
                      'inner': {k: v for k, v in istats.items()
                                if k not in ('reason', 'partial')}}
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

    # ---- view → world 组装（_to_world 已在封壳前定义）----
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
    couple 校验用本质判定（不受窗口漂移影响），见 _solve_couple。
    """
    acts, stats = _solve_couple(coords, m, n, step, hole, anchor,
                                keep_partial=True)
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
    """顶层分流：封闭孔洞 → 填洞宏；边缺口 → 本模块。

    返回 (动作5元组列表, stats)；fill_macro 侧结果原样透传为
    ((actions4, reps), stats)。
    """
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
    if isinstance(res, tuple):
        return res, {'route': 'fill_macro', 'steps': len(res[0])}
    return None, {'reason': res.get('reason', '填洞宏失败'),
                  'route': 'fill_macro'}


# ---------------------------------------------------------------------------
# GUI 求解器入口（与 SOLVER_ALGORITHMS 统一签名）
# ---------------------------------------------------------------------------
def solve_gap_macro(game, step, cancel_check=None, progress_callback=None,
                    **kwargs):
    """补缺宏（GUI 入口）：单边缺口 → 封壳+内部共轭+拆壳；其余交填洞宏。

    返回协议与 solve_fill_macro 一致：
    · 成功 → (actions4, rep_cells)；
    · 失败 → {'type': 'fill_fail', 'reason', 'solver_name': '补缺宏'}；
    · 填洞宏侧结果原样透传（补 solver_name）。
    """
    coords = frozenset(tuple(b.location) for b in game.blocks)
    m, n = game.m, game.n
    g = build_game(coords, m, n)
    if g.is_solved():
        return [], []
    (r0, c0, wh), _ov, holes, _out = window_of(coords, m, n, step)
    use_gap = (len(holes) == 1 and _edge_of(
        next(iter(holes)), r0, c0, wh[0], wh[1]) in ('L', 'R', 'U', 'D'))
    if use_gap:
        wall, stats = solve_edge_gap(coords, m, n, step)
        if wall is not None and stats.get('solved'):
            acts4 = [a[:4] for a in wall]
            reps = [a[4] for a in wall]
            print('[补缺宏] 封壳%d+内部共轭%d+拆壳%d = %d 步（edge=%s%s）'
                  % (stats.get('seal', -1), stats.get('inner', -1),
                     stats.get('unseal', -1), len(wall), stats.get('edge', '?'),
                     '，rot=%s' % stats.get('rot') if stats.get('rot') != 'id'
                     else ''))
            return acts4, reps
        # 缺口分支失败/未复原（如凸起与主体粘连）：回退填洞宏兜底
        gap_why = (stats.get('reason', stats.get('error', '未知'))
                   if wall is None else '回放通但未还原（凸起粘连?）')
        print('[补缺宏] 缺口分支未成（%s），回退填洞宏' % gap_why)
    # 封闭孔洞/多洞/兜底：填洞宏主场，透传
    res = solve_fill_macro(game, step, cancel_check=cancel_check,
                           progress_callback=progress_callback)
    if isinstance(res, dict):
        res.setdefault('solver_name', '填洞宏')
        if use_gap:
            res['reason'] = ('缺口分支未成(%s)；填洞宏：%s'
                             % (gap_why, res.get('reason', '失败')))
    return res


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
        for fname in ('2-6-6-20260930-181940.json', '推測題.json',
                      '推測題2.json', '推測題3.json'):
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
