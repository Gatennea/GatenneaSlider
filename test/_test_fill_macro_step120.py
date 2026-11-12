"""「填洞宏」按钮从存档 step120 起必须能全解（回归护栏）。

历史回归（2026-11-12）：`solve_fill_macro` 多洞分支调 `solve_multi_void` 时
没传 `couple_hook`，于是每条 couple 只用 `solve_single_void`。对边/角洞的
couple，`solve_edge_gap(couple=True)` 提前返回失败，只能退到 band_shift 兜底；
而 step120 的两个洞里，(-1,-1)←(7,3) 这对 band_shift 兜底解不出，需要
`couple_hook` 里的 `solve_edge_gap`/`_couple_orbit_solve` 招。结果：填掉一个洞
后停在「不完美洞」`fill_partial`，只剩 1 洞没填——用户侧表现为「多空位驱动后
填洞宏流水中断」。

修复：`solve_fill_macro` 的 `solve_multi_void` / `solve_multi_search` 都补上
`couple_hook=_vacancy_couple_hook(gap_only=False)`，与 `solve_gap_macro`（补缺宏）
/ `auto_solve`（自动求解）共用同一套原语。

本护栏锁死：默认 30s 墙钟预算内，`solve_fill_macro` 必须把 step120 全解到
ov=64（26 步），不能停在 partial。
"""
import os
import sys
import time

sys.path.insert(0, os.getcwd())
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from solver.ml.fill_macro import (build_game, gcoords, window_of,
                                  _replay_apply, solve_fill_macro,
                                  _FILL_GUI_TIME_BUDGET)
import solver.ml.gap_solver as gs

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

    # P1 哨兵：couple_hook 必须被传给 solve_multi_void（修复核心）
    hook_used = [0]
    _orig = gs._vacancy_couple_hook
    def _spy(gap_only, cancel_check=None):
        hook_used[0] += 1
        return _orig(gap_only=gap_only, cancel_check=cancel_check)
    gs._vacancy_couple_hook = _spy
    try:
        g = build_game(COORDS, M, N)
        t = time.time()
        res = solve_fill_macro(g, STEP, time_budget=_FILL_GUI_TIME_BUDGET)
        dt = time.time() - t
    finally:
        gs._vacancy_couple_hook = _orig

    check('P1 默认预算内解出（非 partial 停机）',
          isinstance(res, tuple),
          'type=%s dt=%.1fs' % (type(res).__name__, dt))
    check('P1b couple_hook 确实被传入 solve_multi_void',
          hook_used[0] >= 1, 'hook_used=%d' % hook_used[0])
    if not isinstance(res, tuple):
        print('  （partial/fail 原因：%s）'
              % (res.get('reason') if isinstance(res, dict) else res))
        print('\nFAILED:', _fails)
        return 1

    acts = res[0]
    reps = res[1]
    acts5 = [a + ((reps[i] if reps[i] is not None else None),)
             for i, a in enumerate(acts)]
    # P2 全解到 64
    g2 = build_game(COORDS, M, N)
    ok = _replay_apply(g2, acts5, M, N, STEP)
    ov1 = window_of(frozenset(gcoords(g2)), M, N, STEP)[1]
    check('P2 重放合法且全解 ov=64', ok and ov1 == M * N,
          'replay_ok=%s end_ov=%s nsteps=%d' % (ok, ov1, len(acts)))

    # P3 预算余量：30s 墙钟内完成（锁「流水中断」回归）
    check('P3 在默认 %ds 预算内完成' % int(_FILL_GUI_TIME_BUDGET),
          dt < _FILL_GUI_TIME_BUDGET, 'dt=%.1fs' % dt)

    if _fails:
        print('\nFAILED:', _fails)
        return 1
    print('\nALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
