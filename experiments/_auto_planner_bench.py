# -*- coding: utf-8 -*-
"""自动规划混合求解器新旧入口对比基准（2026-10-02）。

主指标 = 运算时间（用户 2026-09-30 拍板），步数为副指标。
案例：
  A. 4×4 step2 seed 1000/1001（有表：新旧都应走表，验证不吃亏）
  B. 5×5 step2 seed 1000/1001/1002（无表：新=补缺宏先行，旧=直接混合流水线）
  C. beginner_archive/5.1.json（刚体案例，无表）
  D. archives/失败04.json（已知死局：验证新入口 fill_partial 断点协议；只跑新）

运行：D:/python/python.exe experiments/_auto_planner_bench.py
"""
import os
import sys
import json
import time
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'experiments'))

import harness                                        # noqa: E402
from solver.ml.fill_macro import build_game           # noqa: E402
from solver.auto_solver import auto_solve             # noqa: E402
from solver import hybrid_solve_with_table            # noqa: E402
from game import SliderMatrix                         # noqa: E402


def shuffled_coords(m, n, step, seed, attempts=140):
    import random
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=step)
    return frozenset(tuple(b.location) for b in g.blocks)


def run_one(fn, coords, m, n, step, budget_s=150):
    """带硬超时跑一个求解入口。返回 (耗时, 结果, 是否超时)。"""
    box = {}

    def cancelled():
        return box.get('stop', False)

    def worker():
        g = build_game(coords, m, n)
        t0 = time.time()
        try:
            res = fn(g, step, cancel_check=cancelled)
        except Exception as e:
            res = {'type': 'fill_fail', 'reason': '异常: %s' % e}
        box['res'] = res
        box['dt'] = time.time() - t0

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join(budget_s)
    if th.is_alive():
        box['stop'] = True
        th.join(20)
        return budget_s, None, True
    return box.get('dt', -1), box.get('res'), False


def describe(res):
    if res is None:
        return 'TIMEOUT'
    if isinstance(res, tuple):
        return 'solved %d 步' % len(res[0])
    if isinstance(res, dict):
        t = res.get('type', '?')
        if t == 'fill_partial':
            return 'partial %d 步（%s）' % (len(res.get('actions', [])),
                                           res.get('reason', '')[:40])
        return '%s：%s' % (t, str(res.get('reason', ''))[:40])
    return str(res)


def shuffled_game(m, n, step, seed, attempts=140):
    import random
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=step)
    return g


def case_coords(key):
    if key.startswith('4x4:'):
        return shuffled_coords(4, 4, 2, int(key.split(':')[1]))
    if key.startswith('5x5:'):
        return shuffled_coords(5, 5, 2, int(key.split(':')[1]))
    if key.startswith('archive:'):
        doc = json.load(open(os.path.join(ROOT, 'beginner_archive',
                                          key.split(':')[1]), encoding='utf-8'))
        s0 = doc['history']['snapshots'][0]
        b = s0['bounds']
        pz = doc['puzzle']
        coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                           for i, row in enumerate(s0['matrix'])
                           for j, v in enumerate(row) if v)
        return coords, pz['m'], pz['n'], pz['step']
    if key.startswith('save:'):
        doc = json.load(open(os.path.join(ROOT, 'save',
                                          key.split(':')[1]), encoding='utf-8'))
        s0 = doc['history']['snapshots'][0]
        b = s0['bounds']
        pz = doc['puzzle']
        coords = frozenset((b['min_row'] + i, b['min_col'] + j)
                           for i, row in enumerate(s0['matrix'])
                           for j, v in enumerate(row) if v)
        return coords, pz['m'], pz['n'], pz['step']
    raise KeyError(key)


CASES = ['4x4:1000']
# 完整对比见 _bench_out3.txt（2026-10-02）；本轮只复核 4×4 抽样 + 04 尽早停。

def _main():
    print('%-18s %-28s %-28s' % ('案例', '旧入口(表→混合)', '新入口(自动规划)'), flush=True)
    print('-' * 78, flush=True)
    for key in CASES:
        got = case_coords(key)
        coords, m, n, step = (got if isinstance(got, tuple) else (got, 4, 4, 2)) \
            if key.startswith(('4x4', '5x5')) else got
        print('[bench] %s 旧入口开始' % key, flush=True)
        dt_o, res_o, to_o = run_one(hybrid_solve_with_table, coords, m, n, step)
        print('[bench] %s 旧入口结束 %.1fs' % (key, dt_o), flush=True)
        dt_n, res_n, to_n = run_one(auto_solve, coords, m, n, step)
        print('[bench] %s 新入口结束 %.1fs' % (key, dt_n), flush=True)
        print('%-18s %-28s %-28s' % (
            key,
            ('%.1fs %s' % (dt_o, 'TIMEOUT' if to_o else describe(res_o))),
            ('%.1fs %s' % (dt_n, 'TIMEOUT' if to_n else describe(res_n)))), flush=True)

    # 失败04：新入口全程（补缺宏 partial 96s + 混合续算），预算放宽
    coords4, m4, n4, s4 = case_coords('save:失败04.json')
    print('[bench] save:失败04.json 新入口开始', flush=True)
    dt_n, res_n, to_n = run_one(auto_solve, coords4, m4, n4, s4, budget_s=240)
    print('%-18s %-28s %-28s' % ('save:失败04.json', '（旧=混合单项 76.8s partial）',
                                 '%.1fs %s' % (dt_n, 'TIMEOUT' if to_n else describe(res_n))),
          flush=True)
    print('-' * 78, flush=True)
    print('完成。主指标=时间；两入口同解则新入口应 ≤ 旧入口。', flush=True)


if __name__ == '__main__':
    _main()
