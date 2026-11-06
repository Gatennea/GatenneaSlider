# -*- coding: utf-8 -*-
"""无限打乱接入锚点规划的回归（2026-11-06，脚本型测试）。

覆盖四件事：
1. AnchorPlanner.rank() 的分档偏好：不越界优先、非平行缝优先、绝不裁剪候选；
2. 无限打乱连续取步不停机、record 格式不变、重心不跑远（planner 跟踪与真实
   坐标和一致），连续平行缝比例低于纯随机；
3. planner=None（总开关关掉）时取步与旧版等价，且真实漂移明显大于锚点版；
4. 生命周期与表现层断言：session 只在启动时建 planner、每步传入、停止时
   清掉，且没有把有限次数 / 进度条 / 结束切屏带进无限打乱。
"""
import inspect
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import anchor_shuffle  # noqa: E402
import puzzle_types  # noqa: E402
from engine.config import is_enabled, set_enabled  # noqa: E402
from gui.annotation import AnnotationMixin  # noqa: E402
from gui.session import SessionMixin  # noqa: E402

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


def _raw_drift(pre, post):
    """Σ坐标差向量长度 / 块数（不除 unit，保证 A/B 同口径可比）。"""
    dim = len(pre[0])
    v = [_part_sum(post, k) - _part_sum(pre, k) for k in range(dim)]
    return math.sqrt(sum(x * x for x in v)) / max(1, len(pre))


class Host:
    """只提供 _ann_random_shuffle_move 需要的几个 self 成员，不启 GUI。"""

    _ann_random_shuffle_move = AnnotationMixin._ann_random_shuffle_move

    def __init__(self, game, step):
        self.game = game
        self.current_step = step

    def _ann_all_valid_gaps(self):
        g = self.game
        if hasattr(g, 'all_gaps'):
            try:
                return [(gt, ln) for gt, ln in g.all_gaps()
                        if g.is_valid_gap(gt, ln)]
            except Exception:
                return []
        b = g.get_boundaries()
        out = []
        for i in range(b['min_row'], b['max_row']):
            if g.is_valid_h_line(i):
                out.append(('h', i))
        for j in range(b['min_col'], b['max_col']):
            if g.is_valid_v_line(j):
                out.append(('v', j))
        return out

    def _ann_dirs_for_gap(self, gt):
        g = self.game
        if hasattr(g, '_gap_directions'):
            return g._gap_directions(gt)
        name = g.__class__.__name__
        if name == 'MiSliderMatrix':
            from game_mi import GAP_DIRECTIONS
            return GAP_DIRECTIONS.get(gt, ())
        if name == 'TriangleSliderMatrix':
            from game_triangle import GAP_DIRECTIONS
            return GAP_DIRECTIONS.get(gt, ())
        return {'h': ('a', 'd'), 'v': ('w', 's')}.get(gt, ())


CASES = [
    ('旧方形4x4s2', False, 'square', 4, 4, 2),
    ('旧米字3x3', False, 'mi', 3, 3, 1),
    ('旧三角k4', False, 'triangle', 4, 4, 1),
    ('引擎方形4x4s2', True, 'square', 4, 4, 2),
]
WALK_STEPS = 80


def _walk(eng, kind, m, n, step, seed, with_anchor):
    random.seed(seed)
    set_enabled(eng)
    g = puzzle_types.create_puzzle(
        m, n, 1, kind=kind,
        triangle_side=4 if kind == 'triangle' else None)
    host = Host(g, step)
    pre = [tuple(b.location) for b in g.blocks]
    pl = (anchor_shuffle.AnchorPlanner(
        g.blocks, step, max_drift=anchor_shuffle.MAX_DRIFT)
        if with_anchor else None)
    recs = []
    max_raw = 0.0
    for _ in range(WALK_STEPS):
        rec = host._ann_random_shuffle_move(planner=pl)
        if rec is None:
            break
        recs.append(rec)
        max_raw = max(max_raw, _raw_drift(
            pre, [tuple(b.location) for b in g.blocks]))
    return g, pre, recs, pl, max_raw


def _parallel_rate(recs):
    if len(recs) < 2:
        return 0.0
    return sum(1 for a, b in zip(recs, recs[1:])
               if a['gap'][0] == b['gap'][0]) / (len(recs) - 1)


def t1_rank():
    blocks = [type('B', (), {'location': p})()
              for p in [(0, 0), (0, 1), (1, 0), (1, 1)]]
    pl = anchor_shuffle.AnchorPlanner(blocks, 1, max_drift=1.0)
    pl.prev_key = 'h'
    mk = lambda gt, delta, par: anchor_shuffle.StepCandidate(  # noqa: E731
        gt, 0, 'a', None, [(0, 0)],
        [(int(delta[0]), int(delta[1]))], par)
    parallel_small = mk('h', (0, 1), 'h')
    nonpar_small = mk('v', (1, 0), 'v')
    nonpar_far = mk('v', (9, 0), 'v')
    cands = [parallel_small, nonpar_far, nonpar_small]
    ranked = pl.rank(cands)
    check('T1 rank 不裁剪候选', len(ranked) == len(cands),
          '%d -> %d' % (len(cands), len(ranked)))
    check('T1 rank 非平行缝优先', ranked[0] is nonpar_small,
          'first=%s' % ranked[0].parallel)
    check('T1 rank 越界候选排最后', ranked[-1] is nonpar_far,
          'last delta=%s' % str(ranked[-1].delta))
    check('T1 rank 不消耗选步状态',
          pl.steps == 0 and pl.prev_key == 'h' and pl.offset == (0.0, 0.0))


def t2_walk_with_anchor():
    for label, eng, kind, m, n, step in CASES:
        g, pre, recs, pl, max_raw = _walk(eng, kind, m, n, step,
                                          20261106, True)
        ok = len(recs) == WALK_STEPS
        check('T2 %s 连续 %d 步不停机' % (label, WALK_STEPS), ok,
              '(%d 步)' % len(recs))
        if not recs:
            continue
        shape = all(set(('moved', 'final', 'gap', 'direction', 'step')) <=
                    set(r) and len(r['moved']) == len(r['final'])
                    and r['moved'] for r in recs)
        check('T2 %s record 格式不变' % label, shape)
        check('T2 %s 过程重心不越上限' % label,
              pl.max_seen <= pl.cap() + 0.5,
              '%.3f <= %.3f' % (pl.max_seen, pl.cap()))
        # planner 的 offset 必须等于真实坐标和之差，否则锚点是假的
        dim = len(pre[0])
        real = tuple(_part_sum([tuple(b.location) for b in g.blocks], k) -
                     _part_sum(pre, k) for k in range(dim))
        check('T2 %s 偏移与真实坐标和一致' % label,
              all(abs(a - b) < 1e-6 for a, b in zip(real, pl.offset)),
              'real=%s pl=%s' % (str(real), str(pl.offset)))
        check('T2 %s 真实漂移受控' % label, max_raw <= pl.cap() + 1.0,
              '%.3f' % max_raw)


def t3_compare_without_anchor():
    for label, eng, kind, m, n, step in CASES:
        _, _, recs_a, pl, max_a = _walk(eng, kind, m, n, step,
                                        20261106, True)
        _, _, recs_b, _, max_b = _walk(eng, kind, m, n, step,
                                       20261106, False)
        check('T3 %s 关锚点仍能连续走步' % label,
              len(recs_b) == WALK_STEPS, '(%d 步)' % len(recs_b))
        check('T3 %s 锚点版漂移更小' % label,
              max_a < max_b + 1e-9,
              '%.3f vs %.3f' % (max_a, max_b))
        par_a, par_b = _parallel_rate(recs_a), _parallel_rate(recs_b)
        check('T3 %s 连续平行缝不更多' % label,
              par_a <= par_b + 1e-9, '%.3f vs %.3f' % (par_a, par_b))
        check('T3 %s 锚点版确实提交了步' % label,
              pl is not None and pl.steps == len(recs_a),
              '%d' % (pl.steps if pl else -1))


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


def _replay_back(g, recs):
    """把整条游走倒序重放，能回到起点 = 每步都可逆（终态恒有解）。"""
    for r in reversed(recs):
        gap_type, line = r['gap']
        want = set(r['final'])
        target = set(r['moved'])
        trig = next((b for b in g.blocks
                     if tuple(b.location) in want), None)
        if trig is None:
            return False
        g.opt(gap_type, line, trig)
        ok = False
        for d in _dirs_of(g, gap_type):
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


def t5_reversible_certificate():
    for label, eng, kind, m, n, step in CASES:
        g, pre, recs, _, _ = _walk(eng, kind, m, n, step, 777, True)
        if not recs:
            check('T5 %s 逆放回初态' % label, False, '(没有步)')
            continue
        back_ok = _replay_back(g, recs)
        same = ({tuple(b.location) for b in g.blocks} == set(pre))
        check('T5 %s 逆放回初态' % label, back_ok and same,
              '(%d 步)' % len(recs))


def t4_lifecycle_and_no_demo():
    start = inspect.getsource(SessionMixin._start_infinite_shuffle)
    step = inspect.getsource(SessionMixin._infinite_shuffle_step)
    restore = inspect.getsource(SessionMixin._restore_infinite_duration)
    check('T4 启动时以当前盘面创建 AnchorPlanner',
          'AnchorPlanner' in start and 'anchor_shuffle.ENABLED' in start)
    check('T4 每步把 planner 传给取步',
          '_ann_random_shuffle_move' in step and 'planner=' in step)
    check('T4 停止时清掉 planner',
          '_infinite_anchor = None' in restore)
    check('T4 无限打乱不带进度条 / 切屏 / 有限次数',
          '_shuffle_demo_active' not in step
          and '_start_shuffle_demo' not in step
          and 'attempts' not in step)


def main():
    was = is_enabled()
    try:
        t1_rank()
        t2_walk_with_anchor()
        t3_compare_without_anchor()
        t5_reversible_certificate()
        t4_lifecycle_and_no_demo()
    finally:
        set_enabled(was)
    print('\nFAILS =', len(FAILS), FAILS)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
