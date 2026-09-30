# -*- coding: utf-8 -*-
r"""exp21: 角缺口批量随机测试（创造模式-随机生成 同款生成器）

用 ann_gen.generate_classified(m, n, step, 0, 1) 造「恰 1 个缺口」的局面
（与 GUI 创造模式 [随机生成] 完全同源），按窗口边缘分类后走
solve_gap_macro 全链（补缺宏主路径 + 填洞宏兜底），最后用
replay_and_verify 做独立引擎回放验证。

关注点：
    · CORNER 案例的成功率与失败原因分布（验证 _corner_chain 覆盖面）
    · 奇数尺寸是否如奇偶理论预测那样「生不出」角缺口
    · 边缺口回归（L/R/U/D）是否保持全绿

运行：
    D:\python\python.exe experiments/exp21_corner_random.py [每尺寸批数]
"""
import os
import random
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from solver.ml.ann_gen import generate_classified                    # noqa: E402
from solver.ml.fill_macro import (build_game, window_of,             # noqa: E402
                                  replay_and_verify)
from solver.ml.gap_solver import solve_gap_macro, _edge_of           # noqa: E402


def classify(coords, m, n, step):
    """返回 (edge 分类, 洞坐标)。多洞返回 ('multi%d' % k, None)。"""
    (r0, c0, wh), _ov, holes, _out = window_of(coords, m, n, step)
    if len(holes) != 1:
        return 'multi%d' % len(holes), None
    h = next(iter(holes))
    return _edge_of(h, r0, c0, wh[0], wh[1]), h


def main():
    per_size = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    sizes = [(6, 6), (6, 8), (8, 6), (8, 8), (7, 7), (10, 10)]
    rows = []          # (seed, m, n, edge, ok, steps, secs, reason)
    t0 = time.time()
    for si, (m, n) in enumerate(sizes):
        for j in range(per_size):
            seed = si * 1000 + j
            rng = random.Random(seed)
            try:
                coords, _holes = generate_classified(m, n, 2, 0, 1, rng=rng)
            except ValueError as e:
                rows.append((seed, m, n, 'GEN_FAIL', False, 0, 0.0, str(e)[:50]))
                continue
            edge, _h = classify(coords, m, n, 2)
            g = build_game(coords, m, n)
            t1 = time.time()
            out = solve_gap_macro(g, 2)
            dt = time.time() - t1
            if isinstance(out, dict):
                ok, steps = False, 0
                why = out.get('reason', out.get('type', '?'))
            else:
                acts4, reps = out
                acts5 = [a[:4] + (reps[i],) for i, a in enumerate(acts4)]
                ok = replay_and_verify(coords, m, n, 2, acts5)
                steps = len(acts4)
                why = '' if ok else '回放未还原'
            rows.append((seed, m, n, edge, ok, steps, round(dt, 2), why))

    # ---- 汇总 ----
    print('=' * 78)
    agg = {}
    for r in rows:
        key = (r[1], r[2], r[3], r[4])
        agg.setdefault(key, []).append(r)
    print('%-9s %-9s %-5s %s' % ('尺寸', 'edge', '结果', '例数/均步/均耗时'))
    for (m, n, edge, ok), lst in sorted(agg.items()):
        steps = [r[5] for r in lst if r[4]]
        secs = [r[6] for r in lst if r[4]]
        ms = ('%.1f' % (sum(steps) / len(steps))) if steps else '-'
        mc = ('%.3f' % (sum(secs) / len(secs))) if secs else '-'
        print('%dx%-6d %-9s %-5s %d 例 / 均步 %s / 均 %ss'
              % (m, n, edge, '成功' if ok else '失败', len(lst), ms, mc))
    print('-' * 78)
    print('失败明细（原因分布）:')
    fails = [r for r in rows if not r[4]]
    why_agg = {}
    for r in fails:
        why_agg.setdefault((r[1], r[2], r[3], r[7][:38]), []).append(r[0])
    for (m, n, edge, why), seeds in sorted(why_agg.items()):
        print('  %dx%d edge=%-7s %s  ×%d (seeds %s...)'
              % (m, n, edge, why, len(seeds), seeds[:4]))
    corner = [r for r in rows if r[3] == 'CORNER']
    cok = [r for r in corner if r[4]]
    print('-' * 78)
    print('角缺口：生成 %d 例，全链成功 %d 例（%.0f%%），均步 %s'
          % (len(corner), len(cok),
             100.0 * len(cok) / len(corner) if corner else 0.0,
             ('%.1f' % (sum(r[5] for r in cok) / len(cok))) if cok else '-'))
    print('总耗时 %.1fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
