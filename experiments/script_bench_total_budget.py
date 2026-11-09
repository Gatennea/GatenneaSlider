# -*- coding: utf-8 -*-
"""大盘确定性对照：求解「最大等待秒数」的两种时间语义（2026-11-09）。

背景：GUI 设置页写「求解时间上限（秒）」，但 auto_solve 的 stage_budget
是**每候选各一份**：补缺宏 T 秒 + 混合 T 秒 = 最多 2T（探针实测
T=3 → 墙钟 6.01s）。新增的 total_budget 是整轮共享的单调 deadline，
首个候选最多占一半（份额 0.5，见 6 局敏感性对照）、余额让渡给后续候选。本脚本回答两件事：

  ① 换成整轮语义后，解出率 / 部分成果有没有被削？
  ② 墙钟是否真的收在 T 附近（而不是 2T）？

三组对照（第三组是**等墙钟**对照，避免把「多等一倍时间」误当优化）：
  · old_full = stage_budget=T    旧语义，最多 2T 墙钟
  · new      = total_budget=T    新语义，最多 T 墙钟
  · old_half = stage_budget=T/2  旧语义但同样最多 T 墙钟
公平比较是 new vs old_half；new vs old_full 的差额就是「偷偷多等一倍
时间」换来的解出率，属产品权衡，不是算法退化。

消方差三件套（项目铁律，见待办 §二十四）：
  · PYTHONHASHSEED=0（集合迭代序决定 DFS 探索序）
  · 局面固定：random.seed(seed) + SliderMatrix.shuffle
  · 求解显式 rng_seed=<固定>（补缺宏 `rng = rng or random.Random()` 无参
    播种 + gather_solve 吃全局 random 模块，同局面连跑两次都会漂移；
    不注入则 A/B 不可比）。脚本顺带量化「无种子」的漂移幅度。

⚠️ 固定 rng_seed 消除的是**随机漂移**，不是「带墙钟预算的解链逐位一致」：
到点切断的时机受 CPU 调度影响，大盘 5 局种子探针里 4 局固定种子两次
一致、1 局（7×7 seed1001）不一致；该局单独复跑 / 带预热复跑都一致，
属长跑后的边界抖动。所以本脚本的三组对照比的是「解出数 / 牆鐘 / 聚攏度」，
不靠逐位 fp 相等下结论。

跑法：PYTHONHASHSEED=0 D:/python/python.exe -u experiments/script_bench_total_budget.py
      [--budget 8] [--seeds 12] [--quick] [--no-seed-probe]
结果落盘：experiments/_bench_total_budget_out.txt（临时产物、未入库）
"""
import argparse
import hashlib
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game import SliderMatrix                                   # noqa: E402
from solver.auto_solver import auto_solve                       # noqa: E402
from solver.ml.fill_macro import build_game, window_of          # noqa: E402
from solver.ml.gather_solver import gather_metrics              # noqa: E402
from solver.ml.invariants import is_solved_by_profile           # noqa: E402

OUT = os.path.join(ROOT, 'experiments', '_bench_total_budget_out.txt')
FIXED_SEED = 20261109


def make_coords(m, n, seed, attempts=150):
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=2)
    return frozenset(tuple(b.location) for b in g.blocks)


def fp(r):
    """结果指纹（只看动作链，不看 reason 文案里的耗时等噪声）。"""
    if isinstance(r, tuple):
        acts, reps = r[0], r[1] or []
        payload = repr((tuple(map(tuple, acts)),
                        tuple(tuple(x) if x else None for x in reps)))
    elif isinstance(r, dict):
        acts = r.get('actions') or []
        payload = repr((r.get('type'), tuple(map(tuple, acts))))
    else:
        payload = repr(r)
    return hashlib.md5(payload.encode('utf-8')).hexdigest()[:12]


def run_case(coords, m, n, budget, shared, rng_seed=None):
    kw = {'total_budget': budget} if shared else {'stage_budget': budget}
    if rng_seed is not None:
        kw['rng_seed'] = rng_seed
    stages = []
    g = build_game(coords, m, n)
    t0 = time.time()
    r = auto_solve(g, 2, stage_cb=lambda s: stages.append(len(s['actions'])),
                   **kw)
    dt = time.time() - t0
    if isinstance(r, tuple):
        kind, acts = 'solved', r[0]
    elif isinstance(r, dict):
        kind, acts = r.get('type'), (r.get('actions') or [])
    else:
        kind, acts = 'other', []
    # 终态聚拢度：把整链动作重放到 build_game，失败则记 None
    score = None
    solved_ok = False
    if acts and isinstance(r, (tuple, dict)):
        from solver.ml.fill_macro import _replay_apply
        reps = (r[1] if isinstance(r, tuple) else r.get('rep_cells')) or []
        a5 = [tuple(a) + ((tuple(reps[i]),) if i < len(reps) and reps[i]
                          else (None,))
              for i, a in enumerate(acts)]
        gg = build_game(coords, m, n)
        if _replay_apply(gg, a5, m, n, 2):
            end = frozenset(tuple(b.location) for b in gg.blocks)
            score = gather_metrics(end, m, n)['score']
            solved_ok = is_solved_by_profile(end, m, n)
    return {'kind': kind, 'steps': len(acts), 'dt': dt,
            'stages': len(stages), 'score': score, 'fp': fp(r),
            'solved_ok': solved_ok}


def summarise(rows, budget):
    if not rows:
        return '(空)'
    dts = [r['dt'] for r in rows]
    solved = sum(r['kind'] == 'solved' for r in rows)
    over = sum(r['dt'] > budget * 1.15 + 0.5 for r in rows)
    return ('解出 %d/%d  墙钟 平均 %.2fs / 中位 %.2fs / 最大 %.2fs  '
            '超预算 %d/%d  平均段数 %.1f'
            % (solved, len(rows), statistics.mean(dts),
               statistics.median(dts), max(dts), over, len(rows),
               statistics.mean([r['stages'] for r in rows])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget', type=float, default=8.0)
    ap.add_argument('--seeds', type=int, default=12)
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--no-seed-probe', action='store_true')
    args = ap.parse_args()
    if args.quick:
        sizes = [(5, 5, 2), (6, 6, 2), (7, 7, 1)]
        args.budget = min(args.budget, 3.0)
    else:
        sizes = [(5, 5, args.seeds), (6, 6, args.seeds),
                 (7, 7, max(4, args.seeds * 2 // 3))]
    lines = ['== 时间语义大盘对照  budget=%.1fs  rng_seed=%d  sizes=%s =='
             % (args.budget, FIXED_SEED, sizes)]
    print(lines[-1], flush=True)

    old_all, new_all, half_all = [], [], []
    regressions, gains = [], []
    for m, n, count in sizes:
        for seed in range(1000, 1000 + count):
            coords = make_coords(m, n, seed)
            holes = len(window_of(coords, m, n, 2)[2])
            old = run_case(coords, m, n, args.budget, False, FIXED_SEED)
            new = run_case(coords, m, n, args.budget, True, FIXED_SEED)
            half = run_case(coords, m, n, args.budget / 2.0,
                            False, FIXED_SEED)
            old_all.append(old)
            new_all.append(new)
            half_all.append(half)
            flag = ''
            if old['kind'] == 'solved' and new['kind'] != 'solved':
                regressions.append((m, n, seed, old, new))
                flag = ' **旧解出新未解出**'
            elif new['kind'] == 'solved' and old['kind'] != 'solved':
                gains.append((m, n, seed, old, new))
                flag = ' **新解出旧未解出**'
            elif old['fp'] != new['fp']:
                flag = ' (成果链不同)'
            line = ('%dx%d seed%-5d holes=%-3d | 旧T %-13s %2d步 %5.2fs | '
                    '新 %-13s %2d步 %5.2fs | 旧T/2 %-13s %2d步 %5.2fs | '
                    'σ 旧%s 新%s 半%s%s'
                    % (m, n, seed, holes,
                       old['kind'], old['steps'], old['dt'],
                       new['kind'], new['steps'], new['dt'],
                       half['kind'], half['steps'], half['dt'],
                       '%.3f' % old['score'] if old['score'] is not None else '-',
                       '%.3f' % new['score'] if new['score'] is not None else '-',
                       '%.3f' % half['score'] if half['score'] is not None else '-',
                       flag))
            print(line, flush=True)
            lines.append(line)

    lines += ['', '== 汇总 ==',
              '旧 stage_budget=T   （最多 2T）: ' + summarise(old_all, args.budget),
              '新 total_budget=T   （最多  T）: ' + summarise(new_all, args.budget),
              '旧 stage_budget=T/2 （最多  T）: '
              + summarise(half_all, args.budget),
              '旧T 解出而新未解出: %d 局 %s'
              % (len(regressions),
                 [(a, b, c) for a, b, c, _, _ in regressions]),
              '新解出而旧T 未解出: %d 局 %s'
              % (len(gains), [(a, b, c) for a, b, c, _, _ in gains]),
              '新 vs 旧T/2（等墙钟）解出数: %d vs %d'
              % (sum(r['kind'] == 'solved' for r in new_all),
                 sum(r['kind'] == 'solved' for r in half_all))]

    # ---- 确定性探针：固定种子重复一致 / 无种子漂移幅度 ----
    if not args.no_seed_probe and not args.quick:
        probe_cases = [(6, 6, 1003), (6, 6, 1007), (7, 7, 1001),
                       (5, 5, 1011), (5, 5, 1005)]
        fixed_same = drift = 0
        for m, n, seed in probe_cases:
            coords = make_coords(m, n, seed)
            a = run_case(coords, m, n, args.budget, True, FIXED_SEED)
            b = run_case(coords, m, n, args.budget, True, FIXED_SEED)
            c = run_case(coords, m, n, args.budget, True, None)
            d = run_case(coords, m, n, args.budget, True, None)
            fixed_same += (a['fp'] == b['fp'])
            drift += (c['fp'] != d['fp'])
            line = ('[种子探针] %dx%d seed%-5d 固定同=%s (%s/%d→%s/%d) '
                    '| 无种子同=%s (%s/%d→%s/%d)'
                    % (m, n, seed,
                       a['fp'] == b['fp'], a['kind'], a['steps'],
                       b['kind'], b['steps'],
                       c['fp'] == d['fp'], c['kind'], c['steps'],
                       d['kind'], d['steps']))
            print(line, flush=True)
            lines.append(line)
        lines += ['固定种子重复一致: %d/%d' % (fixed_same, len(probe_cases)),
                  '无种子两次漂移  : %d/%d' % (drift, len(probe_cases))]

    # ---- 全解合法性 ----
    bad = [r for r in old_all + new_all + half_all
           if r['kind'] == 'solved' and not r['solved_ok']]
    lines += ['声称全解但整链未复原: %d 局' % len(bad)]

    text = '\n'.join(lines)
    _start = next((i for i, l in enumerate(lines)
                   if l == '== 汇总 =='), len(lines))
    print('\n'.join(lines[_start:]))
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print('results ->', OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
