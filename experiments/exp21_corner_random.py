# -*- coding: utf-8 -*-
r"""exp21: 角缺口批量随机测试（创造模式-随机生成 同款生成器）

用 ann_gen.generate_classified(m, n, step, 0, 1) 造「恰 1 个缺口」的局面
（与 GUI 创造模式 [随机生成] 完全同源），按窗口边缘分类后走
solve_gap_macro 全链，最后用 replay_and_verify 做独立引擎回放验证。

--save-fail 模式：
    stop_on_fail=True（缺口分支失败即停、不回退填洞宏），失败案例按
    （尺寸, edge, 原因类）去重后存档 save/补缺失败-<edge>-<m>x<n>-seed<N>.json
    （游戏可读：初始+逐步快照，停在失败那一步之前，供载入复现）。

关注点：
    · 补缺宏单独（无兜底）对单缺口的覆盖率与失败原因分布
    · 奇数尺寸是否如奇偶理论预测那样「生不出」角缺口
    · 失败案例存档清单

运行：
    D:\python\python.exe experiments/exp21_corner_random.py [每尺寸批数] [--save-fail]
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
from solver.ml.gap_solver import (solve_gap_macro, _edge_of,         # noqa: E402
                                  _tf_act, _tf_dims, normalize_present,
                                  save_failure_archive)


def classify(coords, m, n, step):
    """返回 (edge 分类, 洞坐标)。多洞返回 ('multi%d' % k, None)。"""
    (r0, c0, wh), _ov, holes, _out = window_of(coords, m, n, step)
    if len(holes) != 1:
        return 'multi%d' % len(holes), None
    h = next(iter(holes))
    return _edge_of(h, r0, c0, wh[0], wh[1]), h


def main():
    argv = [a for a in sys.argv[1:] if a != '--save-fail']
    per_size = int(argv[0]) if argv else 25
    save_fail = '--save-fail' in sys.argv
    sizes = [(6, 6), (6, 8), (8, 6), (8, 8), (7, 7), (10, 10)]
    rows = []          # (seed, m, n, edge, ok, steps, secs, reason, archive)
    seen_cls = set()   # 已存档的规范局面 (coords, m, n)
    num = [0]          # 序号计数
    arch_meta = []     # (序号, m, n, edge, why, fname)
    t0 = time.time()
    for si, (m, n) in enumerate(sizes):
        for j in range(per_size):
            seed = si * 1000 + j
            rng = random.Random(seed)
            try:
                coords, _holes = generate_classified(m, n, 2, 0, 1, rng=rng)
            except ValueError as e:
                rows.append((seed, m, n, 'GEN_FAIL', False, 0, 0.0,
                             str(e)[:50], ''))
                continue
            edge, _h = classify(coords, m, n, 2)
            g = build_game(coords, m, n)
            t1 = time.time()
            out = solve_gap_macro(g, 2, stop_on_fail=save_fail)
            dt = time.time() - t1
            if isinstance(out, dict):
                ok, steps, archive = False, 0, ''
                why = out.get('reason', out.get('type', '?'))
                if save_fail and out.get('fail_world') is not None:
                    # 呈现规范形（边缺口上/凸起右下，角缺口左上/凸起右），
                    # 同一规范局面只存一份，文件名 = 序号
                    nc, nm, nn, tl = normalize_present(coords, m, n, 2)
                    key = (frozenset(nc), nm, nn)
                    if key not in seen_cls:
                        seen_cls.add(key)
                        num[0] += 1
                        fw, cm, cn = list(out['fail_world']), m, n
                        for t in tl:               # 前缀动作逐级映射进规范架
                            fw = [_tf_act(t, a, cm, cn) for a in fw]
                            cm, cn = _tf_dims(t, cm, cn)
                        archive = save_failure_archive(
                            nc, nm, nn, 2, fw, 'fail%02d' % num[0],
                            fname='失败%02d.json' % num[0]) or ''
                        arch_meta.append((num[0], nm, nn, edge, why, archive))
            else:
                acts4, reps = out
                acts5 = [a[:4] + (reps[i],) for i, a in enumerate(acts4)]
                ok = replay_and_verify(coords, m, n, 2, acts5)
                steps = len(acts4)
                why = '' if ok else '回放未还原'
                archive = ''
            rows.append((seed, m, n, edge, ok, steps, round(dt, 2), why,
                         archive))

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
        why_agg.setdefault((r[1], r[2], r[3], r[7][:38]), []).append(r)
    for (m, n, edge, why), lst in sorted(why_agg.items()):
        arch = next((r[8] for r in lst if r[8]), '')
        extra = '　[存档 %s]' % arch if arch else ''
        print('  %dx%d edge=%-7s %s  ×%d (seeds %s...)%s'
              % (m, n, edge, why, len(lst),
                 [r[0] for r in lst][:4], extra))
    corner = [r for r in rows if r[3] == 'CORNER']
    cok = [r for r in corner if r[4]]
    print('-' * 78)
    print('角缺口：生成 %d 例，补缺宏全链成功 %d 例（%.0f%%），均步 %s'
          % (len(corner), len(cok),
             100.0 * len(cok) / len(corner) if corner else 0.0,
             ('%.1f' % (sum(r[5] for r in cok) / len(cok))) if cok else '-'))
    archives = [r[8] for r in rows if r[8]]
    if arch_meta:
        print('失败存档 %d 份（呈现规范形，序号即文件名）:' % len(arch_meta))
        for no, am, an, e, w, fn in arch_meta:
            print('  失败%02d.json  %dx%d edge=%s  %s'
                  % (no, am, an, e, w[:60]))
    print('总耗时 %.1fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
