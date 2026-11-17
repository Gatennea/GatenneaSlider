# -*- coding: utf-8 -*-
"""粘连双凸起拆分整形护栏（2026-11-17，用户存档 2-6-6-20261117 stuck@76）。

用户卡点：第 76 快照是求解器卡住处——目标窗口外恰好两个凸起粘连
（(-1,3) 与 (-1,4) 相邻），每个 couple 的 setup/推进都被粘着的那个挡住，
贴边 setup / 粘上接走（band_shift 最多 1123 组）四条路全败，修复前
fill_fail 15.6s 零推进。用户实测三步「借位-挪块-归位」拆开两凸起
（窗内聚拢度 34→26→34 先降后升）后一切照常。

修复 = 新整形原语 `_split_stuck_outside`（fill_macro.py）：BFS 终点判据 =
两标记块距 ≥2 **且聚拢复原**，中间允许借位降（floor = ov0-(m+n)），挂载在
solve_multi_void 的 couple+整形预演全败、停机之前。修复后本局 21 步
2.8s 自动全解（原 15.6s 零步）。

判据（局面内嵌，不依赖 save/ 文件）：
  S1 端到端：solve_multi_vacancy(76 局面) 解出，手工回放还原；
  S2 原语直调：返回 ≤5 步动作链，回放后聚拢度复原（≥34）；
  S3 边界：拆分后的态再调原语返回 None（不粘连/边界外不触发，防循环烧算）。

执行：D:/python/python.exe test/_test_split_stuck_outside.py
"""
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from solver.ml.fill_macro import (build_game, gcoords,    # noqa: E402
                                  window_of, _split_stuck_outside)
from solver.ml.gap_solver import solve_multi_vacancy      # noqa: E402

M, N, STEP = 6, 6, 2
# 快照 76 局面（存档 save/2-6-6-20261117-122425stuck.json，不入库故内嵌）：
# 行 -1 只有列 3/4 两个粘连凸起；行 3 列 2、行 5 列 5 两个洞；36 块。
COORDS76 = frozenset(
    [(-1, 3), (-1, 4)]
    + [(0, c) for c in range(6)]
    + [(1, c) for c in range(6)]
    + [(2, c) for c in range(6)]
    + [(3, c) for c in range(6) if c != 2]
    + [(4, c) for c in range(6)]
    + [(5, c) for c in range(6) if c != 5]
)

_failures = []


def check(name, cond, extra=''):
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, extra))
    if not cond:
        _failures.append(name)


def replay(sx, acts):
    """手工回放 5 元组动作链（按 rep 定位代表格）。"""
    g = build_game(sx, M, N)
    for a in acts:
        rep = a[4] if len(a) > 4 else None
        blk = next((b for b in g.blocks
                    if tuple(b.location) == tuple(rep)), None) if rep else None
        if blk is None:
            return None
        g.opt(a[0], a[1], blk)
        fin = g.try_move(a[3], STEP)
        if not fin:
            return None
        g.commit_move(fin)
    return gcoords(g)


def main():
    check('S0 局面自检：36 块 + 窗外恰 2 凸起且相邻',
          len(COORDS76) == 36
          and (lambda o: len(o) == 2
               and sum(abs(p[0] - q[0]) + abs(p[1] - q[1])
                       for p, q in [sorted(o)]) == 1)(
              window_of(COORDS76, M, N, STEP)[3]),
          str(sorted(window_of(COORDS76, M, N, STEP)[3])))

    # ---- S2 原语直调：拆开且聚拢复原 ----
    ov0 = window_of(COORDS76, M, N, STEP)[1]
    t0 = time.time()
    plan = _split_stuck_outside(COORDS76, M, N, STEP)
    dt_split = time.time() - t0
    check('S2a 原语返回动作链（≤5 步）', plan is not None and 1 <= len(plan) <= 5,
          'plan=%s' % (None if plan is None else '%d 步' % len(plan)))
    if plan is not None:
        s2 = replay(COORDS76, plan)
        check('S2b 拆分链回放合法', s2 is not None)
        if s2 is not None:
            check('S2c 回放后聚拢复原（≥%d）' % ov0,
                  window_of(s2, M, N, STEP)[1] >= ov0,
                  'ov=%d' % window_of(s2, M, N, STEP)[1])
            # ---- S3 边界：拆开后不再触发 ----
            check('S3 拆开后原语返回 None（不触发防循环）',
                  _split_stuck_outside(s2, M, N, STEP) is None)

    # ---- S1 端到端：从 76 自动解整个谜题 ----
    t0 = time.time()
    stop_at = time.time() + 90.0
    try:
        acts, stats = solve_multi_vacancy(
            COORDS76, M, N, STEP, mode='auto',
            rng=random.Random(20261117),
            cancel_check=lambda: time.time() > stop_at)
    except Exception as e:
        acts, stats = None, {'error': '%s: %s' % (type(e).__name__, e)}
    dt = time.time() - t0
    check('S1a 端到端返回动作链', acts is not None and len(acts) > 0,
          'acts=%s stats=%s' % (None if acts is None else len(acts),
                                stats.get('error') or stats.get('reason', '')))
    if acts:
        s_end = replay(COORDS76, acts)
        check('S1b 手工回放还原整个谜题', s_end is not None
              and build_game(s_end, M, N).is_solved(),
              'dt=%.1fs' % dt)
        check('S1c 耗时有界（< 60s，修复前 15.6s 零步失败）', dt < 60.0,
              '%.1fs 原语段=%.2fs' % (dt, dt_split))

    print('==== %s（%d 项失败）'
          % ('全部通过' if not _failures else '有失败', len(_failures)))
    return 1 if _failures else 0


if __name__ == '__main__':
    sys.exit(main())
