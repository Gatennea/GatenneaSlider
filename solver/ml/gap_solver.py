# -*- coding: utf-8 -*-
r"""缺口求解器（双层共轭）「死代码」— 封壳 + 内部共轭 + 拆壳

外层（本模块新写）：边缘缺口 → 封闭孔洞。
    主路径 = 用户算法（2026-09-30 伪代码教学）：
    缺口旋转归一化到上边缘 (0,c) → 记 L=c、R=n-1-c（缺口两侧顶行滑块数）→
    R>step 取右缝 flag=1 / L>step 取左缝 flag=-1（两侧均≤step = 4*4 特殊型，
    待补充）→ 缺口(flag*右)侧缝整组上移一次 + 窗顶条带(h缝-1上侧)向缺口侧
    平移一次 = 封壳 → 显式 couple 调填洞宏 → 逆外层共轭拆壳。
    （>step 的几何意义：条带侧移 step 后与主体的重叠列非空，保持连通。）
    凸起块开局即跟踪（用户注记：否则可能抓错组）。
    回退路径 v1 = 甩料（切横缝把不含洞行的带向外推 step，甩出料条）
    + 垫洞（料条沿缝平移直到盖住洞的朝外邻格），候选表按总步数升序逐个试。
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
                                  replay_and_verify, solve_multi_void,
                                  _compact_rescue, _convoy_fill,
                                  solve_multi_search, _Cancelled, _emit)
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


# ---------------------------------------------------------------------------
# 全对称群 D4（4 旋转 × 2 反射）作用层 —— 填洞宏 choose_rot「凸起恒在右侧，
# 只手写一种规范情况」的思想推广到 8 元群：每种几何只手写一份链，
# 其余 7 个方位靠群作用搬运，镜像由此获得与旋转同等的覆盖。
# 箱体恒为 [0,m)×[0,n)（世界坐标），公式对界外坐标（料条/凸起）同样成立。
# ---------------------------------------------------------------------------
_D4_ORDER = ('id', 'r180', 'ccw', 'cw', 'fh', 'fv', 'tr', 'at')
_INV_T = {'id': 'id', 'r180': 'r180', 'ccw': 'cw', 'cw': 'ccw',
          'fh': 'fh', 'fv': 'fv', 'tr': 'tr', 'at': 'at'}
_TF_SWAP = ('ccw', 'cw', 'tr', 'at')     # 交换行列的变换

# 方向键映射：(dr,dc) → 变换后的方向
_DIR_TF = {
    'id':  {'w': 'w', 'a': 'a', 's': 's', 'd': 'd'},
    'r180': {'w': 's', 'a': 'd', 's': 'w', 'd': 'a'},
    'ccw': {'w': 'a', 'a': 's', 's': 'd', 'd': 'w'},
    'cw':  {'w': 'd', 'a': 'w', 's': 'a', 'd': 's'},
    'fh':  {'w': 'w', 'a': 'd', 's': 's', 'd': 'a'},
    'fv':  {'w': 's', 'a': 'a', 's': 'w', 'd': 'd'},
    'tr':  {'w': 'a', 'a': 'w', 's': 'd', 'd': 's'},
    'at':  {'w': 's', 'a': 'd', 's': 'w', 'd': 'a'},
}


def _tf_pt(name, p, m, n):
    """点 (r,c) 经全等变换 name（源箱体 m×n）。"""
    r, c = p
    if name == 'id':
        return (r, c)
    if name == 'r180':
        return (m - 1 - r, n - 1 - c)
    if name == 'ccw':
        return (n - 1 - c, r)
    if name == 'cw':
        return (c, m - 1 - r)
    if name == 'fh':
        return (r, n - 1 - c)
    if name == 'fv':
        return (m - 1 - r, c)
    if name == 'tr':
        return (c, r)
    return (n - 1 - c, m - 1 - r)                     # at


def _tf_dims(name, m, n):
    return (n, m) if name in _TF_SWAP else (m, n)


def _tf_act(name, a, m, n):
    """源架（箱体 [0,m)×[0,n)）的动作5元组 → name 变换后架的动作5元组。

    缝线：边界 L|L+1 在变换下的像；侧别与方向按同构逐变换推导。
    rep 为块坐标，直接走 _tf_pt。
    """
    gap, line, side, d, rep = a
    if name == 'id':
        return a
    dm = _DIR_TF[name]
    rp = _tf_pt(name, rep, m, n)
    o = lambda g, ln, sd: (g, ln, sd, dm[d], rp)      # noqa: E731
    if name == 'r180':
        return o(gap, (m if gap == 'h' else n) - 2 - line,
                 _OPP_SIDE[side])
    if name == 'fh':
        return o(gap, line if gap == 'h' else n - 2 - line,
                 side if gap == 'h' else _OPP_SIDE[side])
    if name == 'fv':
        return o(gap, (m - 2 - line) if gap == 'h' else line,
                 _OPP_SIDE[side] if gap == 'h' else side)
    if name == 'ccw':
        return o(_T_GAP[gap], line if gap == 'h' else n - 2 - line,
                 {'above': 'left', 'below': 'right',
                  'left': 'below', 'right': 'above'}[side])
    if name == 'cw':
        return o(_T_GAP[gap], (m - 2 - line) if gap == 'h' else line,
                 {'above': 'right', 'below': 'left',
                  'left': 'above', 'right': 'below'}[side])
    if name == 'tr':
        return o(_T_GAP[gap], line,
                 {'above': 'left', 'below': 'right',
                  'left': 'above', 'right': 'below'}[side])
    # at（反对角镜像）
    return o(_T_GAP[gap], (m - 2 - line) if gap == 'h' else n - 2 - line,
             {'above': 'right', 'below': 'left',
              'left': 'below', 'right': 'above'}[side])


_OPP_SIDE = {'above': 'below', 'below': 'above',
             'left': 'right', 'right': 'left'}


def _orbit_key(coords, m, n, step):
    """链规范型键（边缺口→左边缘、角缺口→左上），轨道成员去重用。"""
    (r0, c0, wh), _ov, holes, _out = window_of(coords, m, n, step)
    if len(holes) != 1:
        return None
    h = next(iter(holes))
    e = _edge_of(h, r0, c0, wh[0], wh[1])
    if e == 'INNER':
        return None
    if e == 'CORNER':
        top, lef = h[0] == r0, h[1] == c0
        name = ('id' if (top and lef) else 'ccw' if top
                else 'cw' if lef else 'r180')
    else:
        name = _ROT_FOR_EDGE[e]
    kf = frozenset(view_rotate.rotate_xy(name, r - r0, c - c0, m, n)
                   for r, c in coords)
    return (kf, view_rotate.view_dims(name, m, n))


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
def _solve_couple(coords, m, n, step, h, p, keep_partial=True,
                  force_rot=None):
    """couple 内部共轭：流程与 solve_single_void 相同，但 couple 校验用
    本质判定（h=空位、p=块、同 mod），不经窗口——封壳料条会把
    find_best_window 的窗口撑得漂移，凸起可能被圈进窗内而遭误杀。
    （fill_macro 本体不动，此处仅绕过其入口预检，_Runner 语义完全一致。）
    force_rot：强制旋转名（None=choose_rot 自动）。补缺链传 'id'——
    封壳后的临时几何（条带在上/空缺在下）就是填洞的缓冲，再旋转会把
    凸起转到与洞同行，setup 在临时几何里无缝可走（实测失败10）。
    """
    coords = frozenset(coords)
    if h in coords or p not in coords:
        return None, {'reason': 'couple坐标无效（hole须为空位、anchor须为块）'}
    if (h[0] - p[0]) % step or (h[1] - p[1]) % step:
        return None, {'reason': '洞凸不同mod'}
    (r0, c0, _wh), _ov, _holes, _out = window_of(coords, m, n, step)
    name = force_rot or view_rotate.choose_rot(p[0] - r0, p[1] - c0, m, n)
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


def _run_chain(vg, seal4, inner4, unseal4, p0, step, trace=None,
               require_solved=True, vh=(0, 0)):
    """在副本上执行 封壳→内部→拆壳 三段（rep 动态跟踪凸起）。

    require_solved=True：全部动作合法且最终 solved 才成功；
    False（couple 模式）：成功判据 = 洞 vh 被填。
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
    if require_solved:
        if not g2.is_solved():
            if trace is not None:
                trace.update(seg='verify', index=-1, action=None,
                             why='链走通但未还原', prefix=list(segs))
            return None, None
    elif vh not in gcoords(g2):
        if trace is not None:
            trace.update(seg='verify', index=-1, action=None,
                         why='链走通但洞未填', prefix=list(segs))
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


def _corner_chain(vg, step, verbose=False, trace=None, p0=None,
                  require_solved=True):
    """角缺口全链（前提：已归一化，角洞在 view (0,0)）。

    p0：显式指定窗外凸起（多凸起 couple 模式）；None=要求窗外恰一块。
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
    if p0 is not None:
        pb = None
        for blk in vg.blocks:
            if tuple(blk.location) == tuple(p0):
                pb = blk
                break
        if pb is None:
            return None, '角缺口：指定凸起 %s 不在盘上' % (p0,)
        outs = [pb]
    else:
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
                             trace=trace, require_solved=require_solved,
                             vh=(0, 0))
    if wall is None:
        return None, '角缺口：链被引擎拒绝或未还原'
    if verbose:
        print('  角链：k=%d c_b=%d（立塔%d+封北西+末N+入洞%d+拆壳%d）'
              % (k, cb, k - 1, cb // s, 2 + k))
    return wall, dict(stats, k=k, cb=cb)


def solve_corner_gap(coords, m, n, step, verbose=False, hole=None,
                     anchor=None, require_solved=True):
    """单角缺口全链求解（步骤3）：四角旋转归一化到左上 → _corner_chain。

    couple 模式：显式喂 hole/anchor，成功判据 = 洞被填（不要求整盘还原）。
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
    couple = hole is not None
    if couple:
        h_w = tuple(hole)
        if h_w not in holes:
            return None, {'reason': 'couple缺口不是窗内空位'}
        if anchor is None or tuple(anchor) not in coords:
            return None, {'reason': 'couple凸起不在盘上'}
        anchor = tuple(anchor)
    else:
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
    vp0 = None
    if couple:
        vp0 = view_rotate.rotate_xy(name, anchor[0] - r0, anchor[1] - c0,
                                    m, n)

    def _to_world(a):
        gap, line, side, d, rep = a
        gap2, line2, side2, d2 = view_rotate.act_to_world(
            name, gap, line, side, d, m, n)
        line2 = line2 + (r0 if gap2 == 'h' else c0)
        rr, cc = view_rotate.rep_to_world(name, rep[0], rep[1], m, n)
        return (gap2, line2, side2, d2, (rr + r0, cc + c0))

    # ---- 角链：先直接解；失败且凸起贴右缘偶行时，转置视角重试 ----
    # 凸起贴右缘顶行 (0, nv)（与洞同行）时，四角旋转是自映射救不动：
    # 先沿右缘下推 step 步到 (step, nv)（正下方全空、每步与 (r,nv-1)
    # 主带相连保持单连通），转置后即成「挂下边缘列 step」的标准型。
    tr1 = {}
    res = _corner_chain(vg, step, verbose=verbose, trace=tr1, p0=vp0,
                        require_solved=require_solved)
    last = (tr1, res[1], False)          # (trace, 失败原因, 是否转置尝试)
    if res[0] is None:
        # 转置重试资格：凸起贴右缘偶行（couple 模式按指定凸起判定）
        if couple:
            avp = next((blk for blk in vg.blocks
                        if tuple(blk.location) == tuple(vp0)), None)
            br = avp.location[0] if avp is not None else None
            ok_t = (avp is not None and avp.location[1] == nv
                    and br % step == 0 and (br > 0 or step <= mv - 1))
        else:
            outs = [blk for blk in vg.blocks
                    if blk.location[0] < 0 or blk.location[0] >= mv
                    or blk.location[1] < 0 or blk.location[1] >= nv]
            br = outs[0].location[0] if len(outs) == 1 else None
            ok_t = (len(outs) == 1 and outs[0].location[1] == nv
                    and br % step == 0 and (br > 0 or step <= mv - 1))
        if ok_t:
            setup5 = []
            vg2 = vg
            p_t = (nv, br)               # 转置后凸起位置（无 setup 时）
            if br == 0:
                g2 = build_game(gcoords(vg), mv, nv)
                a2 = None
                if couple and vp0 is not None:
                    a2 = next((blk for blk in g2.blocks
                               if tuple(blk.location) == tuple(vp0)), None)
                for _ in range(step):
                    ok1, a5 = _capture_apply(g2, ('v', nv - 1, 'right', 's'),
                                             step)
                    if not ok1:
                        break
                    setup5.append(a5)
                if len(setup5) == step:
                    if couple and a2 is not None:
                        # setup 后凸起随带南下 step；块对象原地跟踪
                        p_t = (a2.location[1], a2.location[0])
                    vg2 = build_game(frozenset(gcoords(g2)), mv, nv)
                else:
                    setup5 = []
            vt = build_game(frozenset((c, r) for r, c in gcoords(vg2)),
                            nv, mv)
            if verbose:
                print('  直接角链未成(%s)，转置重试%s'
                      % (res[1], '（先右缘下推 setup）' if setup5 else ''))
            tr2 = {}
            res2 = _corner_chain(vt, step, verbose=verbose, trace=tr2,
                                 p0=p_t if couple else None,
                                 require_solved=require_solved)
            if res2[0] is not None:
                res = (setup5 + _transpose_wall(res2[0]),
                       dict(res2[1], transposed=True,
                            setup=len(setup5) if setup5 else 0))
            else:
                last = (tr2, '%s；转置重试:%s' % (res[1], res2[1]), True)
    if res[0] is None:
        tr, reason, transposed = last
        if transposed:
            pre = [_to_world(_transpose_wall([a])[0])
                   for a in tr.get('prefix', [])]
        else:
            pre = [_to_world(a) for a in tr.get('prefix', [])]
        return None, {'reason': reason, 'rot': name, 'fail_world': pre}
    wall5, cstats = res

    wall = [_to_world(a) for a in wall5]
    g = build_game(coords, m, n)
    ok = _replay_apply(g, wall, m, n, step)
    if require_solved:
        done_world = ok and g.is_solved()
    else:
        done_world = ok and h_w in gcoords(g)
    stats = {'steps': len(wall),
             'seal': cstats['k'] + 1, 'inner': cstats['cb'] // step,
             'unseal': cstats['k'] + 2,
             'rot': name, 'edge': 'CORNER', 'route': 'corner',
             'view_solved': True, 'solved': done_world,
             'secs': round(time.time() - t0, 3)}
    if couple:
        stats['couple'] = True
    if cstats.get('transposed'):
        stats['transposed'] = True
        if cstats.get('setup'):
            stats['setup'] = cstats['setup']
    if not done_world:
        stats['reason'] = '角链回放未还原'
        stats['fail_world'] = wall if ok else []
        return None, stats
    return wall, stats


def solve_gap_any(coords, m, n, step, verbose=False):
    """全对称群轨道求解：对 D4 轨道的每个规范型成员逐一求解，
    成功者的动作经逆变换映射回原架，并用引擎在原架独立回放验收。

    数学根据：D4 是游戏规则的完全同构群 ⇒ 轨道任一成员可解 ⇔ 全体可解；
    反射成员正是此前「镜像后失败」病例的解药。
    返回 (原架世界动作5元组, stats)；全部失败 → (None, stats)。
    """
    t0 = time.time()
    coords = frozenset(coords)
    (r0, c0, wh), _ov, holes, _out = window_of(coords, m, n, step)
    if len(holes) != 1:
        return None, {'reason': '非单缺口'}
    e0 = _edge_of(next(iter(holes)), r0, c0, wh[0], wh[1])
    if e0 == 'INNER':
        return None, {'reason': '封闭孔洞（应交填洞宏）'}
    is_corner = e0 == 'CORNER'
    seen, reasons, best_fw = set(), [], []
    for tname in _D4_ORDER:
        tc = frozenset(_tf_pt(tname, p, m, n) for p in coords)
        tm, tn = _tf_dims(tname, m, n)
        key = _orbit_key(tc, tm, tn, step)
        if key is None or key in seen:
            continue
        seen.add(key)
        if is_corner:
            wall, st = solve_corner_gap(tc, tm, tn, step, verbose=verbose)
        else:
            wall, st = solve_edge_gap(tc, tm, tn, step, verbose=verbose)
        if wall is not None and st.get('solved'):
            wall0 = [_tf_act(_INV_T[tname], a, tm, tn) for a in wall]
            g = build_game(coords, m, n)
            if _replay_apply(g, wall0, m, n, step) and g.is_solved():
                return wall0, dict(st, orbit=tname, steps=len(wall0),
                                   secs=round(time.time() - t0, 3))
            reasons.append('%s架映射回放失败' % tname)
            continue
        reasons.append(st.get('reason', st.get('error', '受阻')))
        fw = [_tf_act(_INV_T[tname], a, tm, tn)
              for a in (st.get('fail_world') or [])]
        if len(fw) > len(best_fw):
            best_fw = fw
    return None, {'reason': '；'.join(dict.fromkeys(reasons)) or '轨道全败',
                  'edge': e0, 'orbit_n': len(seen),
                  'fail_world': best_fw}


_ROT_TO_TOP = {'U': 'id', 'L': 'cw', 'R': 'ccw', 'D': 'r180'}


def _couple_orbit_solve(coords, m, n, step, h, p, kind, verbose=False):
    """D4 轨道 couple 求解：单缺口链主解读失败时，对轨道成员逐一试。

    数学根据同 solve_gap_any：D4 是游戏规则的完全同构群。主解读（id 成员）
    的凸起姿态可能恰是链的盲区（如角缺口凸起挂下缘列 0），换轨道成员
    （反射/旋转）后即落回标准型。失败07终局实证：角链拒（列0），fh 架
    下补缺链 16 步可解。

    kind='CORNER' → solve_corner_gap couple；否则 solve_edge_gap couple。
    成功者动作经逆变换映射回原架，并回放验收「洞 h 被填」。
    返回 (世界动作5元组, stats) 或 (None, stats)。
    """
    coords = frozenset(coords)
    seen = set()
    reasons = []
    for tname in _D4_ORDER:
        tc = frozenset(_tf_pt(tname, q, m, n) for q in coords)
        tm, tn = _tf_dims(tname, m, n)
        th = _tf_pt(tname, tuple(h), m, n)
        tp = _tf_pt(tname, tuple(p), m, n)
        key = _orbit_key(tc, tm, tn, step)
        if key is None or key in seen:
            continue
        seen.add(key)
        if kind == 'CORNER':
            acts, st = solve_corner_gap(tc, tm, tn, step, hole=th, anchor=tp,
                                        require_solved=False, verbose=verbose)
        else:
            acts, st = solve_edge_gap(tc, tm, tn, step, hole=th, anchor=tp,
                                      require_solved=False, verbose=verbose)
        if acts is not None and st.get('solved'):
            wall = [_tf_act(_INV_T[tname], a, tm, tn) for a in acts]
            g = build_game(coords, m, n)
            if _replay_apply(g, wall, m, n, step) and tuple(h) in gcoords(g):
                return wall, dict(st, orbit=tname)
            reasons.append('%s架映射回放失败' % tname)
            continue
        reasons.append(st.get('reason', st.get('error', '受阻')))
    return None, {'reason': 'couple轨道全败：%s'
                            % '；'.join(dict.fromkeys(reasons))}

# 换边等价表达：(side, dir) -> (对侧, 同向)。同缝异侧同向移动与
# 原侧反向移动的相对位移相同（差一个整体平移），is_solved 不钉死
# 绝对位置，故拆壳被拒时可换边重试（用户复原失败01实证）。
_FLIP_SIDE_DIR = {('above', 'a'): ('below', 'd'),
                  ('above', 'd'): ('below', 'a'),
                  ('below', 'a'): ('above', 'd'),
                  ('below', 'd'): ('above', 'a'),
                  ('left', 's'): ('right', 'w'),
                  ('left', 'w'): ('right', 's'),
                  ('right', 's'): ('left', 'w'),
                  ('right', 'w'): ('left', 's')}


def normalize_present(coords, m, n, step):
    """呈现规范形（用户约定）：
    边缺口 → 上边缘，凸起 → 右侧或下侧（左侧经左右翻并入右侧；
    上侧因 mod 类限制不可能）；角缺口 → 左上角，凸起 → 右侧
    （下侧经转置并入右侧；上/左因 mod 类限制不可能）。
    返回 (coords', m', n', 变换链[t1, t2, ...])——
    coords' = t2∘t1 作用于 coords，fail 前缀动作可用 _tf_act 逐级映射。
    """
    coords = frozenset(coords)
    (r0, c0, wh), _ov, holes, _out = window_of(coords, m, n, step)
    if len(holes) != 1:
        return coords, m, n, []
    h = next(iter(holes))
    e = _edge_of(h, r0, c0, wh[0], wh[1])
    if e == 'CORNER':
        top, lef = h[0] == r0, h[1] == c0
        name = ('id' if (top and lef) else 'ccw' if top
                else 'cw' if lef else 'r180')
    elif e in _ROT_TO_TOP:
        name = _ROT_TO_TOP[e]
    else:
        return coords, m, n, []
    tlist = [name]
    tm, tn = _tf_dims(name, m, n)
    tc = frozenset(_tf_pt(name, p, m, n) for p in coords)
    outs = [p for p in tc if not (0 <= p[0] < tm and 0 <= p[1] < tn)]
    if len(outs) == 1:
        br, bc = outs[0]
        if e == 'CORNER' and br >= tm:     # 凸起在下侧 → 转置并入右侧
            tlist.append('tr')
            tc = frozenset(_tf_pt('tr', p, tm, tn) for p in tc)
            tm, tn = _tf_dims('tr', tm, tn)
        elif e != 'CORNER' and bc < 0:     # 凸起在左侧 → 左右翻并入右侧
            tlist.append('fh')
            tc = frozenset(_tf_pt('fh', p, tm, tn) for p in tc)
    return tc, tm, tn, tlist


# ---------------------------------------------------------------------------
# 用户算法（2026-09-30 伪代码教学）：封壳 = 整组上移 + 窗顶条带侧移
# ---------------------------------------------------------------------------
def _user_edge_chain(vg, vh, step, verbose=False, p0=None,
                     require_solved=True):
    """边缺口用户链（规范型：缺口 (0,c)，c>=1，凸起在窗外）。

    p0：显式指定窗外凸起坐标（多凸起 couple 模式）；None=_find_bump 自取。
    require_solved=False（couple 模式）：成功判据 = 洞被填，不要求整盘
    还原（多空位驱动层按聚拢度验收）。

    L=c、R=nv-1-c（顶行缺口两侧滑块数）：
    R>step → flag=1：缝 v@c 选右侧整组上移 step；窗顶条带 h@-1 above 左移 step。
    L>step → flag=-1：缝 v@(c-1) 选左侧整组上移；窗顶条带右移 step。
    两侧均≤step → 4*4 特殊型（用户暂未教学，直接报告）。
    封壳后洞 (0,c) 四邻全块 = 封闭孔洞 → 显式 couple 调填洞宏 → 逆封壳。
    返回 (view 动作5元组列表, stats) 或 (None, {'reason', 'prefix'})。
    """
    mv, nv = vg.m, vg.n
    c = vh[1]
    L, R = c, nv - 1 - c
    if R > step:
        flag = 1
    elif L > step:
        flag = -1
    else:
        return None, {'reason': '两侧均≤step(L=%d,R=%d，4*4特殊型待补充)'
                                 % (L, R), 'prefix': []}
    if p0 is not None:
        pblk = None
        for blk in vg.blocks:
            if tuple(blk.location) == tuple(p0):
                pblk = blk
                break
        if pblk is None:
            return None, {'reason': '指定凸起 %s 不在盘上' % (p0,),
                          'prefix': []}
    else:
        pblk = _find_bump(vg)
        if pblk is None:
            return None, {'reason': '找不到窗外凸起', 'prefix': []}
    p0 = tuple(pblk.location)
    if flag == 1:
        seal4 = [('v', c, 'right', 'w', (0, c + 1)),
                 ('h', -1, 'above', 'a', (-1, c + 1))]
        unseal4 = [('h', -1, 'above', 'd', None),
                   ('v', c, 'right', 's', None)]
    else:
        seal4 = [('v', c - 1, 'left', 'w', (0, c - 1)),
                 ('h', -1, 'above', 'd', (-1, 0))]
        unseal4 = [('h', -1, 'above', 'a', None),
                   ('v', c - 1, 'left', 's', None)]

    def _find_block(g, pos):
        for blk in g.blocks:
            if tuple(blk.location) == pos:
                return blk
        return None

    def _run(squeeze, inner_mode):
        """跑一条完整链。squeeze=False 直解；True 先「下面整带挤入」。
        inner_mode：内层填洞方式——'direct'=用户直接共轭（同缝升凸→
        滑入→降回）；None=通用填洞宏 choose_rot 自动；'id'=宏不旋转。
        返回 (动作列表, stats) 或 (None, 失败原因, 已走前缀)。"""
        g2 = build_game(gcoords(vg), mv, nv)
        p2 = _find_block(g2, p0)
        prefix = []
        # 起手 setup（用户教学 2026-09-30，函数最开始就做）：
        # 凸起与缺口同行（凸起在顶行窗外侧）→ 上移/下移一下；
        # 凸起与缺口同列（正下/正上）→ 左移/右移一下。
        # 方向取引擎第一个接受的；单块平移，不参与共轭还原。
        if p2 is not None:
            pr, pc = p2.location
            if pr == 0 and (pc >= nv or pc < 0):    # 同行：顶行外侧
                scands = ([('v', nv - 1, 'right', 'w', None),
                           ('v', nv - 1, 'right', 's', None)] if pc >= nv else
                          [('v', -1, 'left', 'w', None),
                           ('v', -1, 'left', 's', None)])
            elif pc == c:                           # 同列：正下方/正上方
                scands = ([('h', mv - 1, 'below', 'a', None),
                           ('h', mv - 1, 'below', 'd', None)] if pr >= mv else
                          [('h', 0, 'above', 'a', None),
                           ('h', 0, 'above', 'd', None)])
            else:
                scands = []
            if scands:
                done = False
                for a4 in scands:
                    okk, a5, _why, _mvd = _apply_dbg(g2, a4, step)
                    if okk:
                        prefix.append(a5)
                        done = True
                        break
                if not done:
                    return None, '起手setup两个方向均受阻', list(prefix)
                if verbose:
                    print('  setup：对齐凸起挪位 -> %s' % (tuple(p2.location),))

        for i, a4 in enumerate(seal4):             # 封壳（外层共轭）
            okk, a5, why, _mvd = _apply_dbg(g2, a4, step)
            if not okk:
                return None, '封壳第%d步被拒(%s)' % (i + 1, why), list(prefix)
            prefix.append(a5)
        if not _hole_sealed(g2, vh):
            return None, '封壳完成但洞未封闭', list(prefix)
        if verbose:
            print('  封壳(用户)%s %d 步，凸起 -> %s'
                  % ('+挤入' if squeeze else '', len(prefix),
                     tuple(p2.location)))

        if squeeze:
            # 用户教学（甲/乙型）：凸起未与洞同列时，沿凸起行下缘切缝
            # ('h', pr-1, below)，把凸起所在部整带逐步推向洞列
            # （「下面左移/右移」，等效于洞上方整带反向推移）。
            while p2.location[1] != c:
                want = 'a' if p2.location[1] > c else 'd'
                a4 = ('h', p2.location[0] - 1, 'below', want, None)
                okk, a5, why, _mvd = _apply_dbg(g2, a4, step)
                if not okk:
                    return None, '挤入被拒(%s)' % why, list(prefix)
                prefix.append(a5)

        vp = tuple(p2.location)
        if inner_mode == 'direct':
            # 用户教学（2026-10-01 复原五档逐步解码）：内层填洞 =
            # 「同封壳缝升凸 → 单块滑入洞 → 同缝降回」。升凸/降回必须
            # 复用封壳的缝与侧（flag=1: v@c 右侧；flag=-1: v@(c-1) 左侧），
            # 通用填洞宏的 A 段会切换到相邻缝重组（"上移多次+换缝"），
            # 破坏封壳几何导致拆壳必散——用户明确指出此为 02/04 型错误根源。
            # 洞凸同 mod ⇒ 升距/滑距均为 step 整数倍，逐 step 执行即等价。
            seam_line, seam_side = (c, 'right') if flag == 1 else (c - 1, 'left')
            in_side = (vp[1] >= c + 1) if flag == 1 else (vp[1] <= c - 1)
            D = vp[0] - vh[0]
            if not (in_side and D >= 0):
                return None, ('直接共轭不适用(凸%s不在缝侧或D=%d)' % (vp, D)), \
                    list(prefix)
            n_lift = D // step
            for _ in range(n_lift):                # 升凸：凸起随组升到洞行
                okk, a5, why, _mvd = _apply_dbg(
                    g2, ('v', seam_line, seam_side, 'w'), step)
                if not okk:
                    return None, '升凸被拒(%s)' % why, list(prefix)
                prefix.append(a5)
            if p2.location[1] != vh[1]:            # 单块滑入（rep 指定凸起）
                sdir = 'd' if p2.location[1] < vh[1] else 'a'
                for _ in range(abs(p2.location[1] - vh[1]) // step):
                    a4 = ('h', vh[0] - 1, 'below', sdir, tuple(p2.location))
                    okk, a5, why, _mvd = _apply_dbg(g2, a4, step)
                    if not okk:
                        return None, '滑入被拒(%s)' % why, list(prefix)
                    prefix.append(a5)
            for _ in range(n_lift):                # 降回（升凸逆）
                okk, a5, why, _mvd = _apply_dbg(
                    g2, ('v', seam_line, seam_side, 's'), step)
                if not okk:
                    return None, '降回被拒(%s)' % why, list(prefix)
                prefix.append(a5)
            if vh not in gcoords(g2):
                return None, '直接共轭后洞%s未填' % (vh,), list(prefix)
            if verbose:
                print('  直接共轭内层(升%d步+滑入+降) 完成' % n_lift)
        else:
            # 内层旋转策略（2026-10-01 教学验证）：choose_rot 自动旋转在常规
            # 批量正确，但特殊姿态下会在封壳临时几何里破坏料条/垫洞的几何
            # 关系，拆壳逆动作必散架（"链走通但未还原"真因）→ 失败时以
            # force_rot='id'（不旋转、直接窄缝推入）重试。两级都保留。
            iacts, istats = _solve_couple(gcoords(g2), mv, nv, step, vh, vp,
                                          keep_partial=True,
                                          force_rot=inner_mode)
            if iacts is None or istats.get('partial'):
                return None, ('内部共轭失败: %s' % istats.get('reason', '?')), \
                    list(prefix) + list(iacts or [])
            if verbose:
                print('  内部共轭 %d 步' % len(iacts))
            if not _replay_apply(g2, iacts, mv, nv, step):
                return None, '内部共轭回放失败', list(prefix)
            if vh not in gcoords(g2):
                # 内层返回成功却没填中：_block_at(h) 应有块（h ∈ coords），
                # 该格仍空 = B 段终止判据被骗，不得拼进链里拆壳
                return None, ('内部共轭假阳性：洞%s仍空' % (vh,)), \
                    list(prefix) + list(iacts)
            prefix += list(iacts)

        for i, a4 in enumerate(unseal4):           # 逆外层共轭
            okk, a5, why, _mvd = _apply_dbg(g2, a4, step)
            if not okk:
                # 换边等价表达（用户复原失败01实证）：同缝异侧反向 ≡
                # 相对位移相同、绝对位置不同；is_solved 只看实心矩形
                # 形状不钉死位置，故被拒时换边重试。
                side2, d2 = _FLIP_SIDE_DIR[(a4[2], a4[3])]
                okk, a5, why, _mvd = _apply_dbg(
                    g2, (a4[0], a4[1], side2, d2, None), step)
                if not okk:
                    return None, '拆壳第%d步被拒(%s)' % (i + 1, why), list(prefix)
            prefix.append(a5)
        if require_solved:
            if not g2.is_solved():
                return None, '链走通但未还原', list(prefix)
        elif vh not in gcoords(g2):
            return None, '链走通但洞未填', list(prefix)
        return (list(prefix),
                {'seal': len(seal4),
                 'inner': len(prefix) - len(seal4) - len(unseal4),
                 'unseal': len(unseal4), 'flag': flag,
                 'inner_mode': inner_mode,
                 'squeeze': squeeze})

    # 六级尝试：直解(直接共轭/自动/id) → 挤入(直接共轭/自动/id)
    best = []
    reasons = []
    for squeeze in (False, True):
        for im in ('direct', None, 'id'):
            res = _run(squeeze, im)
            if res[0] is not None:
                return res
            tag = '直解' if not squeeze else '挤入'
            im_tag = {'direct': '直接', None: '自动', 'id': 'id'}[im]
            reasons.append('%s(%s):%s' % (tag, im_tag, res[1]))
            if len(res[2]) > len(best):
                best = res[2]
            if verbose:
                print('  %s(%s)未成(%s)' % (tag, im_tag, res[1]))
    return None, {'reason': '；'.join(reasons), 'prefix': best}


def solve_edge_gap(coords, m, n, step, verbose=False, hole=None,
                   anchor=None, require_solved=True):
    """单边缺口全链求解（用户算法）：缺口 → 上边缘 → _user_edge_chain。

    couple 模式（多空位驱动层）：显式喂 hole/anchor（缺口=窗内空位、
    凸起=窗外块，同 mod），成功判据 = 洞被填（require_solved=False），
    不要求整盘还原；此时不做 v1 回退（v1 只认单缺口）。
    失败回退 v1（左边缘规范型：专列/甩料封壳）。
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
    couple = hole is not None
    if couple:
        h_w = tuple(hole)
        if h_w not in holes:
            return None, {'reason': 'couple缺口不是窗内空位'}
        if anchor is None or tuple(anchor) not in coords:
            return None, {'reason': 'couple凸起不在盘上'}
        anchor = tuple(anchor)
    else:
        if len(holes) != 1:
            return None, {'reason': f'非单缺口（窗内空位 {len(holes)} 个）'}
        h_w = next(iter(holes))
    edge = _edge_of(h_w, r0, c0, wh[0], wh[1])
    if edge == 'INNER':
        return None, {'reason': '封闭孔洞（应交填洞宏）'}
    if edge == 'CORNER':
        return None, {'reason': '角缺口（应走 solve_corner_gap）'}

    # ---- 用户链：缺口 → 上边缘 ----
    name = _ROT_TO_TOP[edge]
    mv, nv = view_rotate.view_dims(name, m, n)
    vc = frozenset(view_rotate.rotate_xy(name, r - r0, c - c0, m, n)
                   for r, c in coords)
    vh = view_rotate.rotate_xy(name, h_w[0] - r0, h_w[1] - c0, m, n)

    def _to_world(a):
        gap, line, side, d, rep = a
        gap2, line2, side2, d2 = view_rotate.act_to_world(
            name, gap, line, side, d, m, n)
        line2 = line2 + (r0 if gap2 == 'h' else c0)
        rr, cc = view_rotate.rep_to_world(name, rep[0], rep[1], m, n)
        return (gap2, line2, side2, d2, (rr + r0, cc + c0))

    vp0 = None
    if couple:
        vp0 = view_rotate.rotate_xy(name, anchor[0] - r0, anchor[1] - c0,
                                    m, n)
    uacts, ustats = _user_edge_chain(build_game(vc, mv, nv), vh, step,
                                     verbose=verbose, p0=vp0,
                                     require_solved=require_solved)
    if uacts is not None:
        wall = [_to_world(a) for a in uacts]
        g = build_game(coords, m, n)
        ok = _replay_apply(g, wall, m, n, step)
        if require_solved:
            done_world = ok and g.is_solved()
        else:
            done_world = ok and h_w in gcoords(g)
        stats = {'steps': len(wall),
                 'seal': ustats['seal'], 'inner': ustats['inner'],
                 'unseal': ustats['unseal'], 'flag': ustats['flag'],
                 'rot': name, 'edge': edge, 'route': 'user2',
                 'view_solved': True, 'solved': done_world,
                 'secs': round(time.time() - t0, 3)}
        if couple:
            stats['couple'] = True
        if done_world:
            return wall, stats
        u_reason, u_prefix = '用户链回放未还原', []
    else:
        u_reason = ustats['reason']
        u_prefix = [_to_world(a) for a in ustats.get('prefix', [])]
    if verbose:
        print('  用户链未成(%s)%s' % (u_reason, '' if couple else '，回退 v1'))
    if couple:
        return None, {'reason': u_reason, 'edge': edge, 'couple': True,
                      'fail_world': u_prefix,
                      'secs': round(time.time() - t0, 3)}

    # ---- 回退 v1：左边缘规范型（专列/甩料封壳）----
    wall1, stats1 = _solve_edge_gap_v1(coords, m, n, step, verbose=verbose)
    if wall1 is not None and stats1.get('solved'):
        return wall1, dict(stats1, user_reason=u_reason, route='v1')
    fw1 = stats1.get('fail_world') or []
    return None, {'reason': '用户链:%s；v1:%s'
                             % (u_reason, stats1.get('reason', '?')),
                  'edge': edge, 'user_reason': u_reason,
                  'fail_world': fw1 if len(fw1) >= len(u_prefix) else u_prefix,
                  'secs': round(time.time() - t0, 3)}


def _solve_edge_gap_v1(coords, m, n, step, verbose=False):
    """v1 回退路径：左边缘规范型 + 甩料封壳（旧算法，保留兜底）。

    单边缺口全链：封壳 → 内部共轭(couple) → 拆壳。
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
        if edge in ('L', 'R', 'U', 'D', 'CORNER'):
            wall, stats = solve_gap_any(coords, m, n, step)
            return wall, dict(stats, route='gap_any')
    # 其余（封闭孔洞/多洞）交填洞宏驱动
    from solver.ml.fill_macro import solve_fill_macro
    res = solve_fill_macro(build_game(coords, m, n), step)
    if isinstance(res, tuple):
        return res, {'route': 'fill_macro', 'steps': len(res[0])}
    return None, {'reason': res.get('reason', '填洞宏失败'),
                  'route': 'fill_macro'}


def save_failure_archive(coords, m, n, step, wall5, tag, fname=None):
    """把失败案例存成游戏可读档（默认 save/补缺失败-<tag>.json）。

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
    fname = fname or ('补缺失败-%s.json' % tag)
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
                    stop_on_fail=False, segment_cb=None, **kwargs):
    """补缺宏（GUI 入口）：单边缺口 → 封壳+内部共轭+拆壳；其余交填洞宏。

    segment_cb：流式播放回调（label, actions5）——多空位贪心每解决一个
    couple 即回调，GUI 边算边播；返回协议含 fill_stream dict。

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
    try:
        return _solve_gap_macro_inner(game, coords, m, n, step,
                                      cancel_check, progress_callback,
                                      stop_on_fail, segment_cb)
    except _Cancelled:
        print('[补缺宏] 已停止（cancel）')
        return {'type': 'fill_fail', 'reason': '已停止', 'cancelled': True}


def _solve_gap_macro_inner(game, coords, m, n, step, cancel_check,
                           progress_callback, stop_on_fail, segment_cb=None):
    """solve_gap_macro 主体（cancel 异常由外层捕获）。"""
    (r0, c0, wh), _ov, holes, _out = window_of(coords, m, n, step)
    edge = None
    if len(holes) == 1:
        edge = _edge_of(next(iter(holes)), r0, c0, wh[0], wh[1])
    use_gap = edge in ('L', 'R', 'U', 'D', 'CORNER')
    if use_gap:
        wall, stats = solve_gap_any(coords, m, n, step)
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
    if len(holes) > 1:
        # 多空位局面（含缺口）：必须走统一驱动（couple 钩子分发洞/缺口）。
        # 旧路径 solve_fill_macro 对缺口 couple 全败——失败04 实证"不正常"。
        if progress_callback is not None:
            from solver.ml.fill_macro import _emit
            _emit(progress_callback, '多空位驱动', 0,
                  '洞%d 凸%d 统一couple' % (len(holes), len(_out)))
        acts, mst = solve_multi_vacancy(coords, m, n, step, mode='auto',
                                        progress_callback=progress_callback,
                                        cancel_check=cancel_check,
                                        segment_cb=segment_cb)
        if isinstance(acts, dict) and acts.get('type') == 'fill_stream':
            # 流式：贪心段已实时播放。全解直接回传；未全解再试紧凑救援
            # （从已播后的局面 end_coords 续算，动作不错位）
            if acts.get('solved'):
                return acts
            why = acts.get('reason', '多空位驱动未全解')
            resc = _compact_rescue(mst.get('end_coords', coords), m, n,
                                   step, why, cancel_check=cancel_check)
            if resc is not None:
                acts = dict(acts, actions=resc[0], rep_cells=resc[1],
                            solved=True)
                return acts
            print('[补缺宏] 多空位 partial：%s' % why)
            return acts
        if acts is not None and not mst.get('partial'):
            return [a[:4] for a in acts], [a[4] for a in acts]
        why = mst.get('reason', '多空位驱动未全解')
        resc = _compact_rescue(coords, m, n, step, why,
                               cancel_check=cancel_check)
        if resc is not None:
            return resc
        if mst.get('partial'):
            # partial（有成果未完）：返回 fill_partial（GUI 播已成功部分并
            # 提示断点）——旧版直接回元组会被 GUI 当全解播完然后停在半路
            print('[补缺宏] 多空位 partial：%s' % why)
            acts4 = [a[:4] for a in acts]
            reps = [a[4] if len(a) > 4 else None for a in acts]
            return {'type': 'fill_partial', 'actions': acts4,
                    'rep_cells': reps, 'reason': why}
        return {'type': 'fill_fail', 'reason': why,
                'solver_name': '多空位驱动', 'fail_world': []}
    res = solve_fill_macro(game, step, cancel_check=cancel_check,
                           progress_callback=progress_callback,
                           segment_cb=segment_cb)
    if isinstance(res, dict):
        res.setdefault('solver_name', '填洞宏')
        if use_gap:
            res['reason'] = ('缺口分支未成(%s)；填洞宏：%s'
                             % (gap_why, res.get('reason', '失败')))
    return res


# ---------------------------------------------------------------------------
# 多空位统一驱动（洞 + 缺口）：框架 = solve_multi_void 贪心 couple 驱动，
# 唯一差异在求解器分发——洞走填洞宏（A-B-A′ 单层共轭），缺口走补缺链
# （封壳+内部共轭+拆壳 双层共轭）；验收闸门同一把（窗口方块数提升）。
# ---------------------------------------------------------------------------
def _vacancy_couple_hook(gap_only, cancel_check=None):
    """构造统一 couple 求解器。gap_only=False：洞回落填洞宏（auto 模式）；
    True：洞返回无成果（纯缺口模式）。cancel_check 注入填洞宏 A/B 段。"""
    def hook(coords, m, n, step, h, p):
        _reg, _ov, holes, _out = window_of(coords, m, n, step)
        if h not in holes or p not in coords:
            return None, {'reason': 'couple坐标无效'}
        edge = _edge_of(h, _reg[0], _reg[1], _reg[2][0], _reg[2][1])
        if edge in ('L', 'R', 'U', 'D'):
            acts, st = solve_edge_gap(coords, m, n, step, hole=h, anchor=p,
                                      require_solved=False)
            if acts is None:
                # 主解读盲区（如凸起挂列 0）→ D4 轨道成员逐一试
                acts, st2 = _couple_orbit_solve(coords, m, n, step, h, p, 'EDGE')
                st = st2 if acts is None else st2
            return acts, st
        if edge == 'CORNER':
            acts, st = solve_corner_gap(coords, m, n, step, hole=h, anchor=p,
                                        require_solved=False)
            if acts is None:
                # 失败07终局实证：角链拒（凸起挂下缘列0），轨道 fh 架下
                # 补缺链可解 → 主解读失败走 D4 轨道兜底
                acts, st2 = _couple_orbit_solve(coords, m, n, step, h, p,
                                                'CORNER')
                st = st2 if acts is None else st2
            return acts, st
        if gap_only:
            return None, {'reason': '非缺口（封闭孔洞归填洞宏）'}
        return solve_single_void(coords, m, n, step, hole=h, anchor=p,
                                 keep_partial=True,
                                 cancel_check=cancel_check)
    return hook


def solve_single_segment(game, step, p, cancel_check=None,
                         progress_callback=None, **kwargs):
    """手动单段求解（GUI 入口，Ctrl+G）：只处理用户指定的凸起 p。

    配洞规则：当前窗口空位中与 p 同 mod 的候选取曼哈顿距离最近者。
    求解链：边缘缺口（L/R/U/D）→ 补缺链（轨道兜底）；CORNER → 角链；
    内部孔洞 → 填洞宏 couple；全败 → 粘上接走（convoy）兜底。

    成功标准：回放全程合法且目标洞 h 被填上（不要求整盘还原——
    用户逐段点名，驱动权在用户手里）。
    返回 (actions4, reps) 或 {'type': 'fill_fail', 'reason': ...}。
    """
    try:
        coords = frozenset(tuple(b.location) for b in game.blocks)
        m, n = game.m, game.n
        p = tuple(p)
        _reg, ov0, holes, outside = window_of(coords, m, n, step)
        if p not in outside:
            return {'type': 'fill_fail',
                    'reason': '请点选窗口外的凸起方块（当前选中块不在窗外）'}
        cands = [h for h in holes
                 if (h[0] - p[0]) % step == 0 and (h[1] - p[1]) % step == 0]
        if not cands:
            return {'type': 'fill_fail',
                    'reason': '该凸起与所有空位不同 mod（step 错位），无法配对'}
        h = min(cands, key=lambda q: abs(q[0] - p[0]) + abs(q[1] - p[1]))
        r0, c0, wh = _reg[0], _reg[1], _reg[2]
        edge = _edge_of(h, r0, c0, wh[0], wh[1])
        acts, stats = None, {}
        if edge in ('L', 'R', 'U', 'D'):
            acts, stats = solve_edge_gap(coords, m, n, step, hole=h,
                                         anchor=p, require_solved=False)
            if acts is None:
                acts, stats = _couple_orbit_solve(coords, m, n, step, h, p,
                                                  'EDGE')
        elif edge == 'CORNER':
            acts, stats = solve_corner_gap(coords, m, n, step, hole=h,
                                           anchor=p, require_solved=False)
            if acts is None:
                acts, stats = _couple_orbit_solve(coords, m, n, step, h, p,
                                                  'CORNER')
        else:
            acts, stats = solve_single_void(coords, m, n, step, hole=h,
                                            anchor=p, keep_partial=False,
                                            cancel_check=cancel_check)
        if acts is not None:
            g = build_game(coords, m, n)
            if (_replay_apply(g, acts, m, n, step)
                    and any(tuple(b.location) == h for b in g.blocks)
                    and window_of(frozenset(tuple(b.location)
                                            for b in g.blocks),
                                  m, n, step)[1] >= ov0):
                acts4 = [a[:4] for a in acts]
                reps = [a[4] if len(a) > 4 else None for a in acts]
                return acts4, reps
            acts = None   # 回放失败/洞未填/ov 下降 → 视为失败，继续兜底
        # 补缺链/填洞宏失败 → 粘上接走兜底（交互场景预算收紧）
        _emit(progress_callback, '单段·粘上接走', 0,
              '洞%s←凸%s 行军搜索' % (h, p))
        cacts, _used = _convoy_fill(coords, m, n, step, h, p,
                                    max_nodes=800,
                                    progress_callback=progress_callback,
                                    cancel_check=cancel_check)
        if cacts:
            g2 = build_game(coords, m, n)
            if (_replay_apply(g2, cacts, m, n, step)
                    and window_of(frozenset(tuple(b.location)
                                            for b in g2.blocks),
                                  m, n, step)[1] >= ov0):
                acts4 = [a[:4] for a in cacts]
                reps = [a[4] if len(a) > 4 else None for a in cacts]
                return acts4, reps
        why = stats.get('reason', stats.get('error', '失败')) \
            if isinstance(stats, dict) else '失败'
        return {'type': 'fill_fail',
                'reason': '单段求解失败（补缺链+粘上接走均未成）：%s' % why,
                'solver_name': '单段求解'}
    except _Cancelled:
        print('[单段求解] 已停止（cancel）')
        return {'type': 'fill_fail', 'reason': '已停止', 'cancelled': True}
    except Exception as e:
        return {'type': 'fill_fail', 'reason': f'单段求解异常：{e}',
                'solver_name': '单段求解'}


def solve_multi_vacancy(coords, m, n, step, mode='auto', verbose=False,
                        rng=None, progress_callback=None, cancel_check=None,
                        segment_cb=None, **kwargs):
    """多空位（洞+缺口）统一贪心驱动（用户设计：与多洞框架同一函数，
    参数决定填洞/补缺）。

    mode：'auto'=洞→填洞宏、缺口→补缺链；'hole'=只填洞（=原多洞行为）；
    'gap'=只补缺（封闭孔洞跳过）。
    segment_cb：流式播放回调（贪心每接受一个 couple 即回调）；此时
    DFS 兜底从「已播段之后的局面」（stats.end_coords）续算，返回协议
    变为 fill_stream dict（streamed=已实时播的步数）。
    返回协议同 solve_multi_void：(actions, stats) / (None, stats)。
    """
    coords = frozenset(coords)
    if len(coords) != m * n:
        return None, {'error': f'格数 {len(coords)} != {m * n}'}
    g = build_game(coords, m, n)
    if g.is_solved():
        return [], {'steps': 0, 'secs': 0.0, 'multi': True, 'mode': mode}
    hook = None
    if mode in ('auto', 'gap'):
        hook = _vacancy_couple_hook(gap_only=(mode == 'gap'),
                                    cancel_check=cancel_check)
    acts, stats = solve_multi_void(coords, m, n, step, verbose=verbose,
                                   rng=rng, couple_hook=hook,
                                   cancel_check=cancel_check,
                                   segment_cb=segment_cb, **kwargs)
    stats['mode'] = mode
    streamed = stats.get('streamed', 0)
    if acts is not None and not stats.get('partial'):
        if segment_cb is not None:
            from solver.ml.fill_macro import _split_actions
            acts4, reps = _split_actions(acts[streamed:])
            return {'type': 'fill_stream', 'streamed': streamed,
                    'actions': acts4, 'rep_cells': reps, 'solved': True,
                    'mode': mode}, stats
        return acts, stats                     # 贪心全解，不进搜索
    # 贪心停机/partial → 宏级 DFS 回溯兜底（顺序依赖实证：换候选序可解）
    if verbose:
        print('  贪心未全解(%s)，宏级搜索兜底' % stats.get('reason', 'partial'))
    from solver.ml.fill_macro import _emit
    _emit(progress_callback, '宏级搜索', 0, '贪心未全解，DFS 回溯兜底')
    # 流式模式：贪心段已实时播放，DFS 从已播后的局面续算（动作才不错位）
    base = stats.get('end_coords', coords) if segment_cb is not None else coords
    acts2, stats2 = solve_multi_search(base, m, n, step,
                                       couple_hook=hook, verbose=verbose,
                                       progress_callback=progress_callback,
                                       cancel_check=cancel_check)
    if acts2 is not None and not stats2.get('partial'):
        stats2['mode'] = mode
        stats2['greedy'] = {'steps': len(acts) if acts else 0,
                            'reason': stats.get('reason')}
        if segment_cb is not None:
            from solver.ml.fill_macro import _split_actions
            acts4, reps = _split_actions(acts2)
            return {'type': 'fill_stream', 'streamed': streamed,
                    'actions': acts4, 'rep_cells': reps, 'solved': True,
                    'mode': mode}, stats2
        return acts2, stats2
    if segment_cb is not None:
        # 搜索也无全解：贪心 partial 段已实时播，未播部分=空（贪心产物
        # 已含在流式段里），只回传流式汇总
        return {'type': 'fill_stream', 'streamed': streamed,
                'actions': [], 'rep_cells': [], 'solved': False,
                'reason': stats.get('reason', '多空位驱动未全解'),
                'mode': mode}, stats
    return acts, stats                         # 搜索也无全解 → 回贪心产物


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
