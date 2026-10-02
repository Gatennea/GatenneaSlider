# -*- coding: utf-8 -*-
"""步数对比报告（2026-10-01）。

求解器步数 vs 用户手打步数：对每个含多帧回放（=用户复原过）的存档，
跑 GUI 同款入口取解长，与「帧数-1」（用户动作数）对比。
BFS/最短化原语下求解器应 ≤ 用户；宏链的解可能更长（贪心顺序），
长出多少就是压缩空间。

用法：
    python experiments/step_compare.py                 # 全部多帧存档
    python experiments/step_compare.py archives/失败03.json
"""
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver.ml.fill_macro import build_game, replay_and_verify
from solver.ml.gap_solver import solve_gap_macro

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'results')


def user_moves(doc):
    """用户动作数 = 有 moveinfo 的相邻帧对数（解码口径同 test/decode_frames）。"""
    snaps = doc.get('history', {}).get('snapshots', [])
    return max(0, len(snaps) - 1)


def main():
    paths = sys.argv[1:] or sorted(
        os.path.join('save', f) for f in os.listdir('save')
        if f.endswith('.json'))
    rows = []
    for path in paths:
        try:
            doc = json.load(open(path, encoding='utf-8'))
            snaps = doc.get('history', {}).get('snapshots', [])
            if len(snaps) < 2:
                continue                      # 无用户回放，跳过
            s0 = snaps[0]
            b = s0['bounds']
            co0 = frozenset((i + b['min_row'], j + b['min_col'])
                            for i, row in enumerate(s0['matrix'])
                            for j, v in enumerate(row) if v)
            pz = doc['puzzle']
            m, n, step = pz['m'], pz['n'], pz['step']
            g = build_game(co0, m, n)
            t0 = time.time()
            with redirect_stdout(io.StringIO()):
                res = solve_gap_macro(g, step)
            dt = time.time() - t0
            tag = os.path.basename(path)
            u = user_moves(doc)
            if isinstance(res, dict):
                rows.append((tag, m, n, step, u, None,
                             res.get('type', '?'), dt))
            else:
                acts4, reps = res
                ok = replay_and_verify(
                    co0, m, n, step,
                    [a + ((r,) if r is not None else ())
                     for a, r in zip(acts4, reps)])
                rows.append((tag, m, n, step, u,
                             len(acts4) if ok else -len(acts4),
                             'ok' if ok else '回放失败', dt))
        except Exception as e:
            print('跳过 %s: %r' % (path, e))

    print('\n%-34s %5s %10s %9s %7s' %
          ('存档', '盘面', '用户步', '求解器步', '用时'))
    for tag, m, n, step, u, sv, note, dt in rows:
        if sv is None:
            print('%-34s %dx%ds%d %10s %9s %6.1fs  %s'
                  % (tag, m, n, step, u, note, dt, ''))
        elif sv < 0:
            print('%-34s %dx%ds%d %10d %9s %6.1fs  %s'
                  % (tag, m, n, step, u, '✗%d' % -sv, dt, note))
        else:
            delta = sv - u
            print('%-34s %dx%ds%d %10d %9d %6.1fs  %s'
                  % (tag, m, n, step, u, sv, dt,
                     ('=%s' % ('持平' if delta == 0 else
                               '+%d' % delta if delta > 0
                               else '%d（更短）' % delta))))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, 'step_compare_%s.json'
                       % time.strftime('%Y%m%d-%H%M%S'))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump([{'archive': r[0], 'user': r[4], 'solver': r[5],
                    'note': r[6], 'secs': round(r[7], 1)} for r in rows],
                  f, ensure_ascii=False, indent=1)
    print('\n明细 → %s' % out)


if __name__ == '__main__':
    main()
