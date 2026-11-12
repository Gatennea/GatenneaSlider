# -*- coding: utf-8 -*-
r"""粘上接走（band_shift）底层修复护栏（task #47 ③ 修其底层 bug）。

覆盖两处修复：
  1) 单轴→对角：旧实现只沿单一轴移动源凸起、丢弃斜对角另一轴分量，导致
     对角线凸起永远到不了 h'；新实现逐轴分解（行→列 / 列→行 两序各试），
     抽出可复用的 _relay_1d / _relay_bump。
  2) mode B「贴上判定」里误用作用域外的局部变量 opp（NameError），改回模块级
     _OPP_DIR。

P1  对角源接运：构造「L 形清空通道」盘面，_relay_bump 必须把凸起从 (1,1)
     对角送到 (3,4)，且回放合法。
P2  反向验证①：把 _relay_bump 打回旧单轴实现，同一盘面必须返回 None —— 证明
     对角修复是「让该盘面可解」的充要改动（行为级，非字符串比对）。
P3  反向验证②：把 _relay_1d 打回修复前的 buggy 版（helper 内引用作用域外
     opp → NameError），调用 _relay_bump 必抛 NameError；恢复后同盘不再抛。
P4  加档接线：_edge_band_shift_attempt 在开洞几何下被调用，必须返回二元组、
     不抛异常（无论原语给出解还是 None）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import solver.ml.fill_macro as FM                                       # noqa: E402
from solver.ml.fill_macro import (build_game, gcoords, _relay_bump,     # noqa: E402
                                  _replay_apply, _DIRS)
from solver.ml import gap_solver as G                                   # noqa: E402

M, N, STEP = 4, 5, 1
P = (1, 1)
H_NEW = (3, 4)
# 全部格子，仅挖空 p 的「L 形」清空通道（下行 + 右行），使对角两轴单轴接运均成立
_HOLES = {(2, 1), (3, 1), (3, 2), (3, 3), (3, 4)}
COORDS = frozenset((r, c) for r in range(M) for c in range(N)
                   if (r, c) not in _HOLES)

FAILS = []


def check(name, cond, detail=''):
    tag = 'OK  ' if cond else 'FAIL'
    print('  [%s] %s %s' % (tag, name, detail))
    if not cond:
        FAILS.append(name)


def run():
    g = build_game(COORDS, M, N)
    print('=== 粘上接走（band_shift）对角修复护栏（%d 块 / p=%s / h=%s）===' % (len(COORDS), P, H_NEW))

    # ---- P1：对角源接运应成功 ----
    res = _relay_bump(g, P, H_NEW, STEP)
    ok_p1 = False
    if res is not None:
        sub, g2 = res
        g3 = build_game(COORDS, M, N)
        ok_replay = _replay_apply(g3, sub, M, N, STEP)
        ok_p1 = ok_replay and (H_NEW in gcoords(g3))
    check('P1 对角 _relay_bump 返回有效解且回放把凸起送到 h\'', ok_p1)

    # ---- P2：反向验证①（旧单轴实现必须失败）----
    def _old_relay_bump(g1, p_src, h_new, step, cancel_check=None):
        # 复刻修复前：只沿首个非零轴移动，另一轴分量被丢弃
        delta = (h_new[0] - p_src[0], h_new[1] - p_src[1])
        axis = 0 if delta[0] else 1
        if delta[axis] % step or abs(delta[axis]) > 6 * step:
            return None
        k2 = abs(delta[axis]) // step
        d2 = ('s' if delta[0] > 0 else 'w') if axis == 0 else \
             ('d' if delta[1] > 0 else 'a')
        r = FM._relay_1d(g1, p_src, axis, k2, d2, step, cancel_check)
        if r is None:
            return None
        sub, _g, new_p = r
        return (sub, _g) if new_p == h_new else None

    orig_rb = FM._relay_bump
    FM._relay_bump = _old_relay_bump
    try:
        old_res = FM._relay_bump(g, P, H_NEW, STEP)
    finally:
        FM._relay_bump = orig_rb
    check('P2 反向：旧单轴实现在对角盘面返回 None（证明对角修复是充要改动）',
          old_res is None)

    # ---- P3：反向验证②（修复前的 NameError 必须复现，恢复后消失）----
    def _buggy_relay_1d(g, p_cur, axis, k2, d2, step, cancel_check=None):
        # 复刻修复前 bug：helper 内引用作用域外才存在的 opp
        _dt, _dc = _DIRS[opp[d2]]   # NameError: name 'opp' is not defined
        return None

    orig_r1 = FM._relay_1d
    FM._relay_1d = _buggy_relay_1d
    raised = False
    try:
        _relay_bump(g, P, H_NEW, STEP)
    except NameError:
        raised = True
    finally:
        FM._relay_1d = orig_r1
    check('P3 反向：修复前 helper 在 mode B 触发 NameError', raised)

    fixed_ok = False
    try:
        fixed_res = _relay_bump(g, P, H_NEW, STEP)
        fixed_ok = fixed_res is not None
    except NameError as e:
        print('   修复后异常: %r' % e)
    check('P3 修复后 mode B 不再抛 NameError', fixed_ok)

    # ---- P4：加档接线不抛异常、返回二元组 ----
    acts, info = G._edge_band_shift_attempt(COORDS, M, N, STEP, H_NEW)
    check('P4 _edge_band_shift_attempt 返回二元组且不抛异常',
          isinstance(acts, list) or acts is None)

    print('\n=== %s ===' % ('ALL PASS' if not FAILS else 'FAILED: %s' % FAILS))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(run())
