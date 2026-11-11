# -*- coding: utf-8 -*-
"""护栏：整体平移消去（防偏移·序列改写）。

用户口径（2026-11-11）：「就像魔方的轉體可以消掉，滑塊整體平移也可以
消掉……禁止使用移動相機」。

事实依据：复原判定只看形状（``game.is_solved`` 取外接矩形、平移不变），
``try_move_ex`` 还显式拒绝「全员选中」并注明平移无关。所以一次滑动的
「A 平移 δ」与「补集平移 −δ」只差一个整体平移，后者在画面上是大片不动、
小片滑——这就是要消掉的那一份。

A 组：``_flip_act`` 直测（构造盘面，换侧动作合法且形状一致、动的块更少）。
B 组：``BulkStaticRewriter`` 端到端（步数不变 / 回放合法 / 仍复原 / 漂移下降）。
C 组：反向验证（关掉换侧 → 漂移回到原来的量级），证明 A/B 不是恒绿。
D 组：相机 gate（流式求解期间相机恒 (0,0)；存档回放仍补偿）。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game import SliderMatrix
from solver.anti_drift import (BulkStaticRewriter, _flip_act,
                               centroid_offset, rewrite_bulk_static)
from solver.ml.fill_macro import build_game, _capture_apply

FAILS = []


def check(cond, msg, detail=''):
    if cond:
        print('  OK   %s' % msg)
    else:
        print('  FAIL %s   %s' % (msg, detail))
        FAILS.append(msg)


def _coords(g):
    return frozenset((b.location[0], b.location[1]) for b in g.blocks)


def _shape(coords):
    mr = min(r for r, c in coords)
    mc = min(c for r, c in coords)
    return frozenset((r - mr, c - mc) for r, c in coords)


def _apply(g, act, step):
    return _capture_apply(g, act, step)[0]


def _drift(coords0, m, n, step, acts5):
    g = build_game(coords0, m, n)
    c0 = centroid_offset(coords0)
    mx = 0.0
    for a in acts5:
        if not _apply(g, a, step):
            return None, False
        c = centroid_offset(_coords(g))
        mx = max(mx, ((c[0] - c0[0]) ** 2 + (c[1] - c0[1]) ** 2) ** 0.5)
    return mx, g.is_solved()


def _snap(g):
    return {id(b): tuple(b.location) for b in g.blocks}


def _moved_count(g, snap):
    """按**块身份**数「真的被推动了几块」（坐标集合对称差会把重叠段吃掉）。"""
    return sum(1 for b in g.blocks
               if snap.get(id(b)) != tuple(b.location))


# ---------------------------------------------------------------- A 直测换侧
def group_a():
    print('[A] _flip_act 换侧：合法、同形状、动的块更少')
    # 4×4 满块（列 0-3）+ 间隔一列（列 4）+ 一条 4 块竖条（列 5）
    cells = frozenset([(r, c) for r in range(4) for c in range(4)]
                      + [(r, 5) for r in range(4)])
    g = build_game(cells, 4, 4)
    step = 1
    act = ('v', 4, 'left', 'd', (0, 0))
    a_flip = _flip_act(cells, act, step)
    check(a_flip is not None, 'A1 补集能被单步切出来 → 给出换侧动作',
          'act=%r' % (act,))
    if a_flip is None:
        return
    gN = build_game(cells, 4, 4)
    gF = build_game(cells, 4, 4)
    snapN, snapF = _snap(gN), _snap(gF)
    okN = _apply(gN, act, step)
    okF = _apply(gF, a_flip, step)
    check(okN and okF, 'A2 原动作与换侧动作都合法', 'okN=%s okF=%s' % (okN, okF))
    if not (okN and okF):
        return
    check(_shape(_coords(gN)) == _shape(_coords(gF)),
          'A3 两者形状完全一致（只差一个整体平移）',
          'N=%s F=%s' % (_shape(_coords(gN)), _shape(_coords(gF))))
    mv_n = _moved_count(gN, snapN)
    mv_f = _moved_count(gF, snapF)
    check(mv_f < mv_n, 'A4 换侧推的块更少（大片真不动）',
          '原=%d 换侧=%d / 共 %d' % (mv_n, mv_f, len(cells)))
    # 小片一侧才是被推的：换侧后 16 块那一大块原地不动
    still = set(cells) & set(_coords(gF))
    check(len(still) >= 16, 'A5 换侧后 4×4 主体原地不动', 'still=%d' % len(still))

    # 补集切不出来时必须返回 None（防止「乱挑一侧」把解改坏）
    cells2 = frozenset([(0, 0), (0, 1), (0, 2), (0, 3),
                        (1, 0), (1, 1), (1, 2), (1, 3),
                        (2, 1), (2, 2), (3, 1), (3, 2),
                        (1, 5), (2, 5)])   # 右侧独立两格，中间隔一列
    g2 = build_game(cells2, 4, 4)
    # 缝在列 2：左侧分量 vs 右侧零碎 → 补集不是单个分量
    a2 = ('v', 2, 'left', 'd', (0, 0))
    res2 = _flip_act(cells2, a2, 1)
    ok_shape = True
    if res2 is not None:
        t1 = build_game(cells2, 4, 4)
        t2 = build_game(cells2, 4, 4)
        ok_shape = (_apply(t1, a2, 1) and _apply(t2, res2, 1)
                    and _shape(_coords(t1)) == _shape(_coords(t2)))
    check(res2 is None or ok_shape,
          'A6 换侧若给出，必须形状一致（不允许偷换解）', 'res=%r' % (res2,))


# ------------------------------------------------- B 改写器端到端（求解器真解）
def _solve_case(m, n, seed, step=2, bulk_static=False):
    """取一份**未经改写**的真解（bulk_static=False），改写由本测试自己调。"""
    import copy
    import random
    from solver.auto_solver import auto_solve
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=40, step=step)
    c0 = frozenset(tuple(b.location) for b in g.blocks)
    res = auto_solve(copy.deepcopy(g), step, idle_budget=2, rng_seed=seed,
                     bulk_static=bulk_static)
    if not (isinstance(res, tuple) and len(res) == 2):
        return c0, None, None
    return c0, res[0], res[1]


def group_b():
    print('[B] BulkStaticRewriter：步数不变 / 回放合法 / 仍复原 / 漂移下降')
    c0, acts, reps = _solve_case(5, 5, 3)
    check(acts is not None, 'B0 5×5 求解成功（拿真解做样本）')
    if acts is None:
        return
    five = [tuple(a)[:4] + ((tuple(reps[i]),) if reps and i < len(reps)
                            and reps[i] else (None,))
            for i, a in enumerate(acts)]
    raw_max, raw_ok = _drift(c0, 5, 5, 2, five)
    rw = BulkStaticRewriter(c0, 5, 5, 2)
    new, end = rw.feed(five)
    flips = rw.flips
    flipped_idx = set(rw.flip_idx)
    check(len(new) == len(five), 'B1 步数不变（改写不增不减）',
          '%d vs %d' % (len(new), len(five)))
    new_max, new_ok = _drift(c0, 5, 5, 2, new)
    check(raw_ok and new_ok, 'B2 原解与改写解都能回放到复原',
          'raw=%s new=%s' % (raw_ok, new_ok))
    check(flips > 0, 'B3 样本里确实发生了换侧（判据非空转）', 'flips=%d' % flips)
    check(new_max is not None and raw_max is not None and new_max < raw_max - 0.5,
          'B4 漂移明显下降', '原=%.2f 改写=%.2f' % (raw_max or -1, new_max or -1))
    check(new_max is not None and new_max <= 2.5,
          'B5 改写后残余漂移 ≤2.5 格（与打乱 1 格同量级）',
          'got=%.2f' % (new_max or -1))

    # 逐步：换过侧的步，推动的块数必须 ≤ 一半
    g = build_game(c0, 5, 5)
    bad = []
    for i, a in enumerate(new):
        snap = _snap(g)
        if not _apply(g, a, 2):
            bad.append((i, 'illegal'))
            break
        mv = _moved_count(g, snap)
        if i in flipped_idx and mv * 2 > len(c0):
            bad.append((i, mv))
    check(not bad, 'B6 换过侧的步都只推小片（≤ 全盘一半）', 'bad=%r' % (bad,))

    # 用户可见属性：推动「多半个盘面」的步数应大幅减少
    def _majority_steps(seq):
        gg = build_game(c0, 5, 5)
        cnt = 0
        for a in seq:
            snap = _snap(gg)
            if not _apply(gg, a, 2):
                break
            if _moved_count(gg, snap) * 2 > len(c0):
                cnt += 1
        return cnt
    maj_raw, maj_new = _majority_steps(five), _majority_steps(new)
    check(maj_new < maj_raw, 'B7 「推大半个盘面」的步数减少',
          '原=%d 改写=%d' % (maj_raw, maj_new))

    # 影子盘面终态 == 返回的 end（GUI 的 checkpoint 直接用它）
    g2 = build_game(c0, 5, 5)
    okall = all(_apply(g2, a, 2) for a in new)
    check(okall and frozenset(_coords(g2)) == frozenset(end),
          'B8 段末影子盘面与返回终态一致',
          'same=%s' % (okall and frozenset(_coords(g2)) == frozenset(end)))


# ------------------------------------------------------- C 反向验证（要转红）
def group_c():
    print('[C] 反向验证：关掉换侧 → 漂移回到原量级（证明判据有效）')
    import solver.anti_drift as ad
    c0, acts, reps = _solve_case(5, 5, 3)
    if acts is None:
        check(False, 'C0 求解失败，无法反向验证')
        return
    five = [tuple(a)[:4] + ((tuple(reps[i]),) if reps and i < len(reps)
                            and reps[i] else (None,))
            for i, a in enumerate(acts)]
    raw_max, _ok = _drift(c0, 5, 5, 2, five)
    orig = ad._flip_act
    try:
        ad._flip_act = lambda *a, **k: None      # 禁掉换侧
        new, _end, flips = rewrite_bulk_static(c0, 5, 5, 2, five)
    finally:
        ad._flip_act = orig
    off_max, _ok2 = _drift(c0, 5, 5, 2, new)
    check(flips == 0, 'C1 禁掉换侧后一次都不换', 'flips=%d' % flips)
    check(off_max is not None and raw_max is not None
          and off_max > raw_max * 0.7,
          'C2 没有换侧时漂移回到原量级（判据真能抓到差异）',
          '原=%.2f 无换侧=%.2f' % (raw_max or -1, off_max or -1))


# ------------------------------------------------------------- D 相机 gate
class _Block(object):
    def __init__(self, r, c):
        self.location = [r, c]
        self.be_opted = False
        self.group = 0


class _Fake(object):
    """只装 _anti_drift_cam_offset / _cam_anti_drift_px 需要的字段。"""

    def __init__(self):
        self.anti_drift_enabled = True
        self.macro_executing = True
        self.macro_selecting_base = False
        self._auto_streamed = False
        self._auto_stage_active = False
        self._anti_drift_origin = None
        self._anti_drift_cam = (0, 0)
        self._anti_drift_active_prev = False
        self.game = type('G', (), {})()
        self.game.blocks = [_Block(r, c) for r in range(6) for c in range(6)]

    def _frame_render_positions(self):
        return {}


def group_d():
    print('[D] 相机 gate：流式求解不使用相机，存档回放仍补偿')
    from gui.renderer import RendererMixin
    f = _Fake()
    off = RendererMixin._anti_drift_cam_offset(f, 40)
    check(off == (0, 0), 'D1 首帧无漂移 → 0')

    # 整盘平移 +3 行（远大于死区）：存档回放必须补偿
    for b in f.game.blocks:
        b.location[0] += 3
    off_replay = RendererMixin._anti_drift_cam_offset(f, 40)
    check(off_replay[1] != 0,
          'D2 存档回放（非流式）仍做相机补偿，未回归', 'off=%r' % (off_replay,))

    # 流式求解：同样的漂移，相机必须恒 0
    f._auto_streamed = True
    off_solve = RendererMixin._anti_drift_cam_offset(f, 40)
    check(off_solve == (0, 0), 'D3 流式求解期间相机恒 (0,0)（禁止移动相机）',
          'off=%r' % (off_solve,))
    cam = RendererMixin._cam_anti_drift_px(f)
    check(cam == (0, 0), 'D4 命中路径读到的相机偏移同样为 (0,0)', 'cam=%r' % (cam,))

    f._auto_streamed = False
    f._auto_stage_active = True
    off_hyb = RendererMixin._anti_drift_cam_offset(f, 40)
    check(off_hyb == (0, 0), 'D5 混合流式（_auto_stage_active）同样不移动相机',
          'off=%r' % (off_hyb,))


if __name__ == '__main__':
    group_a()
    group_b()
    group_c()
    group_d()
    print()
    if FAILS:
        print('FAILED %d:' % len(FAILS))
        for m in FAILS:
            print('  -', m)
        sys.exit(1)
    print('ALL PASS')
