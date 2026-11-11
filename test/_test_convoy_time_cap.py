# -*- coding: utf-8 -*-
r"""convoy（粘上接走）墙钟上限 + 8×8 残局失败耗时回归锁。

起因（2026-11-11 用户报，存档 waiting_optimize 第 109/120 步）：
「填洞补缺」在这些近解残局上停机，且耗时 17~26 秒。排查结论——

  · 这些残局（8×8，剩 2~3 个洞 + 同数窗外凸起）**不存在单调聚拢解**：
    对 state[109] 做「覆盖数不降」的穷尽 BFS 只到 390 个状态、最高覆盖
    数仍是 61（需 62 才能起步），证明任何解都必须先降聚拢再复原（揉形）；
  · 所有现有原语都解不动：边缺口链/single-void 会把整盘甩出窗（覆盖数
    61→25~43，闸门正确拒绝）、加预算到 20000 节点 convoy 仍全败；
  · 十几二十秒几乎全部耗在 `_reshape_edges` 里对每个 (洞,凸起) 调
    `_convoy_fill(max_nodes=2500)`——它只有节点上限、**没有墙钟上限**，
    大盘上多次调用即 17~26 秒。

修法：`_convoy_fill` 新增可选 `time_cap`（默认 None = 行为不变）；
`_reshape_edges` 对 m*n≥40 的大棋盘传 0.2s 上限，把无望的暴力搜索截断，
整体失败耗时压回 2~3 秒。小盘（≤6×6）不设限，保住 convoy 主场。

本测试锁：
  P1 `_convoy_fill` 接受 time_cap 且到点提前收（用节点数远小于上限证明）；
  P2 给 time_cap 后单次调用 < 2.5s（远小于无上限的 ~22s）；
  P3 完整 `solve_gap_macro` 在该残局上返回 fill_fail 且总耗时 < 8s
     （抓住「又变回十几二十秒」的回归）；
  P4 `time_cap=None`（老调用）仍能正常返回（不抛错）。

跑法：``D:/python/python.exe -u test/_test_convoy_time_cap.py``
"""

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from solver.ml.fill_macro import _convoy_fill, build_game  # noqa: E402
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
    res = solve_gap_macro(g, STEP, time_budget=90.0)
    dt = time.time() - t
    ok_type = isinstance(res, dict) and res.get('type') in (
        'fill_fail', 'fill_partial')
    check('P3 残局返回 fill_fail/fill_partial 且 < 8s', ok_type and dt < 8.0,
          'type=%s %.2fs' % (res.get('type') if isinstance(res, dict) else '?',
                             dt))


if __name__ == '__main__':
    test_convoy_time_cap()
    test_convoy_default_no_cap()
    test_gap_macro_bounded_time()
    print('\n' + ('ALL PASS' if not _FAILURES
                  else 'FAILED: %d' % len(_FAILURES)))
    sys.exit(0 if not _FAILURES else 1)
