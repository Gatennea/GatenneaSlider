# -*- coding: utf-8 -*-
r"""couple 分派接粘上接走（band_shift）兜底护栏 — 存档 step120 盘面。

来源：save/2-8-8-20261111-220716waiting_optimize.json 第 120 步（盘面已内嵌，
不依赖存档文件）。该盘面聚拢度 62/64，两洞 (6,0)[D 边] 与 (-1,-1)[U 边]、
窗外凸起 (-2,-2) 与 (7,3)。

背景：粘上接走（band_shift）原语（#50）早在 solve_single_void 内部就接上了，所以 GUI 贪心
路径（solve_multi_vacancy → solve_multi_void，不带 couple_hook）本就能靠它
推到 63。但另一条分派路径——_vacancy_couple_hook（DFS 搜索 / 并行 worker
用它）——的 edge 分支此前只试「补缺链 → D4 轨道」，长共轭硬洞（直接推不进、
须先让路再捎带）在 couple 模式下一律 None，粘上接走（band_shift）兜底从未被调到。

本护栏锁死「edge 分支的粘上接走（band_shift）兜底确实接到了 hook」：
  P0 哨兵：monkeypatch _edge_band_shift_attempt 返回哨兵 → hook 必回哨兵，
      证明兜底分支已接入（有人删掉这行兜底，hook 退回 None，测试转红）。
  P1 正控：放大预算让粘上接走（band_shift）在慢机也能解 step120 → hook 对 (6,0)/(-2,-2)
      这对该回传合法动作且重放后 (6,0) 被填上（62→63，与手解同构）。

反向验证口径：P0 直接盯「被绕开的粘上接走（band_shift）有没有被调用」（比静态判据可靠）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from solver.ml import gap_solver as gs  # noqa: E402
import solver.ml.fill_macro as fm  # noqa: E402

M, N, STEP = 8, 8, 2
HOLE = (6, 0)
BUMP = (-2, -2)

# 存档 step120 的完整盘面（64 块，含 2 个窗外凸起）
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

FAILS = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('  %s' % detail if detail else ''))
    if not ok:
        FAILS.append(name)
    return ok


def _hook():
    return gs._vacancy_couple_hook(False)


def run():
    ov0 = fm.window_of(COORDS, M, N, STEP)[1]
    check('P0 盘面 64 块 / 段首聚拢 62',
          len(COORDS) == M * N and ov0 == 62,
          '块=%d ov=%d' % (len(COORDS), ov0))

    # P0 哨兵：把 _edge_band_shift_attempt 换成哨兵，hook 必须回传哨兵
    # —— 证明 edge 分支的粘上接走（band_shift）兜底分支当前是「活」的（有人删掉这行兜底，
    # hook 退回 None，测试转红）。
    orig = gs._edge_band_shift_attempt

    def _sentinel(*a, **k):
        return ('__BS_SENTINEL__', {'route': 'sentinel'})

    gs._edge_band_shift_attempt = _sentinel
    try:
        acts_s, _ = _hook()(COORDS, M, N, STEP, HOLE, BUMP)
    finally:
        gs._edge_band_shift_attempt = orig
    check('P0b 粘上接走（band_shift）兜底已接入 hook（哨兵被回传）',
          acts_s == '__BS_SENTINEL__',
          'acts=%r' % (acts_s,))

    # P1 正控：放大预算，slow 机也能让粘上接走（band_shift）跑出 step120 长共轭。
    # 只验证「分派层能真把长共轭喂出来并填洞」，不验证生产侧延迟预算。
    saved = gs._BAND_SHIFT_BUDGET
    gs._BAND_SHIFT_BUDGET = 40.0
    try:
        acts, st = _hook()(COORDS, M, N, STEP, HOLE, BUMP)
    finally:
        gs._BAND_SHIFT_BUDGET = saved
    ok = acts is not None
    g = fm.build_game(COORDS, M, N)
    replay_ok = fm._replay_apply(g, acts, M, N, STEP) if ok else False
    filled = (tuple(HOLE) in fm.gcoords(g)) if replay_ok else False
    detail = ''
    if ok:
        end_ov = fm.window_of(frozenset(fm.gcoords(g)), M, N, STEP)[1]
        detail = '步数=%d 重放=%s 洞填=%s end_ov=%s' % (
            len(acts), replay_ok, filled, end_ov)
    check('P1 hook 经粘上接走（band_shift）兜底解出 (6,0) 且重放填洞',
          ok and replay_ok and filled, detail)

    if FAILS:
        print('\n[FAILED] %d 项: %s' % (len(FAILS), ', '.join(FAILS)))
        sys.exit(1)
    print('\n[ALL PASS]')


if __name__ == '__main__':
    run()
