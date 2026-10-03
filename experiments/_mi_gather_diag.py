# -*- coding: utf-8 -*-
"""诊断：mi 3x3 step=1 聚拢为何 0/6 复原（C3c 失败）。

要分清两种完全不同的解读，处置方式相反：

  (A) **时间不够**  —— score 曲线仍在上升、每步耗时高只是 4mn 块导致
      enumerate_actions 变慢。处置 = 加时间/步数预算，或加速枚举。
  (B) **贪心在 mi 上卡住** —— score 在中途平台上不再上升、每步都选不出
      改进动作。处置 = 打分函数/候选池有问题，是算法问题。

**只测现象、不改算法**（用户定方向不管实现，但「方向没价值」vs「时间不够」
的区分必须先做实）。三组对照：
  1. score 轨迹（每 N 步记一次）→ 看是否还在爬；
  2. 每步耗时剖分（枚举 / 应用 / 打分 / canonicalize）→ 看瓶颈在哪；
  3. 关掉时间上限只留步数上限 → 若分数大幅上去了，就是 (A)。

跑法：``D:/python/python.exe -u experiments/_mi_gather_diag.py``
"""
import random
import statistics
import sys
import time

sys.path.insert(0, '.')

from game_mi import MiSliderMatrix                      # noqa: E402
import solver.ml.mi_adapter as MA                      # noqa: E402


def _sg():
    """与生产入口 `mi_gather_solve` **完全同参**构造（都不传 canonicalize /
    mod_filter）—— 诊断必须复现真实失败路径，不能偷偷给更好的参数。"""
    from solver.ml.shape_gather import ShapeGather
    return ShapeGather(
        MA.shape_score, MA.enumerate_actions, MA.apply_action,
        MA.snap, MA.restore, coords_of=MA.mi_coords)


def track_curve(m, n, step, seed, shuf, max_steps, max_wait):
    """跑一局，記 score 軌跡 + 每步耗時（用 progress_callback 取 score，
    耗時在事後按總時長 / 步數近似 —— 這裡只為看「趨勢」，不需要精確剖分）。
    """
    from solver.ml.shape_gather import ShapeGather
    random.seed(seed)
    g = MiSliderMatrix(m, n)
    g.shuffle(shuf, step)
    spec = MA.MiSpec(m, n, step)
    curve = []
    sg = _sg()

    def cb(ev):
        curve.append((ev['step'], ev['score'], ev['best_score']))

    t0 = time.time()
    res = sg.solve(g, spec, step, max_steps=max_steps, patience=10 ** 9,
                   max_wait_time=max_wait, progress_callback=cb)
    el = time.time() - t0
    return res, curve, el


def section_timing(m, n, step, seed, shuf, n_probe=12):
    """拆一局的耗時：枚举 / apply / shape_score / canonicalize 各佔多少。

    直接照 `ShapeGather.solve` 的內循環順序手動跑 N 步並逐段計時 ——
    不改生產代碼，只在探針裡復刻循環（復刻點：候選枚舉 → 逐個試 →
    排序 → 執行）。
    """
    random.seed(seed)
    g = MiSliderMatrix(m, n)
    g.shuffle(shuf, step)
    spec = MA.MiSpec(m, n, step)
    sg = _sg()
    t_enum = t_apply = t_score = t_hash = 0.0
    n_cand = []
    steps_done = 0
    for i in range(n_probe):
        if g.is_solved():
            break
        t0 = time.time()
        cands = MA.enumerate_actions(g, step)
        t_enum += time.time() - t0
        n_cand.append(len(cands))
        snap0 = MA.snap(g)
        n_cells = len(MA.mi_coords(g))
        scored = []
        for act in cands:
            t0 = time.time()
            ok = MA.apply_action(g, act, step)
            t_apply += time.time() - t0
            if not ok:
                MA.restore(g, snap0)
                continue
            nc = MA.mi_coords(g)
            if len(nc) != n_cells:
                MA.restore(g, snap0)
                continue
            t0 = time.time()
            s = MA.shape_score(nc, spec)
            t_score += time.time() - t0
            # 用 frozenset 当 canonicalize 的替身只为**计时这一段的量级**。
            # 生产入口本来就没传 canonicalize（骨架退化成 coords_of 本身），
            # 这里保持同一条路径，测出来的才是真实耗时。
            t0 = time.time()
            h = frozenset(nc)
            t_hash += time.time() - t0
            scored.append((s, act))
            MA.restore(g, snap0)
        if not scored:
            break
        scored.sort(key=lambda x: (-x[0], x[1]))
        MA.restore(g, snap0)
        MA.apply_action(g, scored[0][1], step)
        steps_done += 1
    return {'enum': t_enum, 'apply': t_apply, 'score': t_score,
            'hash': t_hash, 'n_cand': n_cand, 'steps': steps_done}


def main():
    print('=== 實驗 1：score 軌跡（patience 放到無限，看是「爬不上去」还是'
          '「沒時間」）===')
    for tag, max_steps, max_wait in (('短预算', 300, 25.0),
                                     ('长预算', 3000, 240.0)):
        rows = []
        for seed in range(3):
            res, curve, el = track_curve(3, 3, 1, seed, 60,
                                         max_steps, max_wait)
            marks = [f'{c[0]}:{c[2]:.3f}' for c in curve
                     if c[0] % max(1, len(curve) // 8) == 0]
            rows.append((res['solved'], res['best_score'], res['steps'],
                         el, res['reason'], marks))
            print(f'  [{tag}] seed={seed} solved={res["solved"]} '
                  f'best={res["best_score"]:.3f} steps={res["steps"]} '
                  f'{el:.1f}s reason={res["reason"]}')
            print(f'          軌跡 {marks}')
        print(f'  [{tag}] 小結 還原 {sum(1 for r in rows if r[0])}/3，'
              f'均 best {statistics.mean(r[1] for r in rows):.3f}，'
              f'均 {statistics.mean(r[3] for r in rows):.1f}s')
        print()

    print('=== 實驗 2：耗時剖分（3x3 step=1，12 步）===')
    for step in (1, 2):
        tm = section_timing(3, 3, step, 0, 60, n_probe=12)
        tot = tm['enum'] + tm['apply'] + tm['score'] + tm['hash']
        if tot <= 0:
            continue
        print(f'  step={step}: {tm["steps"]} 步耗 {tot:.2f}s '
              f'(每步 {tot / max(1, tm["steps"]):.3f}s)')
        for k in ('enum', 'apply', 'score', 'hash'):
            print(f'      {k:6s} {tm[k] * 1000 / max(1, tm["steps"]):7.1f} '
                  f'ms/步  ({tm[k] / tot * 100:4.1f}%)')
        print(f'      候選數 {tm["n_cand"]}')

    print()
    print('=== 實驗 3：候選動作數 vs 方形的量級對比 ===')
    for step in (1, 2):
        random.seed(0)
        g = MiSliderMatrix(3, 3, 3)
        g.shuffle(60, step)
        t0 = time.time()
        acts = MA.enumerate_actions(g, step)
        dt = time.time() - t0
        print(f'  mi 3x3x3 step={step}: {len(acts)} 個候選，枚舉 {dt * 1000:.0f}ms')
    from game import SliderMatrix
    from solver.actions import enumerate_valid_actions
    random.seed(0)
    gs = SliderMatrix(3, 3)
    gs.shuffle(60)
    t0 = time.time()
    acts_s = enumerate_valid_actions(gs, 1)
    dt = time.time() - t0
    print(f'  方形 3x3 step=1: {len(acts_s)} 個候選，枚舉 {dt * 1000:.0f}ms')


if __name__ == '__main__':
    main()
