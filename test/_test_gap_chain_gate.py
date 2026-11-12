# -*- coding: utf-8 -*-
r"""补缺链六级机构按「段末聚拢度提升」择优 — 8×8 近解残局回归锁。

来源：save/2-8-8-20261111-220716waiting_optimize.json 第 109 步（已内嵌盘面，
不依赖存档文件）。该盘面 3 洞 3 凸起、聚拢度 61/64，红色这组是
洞 (4,-1) <- 凸起 (-2,3)。

修复前：_user_edge_chain 六级「第一个成功就返回」，而 couple 模式
(require_solved=False) 的成功判据只有「洞被填上」，于是直解(直接) 9 步
把聚拢度 61→42 的解抢先返回；排在后面的直解(自动/id) 11 步是 61→62
的正解，却永远没机会试。上层段级闸门拒收 42 的解，导致：
  - 选块填空报「补缺链+粘上接走均未成」（其实补缺链算出来了）
  - 填洞补缺主驱动判「所有 couple 无成果」在 109 步停机

修复后：couple 模式六级按段末聚拢度是否提升择优，早停采纳 11 步正解。

反向验证：把 gap_solver.py 六级循环里的择优分支改回 `return res`
（即修复前行为），本脚本 P1/P2/P3 必须转红。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver.ml.fill_macro import (build_game, gcoords, window_of,     # noqa: E402
                                  _replay_apply, _overlap_raised,
                                  solve_multi_void)
from solver.ml import gap_solver as G                                   # noqa: E402

M, N, STEP = 8, 8, 2
HOLE = (4, -1)
BUMP = (-2, 3)

# 存档 step109 的完整盘面（64 块）
COORDS = frozenset([
    (-2, 0), (-2, 3), (-1, -1), (-1, 0), (-1, 2), (-1, 3), (-1, 4),
    (-1, 5), (-1, 6), (0, -1), (0, 0), (0, 1), (0, 2), (0, 3), (0, 4),
    (0, 5), (0, 6), (1, -1), (1, 0), (1, 1), (1, 2), (1, 3), (1, 4),
    (1, 5), (1, 6), (2, -1), (2, 0), (2, 1), (2, 2), (2, 3), (2, 4),
    (2, 5), (2, 6), (3, -1), (3, 0), (3, 1), (3, 2), (3, 3), (3, 4),
    (3, 5), (3, 6), (4, 0), (4, 1), (4, 2), (4, 3), (4, 4), (4, 5),
    (4, 6), (5, -1), (5, 0), (5, 1), (5, 2), (5, 3), (5, 4), (5, 5),
    (5, 6), (6, -1), (6, 0), (6, 1), (6, 3), (6, 4), (6, 5), (6, 6),
    (7, 5),
])

FAILS = []


def check(name, cond, detail=''):
    tag = 'OK  ' if cond else 'FAIL'
    print('  [%s] %s %s' % (tag, name, detail))
    if not cond:
        FAILS.append(name)


def ov(cc):
    return window_of(cc, M, N, STEP)[1]


def run():
    c = COORDS
    ov0 = ov(c)
    print('=== 补缺链六级择优护栏（段首聚拢 %d）===' % ov0)

    # P1 输入盘面本身
    check('P1 盘面 64 块 / 段首聚拢 61',
          len(c) == M * N and ov0 == 61,
          '块=%d ov=%d' % (len(c), ov0))

    # P2 补缺链直接产物：必须段末提升（修复前是 9 步 / 42）
    acts, st = G.solve_edge_gap(c, M, N, STEP, hole=HOLE, anchor=BUMP,
                               require_solved=False)
    end_ov = None
    if acts is not None:
        g = build_game(c, M, N)
        ok = _replay_apply(g, acts, M, N, STEP)
        end_ov = ov(gcoords(g)) if ok else None
        hole_filled = HOLE in gcoords(g)
    else:
        ok = False
        hole_filled = False
    print('  补缺链: %s' % ('None' if acts is None else '%d 步' % len(acts)))
    check('P2 补缺链回放合法且目标洞被填', ok and hole_filled,
          'hole_filled=%s' % hole_filled)
    check('P2 补缺链段末聚拢提升（61→62）',
          end_ov is not None and end_ov > ov0,
          '段末 ov=%s' % end_ov)
    check('P2 补缺链采纳 11 步正解而非 9 步散架解',
          acts is not None and len(acts) == 11,
          '步数=%s' % (None if acts is None else len(acts)))
    check('P2 段级闸门 _overlap_raised 认可该产物',
          acts is not None and _overlap_raised(c, M, N, STEP, acts))

    # P3 选块填空入口：修复前误报「补缺链+粘上接走均未成」
    res = G.solve_single_segment(build_game(c, M, N), STEP,
                                 p=BUMP, h=HOLE)
    is_actions = isinstance(res, tuple) and res and isinstance(res[0], list)
    print('  选块填空: %s' % ('动作 %d 步' % len(res[0]) if is_actions
                             else str(res)[:80]))
    check('P3 选块填空返回动作而非 fill_fail', is_actions)
    if is_actions:
        check('P3 选块填空动作段末提升',
              _overlap_raised(c, M, N, STEP,
                              [(a[0], a[1], a[2], a[3], tuple(r) if r else None)
                               for a, r in zip(res[0], res[1])]))

    # P4 主驱动从 109 能自动采纳第一段（修复前在 109 停机、零进展）
    hook = G._vacancy_couple_hook(gap_only=False)
    segs = []

    def cb(label, a):
        segs.append((label, a))

    a4, s4 = solve_multi_void(c, M, N, STEP, couple_hook=hook,
                              hook_spec=('vacancy', False), segment_cb=cb)
    print('  主驱动: %s / 流式段 %d' %
          ('None' if a4 is None else '%d 步' % len(a4), len(segs)))
    check('P4 主驱动从 109 至少推进一段', len(segs) >= 1)
    # 注：本测试入口是 solve_multi_void（单趟贪心，解完一个 couple 即返回），
    # 故终态是 61→62 的一段推进；完整 64 自动全解由 GUI 入口 solve_gap_macro
    # 的循环驱动达成，锁在 _test_convoy_time_cap.py 的 P3。修复前主驱动在 109
    # 零进展停机，故「推进到 62」即捕获该回归。
    check('P4 主驱动终态聚拢 62（采纳首个 couple，修复前零进展停机）',
          ov(frozenset(s4.get('end_coords', c))) == 62,
          'end_ov=%s' % ov(frozenset(s4.get('end_coords', c))))

    # P5 require_solved=True（单缺口全解路径）行为不变：仍是首个成功即返回
    # 该盘面是多空位，单缺口全解本就无解，只需确认不抛异常且返回结构正常
    try:
        r5 = G.solve_edge_gap(c, M, N, STEP, hole=HOLE, anchor=BUMP,
                              require_solved=True)
        check('P5 require_solved=True 路径不抛异常',
              isinstance(r5, tuple) and len(r5) == 2)
    except Exception as e:
        check('P5 require_solved=True 路径不抛异常', False, repr(e)[:80])

    print('\n=== %s ===' % ('ALL PASS' if not FAILS else 'FAILED: %s' % FAILS))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(run())
