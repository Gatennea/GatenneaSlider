# -*- coding: utf-8 -*-
"""部分成果择优规则单一真源验证（2026-10-15 解耦修复，不依赖 pygame）。

背景：修复前择优规则分裂两处且不一致——求解器 keep_partial 只比聚拢度
（并列先到先得），「并列取 Φ 最小」只在 GUI _update_auto_best 实现。
后果：headless 调用方（HTTP API / 实验 / 批量实验）拿到的 fill_partial
断点并非同规则最优；流式播放时求解器并列选中的段会被上报播放，GUI 只能
在收到的段之间择优；run_hybrid 续算起点 best['end'] 也建立在次优选择上。

本测试锁定修复后行为：
1. partial_better 规则矩阵（聚拢度高者胜 / 并列 Φ 小者胜 / 其余拒）；
2. GUI _update_auto_best 与求解器引用同一函数（物理同源，行为一致）；
3. 真实局面：auto_solve 返回的 fill_partial 断点不差于任何已上报未解段
   （流式与非流式两条路径同规则）。
"""
import sys
sys.path.insert(0, '.')

import random

from solver.auto_solver import auto_solve, partial_better
from gui.auto_solve import AutoSolveMixin


# ---------- 1. 规则矩阵 ----------

def test_partial_better_matrix():
    cases = [
        # (sc_new, phi_new, sc_old, phi_old) -> 期望
        ((0.5, 3.0, None, None), True),    # 尚无最优：直接胜出
        ((0.9, 0.0, 0.5, 3.0), True),      # 聚拢度严格高：胜（Φ 大也胜）
        ((0.5, 3.0, 0.9, 0.0), False),     # 严格低：败
        ((0.5, 2.0, 0.5, 3.0), True),      # 并列，新 Φ 小：胜
        ((0.5, 3.0, 0.5, 2.0), False),     # 并列，新 Φ 大：败
        ((0.5, 2.0, 0.5, 2.0), False),     # 并列且 Φ 同：不替换（先到先得仅此处）
        ((0.5, 1.5, 0.5, 2.0), True),      # 并列，Φ 小 0.5（>1e-9）：胜
        ((0.5, 2.0 - 1e-12, 0.5, 2.0), False),  # Φ 差在 1e-9 内：视为并列同值
    ]
    for args, expect in cases:
        got = partial_better(*args)
        assert got == expect, 'partial_better%r = %r，期望 %r' % (
            args, got, expect)
    print('[1] partial_better 规则矩阵 8/8 通过')


# ---------- 2. GUI 同源性：行为与规则函数一致 ----------

class _FakeSelf:
    """只带 _update_auto_best 需要的属性。"""

    def __init__(self):
        self._auto_best = None

    class game:
        m = n = 4


def test_gui_update_auto_best_same_rule():
    fake = _FakeSelf()
    upd = AutoSolveMixin._update_auto_best

    # 初始：无最优 → 直接采纳
    upd(fake, [(0, 0)], 0.5, 3.0)
    assert fake._auto_best['score'] == 0.5 and fake._auto_best['phi'] == 3.0
    # 严格低 → 不替换
    upd(fake, [(1, 1)], 0.4, 0.0)
    assert fake._auto_best['score'] == 0.5
    # 并列 Φ 小 → 替换（修复前 GUI 就有的行为，仍须保持）
    upd(fake, [(2, 2)], 0.5, 1.0)
    assert fake._auto_best['phi'] == 1.0
    # 并列 Φ 大 → 不替换
    upd(fake, [(3, 3)], 0.5, 2.0)
    assert fake._auto_best['phi'] == 1.0
    # 严格高 → 替换（Φ 大也换）
    upd(fake, [(4, 4)], 0.9, 9.0)
    assert fake._auto_best['score'] == 0.9

    # 与规则函数逐拍对照：随机序列下 GUI 选择 == 规则函数选择
    fake._auto_best = None   # 清掉固定段遗留，与 ref 同步起步
    rng = random.Random(42)
    ref = None  # (score, phi) 参照最优
    for _ in range(200):
        sc = round(rng.uniform(0, 1), 1)   # 粗量化逼出并列
        ph = float(rng.randint(0, 6))
        upd(fake, [(0, 0)], sc, ph)
        if ref is None or partial_better(sc, ph, ref[0], ref[1]):
            ref = (sc, ph)
        assert abs(fake._auto_best['score'] - ref[0]) < 1e-9
        assert abs(fake._auto_best['phi'] - ref[1]) < 1e-9
    print('[2] GUI _update_auto_best 与 partial_better 同源（200 拍对照）')


# ---------- 3. 真实局面：fill_partial 断点不差于任何已上报未解段 ----------

def _load_archive_coords(path):
    """从 GUI 存档取当前局面 coords（方形；matrix 为 0/1 网格 + bounds 偏移）。"""
    import json
    d = json.load(open(path, encoding='utf-8'))
    snap = d['history']['snapshots'][d['history']['history_index']]
    b = snap['bounds']
    coords = frozenset((r + b['min_row'], c + b['min_col'])
                       for r, row in enumerate(snap['matrix'])
                       for c, v in enumerate(row) if v)
    p = d['puzzle']
    return coords, p['m'], p['n'], p['step']


def test_fill_partial_not_worse_than_streamed(budget=30.0):
    """端到端契约（fixtures：save/死局存档 复制入库的真实死局）。

    对每个局面跑 auto_solve（流式），断言：
    · fill_partial → 必带 score/phi（协议增强），且在 partial_better 规则下
      不差于任何已上报未解段——否则说明择优又分裂回两处了；
    · 存在与断点完全一致的未解段（同一个 best，构造性保证的现场核对）；
    · fill_fail → 无 score/phi（契约另一分支，不受本次增强影响）。
    """
    import glob
    import os
    import time
    from solver.ml.fill_macro import build_game

    here = os.path.dirname(os.path.abspath(__file__))
    paths = sorted(glob.glob(os.path.join(here, 'fixtures', '*.json')))
    assert paths, 'fixtures 目录为空'
    n_partial = n_fail = 0
    for path in paths:
        coords, m, n, step = _load_archive_coords(path)
        g = build_game(coords, m, n)
        stages = []

        def cb(s):
            stages.append(s)

        t0 = time.time()

        def cc():
            return (time.time() - t0) >= budget

        r = auto_solve(g, step, stage_cb=cb, time_budget=budget,
                       cancel_check=cc)
        name = os.path.basename(path)
        if isinstance(r, dict) and r.get('type') == 'fill_partial':
            n_partial += 1
            assert 'score' in r and 'phi' in r, \
                '%s：fill_partial 缺 score/phi（协议回归）' % name
            unsolved = [s for s in stages if not s.get('solved')]
            assert unsolved, '%s：fill_partial 但无未解段上报' % name
            for s in unsolved:
                # 「r 不差于 s」= 「s 不严格好于 r」（partial_better 是
                # 严格更好，同值时返回 False，不能直接拿来断言「不差于」）
                ok = not partial_better(s['score'], s['phi'],
                                        r['score'], r['phi'])
                assert ok, ('%s：断点差于已上报段 %s：断点(%.3f, Φ%.1f) vs '
                            '段(%.3f, Φ%.1f)'
                            % (name, s['label'], r['score'], r['phi'],
                               s['score'], s['phi']))
            # 现场核对：必有一个未解段与断点完全一致（best 同源）
            same = [s for s in unsolved
                    if abs(s['score'] - r['score']) <= 1e-9
                    and abs(s['phi'] - r['phi']) <= 1e-9]
            assert same, '%s：无未解段与断点一致（best 不同源？）' % name
        elif isinstance(r, dict) and r.get('type') == 'fill_fail':
            n_fail += 1
            assert 'score' not in r and 'phi' not in r, \
                '%s：fill_fail 不应带 score/phi' % name
        else:
            raise AssertionError('%s：意外返回 %r' % (name, type(r)))
    print('[3] 端到端契约：fill_partial %d 局 / fill_fail %d 局，'
          '断点均不差于已上报段' % (n_partial, n_fail))


if __name__ == '__main__':
    test_partial_better_matrix()
    test_gui_update_auto_best_same_rule()
    test_fill_partial_not_worse_than_streamed()
    print('全部通过')
