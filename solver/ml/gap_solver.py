# -*- coding: utf-8 -*-
r"""缺口求解器（双层共轭）「死代码」— 封壳 + 内部共轭 + 拆壳

外层（本模块新写）：边缘缺口 → 封闭孔洞。
    手法 = 甩料（切横缝把不含洞行的带向外推 step，甩出料条）
         + 垫洞（料条沿缝平移直到盖住洞的朝外邻格）。
    候选表按总步数升序逐个试，引擎 try_move 当裁判，不回溯、无搜索。
    角缺口（步骤3）：四角旋转归一化到左上 → _corner_chain
    （立塔 → 封北 → 西柱南下封西兼作桥 → 末条北移 → 凸起入洞 → 逆序拆壳）。
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
                                  _capture_apply, _replay_apply, _Runner,
                                  replay_and_verify)
from solver.ml import view_rotate                                          # noqa: E402

_INV = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}

# 引擎拒绝原因 → 中文（未收录的原样透出）
_ENG_WHY = {'collision': '碰撞', 'disconnected': '连通断裂',
            'bad_direction': '方向无效'}
_SEG_CN = {'seal': '封壳', 'inner': '内部共轭', 'unseal': '拆壳'}


def _why_cn(why):
    return _ENG_WHY.get(why, why or '非法')


def _checksum(data):
    """与 gui/file_ops._compute_checksum 完全一致（存档完整性校验）。"""
    import hashlib
    payload = {k: v for k, v in data.items() if k != 'checksum'}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _fail_reason(tr, fallback='受阻'):
    """trace dict → 填洞宏「需双层」风格的失败原因。

    tr 字段：seg(段名)/index(段内步序)/action(被拒动作4元组或None)/why。
    action=None 表示非单步被拒（如动作全通但洞未封）。
    """
    if not tr:
        return fallback
    seg = tr.get('seg', '?')
    why = tr.get('why', '受阻')
    act = tr.get('action')
    if seg == 'verify':
        return '链走通但未还原(假填洞?)'
    if act is None:
        return '%s：%s' % (_SEG_CN.get(seg, seg), why)
    return '%s第%d步 %s 被拒(%s)' % (_SEG_CN.get(seg, seg),
                                     tr.get('index', 0) + 1,
                                     '(%s,%s,%s,%s)' % act[:4], why)


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


def _apply_dbg(g, a4, step):
    """调试驱动单步：与 _apply4/_capture_apply 选块、提交语义完全一致，
    另返回 (引擎拒绝原因, 移动前选中块坐标列表) 供停步报告与存档。

    返回 (ok, 动作5元组, why, moved_pre)。
    """
    gap, line, side, d = a4[:4]
    rep = a4[4] if len(a4) == 5 else None
    b = g.get_boundaries()
    if gap == 'h' and not (b['min_row'] <= line < b['max_row']):
        return False, None, '缝线越界', []
    if gap == 'v' and not (b['min_col'] <= line < b['max_col']):
        return False, None, '缝线越界', []
    tgt = None
    if rep is not None:
        for blk in g.blocks:
            if tuple(blk.location) == tuple(rep):
                tgt = blk
                break
    if tgt is None:                      # = _Runner._side_first_block 语义
        for blk in g.blocks:
            r, c = blk.location
            if gap == 'h':
                if (side == 'above' and r <= line) or \
                        (side == 'below' and r > line):
                    tgt = blk
                    break
            elif (side == 'left' and c <= line) or \
                    (side == 'right' and c > line):
                tgt = blk
                break
    if tgt is None:
        return False, None, '侧内无块', []
    g.opt(gap, line, tgt)
    moved_pre = [list(blk.location) for blk in g.blocks if blk.be_opted]
    final, why = g.try_move_ex(d, step)
    if not final:
        for blk in g.blocks:
            blk.be_opted = False
        return False, None, _why_cn(why), []
    rep_pre = tuple(tgt.location)
    g.commit_move(final)
    return True, (gap, line, side, d, rep_pre), '', moved_pre


def _seal(vg, vh, step, trace=None):
    """在 view 局面上封壳。成功 → (封壳动作5元组列表, 新局面, 凸起新位置)。

    候选逐个在干净副本上试：全部动作合法 + 洞四邻全块 = 封壳成功。
    凸起位置用块对象引用跟踪（commit 改 location，读实例即得）。
    trace 为 dict 时记录最后一个候选的失败细节：
    seg/cand/index/action/why/prefix(该候选已成功的动作)。
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
    for ci, (acts, _n) in enumerate(_seal_candidates(hr, step)):
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
        for i, a4 in enumerate(acts):
            if trace is None:
                okk, a5 = _apply4(g2, a4, step)
                why = ''
            else:
                okk, a5, why, _mv = _apply_dbg(g2, a4, step)
            if not okk:
                ok = False
                if trace is not None:
                    trace.update(seg='seal', cand=ci, index=i, action=a4,
                                 why=why, prefix=list(done))
                break
            done.append(a5)
        if ok and _hole_sealed(g2, vh):
            vp = tuple(p2.location) if p2 is not None else None
            return done, g2, vp
        if ok and trace is not None:
            trace.update(seg='seal', cand=ci, index=-1, action=None,
                         why='动作全通但洞未封', prefix=list(done))
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


def _bumpcol_chain(vg, vh, step, verbose=False, trace=None):
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
                                     p0, step, trace=trace)
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
                                     p0, step, trace=trace)
            if wall is not None:
                if verbose:
                    print('  专列(下端)：j\'=%d k=%d' % (jp, k))
                return wall, stats
    return None, '专列：候选全败'


def _run_chain(vg, seal4, inner4, unseal4, p0, step, trace=None):
    """在副本上执行 封壳→内部→拆壳 三段（rep 动态跟踪凸起）。

    全部动作合法且最终 solved 才成功。
    返回 (view 动作5元组列表, stats) 或 (None, None)。
    trace 为 dict 时记录首个失败：seg/index/action/why/prefix(已成功动作)。
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
            if trace is None:
                okk, a5 = _apply4(g2, a, step)
                why = ''
            else:
                okk, a5, why, _mv = _apply_dbg(g2, a, step)
            if not okk:
                if trace is not None:
                    trace.update(seg=name, index=len(out), action=a4,
                                 why=why, prefix=segs + out)
                return None, None
            out.append(a5)
        segs += out
        nseg[name] = len(out)
    if not g2.is_solved():
        if trace is not None:
            trace.update(seg='verify', index=-1, action=None,
                         why='链走通但未还原', prefix=list(segs))
        return None, None
    return segs, nseg


# ---------------------------------------------------------------------------
# 角缺口（规范型：角洞在 view 左上 (0,0)）——推測題3 官方解参数化
# ---------------------------------------------------------------------------
# 转置同构（行列互换）：角洞 (0,0) 不动、连通/碰撞/矩形全部保持、
# (r%s,c%s) 类计数与转置后还原态一致 ⇒ 右边缘凸起（偶行）↔ 下边缘凸起。
_T_GAP = {'h': 'v', 'v': 'h'}
_T_SIDE = {'above': 'left', 'left': 'above',
           'below': 'right', 'right': 'below'}
_T_DIR = {'w': 'a', 'a': 'w', 's': 'd', 'd': 's'}


def _transpose_wall(wall5):
    """转置世界动作 → 原世界动作（5 元组）。"""
    return [(_T_GAP[g], ln, _T_SIDE[sd], _T_DIR[d], (rp[1], rp[0]))
            for g, ln, sd, d, rp in wall5]


def _corner_chain(vg, step, verbose=False, trace=None):
    """角缺口全链（前提：已归一化，角洞在 view (0,0)）。

    凸起须为窗外单块且贴在下边缘：(mv, c_b)，c_b ≡ 0 (mod step)。
    手法（推測題3 官方 11 步参数化，s=step，k=mv//s）：
      [N]×(k-1)   v 0 right w    东部连同凸起北移，立塔 rows -(mv-s)..-1
      A2          h -1 above a   塔西移 s，封北 (−1,0)
      A3          v 1-s left s   塔西柱南下，封西 (0,1-s),(1,1-s) 且当桥
      [N]         v 0 right w    末条北移：凸起到 (0,c_b)、行0清空；
                                 col0 残条靠西柱链桥接（无桥则引擎拒 disconnected）
      C ×c_b/s    h -1 below a   凸起单块逐段西移入洞
      拆壳 = 前四段逆序反向（rep=None 侧首块语义）。
    返回 (view 动作5元组列表, stats) 或 (None, 原因)。
    """
    mv, nv = vg.m, vg.n
    s = step
    if s < 2:
        return None, '角缺口：仅支持 step>=2'
    if mv % s:
        return None, '角缺口：mv=%d 非 step 整倍（奇偶类不容角洞）' % mv
    if nv < s + 2:
        return None, '角缺口：nv=%d < step+2，塔无落点' % nv
    if mv < 2 * s + 1:
        return None, '角缺口：mv=%d 过矮，西柱无法兼作桥' % mv
    outs = [blk for blk in vg.blocks
            if blk.location[0] < 0 or blk.location[0] >= mv
            or blk.location[1] < 0 or blk.location[1] >= nv]
    if len(outs) != 1:
        return None, '角缺口：窗外块 %d 个（需恰 1）' % len(outs)
    pr, pc = outs[0].location
    if pr != mv:
        return None, '角缺口：凸起不在下边缘 %s' % ((pr, pc),)
    cb = pc
    if cb < 1 or cb % s or cb > nv - 1:
        return None, '角缺口：凸起列 %d 非法（需 1..%d 且 ≡0 mod step）' % (cb, nv - 1)
    k = mv // s
    seal4 = [('v', 0, 'right', 'w')] * (k - 1) + \
            [('h', -1, 'above', 'a', (-1, 1)),
             ('v', 1 - s, 'left', 's', (-1, 1 - s)),
             ('v', 0, 'right', 'w')]
    inner4 = [('h', -1, 'below', 'a')] * (cb // s)
    unseal4 = [('v', 0, 'right', 's', None),
               ('v', 1 - s, 'left', 'w', None),
               ('h', -1, 'above', 'd', None)] + \
              [('v', 0, 'right', 's', None)] * (k - 1)
    wall, stats = _run_chain(vg, seal4, inner4, unseal4, (pr, pc), s,
                             trace=trace)
    if wall is None:
        return None, '角缺口：链被引擎拒绝或未还原'
    if verbose:
        print('  角链：k=%d c_b=%d（立塔%d+封北西+末N+入洞%d+拆壳%d）'
              % (k, cb, k - 1, cb // s, 2 + k))
    return wall, dict(stats, k=k, cb=cb)


def solve_corner_gap(coords, m, n, step, verbose=False):
    """单角缺口全链求解（步骤3）：四角旋转归一化到左上 → _corner_chain。

    角→旋转：左上 id、右上 ccw、左下 cw、右下 r180（rotate_xy 逐一验证）。
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
    top, bot = h_w[0] == r0, h_w[0] == r0 + wh[0] - 1
    lef, rig = h_w[1] == c0, h_w[1] == c0 + wh[1] - 1
    if not (top or bot) or not (lef or rig):
        return None, {'reason': '非角缺口'}
    name = ('id' if lef else 'ccw') if top else ('cw' if lef else 'r180')
    mv, nv = view_rotate.view_dims(name, m, n)
    vc = frozenset(view_rotate.rotate_xy(name, r - r0, c - c0, m, n)
                   for r, c in coords)
    vh = view_rotate.rotate_xy(name, h_w[0] - r0, h_w[1] - c0, m, n)
    if vh != (0, 0):
        return None, {'reason': '角归一化异常 %s' % (vh,), 'rot': name}
    vg = build_game(vc, mv, nv)

    def _to_world(a):
        gap, line, side, d, rep = a
        gap2, line2, side2, d2 = view_rotate.act_to_world(
            name, gap, line, side, d, m, n)
        line2 = line2 + (r0 if gap2 == 'h' else c0)
        rr, cc = view_rotate.rep_to_world(name, rep[0], rep[1], m, n)
        return (gap2, line2, side2, d2, (rr + r0, cc + c0))

    # ---- 角链：先直接解；失败且凸起在右边缘偶行时，转置视角重试 ----
    tr1 = {}
    res = _corner_chain(vg, step, verbose=verbose, trace=tr1)
    last = (tr1, res[1], False)          # (trace, 失败原因, 是否转置尝试)
    if res[0] is None:
        outs = [blk for blk in vg.blocks
                if blk.location[0] < 0 or blk.location[0] >= mv
                or blk.location[1] < 0 or blk.location[1] >= nv]
        if len(outs) == 1 and outs[0].location[1] == nv \
                and outs[0].location[0] % step == 0:
            vt = build_game(frozenset((c, r) for r, c in gcoords(vg)),
                            nv, mv)
            if verbose:
                print('  直接角链未成(%s)，转置重试' % res[1])
            tr2 = {}
            res2 = _corner_chain(vt, step, verbose=verbose, trace=tr2)
            if res2[0] is not None:
                res = (_transpose_wall(res2[0]),
                       dict(res2[1], transposed=True))
            else:
                last = (tr2, '%s；转置重试:%s' % (res[1], res2[1]), True)
    if res[0] is None:
        tr, reason, transposed = last
        if transposed:
            pre = [_to_world(_transpose_wall(a))
                   for a in tr.get('prefix', [])]
        else:
            pre = [_to_world(a) for a in tr.get('prefix', [])]
        return None, {'reason': reason, 'rot': name, 'fail_world': pre}
    wall5, cstats = res

    wall = [_to_world(a) for a in wall5]
    g = build_game(coords, m, n)
    ok = _replay_apply(g, wall, m, n, step)
    solved_world = ok and g.is_solved()
    stats = {'steps': len(wall),
             'seal': cstats['k'] + 1, 'inner': cstats['cb'] // step,
             'unseal': cstats['k'] + 2,
             'rot': name, 'edge': 'CORNER', 'route': 'corner',
             'view_solved': True, 'solved': solved_world,
             'secs': round(time.time() - t0, 3)}
    if not solved_world:
        stats['reason'] = '角链回放未还原'
        stats['fail_world'] = wall if ok else []
        return None, stats
    return wall, stats


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
        return None, {'reason': '角缺口（应走 solve_corner_gap）'}

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
    tr = {}                              # 最后一次失败的细节（last-wins）
    pblk0 = _find_bump(vg)
    if pblk0 is not None and pblk0.location[1] == 0 and \
            pblk0.location[0] in (-1, mv):
        res = _bumpcol_chain(vg, vh, step, verbose=verbose, trace=tr)
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
                stats['fail_world'] = wall if ok else []
                return None, stats
            return wall, stats
        if verbose:
            print('  专列未成(%s)，回常规封壳' % res[1])
    sealed = _seal(vg, vh, step, trace=tr)
    if sealed is None:
        return None, {'reason': _fail_reason(tr, '封壳受阻（候选全败）'),
                      'edge': edge,
                      'fail_world': [_to_world(a)
                                     for a in tr.get('prefix', [])]}
    seal_acts, vg, vp = sealed
    if verbose:
        print('  封壳 %d 步，凸起 -> %s' % (len(seal_acts), vp))

    # ---- 内部共轭（couple 显式指定，本质校验绕窗口）----
    if vp is None:
        return None, {'reason': '封壳后凸起丢失', 'edge': edge,
                      'fail_world': [_to_world(a) for a in seal_acts]}
    iacts, istats = _solve_couple(gcoords(vg), mv, nv, step,
                                  vh, vp, keep_partial=True)
    if iacts is None or istats.get('partial'):
        # partial = 填洞宏 _Runner 撞停（如「A段受阻(需双层)」）：
        # 原因直接透出，已走前缀 = 封壳 + 部分内部动作
        return None, {'reason': '内部共轭失败: %s' % istats.get('reason', '?'),
                      'edge': edge,
                      'inner': {k: v for k, v in istats.items()
                                if k not in ('reason', 'partial')},
                      'fail_world': [_to_world(a) for a in
                                     list(seal_acts) + list(iacts or [])]}
    if verbose:
        print('  内部共轭 %d 步 %s' % (len(iacts), istats))

    # 内部共轭动作回放进 vg（solve_single_void 只吃坐标不回写局面）
    if not _replay_apply(vg, iacts, mv, nv, step):
        return None, {'reason': '内部共轭回放失败', 'edge': edge,
                      'fail_world': [_to_world(a) for a in seal_acts]}

    # ---- 拆壳（封壳逆序宏，在已填洞局面上执行）----
    unseal_acts = []
    for ui, a4 in enumerate(reversed(seal_acts)):
        a_inv = (a4[0], a4[1], a4[2], _INV[a4[3]])
        okk, a5, why, _mv = _apply_dbg(vg, a_inv, step)
        if not okk:
            tr.update(seg='unseal', index=ui, action=a_inv, why=why,
                      prefix=list(seal_acts) + list(iacts) + list(unseal_acts))
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
        stats['reason'] = ('回放通但未还原' if ok
                           else '回放未还原于第?步')
        if not ok:
            stats['reason'] = '全链回放失败: %s' % _fail_reason(tr, '未知')
        stats['fail_world'] = wall if ok else []
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
        if edge == 'CORNER':
            wall, stats = solve_corner_gap(coords, m, n, step)
            return wall, dict(stats, route='corner_gap')
    # 其余（封闭孔洞/多洞）交填洞宏驱动
    from solver.ml.fill_macro import solve_fill_macro
    res = solve_fill_macro(build_game(coords, m, n), step)
    if isinstance(res, tuple):
        return res, {'route': 'fill_macro', 'steps': len(res[0])}
    return None, {'reason': res.get('reason', '填洞宏失败'),
                  'route': 'fill_macro'}


def save_failure_archive(coords, m, n, step, wall5, tag):
    """把失败案例存成游戏可读档 save/补缺失败-<tag>.json。

    wall5 = 世界坐标动作5元组前缀（全部合法、停在被拒那一步之前；
    空列表 = 一步未走就被结构性拒绝，如角缺口凸起列 0）。
    快照序列 = 初始状态 + 每步成功后的状态：游戏载入后停在失败那一刻
    （history_index 指向末条），可逐步撤销回初始，也可直接按补缺宏观察。
    格式与 gui/file_ops._build_save_data 一致（含 SHA256 校验和）。
    返回文件名；写入失败返回 None。
    """
    g = build_game(frozenset(coords), m, n)
    g.update_matrix()
    snaps = [{'matrix': [row[:] for row in g.matrix],
              'bounds': dict(g.matrix_bounds),
              'move_info': None, 'moves': [], 'steps': 0, 'step_total': 0}]
    total = 0
    for a5 in wall5:
        ok, _a, _w, moved = _apply_dbg(g, a5, step)
        if not ok:
            break
        total += 1
        mi = {'gap_type': a5[0], 'gap_line': a5[1], 'side': a5[2],
              'direction': a5[3], 'step': step, 'moved_positions': moved}
        g.update_matrix()
        snaps.append({'matrix': [row[:] for row in g.matrix],
                      'bounds': dict(g.matrix_bounds),
                      'move_info': mi, 'moves': [mi], 'steps': 1,
                      'step_total': total})
    data = {'version': 1,
            'puzzle': {'m': m, 'n': n, 'step': step},
            'step_count': total,
            'history': {'history_index': len(snaps) - 1,
                        'snapshots': snaps}}
    data['checksum'] = _checksum(data)
    fname = '补缺失败-%s.json' % tag
    path = os.path.join(_ROOT, 'save', fname)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return fname
    except OSError:
        return None


# ---------------------------------------------------------------------------
# GUI 求解器入口（与 SOLVER_ALGORITHMS 统一签名）
# ---------------------------------------------------------------------------
def solve_gap_macro(game, step, cancel_check=None, progress_callback=None,
                    stop_on_fail=False, **kwargs):
    """补缺宏（GUI 入口）：单边缺口 → 封壳+内部共轭+拆壳；其余交填洞宏。

    返回协议与 solve_fill_macro 一致：
    · 成功 → (actions4, rep_cells)；
    · 失败 → {'type': 'fill_fail', 'reason', 'solver_name': '补缺宏'}；
    · 填洞宏侧结果原样透传（补 solver_name）。
    stop_on_fail=True：缺口分支失败时停在那一步，不回退填洞宏——reason 为
    填洞宏「需双层」风格的细节（段+步+动作+引擎原因），并附 fail_world
    （已成功的世界动作前缀，供 save_failure_archive 落盘复现）。
    """
    coords = frozenset(tuple(b.location) for b in game.blocks)
    m, n = game.m, game.n
    g = build_game(coords, m, n)
    if g.is_solved():
        return [], []
    (r0, c0, wh), _ov, holes, _out = window_of(coords, m, n, step)
    edge = None
    if len(holes) == 1:
        edge = _edge_of(next(iter(holes)), r0, c0, wh[0], wh[1])
    use_gap = edge in ('L', 'R', 'U', 'D', 'CORNER')
    if use_gap:
        if edge == 'CORNER':
            wall, stats = solve_corner_gap(coords, m, n, step)
        else:
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
        if stop_on_fail:
            print('[补缺宏] 失败停步：%s' % gap_why)
            return {'type': 'fill_fail', 'reason': gap_why,
                    'solver_name': '补缺宏',
                    'fail_world': stats.get('fail_world') or []}
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
            acts, stats = solve_gap(coords, m, n, step)
            if isinstance(acts, tuple):      # fill_macro 透传 (actions4, reps)
                acts4, reps = acts
                acts5 = [a[:4] + (reps[i],) for i, a in enumerate(acts4)]
                ok = replay_and_verify(coords, m, n, step, acts5)
                print('结果: fill_macro %d 步 回放复原=%s' % (len(acts4), ok))
            else:
                print('结果:', '成功' if acts else '失败', stats)
        return
    print(__doc__)


if __name__ == '__main__':
    _main()
