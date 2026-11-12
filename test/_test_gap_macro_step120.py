"""「填洞补缺」按钮（gap_macro → solve_gap_macro）从 step120 起必须能全解。

这是 GUI 真实入口的护栏：游戏菜单「填洞补缺」在 file_ops 里映射为 gap_macro，
SOLVER_ALGORITHMS['gap_macro'] = solve_gap_macro；GUI（gui/auto_solve.py:204-231）
会传 segment_cb（流式）和用户设置的 max_wait_time（config 当前 = 20s）。

⚠️ 这条路径与 solve_fill_macro / auto_solve 都不同：
  - step120 有 2 洞 → solve_gap_macro 走 solve_multi_vacancy(mode='auto')，
    不是 solve_fill_macro，也不是 auto_solve 的 hybrid 路由。
历史教训：前两轮护栏只测 solve_fill_macro / auto_solve，全是旁支，用户点
「填洞补缺」仍中断——必须直接测这条真实路径。
"""
import os
import sys
import time

sys.path.insert(0, os.getcwd())
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from solver.ml.fill_macro import build_game, gcoords, window_of, _replay_apply
from solver.ml.gap_solver import solve_gap_macro

M, N, STEP = 8, 8, 2
GUI_BUDGET = 20.0   # config/config.json: max_wait_time=20（GUI 实际传入值）

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
    (r0, c0, wh), ov0, holes, out = window_of(COORDS, M, N, STEP)
    check('P0 盘面锁：64 块 / ov=62 / 两洞两凸',
          len(COORDS) == 64 and ov0 == 62
          and len(holes) == 2 and len(out) == 2,
          'n=%d ov=%d holes=%s out=%s' % (len(COORDS), ov0, holes, out))

    segs = []

    def seg_cb(label, acts5):
        segs.append((label, [tuple(a) for a in acts5]))

    g = build_game(COORDS, M, N)
    t = time.time()
    res = solve_gap_macro(g, STEP, segment_cb=seg_cb, time_budget=GUI_BUDGET)
    dt = time.time() - t

    # ⚠️ 返回协议有两条，两条都代表「全解」，不能只认 tuple：
    #   - 带 segment_cb 流式全解 → dict{'solved': True, 'streamed': N}
    #   - 非流式全解 → (acts4, reps) 元组
    # 曾经这里只判 isinstance(res, tuple)，把「流式全解」误判成失败
    # （2026-11-12 实测 12/12 都是 dict+solved=True，护栏却 6/6 报红）。
    if isinstance(res, tuple):
        solved, reason = True, None
        acts4, reps = res
        five = []
        for i, a in enumerate(acts4):
            rp = reps[i] if i < len(reps) and reps[i] else None
            rp = tuple(rp) if rp else None
            five.append((a[0], a[1], a[2], a[3], rp))
    else:
        solved = bool(res.get('solved'))
        reason = res.get('reason')
        five = [a for _, seg in segs for a in seg]
    check('P1 GUI 预算 %gs 内全解' % GUI_BUDGET, solved,
          'type=%s solved=%s reason=%s dt=%.1fs segs=%d steps=%d'
          % (type(res).__name__, solved, reason, dt, len(segs), len(five)))
    if not solved:
        print('\nFAILED:', _fails)
        return 1

    g2 = build_game(COORDS, M, N)
    ok = _replay_apply(g2, five, M, N, STEP)
    ov1 = window_of(frozenset(gcoords(g2)), M, N, STEP)[1]
    check('P2 重放合法且全解 ov=64', ok and ov1 == M * N,
          'replay_ok=%s end_ov=%s nsteps=%d' % (ok, ov1, len(five)))

    if _fails:
        print('\nFAILED:', _fails)
        return 1
    print('\nALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
