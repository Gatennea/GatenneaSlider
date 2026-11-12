"""护栏：step120 走「填洞补缺」(gap_macro) 的盘面重建次数必须远低于「每候选建一局」。

背景（2026-11-12 提速）：这条路径原先每解一次 step120 要 build_game 约 9.7 万次
（每次还先建 m*n 个块再丢掉、再跑两遍 update_matrix），实测 11~19 秒。
真正的原因不是「粘上接走」算法复杂，而是搜索内层**每个候选都重建一整盘**：
`_relay_1d` 模式B 对每个候选块各建一份盘面，只为判它属于哪个连通分量。

修复后 build_game 降到万级、耗时降到 4 秒上下（快机 2.5s）。本护栏用
**确定性判据（调用计数）**锁住这一点，不用墙钟阈值——慢机上墙钟会飘，
但「为了判连通把整盘建一遍」这件事一旦被改回来，计数立刻暴涨。

判据：
  P1 求解成功（tuple 返回＝全解）
  P2 重放合法且终盘 ov=64（提速不得改变结果）
  P3 单次求解的 build_game 次数 < 45000（提速前 ~97000，之后 1.2~2.1 万）
  P4 每次建盘的 Block 构造数是「块数级」而非「块数+整张 m*n 网格」
     （旧写法的 build_game 先 SliderMatrix(m,n) 建满 m*n 个块再替换，
      还跑两遍 update_matrix）
  P5 挂死保护：单次墙钟 < 120s
"""
import os
import sys
import time
import importlib.util

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from engine import config as _ecfg  # noqa: E402
_ecfg.set_enabled(False)

_spec = importlib.util.spec_from_file_location(
    't120', os.path.join(_PROJ, 'test', '_test_gap_macro_step120.py'))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
COORDS = _mod.COORDS

import game as _game                                     # noqa: E402
import solver.ml.fill_macro as fm                       # noqa: E402
from solver.ml.fill_macro import gcoords, window_of, _replay_apply  # noqa: E402,E501
from solver.ml.gap_solver import solve_gap_macro       # noqa: E402

M, N, STEP = 8, 8, 2
BUILD_LIMIT = 45000
WALL_LIMIT = 120.0
BLOCKS_PER_BUILD_LIMIT = len(COORDS) + 10    # 旧写法是 len(COORDS) + m*n

_fails = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('' if not detail else '  ' + detail))
    if not ok:
        _fails.append(name)


def solve_counted(budget=30.0):
    """跑一次 gap_macro，统计期间 build_game 调用次数、Block 构造数与墙钟。"""
    counter = {'build': 0, 'block': 0}
    real_build = fm.build_game
    real_block = _game.Block

    class CountingBlock(real_block):
        def __init__(self, location, be_opted=False):
            counter['block'] += 1
            real_block.__init__(self, location, be_opted)

    def counted(coords, m, n):
        counter['build'] += 1
        return real_build(coords, m, n)

    g = real_build(COORDS, M, N)             # 首局不计入搜索开销
    fm.build_game = counted
    _game.Block = CountingBlock
    try:
        segs = []
        t0 = time.time()
        res = solve_gap_macro(
            g, STEP,
            segment_cb=lambda l, a: segs.append((l, [tuple(x) for x in a])),
            time_budget=budget)
        dt = time.time() - t0
    finally:
        fm.build_game = real_build
        _game.Block = real_block
    solved = isinstance(res, tuple) or bool(
        res.get('solved') if isinstance(res, dict) else False)
    return solved, res, segs, counter['build'], counter['block'], dt


def five_of(res, segs):
    """→ 5 元组动作链 (gap,line,side,d,rep)；优先取 tuple 返回的 reps。"""
    if isinstance(res, tuple):
        acts4, reps = res
        out = []
        for i, a in enumerate(acts4):
            rp = reps[i] if i < len(reps) and reps[i] else None
            out.append((a[0], a[1], a[2], a[3], tuple(rp) if rp else None))
        return out
    return [a for _, seg in segs for a in seg]


def main():
    (r0, c0, wh), ov0, holes, out = window_of(COORDS, M, N, STEP)
    check('P0 盘面锁：64 块 / ov=62 / 两洞两凸',
          len(COORDS) == 64 and ov0 == 62
          and len(holes) == 2 and len(out) == 2,
          'n=%d ov=%d holes=%d out=%d' % (len(COORDS), ov0,
                                          len(holes), len(out)))

    # 多洞贪心带随机性、偶发 partial：取第一次成功的尝试作计数口径
    best = None
    for _ in range(5):
        solved, res, segs, nbuild, nblock, dt = solve_counted()
        if solved:
            best = (res, segs, nbuild, nblock, dt)
            break
    check('P1 求解成功', best is not None, '')
    if best is None:
        print('\nFAILED:', _fails)
        return 1
    res, segs, nbuild, nblock, dt = best
    five = five_of(res, segs)

    g2 = fm.build_game(COORDS, M, N)
    ok = _replay_apply(g2, five, M, N, STEP)
    ov = window_of(frozenset(gcoords(g2)), M, N, STEP)[1]
    check('P2 重放合法且终盘 ov=64', ok and ov == M * N,
          'replay_ok=%s end_ov=%d ops=%d' % (ok, ov, len(five)))
    check('P3 build_game 次数 < %d（每候选重建整盘会到 ~97000）'
          % BUILD_LIMIT, nbuild < BUILD_LIMIT, 'builds=%d' % nbuild)
    if nbuild:
        per = nblock / float(nbuild)
        check('P4 每次建盘的 Block 构造数 < %d（应 ≈ 块数 %d；旧写法还会多建 '
              '满盘 %d 个再丢掉）' % (BLOCKS_PER_BUILD_LIMIT, len(COORDS), M * N),
              per < BLOCKS_PER_BUILD_LIMIT,
              'blocks=%d builds=%d per_build=%.1f'
              % (nblock, nbuild, per))
    check('P5 墙钟 < %.0fs（挂死保护）' % WALL_LIMIT, dt < WALL_LIMIT,
          'wall=%.2fs' % dt)
    print('       （builds=%d blocks=%d wall=%.2fs ops=%d —— 提速前 ~97000 次 / '
          '11~19s）' % (nbuild, nblock, dt, len(five)))

    if _fails:
        print('\nFAILED:', _fails)
        return 1
    print('\nALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
