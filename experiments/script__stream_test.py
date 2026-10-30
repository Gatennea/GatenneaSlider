# -*- coding: utf-8 -*-
"""流式协议单测：segment_cb 段拼接 + fill_stream 未播剩余 = 完整可回放解。"""
import json
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from solver.ml.fill_macro import build_game, _replay_apply  # noqa: E402
from solver.ml.gap_solver import solve_gap_macro  # noqa: E402

CASES = ['archives/失败03.json', 'archives/失败04.json',
         'archives/2-4-4-20261001-103250.json']


def load(fname):
    with open(os.path.join(_ROOT, fname), encoding='utf-8') as f:
        doc = json.load(f)
    snap = doc['history']['snapshots'][0]
    b = snap['bounds']
    coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                       for i, row in enumerate(snap['matrix'])
                       for j, v in enumerate(row) if v)
    pz = doc['puzzle']
    return coords, pz['m'], pz['n'], pz['step']


for case in CASES:
    path = os.path.join(_ROOT, case)
    if not os.path.exists(path):
        continue
    coords, m, n, step = load(case)
    segs = []
    g = build_game(coords, m, n)
    res = solve_gap_macro(g, step, segment_cb=lambda lab, a5:
                          segs.append((lab, list(a5))))
    print('=' * 56)
    print(case, '段数=%d' % len(segs))
    for lab, a5 in segs:
        print('  [%s] %d 步' % (lab, len(a5)))
    streamed = 0
    rest = []
    rest_reps = []
    solved_flag = None
    if isinstance(res, dict) and res.get('type') == 'fill_stream':
        streamed = res.get('streamed', 0)
        rest = [(a[0], a[1], a[2], a[3]) for a in res.get('actions', [])]
        rest_reps = res.get('rep_cells', []) or []
        solved_flag = res.get('solved')
        print('  fill_stream: streamed=%d rest=%d solved=%s reason=%s'
              % (streamed, len(rest), solved_flag,
                 res.get('reason', '')))
    elif isinstance(res, dict):
        print('  dict:', res)
        continue
    else:
        acts4, reps = res
        print('  元组协议: %d 步（无流式段时正常）' % len(acts4))
        continue
    # 段拼接 + rest 回放（rest 动作带 rep：convoy/带移宏必须精确选块）
    total = [a for _lab, a5 in segs for a in a5]
    g2 = build_game(coords, m, n)
    ok = _replay_apply(g2, total, m, n, step)
    for i, a4 in enumerate(rest):
        rep = rest_reps[i] if i < len(rest_reps) else None
        a5 = tuple(a4) + ((tuple(rep),) if rep else (None,))
        from solver.ml.fill_macro import _capture_apply
        one_ok, _cap = _capture_apply(g2, a5, step)
        if not one_ok:
            print('  rest 第 %d 步回放失败: %s' % (i, a5))
            ok = False
            break
    print('  拼接回放: ok=%s is_solved=%s (solved字段=%s) 总步=%d 段步=%d'
          % (ok, g2.is_solved(), solved_flag, len(total) + len(rest),
             sum(len(a5) for _l, a5 in segs)))
