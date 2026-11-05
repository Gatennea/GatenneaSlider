# -*- coding: utf-8 -*-
"""锚点式打乱回归（2026-11-06，脚本型测试，与仓库既有约定一致）。

覆盖四件事：
1. 一步贡献 = Σ(final) − Σ(moved)，非数值分量（米字朝向）贡献 0；
2. 打乱全程与终局的重心偏移都不超过硬上限，且 record 正放 / 逆放证书成立；
3. 连续两步平行缝比例、正反向计数不平衡度都明显低于纯随机打乱；
4. 硬上限不会把盘面锁死在聚拢态，min_score 重洗仍能达标。
"""
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import anchor_shuffle
import puzzle_types
from engine.config import is_enabled, set_enabled

FAILS = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name +
          (('  ' + detail) if detail else ''))
    if not ok:
        FAILS.append(name)
    return ok


def _part_sum(locs, k):
    try:
        return sum(float(p[k]) for p in locs)
    except (TypeError, ValueError):
        return 0.0


def _drift(pre, post, unit=1.0):
    dim = len(pre[0])
    v = [_part_sum(post, k) - _part_sum(pre, k) for k in range(dim)]
    return math.sqrt(sum(x * x for x in v)) / (len(pre) * unit)


def _dirs_of(g, gap_type):
    if hasattr(g, '_gap_directions'):
        return g._gap_directions(gap_type)
    name = g.__class__.__name__
    if name == 'MiSliderMatrix':
        from game_mi import GAP_DIRECTIONS
        return GAP_DIRECTIONS[gap_type]
    if name == 'TriangleSliderMatrix':
        from game_triangle import GAP_DIRECTIONS
        return GAP_DIRECTIONS[gap_type]
    return ('a', 'd') if gap_type == 'h' else ('w', 's')


def _replay(g, records, start, forward=True):
    for b, p in zip(g.blocks, start):
        b.location = list(p)
    for r in (records if forward else reversed(records)):
        gap_type, line = r['gap']
        want = set(r['final'] if not forward else r['moved'])
        target = set(r['moved'] if not forward else r['final'])
        trig = next((b for b in g.blocks
                     if tuple(b.location) in want), None)
        if trig is None:
            return False
        g.opt(gap_type, line, trig)
        dirs = (_dirs_of(g, gap_type) if not forward
                else (r['direction'],))
        ok = False
        for d in dirs:
            back = g.try_move(d, r['step'])
            if back and {tuple(p) for p in back} == target:
                g.commit_move(back)
                ok = True
                break
        if not ok:
            return False
        for b in g.blocks:
            b.be_opted = False
    return True


def _balance(records):
    """每族正反向计数差之和 / 总步数。"""
    ref, led, cnt = {}, {}, {}
    for r in records:
        fam = r['gap'][0]
        dim = len(r['moved'][0]) if r['moved'] else 0
        d = tuple(_part_sum(r['final'], k) - _part_sum(r['moved'], k)
                  for k in range(dim))
        if fam not in ref:
            ref[fam], led[fam], cnt[fam] = d, 1, 1
            continue
        led[fam] += 1 if sum(a * b for a, b in zip(ref[fam], d)) > 0 else -1
        cnt[fam] += 1
    return sum(abs(v) for v in led.values()) / max(1, sum(cnt.values()))


def _parallel_rate(records):
    if len(records) < 2:
        return 0.0
    return sum(1 for a, b in zip(records, records[1:])
               if a['gap'][0] == b['gap'][0]) / (len(records) - 1)


class _Capture:
    """捕获本次 shuffle 用到的 planner（不改生产代码）。"""

    def __init__(self):
        self.items = []
        self._orig = anchor_shuffle.AnchorPlanner

    def __enter__(self):
        outer = self

        class Rec(self._orig):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                outer.items.append(self)

        anchor_shuffle.AnchorPlanner = Rec
        return self

    def __exit__(self, *exc):
        anchor_shuffle.AnchorPlanner = self._orig
        return False


def _run(eng, kind, m, n, step, attempts, seed):
    random.seed(seed)
    set_enabled(eng)
    g = puzzle_types.create_puzzle(
        m, n, 1, kind=kind,
        triangle_side=4 if kind == 'triangle' else None)
    pre = [tuple(b.location) for b in g.blocks]
    records = []
    with _Capture() as cap:
        g.shuffle(attempts, step, bias=0.3, min_score=0.75,
                  record=records)
    post = [tuple(b.location) for b in g.blocks]
    return g, pre, post, records, (cap.items[-1] if cap.items else None)


CASES = [
    ('旧方形4x4s2', False, 'square', 4, 4, 2, 60),
    ('旧方形6x6s1', False, 'square', 6, 6, 1, 80),
    ('旧米字3x3', False, 'mi', 3, 3, 1, 40),
    ('旧三角k4', False, 'triangle', 4, 4, 1, 40),
    ('引擎方形4x4s2', True, 'square', 4, 4, 2, 60),
    ('引擎米字3x3', True, 'mi', 3, 3, 1, 40),
    ('引擎三角k4', True, 'triangle', 4, 4, 1, 40),
    ('模型碎三角', True, 'shatter', 4, 4, 1, 40),
]


def t1_delta_math():
    cand = anchor_shuffle.StepCandidate(
        'h', 1, 'a', None,
        [(0, 0, 'N'), (0, 1, 'N')],
        [(0, -2, 'N'), (0, -1, 'N')], 'h')
    check('T1 一步贡献=Σfinal−Σmoved',
          tuple(cand.delta) == (0.0, -4.0, 0.0),
          str(tuple(cand.delta)))
    check('T1 米字朝向 q 贡献为 0', abs(cand.delta[2]) < 1e-9)

    blocks = [type('B', (), {'location': p})()
              for p in [(0, 0), (0, 1), (1, 0), (1, 1)]]
    pl = anchor_shuffle.AnchorPlanner(blocks, 1, max_drift=1.0)
    check('T1 初始即在锚点', pl.offset == (0.0, 0.0) and pl.is_anchored())
    c = anchor_shuffle.StepCandidate('h', 1, 'd', None,
                                    [(0, 0), (0, 1)],
                                    [(0, 1), (0, 2)], 'h')
    pl.commit(c, blocks, 1)
    check('T1 偏移按步累加', pl.offset == (0.0, 2.0) and
          not pl.is_anchored(), str(pl.offset))


def t2_hard_cap_and_certificate():
    was = is_enabled()
    try:
        for label, eng, kind, m, n, step, attempts in CASES:
            g, pre, post, records, pl = _run(eng, kind, m, n, step,
                                             attempts, 4242)
            ok = bool(records) and pl is not None
            check('T2 %s 走出步数且启用规划器' % label, ok,
                  '(%d 步)' % len(records))
            if not ok:
                continue
            check('T2 %s 过程漂移不越硬上限' % label,
                  pl.max_seen <= pl.cap() + 1e-6,
                  '%.3f <= %.3f' % (pl.max_seen, pl.cap()))
            check('T2 %s 终局漂移不越硬上限' % label,
                  _drift(pre, post, pl.unit or 1.0) <= pl.cap() + 1e-6,
                  '%.3f' % _drift(pre, post, pl.unit or 1.0))
            fwd = _replay(g, records, pre, forward=True)
            check('T2 %s record 正放复现终态' % label,
                  fwd and {tuple(b.location) for b in g.blocks} == set(post))
            rev = _replay(g, records, post, forward=False)
            check('T2 %s record 逆放回初态（可解证书）' % label,
                  rev and {tuple(b.location) for b in g.blocks} == set(pre))
    finally:
        set_enabled(was)


def t3_sequence_shape():
    was, was_enabled = is_enabled(), anchor_shuffle.ENABLED
    try:
        set_enabled(False)
        random.seed(20261106)
        anchor_shuffle.ENABLED = False
        g0 = puzzle_types.create_puzzle(6, 6, 1, kind='square')
        rec0 = []
        g0.shuffle(80, 1, bias=0.0, min_score=None, record=rec0)

        anchor_shuffle.ENABLED = True
        g1, pre, post, rec1, pl = _run(False, 'square', 6, 6, 1, 80,
                                       20261106)
        check('T3 两条序列都非空', len(rec0) > 5 and len(rec1) > 5,
              '(%d / %d 步)' % (len(rec0), len(rec1)))
        b0, b1 = _balance(rec0), _balance(rec1)
        check('T3 正反向更接近抵消', b1 <= b0 + 0.05,
              '%.3f vs %.3f' % (b1, b0))
        p0, p1 = _parallel_rate(rec0), _parallel_rate(rec1)
        check('T3 连续平行缝更少', p1 <= p0 + 0.10,
              '%.3f vs %.3f' % (p1, p0))
        check('T3 新版仍守硬上限',
              _drift(pre, post, pl.unit or 1.0) <= pl.cap() + 1e-6)
    finally:
        anchor_shuffle.ENABLED = was_enabled
        set_enabled(was)


def t4_disabled_switch():
    was, was_enabled = is_enabled(), anchor_shuffle.ENABLED
    try:
        set_enabled(False)
        random.seed(17)
        anchor_shuffle.ENABLED = False
        g = puzzle_types.create_puzzle(4, 4, 1, kind='square')
        records = []
        with _Capture() as cap:
            g.shuffle(30, 2, bias=0.0, min_score=None, record=records)
        check('T4 总开关关闭时不建规划器', cap.items == [])
        check('T4 旧路径仍能打乱', bool(records),
              '(%d 步)' % len(records))
    finally:
        anchor_shuffle.ENABLED = was_enabled
        set_enabled(was)


def t5_min_score_not_stuck():
    """硬上限不能把盘面钉在聚拢态：min_score 重洗必须能达标。

    2026-11-06 回归：三角实心盘 step=2 只有「动很多块」的大步可走，
    若所有越界候选一律整步作废，shuffle(min_score=0.75) 会偶发停在
    compute_score=1.000 的还原态（契约测试挂）。修复＝无路可走时收下
    越界最少的一步、把上限抬到必要值。
    故意不播种：这个回归是概率性的（旧行为约 4/60 触发），固定 seed
    可能恰好躲过去；60 次独立打乱足够把护栏撑起来，且修复后恒为 0。
    """
    from game_triangle import TriangleSliderMatrix
    was, was_enabled = is_enabled(), anchor_shuffle.ENABLED
    try:
        set_enabled(False)
        anchor_shuffle.ENABLED = True
        bad = []
        for i in range(60):
            g = TriangleSliderMatrix(4)
            rec = []
            g.shuffle(80, 2, bias=0.0, min_score=0.75, record=rec)
            if g.compute_score() > 0.75 + 1e-9 or not rec:
                bad.append((i, round(g.compute_score(), 3), len(rec)))
        check('T5 三角 step=2 重洗 60 次都达标（硬上限不锁死）',
              not bad, repr(bad[:5]))
    finally:
        anchor_shuffle.ENABLED = was_enabled
        set_enabled(was)


def main():
    t1_delta_math()
    t2_hard_cap_and_certificate()
    t3_sequence_shape()
    t4_disabled_switch()
    t5_min_score_not_stuck()
    print('\nFAILS =', len(FAILS), FAILS)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
