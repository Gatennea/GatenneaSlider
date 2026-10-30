# -*- coding: utf-8 -*-
"""Φ（行列剖面 L1）成本与贪心行为验证（2026-10-10 深夜实验）。

上接 experiments/script__metric_duel.py：Φ 与 σ 在「预测真实距离」上打平，
但**平台率低 4 倍**（2.1% vs 8.7%）。本脚本补两块实证：

  (a) 成本：Φ 是 O(K) 计数，σ 要枚举全部候选窗口（find_best_window
      + _overlap_at，实测占端到端 41%）。直接测两者的计算耗时比。
      ⚠ 本机漂移大（历史教训：曾误回退有效优化），故用 **ABAB 交替 +
      逐轮配对看胜负**，不做单次粗测。
  (b) 行为：在真实 8×8 局面上做纯贪心爬山，比较 σ 引导 vs Φ 引导
      谁走得更远、更早卡住。

用法：
    D:/python/python.exe -u experiments/script__phi_cost.py > experiments/_phi_cost_out.txt 2>&1
"""
import json
import os
import random
import statistics
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'experiments'))          # 非包目录直载

from solver.ml.fill_macro import build_game                       # noqa: E402
from solver.actions import enumerate_valid_actions, apply_action  # noqa: E402
from solver.ml.gather_solver import max_overlap                   # noqa: E402
from _metric_duel import profile_defect                           # noqa: E402


def sigma_at(coords, m, n):
    """给定尺寸的 σ。⚠ 不能直接用 _metric_duel.sigma —— 那个模块为 4×4
    实验写死了 M=N=4，拿去算 8×8 会因 len(coords)!=16 恒返回 0
    （2026-10-10 踩到的坑，曾导致本脚本结果全废）。"""
    return max_overlap(coords, m, n) / (m * n)


def load_coords(path, snap_idx=0):
    with open(os.path.join(_ROOT, path), encoding='utf-8') as f:
        doc = json.load(f)
    snap = doc['history']['snapshots'][snap_idx]
    b = snap['bounds']
    coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                       for i, row in enumerate(snap['matrix'])
                       for j, v in enumerate(row) if v)
    pz = doc['puzzle']
    return coords, pz['m'], pz['n'], pz['step']


def random_8x8_coords(seed, moves=60):
    m = n = 8
    g = build_game(frozenset((r, c) for r in range(m) for c in range(n)), m, n)
    rnd = random.Random(seed)
    for _ in range(moves):
        acts = enumerate_valid_actions(g, 2)
        if not acts:
            break
        apply_action(g, rnd.choice(acts), 2)
    return frozenset((b.location[0], b.location[1]) for b in g.blocks)


# --------------------------------------------------------------- (a) 成本
def cost_abab():
    print('\n=== (a) 计算成本：ABAB 交替，逐轮配对 ===')
    states = []
    for rel in ('archives/失败06.json', 'archives/失败07.json'):
        p = os.path.join(_ROOT, rel)
        if os.path.exists(p):
            states.append(load_coords(rel)[0])
    for sd in (1, 2, 3, 4):
        states.append(random_8x8_coords(sd, 60))
    states = [s for s in states if s]
    print('  样本局面 %d 个（8×8）' % len(states))

    REPEAT = 300          # 每个度量每轮对每个局面跑多少次
    rounds = 8
    win_sigma = win_phi = 0
    ts_all, tp_all = [], []
    for rd in range(rounds):
        if rd % 2 == 0:                      # A→B
            order = [('sigma', REPEAT), ('phi', REPEAT)]
        else:                                # B→A
            order = [('phi', REPEAT), ('sigma', REPEAT)]
        timings = {}
        for tag, rep in order:
            t0 = time.perf_counter()
            if tag == 'sigma':
                for cs in states:
                    for _ in range(rep):
                        sigma_at(cs, 8, 8)
            else:
                for cs in states:
                    for _ in range(rep):
                        profile_defect(cs, 8, 8)
            timings[tag] = time.perf_counter() - t0
        ts, tp = timings['sigma'], timings['phi']
        ts_all.append(ts)
        tp_all.append(tp)
        print('  第%d轮  %s顺序  σ=%.4fs  Φ=%.4fs   winning=%s (x%.2f)'
              % (rd + 1, 'A→B' if rd % 2 == 0 else 'B→A', ts, tp,
                 'Φ' if tp < ts else 'σ',
                 (ts / tp) if tp > 0 else 0))
        if tp < ts:
            win_phi += 1
        else:
            win_sigma += 1
    print('  Φ 胜 %d 轮 / σ 胜 %d 轮（共 %d 轮）' % (win_phi, win_sigma, rounds))
    print('  平均：σ=%.4fs  Φ=%.4fs  → Φ 快 %.2f 倍'
          % (statistics.mean(ts_all), statistics.mean(tp_all),
             statistics.mean(ts_all) / max(1e-9, statistics.mean(tp_all))))


# --------------------------------------------------------------- (b) 贪心
def greedy(coords, m, n, step, use_phi, max_steps=60):
    """纯贪心爬山。返回 dict。"""
    cur = coords
    hist = []
    t0 = time.perf_counter()
    for i in range(max_steps):
        g = build_game(cur, m, n)
        best_val = None
        best_cs = None
        for a in enumerate_valid_actions(g, step):
            g2 = build_game(cur, m, n)
            if not apply_action(g2, a, step):
                continue
            cs2 = frozenset((b.location[0], b.location[1]) for b in g2.blocks)
            if len(cs2) != len(cur):
                continue
            v = profile_defect(cs2, m, n) if use_phi else -sigma_at(cs2, m, n)
            if best_val is None or v < best_val - 1e-12:
                best_val, best_cs = v, cs2
        if best_cs is None or best_cs == cur:
            break                      # 卡住
        cur = best_cs
        hist.append(sigma_at(cur, m, n))
    return {'steps': len(hist), 'final_sigma': sigma_at(cur, m, n),
            'final_phi': profile_defect(cur, m, n),
            'time': time.perf_counter() - t0,
            'solved': build_game(cur, m, n).is_solved()}


def greedy_duel():
    print('\n=== (b) 纯贪心爬山：σ 引导 vs Φ 引导（8×8, step2）===')
    cases = []
    for rel, label in (('archives/失败06.json', '06局面'),
                       ('archives/失败07.json', '07局面')):
        p = os.path.join(_ROOT, rel)
        if os.path.exists(p):
            cs, m, n, st = load_coords(rel)
            cases.append((cs, '%s' % label))
    for sd in (11, 12, 13):
        cases.append((random_8x8_coords(sd, 80), '随机%d' % sd))

    rows = []
    for cs, label in cases:
        r_s = greedy(cs, 8, 8, 2, use_phi=False)
        r_p = greedy(cs, 8, 8, 2, use_phi=True)
        rows.append((label, r_s, r_p))
        print('  %-10s σ引导 %3d步 σ=%.3f Φ=%2d | Φ引导 %3d步 σ=%.3f Φ=%2d'
              % (label, r_s['steps'], r_s['final_sigma'], r_s['final_phi'],
                 r_p['steps'], r_p['final_sigma'], r_p['final_phi']))
    print('\n  汇总（越高越好＝最终 σ，越低越好＝最终 Φ）：')
    avg_s_s = statistics.mean(r['final_sigma'] for _l, r, _p in rows)
    avg_p_s = statistics.mean(r['final_sigma'] for _l, _s, r in rows)
    avg_s_phi = statistics.mean(r['final_phi'] for _l, r, _p in rows)
    avg_p_phi = statistics.mean(r['final_phi'] for _l, _s, r in rows)
    print('    σ 引导：最终 σ=%.4f  最终 Φ=%.2f' % (avg_s_s, avg_s_phi))
    print('    Φ 引导：最终 σ=%.4f  最终 Φ=%.2f' % (avg_p_s, avg_p_phi))
    print('    步数：σ引导均 %.1f，Φ引导均 %.1f'
          % (statistics.mean(r['steps'] for _l, r, _p in rows),
             statistics.mean(r['steps'] for _l, _s, r in rows)))


def main():
    print('=' * 74)
    print('Φ vs σ：成本与贪心行为')
    print('=' * 74)
    cost_abab()
    greedy_duel()


if __name__ == '__main__':
    main()
