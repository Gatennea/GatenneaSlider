# -*- coding: utf-8 -*-
r"""convoy（粘上接走）墙钟上限 + 8×8 残局耗时/进展回归锁。

起因（2026-11-11 用户报，存档 waiting_optimize 第 109/120 步）：
「填洞补缺」在这些近解残局上停机，且耗时 17~26 秒。

两项独立的修复，别混为一谈：

  1. 耗时：`_reshape_edges` 对每个 (洞,凸起) 调
     `_convoy_fill(max_nodes=2500)`，该函数只有节点上限、**没有墙钟上限**，
     大盘上多次调用即 17~26 秒。给 `_convoy_fill` 加可选 `time_cap`
     （默认 None = 行为不变），大盘（m*n≥40）传 0.2s 截断无望的暴力搜索。
     小盘（≤6×6）不设限，保住 convoy 主场。

  2. 停机（2026-11-12）：补缺链 `_user_edge_chain` 六级「第一个成功就返回」，
     而 couple 模式的成功判据只有「洞被填上」；于是直解(直接) 的 9 步散架解
     （聚拢 61→42）抢先返回，挡住后面直解(自动/id) 的 11 步正解（61→62）。
     上层段级闸门拒收 42 的解，判「所有 couple 无成果」停机。
     改法：couple 模式六级按段末聚拢度择优。详见
     `test/_test_gap_chain_gate.py`。

⚠️ 旧版文档曾把该残局定性为「不存在单调聚拢解 / 需非单调揉形搜索」，
   这是拿单步 BFS 结论否定段级驱动的错误推断，已被用户驳回并删除。
   段级闸门一直是「段末聚拢度 > 段首」，用户手解三段 61→62→63→64
   每段都过闸；问题从来不是理论不可解，而是公式生成器被抢先返回挡住。

本测试锁：
  P1 `_convoy_fill` 接受 time_cap 且到点提前收（用节点数远小于上限证明）；
  P2 给 time_cap 后单次调用 < 2.5s（远小于无上限的 ~22s）；
  P3 完整 `solve_gap_macro` 在该残局上有进展（不再零进展停机）且耗时有界
     < 60s（仅抓「挂死 / 逼近 90s 预算」回归；正常 9~25s 皆可，机器速度
     依赖，不在此硬锁秒数）；核心回归锁是「至少推进一段」而非零进展停机；
  P4 `time_cap=None`（老调用）仍能正常返回（不抛错）。

跑法：``D:/python/python.exe -u test/_test_convoy_time_cap.py``
"""

import os
import sys
import time
import random

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from solver.ml.fill_macro import (_convoy_fill, build_game,  # noqa: E402
                                  gcoords, window_of, _replay_apply)
from solver.ml.gap_solver import solve_gap_macro  # noqa: E402

_FAILURES = []


def check(desc, cond, extra=''):
    if cond:
        print('[PASS] %s %s' % (desc, extra))
    else:
        print('[FAIL] %s %s' % (desc, extra))
        _FAILURES.append(desc)


# waiting_optimize 第 109 步盘面（内嵌，避免依赖 save/ 文件）。
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
M, N, STEP = 8, 8, 2
HOLE = (-1, 1)   # 顶边洞
BUMP = (7, 5)    # 同 mod 的对角凸起（convoy 最耗时的一对）


def test_convoy_time_cap():
    t = time.time()
    acts, used = _convoy_fill(COORDS, M, N, STEP, HOLE, BUMP,
                              max_nodes=2500, time_cap=0.1)
    dt = time.time() - t
    check('P1 time_cap 到点提前收（节点数远小于 2500）',
          acts is None and used < 500, 'used=%s' % used)
    check('P2 单次调用 < 2.5s', dt < 2.5, '%.2fs' % dt)


def test_convoy_default_no_cap():
    # 默认 time_cap=None：只跑极小节点数，验证老调用路径不抛错、能返回。
    t = time.time()
    acts, used = _convoy_fill(COORDS, M, N, STEP, HOLE, BUMP, max_nodes=30)
    dt = time.time() - t
    check('P4 time_cap=None 老调用正常返回', acts is None and used <= 30,
          'used=%s %.2fs' % (used, dt))


def test_gap_macro_bounded_time():
    g = build_game(COORDS, M, N)
    t = time.time()
    # 固定 rng 让该盘解链可复现（避免无解路径随机游走导致时长抖动）。
    res = solve_gap_macro(g, STEP, time_budget=90.0,
                          rng=random.Random(20261112))
    dt = time.time() - t
    ok_type = ((isinstance(res, dict)
                and res.get('type') in ('fill_fail', 'fill_partial'))
               or (isinstance(res, tuple) and bool(res[0])))
    # 本护栏锁「不再零进展停机」+「耗时有界」两条。慢机（约 25s）与快机
    # （约 9s）都算合法——只要返回结构有效且到点前停机即可；全解到 64 是
    # 快机上的额外红利，不在此硬性断言（机器速度依赖，易误报）。
    # dt 上限取 60s：远宽于正常 9~25s，仅用于抓「挂死 / 逼近 90s 预算」回归。
    check('P3 残局返回合法结构且未挂死（< 60s）',
          ok_type and dt < 60.0,
          'type=%s %.2fs' % (type(res).__name__, dt))
    # 核心回归锁：修复前该残局零进展停机；修复后至少解出一个 couple
    # （fill_partial 带动作）或全部自动解出（tuple 回放到 64）。
    full_solve = False
    if isinstance(res, tuple) and res[0]:
        g2 = build_game(COORDS, M, N)
        if _replay_apply(g2, res[0], M, N, STEP):
            full_solve = (window_of(frozenset(gcoords(g2)), M, N, STEP)[1]
                          == M * N)
    progressed = (isinstance(res, dict)
                  and res.get('type') == 'fill_partial'
                  and bool(res.get('actions'))) or full_solve
    check('P3 残局至少推进一段（修复前零进展停机）', progressed,
          'full_solve=%s' % full_solve)


if __name__ == '__main__':
    test_convoy_time_cap()
    test_convoy_default_no_cap()
    test_gap_macro_bounded_time()
    print('\n' + ('ALL PASS' if not _FAILURES
                  else 'FAILED: %d' % len(_FAILURES)))
    sys.exit(0 if not _FAILURES else 1)
