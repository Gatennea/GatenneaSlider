"""护栏：`_sel_move`（融合的「选片+平移」原语）与引擎原路径逐项等价。

背景：提速时把求解内层高频操作 `opt + try_move` 合成了一个只建一次占用
掩码的 `_sel_move`（原路径 step=2 时要建 3 次掩码，实测占 step120 求解
墙钟四成以上）。这类「重写热原语」的改动最怕语义漂移——一旦选中片、
碰撞判定或连通判定与引擎有差，求解器会算出游戏里播不动的动作，而
solver 级回放（用 rep 定位）永远测不出来。

判据：同一盘面、同一缝/方向/代表块，引擎原路径与新原语必须给出
① 相同的成败、② 相同的最终位置集合、③ 相同的选中片。
随机盘面 + 随机缝/方向/代表块，固定种子保证可复现。
"""
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import _sel_move, build_game   # noqa: E402

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print('[FAIL] %s' % msg)


def _find_block(g, pos):
    for b in g.blocks:
        if tuple(b.location) == pos:
            return b
    return None


def _engine(g, gap, line, blk, d, step):
    g.opt(gap, line, blk)
    fin = g.try_move(d, step)
    return bool(fin), fin


def _boards(rng, m, n):
    """几种典型盘面：满盘 / 缺 1~3 格 / 带成片缺口。"""
    full = {(r, c) for r in range(m) for c in range(n)}
    out = [frozenset(full)]
    for holes in (1, 2, 3):
        cells = set(full)
        for _ in range(holes):
            cells.discard(rng.choice(sorted(cells)))
        out.append(frozenset(cells))
    if m >= 4 and n >= 4:
        cut = {(r, c) for r in range(m) for c in range(n)
               if not (1 <= r <= 2 and 1 <= c <= 2)}
        out.append(frozenset(cut))
    return out


def main():
    rng = random.Random(20261112)
    cases = 0
    for m, n in ((4, 4), (5, 5), (6, 6), (8, 8)):
        for step in (1, 2):
            for cells in _boards(rng, m, n):
                reps = sorted(cells)[:8]
                for gap in ('h', 'v'):
                    for line in range(-1, max(m, n) + 1):
                        for d in ('w', 's', 'a', 'd'):
                            for rep in reps:
                                g1 = build_game(cells, m, n)
                                g2 = build_game(cells, m, n)
                                b1 = _find_block(g1, rep)
                                b2 = _find_block(g2, rep)
                                if b1 is None or b2 is None:
                                    continue
                                ok1, fin1 = _engine(g1, gap, line, b1, d, step)
                                ok2, fin2 = _sel_move(g2, gap, line, b2, d,
                                                      step)
                                cases += 1
                                check(ok1 == ok2,
                                      '成败不一致 %dx%d step=%d gap=%s '
                                      'line=%d d=%s rep=%s 引擎=%s 新=%s'
                                      % (m, n, step, gap, line, d, rep,
                                         ok1, ok2))
                                if ok1 and ok2:
                                    check(sorted(map(tuple, fin1))
                                          == sorted(map(tuple, fin2)),
                                          '最终位置不一致 %dx%d gap=%s '
                                          'line=%d d=%s rep=%s'
                                          % (m, n, gap, line, d, rep))
                                sel1 = sorted(tuple(b.location) for b
                                              in g1.blocks if b.be_opted)
                                sel2 = sorted(tuple(b.location) for b
                                              in g2.blocks if b.be_opted)
                                check(sel1 == sel2,
                                      '选中片不一致 %dx%d gap=%s line=%d '
                                      'd=%s rep=%s | %s vs %s'
                                      % (m, n, gap, line, d, rep,
                                         sel1[:6], sel2[:6]))

    print('cases=%d fails=%d' % (cases, len(FAILS)))
    if FAILS:
        print('RESULT: FAIL')
        return 1
    print('RESULT: ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
