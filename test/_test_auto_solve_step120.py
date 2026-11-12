"""「自动求解」按钮入口（auto_solve）从存档 step120 起必须能全解（回归护栏）。

历史回归（2026-11-12）：仅修了 `solve_fill_macro`（填洞宏按钮）入口的
`couple_hook`，但游戏主菜单「自动求解」走的是另一条入口 `auto_solve`。
step120 有 2 个洞，默认路由是「混合流水线先跑、补缺宏（couple_hook）兜底」，
与填洞宏按钮走的分派链不同。本护栏锁死这条入口：默认整轮预算内，
`auto_solve` 必须把 step120 全解到 ov=64，不能停在 partial/fail。

这是 `test/_test_fill_macro_step120.py`（填洞宏按钮入口）的姊妹护栏——
改求解器必须两入口都验（项目铁律）。
"""
import os
import sys
import time

sys.path.insert(0, os.getcwd())
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from solver.ml.fill_macro import (build_game, gcoords, window_of,
                                  _replay_apply)
from solver.auto_solver import auto_solve

M, N, STEP = 8, 8, 2

# step120 盘面：64 块 / ov=62 / 两洞 (-1,-1) 与 (6,0) / 窗外凸 (-2,-2) 与 (7,3)
COORDS = frozenset([
    (-2, -2),
    (-1, -3), (-1, -2), (-1, 0), (-1, 1), (-1, 2), (-1, 3), (-1, 4),
    (0, -3), (0, -2), (0, -1), (0, 0), (0, 1), (0, 2), (0, 3), (0, 4),
    (1, -3), (1, -2), (1, -1), (1, 0), (1, 1), (1, 2), (1, 3), (1, 4),
    (2, -3), (2, -2), (2, -1), (2, 0), (2, 1), (2, 2), (2, 3), (2, 4),
    (3, -3), (3, -2), (3, -1), (3, 0), (3, 1), (3, 2), (3, 3), (3, 4),
    (4, -3), (4, -2), (4, -1), (4, 0), (4, 1), (4, 2), (4, 3), (4, 4),
    (5, -3), (5, -2), (5, -1), (5, 0), (5, 1), (5, 2), (5, 3), (5, 4),
    (6, -3), (6, -2), (6, -1), (6, 1), (6, 2), (6, 3), (6, 4),
    (7, 3),
])

_fails = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('' if not detail else '  ' + detail))
    if not ok:
        _fails.append(name)


def main():
    # P0 盘面锁：64 块 / ov=62
    (r0, c0, wh), ov0, holes, out = window_of(COORDS, M, N, STEP)
    check('P0 盘面锁：64 块 / ov=62 / 两洞两凸',
          len(COORDS) == 64 and ov0 == 62
          and len(holes) == 2 and len(out) == 2,
          'n=%d ov=%d holes=%s out=%s' % (len(COORDS), ov0, holes, out))

    # P1 auto_solve（自动求解按钮）入口，非流式，整轮预算 150s
    g = build_game(COORDS, M, N)
    segs = []
    t = time.time()
    # 模拟 GUI 真实入口：gui/auto_solve.py 调 auto_solve 时传 stage_cb 走流式分段。
    res = auto_solve(g, STEP, time_budget=150, stage_cb=lambda s: segs.append(s))
    dt = time.time() - t

    if isinstance(res, tuple):
        check('P1 默认整轮预算内全解（tuple 返回）', True,
              'dt=%.1fs' % dt)
    else:
        check('P1 默认整轮预算内全解（tuple 返回）', False,
              'type=%s %s' % (type(res).__name__,
                              res.get('reason') if isinstance(res, dict) else res))
        print('\nFAILED:', _fails)
        return 1

    acts4, reps = res
    five = []
    for i, a in enumerate(acts4):
        rp = reps[i] if i < len(reps) and reps[i] else None
        # 代表格统一成 tuple：_capture_apply 按 tuple 精确比对块位置，
        # auto_solve 的 BulkStaticRewriter 可能产出 list 形式的 rep。
        rp = tuple(rp) if rp else None
        five.append((a[0], a[1], a[2], a[3], rp))

    # P2 重放合法且全解 ov=64
    g2 = build_game(COORDS, M, N)
    ok = _replay_apply(g2, five, M, N, STEP)
    ov1 = window_of(frozenset(gcoords(g2)), M, N, STEP)[1]
    check('P2 重放合法且全解 ov=64', ok and ov1 == M * N,
          'replay_ok=%s end_ov=%s nsteps=%d' % (ok, ov1, len(acts4)))

    # P3 整轮预算余量
    check('P3 在 150s 整轮预算内完成', dt < 150, 'dt=%.1fs' % dt)

    if _fails:
        print('\nFAILED:', _fails)
        return 1
    print('\nALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
