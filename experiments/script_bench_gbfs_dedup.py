# -*- coding: utf-8 -*-
"""GBFS 等价去重（A1 堆条目复用入堆值 + A3 父指针去路径拷贝）的差分 + ABAB 验收。

背景（2026-11-07 端到端画像，5×5 seed1000）：guided_reduce_one 占 hybrid
~71%，其中 canonicalize ~19%、fast_window ~14%——但**出堆侧约一半是入堆刚
算过的同值重算**（cProfile 放大了呼叫型函数的占比，墙钟收益要实测）。
本脚本：
  1. 差分：同一状态/同一局，旧版 vs 新版返回路径/解必须逐位一致；
  2. ABAB 逐轮配对（交替先后，抵消机器漂移）：
     · GBFS 层：固定 6×6 状态 budget=3000（隔离 gather/重放方差，主力指标）
     · 端到端：5×5 两局 hybrid_solve 全链（体感指标）
  3. 结果落盘 _bench_gbfs_dedup_out.txt（临时产物、未入库）。
  4. **抽象图深层差分**（2026-11-09 审查补）：真实局面几乎都是
     `ex=1`（走一步就填掉一个洞），父指针回溯 / closed / bestg 根本没被覆盖，
     「零差异」证明力很弱。把四个几何依赖换成可控图，强迫走出 8 层路径、
     展开数百节点，再与逐字旧版逐位对比。

跑法：python experiments/script_bench_gbfs_dedup.py [--rounds 8]
"""
import argparse
import heapq
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game import SliderMatrix                                    # noqa: E402
from solver.ml.fill_macro import build_game                      # noqa: E402
from solver.hybrid_solver import hybrid_solve                    # noqa: E402
import solver.hybrid_solver as hs                                # noqa: E402
import solver.search_core as sc                                  # noqa: E402
from solver.search_core import (expand, fast_window,             # noqa: E402
                                canonicalize)

OUT = os.path.join(ROOT, 'experiments', '_bench_gbfs_dedup_out.txt')


# ---------------------------------------------------------------------------
# 旧版实现（逐字取自改动前 search_core，作为 A/B 的 A；启发为旧 heuristic）
# ---------------------------------------------------------------------------
def old_heuristic(coords, m, n, step):
    _win, holes, protr = fast_window(coords, m, n)
    h = len(holes)
    for p in protr:
        if holes:
            d = min(abs(p[0] - q[0]) + abs(p[1] - q[1]) for q in holes)
            h += max(1, d // step)
    return h


def old_guided_reduce_one(coords, m, n, step, budget=80000,
                          cancel_check=None, progress_cb=None,
                          progress_every=2000):
    start = frozenset(coords)
    h0 = len(fast_window(start, m, n)[1])
    counter = 0
    openq = [(h0, 0, 0, start, [])]
    bestg = {canonicalize(start): 0}
    closed = set()
    expanded = 0
    while openq:
        _f, g, _, cur, path = heapq.heappop(openq)
        ck = canonicalize(cur)
        if g > bestg.get(ck, -1) or ck in closed:
            continue
        if len(fast_window(cur, m, n)[1]) < h0:
            return path, expanded
        closed.add(ck)
        expanded += 1
        if progress_cb is not None and expanded % progress_every == 0:
            progress_cb(expanded)
        if expanded > budget or (cancel_check and cancel_check()):
            return None, expanded
        for new, act, rep in expand(cur, step):
            nk = canonicalize(new)
            ng = g + 1
            if ng >= bestg.get(nk, 10 ** 9):
                continue
            bestg[nk] = ng
            counter += 1
            heapq.heappush(openq, (old_heuristic(new, m, n, step), ng,
                                   counter, new, path + [(act, rep)]))
    return None, expanded


# ---------------------------------------------------------------------------
# 语料
# ---------------------------------------------------------------------------
def coords_of(m, n, seed, attempts):
    random.seed(seed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=2)
    return frozenset(tuple(b.location) for b in g.blocks)


def abstract_diff():
    """抽象图差分：把 search_core 的几何依赖换成可控图，逼出深层回溯。

    状态 = frozenset({编号})；洞数 = hval[编号]；expand 给出有向边。
    0→1→…→8 是一条洞数恒为 h0 的链，末端才降到 1 ⇒ 必须回溯 8 层父指针
    才能拼出路径；seed99 把目标洞数抹掉，逼搜索把整张图跑到堆空。
    返回 (日志行, 差异数, 最大展开数, 最长路径)。
    """
    def build(seed, size=500):
        rng = random.Random(seed)
        hval = [rng.choice([3, 3, 3, 4, 4, 5]) for _ in range(size)]
        hval[0] = 3
        edges = {}
        for s in range(size):
            tgt = set(rng.randint(1, size - 1)
                      for _ in range(rng.randint(1, 3)))
            tgt.discard(s)
            edges[frozenset({s})] = [(frozenset({t}), ('mv', s, t), None)
                                     for t in sorted(tgt)]
        for i in range(8):
            edges[frozenset({i})].append(
                (frozenset({i + 1}), ('chain', i, i + 1), None))
            hval[i] = 3
        hval[8] = 1
        return hval, edges

    def idx(s):
        return next(iter(s))

    self_mod = sys.modules[__name__]       # 旧版实现就在本模块全局
    saved = {mod: {k: getattr(mod, k) for k in
                   ('expand', 'fast_window', 'canonicalize')}
             for mod in (sc, self_mod)}
    saved_hp = sc.heuristic_parts
    lines, diffs, exs, paths = [], 0, [], []
    try:
        for seed in (7, 17, 29, 43, 61, 99):
            hval, edges = build(seed)
            if seed == 99:                     # 无解图：跑满整张图
                hval = [max(v, 3) for v in hval]

            def fw(coords, m, n, _h=hval):
                return None, [0] * _h[idx(coords)], []

            def ex(cur, step, _e=edges):
                return _e.get(cur, [])

            def canon(s):
                return s

            def hp(coords, m, n, step, _h=hval):
                v = _h[idx(coords)]
                return v, v

            for mod in (sc, self_mod):
                mod.expand, mod.fast_window, mod.canonicalize = ex, fw, canon
            sc.heuristic_parts = hp
            st = frozenset({0})
            po, xo = old_guided_reduce_one(st, 4, 4, 2, budget=10000)
            pn, xn = sc.guided_reduce_one(st, 4, 4, 2, budget=10000)
            same = (po == pn and xo == xn)
            diffs += (not same)
            exs.append(xo)
            paths.append(len(pn or []))
            lines.append('[抽象图] seed%-3d ex=%-5d path=%-3s %s'
                         % (seed, xo, len(pn) if pn else None,
                            'SAME' if same else '**DIFF**'))
    finally:
        for mod, orig in saved.items():
            for k, v in orig.items():
                setattr(mod, k, v)
        sc.heuristic_parts = saved_hp
    return lines, diffs, max(exs), max(paths)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=8)
    args = ap.parse_args()
    lines = []
    fails = 0

    def log(s):
        print(s, flush=True)
        lines.append(s)

    # ---- 语料（固定） ----
    c66 = coords_of(6, 6, 2, 150)
    e2e = [(5, 5, 11), (5, 5, 5)]

    # ---- 1. 差分：GBFS 层（固定 6×6 状态） ----
    #    ⚠️ 2026-11-09 审查：真实局面通常 ex=1（一步就填掉一个洞），
    #    这条差分只能证明浅层一致；深层回溯靠下面 1b 的抽象图差分。
    #    另：所谓「改动前采的基线 JSON」不在仓库里，无法复核，别当证据。
    for budget in (3000,):
        p_old, ex_old = old_guided_reduce_one(c66, 6, 6, 2, budget=budget)
        p_new, ex_new = sc.guided_reduce_one(c66, 6, 6, 2, budget=budget)
        same = (p_old == p_new and ex_old == ex_new)
        log('[差分] GBFS 6x6 budget=%d: old(ex=%d,len=%s) new(ex=%d,len=%s) '
            '→ %s' % (budget, ex_old,
                      len(p_old) if p_old else None, ex_new,
                      len(p_new) if p_new else None,
                      'SAME' if same else '**DIFF**'))
        if not same:
            fails += 1

    # ---- 1b. 抽象图深层差分（父指针回溯 / closed / bestg） ----
    ad_lines, ad_diffs, ad_ex, ad_path = abstract_diff()
    for line in ad_lines:
        log(line)
    log('[抽象图] 覆盖：最大展开 %d 节点、最长路径 %d 步' % (ad_ex, ad_path))
    ad_ok = (ad_diffs == 0 and ad_ex >= 100 and ad_path >= 4)
    log('[抽象图] %s' % ('全部逐位一致且覆盖深层回溯'
                       if ad_ok else '**FAIL** 差异=%d' % ad_diffs))
    if not ad_ok:
        fails += 1

    # ---- 2. 差分：端到端（5×5 两局全链） ----
    e2e_results = {}
    for m, n, seed in e2e:
        coords = coords_of(m, n, seed, 150)
        res = hybrid_solve(build_game(coords, m, n), 2,
                           cancel_check=lambda: False)
        e2e_results[(m, n, seed)] = (coords, res)
        # 新版已替换生产实现；旧版端到端用「旧 GBFS + 生产其余部分」无法在
        # 单进程共存（hybrid 直接 import 生产 guided_reduce_one）。端到端差分
        # 已由 Temp 的基线 JSON（改动前采）覆盖，这里只记录新版耗时供 ABAB。
        log('[e2e] %dx%d seed%d 新版 %d 步（基线见 Temp JSON）'
            % (m, n, seed, len(res[0]) if isinstance(res, tuple) else -1))

    # ---- 3. ABAB：GBFS 层固定状态（主力指标，交替先后） ----
    #    指标：3000 预算内 expanded 数相同（确定性）+ 墙钟配对
    gbfs_old, gbfs_new = [], []
    for r in range(args.rounds):
        order = ('old', 'new') if r % 2 == 0 else ('new', 'old')
        for which in order:
            t0 = time.time()
            if which == 'old':
                p, ex = old_guided_reduce_one(c66, 6, 6, 2, budget=3000)
                gbfs_old.append(time.time() - t0)
            else:
                p, ex = sc.guided_reduce_one(c66, 6, 6, 2, budget=3000)
                gbfs_new.append(time.time() - t0)
        log('[ABAB] r%-2d order=%s  old=%.2fs  new=%.2fs'
            % (r, order[0], gbfs_old[-1] if order[0] == 'old' else gbfs_new[-1],
               gbfs_new[-1] if order[0] == 'old' else gbfs_old[-1]))

    wins = sum(1 for a, b in zip(gbfs_old, gbfs_new) if b < a)
    mo = sorted(gbfs_old)[len(gbfs_old) // 2]
    mn = sorted(gbfs_new)[len(gbfs_new) // 2]
    log('[ABAB] GBFS 层（3000 预算，%d 对）：旧中位 %.2fs / 新中位 %.2fs → '
        '%.3fx，新胜 %d/%d 轮'
        % (len(gbfs_old), mo, mn, mo / mn if mn else 0, wins, len(gbfs_old)))

    # ---- 4. ABAB：端到端 5×5（体感指标） ----
    e_old, e_new = [], []
    for r in range(args.rounds):
        order = ('old', 'new') if r % 2 == 0 else ('new', 'old')
        for which in order:
            for m, n, seed in e2e:
                coords = coords_of(m, n, seed, 150)
                t0 = time.time()
                if which == 'old':
                    # 旧版端到端 = 旧 GBFS（其余环节两版共用、无改动）。
                    # ⚠️ hybrid 是 `from ... import guided_reduce_one` 的
                    # 模块绑定，要 patch hybrid_solver 命名空间才生效。
                    _old = hs.guided_reduce_one
                    hs.guided_reduce_one = old_guided_reduce_one
                    try:
                        hybrid_solve(build_game(coords, m, n), 2,
                                     cancel_check=lambda: False)
                    finally:
                        hs.guided_reduce_one = _old
                    e_old.append(time.time() - t0)
                else:
                    hybrid_solve(build_game(coords, m, n), 2,
                                 cancel_check=lambda: False)
                    e_new.append(time.time() - t0)
        log('[ABAB-e2e] r%-2d order=%s  old=%.2fs  new=%.2fs'
            % (r, order[0], e_old[-1], e_new[-1]))

    wins2 = sum(1 for a, b in zip(e_old, e_new) if b < a)
    mo2 = sorted(e_old)[len(e_old) // 2]
    mn2 = sorted(e_new)[len(e_new) // 2]
    log('[ABAB-e2e] 端到端（%d 对）：旧中位 %.2fs / 新中位 %.2fs → %.3fx，'
        '新胜 %d/%d 轮'
        % (len(e_old), mo2, mn2, mo2 / mn2 if mn2 else 0, wins2, len(e_old)))

    log('==== ' + ('全部差分零差异' if fails == 0 else '%d 项差分失败!' % fails))
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('results ->', OUT)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
